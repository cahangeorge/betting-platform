from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import ExecutionIntent
from app.services.trading_execution import _event


class TradingDeliveryError(RuntimeError):
    """The durable intent exists, but publishing it to Taskiq failed."""


async def _send_taskiq(execution_id: int) -> Any:
    from app.tasks.trading import execute_trading_intent_task

    return await execute_trading_intent_task.kiq(execution_id)


async def publish_trading_intent(
    db: AsyncSession,
    intent: ExecutionIntent,
    *,
    sender: Callable[[int], Awaitable[Any]] | None = None,
) -> ExecutionIntent:
    """Publish a committed queued intent and persist the outcome.

    Failed delivery remains retryable through the same idempotency key. An
    ambiguous duplicate publish is safe because execution locks the intent and
    terminal states are no-ops.
    """
    if intent.status != "queued" or intent.delivery_status in {"published", "completed"}:
        return intent

    intent.transport = "taskiq"
    intent.delivery_status = "publishing"
    intent.delivery_attempts += 1
    intent.last_delivery_error = None
    await db.commit()

    try:
        task = await (sender or _send_taskiq)(intent.id)
    except Exception as exc:
        intent.delivery_status = "failed"
        intent.last_delivery_error = str(exc)[:2000]
        db.add(
            _event(
                intent,
                "execution.delivery_failed",
                "queued",
                from_status="queued",
                message="Taskiq publication failed; retry the same idempotency key to republish.",
                payload={"attempt": intent.delivery_attempts},
            )
        )
        await db.commit()
        raise TradingDeliveryError("Paper execution is durable but Taskiq publication failed") from exc

    intent.delivery_status = "published"
    intent.transport_task_id = getattr(task, "task_id", None)
    intent.last_delivery_error = None
    db.add(
        _event(
            intent,
            "execution.published",
            "queued",
            from_status="queued",
            payload={"attempt": intent.delivery_attempts, "transport_task_id": intent.transport_task_id},
        )
    )
    await db.commit()
    return intent
