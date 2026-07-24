from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_governance import (
    ModelCertification,
    ModelEvaluation,
    ModelEvaluationFold,
    ModelEvaluationPrediction,
    ModelMonitoringSnapshot,
    ModelVersion,
)
from app.schemas.model_governance import (
    EvaluationFoldInput,
    EvaluationObservationInput,
    GovernanceGateResponse,
    ModelEvaluationCreateRequest,
    MonitoringSnapshotCreateRequest,
)
from app.services.model_validation import (
    CalibrationMetrics,
    calibration_metrics,
    classify_model_drift,
    evaluate_walk_forward_gate,
    serialize_metrics,
    stable_fingerprint,
)


@dataclass(frozen=True)
class ObservationCalculation:
    payload: EvaluationObservationInput
    normalized_probabilities: dict[str, float]
    predicted_selection: str
    predicted_probability: float
    leakage: bool
    quote_cutoff_violation: bool


@dataclass(frozen=True)
class FoldCalculation:
    payload: EvaluationFoldInput
    metrics: CalibrationMetrics
    observations: tuple[ObservationCalculation, ...]
    leakage_errors: int
    quote_cutoff_violations: int
    fallback_count: int

    @property
    def valid(self) -> bool:
        return self.leakage_errors == 0 and self.quote_cutoff_violations == 0 and bool(self.observations)


@dataclass(frozen=True)
class EvaluationCalculation:
    folds: tuple[FoldCalculation, ...]
    metrics: CalibrationMetrics
    market_samples: dict[str, int]
    valid_folds: int
    leakage_errors: int
    quote_cutoff_violations: int
    fallback_count: int
    brier_skill: float
    status: str
    reasons: tuple[str, ...]
    window_days: int


def _require_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(timezone.utc)


def _calculate_observation(
    fold: EvaluationFoldInput,
    observation: EvaluationObservationInput,
) -> ObservationCalculation:
    training_cutoff = _require_aware(fold.training_cutoff_at, "training_cutoff_at")
    test_started = _require_aware(fold.test_started_at, "test_started_at")
    test_ended = _require_aware(fold.test_ended_at, "test_ended_at")
    forecast_at = _require_aware(observation.forecast_at, "forecast_at")
    kickoff_at = _require_aware(observation.kickoff_at, "kickoff_at")

    total = sum(observation.probabilities.values())
    normalized = {selection: probability / total for selection, probability in observation.probabilities.items()}
    predicted_selection = max(sorted(normalized), key=normalized.__getitem__)
    predicted_probability = normalized[predicted_selection]
    if predicted_probability >= 1:
        raise ValueError("probability vectors must retain uncertainty after normalization")

    leakage = not (
        training_cutoff < test_started <= forecast_at < kickoff_at and test_started <= kickoff_at <= test_ended
    )
    quote_violation = False
    if observation.quote_observed_at is not None:
        quote_observed_at = _require_aware(observation.quote_observed_at, "quote_observed_at")
        quote_violation = quote_observed_at > forecast_at

    return ObservationCalculation(
        payload=observation,
        normalized_probabilities=normalized,
        predicted_selection=predicted_selection,
        predicted_probability=predicted_probability,
        leakage=leakage,
        quote_cutoff_violation=quote_violation,
    )


