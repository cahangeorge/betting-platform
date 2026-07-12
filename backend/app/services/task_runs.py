from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.job import ScheduledJob, ScheduledJobRun, TaskOutbox

ACTIVE_TASK_RUN_STATUSES = {"queued", "running"}
TERMINAL_TASK_RUN_STATUSES = {
    "completed",
    "partial",
    "skipped",
    "failed",
    "enqueue_failed",
    "timed_out",
    "cancelled",
}

settings = get_settings()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    if started_at is None or finished_at is None:
        return None
    started = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    finished = finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)
    return max(0, int((finished - started).total_seconds() * 1000))


async def find_active_scrape_task_run(
    db: AsyncSession,
    *,
    task_type: str,
    scrape_job_id: int,
) -> ScheduledJobRun | None:
    stmt = (
        select(ScheduledJobRun)
        .where(
            ScheduledJobRun.task_type == task_type,
            ScheduledJobRun.scrape_job_id == scrape_job_id,
            ScheduledJobRun.status.in_(ACTIVE_TASK_RUN_STATUSES),
        )
        .order_by(ScheduledJobRun.created_at.desc(), ScheduledJobRun.id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_task_run(
    db: AsyncSession,
    *,
    task_type: str,
    scheduled_job: ScheduledJob | None = None,
    scrape_job_id: int | None = None,
    triggered_by: str = "scheduler",
    due_at: datetime | None = None,
    artifacts: dict[str, Any] | None = None,
    status: str = "queued",
    transport: str | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> ScheduledJobRun:
    now = utcnow()
    run = ScheduledJobRun(
        scheduled_job_id=scheduled_job.id if scheduled_job else None,
        scrape_job_id=scrape_job_id,
        task_type=task_type,
        status=status,
        queued_at=now if status in {"queued", "running"} else None,
        started_at=now if status == "running" else None,
        triggered_by=triggered_by,
        due_at=due_at,
        artifacts=artifacts or None,
        transport=transport or settings.task_queue_backend,
        idempotency_key=idempotency_key or f"task-run:{uuid4()}",
        max_attempts=max_attempts,
    )
    db.add(run)
    await db.flush()
    return run


async def mark_task_run_queued(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    transport_task_id: str | None = None,
    taskiq_task_id: str | None = None,
) -> ScheduledJobRun:
    run.status = "queued"
    run.queued_at = run.queued_at or utcnow()
    task_id = transport_task_id or taskiq_task_id
    run.transport_task_id = task_id or run.transport_task_id
    # Deprecated compatibility alias. New code should read transport_task_id.
    run.taskiq_task_id = task_id or run.taskiq_task_id
    await db.flush()
    return run


async def mark_task_run_running(
    db: AsyncSession, run: ScheduledJobRun, *, lease_seconds: int | None = None
) -> ScheduledJobRun:
    now = utcnow()
    run.status = "running"
    run.started_at = run.started_at or now
    run.heartbeat_at = now
    run.lease_expires_at = now + timedelta(seconds=lease_seconds or settings.task_run_lease_seconds)
    run.error = None
    await db.flush()
    return run


async def claim_queued_task_run(
    db: AsyncSession,
    run_id: int,
    *,
    now: datetime | None = None,
    lease_seconds: int | None = None,
) -> ScheduledJobRun | None:
    """Atomically transition a queued run to running.

    Returns the claimed run, or None when another worker already claimed or
    completed it. This protects Taskiq duplicate delivery/retry paths from
    executing side effects more than once.
    """
    claimed_at = now or utcnow()
    lease_expires_at = claimed_at + timedelta(seconds=lease_seconds or settings.task_run_lease_seconds)
    bind = db.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name == "sqlite":
        run = await db.get(ScheduledJobRun, run_id)
        if run is None:
            return None
        queued_ready = run.status == "queued" and (
            getattr(run, "next_attempt_at", None) is None or run.next_attempt_at <= claimed_at
        )
        stale_running = run.status == "running" and (
            getattr(run, "lease_expires_at", None) is not None and run.lease_expires_at <= claimed_at
        )
        if not queued_ready and not stale_running:
            return None
        if stale_running:
            run.attempt = getattr(run, "attempt", 1) + 1
            if run.attempt > getattr(run, "max_attempts", 3):
                run.status = "timed_out"
                run.finished_at = claimed_at
                run.error = "task lease expired and retry limit was exhausted"
                await db.flush()
                return None
        run.status = "running"
        run.started_at = claimed_at
        run.heartbeat_at = claimed_at
        run.lease_expires_at = lease_expires_at
        run.next_attempt_at = None
        run.error = None
        await db.flush()
        return run

    stmt = (
        update(ScheduledJobRun)
        .where(
            ScheduledJobRun.id == run_id,
            or_(
                (
                    (ScheduledJobRun.status == "queued")
                    & or_(ScheduledJobRun.next_attempt_at.is_(None), ScheduledJobRun.next_attempt_at <= claimed_at)
                ),
                (
                    (ScheduledJobRun.status == "running")
                    & (ScheduledJobRun.lease_expires_at.is_not(None))
                    & (ScheduledJobRun.lease_expires_at <= claimed_at)
                    & (ScheduledJobRun.attempt < ScheduledJobRun.max_attempts)
                ),
            ),
        )
        .values(
            status="running",
            started_at=claimed_at,
            heartbeat_at=claimed_at,
            lease_expires_at=lease_expires_at,
            next_attempt_at=None,
            attempt=ScheduledJobRun.attempt + sa.case((ScheduledJobRun.status == "running", 1), else_=0),
            error=None,
        )
        .returning(ScheduledJobRun.id)
    )
    result = await db.execute(stmt)
    claimed_id = result.scalar_one_or_none()
    if claimed_id is None:
        return None
    return await db.get(ScheduledJobRun, claimed_id)


async def finish_task_run(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    status: str,
    detail: str | None = None,
    artifacts: dict[str, Any] | None = None,
    error: str | None = None,
) -> ScheduledJobRun:
    finished_at = utcnow()
    run.status = status
    run.finished_at = finished_at
    run.duration_ms = duration_ms(run.started_at, finished_at)
    run.detail = detail
    if artifacts:
        merged = dict(run.artifacts or {})
        merged.update(artifacts)
        run.artifacts = merged
    run.error = error
    run.lease_expires_at = None
    run.heartbeat_at = finished_at
    await db.flush()
    return run


async def mark_task_run_enqueue_failed(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    error: str,
) -> ScheduledJobRun:
    return await finish_task_run(db, run, status="enqueue_failed", detail="enqueue_failed", error=error)


async def heartbeat_task_run(
    db: AsyncSession, run: ScheduledJobRun, *, lease_seconds: int | None = None
) -> ScheduledJobRun:
    if run.status != "running":
        return run
    now = utcnow()
    run.heartbeat_at = now
    run.lease_expires_at = now + timedelta(seconds=lease_seconds or settings.task_run_lease_seconds)
    await db.flush()
    return run


async def create_task_outbox(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    task_name: str,
    transport: str | None = None,
    max_attempts: int | None = None,
) -> TaskOutbox:
    outbox = TaskOutbox(
        run_id=run.id,
        task_name=task_name,
        transport=transport or run.transport,
        status="pending",
        attempts=0,
        max_attempts=max_attempts or settings.task_publish_max_attempts,
        available_at=utcnow(),
    )
    db.add(outbox)
    await db.flush()
    return outbox


async def mark_outbox_published(
    db: AsyncSession, outbox: TaskOutbox, run: ScheduledJobRun, *, transport_task_id: str | None
) -> None:
    now = utcnow()
    outbox.status = "published"
    outbox.published_at = now
    outbox.last_error = None
    outbox.transport_task_id = transport_task_id
    run.transport_task_id = transport_task_id or run.transport_task_id
    if run.transport == "taskiq":
        run.taskiq_task_id = transport_task_id or run.taskiq_task_id
    if run.detail == "enqueue_retry_pending":
        run.detail = None
        run.error = None
    await db.flush()


async def mark_outbox_publish_failed(db: AsyncSession, outbox: TaskOutbox, run: ScheduledJobRun, *, error: str) -> None:
    outbox.last_error = error
    run.error = error
    run.detail = "enqueue_retry_pending"
    if outbox.attempts >= outbox.max_attempts:
        outbox.status = "failed"
        await finish_task_run(db, run, status="enqueue_failed", detail="enqueue_failed", error=error)
    else:
        outbox.status = "pending"
        outbox.available_at = utcnow() + timedelta(seconds=settings.task_publish_retry_seconds)
    await db.flush()
