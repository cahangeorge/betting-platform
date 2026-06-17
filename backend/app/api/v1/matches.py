from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user_optional
from app.database import get_db
from app.models.match import Match, OddsEntry
from app.models.user import User
from app.schemas.match import MatchDetailResponse, MatchListResponse, MatchResponse, OddsEntryResponse

router = APIRouter()


@router.get("", response_model=MatchListResponse)
async def list_matches(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    status: str | None = None,
    competition: str | None = None,
    team: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User | None = Depends(get_current_user_optional),
):
    query = select(Match).options(selectinload(Match.odds))
    count_query = select(func.count(Match.id))

    if status:
        query = query.where(Match.status == status)
        count_query = count_query.where(Match.status == status)
    if competition:
        query = query.where(Match.competition.ilike(f"%{competition}%"))
        count_query = count_query.where(Match.competition.ilike(f"%{competition}%"))
    if team:
        query = query.where((Match.home_team.ilike(f"%{team}%")) | (Match.away_team.ilike(f"%{team}%")))
        count_query = count_query.where((Match.home_team.ilike(f"%{team}%")) | (Match.away_team.ilike(f"%{team}%")))
    if date_from:
        query = query.where(Match.match_date >= date_from)
        count_query = count_query.where(Match.match_date >= date_from)
    if date_to:
        query = query.where(Match.match_date <= date_to)
        count_query = count_query.where(Match.match_date <= date_to)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Match.match_date.desc().nullslast(), Match.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    matches = result.scalars().all()

    return MatchListResponse(
        matches=[MatchResponse.model_validate(m) for m in matches],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{match_id}", response_model=MatchDetailResponse)
async def get_match(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User | None = Depends(get_current_user_optional),
):
    stmt = (
        select(Match)
        .options(
            selectinload(Match.odds),
            selectinload(Match.stats),
            selectinload(Match.sources),
        )
        .where(Match.id == match_id)
    )
    result = await db.execute(stmt)
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.get("/{match_id}/odds", response_model=list[OddsEntryResponse])
async def get_match_odds(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User | None = Depends(get_current_user_optional),
):
    stmt = select(OddsEntry).where(OddsEntry.match_id == match_id).order_by(OddsEntry.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()
