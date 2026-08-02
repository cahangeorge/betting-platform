from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import scheduled_jobs, task_runs
from app.services.task_runs import WorkerLaneAdmissionClosedError, create_task_run
from app.services.worker_observability import (
    WorkerLaneSnapshot,
    collect_worker_lane_snapshot,
    evaluate_worker_lane_alerts,
)
from app.tasks import jobs
from app.tasks.worker_lanes import (
    LEGACY_WORKER_CONTRACT_VERSION,
    WORKER_LANE_CONTRACT_VERSION,
    WorkerLane,
    admitted_worker_lanes,
    backlog_cap_for_lane,
    is_worker_lane_admitted,
    is_worker_lane_enabled,
    lane_for_operation,
)


def test_explicit_operation_registry_does_not_infer_provider_names():
    assert lane_for_operation("scrape_job") is WorkerLane.PROVIDER_BROWSER
    assert lane_for_operation("run_predictions") is WorkerLane.MODEL_CPU
    assert lane_for_operation("soccerdata_http_ingest") is WorkerLane.PROVIDER_HTTP
    assert lane_for_operation("fetch_latest_odds") is WorkerLane.PROVIDER_HTTP
    assert lane_for_operation("soccerdata_browser_ingest") is WorkerLane.PROVIDER_BROWSER
    # The composite legacy pipeline remains on the safe control envelope until
    # it is decomposed into independently idempotent stages.
    assert lane_for_operation("world_cup_pipeline") is WorkerLane.CONTROL
    with pytest.raises(ValueError, match="No approved worker-lane contract"):
        lane_for_operation("my_scraper_like_name")


def test_licensed_odds_lease_uses_provider_http_lane_not_browser_timeout():
    run = SimpleNamespace(task_type="fetch_latest_odds")
    expected = max(
        scheduled_jobs.settings.task_run_lease_seconds,
        scheduled_jobs.worker_lane_spec(WorkerLane.PROVIDER_HTTP).timeout_seconds + 60,
    )

    assert scheduled_jobs._task_run_lease_seconds(run) == expected


def test_backlog_caps_are_lane_specific_and_match_the_staged_capacity_contract():
    from app.config import Settings

    settings = Settings(_env_file=None)

    assert {lane: backlog_cap_for_lane(settings, lane) for lane in WorkerLane} == {
        WorkerLane.CONTROL: 1_000,
        WorkerLane.PROVIDER_HTTP: 200,
        WorkerLane.PROVIDER_BROWSER: 50,
        WorkerLane.MODEL_CPU: 50,
    }


def test_enabled_provider_workers_can_drain_while_admission_remains_control_only():
    from app.config import Settings

    settings = Settings(
        _env_file=None,
        taskiq_enabled_lanes="control,provider-http,provider-browser,model-cpu",
        taskiq_admitted_lanes="control",
    )

    assert WorkerLane.PROVIDER_BROWSER not in admitted_worker_lanes(settings)
    assert is_worker_lane_enabled(settings, WorkerLane.PROVIDER_BROWSER) is True
    assert is_worker_lane_admitted(settings, WorkerLane.PROVIDER_BROWSER) is False
    assert is_worker_lane_admitted(settings, WorkerLane.CONTROL) is True


@pytest.mark.asyncio
async def test_new_provider_work_is_rejected_before_any_database_admission(monkeypatch):
    monkeypatch.setattr(task_runs.settings, "taskiq_admitted_lanes", ("control",))

    with pytest.raises(WorkerLaneAdmissionClosedError, match="provider-browser.*not admitted"):
        await create_task_run(SimpleNamespace(), task_type="scrape_job")


@pytest.mark.asyncio
async def test_taskiq_publish_uses_dynamic_lane_label_and_run_id_only(monkeypatch):
    sent: list[tuple[dict[str, str], tuple[int, ...], dict]] = []

    class FakeKicker:
        def with_labels(self, **labels):
            self.labels = labels
            return self

        async def kiq(self, *args, **kwargs):
            sent.append((self.labels, args, kwargs))
            return SimpleNamespace(task_id="task-42")

    class FakeTask:
        def kicker(self):
            return FakeKicker()

    import app.tasks.jobs as task_jobs

    monkeypatch.setattr(task_jobs, "execute_scrape_job_task", FakeTask())
    run = SimpleNamespace(
        id=42,
        queue_lane="provider-browser",
        queue_contract_version=WORKER_LANE_CONTRACT_VERSION,
    )

    task_id = await scheduled_jobs._send_taskiq_run(run, task_name="scrape_job")

    assert task_id == "task-42"
    assert sent == [({"queue_name": "bet-provider-browser"}, (42,), {})]


