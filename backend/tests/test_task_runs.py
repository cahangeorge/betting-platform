import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import scheduled_jobs
from app.services.task_runs import (
    claim_queued_task_run,
    create_task_outbox,
    create_task_run,
    duration_ms,
    finish_task_run,
    heartbeat_task_run_by_id,
    requeue_task_run_failure,
)


class _FakeDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added = []
        self.flushes = 0
        self.commits = 0

    def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = len(self.added) + 1
        self.added.append(value)

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1

    async def get(self, model, row_id, **_kwargs):
        for row in [*self.rows, *self.added]:
            if getattr(row, "id", None) == row_id:
                return row
        return None

    async def execute(self, _stmt):
        if getattr(_stmt, "is_update", False):
            params = _stmt.compile().params
            row_id = next((value for key, value in params.items() if key.startswith("id_")), None)
            row = next((item for item in self.rows if getattr(item, "id", None) == row_id), None)
            updated = None
            if row is not None and params.get("status") == "timed_out":
                stale = (
                    row.status == "running"
                    and getattr(row, "lease_expires_at", None) is not None
                    and row.lease_expires_at <= params["lease_expires_at_1"]
                )
                if stale and getattr(row, "attempt", 1) >= getattr(row, "max_attempts", 3):
                    row.status = "timed_out"
                    row.finished_at = params["finished_at"]
                    row.heartbeat_at = params["heartbeat_at"]
                    row.lease_expires_at = None
                    row.error = params["error"]
                    updated = row.id
            elif row is not None and params.get("status") == "running":
                claimed_at = params["started_at"]
                queued_ready = row.status == "queued" and (
                    getattr(row, "next_attempt_at", None) is None or row.next_attempt_at <= claimed_at
                )
                stale = (
                    row.status == "running"
                    and getattr(row, "lease_expires_at", None) is not None
                    and row.lease_expires_at <= claimed_at
                    and getattr(row, "attempt", 1) < getattr(row, "max_attempts", 3)
                )
                if queued_ready or stale:
                    if stale:
                        row.attempt = getattr(row, "attempt", 1) + 1
                    row.status = "running"
                    row.started_at = claimed_at
                    row.heartbeat_at = params["heartbeat_at"]
                    row.lease_expires_at = params["lease_expires_at"]
                    row.next_attempt_at = None
                    row.error = None
                    updated = row.id

            class _UpdateResult:
                def scalar_one_or_none(self):
                    return updated

            return _UpdateResult()

        rows = self.rows

        class _Scalars:
            def all(self):
                return rows

        class _Result:
            def scalars(self):
                return _Scalars()

            def scalar_one_or_none(self):
                return rows[0] if rows else None

        return _Result()


def test_duration_ms_handles_naive_and_aware_datetimes():
    started = datetime(2026, 7, 8, 10, 0, 0)
    finished = datetime(2026, 7, 8, 10, 0, 1, 250000, tzinfo=timezone.utc)

    assert duration_ms(started, finished) == 1250


@pytest.mark.asyncio
async def test_claim_queued_task_run_is_idempotent():
    run = SimpleNamespace(id=1, task_type="scrape_job", status="queued", started_at=None, error="old error")
    db = _FakeDb(rows=[run])

    claimed = await claim_queued_task_run(db, run.id)
    duplicate = await claim_queued_task_run(db, run.id)

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.started_at is not None
    assert claimed.error is None
    assert claimed.execution_token
    assert duplicate is None


@pytest.mark.asyncio
async def test_claim_recovers_a_stale_lease_without_allowing_a_live_duplicate():
    now = datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)
    run = SimpleNamespace(
        id=1,
        task_type="scrape_job",
        status="running",
        started_at=now - timedelta(minutes=10),
        heartbeat_at=now - timedelta(minutes=10),
        lease_expires_at=now - timedelta(seconds=1),
        next_attempt_at=None,
        attempt=1,
        max_attempts=3,
        error="worker lost",
    )
    db = _FakeDb(rows=[run])

    recovered = await claim_queued_task_run(db, run.id, now=now, lease_seconds=30)
    duplicate = await claim_queued_task_run(db, run.id, now=now + timedelta(seconds=1), lease_seconds=30)

    assert recovered is run
    assert run.status == "running"
    assert run.attempt == 2
    assert run.heartbeat_at == now
    assert run.lease_expires_at == now + timedelta(seconds=30)
    assert duplicate is None


