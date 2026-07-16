import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bankroll import Bankroll, LedgerEntry
from app.models.ticket import Settlement, Ticket, TicketLeg
from app.services.clv_tracking import capture_ticket_closing_quotes

FINAL_MATCH_STATUSES = {"finished", "complete", "completed", "final", "ft"}
ACTIVE_TICKET_STATUSES = {"open"}


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TicketSettlementOutcome:
    status: str
    return_amount: float | None
    unresolved_legs: int = 0


@dataclass(frozen=True)
class SettlementRunSummary:
    checked_tickets: int = 0
    settled_tickets: int = 0
    won_tickets: int = 0
    lost_tickets: int = 0
    void_tickets: int = 0
    pending_tickets: int = 0
    updated_legs: int = 0


@dataclass(frozen=True)
class ModelPredictionEvaluation:
    status: str
    predicted_selection: str | None = None
    actual_selection: str | None = None


def _normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9_.:+-]+", "_", (value or "").strip().lower()).strip("_")


def _score(match: Any) -> tuple[int, int] | None:
    home_score = getattr(match, "home_score", None)
    away_score = getattr(match, "away_score", None)
    if home_score is None or away_score is None:
        return None
    try:
        return int(home_score), int(away_score)
    except (TypeError, ValueError):
        return None


def _is_finished(match: Any) -> bool:
    if _score(match) is None:
        return False
    return _normalize(getattr(match, "status", None)) in FINAL_MATCH_STATUSES


def _over_under_line(market: str) -> float:
    normalized = _normalize(market)
    match = re.search(r"(\d+(?:[_.]\d+)?)$", normalized)
    if not match:
        return 2.5
    return float(match.group(1).replace("_", "."))


def _selection_group(selection: str) -> str:
    normalized = _normalize(selection)
    if normalized in {"1", "h", "home", "home_win", "team_home"}:
        return "home"
    if normalized in {"x", "d", "draw"}:
        return "draw"
    if normalized in {"2", "a", "away", "away_win", "team_away"}:
        return "away"
    if normalized in {"yes", "y", "true", "both", "btts_yes"}:
        return "yes"
    if normalized in {"no", "n", "false", "btts_no"}:
        return "no"
    if normalized in {"over", "o", "over_2_5"}:
        return "over"
    if normalized in {"under", "u", "under_2_5"}:
        return "under"
    return normalized


def _market_group(market: str) -> str:
    normalized = _normalize(market)
    if normalized in {"1x2", "match_winner", "matchwinner", "home_away"}:
        return "1x2"
    if normalized in {"btts", "both_teams_to_score", "both_score", "bothteams"}:
        return "btts"
    if normalized.startswith(("ou_", "ou", "over_under", "overunder", "totals")):
        return "over_under"
    return normalized


def _actual_selection_for_match(match: Any, market: str) -> str | None:
    if match is None or not _is_finished(match):
        return None

    score = _score(match)
    if score is None:
        return None

    home_score, away_score = score
    market_group = _market_group(market)

    if market_group == "1x2":
        if home_score > away_score:
            return "home"
        if away_score > home_score:
            return "away"
        return "draw"

    if market_group == "btts":
        return "yes" if home_score > 0 and away_score > 0 else "no"

    if market_group == "over_under":
        total_goals = home_score + away_score
        line = _over_under_line(market)
        if total_goals == line:
            return "void"
        return "over" if total_goals > line else "under"

    return None


def _predicted_selection(prediction: Any) -> str | None:
    market = _market_group(getattr(prediction, "market", ""))
    home_prob = float(getattr(prediction, "home_prob", 0.0) or 0.0)
    draw_prob = getattr(prediction, "draw_prob", None)
    away_prob = float(getattr(prediction, "away_prob", 0.0) or 0.0)

    if market == "1x2":
        outcomes = [("home", home_prob), ("draw", float(draw_prob or 0.0)), ("away", away_prob)]
    elif market == "btts":
        outcomes = [("yes", home_prob), ("no", away_prob)]
    elif market == "over_under":
        outcomes = [("over", home_prob), ("under", away_prob)]
    else:
        return None

    return max(outcomes, key=lambda item: item[1])[0]


def evaluate_model_prediction(prediction: Any) -> ModelPredictionEvaluation:
    predicted = _predicted_selection(prediction)
    actual = _actual_selection_for_match(getattr(prediction, "match", None), getattr(prediction, "market", ""))

    if predicted is None:
        return ModelPredictionEvaluation(status="unsupported")
    if actual is None:
        return ModelPredictionEvaluation(status="pending", predicted_selection=predicted)
    if actual == "void":
        return ModelPredictionEvaluation(status="void", predicted_selection=predicted, actual_selection=actual)
    return ModelPredictionEvaluation(
        status="won" if predicted == actual else "lost",
        predicted_selection=predicted,
        actual_selection=actual,
    )


