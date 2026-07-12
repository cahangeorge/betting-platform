from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bankroll import Bankroll, LedgerEntry
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.ticket import BetPlacement, Settlement, Ticket, TicketBatch, TicketLeg


def _market_probability_and_odds_fields(market: str, selection: str) -> tuple[str, str]:
    market_key = (market or "").lower()
    selection_key = (selection or "").lower()
    if market_key == "1x2":
        return {
            "home": ("home_prob", "home_odds"),
            "draw": ("draw_prob", "draw_odds"),
            "away": ("away_prob", "away_odds"),
        }.get(selection_key, ("home_prob", "home_odds"))
    if market_key in {"btts", "both_score", "both_teams_to_score"}:
        return {
            "yes": ("home_prob", "home_odds"),
            "no": ("away_prob", "away_odds"),
        }.get(selection_key, ("home_prob", "home_odds"))
    if market_key in {"ou_2_5", "over_under", "over_under_2_5", "overunder", "totals"}:
        return {
            "over": ("home_prob", "home_odds"),
            "under": ("away_prob", "away_odds"),
        }.get(selection_key, ("home_prob", "home_odds"))
    return "home_prob", "home_odds"


def _fallback_selection_for_prediction(prediction: ModelPrediction) -> str:
    market_key = (prediction.market or "").lower()
    if market_key == "1x2":
        candidates = [
            ("home", prediction.home_prob or 0),
            ("draw", prediction.draw_prob or 0),
            ("away", prediction.away_prob or 0),
        ]
    elif market_key in {"btts", "both_score", "both_teams_to_score"}:
        candidates = [("yes", prediction.home_prob or 0), ("no", prediction.away_prob or 0)]
    elif market_key in {"ou_2_5", "over_under", "over_under_2_5", "overunder", "totals"}:
        candidates = [("over", prediction.home_prob or 0), ("under", prediction.away_prob or 0)]
    else:
        candidates = [("home", prediction.home_prob or 0), ("away", prediction.away_prob or 0)]
    return max(candidates, key=lambda item: item[1])[0]


def _build_ticket_candidate(
    prediction: ModelPrediction,
    *,
    min_odds: float,
    max_odds: float,
) -> dict | None:
    quality_report = prediction.quality_report if isinstance(prediction.quality_report, dict) else {}
    model_payload = quality_report.get("model", {}) if isinstance(quality_report, dict) else {}
    selection = str(model_payload.get("pick") or _fallback_selection_for_prediction(prediction)).lower()
    probability_field, odds_field = _market_probability_and_odds_fields(prediction.market, selection)

    probability = getattr(prediction, probability_field, None)
    odds = getattr(prediction, odds_field, None)
    bookmaker = None

    market_payload = quality_report.get("market", {}) if isinstance(quality_report, dict) else {}
    odds_payload = market_payload.get("odds", {}) if isinstance(market_payload, dict) else {}
    selected_odds_payload = odds_payload.get(selection) if isinstance(odds_payload, dict) else None
    if isinstance(selected_odds_payload, dict):
        odds = selected_odds_payload.get("odds", odds)
        bookmaker = selected_odds_payload.get("bookmaker")

    if odds is None or probability is None:
        return None
    odds = float(odds)
    probability = float(probability)
    if odds < min_odds or odds > max_odds or odds <= 1:
        return None

    return {
        "model_prediction_id": prediction.id,
        "match_id": prediction.match_id,
        "market": prediction.market,
        "selection": selection,
        "odds": odds,
        "probability": probability,
        "bookmaker": bookmaker,
        "score": float(prediction.expected_value if prediction.expected_value is not None else probability),
    }


def _legs_for_difficulty(difficulty: str) -> int:
    return {
        "safe": 1,
        "low": 1,
        "balanced": 2,
        "medium": 2,
        "aggressive": 3,
        "high": 3,
    }.get((difficulty or "").lower(), 2)


def _recalculate_ticket_totals(ticket: Ticket) -> float:
    combined_odds = 1.0
    for leg in getattr(ticket, "legs", []) or []:
        combined_odds *= float(getattr(leg, "odds", 1.0) or 1.0)
    ticket.total_odds = round(combined_odds, 6)
    ticket.potential_return = round(float(ticket.stake or 0.0) * ticket.total_odds, 2)
    return ticket.total_odds


