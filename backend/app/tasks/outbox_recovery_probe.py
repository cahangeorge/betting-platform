"""Real PostgreSQL/Redis proof for stale published-outbox replay."""

import asyncio
import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path


async def _stop_worker(worker: asyncio.subprocess.Process | None) -> None:
    if worker is None or worker.returncode is not None:
        return
    worker.terminate()
    try:
        await asyncio.wait_for(worker.wait(), timeout=10)
    except TimeoutError:
        worker.kill()
        await worker.wait()


async def verify_lost_stream_outbox_recovery() -> None:
    token = secrets.token_hex(8)
    queue_name = f"bet-outbox-recovery-{token}"
    os.environ["BET_TASK_QUEUE_BACKEND"] = "taskiq"
    os.environ["BET_TASKIQ_QUEUE_NAME"] = queue_name
    os.environ["BET_TASKIQ_CONSUMER_GROUP"] = f"{queue_name}-workers"
    os.environ["BET_TASKIQ_INSTANCE_ID"] = queue_name
    os.environ["BET_TASK_PUBLISH_REPLAY_GRACE_SECONDS"] = "1"
    os.environ["BET_DEBUG"] = "false"

    from redis.asyncio import Redis

    from app.config import get_settings
    from app.database import async_session_factory
    from app.models.job import ScheduledJob, ScheduledJobRun, TaskOutbox
    from app.services.scheduled_jobs import _publish_outbox_entry, reconcile_task_outbox
    from app.services.task_runs import create_task_outbox, create_task_run, utcnow
    from app.tasks.broker import broker

    settings = get_settings()
    taskiq_cli = Path(sys.executable).with_name("taskiq")
    worker: asyncio.subprocess.Process | None = None
    run_id: int | None = None
    outbox_id: int | None = None
    scheduled_job_id: int | None = None
    redis = Redis.from_url(settings.resolved_taskiq_broker_url)

    try:
        await broker.startup()
        async with async_session_factory() as db:
            scheduled_job = ScheduledJob(
                name=f"Outbox recovery probe {token}",
                task_type="outbox_recovery_probe",
                cron_expression="0 0 1 1 *",
                enabled=False,
                config={},
            )
            db.add(scheduled_job)
            await db.flush()
            run = await create_task_run(
                db,
                task_type=scheduled_job.task_type,
                scheduled_job=scheduled_job,
                triggered_by="outbox_recovery_probe",
                transport="taskiq",
            )
            outbox = await create_task_outbox(
                db,
                run,
                task_name="scheduled_job",
                transport="taskiq",
                max_attempts=3,
            )
            await db.commit()
            await _publish_outbox_entry(db, outbox)
            run_id = run.id
            outbox_id = outbox.id
            scheduled_job_id = scheduled_job.id
            first_task_id = outbox.transport_task_id

        await redis.delete(queue_name)

        worker = await asyncio.create_subprocess_exec(
            str(taskiq_cli),
            "worker",
            "app.tasks.broker:broker",
            "app.tasks.jobs",
            "--log-level",
            "INFO",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        group_deadline = asyncio.get_running_loop().time() + 10
        groups: list[dict] = []
        while asyncio.get_running_loop().time() < group_deadline:
            if worker.returncode is not None:
                stderr = await worker.stderr.read() if worker.stderr else b""
                raise RuntimeError(f"Outbox recovery worker failed to start: {stderr.decode().strip()}")
            try:
                groups = await redis.xinfo_groups(queue_name)
            except Exception:
                groups = []
            if any(
                group.get(b"name", group.get("name")) == os.environ["BET_TASKIQ_CONSUMER_GROUP"]
                or group.get(b"name", group.get("name")) == os.environ["BET_TASKIQ_CONSUMER_GROUP"].encode()
                for group in groups
            ):
                break
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError("Taskiq worker did not create its dedicated Redis consumer group")

        async with async_session_factory() as db:
            outbox = await db.get(TaskOutbox, outbox_id)
            if outbox is None:
                raise RuntimeError("Outbox recovery probe lost its durable outbox row")
            outbox.published_at = utcnow() - timedelta(seconds=2)
            await db.commit()
            replayed = await reconcile_task_outbox(db)
            await db.commit()
            if not replayed:
                raise RuntimeError("Stale published outbox was not replayed")
            if outbox.attempts != 2 or outbox.transport_task_id == first_task_id:
                raise RuntimeError("Outbox replay did not refresh its durable delivery evidence")

        async def terminal_status() -> str | None:
            async with async_session_factory() as db:
                run = await db.get(ScheduledJobRun, run_id)
                return run.status if run is not None else None

        deadline = asyncio.get_running_loop().time() + 20
        status = await terminal_status()
        while status == "queued" and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.25)
            status = await terminal_status()
        if status != "skipped":
            await _stop_worker(worker)
            stderr = await worker.stderr.read() if worker.stderr else b""
            worker = None
            raise RuntimeError(
                f"Replayed outbox task did not reach the expected safe terminal state: {status}; "
                f"{stderr.decode().strip()}"
            )
    finally:
        await _stop_worker(worker)
        await broker.shutdown()
        if scheduled_job_id is not None:
            async with async_session_factory() as db:
                scheduled_job = await db.get(ScheduledJob, scheduled_job_id)
                if scheduled_job is not None:
                    await db.delete(scheduled_job)
                    await db.commit()
        keys = [key async for key in redis.scan_iter(match=f"*{queue_name}*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(verify_lost_stream_outbox_recovery())
    print("Taskiq lost-stream published-outbox recovery passed")
