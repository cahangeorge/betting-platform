import asyncio
import secrets

from app.tasks.broker import broker
from app.tasks.jobs import taskiq_healthcheck_task


async def verify_taskiq_round_trip(*, timeout_seconds: float = 15.0) -> None:
    nonce = secrets.token_urlsafe(18)
    await broker.startup()
    try:
        task = await taskiq_healthcheck_task.kiq(nonce)
        result = await task.wait_result(timeout=timeout_seconds)
    finally:
        await broker.shutdown()

    if result.is_err or result.return_value != nonce:
        raise RuntimeError("Taskiq worker returned an invalid healthcheck result")


if __name__ == "__main__":
    asyncio.run(verify_taskiq_round_trip())
    print("Taskiq worker round-trip passed")
