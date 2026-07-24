from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

EPSILON = 1e-15


@dataclass(frozen=True)
class WalkForwardFold:
    train_start: int
    train_end: int
    test_start: int
    test_end: int


@dataclass(frozen=True)
class CalibrationMetrics:
    sample_size: int
    accuracy: float
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    coverage: float


@dataclass(frozen=True)
class GateResult:
    verdict: str
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.verdict == "passed"


@dataclass(frozen=True)
class EnsembleWeightResult:
    weights: dict[str, float]
    evidence_models: tuple[str, ...]
    fallback_reason: str | None


@dataclass(frozen=True)
class DriftResult:
    severity: str
    reasons: tuple[str, ...]


def stable_fingerprint(payload: Mapping[str, Any] | Sequence[Any]) -> str:
    """Return a deterministic SHA-256 fingerprint for model/config/data evidence."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_walk_forward_folds(
    total_samples: int,
    *,
    min_train: int = 200,
    test_size: int = 50,
    step: int = 50,
    max_folds: int = 8,
) -> list[WalkForwardFold]:
    if min(total_samples, min_train, test_size, step, max_folds) < 1:
        raise ValueError("walk-forward parameters must be positive")

    folds: list[WalkForwardFold] = []
    test_start = min_train
    while test_start + test_size <= total_samples and len(folds) < max_folds:
        folds.append(
            WalkForwardFold(
                train_start=0,
                train_end=test_start,
                test_start=test_start,
                test_end=test_start + test_size,
            )
        )
        test_start += step
    return folds


def calibration_metrics(
    rows: Iterable[tuple[Sequence[float], int]],
    *,
    eligible_count: int | None = None,
    bucket_count: int = 10,
) -> CalibrationMetrics:
    if bucket_count < 2:
        raise ValueError("bucket_count must be at least 2")

    materialized = list(rows)
    if not materialized:
        return CalibrationMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0)

    correct = 0
    brier_total = 0.0
    log_loss_total = 0.0
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bucket_count)]

    for probabilities, outcome_index in materialized:
        probs = [float(value) for value in probabilities]
        if len(probs) < 2 or not 0 <= outcome_index < len(probs):
            raise ValueError("invalid probability vector or outcome index")
        if any(not math.isfinite(value) or value < 0 for value in probs):
            raise ValueError("probabilities must be finite and non-negative")
        total = sum(probs)
        if total <= 0:
            raise ValueError("probabilities must have positive mass")
        probs = [value / total for value in probs]

        predicted_index = max(range(len(probs)), key=probs.__getitem__)
        confidence = probs[predicted_index]
        actual_correct = 1.0 if predicted_index == outcome_index else 0.0
        correct += int(actual_correct)
        bucket_index = min(bucket_count - 1, int(confidence * bucket_count))
        buckets[bucket_index].append((confidence, actual_correct))

        for index, probability in enumerate(probs):
            target = 1.0 if index == outcome_index else 0.0
            brier_total += (probability - target) ** 2
        log_loss_total -= math.log(max(EPSILON, probs[outcome_index]))

    sample_size = len(materialized)
    ece = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        mean_confidence = sum(value[0] for value in bucket) / len(bucket)
        mean_accuracy = sum(value[1] for value in bucket) / len(bucket)
        ece += (len(bucket) / sample_size) * abs(mean_accuracy - mean_confidence)

    denominator = eligible_count if eligible_count is not None else sample_size
    coverage = sample_size / denominator if denominator > 0 else 0.0
    return CalibrationMetrics(
        sample_size=sample_size,
        accuracy=correct / sample_size,
        brier_score=brier_total / sample_size,
        log_loss=log_loss_total / sample_size,
        expected_calibration_error=ece,
        coverage=coverage,
    )


def evaluate_walk_forward_gate(
    *,
    sample_size: int,
    market_samples: Mapping[str, int],
    valid_folds: int,
    expected_calibration_error: float,
    brier_skill: float,
    coverage: float,
    leakage_errors: int = 0,
    quote_after_cutoff_errors: int = 0,
    fallback_predictions: int = 0,
) -> GateResult:
    reasons: list[str] = []
    if sample_size < 300:
        reasons.append("minimum_total_sample_not_met")
    if any(count < 100 for count in market_samples.values()) or not market_samples:
        reasons.append("minimum_market_sample_not_met")
    if valid_folds < 4:
        reasons.append("minimum_valid_folds_not_met")
    if expected_calibration_error > 0.08:
        reasons.append("ece_above_threshold")
    if brier_skill <= 0:
        reasons.append("brier_skill_not_positive")
    if coverage < 0.80:
        reasons.append("coverage_below_threshold")
    if leakage_errors:
        reasons.append("temporal_leakage_detected")
    if quote_after_cutoff_errors:
        reasons.append("quote_after_cutoff_detected")
    if fallback_predictions:
        reasons.append("fallback_predictions_present")

    insufficient = {
        "minimum_total_sample_not_met",
        "minimum_market_sample_not_met",
        "minimum_valid_folds_not_met",
    }
    verdict = "passed" if not reasons else ("insufficient_evidence" if insufficient.intersection(reasons) else "failed")
    return GateResult(verdict=verdict, reasons=tuple(reasons))


def compute_shrunk_inverse_brier_weights(
    model_evidence: Mapping[str, tuple[float, int]],
    *,
    min_samples: int = 100,
    shrinkage_samples: int = 200,
) -> EnsembleWeightResult:
    model_keys = tuple(sorted(model_evidence))
    if not model_keys:
        return EnsembleWeightResult({}, (), "no_models")

    eligible = {
        key: (score, count)
        for key, (score, count) in model_evidence.items()
        if count >= min_samples and math.isfinite(score) and score >= 0
    }
    if len(eligible) < 2:
        uniform = 1.0 / len(model_keys)
        return EnsembleWeightResult(
            weights={key: uniform for key in model_keys},
            evidence_models=tuple(sorted(eligible)),
            fallback_reason="insufficient_evidence_models",
        )

    raw = {key: 1.0 / (score + 1e-3) for key, (score, _count) in eligible.items()}
    raw_total = sum(raw.values())
    evidence_weight = {key: value / raw_total for key, value in raw.items()}
    uniform = 1.0 / len(eligible)

    shrunk: dict[str, float] = {}
    for key, (_score, count) in eligible.items():
        alpha = count / (count + shrinkage_samples)
        shrunk[key] = alpha * evidence_weight[key] + (1.0 - alpha) * uniform
    total = sum(shrunk.values())
    normalized = {key: value / total for key, value in shrunk.items()}
    return EnsembleWeightResult(normalized, tuple(sorted(eligible)), None)


def classify_model_drift(
    *,
    psi: float | None = None,
    ece: float | None = None,
    ece_delta: float | None = None,
    brier_relative_degradation: float | None = None,
    fallback_rate: float | None = None,
    median_clv_pct: float | None = None,
    resolved_samples: int = 0,
) -> DriftResult:
    warning: list[str] = []
    critical: list[str] = []

    if psi is not None:
        if psi > 0.25:
            critical.append("psi_critical")
        elif psi > 0.10:
            warning.append("psi_warning")
    if fallback_rate is not None:
        if fallback_rate > 0.05:
            critical.append("fallback_rate_critical")
        elif fallback_rate > 0.02:
            warning.append("fallback_rate_warning")

    if resolved_samples >= 100:
        if ece is not None and ece_delta is not None and ece > 0.12 and ece_delta > 0.04:
            critical.append("ece_critical")
        elif ece_delta is not None and ece_delta > 0.02:
            warning.append("ece_delta_warning")
        if brier_relative_degradation is not None and brier_relative_degradation > 0.10:
            critical.append("brier_degradation_critical")
        if median_clv_pct is not None and median_clv_pct < -1.5:
            critical.append("clv_critical")

    if critical:
        return DriftResult("critical", tuple(critical + warning))
    if warning:
        return DriftResult("warning", tuple(warning))
    return DriftResult("ok", ())


def serialize_metrics(metrics: CalibrationMetrics) -> dict[str, Any]:
    return asdict(metrics)
