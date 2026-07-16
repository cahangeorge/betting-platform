import math
import re
from collections import defaultdict
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
    PredictionCalibrationBucket,
    PredictionCalibrationGroup,
    PredictionCalibrationResponse,
    PredictionCatalogResponse,
    PredictionRunDetailResponse,
    PredictionRunPageResponse,
    PredictionRunResponse,
    PredictionScoreGridCell,
    PredictionScoreGridItem,
    PredictionScoreGridResponse,
    PredictionVerificationItem,
    PredictionVerificationResponse,
    RunEnsembleRequest,
    RunSingleRequest,
    ValueBetItem,
    ValueBetResponse,
)
from app.services.ensemble import run_ensemble_prediction
from app.services.odds_quotes import select_quote_set
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

    priced_candidates: list[tuple[OddsEntry, float, datetime | None]] = []
    for odds in candidates:
        value = getattr(odds, outcome_field, None)
        if value is None or value <= 1:
            continue
        observed_at = odds.timestamp or getattr(odds, "created_at", None)
        priced_candidates.append((odds, float(value), observed_at))

    if not priced_candidates:
        return None, outcome_field, None

    # Never let a stale but historically larger quote represent the current market.
    # OddsHarvester gives every bookmaker row in one scrape the same timestamp, so
    # first select the newest snapshot and only then shop for its best bookmaker.
    timestamped_candidates = [candidate for candidate in priced_candidates if candidate[2] is not None]
    current_snapshot = priced_candidates
    if timestamped_candidates:
        latest_observed_at = max(candidate[2] for candidate in timestamped_candidates)
        current_snapshot = [candidate for candidate in timestamped_candidates if candidate[2] == latest_observed_at]

    best, value, observed_at = max(
        current_snapshot,
        key=lambda candidate: (
            candidate[1],
            str(candidate[0].bookmaker),
            getattr(candidate[0], "id", 0) or 0,
        ),
    )
    return value, best.bookmaker, observed_at


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
        quote_set = select_quote_set(odds_entries, market=prediction.market, as_of=now)
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
            quote = quote_set.quote_for(selection)
            if quote is None:
                continue
            odds_value = quote.price
            bookmaker = quote.bookmaker
            odds_timestamp = quote.observed_at

            market_probability = quote_set.consensus_probabilities.get(selection)
            if market_probability is None:
                continue
            edge_pct = (model_prob - market_probability) * 100
            if edge_pct < min_edge:
                continue

            prediction_age_seconds = _age_seconds(getattr(prediction, "created_at", None), now)
            odds_freshness_seconds = _age_seconds(odds_timestamp, now)
            known_ages = [age for age in (prediction_age_seconds, odds_freshness_seconds) if age is not None]
            data_age_seconds = max(known_ages) if known_ages else None
            source_ok = quote_set.is_ticket_eligible
            model_drift_flag = prediction_age_seconds is None or (
                odds_freshness_seconds is not None
                and prediction_age_seconds > odds_freshness_seconds + VALUE_BET_MODEL_ODDS_SKEW_SECONDS
            )

            block_reasons: list[str] = []
            if not is_ticket_eligible:
                block_reasons.append("prediction_untrusted")
            if not source_ok:
                block_reasons.append("odds_untrusted")
                block_reasons.extend(quote_set.reason_codes)
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
        training_history_days=body.training_history_days,
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
        training_history_days=body.training_history_days,
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
    count_result = await db.execute(select(func.count(PredictionRun.id)).where(PredictionRun.user_id == user.id))
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


def _calibration_outcomes(prediction: ModelPrediction) -> list[tuple[str, float]]:
    market = (prediction.market or "").lower()
    if market == "1x2":
        return [
            ("home", float(prediction.home_prob or 0)),
            ("draw", float(prediction.draw_prob or 0)),
            ("away", float(prediction.away_prob or 0)),
        ]
    if market in {"btts", "both_teams_to_score"}:
        return [("yes", float(prediction.home_prob or 0)), ("no", float(prediction.away_prob or 0))]
    if market in {"ou_2_5", "over_under", "overunder", "totals"}:
        return [("over", float(prediction.home_prob or 0)), ("under", float(prediction.away_prob or 0))]
    return []