async def create_ticket(
    db: AsyncSession,
    user_id: int,
    ticket_type: str,
    stake: float,
    bankroll_id: int | None = None,
    legs_data: list[dict] | None = None,
    batch_id: int | None = None,
) -> Ticket:
    if legs_data is None:
        legs_data = []

    bankroll = None
    if bankroll_id:
        bankroll = await db.get(Bankroll, bankroll_id)
        if bankroll is None:
            raise ValueError(f"Bankroll {bankroll_id} not found")
        if bankroll.user_id != user_id:
            raise PermissionError(f"Bankroll {bankroll_id} does not belong to the current user")
        if bankroll.balance < stake:
            raise ValueError("Insufficient bankroll balance")

    combined_odds = 1.0
    for leg in legs_data:
        combined_odds *= leg.get("odds", 1.0)

    potential_return = stake * combined_odds

    ticket = Ticket(
        user_id=user_id,
        bankroll_id=bankroll_id,
        batch_id=batch_id,
        ticket_type=ticket_type,
        stake=stake,
        total_odds=combined_odds,
        potential_return=potential_return,
        status="open",
    )
    db.add(ticket)
    await db.flush()

    for leg_data in legs_data:
        leg = TicketLeg(
            ticket_id=ticket.id,
            model_prediction_id=leg_data.get("model_prediction_id"),
            match_id=leg_data.get("match_id"),
            selection=leg_data.get("selection", ""),
            market=leg_data.get("market", ""),
            odds=leg_data.get("odds", 1.0),
            bookmaker=leg_data.get("bookmaker"),
            status="pending",
        )
        db.add(leg)

    if bankroll_id and bankroll is not None:
        bankroll.balance -= stake
        ledger = LedgerEntry(
            bankroll_id=bankroll_id,
            ticket_id=ticket.id,
            entry_type="stake",
            amount=-stake,
            balance_after=bankroll.balance,
        )
        db.add(ledger)

    await db.flush()
    return ticket


async def generate_tickets(
    db: AsyncSession,
    *,
    user_id: int,
    bankroll_id: int | None,
    ticket_count: int,
    difficulty: str,
    market_types: list[str],
    min_odds: float,
    max_odds: float,
    stake: float,
    run_id: int | None = None,
) -> tuple[TicketBatch, list[Ticket]]:
    if ticket_count < 1:
        raise ValueError("ticket_count must be at least 1")
    if stake <= 0:
        raise ValueError("stake must be greater than 0")
    if min_odds > max_odds:
        raise ValueError("min_odds must be lower than or equal to max_odds")

    normalized_markets = {market.lower() for market in (market_types or ["1x2"])}
    run_stmt = select(PredictionRun.id).where(PredictionRun.user_id == user_id)
    if run_id is not None:
        run_stmt = run_stmt.where(
            PredictionRun.id == run_id,
            PredictionRun.status == "completed",
        )
    else:
        run_stmt = run_stmt.where(PredictionRun.status.in_(["completed", "partial"]))
        run_stmt = run_stmt.order_by(
            PredictionRun.completed_at.desc().nulls_last(),
            PredictionRun.started_at.desc().nulls_last(),
            PredictionRun.created_at.desc(),
            PredictionRun.id.desc(),
        )
    run_result = await db.execute(run_stmt.limit(1))
    selected_run_id = run_result.scalar_one_or_none()
    if selected_run_id is None:
        if run_id is not None:
            raise ValueError(f"Prediction run {run_id} not found or not eligible for ticket generation")
        raise ValueError("No completed prediction run available for ticket generation")

    stmt = (
        select(ModelPrediction)
        .where(
            ModelPrediction.run_id == selected_run_id,
            ModelPrediction.market.in_(normalized_markets),
        )
        .order_by(ModelPrediction.expected_value.desc().nulls_last(), ModelPrediction.created_at.desc())
        .limit(500)
    )
    result = await db.execute(stmt)
    predictions = list(result.scalars().all())

    candidates = [
        candidate
        for prediction in predictions
        if (candidate := _build_ticket_candidate(prediction, min_odds=min_odds, max_odds=max_odds)) is not None
    ]
    candidates.sort(key=lambda item: item["score"], reverse=True)
    if not candidates:
        raise ValueError("No prediction candidates match the requested markets and odds interval")

    legs_per_ticket = _legs_for_difficulty(difficulty)
    batch = TicketBatch(
        bankroll_id=bankroll_id,
        name=f"Generated {difficulty} tickets",
        strategy=difficulty,
        tickets_count=0,
        total_stake=0.0,
    )
    db.add(batch)
    await db.flush()

    tickets: list[Ticket] = []
    cursor = 0
    for _ in range(ticket_count):
        legs: list[dict] = []
        used_matches: set[int] = set()
        attempts = 0
        while len(legs) < legs_per_ticket and attempts < len(candidates) * 2:
            candidate = candidates[cursor % len(candidates)]
            cursor += 1
            attempts += 1
            match_id = candidate.get("match_id")
            if match_id in used_matches:
                continue
            used_matches.add(match_id)
            legs.append(candidate)

        if not legs:
            break

        ticket = await create_ticket(
            db=db,
            user_id=user_id,
            ticket_type="single" if len(legs) == 1 else "accumulator",
            stake=stake,
            bankroll_id=bankroll_id,
            legs_data=legs,
            batch_id=batch.id,
        )
        tickets.append(ticket)

    batch.tickets_count = len(tickets)
    batch.total_stake = round(len(tickets) * stake, 2)
    await db.flush()
    return batch, tickets


