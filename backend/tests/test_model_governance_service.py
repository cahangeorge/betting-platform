from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.model_governance import (
    ModelEvaluation,
    ModelEvaluationFold,
    ModelEvaluationPrediction,
    ModelMonitoringSnapshot,
)
from app.schemas.model_governance import ModelEvaluationCreateRequest, MonitoringSnapshotCreateRequest
from app.services import model_governance
from app.services.model_governance import (
    assess_prediction_runs_governance,
    calculate_evaluation,
    certification_status_for_evaluation,
    create_evaluation,
    create_monitoring_snapshot,
    governance_gate,
)


def _evaluation_payload(*, fold_count: int = 4, observations_per_fold: int = 100) -> dict:
    origin = datetime(2025, 1, 1, tzinfo=timezone.utc)
    folds = []
    match_id = 1
    for fold_number in range(fold_count):
        test_started_at = origin + timedelta(days=fold_number * 10)
        observations = []
        for index in range(observations_per_fold):
            forecast_at = test_started_at + timedelta(hours=index + 1)
            kickoff_at = forecast_at + timedelta(minutes=30)
            observations.append(
                {
                    "match_id": match_id,
                    "market": "1x2" if match_id % 2 else "btts",
                    "probabilities": {"home": 0.8, "draw": 0.1, "away": 0.1},
                    "actual_selection": "home" if index < observations_per_fold * 0.8 else "draw",
                    "forecast_at": forecast_at,
                    "kickoff_at": kickoff_at,
                    "quoted_odds": 2.1,
                    "quote_observed_at": forecast_at - timedelta(minutes=1),
                }
            )
            match_id += 1
        folds.append(
            {
                "fold_number": fold_number,
                "training_started_at": test_started_at - timedelta(days=365),
                "training_cutoff_at": test_started_at - timedelta(minutes=1),
                "test_started_at": test_started_at,
                "test_ended_at": test_started_at + timedelta(days=7),
                "training_count": 200 + fold_number * 50,
                "eligible_count": observations_per_fold,
                "observations": observations,
            }
        )
    return {
        "model_version": {
            "model_key": "DixonColes",
            "version": "2026.07.16",
            "build_revision": "abc123",
            "engine_version": "penaltyblog-test",
            "feature_schema": {"features": ["home_attack", "away_defence"]},
            "strategy_config": {"xi": 0.0018},
            "training_data": [{"match_id": 1, "updated_at": "2024-12-01T00:00:00Z"}],
            "training_cutoff_at": origin - timedelta(days=1),
        },
        "evaluation_kind": "walk_forward",
        "scope_key": "league=Premier League|markets=1x2,btts",
        "scope": {"league": "Premier League", "markets": ["1x2", "btts"]},
        "baseline_brier_score": 0.6,
        "folds": folds,
    }


def test_walk_forward_evaluation_recalculates_metrics_and_passes_clean_evidence():
    request = ModelEvaluationCreateRequest.model_validate(_evaluation_payload())

    result = calculate_evaluation(request)

    assert result.status == "passed"
    assert result.valid_folds == 4
    assert result.market_samples == {"1x2": 200, "btts": 200}
    assert result.metrics.sample_size == 400
    assert result.metrics.expected_calibration_error == pytest.approx(0.0)
    assert result.brier_skill > 0


def test_walk_forward_evaluation_detects_quote_after_forecast():
    payload = _evaluation_payload()
    first = payload["folds"][0]["observations"][0]
    first["quote_observed_at"] = first["forecast_at"] + timedelta(seconds=1)

    result = calculate_evaluation(ModelEvaluationCreateRequest.model_validate(payload))

    assert result.status == "failed"
    assert result.quote_cutoff_violations == 1
    assert "quote_after_cutoff_detected" in result.reasons


def test_certification_is_staged_and_legacy_models_remain_analysis_only():
    evaluation = SimpleNamespace(
        evaluation_kind="walk_forward",
        status="passed",
        metrics={},
        resolved_count=400,
    )
    version = SimpleNamespace(status="candidate")
    assert certification_status_for_evaluation(evaluation, version) == "walk_forward_passed"

    legacy = SimpleNamespace(status="legacy_unversioned")
    with pytest.raises(ValueError, match="analysis-only"):
        certification_status_for_evaluation(evaluation, legacy)

    gate = governance_gate(model_version=legacy, certification=None)
    assert gate.analysis_allowed is True
    assert gate.manual_paper_allowed is False
    assert gate.scheduled_paper_allowed is False


