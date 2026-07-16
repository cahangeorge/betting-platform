from __future__ import annotations

import pytest

from app.services.model_validation import (
    build_walk_forward_folds,
    calibration_metrics,
    classify_model_drift,
    compute_shrunk_inverse_brier_weights,
    evaluate_walk_forward_gate,
    stable_fingerprint,
)


def test_fingerprint_is_order_independent_for_mapping_keys():
    assert stable_fingerprint({"b": 2, "a": [1, 3]}) == stable_fingerprint({"a": [1, 3], "b": 2})


def test_walk_forward_folds_use_strictly_prior_training_rows():
    folds = build_walk_forward_folds(450)
    assert len(folds) == 5
    assert folds[0].train_end == folds[0].test_start == 200
    assert folds[-1].test_end == 450
    assert all(fold.train_end <= fold.test_start for fold in folds)


def test_calibration_metrics_normalize_and_measure_coverage():
    metrics = calibration_metrics(
        [([0.8, 0.1, 0.1], 0), ([0.2, 0.6, 0.2], 1), ([0.1, 0.2, 0.7], 0)],
        eligible_count=4,
    )
    assert metrics.sample_size == 3
    assert metrics.accuracy == pytest.approx(2 / 3)
    assert metrics.coverage == pytest.approx(0.75)
    assert metrics.brier_score > 0
    assert metrics.log_loss > 0


def test_walk_forward_gate_distinguishes_insufficient_evidence_from_failure():
    insufficient = evaluate_walk_forward_gate(
        sample_size=299,
        market_samples={"1x2": 99},
        valid_folds=3,
        expected_calibration_error=0.01,
        brier_skill=0.1,
        coverage=1.0,
    )
    assert insufficient.verdict == "insufficient_evidence"

    failed = evaluate_walk_forward_gate(
        sample_size=400,
        market_samples={"1x2": 200},
        valid_folds=4,
        expected_calibration_error=0.09,
        brier_skill=-0.01,
        coverage=0.9,
    )
    assert failed.verdict == "failed"


def test_walk_forward_gate_passes_only_clean_evidence():
    result = evaluate_walk_forward_gate(
        sample_size=400,
        market_samples={"1x2": 200, "btts": 200},
        valid_folds=5,
        expected_calibration_error=0.06,
        brier_skill=0.03,
        coverage=0.9,
    )
    assert result.passed


def test_ensemble_weights_require_two_evidence_models_and_shrink():
    fallback = compute_shrunk_inverse_brier_weights({"a": (0.2, 120), "b": (0.3, 20)})
    assert fallback.fallback_reason == "insufficient_evidence_models"
    assert fallback.weights == {"a": 0.5, "b": 0.5}

    weighted = compute_shrunk_inverse_brier_weights({"a": (0.2, 200), "b": (0.4, 200)})
    assert weighted.fallback_reason is None
    assert weighted.weights["a"] > weighted.weights["b"]
    assert sum(weighted.weights.values()) == pytest.approx(1.0)


def test_drift_ignores_performance_metrics_until_sample_floor():
    early = classify_model_drift(ece=0.3, ece_delta=0.2, median_clv_pct=-5, resolved_samples=99)
    assert early.severity == "ok"

    critical = classify_model_drift(
        psi=0.26,
        ece=0.13,
        ece_delta=0.05,
        fallback_rate=0.06,
        median_clv_pct=-2,
        resolved_samples=100,
    )
    assert critical.severity == "critical"
    assert "psi_critical" in critical.reasons