@pytest.mark.asyncio
async def test_claim_terminalizes_an_exhausted_stale_lease_on_sqlite():
    now = datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)
    run = SimpleNamespace(
        id=1,
        task_type="scrape_job",
        status="running",
        started_at=now - timedelta(minutes=10),
        heartbeat_at=now - timedelta(minutes=10),
        lease_expires_at=now - timedelta(seconds=1),
        next_attempt_at=None,
        attempt=3,
        max_attempts=3,
        finished_at=None,
        duration_ms=None,
        error=None,
    )
    db = _FakeDb(rows=[run])

    claimed = await claim_queued_task_run(db, run.id, now=now, lease_seconds=30)

    assert claimed is None
    assert run.status == "timed_out"
    assert run.attempt == 3
    assert run.finished_at == now
    assert run.duration_ms == 600_000
    assert run.heartbeat_at == now
    assert run.lease_expires_at is None
    assert run.error == "task lease expired and retry limit was exhausted"


@pytest.mark.asyncio
async def test_postgres_claim_terminalizes_an_exhausted_stale_lease_before_retry():
    class _PostgresDb(_FakeDb):
        def __init__(self):
            super().__init__()
            self.statements = []

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def execute(self, stmt):
            self.statements.append(stmt)
            updated_id = 91 if len(self.statements) == 2 else None

            class _Result:
                def scalar_one_or_none(self):
                    return updated_id

            return _Result()

    now = datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)
    db = _PostgresDb()

    claimed = await claim_queued_task_run(db, 91, now=now, lease_seconds=30)

    assert claimed is None
    assert len(db.statements) == 2
    compiled = str(db.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "scheduled_job_runs.attempt >= scheduled_job_runs.max_attempts" in compiled
    assert "status='timed_out'" in compiled.replace(" ", "")


@pytest.mark.asyncio
async def test_atomic_heartbeat_only_renews_a_running_run():
    class _HeartbeatDb(_FakeDb):
        def __init__(self, updated_id):
            super().__init__()
            self.updated_id = updated_id
            self.statement = None

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def execute(self, stmt):
            self.statement = stmt
            updated_id = self.updated_id

            class _Result:
                def scalar_one_or_none(self):
                    return updated_id

            return _Result()

    now = datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)
    running_db = _HeartbeatDb(updated_id=7)
    terminal_db = _HeartbeatDb(updated_id=None)

    assert await heartbeat_task_run_by_id(running_db, 7, now=now, lease_seconds=30) is True
    assert await heartbeat_task_run_by_id(terminal_db, 7, now=now, lease_seconds=30) is False
    compiled = str(running_db.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "scheduled_job_runs.status = 'running'" in compiled
    assert "2026-07-12 10:00:30" in compiled


@pytest.mark.asyncio
async def test_long_running_task_heartbeat_uses_a_separate_committed_session(monkeypatch):
    stopped = scheduled_jobs.asyncio.Event()
    heartbeat_db = _FakeDb()
    heartbeat_calls = []

    class _SessionManager:
        async def __aenter__(self):
            return heartbeat_db

        async def __aexit__(self, *_args):
            return None

    async def fake_heartbeat(db, run_id, *, lease_seconds):
        heartbeat_calls.append((db, run_id, lease_seconds))
        stopped.set()
        return True

    async def immediate_timeout(awaitable, *, timeout):
        del timeout
        if stopped.is_set():
            return await awaitable
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", _SessionManager)
    monkeypatch.setattr(scheduled_jobs, "heartbeat_task_run_by_id", fake_heartbeat)
    monkeypatch.setattr(scheduled_jobs.asyncio, "wait_for", immediate_timeout)

    await scheduled_jobs._maintain_task_run_heartbeat(12, stopped, lease_seconds=600)

    assert heartbeat_calls == [(heartbeat_db, 12, 600)]
    assert heartbeat_db.commits == 1


@pytest.mark.asyncio
async def test_scrape_run_commits_result_before_stopping_heartbeat(monkeypatch):
    events: list[str] = []
    run = SimpleNamespace(
        id=27,
        task_type="scrape_job",
        status="queued",
        artifacts={"scrape_job_ids": [42]},
    )
    job = SimpleNamespace(id=42, status="completed", error=None)

    class _Db(_FakeDb):
        async def commit(self):
            events.append("commit")
            await super().commit()

        async def rollback(self):
            events.append("rollback")

    db = _Db(rows=[run])

    class _SessionManager:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

    async def fake_claim(_db, run_id, *, lease_seconds):
        assert _db is db
        assert run_id == run.id
        assert lease_seconds > 0
        events.append("claim")
        return run

    @contextlib.asynccontextmanager
    async def fake_heartbeat(run_id, *, lease_seconds):
        assert run_id == run.id
        assert lease_seconds > 0
        events.append("heartbeat_enter")
        try:
            yield
        finally:
            events.append("heartbeat_exit")

    async def fake_execute(_db, job_id):
        assert _db is db
        assert job_id == job.id
        events.append("execute")
        return job

    async def fake_finish(_db, bound_run, **_kwargs):
        assert _db is db
        assert bound_run is run
        events.append("finish")
        return run

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", _SessionManager)
    monkeypatch.setattr(scheduled_jobs, "claim_queued_task_run", fake_claim)
    monkeypatch.setattr(scheduled_jobs, "_task_run_heartbeat", fake_heartbeat)
    monkeypatch.setattr(scheduled_jobs, "execute_scrape_job", fake_execute)
    monkeypatch.setattr(scheduled_jobs, "_scrape_job_artifacts", lambda _job: {"scrape_job_ids": [42]})
    monkeypatch.setattr(scheduled_jobs, "_scrape_task_run_status", lambda *_args: "completed")
    monkeypatch.setattr(scheduled_jobs, "finish_task_run", fake_finish)

    result = await scheduled_jobs.execute_scrape_job_run(run.id)

    assert result is run
    assert events == [
        "claim",
        "commit",
        "heartbeat_enter",
        "execute",
        "heartbeat_exit",
        "finish",
        "commit",
    ]


@pytest.mark.asyncio
async def test_scrape_run_routes_returned_bridge_timeout_through_fenced_retry(monkeypatch):
    run = SimpleNamespace(
        id=28,
        task_type="scrape_job",
        status="queued",
        artifacts={"scrape_job_ids": [43]},
        queue_contract_version="worker-lanes/v1",
        execution_token="token-28",
    )
    job = SimpleNamespace(
        id=43,
        status="failed",
        error="OddsHarvester request timed out",
        output='{"failure":{"kind":"timeout"}}',
    )
    db = _FakeDb(rows=[run])

    class _SessionManager:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

    async def fake_claim(_db, _run_id, *, lease_seconds):
        run.status = "running"
        return run

    @contextlib.asynccontextmanager
    async def fake_heartbeat(*_args, **_kwargs):
        yield

    async def fake_requeue(_db, bound_run, **kwargs):
        assert kwargs["execution_token"] == "token-28"
        assert kwargs["failure_kind"] == "timeout"
        bound_run.status = "queued"
        bound_run.execution_token = None
        bound_run.retry_disposition = "retryable"
        return True

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", _SessionManager)
    monkeypatch.setattr(scheduled_jobs, "claim_queued_task_run", fake_claim)
    monkeypatch.setattr(scheduled_jobs, "_task_run_heartbeat", fake_heartbeat)

    async def fake_execute(*_args):
        return job

    monkeypatch.setattr(scheduled_jobs, "execute_scrape_job", fake_execute)
    monkeypatch.setattr(scheduled_jobs, "requeue_task_run_failure", fake_requeue)

    result = await scheduled_jobs.execute_scrape_job_run(run.id)

    assert result.status == "queued"
    assert result.retry_disposition == "retryable"
    assert result.artifacts["failure_kind"] == "timeout"


@pytest.mark.asyncio
async def test_returned_scrape_failure_cannot_commit_after_fence_is_lost(monkeypatch):
    run = SimpleNamespace(id=29, artifacts=None)

    class Db:
        def __init__(self):
            self.flushes = 0

        async def flush(self):
            self.flushes += 1

    db = Db()

    async def stale_requeue(*_args, **_kwargs):
        return False

    monkeypatch.setattr(scheduled_jobs, "requeue_task_run_failure", stale_requeue)

    with pytest.raises(RuntimeError, match="lost its execution fence"):
        await scheduled_jobs._apply_scrape_failure_retry(
            db,
            run,
            artifacts={"scrape_job_ids": [44], "failure_kind": "timeout"},
            execution_token="stale-token",
            error="timeout",
        )

    assert run.artifacts is None
    assert db.flushes == 0


@pytest.mark.asyncio
async def test_non_scrape_scheduled_result_without_artifacts_skips_scrape_retry_path():
    run = SimpleNamespace(id=30, artifacts=None)

    class Db:
        async def flush(self):
            raise AssertionError("a result without scrape failure artifacts must not mutate the run")

    changed = await scheduled_jobs._apply_scrape_failure_retry(
        Db(),
        run,
        artifacts=None,
        execution_token="active-token",
        error="not a scrape failure",
    )

    assert changed is False
    assert run.artifacts is None


@pytest.mark.asyncio
async def test_task_run_helpers_create_and_finish_durable_run():
    db = _FakeDb()
    job = SimpleNamespace(id=42)

    run = await create_task_run(
        db,
        task_type="scrape_predict_tickets",
        scheduled_job=job,
        triggered_by="scheduler",
        due_at=datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc),
        artifacts={"prediction_run_ids": [7]},
        status="running",
    )
    run.queue_contract_version = "legacy-control/v0"
    await finish_task_run(
        db,
        run,
        status="completed",
        detail="ok",
        artifacts={"ticket_batch_id": 3},
    )

    assert run.id == 1
    assert run.scheduled_job_id == 42
    assert run.status == "completed"
    assert run.detail == "ok"
    assert run.queued_at is not None
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.duration_ms is not None
    assert run.artifacts == {"prediction_run_ids": [7], "ticket_batch_id": 3}
    assert db.flushes == 2


