import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_current_user
from app.api.v1.catalog import CATALOG
from app.api.v1.live import broadcast_prediction_update
from app.database import get_db
from app.models.match import Match
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.prediction import PredictionRunDetailResponse, PredictionRunResponse
from app.schemas.strategy import (
    StrategyBatchRunRequest,
    StrategyBatchRunResponse,
    StrategyCreateRequest,
    StrategyDuplicateRequest,
    StrategyResponse,
    StrategyRunRequest,
    StrategyRunResponse,
    StrategyUpdateRequest,
)
from app.services.analysis_flow import (
    load_analysis_strategies,
    resolve_dataset_match_ids,
    summarize_analysis_batch_status,
)
from app.services.prediction_engine import execute_single_model_run, resolve_prediction_model_key
from app.services.python_bridge import BridgeError

router = APIRouter()

SUPPORTED_MARKETS = {"1x2", "btts", "ou_2_5"}
LIVE_PREDICTION_BROADCAST_STATUSES = {"running", "completed", "partial", "failed"}
ACTIVE_DEDUPE_RUN_STATUSES = {"running", "completed"}
MARKET_ALIASES = {
    "1x2": "1x2",
    "btts": "btts",
    "ou_2_5": "ou_2_5",
    "over_under_2.5": "ou_2_5",
    "over/under 2.5": "ou_2_5",
}


@dataclass(frozen=True)
class StrategyExecutionSpec:
    id: int
    name: str
    model_type: str
    parameters: dict


