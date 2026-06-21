from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.ticket import Settlement, Ticket, TicketBatch, TicketLeg
from app.models.user import User
from app.schemas.ticket import (
    BetPlacementResponse,
    SettlementResponse,
    TicketBatchResponse,
    TicketCreateRequest,
    TicketDetailResponse,
    TicketResponse,
    TicketStatsResponse,
)
from app.services.ticket_engine import create_ticket, place_bet, settle_ticket

router = APIRouter()


def _resolve_ticket_reference(ticket: Ticket) -> str:
    placements = getattr(ticket, "placements", []) or []
    for placement in placements:
        reference = getattr(placement, "reference", None)
        if reference:
            return reference
    return f"TKT-{ticket.id}"


def _serialize_ticket_summary(
    ticket: Ticket,
    *,
    reference: str,
    actual_return: float | None,
    settled_at,
) -> TicketResponse:
    def serialize_leg_match(leg: TicketLeg) -> dict | None:
        match = getattr(leg, "match", None)
        if match is None:
            return None
        return {
            "id": match.id,
            "league": getattr(match, "competition", None) or getattr(match, "league", None),
            "home_team": match.home_team,
            "away_team": match.away_team,
            "start_time": getattr(match, "match_date", None) or getattr(match, "start_time", None),
            "status": match.status,
        }

    legs = [
        {
            "id": leg.id,
            "ticket_id": leg.ticket_id,
            "model_prediction_id": leg.model_prediction_id,
            "match_id": leg.match_id,
            "selection": leg.selection,
            "market": leg.market,
            "odds": leg.odds,
            "bookmaker": leg.bookmaker,
            "status": leg.status,
            "created_at": leg.created_at,
            "match": serialize_leg_match(leg),
        }
        for leg in getattr(ticket, "legs", []) or []
    ]

    return TicketResponse(
        id=ticket.id,
        reference=reference,
        user_id=ticket.user_id,
        bankroll_id=ticket.bankroll_id,
        batch_id=ticket.batch_id,
        ticket_type=ticket.ticket_type,
        stake=ticket.stake,
        total_odds=ticket.total_odds,
        potential_return=ticket.potential_return,
        actual_return=actual_return,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        settled_at=settled_at,
        legs=legs,
    )


def _compute_ticket_stats(
    tickets: list[Ticket], settlements_by_ticket_id: dict[int, Settlement]
) -> dict[str, float | int]:
    return {
        "total": len(tickets),
        "won": sum(1 for ticket in tickets if ticket.status == "won"),
        "lost": sum(1 for ticket in tickets if ticket.status == "lost"),
        "profit_loss": round(
            sum(
                (settlements_by_ticket_id.get(ticket.id).pnl if settlements_by_ticket_id.get(ticket.id) else 0.0)
                for ticket in tickets
            ),
            2,
        ),
    }


async def _load_latest_settlements(db: AsyncSession, ticket_ids: list[int]) -> dict[int, Settlement]:
    if not ticket_ids:
        return {}

    result = await db.execute(select(Settlement).where(Settlement.ticket_id.in_(ticket_ids)))
    settlements = result.scalars().all()

    latest_by_ticket_id: dict[int, Settlement] = {}
    for settlement in settlements:
        if settlement.ticket_id is None:
            continue
        previous = latest_by_ticket_id.get(settlement.ticket_id)
        if previous is None or settlement.settled_at > previous.settled_at:
            latest_by_ticket_id[settlement.ticket_id] = settlement

    return latest_by_ticket_id


async def _load_ticket_summary(db: AsyncSession, ticket_id: int, user_id: int) -> TicketResponse | None:
    stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.legs).selectinload(TicketLeg.match),
            selectinload(Ticket.placements),
        )
        .where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    )
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        return None

    settlements_by_ticket_id = await _load_latest_settlements(db, [ticket.id])
    settlement = settlements_by_ticket_id.get(ticket.id)
    return _serialize_ticket_summary(
        ticket,
        reference=_resolve_ticket_reference(ticket),
        actual_return=settlement.return_amount if settlement else None,
        settled_at=settlement.settled_at if settlement else None,
    )


@router.get("", response_model=list[TicketResponse])
async def list_tickets(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.legs).selectinload(TicketLeg.match),
            selectinload(Ticket.placements),
        )
        .where(Ticket.user_id == user.id)
    )
    if status:
        stmt = stmt.where(Ticket.status == status)
    stmt = stmt.order_by(Ticket.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    tickets = result.scalars().unique().all()
    settlements_by_ticket_id = await _load_latest_settlements(db, [ticket.id for ticket in tickets])

    return [
        _serialize_ticket_summary(
            ticket,
            reference=_resolve_ticket_reference(ticket),
            actual_return=settlements_by_ticket_id[ticket.id].return_amount
            if ticket.id in settlements_by_ticket_id
            else None,
            settled_at=settlements_by_ticket_id[ticket.id].settled_at
            if ticket.id in settlements_by_ticket_id
            else None,
        )
        for ticket in tickets
    ]


@router.get("/stats", response_model=TicketStatsResponse)
async def get_ticket_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Ticket).where(Ticket.user_id == user.id))
    tickets = result.scalars().all()
    settlements_by_ticket_id = await _load_latest_settlements(db, [ticket.id for ticket in tickets])
    return TicketStatsResponse(**_compute_ticket_stats(tickets, settlements_by_ticket_id))


@router.post("", response_model=TicketResponse, status_code=201)
async def create_new_ticket(
    body: TicketCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        ticket = await create_ticket(
            db=db,
            user_id=user.id,
            ticket_type=body.ticket_type,
            stake=body.stake,
            bankroll_id=body.bankroll_id,
            legs_data=body.legs,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = await _load_ticket_summary(db, ticket.id, user.id)
    if summary is None:
        raise HTTPException(status_code=500, detail="Created ticket could not be reloaded")
    return summary


@router.get("/{ticket_id}", response_model=TicketDetailResponse)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.legs), selectinload(Ticket.placements))
        .where(Ticket.id == ticket_id, Ticket.user_id == user.id)
    )
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/{ticket_id}/place", response_model=BetPlacementResponse)
async def place_ticket(
    ticket_id: int,
    bookmaker: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user.id)
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    placement = await place_bet(db, ticket_id, bookmaker)
    return placement


@router.post("/{ticket_id}/settle", response_model=SettlementResponse)
async def settle_ticket_endpoint(
    ticket_id: int,
    outcome: str,
    return_amount: float = 0.0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user.id)
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    result_data = await settle_ticket(db, ticket_id, outcome, return_amount)
    return result_data


@router.get("/batches", response_model=list[TicketBatchResponse])
async def list_batches(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(TicketBatch).order_by(TicketBatch.created_at.desc()).limit(50)
    result = await db.execute(stmt)
    return result.scalars().all()
