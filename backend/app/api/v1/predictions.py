import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.api.v1.live import broadcast_prediction_update
from app.database import get_db
from app.models.match import Match, OddsEntry
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.user import User
from app.schemas.prediction import (
    PredictionCatalogResponse,
    PredictionRunDetailResponse,
    PredictionRunPageResponse,
    PredictionRunResponse,
    PredictionVerificationItem,
    PredictionVerificationResponse,
    RunEnsembleRequest,
    RunSingleRequest,
    ValueBetItem,
    ValueBetResponse,
)
from app.services.ensemble import run_ensemble_prediction
from app.services.prediction_engine import PREDICT_MODELS, run_single_prediction
from app.services.result_settlement import evaluate_model_prediction

router = APIRouter()
LIVE_PREDICTION_BROADCAST_STATUSES = {"running", "completed", "partial", "failed"}
VALUE_BET_BETSLIP_MAX_DATA_AGE_SECONDS = 15 * 60
VALUE_BET_MODEL_ODDS_SKEW_SECONDS = 15 * 60
VALUE_BET_ACTIVE_STATUSES = {"live", "running", "active", "in_play", "halftime", "ht"}
VALUE_BET_FINISHED_STATUSES = {"finished", "ft", "fulltime"}


def _prediction_value_for_selection(prediction: ModelPrediction, selection: str | None, suffix: str) -> float | None:
    if not selection:
        return None

    normalized_market = (prediction.market or "").lower()
    normalized_selection = selection.lower()
    if normalized_selection == "home":
        field = f"home_{suffix}"
    elif normalized_selection == "draw":
        field = f"draw_{suffix}"
    elif normalized_selection == "away":
        field = f"away_{suffix}"
    elif normalized_selection in {"yes", "over"}:
        field = f"home_{suffix}"
    elif normalized_selection in {"no", "under"}:
        field = f"away_{suffix}"
    elif normalized_market in {"btts", "both_teams_to_score"}:
        field = f"home_{suffix}" if normalized_selection == "yes" else f"away_{suffix}"
    else:
        return None

    value = getattr(prediction, field, None)
    return float(value) if value is not None else None


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
    prediction: ModelPrediction, outcome: str, odds_entries: list[OddsEntry]
) -> tuple[float, str, datetime | None] | tuple[None, str, None]:
    if not odds_entries:
        return None, "", None

    candidates = [e for e in odds_entries if _is_eligible_market(prediction.market, e.market)]
    if not candidates:
        return None, "", None

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
        return None, outcome_field, None
    return getattr(best, outcome_field), best.bookmaker, best.timestamp or getattr(best, "created_at", None)


def _prediction_quality_details(prediction: ModelPrediction) -> tuple[bool, str | None, list[str]]:
    quality = getattr(prediction, "quality_report", None) or {}
    reliability = quality.get("reliability", {}) if isinstance(quality, dict) else {}
    label = reliability.get("label") if isinstance(reliability, dict) else None
    reasons = reliability.get("block_reasons", []) if isinstance(reliability, dict) else []
    if not isinstance(reasons, list):
        reasons = []
    return bool(reliability.get("is_ticket_eligible", False)), label, [str(reason) for reason in reasons]


def _normalize_match_status(value: str | None) -> str:
    return (value or "").strip().lower()


def _age_seconds(timestamp: datetime | None, now: datetime) -> int | None:
    if timestamp is None:
        return None
    return max(0, int((now - timestamp).total_seconds()))


async def _broadcast_live_prediction_update_if_relevant(result: dict) -> None:
    run_id = result.get("run_id")
    status = result.get("status")
    if not isinstance(run_id, int) or not isinstance(status, str):
        return
    if status not in LIVE_PREDICTION_BROADCAST_STATUSES:
        return
    await broadcast_prediction_update(run_id=run_id, status=status)


