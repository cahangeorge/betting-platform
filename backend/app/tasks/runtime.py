import asyncio
import os
import socket
import sys
from collections.abc import Iterable
from contextlib import suppress

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import get_settings

settings = get_settings()


async def _ping_redis(url: str) -> None:
    client = Redis.from_url(url)
    try:
        if not await client.ping():
            raise RuntimeError("Redis ping returned a false response")
    except RedisError as exc:
        raise RuntimeError("Redis is unavailable") from exc
    finally:
        await client.aclose()


def runtime_instance_id() -> str:
    return os.environ.get("BET_TASKIQ_INSTANCE_ID", socket.gethostname())


def runtime_heartbeat_key(role: str) -> str:
    return f"bet:taskiq:{role}:{runtime_instance_id()}"


async def runtime_heartbeat(role: str) -> None:
    """Keep a role-specific Redis lease alive for container-local healthchecks."""
    client = Redis.from_url(settings.resolved_taskiq_broker_url)
    key = runtime_heartbeat_key(role)
    try:
        while True:
            await client.set(
                key,
                "ready",
                ex=settings.taskiq_runtime_stale_seconds,
            )
            await asyncio.sleep(settings.taskiq_runtime_heartbeat_seconds)
    finally:
        with suppress(RedisError):
            await client.delete(key)
        await client.aclose()


async def stop_runtime_heartbeat(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def verify_runtime_role(role: str) -> None:
    """Check this process instance's heartbeat (for worker/scheduler probes)."""
    client = Redis.from_url(settings.resolved_taskiq_broker_url)
    try:
        if not await client.get(runtime_heartbeat_key(role)):
            raise RuntimeError(f"Taskiq {role} heartbeat is stale or missing")
    except RedisError as exc:
        raise RuntimeError("Redis is unavailable") from exc
    finally:
        await client.aclose()


async def verify_any_runtime_role(role: str) -> None:
    """Check that at least one live instance advertises a role.

    API containers deliberately have a different hostname than worker and
    scheduler containers, so deployment readiness must not use the local
    instance key. Redis expiry makes every discovered lease fresh by design.
    """
    client = Redis.from_url(settings.resolved_taskiq_broker_url)
    try:
        pattern = f"bet:taskiq:{role}:*"
        async for key in client.scan_iter(match=pattern, count=100):
            if await client.get(key):
                return
        raise RuntimeError(f"Taskiq {role} heartbeat is stale or missing")
    except RedisError as exc:
        raise RuntimeError("Redis is unavailable") from exc
    finally:
        await client.aclose()


async def task_queue_probe(broker_url: str, result_backend_url: str) -> None:
    """Verify every distinct Redis endpoint required by the Taskiq runtime."""
    urls: Iterable[str] = dict.fromkeys((broker_url, result_backend_url))
    for url in urls:
        await _ping_redis(url)


if __name__ == "__main__":

    async def main() -> None:
        await task_queue_probe(
            settings.resolved_taskiq_broker_url,
            settings.resolved_taskiq_result_backend_url,
        )
        if len(sys.argv) > 1:
            await verify_runtime_role(sys.argv[1])

    asyncio.run(main())
    print("Taskiq runtime is ready")
