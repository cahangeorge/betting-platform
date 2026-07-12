from app.config import get_settings

settings = get_settings()

try:
    from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker
except ModuleNotFoundError as exc:  # pragma: no cover - dependency is validated by deployment/test installs.
    raise RuntimeError(
        "Taskiq Redis dependencies are not installed. Install backend dependencies before running workers."
    ) from exc


result_backend = RedisAsyncResultBackend(
    redis_url=settings.resolved_taskiq_result_backend_url,
    result_ex_time=settings.taskiq_result_ttl_seconds,
)

broker = RedisStreamBroker(
    url=settings.resolved_taskiq_broker_url,
    queue_name=settings.taskiq_queue_name,
    consumer_group_name=settings.taskiq_consumer_group,
).with_result_backend(result_backend)
