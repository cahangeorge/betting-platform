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

    async def get(self, model, row_id):
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
