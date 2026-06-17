from datetime import datetime, timezone
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.match import OddsEntry
from app.models.match import Match
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.user import User
from app.schemas.prediction import (
    PredictionCatalogResponse,
    PredictionRunDetailResponse,
    PredictionRunResponse,
    ValueBetItem,
    ValueBetResponse,
    RunEnsembleRequest,
    RunSingleRequest,
)
from app.services.ensemble import run_ensemble_prediction
from app.services.prediction_engine import PREDICT_MODELS, run_single_prediction

router = APIRouter()


def _normalize_market_market(value: str) -> str:
    return re.sub(r"[^a-z0-9_:.]+", "", value.strip().lower())


def _market_base_and_line(value: str) -> tuple[str, str]:
    value = _normalize_market_market(value)
    if ":" in value:
        base, line = value.split(":", 1)
        return base, line
    trailing_line = re.search(r"[_:](\d+_\d+|\d+\.\d+|\d+)$", value)
    if trailing_line:
        line = trailing_line.group(1)
        base = value[: trailing_line.start()]
        return base, line
    return value, ""


def _extract_line_token(value: str) -> str:
    if not value:
        return ""

    line_match = re.search(r"\d+_\d+|\d+\.\d+|\d+", value)
    if not line_match:
        return ""
    return line_match.group(0).replace("_", ".")


def _is_two_point_five_market_line(value: str) -> bool:
    return _extract_line_token(value) in {"2.5", "2.50"}


def _market_aliases(prediction_market: str) -> set[str]:
    aliases = {_normalize_market_market(prediction_market)}
    normalized = _normalize_market_market(prediction_market)

    if normalized in {"ou_2_5", "ou2_5", "over_under", "overunder", "totals"}:
        aliases.update({"ou_2_5", "ou2_5", "over_under", "overunder", "totals"})
    if normalized.startswith("over_under_") or normalized.startswith("over_under:"):
        aliases.update({"ou_2_5", "ou2_5", "over_under", "overunder", "totals"})
    if normalized.startswith("ou_2_5") or normalized.startswith("ou25") or normalized.startswith("ou2_5"):
        aliases.update({"ou_2_5", "ou2_5", "over_under", "overunder", "totals"})

    if normalized in {"btts", "both_teams_to_score", "bt_ts", "bt-ts", "bothteams"}:
        aliases.update({"btts", "both_teams_to_score", "bothteams"})

    if normalized in {"1x2", "match_winner", "home_away", "matchwinner"}:
        aliases.update({"1x2", "match_winner", "home_away", "matchwinner"})

    return aliases


def _is_eligible_market(prediction_market: str, candidate_market: str) -> bool:
    prediction_base, _ = _market_base_and_line(prediction_market)
    candidate_base, candidate_line = _market_base_and_line(candidate_market)

    aliases = _market_aliases(prediction_base)
    if candidate_base not in aliases:
        return False

    if prediction_base in {"ou_2_5", "ou25", "over_under", "totals", "overunder"}:
        # Accept explicit 2.5/2_5 over/under markets and legacy variants.
        return _is_two_point_five_market_line(candidate_line) or _is_two_point_five_market_line(candidate_market)

    return True


def _resolve_market_odds(
    prediction: ModelPrediction,
    outcome: str,
    odds_entries: list[OddsEntry]
) -> tuple[float, str] | tuple[None, str]:
    if not odds_entries:
        return None, ""

    candidates = [
        e
        for e in odds_entries
        if _is_eligible_market(prediction.market, e.market)
    ]
    if not candidates:
        return None, ""

    outcome_field = {
        "home": "home_odds",
        "draw": "draw_odds",
        "away": "away_odds",
        "yes": "home_odds",
        "no": "away_odds",
        "over": "home_odds",
        "under": "away_odds",
    }.get(outcome, "home_odds")

    best = None
    for odds in candidates:
        value = getattr(odds, outcome_field, None)
        if value is None or value <= 1:
            continue
        if best is None or value > getattr(best, outcome_field):
            best = odds

    if best is None:
        return None, outcome_field
    return getattr(best, outcome_field), best.bookmaker