@pytest.mark.asyncio
async def test_enqueue_due_scheduled_jobs_creates_run_and_advances_job(monkeypatch):
    now = datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id=5,
        enabled=True,
        task_type="scrape_odds",
        next_run=now - timedelta(minutes=1),
        cron_expression="0 */6 * * *",
    )
    db = _FakeDb(rows=[job])

    calls = []

    async def fake_send(run, *, task_name):
        assert task_name == "scheduled_job"
        calls.append(("send", db.commits, run.id))
        return "task-123"

    monkeypatch.setattr(scheduled_jobs, "_send_taskiq_run", fake_send)

    runs = await scheduled_jobs.enqueue_due_scheduled_jobs(db, now=now, limit=10)

    assert len(runs) == 1
    assert runs[0].scheduled_job_id == job.id
    assert runs[0].status == "queued"
    assert runs[0].taskiq_task_id == "task-123"
    assert calls == [("send", 1, runs[0].id)]
    assert db.commits == 2
    assert job.last_run == now
    assert job.next_run == now + timedelta(hours=6)


@pytest.mark.asyncio
async def test_taskiq_enqueue_commits_run_before_publishing(monkeypatch):
    db = _FakeDb()
    run = await create_task_run(db, task_type="scrape_job", scrape_job_id=44)
    calls = []

    async def fake_send(published_run, *, task_name):
        calls.append(("send", db.commits, published_run.id, task_name))
        return "task-abc"

    monkeypatch.setattr(scheduled_jobs, "_send_taskiq_run", fake_send)

    result = await scheduled_jobs._enqueue_taskiq_run_after_commit(db, run, task_name="scrape_job")

    assert result is run
    assert calls == [("send", 1, run.id, "scrape_job")]
    assert run.taskiq_task_id == "task-abc"
    assert db.commits == 2


