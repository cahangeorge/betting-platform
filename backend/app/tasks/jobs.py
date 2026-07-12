import asyncio

from app.config import get_settings
from app.database import async_session_factory
from app.services.scheduled_jobs import (
    enqueue_due_scheduled_jobs,
    execute_scheduled_job_run,
    execute_scrape_job_run,
    execute_world_cup_pipeline_run,
)
from app.tasks.broker import broker

settings = get_settings()


@broker.task
async def execute_scheduled_job_run_task(run_id: int) -> None:
    await execute_scheduled_job_run(run_id)


@broker.task
async def execute_scrape_job_task(run_id: int) -> None:
    await execute_scrape_job_run(run_id)


@broker.task
async def execute_world_cup_pipeline_task(run_id: int) -> None:
    await execute_world_cup_pipeline_run(run_id)


@broker.task
async def poll_due_scheduled_jobs_task(limit: int = 10) -> int:
    async with async_session_factory() as db:
        runs = await enqueue_due_scheduled_jobs(db, limit=limit)
        await db.commit()
        return len(runs)


async def scheduler_loop() -> None:
    while True:
        await poll_due_scheduled_jobs_task.kiq()
        await asyncio.sleep(max(5, settings.taskiq_poll_interval_seconds))


if __name__ == "__main__":
    asyncio.run(scheduler_loop())
