from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.api.v1.catalog import CATALOG
from app.database import get_db
from app.models.match import Match
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.prediction import PredictionRunDetailResponse, PredictionRunResponse
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyResponse,
    StrategyRunRequest,
    StrategyRunResponse,
    StrategyUpdateRequest,
)
from app.services.prediction_engine import execute_single_model_run
from app.services.prediction_engine import resolve_prediction_model_key
from app.services.python_bridge import BridgeError

router = APIRouter()

SUPPORTED_MARKETS = {"1x2", "btts", "ou_2_5"}
MARKET_ALIASES = {
    "1x2": "1x2",
    "btts": "btts",
    "ou_2_5": "ou_2_5",
    "over_under_2.5": "ou_2_5",
    "over/under 2.5": "ou_2_5",
}


def _parse_filter_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if len(value) == 10:
        parsed = datetime.combine(parsed.date(), time.max if end_of_day else time.min)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def _resolve_league_names(country_filters: list[str], league_filters: list[str]) -> list[str]:
    league_names_by_id = {
        league.id.lower(): league.name
        for country in CATALOG
        for league in country.leagues
    }

    if league_filters:
        resolved = [league_names_by_id.get(league_id.lower(), league_id) for league_id in league_filters]
    elif country_filters:
        resolved = [
            league.name
            for country in CATALOG
            if country.country in country_filters
            for league in country.leagues
        ]
    else:
        resolved = []

    unique_names: list[str] = []
    seen: set[str] = set()
    for name in resolved:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique_names.append(name)

    return unique_names


def _normalize_strategy_markets(markets: list[str] | None) -> list[str]:
    if not markets:
        return ["1x2"]

    normalized: list[str] = []
    seen: set[str] = set()
    for market in markets:
        resolved = MARKET_ALIASES.get(market.lower())
        if resolved and resolved not in seen and resolved in SUPPORTED_MARKETS:
            seen.add(resolved)
            normalized.append(resolved)

    return normalized or ["1x2"]