def _build_value_candidates(
    run: PredictionRun,
    min_edge: float,
    max_results: int,
    *,
    include_unreliable: bool = False,
    now: datetime,
) -> list[ValueBetItem]:
    items: list[ValueBetItem] = []

    for prediction in run.model_predictions:
        is_ticket_eligible, reliability, quality_reasons = _prediction_quality_details(prediction)
        if not include_unreliable and not is_ticket_eligible:
            continue

        match = prediction.match
        if not match:
            continue

        odds_entries = match.odds
        match_status = _normalize_match_status(getattr(match, "status", None))
        kickoff = getattr(match, "match_date", None)
        match_started = bool(kickoff and kickoff <= now)

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
            odds_value, bookmaker, odds_timestamp = _resolve_market_odds(prediction, selection, odds_entries)
            if odds_value is None:
                continue

            implied = 1 / odds_value
            edge_pct = (model_prob - implied) * 100
            if edge_pct < min_edge:
                continue

            prediction_age_seconds = _age_seconds(getattr(prediction, "created_at", None), now)
            odds_freshness_seconds = _age_seconds(odds_timestamp, now)
            known_ages = [age for age in (prediction_age_seconds, odds_freshness_seconds) if age is not None]
            data_age_seconds = max(known_ages) if known_ages else None
            source_ok = bool(bookmaker) and odds_timestamp is not None
            model_drift_flag = prediction_age_seconds is None or (
                odds_freshness_seconds is not None
                and prediction_age_seconds > odds_freshness_seconds + VALUE_BET_MODEL_ODDS_SKEW_SECONDS
            )

            block_reasons: list[str] = []
            if not is_ticket_eligible:
                block_reasons.append("prediction_untrusted")
            if not source_ok:
                block_reasons.append("odds_untrusted")
            if odds_timestamp is None:
                block_reasons.append("odds_missing_timestamp")
            if prediction_age_seconds is None:
                block_reasons.append("prediction_missing_timestamp")
            if data_age_seconds is None:
                block_reasons.append("data_age_unknown")
            elif data_age_seconds >= VALUE_BET_BETSLIP_MAX_DATA_AGE_SECONDS:
                block_reasons.append("data_stale")
            if model_drift_flag:
                block_reasons.append("model_drift")
            if match_status in VALUE_BET_FINISHED_STATUSES:
                block_reasons.append("match_finished")
            elif match_status in VALUE_BET_ACTIVE_STATUSES or match_started:
                block_reasons.append("match_started")

            is_betslip_eligible = (
                is_ticket_eligible
                and source_ok
                and data_age_seconds is not None
                and data_age_seconds < VALUE_BET_BETSLIP_MAX_DATA_AGE_SECONDS
                and not model_drift_flag
                and "match_started" not in block_reasons
                and "match_finished" not in block_reasons
            )

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
                    reliability=reliability,
                    quality_reasons=quality_reasons,
                    source=f"odds:{bookmaker}" if bookmaker else "odds",
                    prediction_age_seconds=prediction_age_seconds,
                    selection_age_seconds=prediction_age_seconds,
                    odds_freshness_seconds=odds_freshness_seconds,
                    data_age_seconds=data_age_seconds,
                    source_ok=source_ok,
                    model_drift_flag=model_drift_flag,
                    is_betslip_eligible=is_betslip_eligible,
                    block_reasons=block_reasons,
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
    result = await run_single_prediction(
        db=db,
        league=body.league,
        user_id=user.id,
        model_key=body.model_key,
        markets=body.markets,
        sport=body.sport,
        training_limit=body.training_limit,
        target_limit=body.target_limit,
        target_mode=body.target_mode,
        target_match_ids=body.target_match_ids,
        date_from=body.date_from,
        date_to=body.date_to,
        max_goals=body.max_goals,
    )
    await _broadcast_live_prediction_update_if_relevant(result)
    return result


@router.post("/ensemble", response_model=dict)
async def create_ensemble_run(
    body: RunEnsembleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await run_ensemble_prediction(
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
    await _broadcast_live_prediction_update_if_relevant(result)
    return result


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


@router.get("/runs/page", response_model=PredictionRunPageResponse)
async def list_prediction_runs_page(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count_result = await db.execute(
        select(func.count(PredictionRun.id)).where(PredictionRun.user_id == user.id)
    )
    total = count_result.scalar() or 0
    stmt = (
        select(PredictionRun)
        .where(PredictionRun.user_id == user.id)
        .order_by(PredictionRun.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    return PredictionRunPageResponse(
        items=list(result.scalars().all()),
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/verification", response_model=PredictionVerificationResponse)
async def verify_predictions(
    run_id: int | None = None,
    max_results: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(ModelPrediction)
        .join(PredictionRun, ModelPrediction.run_id == PredictionRun.id)
        .options(selectinload(ModelPrediction.match))
        .where(PredictionRun.user_id == user.id)
        .order_by(ModelPrediction.created_at.desc())
        .limit(max_results)
    )
    if run_id is not None:
        stmt = stmt.where(ModelPrediction.run_id == run_id)

    result = await db.execute(stmt)
    predictions = result.scalars().all()

    items: list[PredictionVerificationItem] = []
    correct = incorrect = pending = void = unsupported = 0
    for prediction in predictions:
        evaluation = evaluate_model_prediction(prediction)
        if evaluation.status == "won":
            correct += 1
        elif evaluation.status == "lost":
            incorrect += 1
        elif evaluation.status == "pending":
            pending += 1
        elif evaluation.status == "void":
            void += 1
        else:
            unsupported += 1

        match = prediction.match
        items.append(
            PredictionVerificationItem(
                prediction_id=prediction.id,
                run_id=prediction.run_id,
                match_id=prediction.match_id,
                model_type=prediction.model_type,
                league=match.competition if match else None,
                kickoff=match.match_date if match else None,
                market=prediction.market,
                predicted_selection=evaluation.predicted_selection,
                actual_selection=evaluation.actual_selection,
                model_probability=_prediction_value_for_selection(prediction, evaluation.predicted_selection, "prob"),
                market_odds=_prediction_value_for_selection(prediction, evaluation.predicted_selection, "odds"),
                status=evaluation.status,
                home_team=match.home_team if match else "",
                away_team=match.away_team if match else "",
                home_score=match.home_score if match else None,
                away_score=match.away_score if match else None,
            )
        )

    resolved = correct + incorrect
    accuracy = round(correct / resolved * 100, 2) if resolved else None
    return PredictionVerificationResponse(
        checked_predictions=len(predictions),
        resolved_predictions=resolved,
        correct_predictions=correct,
        incorrect_predictions=incorrect,
        pending_predictions=pending,
        void_predictions=void,
        unsupported_predictions=unsupported,
        accuracy=accuracy,
        items=items,
    )


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
    include_unreliable: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    run_stmt = (
        select(PredictionRun)
        .where(PredictionRun.user_id == user.id, PredictionRun.status == "completed")
        .options(
            selectinload(PredictionRun.model_predictions).selectinload(ModelPrediction.match).selectinload(Match.odds),
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
            generated_at=now.isoformat(),
        )

    items = _build_value_candidates(
        run,
        min_edge=min_edge,
        max_results=max_results,
        include_unreliable=include_unreliable,
        now=now,
    )
    return ValueBetResponse(
        items=items,
        source="prediction",
        is_demo=False,
        generated_at=now.isoformat(),
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