def test_scheduled_paper_requires_full_certification():
    now = datetime.now(timezone.utc)
    version = SimpleNamespace(status="active")
    collecting = SimpleNamespace(
        id=10,
        status="paper_collecting",
        valid_until=now + timedelta(days=10),
    )
    certified = SimpleNamespace(
        id=11,
        status="certified",
        valid_until=now + timedelta(days=10),
    )

    collecting_gate = governance_gate(model_version=version, certification=collecting, now=now)
    assert collecting_gate.manual_paper_allowed is True
    assert collecting_gate.scheduled_paper_allowed is False

    certified_gate = governance_gate(model_version=version, certification=certified, now=now)
    assert certified_gate.manual_paper_allowed is True
    assert certified_gate.scheduled_paper_allowed is True


@pytest.mark.asyncio
async def test_create_evaluation_persists_version_folds_and_observations():
    class _NoRow:
        @staticmethod
        def scalar_one_or_none():
            return None

    class _RecordingSession:
        def __init__(self):
            self.added = []
            self.next_id = 1

        async def execute(self, _statement):
            return _NoRow()

        def add(self, value):
            if hasattr(value, "id") and value.id is None:
                value.id = self.next_id
                self.next_id += 1
            self.added.append(value)

        async def flush(self):
            return None

    db = _RecordingSession()
    payload = _evaluation_payload(fold_count=1, observations_per_fold=3)
    request = ModelEvaluationCreateRequest.model_validate(payload)
    evaluation, model_version, folds = await create_evaluation(db, user_id=7, request=request)

    assert evaluation.status == "insufficient_evidence"
    assert model_version.training_data_fingerprint
    assert len(folds) == 1
    assert sum(isinstance(item, ModelEvaluation) for item in db.added) == 1
    assert sum(isinstance(item, ModelEvaluationFold) for item in db.added) == 1
    assert sum(isinstance(item, ModelEvaluationPrediction) for item in db.added) == 3


@pytest.mark.asyncio
async def test_monitoring_snapshot_is_tenant_owned_and_auto_links_active_certification(monkeypatch):
    now = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
    version = SimpleNamespace(id=9)
    certification = SimpleNamespace(id=12, model_version_id=9, scope_key="league=test", status="certified")

    async def fake_get_owned_model_version(*_args, **_kwargs):
        return version

    async def fake_latest_certification(*_args, **kwargs):
        assert kwargs == {
            "model_version_id": 9,
            "user_id": 7,
            "scope_key": "league=test",
            "active_at": now,
        }
        return certification

    class _Session:
        def __init__(self):
            self.added = []

        def add(self, value):
            value.id = 31
            self.added.append(value)

        async def flush(self):
            return None

    monkeypatch.setattr(model_governance, "get_owned_model_version", fake_get_owned_model_version)
    monkeypatch.setattr(model_governance, "get_latest_owned_certification", fake_latest_certification)
    db = _Session()
    request = MonitoringSnapshotCreateRequest(
        model_version_id=9,
        scope_key="league=test",
        window_started_at=now - timedelta(days=7),
        window_ended_at=now,
        sample_size=20,
    )

    snapshot = await create_monitoring_snapshot(db, user_id=7, request=request)

    assert isinstance(snapshot, ModelMonitoringSnapshot)
    assert snapshot.user_id == 7
    assert snapshot.model_certification_id == 12
    assert snapshot.severity == "insufficient_evidence"