def calculate_evaluation(request: ModelEvaluationCreateRequest) -> EvaluationCalculation:
    fold_calculations: list[FoldCalculation] = []
    all_metric_rows: list[tuple[list[float], int]] = []
    market_samples: Counter[str] = Counter()
    kickoff_values: list[datetime] = []
    total_eligible = 0

    for fold in sorted(request.folds, key=lambda item: item.fold_number):
        test_started = _require_aware(fold.test_started_at, "test_started_at")
        test_ended = _require_aware(fold.test_ended_at, "test_ended_at")
        training_cutoff = _require_aware(fold.training_cutoff_at, "training_cutoff_at")
        if test_ended <= test_started:
            raise ValueError("test_ended_at must be later than test_started_at")
        if training_cutoff >= test_started:
            raise ValueError("training_cutoff_at must be strictly earlier than test_started_at")
        if fold.training_started_at is not None:
            training_started = _require_aware(fold.training_started_at, "training_started_at")
            if training_started >= training_cutoff:
                raise ValueError("training_started_at must be earlier than training_cutoff_at")
        if fold.eligible_count < len(fold.observations):
            raise ValueError("eligible_count cannot be smaller than resolved observations")

        observations = tuple(_calculate_observation(fold, observation) for observation in fold.observations)
        metric_rows: list[tuple[list[float], int]] = []
        for item in observations:
            selections = sorted(item.normalized_probabilities)
            probabilities = [item.normalized_probabilities[selection] for selection in selections]
            outcome_index = selections.index(item.payload.actual_selection)
            metric_rows.append((probabilities, outcome_index))
            all_metric_rows.append((probabilities, outcome_index))
            market_samples[item.payload.market] += 1
            kickoff_values.append(_require_aware(item.payload.kickoff_at, "kickoff_at"))

        fold_calculations.append(
            FoldCalculation(
                payload=fold,
                metrics=calibration_metrics(metric_rows, eligible_count=fold.eligible_count),
                observations=observations,
                leakage_errors=sum(item.leakage for item in observations),
                quote_cutoff_violations=sum(item.quote_cutoff_violation for item in observations),
                fallback_count=sum(item.payload.fallback for item in observations),
            )
        )
        total_eligible += fold.eligible_count

    metrics = calibration_metrics(all_metric_rows, eligible_count=total_eligible)
    leakage_errors = sum(fold.leakage_errors for fold in fold_calculations)
    quote_cutoff_violations = sum(fold.quote_cutoff_violations for fold in fold_calculations)
    fallback_count = sum(fold.fallback_count for fold in fold_calculations)
    valid_folds = sum(fold.valid for fold in fold_calculations)
    brier_skill = 1.0 - (metrics.brier_score / request.baseline_brier_score)
    gate = evaluate_walk_forward_gate(
        sample_size=metrics.sample_size,
        market_samples=market_samples,
        valid_folds=valid_folds,
        expected_calibration_error=metrics.expected_calibration_error,
        brier_skill=brier_skill,
        coverage=metrics.coverage,
        leakage_errors=leakage_errors,
        quote_after_cutoff_errors=quote_cutoff_violations,
        fallback_predictions=fallback_count,
    )
    status = gate.verdict
    if leakage_errors or quote_cutoff_violations or fallback_count:
        status = "failed"
    window_days = 0
    if kickoff_values:
        window_days = max(0, (max(kickoff_values) - min(kickoff_values)).days)

    return EvaluationCalculation(
        folds=tuple(fold_calculations),
        metrics=metrics,
        market_samples=dict(sorted(market_samples.items())),
        valid_folds=valid_folds,
        leakage_errors=leakage_errors,
        quote_cutoff_violations=quote_cutoff_violations,
        fallback_count=fallback_count,
        brier_skill=brier_skill,
        status=status,
        reasons=gate.reasons,
        window_days=window_days,
    )


