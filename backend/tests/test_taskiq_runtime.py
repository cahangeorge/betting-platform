import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.tasks import runtime, scheduler


@pytest.mark.parametrize(
    ("module_name", "symbols"),
    [
        (
            "app.tasks.jobs",
            (
                "execute_scheduled_job_run_task",
                "execute_scrape_job_task",
                "execute_world_cup_pipeline_task",
                "poll_due_scheduled_jobs_task",
                "taskiq_healthcheck_task",
            ),
        ),
        ("app.tasks.trading", ("execute_trading_intent_task",)),
    ],
)
def test_task_modules_keep_canonical_names_when_loaded_from_an_absolute_script_path(
    module_name,
    symbols,
):
    module_path = Path(__file__).parents[1].joinpath(*module_name.split(".")).with_suffix(".py")
    script = f"""
import runpy
import sys

module_path = {str(module_path.resolve())!r}
sys.argv[0] = module_path
namespace = runpy.run_path(module_path, run_name="__main__")
expected = {{
    symbol: f"{module_name}:{{symbol}}"
    for symbol in {symbols!r}
}}
actual = {{symbol: namespace[symbol].task_name for symbol in expected}}
if actual != expected:
    raise SystemExit(f"non-canonical Taskiq names: {{actual!r}}")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=module_path.parents[2],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.asyncio
async def test_task_queue_probe_checks_each_distinct_redis_endpoint(monkeypatch):
    ping = AsyncMock()
    monkeypatch.setattr(runtime, "_ping_redis", ping)

    await runtime.task_queue_probe("redis://queue/0", "redis://results/1")

    assert ping.await_args_list == [
        (("redis://queue/0",), {}),
        (("redis://results/1",), {}),
    ]


@pytest.mark.asyncio
async def test_task_queue_probe_deduplicates_shared_redis_endpoint(monkeypatch):
    ping = AsyncMock()
    monkeypatch.setattr(runtime, "_ping_redis", ping)

    await runtime.task_queue_probe("redis://shared/0", "redis://shared/0")

    ping.assert_awaited_once_with("redis://shared/0")


@pytest.mark.asyncio
async def test_runtime_heartbeat_is_role_and_instance_specific(monkeypatch):
    heartbeat_written = asyncio.Event()

    class FakeRedis:
        deleted: list[str] = []

        async def set(self, key, value, *, ex):
            assert key == "bet:taskiq:worker:test-instance"
            assert value == "ready"
            assert ex == runtime.settings.taskiq_runtime_stale_seconds
            heartbeat_written.set()

        async def delete(self, key):
            self.deleted.append(key)

        async def aclose(self):
            return None

    client = FakeRedis()
    monkeypatch.setenv("BET_TASKIQ_INSTANCE_ID", "test-instance")
    monkeypatch.setattr(runtime.Redis, "from_url", lambda _url: client)

    task = asyncio.create_task(runtime.runtime_heartbeat("worker"))
    await asyncio.wait_for(heartbeat_written.wait(), timeout=1)
    await runtime.stop_runtime_heartbeat(task)

    assert client.deleted == ["bet:taskiq:worker:test-instance"]


@pytest.mark.asyncio
async def test_verify_runtime_role_rejects_a_missing_instance_heartbeat(monkeypatch):
    class FakeRedis:
        async def get(self, key):
            assert key == "bet:taskiq:scheduler:test-instance"
            return None

        async def aclose(self):
            return None

    monkeypatch.setenv("BET_TASKIQ_INSTANCE_ID", "test-instance")
    monkeypatch.setattr(runtime.Redis, "from_url", lambda _url: FakeRedis())

    with pytest.raises(RuntimeError, match="scheduler heartbeat is stale or missing"):
        await runtime.verify_runtime_role("scheduler")


@pytest.mark.asyncio
async def test_deployment_readiness_accepts_role_heartbeats_from_other_container_hostnames(monkeypatch):
    class FakeRedis:
        async def scan_iter(self, *, match, count):
            assert count == 100
            keys = {
                "bet:taskiq:worker:*": ["bet:taskiq:worker:worker-container"],
                "bet:taskiq:scheduler:*": ["bet:taskiq:scheduler:scheduler-container"],
            }[match]
            for key in keys:
                yield key

        async def get(self, key):
            return "ready" if key.endswith(("worker-container", "scheduler-container")) else None

        async def aclose(self):
            return None

    monkeypatch.setenv("BET_TASKIQ_INSTANCE_ID", "api-container")
    monkeypatch.setattr(runtime.Redis, "from_url", lambda _url: FakeRedis())

    await runtime.verify_any_runtime_role("worker")
    await runtime.verify_any_runtime_role("scheduler")


@pytest.mark.asyncio
async def test_scheduler_reconciles_outbox_before_publishing_poll(monkeypatch):
    calls: list[str] = []

    class StopLoopError(Exception):
        pass

    class FakeDb:
        async def commit(self):
            calls.append("commit")

    class FakeSession:
        async def __aenter__(self):
            return FakeDb()

        async def __aexit__(self, *_args):
            return None

    async def fake_requeue(_db):
        calls.append("requeue")

    async def fake_reconcile(_db):
        calls.append("reconcile")

    async def fake_kiq():
        calls.append("publish-poll")

    async def stop_after_one_iteration(_seconds):
        raise StopLoopError

    monkeypatch.setattr(scheduler, "async_session_factory", FakeSession)
    monkeypatch.setattr(scheduler, "requeue_expired_task_run_leases", fake_requeue)
    monkeypatch.setattr(scheduler, "reconcile_task_outbox", fake_reconcile)
    monkeypatch.setattr(scheduler.poll_due_scheduled_jobs_task, "kiq", fake_kiq)
    monkeypatch.setattr(scheduler.asyncio, "sleep", stop_after_one_iteration)

    with pytest.raises(StopLoopError):
        await scheduler.scheduler_loop()

    assert calls == ["requeue", "reconcile", "commit", "publish-poll"]


@pytest.mark.asyncio
async def test_enabled_worker_role_readiness_requires_all_durable_lanes(monkeypatch):
    checked: list[str] = []

    async def fake_verify(role: str):
        checked.append(role)

    monkeypatch.setattr(runtime, "verify_any_runtime_role", fake_verify)

    await runtime.verify_enabled_worker_roles()

    assert checked == [
        "worker:control",
        "worker:provider-http",
        "worker:provider-browser",
        "worker:model-cpu",
    ]


@pytest.mark.asyncio
async def test_enabled_worker_role_readiness_checks_only_the_configured_ordered_subset(monkeypatch):
    checked: list[str] = []

    async def fake_verify(role: str):
        checked.append(role)

    monkeypatch.setattr(runtime.settings, "taskiq_enabled_lanes", ("control", "model-cpu"))
    monkeypatch.setattr(runtime, "verify_any_runtime_role", fake_verify)

    await runtime.verify_enabled_worker_roles()

    assert checked == ["worker:control", "worker:model-cpu"]


def test_cgroup_resource_snapshot_reads_v2_counters_or_degrades(tmp_path):
    (tmp_path / "memory.peak").write_text("123\n", encoding="utf-8")
    (tmp_path / "pids.peak").write_text("4\n", encoding="utf-8")
    assert runtime.cgroup_resource_snapshot(str(tmp_path)) == {"peak_rss_bytes": 123, "peak_pid_count": 4}
    assert runtime.cgroup_resource_snapshot(str(tmp_path / "unsupported")) == {
        "peak_rss_bytes": None,
        "peak_pid_count": None,
    }
