from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.bankroll import Bankroll, LedgerEntry
from app.models.match import Match, OddsEntry
from app.models.scrape import ScrapeJob
from app.models.ticket import Ticket, TicketLeg
from app.models.user import User
from app.schemas.dashboard import (
    DashboardJobLog,
    DashboardSummary,
    DashboardTicket,
    DashboardTicketLeg,
    DashboardUpcomingMatch,
)

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    match_count_result = await db.execute(select(func.count(Match.id)))
    total_matches = match_count_result.scalar() or 0

    ticket_count_result = await db.execute(select(func.count(Ticket.id)).where(Ticket.user_id == user.id))
    total_tickets = ticket_count_result.scalar() or 0

    won_result = await db.execute(
        select(func.count(Ticket.id)).where(Ticket.user_id == user.id, Ticket.status == "won")
    )
    won_count = won_result.scalar() or 0
    win_rate = (won_count / total_tickets * 100) if total_tickets > 0 else 0.0

    pnl_result = await db.execute(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0.0))
        .join(Bankroll, LedgerEntry.bankroll_id == Bankroll.id)
        .where(Bankroll.user_id == user.id)
    )
    total_pnl = pnl_result.scalar() or 0.0

    bankroll_result = await db.execute(
        select(func.coalesce(func.sum(Bankroll.balance), 0.0)).where(Bankroll.user_id == user.id)
    )
    active_bankroll = bankroll_result.scalar() or 0.0

    pending_result = await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.user_id == user.id,
            Ticket.status.in_(["open", "pending"]),
        )
    )
    pending_bets = pending_result.scalar() or 0

    return DashboardSummary(
        total_matches=total_matches,
        total_tickets=total_tickets,
        win_rate=round(win_rate, 1),
        total_pnl=round(total_pnl, 2),
        active_bankroll=round(active_bankroll, 2),
        pending_bets=pending_bets,
    )


@router.get("/recent-tickets", response_model=list[DashboardTicket])
async def get_recent_tickets(
    limit: int = Query(10, ge=1, le=100),
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Ticket).options(selectinload(Ticket.legs).selectinload(TicketLeg.match)).where(Ticket.user_id == user.id)
    )
    if date_from:
        stmt = stmt.where(Ticket.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Ticket.created_at <= date_to)
    stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    tickets = result.scalars().unique().all()

    out = []
    for t in tickets:
        legs = []
        for leg in t.legs:
            match = leg.match
            legs.append(
                DashboardTicketLeg(
                    match_id=leg.match_id,
                    home_team=match.home_team if match else None,
                    away_team=match.away_team if match else None,
                    market=leg.market,
                    selection=leg.selection,
                    odds=leg.odds,
                    status=leg.status,
                    home_score=match.home_score if match else None,
                    away_score=match.away_score if match else None,
                )
            )
        out.append(
            DashboardTicket(
                id=t.id,
                ticket_type=t.ticket_type,
                status=t.status,
                stake=t.stake,
                total_odds=t.total_odds,
                potential_return=t.potential_return,
                legs=legs,
                created_at=t.created_at,
            )
        )
    return out


@router.get("/upcoming", response_model=list[DashboardUpcomingMatch])
async def get_upcoming(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)

    stmt = (
        select(Match)
        .where(
            Match.match_date >= now,
            Match.match_date <= cutoff,
            Match.status == "scheduled",
        )
        .order_by(Match.match_date.asc())
        .limit(50)
    )
    result = await db.execute(stmt)
    matches = result.scalars().all()

    out = []
    for m in matches:
        odds_stmt = select(OddsEntry).where(OddsEntry.match_id == m.id).order_by(OddsEntry.created_at.desc()).limit(1)
        odds_result = await db.execute(odds_stmt)
        odds = odds_result.scalar_one_or_none()

        out.append(
            DashboardUpcomingMatch(
                id=m.id,
                home_team=m.home_team,
                away_team=m.away_team,
                start_time=m.match_date.isoformat() if m.match_date else None,
                league=m.competition,
                home_odds=odds.home_odds if odds else None,
                draw_odds=odds.draw_odds if odds else None,
                away_odds=odds.away_odds if odds else None,
            )
        )
    return out


@router.get("/job-logs", response_model=list[DashboardJobLog])
async def get_job_logs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    jobs = result.scalars().all()

    return [
        DashboardJobLog(
            id=j.id,
            job_type=j.job_type,
            status=j.status,
            league=j.league,
            started_at=j.started_at,
            completed_at=j.completed_at,
            error=j.error,
            created_at=j.created_at,
        )
        for j in jobs
    ]