@dataclass(frozen=True)
class AnalysisUserIdentity:
    id: int
    is_admin: bool = False


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
    league_names_by_id = {league.id.lower(): league.name for country in CATALOG for league in country.leagues}

    if league_filters:
        resolved = [league_names_by_id.get(league_id.lower(), league_id) for league_id in league_filters]
    elif country_filters:
        resolved = [
            league.name for country in CATALOG if country.country in country_filters for league in country.leagues
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


async def _filter_explicit_match_ids_by_date(
    db: AsyncSession,
    match_ids: list[int],
    filters,
) -> list[int]:
    if not match_ids or filters is None or not (filters.date_from or filters.date_to):
        return match_ids

    stmt = select(Match.id).where(Match.id.in_(match_ids))
    if filters.date_from:
        date_from = _parse_filter_datetime(filters.date_from)
        if date_from is None:
            raise ValueError("date_from must be an ISO-8601 date or datetime")
        stmt = stmt.where(Match.match_date.is_not(None), Match.match_date >= date_from)
    if filters.date_to:
        date_to = _parse_filter_datetime(filters.date_to, end_of_day=True)
        if date_to is None:
            raise ValueError("date_to must be an ISO-8601 date or datetime")
        stmt = stmt.where(Match.match_date.is_not(None), Match.match_date <= date_to)

    result = await db.execute(stmt)
    eligible_ids = {row[0] for row in result.all()}
    return [match_id for match_id in match_ids if match_id in eligible_ids]


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


def _strategy_runnable_metadata(strategy: Strategy) -> tuple[bool, str | None]:
    if not strategy.is_active:
        return False, "Strategy is inactive"
    try:
        resolve_prediction_model_key(strategy.model_type)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def _strategy_response(strategy: Strategy) -> StrategyResponse:
    runnable, incompatibility_reason = _strategy_runnable_metadata(strategy)
    return StrategyResponse.model_validate(strategy).model_copy(
        update={
            "runnable": runnable,
            "incompatibility_reason": incompatibility_reason,
        }
    )


def _strategy_issue(strategy: Strategy) -> dict[str, object] | None:
    runnable, reason = _strategy_runnable_metadata(strategy)
    if runnable:
        return None
    return {
        "strategy_id": strategy.id,
        "name": strategy.name,
        "model_type": strategy.model_type,
        "reason": reason,
    }


def _strategy_execution_spec(strategy: Strategy) -> StrategyExecutionSpec:
    return StrategyExecutionSpec(
        id=strategy.id,
        name=strategy.name,
        model_type=strategy.model_type,
        parameters=deepcopy(strategy.parameters or {}),
    )


def _strategy_run_input_hash(
    *,
    strategy: Strategy,
    execution_config: dict,
    markets: list[str],
    match_ids: list[int],
    filters,
    source_dataset_id: int | None = None,
) -> str:
    filters_payload = {}
    if filters is not None:
        filters_payload = {
            "countries": sorted(filters.countries),
            "leagues": sorted(filters.leagues),
            "date_from": filters.date_from,
            "date_to": filters.date_to,
        }

    payload = {
        "strategy_id": strategy.id,
        "strategy_model_type": strategy.model_type,
        "execution_config": execution_config,
        "markets": sorted(markets),
        "match_ids": sorted(match_ids),
        "filters": filters_payload,
        "source_dataset_id": source_dataset_id,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]


def _strategy_run_name(strategy: Strategy, input_hash: str) -> str:
    return f"Strategy: {getattr(strategy, 'name', strategy.id)} | input:{input_hash}"


async def _find_active_strategy_run(
    db: AsyncSession,
    *,
    user_id: int,
    input_hash: str,
) -> PredictionRun | None:
    """Return the run currently owning an idempotent analysis input.

    Historical runs predate the database guard, so lookup intentionally uses
    immutable ``input_hash`` lineage rather than ``dedupe_enabled``.
    """

    result = await db.execute(
        select(PredictionRun)
        .where(
            PredictionRun.user_id == user_id,
            PredictionRun.input_hash == input_hash,
            PredictionRun.status.in_(ACTIVE_DEDUPE_RUN_STATUSES),
        )
        .order_by(PredictionRun.created_at.desc(), PredictionRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _claim_deduplicated_strategy_run(
    db: AsyncSession,
    *,
    run: PredictionRun,
) -> PredictionRun | None:
    """Persist a guarded run or return the concurrent transaction's winner.

    The partial unique index is the actual concurrency boundary. A savepoint
    contains the expected uniqueness error so the request can immediately read
    and reuse the committed winner without invalidating the outer transaction.
    """

    try:
        async with db.begin_nested():
            db.add(run)
            await db.flush()
    except IntegrityError:
        existing_run = await _find_active_strategy_run(
            db,
            user_id=run.user_id,
            input_hash=run.input_hash,
        )
        if existing_run is None:
            raise
        return existing_run
    return None


def _deduped_strategy_response(
    existing_run: PredictionRun,
    *,
    strategy_id: int,
    dataset_id: int | None,
    input_hash: str,
) -> StrategyRunResponse:
    return StrategyRunResponse(
        run_id=existing_run.id,
        status="deduped",
        matches_count=existing_run.matches_count,
        deduped=True,
        strategy_id=strategy_id,
        dataset_id=dataset_id,
        input_hash=input_hash,
    )


async def _persist_failed_strategy_batch_attempt(
    db: AsyncSession,
    *,
    strategy: StrategyExecutionSpec,
    user_id: int,
    dataset_id: int,
    match_ids: list[int],
    markets: list[str],
    filters,
    dedupe_enabled: bool,
    error: Exception,
) -> StrategyRunResponse:
    execution_config = _build_strategy_execution_config(strategy)
    normalized_markets = _normalize_strategy_markets(markets)
    input_hash = _strategy_run_input_hash(
        strategy=strategy,
        execution_config=execution_config,
        markets=normalized_markets,
        match_ids=match_ids,
        filters=filters,
        source_dataset_id=dataset_id,
    )
    error_message = f"Unexpected strategy execution error: {error}"
    now = datetime.now(timezone.utc)
    context = {
        "source_dataset_id": dataset_id,
        "strategy_id": strategy.id,
        "strategy_model_type": strategy.model_type,
        "match_ids": sorted(match_ids),
        "markets": sorted(normalized_markets),
        "filters": filters.model_dump(mode="json") if filters is not None else None,
        "input_hash": input_hash,
        "execution": {
            "status": "failed",
            "failure_kind": "unexpected_exception",
            "error": error_message,
        },
    }
    run = PredictionRun(
        user_id=user_id,
        name=_strategy_run_name(strategy, input_hash),
        model_type=strategy.model_type,
        ensemble=False,
        status="failed",
        matches_count=0,
        started_at=now,
        completed_at=now,
        error=error_message,
        source_dataset_id=dataset_id,
        strategy_id=strategy.id,
        input_hash=input_hash,
        dedupe_enabled=dedupe_enabled,
        input_context=context,
    )
    db.add(run)
    await db.flush()
    commit = getattr(db, "commit", None)
    if commit is not None:
        await commit()
    await _broadcast_live_prediction_update_if_relevant(run)
    return StrategyRunResponse(
        run_id=run.id,
        status="failed",
        matches_count=0,
        error=error_message,
        strategy_id=strategy.id,
        dataset_id=dataset_id,
        input_hash=input_hash,
        context=context["execution"],
    )


def _build_strategy_duplicate(strategy: Strategy, *, name: str | None = None) -> Strategy:
    copy_name = (name or "").strip() or f"Copy of {strategy.name}"
    return Strategy(
        name=copy_name,
        description=strategy.description,
        model_type=strategy.model_type,
        parameters=deepcopy(strategy.parameters or {}),
        weights=deepcopy(strategy.weights),
        is_active=strategy.is_active,
    )


async def _broadcast_live_prediction_update_if_relevant(run: PredictionRun) -> None:
    if not isinstance(run.id, int) or not isinstance(run.status, str):
        return
    if run.status not in LIVE_PREDICTION_BROADCAST_STATUSES:
        return
    await broadcast_prediction_update(run_id=run.id, status=run.status)


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(Strategy).order_by(Strategy.created_at.desc())
    result = await db.execute(stmt)
    return [_strategy_response(strategy) for strategy in result.scalars().all()]


@router.post("/run-batch", response_model=StrategyBatchRunResponse)
async def run_strategy_batch(
    body: StrategyBatchRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        strategies = await load_analysis_strategies(db, body.strategy_ids)
        resolution = await resolve_dataset_match_ids(db, body.dataset_id, user=user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    issues = [issue for strategy in strategies if (issue := _strategy_issue(strategy)) is not None]
    if body.strategy_ids and issues:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "One or more explicitly selected strategies are not runnable",
                "strategies": issues,
            },
        )
    if not body.strategy_ids:
        strategies = [strategy for strategy in strategies if _strategy_issue(strategy) is None]
    if not strategies:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "No active runnable strategies are available for analysis",
                "strategies": issues,
            },
        )
    if resolution.unresolved_records and not body.allow_partial_resolution:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Dataset match resolution is incomplete; analysis was not started",
                "dataset_id": resolution.dataset.id,
                "scrape_job_id": resolution.scrape_job_id,
                "scrape_job_status": resolution.scrape_job_status,
                "dataset_records_count": resolution.total_records,
                "resolved_records_count": resolution.resolved_records,
                "unresolved_records_count": resolution.unresolved_records,
                "resolution_counts": resolution.resolution_counts,
                "unresolved_samples": resolution.unresolved_samples,
            },
        )

    dataset = resolution.dataset
    dataset_id = dataset.id
    try:
        match_ids = await _filter_explicit_match_ids_by_date(db, resolution.match_ids, body.filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not match_ids:
        return StrategyBatchRunResponse(
            status="no_matches",
            dataset_id=dataset_id,
            scrape_job_id=resolution.scrape_job_id,
            scrape_job_status=resolution.scrape_job_status,
            dataset_records_count=resolution.total_records,
            resolved_records_count=resolution.resolved_records,
            unresolved_records_count=resolution.unresolved_records,
            resolution_counts=resolution.resolution_counts,
            unresolved_samples=resolution.unresolved_samples,
            strategy_count=len(strategies),
        )

    request = StrategyRunRequest(
        match_ids=match_ids,
        markets=body.markets,
        filters=body.filters,
        autopredict=body.autopredict,
        avoid_reprediction=body.avoid_reprediction,
        dataset_id=dataset_id,
        allow_partial_resolution=body.allow_partial_resolution,
    )
    strategy_specs = [_strategy_execution_spec(strategy) for strategy in strategies]
    user_identity = AnalysisUserIdentity(id=user.id, is_admin=bool(getattr(user, "is_admin", False)))
    runs: list[StrategyRunResponse] = []
    for strategy in strategy_specs:
        try:
            run_response = await run_strategy(strategy_id=strategy.id, body=request, db=db, user=user_identity)
            commit = getattr(db, "commit", None)
            if commit is not None:
                await commit()
        except Exception as exc:
            rollback = getattr(db, "rollback", None)
            if rollback is not None:
                await rollback()
            try:
                run_response = await _persist_failed_strategy_batch_attempt(
                    db,
                    strategy=strategy,
                    user_id=user_identity.id,
                    dataset_id=dataset_id,
                    match_ids=match_ids,
                    markets=body.markets,
                    filters=body.filters,
                    dedupe_enabled=body.avoid_reprediction,
                    error=exc,
                )
            except Exception as persistence_exc:
                if rollback is not None:
                    await rollback()
                run_response = StrategyRunResponse(
                    run_id=0,
                    status="failed",
                    error=(
                        f"Unexpected strategy execution error: {exc}; "
                        f"failed to persist attempt: {persistence_exc}"
                    ),
                    strategy_id=strategy.id,
                    dataset_id=dataset_id,
                )
        runs.append(run_response)

    return StrategyBatchRunResponse(
        status=summarize_analysis_batch_status([run.status for run in runs]),
        dataset_id=dataset_id,
        scrape_job_id=resolution.scrape_job_id,
        scrape_job_status=resolution.scrape_job_status,
        match_ids=match_ids,
        dataset_records_count=resolution.total_records,
        resolved_records_count=resolution.resolved_records,
        unresolved_records_count=resolution.unresolved_records,
        resolution_counts=resolution.resolution_counts,
        unresolved_samples=resolution.unresolved_samples,
        strategy_count=len(strategies),
        runs=runs,
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


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(
    body: StrategyCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
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
    return _strategy_response(strategy)


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
    return _strategy_response(strategy)


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    body: StrategyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
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
    return _strategy_response(strategy)


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    stmt = select(Strategy).where(Strategy.id == strategy_id)
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await db.delete(strategy)
    await db.flush()


@router.post("/{strategy_id}/duplicate", response_model=StrategyResponse, status_code=201)
async def duplicate_strategy(
    strategy_id: int,
    body: StrategyDuplicateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    stmt = select(Strategy).where(Strategy.id == strategy_id)
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    duplicate = _build_strategy_duplicate(strategy, name=body.name)
    db.add(duplicate)
    await db.flush()
    await db.refresh(duplicate)
    return _strategy_response(duplicate)


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

    issue = _strategy_issue(strategy)
    if issue is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Selected strategy is not runnable",
                "strategy": issue,
            },
        )

    # Normalise markets
    markets = _normalize_strategy_markets(body.markets)

    try:
        execution_config = _build_strategy_execution_config(strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Resolve match IDs and validate any claimed source-dataset lineage.
    match_ids = body.match_ids
    if body.dataset_id is not None:
        try:
            dataset_resolution = await resolve_dataset_match_ids(db, body.dataset_id, user=user)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if dataset_resolution.unresolved_records and not body.allow_partial_resolution:
            raise HTTPException(
                status_code=409,
                detail="Dataset match resolution is incomplete; strategy analysis was not started",
            )
        dataset_match_ids = set(dataset_resolution.match_ids)
        if match_ids:
            foreign_match_ids = [match_id for match_id in match_ids if match_id not in dataset_match_ids]
            if foreign_match_ids:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Requested matches do not belong to the claimed source dataset",
                        "dataset_id": body.dataset_id,
                        "foreign_match_ids": foreign_match_ids,
                    },
                )
        else:
            match_ids = dataset_resolution.match_ids
    if match_ids:
        try:
            match_ids = await _filter_explicit_match_ids_by_date(db, match_ids, body.filters)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        return StrategyRunResponse(
            run_id=0,
            status="no_matches",
            strategy_id=strategy.id,
            dataset_id=body.dataset_id,
        )

    input_hash = _strategy_run_input_hash(
        strategy=strategy,
        execution_config=execution_config,
        markets=markets,
        match_ids=match_ids,
        filters=body.filters,
        source_dataset_id=body.dataset_id,
    )
    run_name = _strategy_run_name(strategy, input_hash)

    if body.avoid_reprediction:
        existing_run = await _find_active_strategy_run(
            db,
            user_id=user.id,
            input_hash=input_hash,
        )
        if existing_run:
            return _deduped_strategy_response(
                existing_run,
                strategy_id=strategy.id,
                dataset_id=body.dataset_id,
                input_hash=input_hash,
            )

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
        name=run_name,
        model_type=strategy.model_type,
        ensemble=strategy.model_type == "ensemble",
        status="running",
        matches_count=len(match_ids),
        started_at=datetime.now(timezone.utc),
        source_dataset_id=body.dataset_id,
        strategy_id=strategy.id,
        input_hash=input_hash,
        dedupe_enabled=body.avoid_reprediction,
        input_context={
            "source_dataset_id": body.dataset_id,
            "strategy_id": strategy.id,
            "strategy_model_type": strategy.model_type,
            "match_ids": sorted(match_ids),
            "markets": sorted(markets),
            "filters": body.filters.model_dump(mode="json") if body.filters is not None else None,
            "input_hash": input_hash,
        },
    )
    if body.avoid_reprediction:
        existing_run = await _claim_deduplicated_strategy_run(db, run=run)
        if existing_run is not None:
            return _deduped_strategy_response(
                existing_run,
                strategy_id=strategy.id,
                dataset_id=body.dataset_id,
                input_hash=input_hash,
            )
    else:
        db.add(run)
        await db.flush()
    await _broadcast_live_prediction_update_if_relevant(run)

    total_written = 0
    total_fallbacks = 0
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
            fallbacks = result.get("fallbacks", 0)
            target_errors = result.get("target_errors", [])

            if written == 0 and target_matches > 0:
                message = f"{league}: prediction bridge produced no results for {target_matches} target matches"
                league_errors.append(message)
                per_league.append(
                    {"league": league, "status": "failed", "error": message, "matches": len(league_match_ids)}
                )
                continue

            if failed > 0 or fallbacks > 0:
                detail_parts = []
                if failed > 0:
                    detail_parts.append(f"{failed} target matches failed during bridge execution")
                if fallbacks > 0:
                    detail_parts.append(f"{fallbacks} target matches used model fallback predictions")
                message = f"{league}: {'; '.join(detail_parts)}"
                league_errors.append(message)
                per_league.append(
                    {
                        "league": league,
                        "status": "partial",
                        "error": message,
                        "matches": len(league_match_ids),
                        "written": written,
                        "failed": failed,
                        "fallbacks": fallbacks,
                        "target_errors": target_errors,
                    }
                )
            else:
                per_league.append(
                    {"league": league, "status": "ok", "matches": len(league_match_ids), "written": written}
                )

            total_written += written
            total_fallbacks += fallbacks
        except ValueError as e:
            league_errors.append(f"{league}: {e}")
            per_league.append({"league": league, "status": "failed", "error": str(e), "matches": len(league_match_ids)})
        except BridgeError as e:
            league_errors.append(f"{league}: {e}")
            per_league.append({"league": league, "status": "failed", "error": str(e), "matches": len(league_match_ids)})

    await db.flush()

    if total_written == 0:
        run.status = "failed"
    elif league_errors:
        run.status = "partial"
    else:
        run.status = "completed"

    run.completed_at = datetime.now(timezone.utc)
    predicted_matches_result = await db.execute(
        select(func.count(func.distinct(ModelPrediction.match_id))).where(ModelPrediction.run_id == run.id)
    )
    predicted_matches_count = int(predicted_matches_result.scalar_one_or_none() or 0)
    run.matches_count = predicted_matches_count
    run.error = " | ".join(league_errors) if league_errors else None
    execution_context = {
        "status": run.status,
        "written": total_written,
        "predicted_matches": predicted_matches_count,
        "fallbacks": total_fallbacks,
        "per_league": per_league,
    }
    run.input_context = {**(run.input_context or {}), "execution": execution_context}
    await db.flush()
    await _broadcast_live_prediction_update_if_relevant(run)

    return StrategyRunResponse(
        run_id=run.id,
        status=run.status,
        matches_count=predicted_matches_count,
        error=run.error,
        strategy_id=strategy.id,
        dataset_id=body.dataset_id,
        input_hash=input_hash,
        context=execution_context,
    )