def evaluate_ticket_leg(leg: Any, *, unsupported_policy: str = "pending") -> str:
    """Return won/lost/pending/void for a ticket leg using the linked match final score."""
    match = getattr(leg, "match", None)
    if match is None or not _is_finished(match):
        return "pending"

    score = _score(match)
    if score is None:
        return "pending"

    home_score, away_score = score
    selection = _selection_group(getattr(leg, "selection", ""))
    market = _market_group(getattr(leg, "market", ""))

    if market == "1x2":
        actual = "draw"
        if home_score > away_score:
            actual = "home"
        elif away_score > home_score:
            actual = "away"
        return "won" if selection == actual else "lost"

    if market == "btts":
        actual = "yes" if home_score > 0 and away_score > 0 else "no"
        return "won" if selection == actual else "lost"

    if market == "over_under":
        total_goals = home_score + away_score
        line = _over_under_line(getattr(leg, "market", ""))
        if total_goals == line:
            return "void"
        actual = "over" if total_goals > line else "under"
        return "won" if selection == actual else "lost"

    return "void" if unsupported_policy == "void" else "pending"


def resolve_finished_ticket(ticket: Any, *, unsupported_policy: str = "pending") -> TicketSettlementOutcome:
    """Update leg statuses in-memory and return the ticket settlement decision."""
    unresolved = 0
    won_odds_product = 1.0
    has_won_leg = False
    statuses: list[str] = []

    for leg in getattr(ticket, "legs", []) or []:
        status = evaluate_ticket_leg(leg, unsupported_policy=unsupported_policy)
        leg.status = status
        statuses.append(status)
        if status == "pending":
            unresolved += 1
        elif status == "won":
            has_won_leg = True
            won_odds_product *= float(getattr(leg, "odds", 1.0) or 1.0)

    if not statuses:
        return TicketSettlementOutcome(status="open", return_amount=None, unresolved_legs=0)
    if unresolved:
        return TicketSettlementOutcome(status="open", return_amount=None, unresolved_legs=unresolved)
    if "lost" in statuses:
        return TicketSettlementOutcome(status="lost", return_amount=0.0)
    if all(status == "void" for status in statuses):
        return TicketSettlementOutcome(status="void", return_amount=float(getattr(ticket, "stake", 0.0) or 0.0))

    stake = float(getattr(ticket, "stake", 0.0) or 0.0)
    return_amount = stake * won_odds_product if has_won_leg else stake
    return TicketSettlementOutcome(status="won", return_amount=round(return_amount, 2))


async def _has_settlement(db: AsyncSession, ticket_id: int) -> bool:
    result = await db.execute(select(Settlement.id).where(Settlement.ticket_id == ticket_id).limit(1))
    return result.scalar_one_or_none() is not None


async def _write_settlement(db: AsyncSession, ticket: Ticket, outcome: TicketSettlementOutcome) -> None:
    if outcome.return_amount is None or await _has_settlement(db, ticket.id):
        return

    return_amount = _money(outcome.return_amount)
    pnl = _money(return_amount - _money(ticket.stake))
    db.add(
        Settlement(
            ticket_id=ticket.id,
            outcome=outcome.status,
            return_amount=return_amount,
            pnl=pnl,
        )
    )

    if ticket.bankroll_id and outcome.return_amount > 0:
        bankroll_result = await db.execute(
            select(Bankroll).where(Bankroll.id == ticket.bankroll_id).with_for_update()
        )
        bankroll = bankroll_result.scalar_one_or_none()
        if bankroll is not None:
            bankroll.balance = _money(bankroll.balance) + return_amount
            db.add(
                LedgerEntry(
                    bankroll_id=ticket.bankroll_id,
                    ticket_id=ticket.id,
                    entry_type="win" if outcome.status == "won" else "void",
                    amount=return_amount,
                    balance_after=bankroll.balance,
                )
            )


async def settle_due_tickets(
    db: AsyncSession,
    *,
    user_id: int,
    now: datetime | None = None,
    unsupported_policy: str = "pending",
    limit: int = 100,
) -> SettlementRunSummary:
    """Settle open tickets whose linked matches now have final scores."""
    now = now or datetime.now(timezone.utc)
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.legs).selectinload(TicketLeg.match))
        .where(Ticket.user_id == user_id, Ticket.status.in_(ACTIVE_TICKET_STATUSES))
        .order_by(Ticket.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    tickets = [ticket for ticket in result.scalars().unique().all() if ticket.status in ACTIVE_TICKET_STATUSES]

    settled = won = lost = void = pending = updated_legs = 0

    for ticket in tickets:
        before = [leg.status for leg in ticket.legs]
        outcome = resolve_finished_ticket(ticket, unsupported_policy=unsupported_policy)
        updated_legs += sum(1 for previous, leg in zip(before, ticket.legs, strict=False) if previous != leg.status)

        if outcome.status == "open":
            pending += 1
            continue

        await capture_ticket_closing_quotes(db, ticket)
        ticket.status = outcome.status
        ticket.updated_at = now
        await _write_settlement(db, ticket, outcome)
        settled += 1
        if outcome.status == "won":
            won += 1
        elif outcome.status == "lost":
            lost += 1
        elif outcome.status == "void":
            void += 1

    await db.flush()
    return SettlementRunSummary(
        checked_tickets=len(tickets),
        settled_tickets=settled,
        won_tickets=won,
        lost_tickets=lost,
        void_tickets=void,
        pending_tickets=pending,
        updated_legs=updated_legs,
    )
