import asyncio

from app.config import get_settings
from app.tasks.runtime import runtime_heartbeat, stop_runtime_heartbeat
from app.tasks.worker_lanes import consumer_group_for_lane, normalize_worker_lane, queue_name_for_lane

settings = get_settings()
worker_lane = normalize_worker_lane(settings.taskiq_worker_lane)

try:
    from taskiq import TaskiqEvents, TaskiqState
    from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker
except ModuleNotFoundError as exc:  # pragma: no cover - dependency is validated by deployment/test installs.
    raise RuntimeError(
        "Taskiq Redis dependencies are not installed. Install backend dependencies before running workers."
    ) from exc


result_backend = RedisAsyncResultBackend(
    redis_url=settings.resolved_taskiq_result_backend_url,
    result_ex_time=settings.taskiq_result_ttl_seconds,
)

# A process consumes exactly one configured lane.  The durable run remains the
# work specification; Taskiq receives only run_id plus this routing label.
broker = RedisStreamBroker(
    url=settings.resolved_taskiq_broker_url,
    queue_name=queue_name_for_lane(settings, worker_lane),
    consumer_group_name=consumer_group_for_lane(settings, worker_lane),
).with_result_backend(result_backend)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def start_worker_heartbeat(state: TaskiqState) -> None:
    state.runtime_heartbeat_task = asyncio.create_task(
        runtime_heartbeat(f"worker:{worker_lane.value}"),
        name=f"taskiq-worker-{worker_lane.value}-heartbeat",
    )


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def stop_worker_heartbeat(state: TaskiqState) -> None:
    await stop_runtime_heartbeat(getattr(state, "runtime_heartbeat_task", None))