def _build_value_candidates(run: PredictionRun, min_edge: float, max_results: int) -> list[ValueBetItem]:
    items: list[ValueBetItem] = []

    for prediction in run.model_predictions:
        match = prediction.match
        if not match:
            continue

        odds_entries = match.odds

        outcomes = []
        market = _normalize_market_market(prediction.market)
        if market == "1x2":
            outcomes = [
                ("home", prediction.home_prob),
                ("draw", prediction.draw_prob),
                ("away", prediction.away_prob),
            ]
        elif market in {"btts", "both_teams_to_score", "bothteams"}:
            outcomes = [("yes", prediction.home_prob), ("no", prediction.away_prob)]
        elif market in {"ou_2_5", "ou25", "over_under", "over_under:2.5", "over_under_2_5", "overunder", "totals"}:
            outcomes = [("over", prediction.home_prob), ("under", prediction.away_prob)]

        for selection, model_prob in outcomes:
            if model_prob is None or model_prob <= 0:
                continue
            odds_value, bookmaker = _resolve_market_odds(prediction, selection, odds_entries)
            if odds_value is None:
                continue

            implied = 1 / odds_value
            edge_pct = (model_prob - implied) * 100
            if edge_pct < min_edge:
                continue

            items.append(
                ValueBetItem(
                    id=prediction.id,
                    match_id=match.id,
                    league=match.competition,
                    home_team=match.home_team,
                    away_team=match.away_team,
                    kickoff=match.match_date.isoformat() if match.match_date else None,
                    market=prediction.market,
                    selection=selection,
                    model_prob=model_prob,
                    odds=odds_value,
                    edge=edge_pct,
                    model_type=run.model_type,
                    confidence=max(0.0, min(1.0, model_prob)) * 100,
                    source=f"odds:{bookmaker}" if bookmaker else "odds",
                )
            )

    items.sort(key=lambda item: item.edge, reverse=True)
    if max_results > 0:
        return items[:max_results]
    return items


@router.get("/catalog", response_model=PredictionCatalogResponse)
async def get_catalog():
    return PredictionCatalogResponse(
        models=[dict(m) for m in PREDICT_MODELS],
        markets=["1x2", "btts", "ou_2_5"],
    )


@router.post("/run", response_model=dict)
async def create_prediction_run(
    body: RunSingleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await run_single_prediction(
        db=db,
        league=body.league,
        user_id=user.id,
        model_key=body.model_key,
        markets=body.markets,
        sport=body.sport,
        training_limit=body.training_limit,
        target_limit=body.target_limit,
        target_mode=body.target_mode,
        max_goals=body.max_goals,
    )


@router.post("/ensemble", response_model=dict)
async def create_ensemble_run(
    body: RunEnsembleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await run_ensemble_prediction(
        db=db,
        league=body.league,
        user_id=user.id,
        model_keys=body.model_keys,
        markets=body.markets,
        weighting=body.weighting,
        sport=body.sport,
        training_limit=body.training_limit,
        target_limit=body.target_limit,
        target_mode=body.target_mode,
        max_goals=body.max_goals,
    )


@router.get("/runs", response_model=list[PredictionRunResponse])
async def list_prediction_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(PredictionRun)
        .where(PredictionRun.user_id == user.id)
        .order_by(PredictionRun.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=PredictionRunDetailResponse)
async def get_prediction_run(
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
        raise HTTPException(status_code=404, detail="Prediction run not found")
    return run


@router.get("/value-bets", response_model=ValueBetResponse)
async def list_value_bets(
    min_edge: float = Query(0, ge=-100, le=100),
    max_results: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run_stmt = (
        select(PredictionRun)
        .where(PredictionRun.user_id == user.id, PredictionRun.status == "completed")
        .options(
            selectinload(PredictionRun.model_predictions)
            .selectinload(ModelPrediction.match)
            .selectinload(Match.odds),
        )
        .order_by(PredictionRun.created_at.desc())
        .limit(1)
    )
    result = await db.execute(run_stmt)
    run = result.scalar_one_or_none()

    if not run:
        return ValueBetResponse(
            items=[],
            source="prediction",
            is_demo=False,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    items = _build_value_candidates(run, min_edge=min_edge, max_results=max_results)
    return ValueBetResponse(
        items=items,
        source="prediction",
        is_demo=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.delete("/runs/{run_id}", status_code=204)
async def delete_prediction_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(PredictionRun).where(PredictionRun.id == run_id, PredictionRun.user_id == user.id)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Prediction run not found")
    await db.delete(run)
    await db.flush()