def _build_strategy_execution_config(strategy: Strategy) -> dict:
    params = strategy.parameters if isinstance(strategy.parameters, dict) else {}
    model_kwargs = params.get("model_kwargs")
    fit_kwargs = params.get("fit_kwargs")

    return {
        "model_key": resolve_prediction_model_key(strategy.model_type),
        "training_limit": int(params.get("training_limit", 380) or 380),
        "target_limit": int(params.get("target_limit", 50) or 50),
        "max_goals": int(params.get("max_goals", 10) or 10),
        "model_kwargs": model_kwargs if isinstance(model_kwargs, dict) else {},
        "fit_kwargs": fit_kwargs if isinstance(fit_kwargs, dict) else {},
        "use_time_decay": bool(params.get("use_time_decay", False)),
        "time_decay_xi": float(params.get("time_decay_xi", params.get("xi", 0.0018)) or 0.0018),
    }


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(Strategy).order_by(Strategy.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(
    body: StrategyCreateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        resolve_prediction_model_key(body.model_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    strategy = Strategy(
        name=body.name,
        description=body.description,
        model_type=body.model_type,
        parameters=body.parameters,
        weights=body.weights,
        is_active=body.is_active,
    )
    db.add(strategy)
    await db.flush()
    return strategy


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(Strategy).where(Strategy.id == strategy_id)
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    body: StrategyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(Strategy).where(Strategy.id == strategy_id)
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    update_data = body.model_dump(exclude_unset=True)
    if "model_type" in update_data and update_data["model_type"] is not None:
        try:
            resolve_prediction_model_key(update_data["model_type"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    for field, value in update_data.items():
        setattr(strategy, field, value)

    await db.flush()
    await db.refresh(strategy)
    return strategy


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(Strategy).where(Strategy.id == strategy_id)
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await db.delete(strategy)
    await db.flush()


@router.post("/{strategy_id}/run", response_model=StrategyRunResponse)
async def run_strategy(
    strategy_id: int,
    body: StrategyRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Strategy).where(Strategy.id == strategy_id)
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Normalise markets
    markets = _normalize_strategy_markets(body.markets)

    try:
        execution_config = _build_strategy_execution_config(strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Resolve match IDs
    match_ids = body.match_ids
    if not match_ids:
        filters = body.filters
        match_stmt = select(Match.id).where(Match.status == "scheduled")

        if filters:
            league_names = _resolve_league_names(filters.countries, filters.leagues)
            if league_names:
                competition_conditions = [Match.competition.ilike(f"%{league_name}%") for league_name in league_names]
                match_stmt = match_stmt.where(or_(*competition_conditions))

            date_from = _parse_filter_datetime(filters.date_from)
            if date_from is not None:
                match_stmt = match_stmt.where(Match.match_date.is_not(None), Match.match_date >= date_from)

            date_to = _parse_filter_datetime(filters.date_to, end_of_day=True)
            if date_to is not None:
                match_stmt = match_stmt.where(Match.match_date.is_not(None), Match.match_date <= date_to)

        match_stmt = match_stmt.order_by(Match.match_date.asc().nulls_last(), Match.id.asc()).limit(50)
        match_result = await db.execute(match_stmt)
        match_ids = [row[0] for row in match_result.all()]

    if not match_ids:
        return StrategyRunResponse(run_id=0, status="no_matches")

    # Fetch matches to group by league
    match_stmt = select(Match).where(Match.id.in_(match_ids))
    match_result = await db.execute(match_stmt)
    matches = list(match_result.scalars().all())

    # Group match IDs by league
    leagues: dict[str, list[int]] = {}
    for m in matches:
        league = m.competition or "Unknown"
        if league not in leagues:
            leagues[league] = []
        leagues[league].append(m.id)

    # Create the prediction run
    run = PredictionRun(
        user_id=user.id,
        name=f"Strategy: {strategy.name}",
        model_type=strategy.model_type,
        ensemble=strategy.model_type == "ensemble",
        status="running",
        matches_count=len(match_ids),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    total_written = 0
    per_league = []
    league_errors: list[str] = []

    # For each league, run the real prediction engine
    for league, league_match_ids in leagues.items():
        try:
            result = await execute_single_model_run(
                db=db,
                run_id=run.id,
                model_key=execution_config["model_key"],
                league=league,
                markets=markets,
                target_mode="matches",
                target_match_ids=league_match_ids,
                training_limit=execution_config["training_limit"],
                target_limit=execution_config["target_limit"],
                max_goals=execution_config["max_goals"],
                model_kwargs=execution_config["model_kwargs"],
                fit_kwargs=execution_config["fit_kwargs"],
                use_time_decay=execution_config["use_time_decay"],
                time_decay_xi=execution_config["time_decay_xi"],
            )
            written = result.get("written", 0)
            target_matches = result.get("target_matches", 0)
            failed = result.get("failed", 0)

            if written == 0 and target_matches > 0:
                message = f"{league}: prediction bridge produced no results for {target_matches} target matches"
                league_errors.append(message)
                per_league.append({"league": league, "status": "failed", "error": message, "matches": len(league_match_ids)})
                continue

            if failed > 0:
                message = f"{league}: {failed} target matches failed during bridge execution"
                league_errors.append(message)
                per_league.append(
                    {
                        "league": league,
                        "status": "partial",
                        "error": message,
                        "matches": len(league_match_ids),
                        "written": written,
                    }
                )
            else:
                per_league.append({"league": league, "status": "ok", "matches": len(league_match_ids), "written": written})

            total_written += written
        except ValueError as e:
            league_errors.append(f"{league}: {e}")
            per_league.append(
                {"league": league, "status": "failed", "error": str(e), "matches": len(league_match_ids)}
            )
        except BridgeError as e:
            league_errors.append(f"{league}: {e}")
            per_league.append(
                {"league": league, "status": "failed", "error": str(e), "matches": len(league_match_ids)}
            )

    await db.flush()

    if total_written == 0:
        run.status = "failed"
    elif league_errors:
        run.status = "partial"
    else:
        run.status = "completed"

    run.completed_at = datetime.now(timezone.utc)
    run.matches_count = total_written
    run.error = " | ".join(league_errors) if league_errors else None
    await db.flush()

    return StrategyRunResponse(
        run_id=run.id,
        status=run.status,
        matches_count=total_written,
        error=run.error,
    )


@router.get("/runs", response_model=list[PredictionRunResponse])
async def list_strategy_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(PredictionRun)
        .where(PredictionRun.user_id == user.id, PredictionRun.name.ilike("Strategy:%"))
        .order_by(PredictionRun.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=PredictionRunDetailResponse)
async def get_strategy_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(PredictionRun)
        .options(
            selectinload(PredictionRun.model_predictions),
            selectinload(PredictionRun.ensemble_predictions),
        )
        .where(PredictionRun.id == run_id, PredictionRun.user_id == user.id)
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Strategy run not found")
    return run
