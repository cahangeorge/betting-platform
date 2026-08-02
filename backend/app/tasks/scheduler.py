import asyncio

from app.config import get_settings
from app.database import async_session_factory
from app.services.scheduled_jobs import reconcile_task_outbox, requeue_expired_task_run_leases
from app.tasks.broker import broker
from app.tasks.jobs import poll_due_scheduled_jobs_task
from app.tasks.runtime import runtime_heartbeat, stop_runtime_heartbeat

settings = get_settings()


async def scheduler_loop() -> None:
    while True:
        async with async_session_factory() as db:
            await requeue_expired_task_run_leases(db)
            await reconcile_task_outbox(db)
            await db.commit()
        await poll_due_scheduled_jobs_task.kiq()
        await asyncio.sleep(max(5, settings.taskiq_poll_interval_seconds))


async def scheduler_main() -> None:
    await broker.startup()
    heartbeat = asyncio.create_task(
        runtime_heartbeat("scheduler"),
        name="taskiq-scheduler-heartbeat",
    )
    try:
        await scheduler_loop()
    finally:
        await stop_runtime_heartbeat(heartbeat)
        await broker.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(scheduler_main())
    except KeyboardInterrupt:
        pass