@pytest.mark.asyncio
async def test_auto_linked_certification_is_suspended_after_consecutive_critical_drift(monkeypatch):
    now = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
    certification = SimpleNamespace(
        id=12,
        model_version_id=9,
        scope_key="league=test",
        status="certified",
        suspended_at=None,
        suspension_reason=None,
    )

    async def fake_get_owned_model_version(*_args, **_kwargs):
        return SimpleNamespace(id=9)

    async def fake_latest_certification(*_args, **_kwargs):
        return certification

    class _CriticalResult:
        def scalars(self):
            return self

        def all(self):
            return ["critical", "critical"]

    class _Session:
        def add(self, value):
            value.id = 31

        async def flush(self):
            return None

        async def execute(self, _statement):
            return _CriticalResult()

    monkeypatch.setattr(model_governance, "get_owned_model_version", fake_get_owned_model_version)
    monkeypatch.setattr(model_governance, "get_latest_owned_certification", fake_latest_certification)
    request = MonitoringSnapshotCreateRequest(
        model_version_id=9,
        scope_key="league=test",
        window_started_at=now - timedelta(days=7),
        window_ended_at=now,
        sample_size=100,
        psi=0.26,
        expected_calibration_error=0.13,
        ece_delta=0.05,
        fallback_rate=0.06,
        median_clv_pct=-2,
    )

    snapshot = await create_monitoring_snapshot(_Session(), user_id=7, request=request)

    assert snapshot.model_certification_id == 12
    assert snapshot.severity == "critical"
    assert certification.status == "suspended"
    assert certification.suspension_reason == "two_consecutive_critical_monitoring_windows"


@pytest.mark.asyncio
async def test_versioned_run_gate_distinguishes_manual_scheduled_and_critical_drift(monkeypatch):
    now = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
    version = SimpleNamespace(
        id=9,
        status="active",
        strategy_config_hash="strategy-hash",
        training_data_fingerprint="training-hash",
    )
    evaluation = SimpleNamespace(id=21)
    certification = SimpleNamespace(
        id=12,
        status="paper_collecting",
        valid_until=now + timedelta(days=7),
    )
    healthy = SimpleNamespace(severity="healthy")
    staged_gate = governance_gate(model_version=version, certification=certification, now=now)
    evidence = (version, evaluation, certification, healthy, staged_gate)

    async def fake_governance_evidence(*_args, **_kwargs):
        return evidence

    monkeypatch.setattr(model_governance, "governance_evidence", fake_governance_evidence)
    run = SimpleNamespace(
        id=101,
        model_version_id=9,
        strategy_config_hash="strategy-hash",
        training_data_fingerprint="training-hash",
    )

    manual = await assess_prediction_runs_governance(
        object(), user_id=7, runs=[run], automated=False, now=now
    )
    scheduled = await assess_prediction_runs_governance(
        object(), user_id=7, runs=[run], automated=True, now=now
    )

    assert manual["allowed"] is True
    assert manual["model_evaluation_ids"] == [21]
    assert scheduled["allowed"] is False
    assert scheduled["runs"][0]["reason"] == "staged_manual_paper_only"

    critical_gate = staged_gate.model_copy(
        update={
            "manual_paper_allowed": False,
            "scheduled_paper_allowed": False,
            "reason": "critical_monitoring_drift",
        }
    )
    evidence = (version, evaluation, certification, SimpleNamespace(severity="critical"), critical_gate)
    critical = await assess_prediction_runs_governance(
        object(), user_id=7, runs=[run], automated=False, now=now
    )
    assert critical["allowed"] is False
    assert critical["runs"][0]["reason"] == "critical_monitoring_drift"


@pytest.mark.asyncio
async def test_versioned_run_gate_rejects_immutable_fingerprint_mismatch(monkeypatch):
    now = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
    version = SimpleNamespace(
        id=9,
        status="active",
        strategy_config_hash="expected",
        training_data_fingerprint="training",
    )
    certification = SimpleNamespace(id=12, status="certified", valid_until=now + timedelta(days=7))
    evidence = (
        version,
        SimpleNamespace(id=21),
        certification,
        SimpleNamespace(severity="healthy"),
        governance_gate(model_version=version, certification=certification, now=now),
    )

    async def fake_governance_evidence(*_args, **_kwargs):
        return evidence

    monkeypatch.setattr(model_governance, "governance_evidence", fake_governance_evidence)
    run = SimpleNamespace(
        id=101,
        model_version_id=9,
        strategy_config_hash="tampered",
        training_data_fingerprint="training",
    )

    result = await assess_prediction_runs_governance(
        object(), user_id=7, runs=[run], automated=False, now=now
    )

    assert result["allowed"] is False
    assert result["runs"][0]["reason"] == "run_model_version_fingerprint_mismatch"
