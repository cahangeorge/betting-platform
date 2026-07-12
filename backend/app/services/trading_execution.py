from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.flumine_paper import FluminePaperAdapter
from app.config import Settings, get_settings
from app.models.match import Match, OddsEntry
from app.models.ticket import Ticket, TicketLeg
from app.models.trading import ExecutionEvent, ExecutionIntent, ExecutionOrder, TradingAccount

SUPPORTED_MARKET = "1x2"
SUPPORTED_SELECTIONS = {"home", "draw", "away"}
TERMINAL_STATUSES = {"filled", "failed", "cancelled"}


def _persisted_price(odds: OddsEntry, selection: str) -> float | None:
    return {
        "home": odds.home_odds,
        "draw": odds.draw_odds,
        "away": odds.away_odds,
    }.get(selection)


def _event(
    intent: ExecutionIntent,
    event_type: str,
    to_status: str,
    *,
    from_status: str | None = None,
    message: str | None = None,
    payload: dict | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        intent=intent,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        message=message,
        payload=payload,
    )


async def load_execution(db: AsyncSession, execution_id: int, user_id: int) -> ExecutionIntent | None:
    result = await db.execute(
        select(ExecutionIntent)
        .options(selectinload(ExecutionIntent.orders), selectinload(ExecutionIntent.events))
        .where(ExecutionIntent.id == execution_id, ExecutionIntent.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_execution_intent(
    db: AsyncSession,
    *,
    user_id: int,
    trading_account_id: int,
    ticket_id: int,
    idempotency_key: str,
    side: str,
    order_type: str,
    settings: Settings | None = None,
) -> tuple[ExecutionIntent, bool]:
    settings = settings or get_settings()
    if not settings.trading_enabled or not settings.trading_paper_enabled:
        raise PermissionError("Paper trading execution is disabled")

    normalized_key = idempotency_key.strip()
    existing_result = await db.execute(
        select(ExecutionIntent).where(
            ExecutionIntent.user_id == user_id,
            ExecutionIntent.idempotency_key == normalized_key,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        if existing.ticket_id != ticket_id or existing.trading_account_id != trading_account_id:
            raise ValueError("Idempotency key is already used for a different execution")
        return existing, False

    normalized_side = side.strip().upper()
    normalized_order_type = order_type.strip().upper()
    if normalized_side != "BACK" or normalized_order_type != "LIMIT":
        raise ValueError("Paper execution supports BACK LIMIT orders only")

    account = await db.get(TradingAccount, trading_account_id)
    if account is None:
        raise LookupError("Trading account not found")
    if account.user_id != user_id:
        raise PermissionError("Trading account does not belong to the current user")
    if not account.enabled:
        raise ValueError("Trading account is disabled")
    if account.mode != "paper" or account.provider != "paper-local":
        raise PermissionError("Only enabled paper-local accounts can execute orders")

    ticket_result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.legs).selectinload(TicketLeg.match))
        .where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    )
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise LookupError("Ticket not found")
    if ticket.ticket_type != "single" or len(ticket.legs) != 1:
        raise ValueError("Paper execution supports single-leg tickets only")
    if ticket.status != "open":
        raise ValueError("Only open tickets can be executed")
    if ticket.stake <= 0:
        raise ValueError("Ticket stake must be positive")
    stake = Decimal(str(ticket.stake)).quantize(Decimal("0.01"))
    if account.balance < stake:
        raise ValueError("Insufficient paper trading balance")

    leg = ticket.legs[0]
    market = leg.market.strip().lower()
    selection = leg.selection.strip().lower()
    if market != SUPPORTED_MARKET or selection not in SUPPORTED_SELECTIONS:
        raise ValueError("Paper execution supports pre-match 1x2 home/draw/away selections only")
    match: Match | None = leg.match
    if match is None or match.status not in {"scheduled", "upcoming"}:
        raise ValueError("Paper execution supports pre-match tickets only")
    now = datetime.now(timezone.utc)
    if match.match_date is not None:
        match_date = match.match_date
        if match_date.tzinfo is None:
            match_date = match_date.replace(tzinfo=timezone.utc)
        if match_date <= now:
            raise ValueError("Paper execution supports pre-match tickets only")

    odds_result = await db.execute(
        select(OddsEntry)
        .where(OddsEntry.match_id == match.id, OddsEntry.market == SUPPORTED_MARKET)
        .order_by(OddsEntry.timestamp.desc().nullslast(), OddsEntry.created_at.desc(), OddsEntry.id.desc())
        .limit(1)
    )
    odds_entry = odds_result.scalar_one_or_none()
    if odds_entry is None:
        raise ValueError("No persisted 1x2 odds are available for this match")
    persisted_price = _persisted_price(odds_entry, selection)
    if persisted_price is None or persisted_price <= 1:
        raise ValueError(f"No persisted {selection} price is available for this match")
    price = Decimal(str(persisted_price)).quantize(Decimal("0.0001"))

    intent = ExecutionIntent(
        user_id=user_id,
        trading_account_id=account.id,
        ticket_id=ticket.id,
        odds_entry_id=odds_entry.id,
        idempotency_key=normalized_key,
        mode="paper",
        market=SUPPORTED_MARKET,
        selection=selection,
        side="BACK",
        order_type="LIMIT",
        stake=stake,
        limit_price=price,
        status="queued",
        transport=settings.task_queue_backend,
        delivery_status="pending",
    )
    db.add(intent)
    await db.flush()
    db.add(
        _event(
            intent,
            "execution.queued",
            "queued",
            message="Paper execution accepted for deterministic local processing.",
            payload={"odds_entry_id": odds_entry.id, "persisted_price": str(price)},
        )
    )
    await db.flush()
    return intent, True


async def execute_paper_intent(db: AsyncSession, execution_id: int) -> ExecutionIntent:
    result = await db.execute(
        select(ExecutionIntent)
        .options(selectinload(ExecutionIntent.orders), selectinload(ExecutionIntent.events))
        .where(ExecutionIntent.id == execution_id)
        .with_for_update()
    )
    intent = result.scalar_one_or_none()
    if intent is None:
        raise LookupError("Execution not found")
    if intent.status in TERMINAL_STATUSES:
        return intent
    if intent.mode != "paper":
        raise PermissionError("Live execution is not implemented")

    try:
        instruction = FluminePaperAdapter().build_back_limit(price=float(intent.limit_price), size=float(intent.stake))
    except (RuntimeError, ValueError) as exc:
        intent.status = "failed"
        intent.delivery_status = "completed"
        intent.error = f"Flumine paper instruction rejected: {exc}"
        intent.completed_at = datetime.now(timezone.utc)
        db.add(_event(intent, "execution.failed", "failed", from_status="queued", message=intent.error))
        await db.flush()
        return intent

    account = await db.get(TradingAccount, intent.trading_account_id, with_for_update=True)
    if account is None or not account.enabled or account.mode != "paper" or account.provider != "paper-local":
        intent.status = "failed"
        intent.error = "Paper-local trading account is unavailable"
        intent.completed_at = datetime.now(timezone.utc)
        db.add(_event(intent, "execution.failed", "failed", from_status="queued", message=intent.error))
        await db.flush()
        return intent
    if account.balance < intent.stake:
        intent.status = "failed"
        intent.error = "Insufficient paper trading balance"
        intent.completed_at = datetime.now(timezone.utc)
        db.add(_event(intent, "execution.failed", "failed", from_status="queued", message=intent.error))
        await db.flush()
        return intent

    intent.status = "accepted"
    db.add(_event(intent, "execution.accepted", "accepted", from_status="queued"))
    account.balance = (account.balance - intent.stake).quantize(Decimal("0.01"))
    order = ExecutionOrder(
        intent=intent,
        provider="flumine-paper-local",
        external_order_id=None,
        status="filled",
        requested_price=intent.limit_price,
        average_price=intent.limit_price,
        requested_size=intent.stake,
        matched_size=intent.stake,
    )
    db.add(order)
    intent.status = "filled"
    intent.delivery_status = "completed"
    intent.last_delivery_error = None
    intent.completed_at = datetime.now(timezone.utc)
    db.add(
        _event(
            intent,
            "execution.filled",
            "filled",
            from_status="accepted",
            message=(
                "Flumine BACK LIMIT contract filled locally at the persisted odds price; "
                "no external order was sent."
            ),
            payload={
                "framework": instruction.framework,
                "order_type": instruction.order_type,
                "persistence_type": instruction.persistence_type,
            },
        )
    )
    await db.flush()
    return intent


async def cancel_execution(db: AsyncSession, execution_id: int, user_id: int) -> ExecutionIntent:
    result = await db.execute(
        select(ExecutionIntent)
        .options(selectinload(ExecutionIntent.orders), selectinload(ExecutionIntent.events))
        .where(ExecutionIntent.id == execution_id, ExecutionIntent.user_id == user_id)
        .with_for_update()
    )
    intent = result.scalar_one_or_none()
    if intent is None:
        raise LookupError("Execution not found")
    if intent.status in TERMINAL_STATUSES:
        raise ValueError(f"Execution is already {intent.status}")
    previous = intent.status
    intent.status = "cancelled"
    intent.completed_at = datetime.now(timezone.utc)
    db.add(_event(intent, "execution.cancelled", "cancelled", from_status=previous))
    await db.flush()
    return intent
