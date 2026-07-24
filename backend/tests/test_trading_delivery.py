from types import SimpleNamespace

import pytest

from app.api.v1 import trading
from app.models.trading import ExecutionIntent
from app.schemas.trading import ExecutionCreateRequest
from app.services.trading_delivery import TradingDeliveryError, publish_trading_intent


class _DeliveryDb:
    def __init__(self):
        self.commits = 0
        self.added = []

    async def commit(self):
        self.commits += 1

    def add(self, value):
        self.added.append(value)


def _intent(*, delivery_status: str = "pending") -> ExecutionIntent:
    return ExecutionIntent(
        id=41,
        user_id=1,
        trading_account_id=2,
        ticket_id=3,
        odds_entry_id=4,
        idempotency_key="delivery-key",
        market="1x2",
        selection="home",
        stake=10,
        limit_price=2.2,
        status="queued",
        transport="taskiq",
        delivery_status=delivery_status,
        delivery_attempts=0,
    )


@pytest.mark.asyncio
async def test_failed_publish_is_durable_and_retryable_with_same_intent():
    db = _DeliveryDb()
    intent = _intent()

    async def fail(_execution_id: int):
        raise ConnectionError("redis unavailable")

    with pytest.raises(TradingDeliveryError, match="durable"):
        await publish_trading_intent(db, intent, sender=fail)

    assert intent.status == "queued"
    assert intent.delivery_status == "failed"
    assert intent.delivery_attempts == 1
    assert intent.last_delivery_error == "redis unavailable"
    assert db.commits == 2

    async def succeed(execution_id: int):
        assert execution_id == intent.id
        return SimpleNamespace(task_id="task-retry-2")

    await publish_trading_intent(db, intent, sender=succeed)

    assert intent.delivery_status == "published"
    assert intent.delivery_attempts == 2
    assert intent.transport_task_id == "task-retry-2"
    assert intent.last_delivery_error is None
    assert db.commits == 4


@pytest.mark.asyncio
async def test_published_intent_is_not_published_twice():
    db = _DeliveryDb()
    intent = _intent(delivery_status="published")

    async def unexpected(_execution_id: int):
        raise AssertionError("sender must not be called")

    returned = await publish_trading_intent(db, intent, sender=unexpected)

    assert returned is intent
    assert db.commits == 0


@pytest.mark.asyncio
async def test_create_execution_uses_canonical_inprocess_transport_without_taskiq(monkeypatch):
    db = _DeliveryDb()
    intent = _intent()
    calls = []

    async def create_intent(*_args, **_kwargs):
        # A durable queued intent may be resumed through the same idempotency
        # key after a process interruption, not only on its first request.
        return intent, False

    async def execute_locally(_db, execution_id):
        calls.append(execution_id)
        intent.status = "filled"
        intent.delivery_status = "completed"
        return intent

    async def load(_db, _execution_id, _user_id):
        return intent

    async def must_not_publish(*_args, **_kwargs):
        raise AssertionError("inprocess mode must not publish to Taskiq")

    monkeypatch.setattr(trading, "create_execution_intent", create_intent)
    monkeypatch.setattr(trading, "execute_paper_intent", execute_locally)
    monkeypatch.setattr(trading, "load_execution", load)
    monkeypatch.setattr(trading, "publish_trading_intent", must_not_publish)
    monkeypatch.setattr(trading, "get_settings", lambda: SimpleNamespace(task_queue_backend="inprocess"))

    response = await trading.create_execution(
        ExecutionCreateRequest(
            trading_account_id=2,
            ticket_id=3,
            idempotency_key="inprocess-stable-key",
        ),
        db=db,
        user=SimpleNamespace(id=1),
    )

    assert response is intent
    assert calls == [intent.id]
    assert intent.transport == "inprocess"
    assert intent.delivery_attempts == 1
