"""Live match stats routes — ingest stats, query momentum."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_current_user
from app.models.match import Match, MatchStat
from app.models.user import User
from app.services.live_engine.momentum import LiveMomentumScorer

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/momentum/{match_id}", response_model=dict[str, Any])
async def get_momentum(
    match_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current momentum score for a match."""
    result = await db.execute(
        select(MatchStat).where(
            MatchStat.match_id == match_id,
            MatchStat.is_deleted.is_(False),
        ).order_by(MatchStat.elapsed.desc()).limit(1)
    )
    stat = result.scalar_one_or_none()
    if not stat:
        return {"match_id": match_id, "momentum": None, "stats_present": False}

    scorer = LiveMomentumScorer()
    ms = scorer.score_from_matchstat(match_id, stat)
    return {
        "match_id": match_id,
        "momentum": ms.to_dict(),
        "elapsed": stat.elapsed,
        "xg_home": stat.xg_home,
        "xg_away": stat.xg_away,
        "possession_home": stat.possession_home,
        "shots_on_target_home": stat.shots_on_target_home,
        "shots_on_target_away": stat.shots_on_target_away,
        "stats_present": True,
    }


@router.get("/history/{match_id}", response_model=list[dict[str, Any]])
async def get_stat_history(
    match_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return all stat snapshots for a match, newest first."""
    result = await db.execute(
        select(MatchStat).where(
            MatchStat.match_id == match_id,
            MatchStat.is_deleted.is_(False),
        ).order_by(MatchStat.elapsed.desc()).limit(limit)
    )
    return [{
        "id": s.id,
        "elapsed": s.elapsed,
        "source": s.source,
        "xg_home": s.xg_home,
        "xg_away": s.xg_away,
        "possession_home": s.possession_home,
        "possession_away": s.possession_away,
        "shots_on_target_home": s.shots_on_target_home,
        "shots_on_target_away": s.shots_on_target_away,
        "dangerous_attacks_home": s.dangerous_attacks_home,
        "dangerous_attacks_away": s.dangerous_attacks_away,
        "cards_home": s.cards_home,
        "cards_away": s.cards_away,
    } for s in result.scalars().all()]


@router.post("/ingest/{match_id}", response_model=dict[str, Any])
async def ingest_stats(
    match_id: str,
    source: str,
    elapsed: int,
    xg_home: float | None = None,
    xg_away: float | None = None,
    possession_home: float | None = None,
    possession_away: float | None = None,
    shots_home: int | None = None,
    shots_away: int | None = None,
    shots_on_target_home: int | None = None,
    shots_on_target_away: int | None = None,
    corners_home: int | None = None,
    corners_away: int | None = None,
    dangerous_attacks_home: int | None = None,
    dangerous_attacks_away: int | None = None,
    cards_home: int | None = None,
    cards_away: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ingest a live stat snapshot for a match."""
    # Verify match exists
    result = await db.execute(
        select(Match).where(Match.id == match_id, Match.is_deleted.is_(False))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Match not found")

    stat = MatchStat(
        match_id=match_id,
        source=source,
        elapsed=elapsed,
        xg_home=xg_home,
        xg_away=xg_away,
        possession_home=possession_home,
        possession_away=possession_away,
        shots_home=shots_home,
        shots_away=shots_away,
        shots_on_target_home=shots_on_target_home,
        shots_on_target_away=shots_on_target_away,
        corners_home=corners_home,
        corners_away=corners_away,
        dangerous_attacks_home=dangerous_attacks_home,
        dangerous_attacks_away=dangerous_attacks_away,
        cards_home=cards_home,
        cards_away=cards_away,
    )
    db.add(stat)
    await db.commit()

    scorer = LiveMomentumScorer()
    ms = scorer.score(match_id, {
        "elapsed": elapsed,
        "xg_home": xg_home or 0,
        "xg_away": xg_away or 0,
        "shots_on_target_home": shots_on_target_home or 0,
        "shots_on_target_away": shots_on_target_away or 0,
        "possession_home": possession_home or 50,
        "possession_away": possession_away or 50,
        "dangerous_attacks_home": dangerous_attacks_home or 0,
        "dangerous_attacks_away": dangerous_attacks_away or 0,
        "cards_home": cards_home or 0,
        "cards_away": cards_away or 0,
    })

    return {
        "status": "ingested",
        "stat_id": stat.id,
        "momentum": ms.to_dict(),
    }