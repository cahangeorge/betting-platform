from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.config import get_settings

settings = get_settings()

trading_result_backend = RedisAsyncResultBackend(
    redis_url=settings.resolved_taskiq_result_backend_url,
    result_ex_time=settings.taskiq_result_ttl_seconds,
)

trading_broker = RedisStreamBroker(
    url=settings.resolved_taskiq_broker_url,
    queue_name=settings.trading_taskiq_queue_name,
    consumer_group_name=f"{settings.taskiq_consumer_group}-trading",
).with_result_backend(trading_result_backend)
