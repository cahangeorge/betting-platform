from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ModelVersionStatus = Literal["candidate", "active", "retired", "legacy_unversioned"]
EvaluationKind = Literal["walk_forward", "paper"]
EvaluationStatus = Literal["pending", "running", "passed", "failed", "insufficient_evidence"]
CertificationStatus = Literal[
    "walk_forward_passed",
    "paper_collecting",
    "certified",
    "suspended",
    "expired",
]
MonitoringSeverity = Literal["healthy", "warning", "critical", "insufficient_evidence"]


class ModelVersionInput(BaseModel):
    model_key: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    build_revision: str = Field(min_length=1, max_length=100)
    engine_version: str | None = Field(default=None, max_length=100)
    feature_schema: dict[str, Any] | list[Any]
    strategy_config: dict[str, Any]
    training_data: list[dict[str, Any]] = Field(min_length=1)
    training_cutoff_at: datetime
    status: ModelVersionStatus = "candidate"
    metadata: dict[str, Any] | None = None


class EvaluationObservationInput(BaseModel):
    match_id: int = Field(gt=0)
    market: str = Field(min_length=1, max_length=50)
    probabilities: dict[str, float] = Field(min_length=2)
    actual_selection: str = Field(min_length=1, max_length=50)
    forecast_at: datetime
    kickoff_at: datetime
    quoted_odds: float | None = Field(default=None, gt=1)
    quote_observed_at: datetime | None = None
    odds_snapshot_id: int | None = Field(default=None, gt=0)
    fallback: bool = False

    @model_validator(mode="after")
    def validate_probabilities(self) -> EvaluationObservationInput:
        if self.actual_selection not in self.probabilities:
            raise ValueError("actual_selection must be present in probabilities")
        if any(value < 0 or value >= 1 for value in self.probabilities.values()):
            raise ValueError("probabilities must be in the [0, 1) interval")
        if sum(self.probabilities.values()) <= 0:
            raise ValueError("probabilities must have positive mass")
        return self


class EvaluationFoldInput(BaseModel):
    fold_number: int = Field(ge=0)
    training_started_at: datetime | None = None
    training_cutoff_at: datetime
    test_started_at: datetime
    test_ended_at: datetime
    training_count: int = Field(ge=0)
    eligible_count: int = Field(gt=0)
    observations: list[EvaluationObservationInput] = Field(min_length=1)


class ModelEvaluationCreateRequest(BaseModel):
    model_version: ModelVersionInput
    evaluation_kind: EvaluationKind = "walk_forward"
    scope_key: str = Field(min_length=1, max_length=255)
    scope: dict[str, Any] = Field(default_factory=dict)
    baseline_brier_score: float = Field(gt=0)
    parameters: dict[str, Any] = Field(default_factory=dict)
    folds: list[EvaluationFoldInput] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_fold_numbers(self) -> ModelEvaluationCreateRequest:
        numbers = [fold.fold_number for fold in self.folds]
        if len(set(numbers)) != len(numbers):
            raise ValueError("fold_number must be unique within an evaluation")
        return self


class ModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_key: str
    version: str
    build_revision: str
    engine_version: str | None = None
    feature_schema_hash: str
    strategy_config_hash: str
    training_data_fingerprint: str
    training_cutoff_at: datetime
    status: ModelVersionStatus
    metadata_json: dict[str, Any] | None = None
    created_at: datetime


class ModelEvaluationFoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fold_number: int
    training_started_at: datetime | None = None
    training_cutoff_at: datetime
    test_started_at: datetime
    test_ended_at: datetime
    training_count: int
    test_count: int
    resolved_count: int
    metrics: dict[str, Any] | None = None
    created_at: datetime


class ModelEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_version_id: int
    user_id: int | None = None
    evaluation_kind: EvaluationKind
    status: EvaluationStatus
    scope_key: str
    scope_json: dict[str, Any] | None = None
    parameters: dict[str, Any]
    sample_size: int
    resolved_count: int
    valid_folds: int
    coverage: float | None = None
    metrics: dict[str, Any] | None = None
    leakage_detected: bool
    quote_cutoff_violations: int
    fallback_count: int
    failure_reasons: list[str] | dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class ModelEvaluationDetailResponse(ModelEvaluationResponse):
    model_version: ModelVersionResponse
    folds: list[ModelEvaluationFoldResponse]


class ModelEvaluationListResponse(BaseModel):
    items: list[ModelEvaluationResponse]
    total: int


class CertificationCreateRequest(BaseModel):
    evaluation_id: int = Field(gt=0)
    validity_days: int = Field(default=90, ge=1, le=90)


class ModelCertificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_version_id: int
    model_evaluation_id: int
    certification_type: EvaluationKind
    status: CertificationStatus
    scope_key: str
    evidence: dict[str, Any]
    valid_from: datetime
    valid_until: datetime
    suspended_at: datetime | None = None
    suspension_reason: str | None = None
    created_at: datetime


class ModelCertificationListResponse(BaseModel):
    items: list[ModelCertificationResponse]
    total: int


class MonitoringSnapshotCreateRequest(BaseModel):
    model_version_id: int = Field(gt=0)
    model_certification_id: int | None = Field(default=None, gt=0)
    scope_key: str = Field(min_length=1, max_length=255)
    window_started_at: datetime
    window_ended_at: datetime
    sample_size: int = Field(ge=0)
    psi: float | None = Field(default=None, ge=0)
    expected_calibration_error: float | None = Field(default=None, ge=0)
    ece_delta: float | None = None
    brier_relative_degradation: float | None = None
    fallback_rate: float | None = Field(default=None, ge=0, le=1)
    median_clv_pct: float | None = None
    extra_metrics: dict[str, Any] = Field(default_factory=dict)


class ModelMonitoringSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    model_version_id: int
    model_certification_id: int | None = None
    scope_key: str
    window_started_at: datetime
    window_ended_at: datetime
    sample_size: int
    severity: MonitoringSeverity
    metrics: dict[str, Any]
    reasons: list[str] | dict[str, Any] | None = None
    created_at: datetime


class ModelMonitoringListResponse(BaseModel):
    items: list[ModelMonitoringSnapshotResponse]
    total: int


class GovernanceGateResponse(BaseModel):
    analysis_allowed: bool
    manual_paper_allowed: bool
    scheduled_paper_allowed: bool
    reason: str
    certification_status: CertificationStatus | None = None
    certification_id: int | None = None


class ModelGovernanceEvidenceResponse(BaseModel):
    model_version: ModelVersionResponse
    latest_evaluation: ModelEvaluationResponse | None = None
    latest_certification: ModelCertificationResponse | None = None
    latest_monitoring: ModelMonitoringSnapshotResponse | None = None
    gate: GovernanceGateResponse