def _build_calibration_summary(predictions: list[ModelPrediction], *, bin_count: int) -> PredictionCalibrationResponse:
    grouped: dict[tuple[str, str], list[tuple[list[tuple[str, float]], str]]] = defaultdict(list)
    for prediction in predictions:
        evaluation = evaluate_model_prediction(prediction)
        outcomes = _calibration_outcomes(prediction)
        if evaluation.actual_selection not in {name for name, _ in outcomes}:
            continue
        grouped[(prediction.model_type, prediction.market)].append((outcomes, evaluation.actual_selection))

    groups: list[PredictionCalibrationGroup] = []
    total_resolved = 0
    for (model_type, market), rows in sorted(grouped.items()):
        total_resolved += len(rows)
        correct = 0
        brier_total = 0.0
        log_loss_total = 0.0
        bins: list[list[tuple[float, float]]] = [[] for _ in range(bin_count)]

        for outcomes, actual in rows:
            predicted = max(outcomes, key=lambda item: item[1])[0]
            correct += int(predicted == actual)
            actual_probability = 0.0
            for outcome, raw_probability in outcomes:
                probability = min(1.0, max(0.0, raw_probability))
                observed = 1.0 if outcome == actual else 0.0
                brier_total += (probability - observed) ** 2
                bucket_index = min(int(probability * bin_count), bin_count - 1)
                bins[bucket_index].append((probability, observed))
                if outcome == actual:
                    actual_probability = probability
            log_loss_total += -math.log(max(actual_probability, 1e-15))

        calibration_buckets: list[PredictionCalibrationBucket] = []
        ece = 0.0
        outcome_samples = sum(len(bucket) for bucket in bins)
        for index, bucket in enumerate(bins):
            if not bucket:
                continue
            mean_probability = sum(value[0] for value in bucket) / len(bucket)
            observed_frequency = sum(value[1] for value in bucket) / len(bucket)
            gap = abs(mean_probability - observed_frequency)
            ece += gap * len(bucket) / outcome_samples
            calibration_buckets.append(
                PredictionCalibrationBucket(
                    lower_bound=round(index / bin_count, 4),
                    upper_bound=round((index + 1) / bin_count, 4),
                    mean_predicted_probability=round(mean_probability, 6),
                    observed_frequency=round(observed_frequency, 6),
                    calibration_gap=round(gap, 6),
                    samples=len(bucket),
                )
            )

        groups.append(
            PredictionCalibrationGroup(
                model_type=model_type,
                market=market,
                resolved_predictions=len(rows),
                accuracy=round(correct / len(rows), 6),
                brier_score=round(brier_total / len(rows), 6),
                log_loss=round(log_loss_total / len(rows), 6),
                expected_calibration_error=round(ece, 6),
                buckets=calibration_buckets,
            )
        )

    return PredictionCalibrationResponse(resolved_predictions=total_resolved, groups=groups)