@pytest.mark.asyncio
async def test_taskiq_publish_drains_existing_work_when_new_admission_is_closed(monkeypatch):
    sent: list[int] = []

    class FakeKicker:
        def with_labels(self, **_labels):
            return self

        async def kiq(self, run_id):
            sent.append(run_id)
            return SimpleNamespace(task_id="drain-42")

    class FakeTask:
        def kicker(self):
            return FakeKicker()

    import app.tasks.jobs as task_jobs

    monkeypatch.setattr(task_jobs, "execute_scrape_job_task", FakeTask())
    run = SimpleNamespace(
        id=42,
        queue_lane="provider-browser",
        queue_contract_version=WORKER_LANE_CONTRACT_VERSION,
    )
    monkeypatch.setattr(
        scheduled_jobs.settings,
        "taskiq_enabled_lanes",
        ("control", "provider-http", "provider-browser", "model-cpu"),
    )
    monkeypatch.setattr(scheduled_jobs.settings, "taskiq_admitted_lanes", ("control",))

    assert await scheduled_jobs._send_taskiq_run(run, task_name="scrape_job") == "drain-42"
    assert sent == [42]


@pytest.mark.asyncio
async def test_taskiq_publish_allows_legacy_control_when_only_control_is_enabled(monkeypatch):
    sent: list[tuple[dict[str, str], tuple[int, ...]]] = []

    class FakeKicker:
        def with_labels(self, **labels):
            self.labels = labels
            return self

        async def kiq(self, *args):
            sent.append((self.labels, args))
            return SimpleNamespace(task_id="legacy-control")

    class FakeTask:
        def kicker(self):
            return FakeKicker()

    import app.tasks.jobs as task_jobs

    monkeypatch.setattr(task_jobs, "execute_world_cup_pipeline_task", FakeTask())
    monkeypatch.setattr(scheduled_jobs.settings, "taskiq_enabled_lanes", ("control",))
    run = SimpleNamespace(
        id=43,
        queue_lane="control",
        queue_contract_version=LEGACY_WORKER_CONTRACT_VERSION,
    )

    task_id = await scheduled_jobs._send_taskiq_run(run, task_name="world_cup_pipeline")

    assert task_id == "legacy-control"
    assert sent == [({"queue_name": "bet"}, (43,))]


@pytest.mark.asyncio
async def test_healthcheck_delay_is_bounded_for_controlled_hol_probe():
    assert await jobs.taskiq_healthcheck_task("ok", delay_seconds=0) == "ok"
    with pytest.raises(ValueError, match="between 0 and 5"):
        await jobs.taskiq_healthcheck_task("bad", delay_seconds=6)


@pytest.mark.asyncio
async def test_worker_rejects_wrong_lane_and_accepts_legacy_control(monkeypatch):
    class FakeSession:
        def __init__(self, run):
            self.run = run

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _model, _run_id):
            return self.run

    monkeypatch.setattr(jobs, "worker_lane", WorkerLane.CONTROL)
    browser_run = SimpleNamespace(
        id=11, queue_lane="provider-browser", queue_contract_version=WORKER_LANE_CONTRACT_VERSION
    )
    monkeypatch.setattr(jobs, "async_session_factory", lambda: FakeSession(browser_run))
    with pytest.raises(RuntimeError, match="belongs to lane"):
        await jobs.validate_task_run_lane(11)

    legacy_run = SimpleNamespace(id=12, queue_lane="control", queue_contract_version=LEGACY_WORKER_CONTRACT_VERSION)
    monkeypatch.setattr(jobs, "async_session_factory", lambda: FakeSession(legacy_run))
    assert await jobs.validate_task_run_lane(12) is legacy_run