@pytest.mark.asyncio
async def test_taskiq_enqueue_failure_is_reported_to_api_caller(monkeypatch):
    db = _FakeDb()
    run = await create_task_run(db, task_type="scrape_job", scrape_job_id=44)

    async def fake_send(_published_run, *, task_name):
        assert task_name == "scrape_job"
        raise RuntimeError("redis down")

    monkeypatch.setattr(scheduled_jobs, "_send_taskiq_run", fake_send)

    with pytest.raises(scheduled_jobs.TaskEnqueueError) as exc_info:
        await scheduled_jobs._enqueue_taskiq_run_after_commit(db, run, task_name="scrape_job")

    assert exc_info.value.run is run
    assert run.status == "enqueue_failed"
    assert run.error == "redis down"
    assert db.commits == 2


@pytest.mark.asyncio
async def test_outbox_enqueue_failure_remains_retryable_then_publishes(monkeypatch):
    db = _FakeDb()
    run = await create_task_run(db, task_type="scrape_job", scrape_job_id=44, transport="taskiq")
    outbox = await create_task_outbox(db, run, task_name="scrape_job", transport="taskiq", max_attempts=2)
    await db.commit()
    sends = 0

    async def flaky_send(_run, _outbox):
        nonlocal sends
        sends += 1
        if sends == 1:
            raise RuntimeError("redis down")
        return "task-retry-2"

    monkeypatch.setattr(scheduled_jobs, "_send_outbox_run", flaky_send)

    with pytest.raises(scheduled_jobs.TaskEnqueueError):
        await scheduled_jobs._publish_outbox_entry(db, outbox)

    assert run.status == "queued"
    assert run.detail == "enqueue_retry_pending"
    assert outbox.status == "pending"
    assert outbox.attempts == 1

    published = await scheduled_jobs._publish_outbox_entry(db, outbox)

    assert published is run
    assert outbox.status == "published"
    assert run.transport_task_id == "task-retry-2"
    assert run.taskiq_task_id == "task-retry-2"


