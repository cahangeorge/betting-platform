"""Real Redis/Taskiq worker stop-and-restart recovery diagnostic."""

import asyncio
import os
import secrets
import sys
from pathlib import Path


async def _stop_worker(worker: asyncio.subprocess.Process) -> None:
    if worker.returncode is not None:
        return
    worker.terminate()
    try:
        await asyncio.wait_for(worker.wait(), timeout=10)
    except TimeoutError:
        worker.kill()
        await worker.wait()


async def verify_worker_restart_recovery() -> None:
    token = secrets.token_hex(8)
    os.environ["BET_TASK_QUEUE_BACKEND"] = "taskiq"
    os.environ["BET_TASKIQ_QUEUE_NAME"] = f"bet-recovery-{token}"
    os.environ["BET_TASKIQ_CONSUMER_GROUP"] = f"bet-recovery-workers-{token}"
    os.environ["BET_TASKIQ_INSTANCE_ID"] = f"recovery-{token}"

    from taskiq.exceptions import TaskiqResultTimeoutError

    from app.tasks.broker import broker
    from app.tasks.jobs import taskiq_healthcheck_task

    taskiq_cli = Path(sys.executable).with_name("taskiq")
    worker_command = [
        str(taskiq_cli),
        "worker",
        "app.tasks.broker:broker",
        "app.tasks.jobs",
        "--log-level",
        "WARNING",
    ]

    async def start_worker() -> asyncio.subprocess.Process:
        worker = await asyncio.create_subprocess_exec(
            *worker_command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        await asyncio.sleep(2)
        if worker.returncode is not None:
            stderr = await worker.stderr.read() if worker.stderr else b""
            raise RuntimeError(f"Taskiq recovery worker failed to start: {stderr.decode().strip()}")
        return worker

    await broker.startup()
    worker = await start_worker()
    try:
        first_nonce = secrets.token_urlsafe(18)
        first_task = await taskiq_healthcheck_task.kiq(first_nonce)
        first_result = await first_task.wait_result(timeout=15)
        if first_result.is_err or first_result.return_value != first_nonce:
            raise RuntimeError("Taskiq recovery baseline round-trip failed")

        await _stop_worker(worker)

        queued_nonce = secrets.token_urlsafe(18)
        queued_task = await taskiq_healthcheck_task.kiq(queued_nonce)
        try:
            await queued_task.wait_result(timeout=1)
        except TaskiqResultTimeoutError:
            pass
        else:
            raise RuntimeError("Taskiq message completed while the dedicated worker was stopped")

        worker = await start_worker()
        recovered_result = await queued_task.wait_result(timeout=15)
        if recovered_result.is_err or recovered_result.return_value != queued_nonce:
            raise RuntimeError("Taskiq worker restart returned an invalid queued result")
    finally:
        await _stop_worker(worker)
        await broker.shutdown()


if __name__ == "__main__":
    asyncio.run(verify_worker_restart_recovery())
    print("Taskiq queued-message worker restart recovery passed")