@pytest.mark.asyncio
async def test_lease_reaper_resets_delivery_generation_without_creating_outbox():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    run = SimpleNamespace(
        id=9,
        status="running",
        queue_contract_version=WORKER_LANE_CONTRACT_VERSION,
        lease_expires_at=now - timedelta(seconds=1),
        attempt=1,
        max_attempts=2,
        execution_token="lost-token",
        queue_lane="provider-http",
    )
    outbox = SimpleNamespace(
        id=2,
        run_id=9,
        queue_lane="provider-http",
        queue_contract_version=WORKER_LANE_CONTRACT_VERSION,
        delivery_generation=1,
        attempts=3,
        status="published",
        available_at=None,
        last_error=None,
    )

    class Result:
        def __init__(self, rows=(), scalar=None):
            self.rows = list(rows)
            self.scalar = scalar

        def scalars(self):
            return SimpleNamespace(all=lambda: self.rows)

        def scalar_one_or_none(self):
            return self.scalar

    class FakeDb:
        def __init__(self):
            self.calls = 0
            self.flushes = 0

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        async def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return Result(rows=[run])
            return Result(scalar=outbox if self.calls == 2 else run)

        async def flush(self):
            self.flushes += 1

    db = FakeDb()
    recovered = await scheduled_jobs.requeue_expired_task_run_leases(db, now=now)

    assert recovered == [run]
    assert run.status == "queued"
    assert run.execution_token is None
    assert (outbox.delivery_generation, outbox.attempts, outbox.status) == (2, 0, "pending")
    assert db.flushes == 1


def test_lane_alerts_activate_and_recover_with_stable_codes():
    unhealthy = WorkerLaneSnapshot(
        lane=WorkerLane.PROVIDER_BROWSER,
        queued=4,
        running=1,
        oldest_queue_age_ms=3_660_001,
        sampled_terminal_runs=4,
        retries=2,
        fallbacks=2,
        freshness_failures=1,
        peak_rss_bytes=4 * 1024**3 + 1,
        peak_pid_count=513,
    )
    assert evaluate_worker_lane_alerts(unhealthy) == (
        "queue_age_high",
        "rss_high",
        "pid_high",
        "retry_rate_high",
        "fallback_rate_high",
        "freshness_failure",
    )

    recovered = WorkerLaneSnapshot(
        lane=WorkerLane.PROVIDER_BROWSER,
        queued=0,
        running=0,
        oldest_queue_age_ms=0,
        sampled_terminal_runs=4,
        retries=0,
        fallbacks=0,
        freshness_failures=0,
        peak_rss_bytes=1024,
        peak_pid_count=1,
    )
    assert evaluate_worker_lane_alerts(recovered) == ()


@pytest.mark.asyncio
async def test_lane_snapshot_collects_queue_retry_fallback_and_freshness_metrics():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    active = [
        SimpleNamespace(
            status="queued",
            queued_at=now - timedelta(seconds=3),
            attempt=1,
            metrics=None,
            peak_rss_bytes=None,
            peak_pid_count=None,
        ),
        SimpleNamespace(
            status="running",
            queued_at=now - timedelta(seconds=1),
            attempt=1,
            metrics={"fallback_count": 1},
            peak_rss_bytes=100,
            peak_pid_count=2,
        ),
    ]
    terminal = [
        SimpleNamespace(
            status="failed",
            queued_at=now,
            attempt=3,
            metrics={"fallback_count": 2, "freshness_status": "stale"},
            peak_rss_bytes=120,
            peak_pid_count=3,
        )
    ]

    class ScalarRows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class SnapshotDb:
        def __init__(self):
            self.rows = iter((active, terminal))

        async def scalars(self, _statement):
            return ScalarRows(next(self.rows))

    snapshot = await collect_worker_lane_snapshot(SnapshotDb(), WorkerLane.PROVIDER_HTTP, now=now)

    assert (snapshot.queued, snapshot.running, snapshot.oldest_queue_age_ms) == (1, 1, 3000)
    assert (snapshot.retries, snapshot.fallbacks, snapshot.freshness_failures) == (2, 3, 1)
    assert (snapshot.peak_rss_bytes, snapshot.peak_pid_count) == (120, 3)


def test_execution_failure_classifier_retries_only_timeout_or_explicit_typed_signal():
    from app.services.task_runs import TransientTaskRunError, classify_execution_failure

    assert classify_execution_failure(TimeoutError()) == "timeout"
    assert classify_execution_failure(TransientTaskRunError("provider_429", "rate limited")) == "provider_429"
    assert classify_execution_failure(RuntimeError("provider returned 429 text")) == "internal"


def test_retry_backoff_is_deterministic_and_lane_bounded():
    from app.services.task_runs import next_task_retry_at

    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    run = SimpleNamespace(id=77, queue_lane="provider-browser", attempt=2)
    first = next_task_retry_at(run, "timeout", now=now)
    second = next_task_retry_at(run, "timeout", now=now)

    assert first == second
    assert 60 <= (first - now).total_seconds() <= 72