def _build_score_grid_item(predictions: list[ModelPrediction]) -> PredictionScoreGridItem:
    exemplar = predictions[0]
    match = exemplar.match
    stored_grid: dict | None = None
    for prediction in predictions:
        report = prediction.quality_report if isinstance(prediction.quality_report, dict) else {}
        analysis_only = report.get("analysis_only") if isinstance(report.get("analysis_only"), dict) else {}
        candidate = analysis_only.get("score_grid")
        if isinstance(candidate, dict):
            stored_grid = candidate
            break

    base = {
        "match_id": exemplar.match_id,
        "home_team": match.home_team if match else "",
        "away_team": match.away_team if match else "",
        "kickoff": match.match_date if match else None,
        "league": match.competition if match else None,
        "model_type": exemplar.model_type,
        "prediction_ids": sorted({prediction.id for prediction in predictions}),
        "source_markets": sorted({prediction.market for prediction in predictions}),
    }
    if stored_grid is None:
        return PredictionScoreGridItem(
            **base,
            available=False,
            unavailable_reason="score_grid_not_persisted_for_prediction",
        )

    probabilities = stored_grid.get("probabilities")
    if not isinstance(probabilities, list):
        return PredictionScoreGridItem(
            **base,
            available=False,
            unavailable_reason="score_grid_payload_invalid",
        )

    home_expected_goals = stored_grid.get("home_expected_goals")
    away_expected_goals = stored_grid.get("away_expected_goals")
    if home_expected_goals is None or away_expected_goals is None:
        return PredictionScoreGridItem(
            **base,
            available=False,
            unavailable_reason="score_grid_payload_invalid",
        )
    try:
        parsed_home_expected_goals = float(home_expected_goals)
        parsed_away_expected_goals = float(away_expected_goals)
        parsed_max_displayed_goals = int(stored_grid.get("max_displayed_goals", 5))
    except (TypeError, ValueError):
        return PredictionScoreGridItem(
            **base,
            available=False,
            unavailable_reason="score_grid_payload_invalid",
        )

    cells: list[PredictionScoreGridCell] = []
    try:
        for home_goals, row in enumerate(probabilities):
            if not isinstance(row, list):
                raise ValueError("invalid score-grid row")
            for away_goals, raw_probability in enumerate(row):
                probability = min(1.0, max(0.0, float(raw_probability)))
                cells.append(
                    PredictionScoreGridCell(
                        home_goals=home_goals,
                        away_goals=away_goals,
                        probability=probability,
                    )
                )
    except (TypeError, ValueError):
        return PredictionScoreGridItem(
            **base,
            available=False,
            unavailable_reason="score_grid_payload_invalid",
        )

    top_scores = sorted(cells, key=lambda cell: cell.probability, reverse=True)[:5]
    try:
        displayed_probability_mass = float(
            stored_grid.get("displayed_probability_mass", sum(cell.probability for cell in cells))
        )
    except (TypeError, ValueError):
        return PredictionScoreGridItem(
            **base,
            available=False,
            unavailable_reason="score_grid_payload_invalid",
        )
    return PredictionScoreGridItem(
        **base,
        available=True,
        home_expected_goals=parsed_home_expected_goals,
        away_expected_goals=parsed_away_expected_goals,
        max_displayed_goals=parsed_max_displayed_goals,
        displayed_probability_mass=displayed_probability_mass,
        cells=cells,
        top_scores=top_scores,
        usage="analysis_only",
        ticket_generation_eligible=False,
    )


@router.get("/calibration", response_model=PredictionCalibrationResponse)
async def get_prediction_calibration(
    run_id: int | None = None,
    max_results: int = Query(1000, ge=1, le=10000),
    bin_count: int = Query(10, ge=2, le=20),
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
        stmt = stmt.where(PredictionRun.id == run_id)
    result = await db.execute(stmt)
    return _build_calibration_summary(list(result.scalars().all()), bin_count=bin_count)


@router.get("/runs/{run_id}/score-grids", response_model=PredictionScoreGridResponse)
async def get_prediction_score_grids(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(PredictionRun)
        .options(selectinload(PredictionRun.model_predictions).selectinload(ModelPrediction.match))
        .where(PredictionRun.id == run_id, PredictionRun.user_id == user.id)
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Prediction run not found")

    grouped: dict[tuple[int, str], list[ModelPrediction]] = defaultdict(list)
    for prediction in run.model_predictions:
        grouped[(prediction.match_id, prediction.model_type)].append(prediction)

    return PredictionScoreGridResponse(
        run_id=run.id,
        source_dataset_id=run.source_dataset_id,
        items=[_build_score_grid_item(predictions) for _, predictions in sorted(grouped.items())],
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
            selectinload(PredictionRun.model_predictions)
            .selectinload(ModelPrediction.match)
            .selectinload(Match.odds)
            .selectinload(OddsEntry.odds_snapshot),
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
