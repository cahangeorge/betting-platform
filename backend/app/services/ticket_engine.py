from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bankroll import Bankroll, LedgerEntry
from app.models.ticket import BetPlacement, Settlement, Ticket, TicketLeg


async def create_ticket(
    db: AsyncSession,
    user_id: int,
    ticket_type: str,
    stake: float,
    bankroll_id: int | None = None,
    legs_data: list[dict] | None = None,
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


async def settle_ticket(
    db: AsyncSession,
    ticket_id: int,
    outcome: str,
    return_amount: float = 0.0,
) -> dict:
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
    return {"ticket_id": ticket_id, "outcome": outcome, "pnl": pnl}


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
