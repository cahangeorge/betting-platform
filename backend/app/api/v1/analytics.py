from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.bankroll import Bankroll, LedgerEntry
from app.models.match import Match
from app.models.prediction import ModelPrediction
from app.models.ticket import Ticket, TicketLeg
from app.models.user import User
from app.schemas.analytics import (
    EquityCurvePoint,
    PnlByLeague,
    PnlByModel,
    PnlTimeSeriesPoint,
)

router = APIRouter()


def _parse_period(period: str) -> timedelta:
    unit = period[-1]
    value = int(period[:-1])
    if unit == "d":
        return timedelta(days=value)
    if unit == "m":
        return timedelta(days=value * 30)
    if unit == "y":
        return timedelta(days=value * 365)
    return timedelta(days=30)


def _group_expression(group_by: str, col):
    if group_by == "week":
        return func.date_trunc("week", col)
    if group_by == "month":
        return func.date_trunc("month", col)
    return func.date_trunc("day", col)


@router.get("/pnl", response_model=list[PnlTimeSeriesPoint])
async def get_pnl(
    period: str = Query("30d"),
    group_by: str = Query("day"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    delta = _parse_period(period)
    since = datetime.now(timezone.utc) - delta

    user_bankrolls = select(Bankroll.id).where(Bankroll.user_id == user.id).scalar_subquery()

    trunc = _group_expression(group_by, LedgerEntry.created_at)

    stmt = (
        select(
            cast(trunc, String).label("date"),
            func.coalesce(func.sum(LedgerEntry.amount), 0.0).label("pnl"),
            func.count(LedgerEntry.id).label("bets_count"),
            func.sum(case((LedgerEntry.amount > 0, 1), else_=0)).label("wins"),
        )
        .where(
            LedgerEntry.bankroll_id.in_(user_bankrolls),
            LedgerEntry.created_at >= since,
        )
        .group_by(trunc)
        .order_by(trunc.asc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    cumulative = 0.0
    out = []
    for row in rows:
        cumulative += row.pnl
        out.append(
            PnlTimeSeriesPoint(
                date=row.date[:10] if row.date else "",
                pnl=round(row.pnl, 2),
                cumulative_pnl=round(cumulative, 2),
                bets_count=row.bets_count,
                wins=row.wins or 0,
            )
        )
    return out


@router.get("/pnl/by-league", response_model=list[PnlByLeague])
async def get_pnl_by_league(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user_bankrolls = select(Bankroll.id).where(Bankroll.user_id == user.id).scalar_subquery()

    stmt = (
        select(
            Match.competition.label("league"),
            func.coalesce(func.sum(LedgerEntry.amount), 0.0).label("total_pnl"),
            func.count(LedgerEntry.id).label("bets_count"),
            func.sum(case((LedgerEntry.amount > 0, 1), else_=0)).label("wins"),
        )
        .join(Ticket, LedgerEntry.ticket_id == Ticket.id)
        .join(TicketLeg, TicketLeg.ticket_id == Ticket.id)
        .join(Match, TicketLeg.match_id == Match.id)
        .where(
            LedgerEntry.bankroll_id.in_(user_bankrolls),
            Match.competition.isnot(None),
        )
        .group_by(Match.competition)
        .order_by(func.sum(LedgerEntry.amount).desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        PnlByLeague(
            league=row.league or "Unknown",
            total_pnl=round(row.total_pnl, 2),
            bets_count=row.bets_count,
            wins=row.wins or 0,
            win_rate=round((row.wins or 0) / row.bets_count * 100, 1) if row.bets_count > 0 else 0.0,
        )
        for row in rows
    ]


@router.get("/pnl/by-model", response_model=list[PnlByModel])
async def get_pnl_by_model(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user_bankrolls = select(Bankroll.id).where(Bankroll.user_id == user.id).scalar_subquery()
    model_bucket = func.coalesce(ModelPrediction.model_type, "manual")

    stmt = (
        select(
            model_bucket.label("model_type"),
            func.coalesce(func.sum(LedgerEntry.amount), 0.0).label("total_pnl"),
            func.count(LedgerEntry.id).label("bets_count"),
            func.sum(case((LedgerEntry.amount > 0, 1), else_=0)).label("wins"),
        )
        .join(Ticket, LedgerEntry.ticket_id == Ticket.id)
        .join(TicketLeg, TicketLeg.ticket_id == Ticket.id)
        .outerjoin(ModelPrediction, ModelPrediction.id == TicketLeg.model_prediction_id)
        .where(
            LedgerEntry.bankroll_id.in_(user_bankrolls),
        )
        .group_by(model_bucket)
        .order_by(func.sum(LedgerEntry.amount).desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        PnlByModel(
            model_type=row.model_type,
            total_pnl=round(row.total_pnl, 2),
            bets_count=row.bets_count,
            wins=row.wins or 0,
            win_rate=round((row.wins or 0) / row.bets_count * 100, 1) if row.bets_count > 0 else 0.0,
        )
        for row in rows
    ]


@router.get("/equity-curve", response_model=list[EquityCurvePoint])
async def get_equity_curve(
    period: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    delta = _parse_period(period)
    since = datetime.now(timezone.utc) - delta

    user_bankrolls = select(Bankroll.id).where(Bankroll.user_id == user.id).scalar_subquery()

    stmt = (
        select(
            cast(func.date_trunc("day", LedgerEntry.created_at), String).label("date"),
            LedgerEntry.balance_after.label("balance"),
        )
        .where(
            LedgerEntry.bankroll_id.in_(user_bankrolls),
            LedgerEntry.created_at >= since,
        )
        .order_by(LedgerEntry.created_at.asc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        EquityCurvePoint(
            date=row.date[:10] if row.date else "",
            balance=round(row.balance, 2),
        )
        for row in rows
    ]