@pytest.mark.asyncio
async def test_stale_published_outbox_replays_only_an_unclaimed_queued_run(monkeypatch):
    db = _FakeDb()
    run = await create_task_run(db, task_type="scrape_job", scrape_job_id=45, transport="taskiq")
    outbox = await create_task_outbox(db, run, task_name="scrape_job", transport="taskiq", max_attempts=3)
    outbox.status = "published"
    outbox.attempts = 1
    outbox.published_at = datetime.now(timezone.utc) - timedelta(minutes=20)

    async def replay_send(_run, _outbox):
        return "task-replayed-2"

    monkeypatch.setattr(scheduled_jobs, "_send_outbox_run", replay_send)

    replayed = await scheduled_jobs._replay_stale_published_outbox_entry(db, outbox)

    assert replayed is run
    assert run.status == "queued"
    assert outbox.status == "published"
    assert outbox.attempts == 2
    assert run.transport_task_id == "task-replayed-2"


@pytest.mark.asyncio
async def test_stale_published_outbox_exhaustion_marks_delivery_unconfirmed():
    db = _FakeDb()
    run = await create_task_run(db, task_type="scrape_job", scrape_job_id=46, transport="taskiq")
    outbox = await create_task_outbox(db, run, task_name="scrape_job", transport="taskiq", max_attempts=2)
    outbox.status = "published"
    outbox.attempts = 2
    outbox.published_at = datetime.now(timezone.utc) - timedelta(minutes=40)

    replayed = await scheduled_jobs._replay_stale_published_outbox_entry(db, outbox)

    assert replayed is None
    assert outbox.status == "failed"
    assert run.status == "timed_out"
    assert run.detail == "task_delivery_unconfirmed"


@pytest.mark.asyncio
async def test_stale_published_outbox_waits_behind_an_earlier_unfinished_delivery():
    predecessor = SimpleNamespace(id=999)
    db = _FakeDb(rows=[predecessor])
    run = await create_task_run(db, task_type="scrape_job", scrape_job_id=47, transport="taskiq")
    outbox = await create_task_outbox(db, run, task_name="scrape_job", transport="taskiq", max_attempts=2)
    outbox.status = "published"
    outbox.attempts = 2
    outbox.published_at = datetime.now(timezone.utc) - timedelta(minutes=40)

    replayed = await scheduled_jobs._replay_stale_published_outbox_entry(db, outbox)

    assert replayed is run
    assert outbox.status == "published"
    assert outbox.attempts == 2
    assert run.status == "queued"
    assert run.finished_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["inprocess", "taskiq"])