async def _get_or_create_model_version(
    db: AsyncSession,
    request: ModelEvaluationCreateRequest,
) -> ModelVersion:
    payload = request.model_version
    feature_schema_hash = stable_fingerprint(payload.feature_schema)
    strategy_config_hash = stable_fingerprint(payload.strategy_config)
    training_data_fingerprint = stable_fingerprint(payload.training_data)
    identity = (
        ModelVersion.model_key == payload.model_key,
        ModelVersion.version == payload.version,
        ModelVersion.strategy_config_hash == strategy_config_hash,
        ModelVersion.training_data_fingerprint == training_data_fingerprint,
    )
    existing = (await db.execute(select(ModelVersion).where(*identity))).scalar_one_or_none()
    if existing is not None:
        immutable_values = (
            existing.build_revision == payload.build_revision,
            existing.feature_schema_hash == feature_schema_hash,
            existing.training_cutoff_at == payload.training_cutoff_at,
        )
        if not all(immutable_values):
            raise ValueError("model version identity collides with different immutable evidence")
        return existing

    model_version = ModelVersion(
        model_key=payload.model_key,
        version=payload.version,
        build_revision=payload.build_revision,
        engine_version=payload.engine_version,
        feature_schema_hash=feature_schema_hash,
        strategy_config_hash=strategy_config_hash,
        training_data_fingerprint=training_data_fingerprint,
        training_cutoff_at=payload.training_cutoff_at,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    db.add(model_version)
    await db.flush()
    return model_version


async def create_evaluation(
    db: AsyncSession,
    *,
    user_id: int,
    request: ModelEvaluationCreateRequest,
) -> tuple[ModelEvaluation, ModelVersion, list[ModelEvaluationFold]]:
    calculation = calculate_evaluation(request)
    model_version = await _get_or_create_model_version(db, request)
    now = datetime.now(timezone.utc)
    metrics = {
        **serialize_metrics(calculation.metrics),
        "brier_skill": calculation.brier_skill,
        "baseline_brier_score": request.baseline_brier_score,
        "market_samples": calculation.market_samples,
        "window_days": calculation.window_days,
        "median_clv_pct": request.parameters.get("median_clv_pct"),
    }
    evaluation = ModelEvaluation(
        model_version_id=model_version.id,
        user_id=user_id,
        evaluation_kind=request.evaluation_kind,
        status=calculation.status,
        scope_key=request.scope_key,
        scope_json=request.scope,
        parameters={
            **request.parameters,
            "baseline_brier_score": request.baseline_brier_score,
            "fold_count": len(request.folds),
        },
        sample_size=calculation.metrics.sample_size,
        resolved_count=calculation.metrics.sample_size,
        valid_folds=calculation.valid_folds,
        coverage=Decimal(str(calculation.metrics.coverage)),
        metrics=metrics,
        leakage_detected=calculation.leakage_errors > 0,
        quote_cutoff_violations=calculation.quote_cutoff_violations,
        fallback_count=calculation.fallback_count,
        failure_reasons=list(calculation.reasons),
        started_at=now,
        completed_at=now,
    )
    db.add(evaluation)
    await db.flush()

    persisted_folds: list[ModelEvaluationFold] = []
    for fold in calculation.folds:
        fold_metrics = {
            **serialize_metrics(fold.metrics),
            "leakage_errors": fold.leakage_errors,
            "quote_cutoff_violations": fold.quote_cutoff_violations,
            "fallback_count": fold.fallback_count,
        }
        record = ModelEvaluationFold(
            evaluation_id=evaluation.id,
            fold_number=fold.payload.fold_number,
            training_started_at=fold.payload.training_started_at,
            training_cutoff_at=fold.payload.training_cutoff_at,
            test_started_at=fold.payload.test_started_at,
            test_ended_at=fold.payload.test_ended_at,
            training_count=fold.payload.training_count,
            test_count=fold.payload.eligible_count,
            resolved_count=len(fold.observations),
            metrics=fold_metrics,
        )
        db.add(record)
        await db.flush()
        persisted_folds.append(record)

        for observation in fold.observations:
            payload = observation.payload
            db.add(
                ModelEvaluationPrediction(
                    fold_id=record.id,
                    match_id=payload.match_id,
                    odds_snapshot_id=payload.odds_snapshot_id,
                    market=payload.market,
                    selection=observation.predicted_selection,
                    predicted_probability=Decimal(str(observation.predicted_probability)),
                    fair_odds=Decimal(str(1.0 / observation.predicted_probability)),
                    quoted_odds=Decimal(str(payload.quoted_odds)) if payload.quoted_odds is not None else None,
                    quote_observed_at=payload.quote_observed_at,
                    kickoff_at=payload.kickoff_at,
                    actual_selection=payload.actual_selection,
                    is_correct=observation.predicted_selection == payload.actual_selection,
                    resolved_at=now,
                )
            )
    await db.flush()
    return evaluation, model_version, persisted_folds


async def get_owned_evaluation(db: AsyncSession, *, evaluation_id: int, user_id: int) -> ModelEvaluation | None:
    return (
        await db.execute(
            select(ModelEvaluation).where(
                ModelEvaluation.id == evaluation_id,
                ModelEvaluation.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def get_evaluation_detail(
    db: AsyncSession,
    *,
    evaluation_id: int,
    user_id: int,
) -> tuple[ModelEvaluation, ModelVersion, list[ModelEvaluationFold]] | None:
    evaluation = await get_owned_evaluation(db, evaluation_id=evaluation_id, user_id=user_id)
    if evaluation is None:
        return None
    model_version = await db.get(ModelVersion, evaluation.model_version_id)
    if model_version is None:
        return None
    folds = (
        (
            await db.execute(
                select(ModelEvaluationFold)
                .where(ModelEvaluationFold.evaluation_id == evaluation.id)
                .order_by(ModelEvaluationFold.fold_number)
            )
        )
        .scalars()
        .all()
    )
    return evaluation, model_version, list(folds)


async def list_evaluations(
    db: AsyncSession,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[ModelEvaluation], int]:
    filters = (ModelEvaluation.user_id == user_id,)
    total = int((await db.execute(select(func.count()).select_from(ModelEvaluation).where(*filters))).scalar_one())
    rows = (
        (
            await db.execute(
                select(ModelEvaluation)
                .where(*filters)
                .order_by(ModelEvaluation.created_at.desc(), ModelEvaluation.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


def certification_status_for_evaluation(evaluation: ModelEvaluation, model_version: ModelVersion) -> str:
    if model_version.status == "legacy_unversioned":
        raise ValueError("legacy_unversioned models are analysis-only")
    if evaluation.evaluation_kind == "walk_forward":
        if evaluation.status != "passed":
            raise ValueError("walk-forward evaluation must pass before certification")
        return "walk_forward_passed"

    metrics = evaluation.metrics if isinstance(evaluation.metrics, dict) else {}
    market_samples = metrics.get("market_samples") if isinstance(metrics.get("market_samples"), dict) else {}
    evidence_ready = (
        evaluation.status == "passed"
        and evaluation.resolved_count >= 500
        and int(metrics.get("window_days") or 0) >= 60
        and bool(market_samples)
        and all(int(count) >= 100 for count in market_samples.values())
        and float(metrics.get("expected_calibration_error") or 1) <= 0.08
        and float(metrics.get("median_clv_pct") if metrics.get("median_clv_pct") is not None else -999) >= -0.5
    )
    return "certified" if evidence_ready else "paper_collecting"


async def create_certification(
    db: AsyncSession,
    *,
    user_id: int,
    evaluation_id: int,
    validity_days: int,
) -> ModelCertification:
    detail = await get_evaluation_detail(db, evaluation_id=evaluation_id, user_id=user_id)
    if detail is None:
        raise LookupError("evaluation not found")
    evaluation, model_version, _folds = detail
    status = certification_status_for_evaluation(evaluation, model_version)
    now = datetime.now(timezone.utc)
    certification = ModelCertification(
        model_version_id=model_version.id,
        model_evaluation_id=evaluation.id,
        certification_type=evaluation.evaluation_kind,
        status=status,
        scope_key=evaluation.scope_key,
        evidence={
            "evaluation_status": evaluation.status,
            "evaluation_metrics": evaluation.metrics,
            "failure_reasons": evaluation.failure_reasons,
            "model_fingerprint": model_version.training_data_fingerprint,
            "staged_gate": True,
        },
        valid_from=now,
        valid_until=now + timedelta(days=validity_days),
    )
    db.add(certification)
    await db.flush()
    return certification


def _owned_version_exists(user_id: int):
    return exists(
        select(ModelEvaluation.id).where(
            ModelEvaluation.model_version_id == ModelVersion.id,
            ModelEvaluation.user_id == user_id,
        )
    )


async def get_owned_model_version(db: AsyncSession, *, model_version_id: int, user_id: int) -> ModelVersion | None:
    return (
        await db.execute(
            select(ModelVersion).where(
                ModelVersion.id == model_version_id,
                _owned_version_exists(user_id),
            )
        )
    ).scalar_one_or_none()


async def list_certifications(
    db: AsyncSession,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[ModelCertification], int]:
    owner_filter = exists(
        select(ModelEvaluation.id).where(
            ModelEvaluation.id == ModelCertification.model_evaluation_id,
            ModelEvaluation.user_id == user_id,
        )
    )
    total = int(
        (await db.execute(select(func.count()).select_from(ModelCertification).where(owner_filter))).scalar_one()
    )
    rows = (
        (
            await db.execute(
                select(ModelCertification)
                .where(owner_filter)
                .order_by(ModelCertification.created_at.desc(), ModelCertification.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def get_owned_certification(
    db: AsyncSession,
    *,
    certification_id: int,
    user_id: int,
) -> ModelCertification | None:
    owner_filter = exists(
        select(ModelEvaluation.id).where(
            ModelEvaluation.id == ModelCertification.model_evaluation_id,
            ModelEvaluation.user_id == user_id,
        )
    )
    return (
        await db.execute(
            select(ModelCertification).where(
                ModelCertification.id == certification_id,
                owner_filter,
            )
        )
    ).scalar_one_or_none()


async def get_latest_owned_certification(
    db: AsyncSession,
    *,
    model_version_id: int,
    user_id: int,
    scope_key: str | None = None,
    active_at: datetime | None = None,
) -> ModelCertification | None:
    """Return the tenant-owned certification eligible for a scope/window."""

    owner_filter = exists(
        select(ModelEvaluation.id).where(
            ModelEvaluation.id == ModelCertification.model_evaluation_id,
            ModelEvaluation.user_id == user_id,
        )
    )
    statement = select(ModelCertification).where(
        ModelCertification.model_version_id == model_version_id,
        owner_filter,
    )
    if scope_key is not None:
        statement = statement.where(ModelCertification.scope_key == scope_key)
    if active_at is not None:
        statement = statement.where(
            ModelCertification.valid_from <= active_at,
            ModelCertification.valid_until > active_at,
            ModelCertification.status.not_in(("suspended", "expired")),
        )
    return (
        await db.execute(
            statement.order_by(
                ModelCertification.valid_from.desc(),
                ModelCertification.created_at.desc(),
                ModelCertification.id.desc(),
            ).limit(1)
        )
    ).scalar_one_or_none()


async def create_monitoring_snapshot(
    db: AsyncSession,
    *,
    user_id: int,
    request: MonitoringSnapshotCreateRequest,
) -> ModelMonitoringSnapshot:
    model_version = await get_owned_model_version(db, model_version_id=request.model_version_id, user_id=user_id)
    if model_version is None:
        raise LookupError("model version not found")
    window_started = _require_aware(request.window_started_at, "window_started_at")
    window_ended = _require_aware(request.window_ended_at, "window_ended_at")
    if window_ended <= window_started:
        raise ValueError("window_ended_at must be later than window_started_at")

    certification: ModelCertification | None = None
    if request.model_certification_id is not None:
        certification = await get_owned_certification(
            db,
            certification_id=request.model_certification_id,
            user_id=user_id,
        )
        if certification is None:
            raise LookupError("certification not found")
        if certification.model_version_id != model_version.id or certification.scope_key != request.scope_key:
            raise ValueError("monitoring scope does not match certification")
    else:
        certification = await get_latest_owned_certification(
            db,
            model_version_id=model_version.id,
            user_id=user_id,
            scope_key=request.scope_key,
            active_at=window_ended,
        )

    metrics = {
        **request.extra_metrics,
        "psi": request.psi,
        "expected_calibration_error": request.expected_calibration_error,
        "ece_delta": request.ece_delta,
        "brier_relative_degradation": request.brier_relative_degradation,
        "fallback_rate": request.fallback_rate,
        "median_clv_pct": request.median_clv_pct,
    }
    if request.sample_size < 100:
        severity = "insufficient_evidence"
        reasons = ["minimum_monitoring_sample_not_met"]
    else:
        drift = classify_model_drift(
            psi=request.psi,
            ece=request.expected_calibration_error,
            ece_delta=request.ece_delta,
            brier_relative_degradation=request.brier_relative_degradation,
            fallback_rate=request.fallback_rate,
            median_clv_pct=request.median_clv_pct,
            resolved_samples=request.sample_size,
        )
        severity = "healthy" if drift.severity == "ok" else drift.severity
        reasons = list(drift.reasons)

    snapshot = ModelMonitoringSnapshot(
        user_id=user_id,
        model_version_id=model_version.id,
        model_certification_id=certification.id if certification is not None else None,
        scope_key=request.scope_key,
        window_started_at=window_started,
        window_ended_at=window_ended,
        sample_size=request.sample_size,
        severity=severity,
        metrics=metrics,
        reasons=reasons,
    )
    db.add(snapshot)
    await db.flush()

    if severity == "critical" and certification is not None and certification.status != "suspended":
        latest = (
            (
                await db.execute(
                    select(ModelMonitoringSnapshot.severity)
                    .where(
                        ModelMonitoringSnapshot.user_id == user_id,
                        ModelMonitoringSnapshot.model_version_id == model_version.id,
                        ModelMonitoringSnapshot.scope_key == request.scope_key,
                        ModelMonitoringSnapshot.model_certification_id == certification.id,
                    )
                    .order_by(ModelMonitoringSnapshot.window_ended_at.desc(), ModelMonitoringSnapshot.id.desc())
                    .limit(2)
                )
            )
            .scalars()
            .all()
        )
        if len(latest) == 2 and all(value == "critical" for value in latest):
            certification.status = "suspended"
            certification.suspended_at = datetime.now(timezone.utc)
            certification.suspension_reason = "two_consecutive_critical_monitoring_windows"
            await db.flush()
    return snapshot


async def list_monitoring_snapshots(
    db: AsyncSession,
    *,
    user_id: int,
    model_version_id: int | None,
    limit: int,
    offset: int,
) -> tuple[list[ModelMonitoringSnapshot], int]:
    filters: list[Any] = [ModelMonitoringSnapshot.user_id == user_id]
    if model_version_id is not None:
        filters.append(ModelMonitoringSnapshot.model_version_id == model_version_id)
    total = int(
        (await db.execute(select(func.count()).select_from(ModelMonitoringSnapshot).where(*filters))).scalar_one()
    )
    rows = (
        (
            await db.execute(
                select(ModelMonitoringSnapshot)
                .where(*filters)
                .order_by(ModelMonitoringSnapshot.window_ended_at.desc(), ModelMonitoringSnapshot.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def governance_evidence(
    db: AsyncSession,
    *,
    user_id: int,
    model_version_id: int,
) -> (
    tuple[
        ModelVersion,
        ModelEvaluation | None,
        ModelCertification | None,
        ModelMonitoringSnapshot | None,
        GovernanceGateResponse,
    ]
    | None
):
    model_version = await get_owned_model_version(db, model_version_id=model_version_id, user_id=user_id)
    if model_version is None:
        return None
    latest_evaluation = (
        await db.execute(
            select(ModelEvaluation)
            .where(
                ModelEvaluation.model_version_id == model_version.id,
                ModelEvaluation.user_id == user_id,
            )
            .order_by(ModelEvaluation.created_at.desc(), ModelEvaluation.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    certification_owner = exists(
        select(ModelEvaluation.id).where(
            ModelEvaluation.id == ModelCertification.model_evaluation_id,
            ModelEvaluation.user_id == user_id,
        )
    )
    latest_certification = (
        await db.execute(
            select(ModelCertification)
            .where(
                ModelCertification.model_version_id == model_version.id,
                certification_owner,
            )
            .order_by(ModelCertification.created_at.desc(), ModelCertification.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    latest_monitoring = (
        await db.execute(
            select(ModelMonitoringSnapshot)
            .where(
                ModelMonitoringSnapshot.model_version_id == model_version.id,
                ModelMonitoringSnapshot.user_id == user_id,
            )
            .order_by(ModelMonitoringSnapshot.window_ended_at.desc(), ModelMonitoringSnapshot.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    gate = governance_gate(model_version=model_version, certification=latest_certification)
    if latest_monitoring is not None and latest_monitoring.severity == "critical":
        gate = GovernanceGateResponse(
            analysis_allowed=True,
            manual_paper_allowed=False,
            scheduled_paper_allowed=False,
            reason="critical_monitoring_drift",
            certification_status=latest_certification.status if latest_certification is not None else None,
            certification_id=latest_certification.id if latest_certification is not None else None,
        )
    return model_version, latest_evaluation, latest_certification, latest_monitoring, gate


async def assess_prediction_runs_governance(
    db: AsyncSession,
    *,
    user_id: int,
    runs: list[Any],
    automated: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Revalidate versioned prediction runs at every paper action boundary.

    Unversioned historical runs remain usable during the staged rollout. Once
    a run declares a model version, however, certification, ownership,
    immutable fingerprints, expiry, suspension, and critical drift are all
    fail-closed. Scheduled jobs require full certification; manual draft and
    activation paths may use the staged manual statuses.
    """

    checked_at = now or datetime.now(timezone.utc)
    mode = "scheduled" if automated else "manual"
    run_results: list[dict[str, Any]] = []
    evaluation_ids: list[int] = []
    for run in runs:
        model_version_id = getattr(run, "model_version_id", None)
        if model_version_id is None:
            run_results.append(
                {
                    "run_id": run.id,
                    "model_version_id": None,
                    "allowed": True,
                    "reason": "unversioned_rollout_compatibility",
                }
            )
            continue

        evidence = await governance_evidence(
            db,
            user_id=user_id,
            model_version_id=int(model_version_id),
        )
        if evidence is None:
            run_results.append(
                {
                    "run_id": run.id,
                    "model_version_id": model_version_id,
                    "allowed": False,
                    "reason": "model_version_not_owned_or_unevaluated",
                }
            )
            continue
        model_version, evaluation, certification, monitoring, gate = evidence
        fingerprint_matches = getattr(run, "strategy_config_hash", None) in {
            None,
            model_version.strategy_config_hash,
        } and getattr(run, "training_data_fingerprint", None) in {None, model_version.training_data_fingerprint}
        allowed = gate.scheduled_paper_allowed if automated else gate.manual_paper_allowed
        reason = gate.reason
        if not fingerprint_matches:
            allowed = False
            reason = "run_model_version_fingerprint_mismatch"
        if model_version.status == "retired":
            allowed = False
            reason = "model_version_retired"
        if evaluation is not None:
            evaluation_ids.append(int(evaluation.id))
        run_results.append(
            {
                "run_id": run.id,
                "model_version_id": model_version.id,
                "model_evaluation_id": evaluation.id if evaluation is not None else None,
                "certification_id": certification.id if certification is not None else None,
                "certification_status": certification.status if certification is not None else None,
                "monitoring_severity": monitoring.severity if monitoring is not None else None,
                "allowed": allowed,
                "reason": reason,
            }
        )

    return {
        "allowed": all(item["allowed"] for item in run_results),
        "mode": mode,
        "checked_at": checked_at.isoformat(),
        "runs": run_results,
        "model_evaluation_ids": list(dict.fromkeys(evaluation_ids)),
    }


def governance_gate(
    *,
    model_version: ModelVersion,
    certification: ModelCertification | None,
    now: datetime | None = None,
) -> GovernanceGateResponse:
    current_time = now or datetime.now(timezone.utc)
    if model_version.status == "legacy_unversioned":
        return GovernanceGateResponse(
            analysis_allowed=True,
            manual_paper_allowed=False,
            scheduled_paper_allowed=False,
            reason="legacy_unversioned_analysis_only",
        )
    if certification is None or certification.valid_until <= current_time:
        return GovernanceGateResponse(
            analysis_allowed=True,
            manual_paper_allowed=False,
            scheduled_paper_allowed=False,
            reason="certification_missing_or_expired",
        )
    if certification.status in {"suspended", "expired"}:
        return GovernanceGateResponse(
            analysis_allowed=True,
            manual_paper_allowed=False,
            scheduled_paper_allowed=False,
            reason=f"certification_{certification.status}",
            certification_status=certification.status,
            certification_id=certification.id,
        )
    manual_allowed = certification.status in {"walk_forward_passed", "paper_collecting", "certified"}
    scheduled_allowed = certification.status == "certified"
    return GovernanceGateResponse(
        analysis_allowed=True,
        manual_paper_allowed=manual_allowed,
        scheduled_paper_allowed=scheduled_allowed,
        reason="certified_for_scheduled_paper" if scheduled_allowed else "staged_manual_paper_only",
        certification_status=certification.status,
        certification_id=certification.id,
    )
