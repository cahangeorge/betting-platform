from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import ScheduledJob, ScheduledJobRun

ACTIVE_TASK_RUN_STATUSES = {"queued", "running"}


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
    )
    db.add(run)
    await db.flush()
    return run


async def mark_task_run_queued(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    taskiq_task_id: str | None = None,
) -> ScheduledJobRun:
    run.status = "queued"
    run.queued_at = run.queued_at or utcnow()
    run.taskiq_task_id = taskiq_task_id or run.taskiq_task_id
    await db.flush()
    return run


async def mark_task_run_running(db: AsyncSession, run: ScheduledJobRun) -> ScheduledJobRun:
    run.status = "running"
    run.started_at = utcnow()
    run.error = None
    await db.flush()
    return run


async def claim_queued_task_run(db: AsyncSession, run_id: int) -> ScheduledJobRun | None:
    """Atomically transition a queued run to running.

    Returns the claimed run, or None when another worker already claimed or
    completed it. This protects Taskiq duplicate delivery/retry paths from
    executing side effects more than once.
    """
    now = utcnow()
    bind = db.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name == "sqlite":
        run = await db.get(ScheduledJobRun, run_id)
        if run is None or run.status != "queued":
            return None
        run.status = "running"
        run.started_at = now
        run.error = None
        await db.flush()
        return run

    stmt = (
        update(ScheduledJobRun)
        .where(ScheduledJobRun.id == run_id, ScheduledJobRun.status == "queued")
        .values(status="running", started_at=now, error=None)
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
    await db.flush()
    return run


async def mark_task_run_enqueue_failed(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    error: str,
) -> ScheduledJobRun:
    return await finish_task_run(db, run, status="enqueue_failed", detail="enqueue_failed", error=error)
