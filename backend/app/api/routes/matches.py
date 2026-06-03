"""Match CRUD routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_current_user
from app.models.match import Match
from app.models.user import User
from app.schemas import MatchCreate, MatchOut

router = APIRouter(prefix="/matches", tags=["matches"])


@router.post("", response_model=MatchOut, status_code=201)
async def create_match(
    payload: MatchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Match:
    match = Match(
        external_id=payload.external_id,
        home_team=payload.home_team,
        away_team=payload.away_team,
        league=payload.league,
        sport=payload.sport,
        kickoff_time=payload.kickoff_time,
        status=payload.status if payload.status else "upcoming",
        home_score=payload.home_score,
        away_score=payload.away_score,
        betfair_market_id=payload.betfair_market_id,
        smarkets_market_id=payload.smarkets_market_id,
    )
    db.add(match)
    await db.commit()
    return match


@router.get("", response_model=list[MatchOut])
async def list_matches(
    status: str | None = None,
    league: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[Match]:
    query = select(Match).where(Match.is_deleted.is_(False))
    if status:
        query = query.where(Match.status == status)
    if league:
        query = query.where(Match.league == league)
    query = query.order_by(Match.kickoff_time.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{match_id}", response_model=MatchOut)
async def get_match(match_id: str, db: AsyncSession = Depends(get_db)) -> Match:
    result = await db.execute(select(Match).where(Match.id == match_id, Match.is_deleted.is_(False)))
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match