async def test_common_executor_routes_both_transports_through_same_run_path(monkeypatch, transport):
    run = SimpleNamespace(id=77, scheduled_job_id=None, task_type="scrape_job", transport=transport)

    class _SessionManager:
        async def __aenter__(self):
            return _FakeDb(rows=[run])

        async def __aexit__(self, *_args):
            return None

    calls = []

    async def fake_execute(run_id):
        calls.append(run_id)
        return run

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", _SessionManager)
    monkeypatch.setattr(scheduled_jobs, "execute_scrape_job_run", fake_execute)

    result = await scheduled_jobs.execute_task_run(run.id)

    assert result is run
    assert calls == [run.id]


@pytest.mark.asyncio
async def test_inprocess_scrape_dispatch_is_serialized(monkeypatch):
    started: list[int] = []
    release_first = asyncio.Event()
    first_started = asyncio.Event()

    async def fake_execute(run_id: int):
        started.append(run_id)
        if run_id == 1:
            first_started.set()
            await release_first.wait()
        return SimpleNamespace(id=run_id)

    monkeypatch.setattr(scheduled_jobs, "execute_task_run", fake_execute)
    monkeypatch.setattr(scheduled_jobs.settings, "inprocess_scrape_max_concurrency", 1)
    monkeypatch.setattr(scheduled_jobs, "_inprocess_scrape_semaphore", None)

    first = asyncio.create_task(scheduled_jobs._execute_inprocess_task(1, task_name="scrape_job"))
    await first_started.wait()
    second = asyncio.create_task(scheduled_jobs._execute_inprocess_task(2, task_name="scrape_job"))
    await asyncio.sleep(0)

    assert started == [1]

    release_first.set()
    await asyncio.gather(first, second)

    assert started == [1, 2]


@pytest.mark.asyncio
async def test_enqueue_scrape_job_execution_reuses_active_run(monkeypatch):
    existing_run = SimpleNamespace(
        id=31,
        task_type="scrape_job",
        scrape_job_id=44,
        status="queued",
        created_at=datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc),
    )
    db = _FakeDb(rows=[existing_run])

    async def fail_create_task_run(*_args, **_kwargs):
        raise AssertionError("duplicate active scrape run should not be created")

    monkeypatch.setattr(scheduled_jobs, "create_task_run", fail_create_task_run)

    result = await scheduled_jobs.enqueue_scrape_job_execution(db, scrape_job_id=44, triggered_by="api", user_id=12)

    assert result is existing_run


@pytest.mark.asyncio
async def test_publish_failure_keeps_scheduled_job_due_for_retry(monkeypatch):
    due_at = datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)
    advanced_next_run = due_at + timedelta(hours=6)
    job = SimpleNamespace(id=9, next_run=advanced_next_run)
    db = _FakeDb(rows=[job])
    run = await create_task_run(
        db,
        task_type="scrape_odds",
        scheduled_job=job,
        due_at=due_at,
    )

    async def fake_send(_run, *, task_name):
        assert task_name == "scheduled_job"
        raise RuntimeError("redis down")

    monkeypatch.setattr(scheduled_jobs, "_send_taskiq_run", fake_send)

    result = await scheduled_jobs._publish_committed_taskiq_run(db, run, task_name="scheduled_job")

    assert result.status == "enqueue_failed"
    assert result.error == "redis down"
    assert job.next_run == due_at


@pytest.mark.asyncio
async def test_run_due_scheduled_jobs_inprocess_uses_queued_transport_semantics(monkeypatch):
    now = datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id=8,
        enabled=True,
        task_type="scrape_odds",
        next_run=now - timedelta(minutes=1),
        cron_expression="0 */6 * * *",
    )
    db = _FakeDb(rows=[job])

    async def fake_send(run, outbox):
        assert outbox.transport == "inprocess"
        return f"inprocess:{run.id}"

    monkeypatch.setattr(scheduled_jobs.settings, "task_queue_backend", "inprocess")
    monkeypatch.setattr(scheduled_jobs, "_send_outbox_run", fake_send)

    runs = await scheduled_jobs.run_due_scheduled_jobs(db, now=now, limit=10)

    assert len(runs) == 1
    assert runs[0].status == "queued"
    assert runs[0].transport == "inprocess"
    assert runs[0].transport_task_id == f"inprocess:{runs[0].id}"
    assert job.last_run == now
    assert job.next_run == now + timedelta(hours=6)


