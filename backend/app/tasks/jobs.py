import asyncio

from app.config import get_settings
from app.database import async_session_factory
from app.models.job import ScheduledJobRun
from app.services.scheduled_jobs import (
    enqueue_due_scheduled_jobs,
    execute_task_run,
    reconcile_task_outbox,
)
from app.tasks.broker import broker, worker_lane
from app.tasks.worker_lanes import LEGACY_WORKER_CONTRACT_VERSION, WORKER_LANE_CONTRACT_VERSION

settings = get_settings()


async def validate_task_run_lane(run_id: int) -> ScheduledJobRun:
    """Fail closed when a transport message reaches the wrong worker lane."""
    async with async_session_factory() as db:
        run = await db.get(ScheduledJobRun, run_id)
        if run is None:
            raise LookupError(f"Task run {run_id} not found")
        legacy_control = (
            run.queue_contract_version == LEGACY_WORKER_CONTRACT_VERSION
            and run.queue_lane == "control"
            and worker_lane.value == "control"
        )
        if run.queue_contract_version != WORKER_LANE_CONTRACT_VERSION and not legacy_control:
            raise RuntimeError(f"Task run {run_id} has unsupported queue contract {run.queue_contract_version!r}")
        if run.queue_lane != worker_lane.value:
            raise RuntimeError(
                f"Task run {run_id} belongs to lane {run.queue_lane!r}, not worker lane {worker_lane.value!r}"
            )
        return run


async def _execute_validated_task_run(run_id: int) -> None:
    await validate_task_run_lane(run_id)
    await execute_task_run(run_id)


@broker.task(task_name="app.tasks.jobs:execute_scheduled_job_run_task")
async def execute_scheduled_job_run_task(run_id: int) -> None:
    await _execute_validated_task_run(run_id)


@broker.task(task_name="app.tasks.jobs:execute_scrape_job_task")
async def execute_scrape_job_task(run_id: int) -> None:
    await _execute_validated_task_run(run_id)


@broker.task(task_name="app.tasks.jobs:execute_world_cup_pipeline_task")
async def execute_world_cup_pipeline_task(run_id: int) -> None:
    await _execute_validated_task_run(run_id)


@broker.task(task_name="app.tasks.jobs:poll_due_scheduled_jobs_task")
async def poll_due_scheduled_jobs_task(limit: int = 10) -> int:
    async with async_session_factory() as db:
        await reconcile_task_outbox(db, limit=limit)
        runs = await enqueue_due_scheduled_jobs(db, limit=limit)
        await db.commit()
        return len(runs)


@broker.task(task_name="app.tasks.jobs:taskiq_healthcheck_task")
async def taskiq_healthcheck_task(nonce: str, delay_seconds: float = 0) -> str:
    """Round-trip diagnostic used by release and development smoke checks."""
    if delay_seconds < 0 or delay_seconds > 5:
        raise ValueError("healthcheck delay_seconds must be between 0 and 5")
    if delay_seconds:
        await asyncio.sleep(delay_seconds)
    return nonce