async def swap_ticket_legs(
    db: AsyncSession,
    *,
    user_id: int,
    source_ticket_id: int,
    source_leg_id: int,
    target_ticket_id: int,
    target_leg_id: int,
) -> tuple[Ticket, Ticket]:
    if source_leg_id == target_leg_id:
        raise ValueError("Choose two different legs to swap")

    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.legs).selectinload(TicketLeg.match), selectinload(Ticket.placements))
        .where(Ticket.user_id == user_id, Ticket.id.in_([source_ticket_id, target_ticket_id]))
    )
    result = await db.execute(stmt)
    tickets = {ticket.id: ticket for ticket in result.scalars().unique().all()}
    source_ticket = tickets.get(source_ticket_id)
    target_ticket = tickets.get(target_ticket_id)
    if source_ticket is None or target_ticket is None:
        raise ValueError("Ticket not found")

    source_leg = next((leg for leg in source_ticket.legs if leg.id == source_leg_id), None)
    target_leg = next((leg for leg in target_ticket.legs if leg.id == target_leg_id), None)
    if source_leg is None or target_leg is None:
        raise ValueError("Ticket leg not found")

    fields = ("model_prediction_id", "match_id", "selection", "market", "odds", "bookmaker")
    source_values = {field: getattr(source_leg, field) for field in fields}
    target_values = {field: getattr(target_leg, field) for field in fields}
    for field in fields:
        setattr(source_leg, field, target_values[field])
        setattr(target_leg, field, source_values[field])

    _recalculate_ticket_totals(source_ticket)
    _recalculate_ticket_totals(target_ticket)
    await db.flush()
    return source_ticket, target_ticket


async def settle_ticket(
    db: AsyncSession,
    ticket_id: int,
    outcome: str,
    return_amount: float = 0.0,
) -> Settlement:
    stmt = select(Ticket).options(selectinload(Ticket.legs)).where(Ticket.id == ticket_id)
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    pnl = return_amount - ticket.stake

    ticket.status = outcome
    await db.flush()

    settlement = Settlement(
        ticket_id=ticket_id,
        outcome=outcome,
        return_amount=return_amount,
        pnl=pnl,
    )
    db.add(settlement)

    for leg in ticket.legs:
        leg.status = outcome

    if ticket.bankroll_id and return_amount > 0:
        bankroll = await db.get(Bankroll, ticket.bankroll_id)
        if bankroll:
            bankroll.balance += return_amount
            ledger = LedgerEntry(
                bankroll_id=ticket.bankroll_id,
                ticket_id=ticket.id,
                entry_type="win" if outcome == "won" else "loss",
                amount=return_amount,
                balance_after=bankroll.balance,
            )
            db.add(ledger)

    await db.flush()
    await db.refresh(settlement)
    return settlement


async def place_bet(
    db: AsyncSession,
    ticket_id: int,
    bookmaker: str,
    bookmaker_account_id: int | None = None,
) -> BetPlacement:
    placement = BetPlacement(
        ticket_id=ticket_id,
        bookmaker_account_id=bookmaker_account_id,
        bookmaker=bookmaker,
        status="placed",
    )
    db.add(placement)
    await db.flush()
    return placement