@pytest.mark.asyncio
async def test_worker_lane_defaults_follow_explicit_operation_registry():
    db = _FakeDb()

    browser = await create_task_run(db, task_type="scrape_job", scrape_job_id=44)
    model = await create_task_run(db, task_type="run_predictions")
    train = await create_task_run(db, task_type="train_model")
    backtest = await create_task_run(db, task_type="backtest_model")
    predict = await create_task_run(db, task_type="predict_model")
    control = await create_task_run(db, task_type="unknown_legacy_probe")

    assert (browser.queue_lane, browser.max_attempts) == ("provider-browser", 2)
    assert (model.queue_lane, model.max_attempts) == ("model-cpu", 3)
    assert (train.queue_lane, train.max_attempts) == ("model-cpu", 3)
    assert (backtest.queue_lane, backtest.max_attempts) == ("model-cpu", 3)
    assert (predict.queue_lane, predict.max_attempts) == ("model-cpu", 3)
    assert (control.queue_lane, control.max_attempts) == ("control", 3)


@pytest.mark.asyncio
async def test_outbox_rejects_lane_or_contract_mismatch():
    db = _FakeDb()
    run = await create_task_run(db, task_type="scrape_job")

    with pytest.raises(ValueError, match="must match"):
        await create_task_outbox(db, run, task_name="scrape_job", queue_lane="control")
    with pytest.raises(ValueError, match="must match"):
        await create_task_outbox(db, run, task_name="scrape_job", queue_contract_version="worker-lanes/v0")


@pytest.mark.asyncio
async def test_fenced_terminal_update_and_retry_sql_predicate():
    class _FenceDb(_FakeDb):
        def __init__(self, updated_id):
            super().__init__()
            self.updated_id = updated_id
            self.statements = []

        async def execute(self, stmt):
            self.statements.append(stmt)

            updated_id = self.updated_id

            class _Result:
                def scalar_one_or_none(self):
                    return updated_id

            return _Result()

    now = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    run = SimpleNamespace(
        id=8,
        status="running",
        started_at=now - timedelta(seconds=5),
        attempt=1,
        max_attempts=2,
        artifacts=None,
        metrics=None,
        execution_token="current-token",
    )
    stale_db = _FenceDb(updated_id=None)
    with pytest.raises(Exception, match="lost its execution fence"):
        await finish_task_run(stale_db, run, status="completed", execution_token="old-token")
    assert run.status == "running"
    compiled = str(stale_db.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "execution_token = 'old-token'" in compiled

    retry_db = _FenceDb(updated_id=8)
    assert await requeue_task_run_failure(
        retry_db, run, execution_token="current-token", failure_kind="provider_429", error="rate limited"
    )
    retry_compiled = str(retry_db.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "status='queued'" in retry_compiled.replace(" ", "")
    assert "execution_token = 'current-token'" in retry_compiled


@pytest.mark.asyncio
async def test_v1_running_finish_requires_execution_token_and_legacy_heartbeat_is_only_tokenless_path():
    run = SimpleNamespace(id=91, status="running", queue_contract_version="worker-lanes/v1")
    db = _FakeDb()

    with pytest.raises(Exception, match="requires an execution fence"):
        await finish_task_run(db, run, status="completed")

    class _HeartbeatDb(_FakeDb):
        def __init__(self):
            super().__init__()
            self.statement = None

        async def execute(self, statement):
            self.statement = statement

            class _Result:
                def scalar_one_or_none(self):
                    return None

            return _Result()

    heartbeat_db = _HeartbeatDb()
    assert not await heartbeat_task_run_by_id(heartbeat_db, 91)
    assert "queue_contract_version = 'legacy-control/v0'" in str(
        heartbeat_db.statement.compile(compile_kwargs={"literal_binds": True})
    )
