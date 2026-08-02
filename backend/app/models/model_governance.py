from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'active', 'retired', 'legacy_unversioned')",
            name="ck_model_versions_status",
        ),
        UniqueConstraint(
            "model_key",
            "version",
            "strategy_config_hash",
            "training_data_fingerprint",
            name="uq_model_versions_identity",
        ),
        Index("ix_model_versions_model_key_status", "model_key", "status"),
        Index("ix_model_versions_training_fingerprint", "training_data_fingerprint"),
        Index("ix_model_versions_feature_set", "feature_set_id"),
        CheckConstraint(
            "runtime_dependency_fingerprint IS NULL OR length(runtime_dependency_fingerprint) = 64",
            name="ck_model_versions_runtime_fingerprint_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    build_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feature_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_feature_sets.id", ondelete="SET NULL"), nullable=True
    )
    feature_schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    training_data_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    training_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    runtime_dependency_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"
    __table_args__ = (
        CheckConstraint("evaluation_kind IN ('walk_forward', 'paper')", name="ck_model_evaluations_kind"),
        CheckConstraint(
            "status IN ('pending', 'running', 'passed', 'failed', 'insufficient_evidence')",
            name="ck_model_evaluations_status",
        ),
        CheckConstraint("sample_size >= 0 AND resolved_count >= 0", name="ck_model_evaluations_counts"),
        Index("ix_model_evaluations_version_scope", "model_version_id", "scope_key", "created_at"),
        Index("ix_model_evaluations_status", "status"),
        CheckConstraint(
            "evaluation_fingerprint IS NULL OR length(evaluation_fingerprint) = 64",
            name="ck_model_evaluations_fingerprint_length",
        ),
        CheckConstraint(
            "pipeline_contract_version IS NULL OR pipeline_contract_version != 'penaltyblog-model-pipeline/v1' "
            "OR evaluation_fingerprint IS NOT NULL",
            name="ck_model_evaluations_p4_fingerprint_required",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    evaluation_kind: Mapped[str] = mapped_column(String(32), default="walk_forward", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    pipeline_contract_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evaluation_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_folds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coverage: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    leakage_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quote_cutoff_violations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_reasons: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelEvaluationFold(Base):
    __tablename__ = "model_evaluation_folds"
    __table_args__ = (
        CheckConstraint("fold_number >= 0", name="ck_model_evaluation_folds_number"),
        CheckConstraint(
            "training_count >= 0 AND test_count >= 0 AND resolved_count >= 0",
            name="ck_model_evaluation_folds_counts",
        ),
        UniqueConstraint("evaluation_id", "fold_number", name="uq_model_evaluation_folds_number"),
        Index("ix_model_evaluation_folds_evaluation_id", "evaluation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("model_evaluations.id", ondelete="CASCADE"), nullable=False)
    feature_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="RESTRICT"), nullable=True
    )
    fold_number: Mapped[int] = mapped_column(Integer, nullable=False)
    training_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    training_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    test_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    test_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_count: Mapped[int] = mapped_column(Integer, nullable=False)
    test_count: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelEvaluationPrediction(Base):
    __tablename__ = "model_evaluation_predictions"
    __table_args__ = (
        CheckConstraint(
            "predicted_probability >= 0 AND predicted_probability <= 1",
            name="ck_model_evaluation_predictions_probability",
        ),
        CheckConstraint("fair_odds > 1", name="ck_model_evaluation_predictions_fair_odds"),
        UniqueConstraint("fold_id", "match_id", "market", "selection", name="uq_model_evaluation_predictions_target"),
        Index("ix_model_evaluation_predictions_fold_id", "fold_id"),
        Index("ix_model_evaluation_predictions_match_market", "match_id", "market"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fold_id: Mapped[int] = mapped_column(ForeignKey("model_evaluation_folds.id", ondelete="CASCADE"), nullable=False)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    odds_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("odds_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    selection: Mapped[str] = mapped_column(String(50), nullable=False)
    predicted_probability: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    fair_odds: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    quoted_odds: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    quote_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    forecast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_selection: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PredictionOutcome(Base):
    __tablename__ = "prediction_outcomes"
    __table_args__ = (UniqueConstraint("model_prediction_id", name="uq_prediction_outcomes_model_prediction_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_prediction_id: Mapped[int] = mapped_column(
        ForeignKey("model_predictions.id", ondelete="CASCADE"), nullable=False
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actual_selection: Mapped[str] = mapped_column(String(50), nullable=False)
    brier_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    log_loss: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelCertification(Base):
    __tablename__ = "model_certifications"
    __table_args__ = (
        CheckConstraint("certification_type IN ('walk_forward', 'paper')", name="ck_model_certifications_type"),
        CheckConstraint(
            "status IN ('walk_forward_passed', 'paper_collecting', 'certified', 'suspended', 'expired')",
            name="ck_model_certifications_status",
        ),
        CheckConstraint("valid_until > valid_from", name="ck_model_certifications_validity"),
        Index("ix_model_certifications_version_scope_status", "model_version_id", "scope_key", "status"),
        Index("ix_model_certifications_valid_until", "valid_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)
    model_evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("model_evaluations.id", ondelete="RESTRICT"), nullable=False
    )
    certification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelMonitoringSnapshot(Base):
    __tablename__ = "model_monitoring_snapshots"
    __table_args__ = (
        CheckConstraint("sample_size >= 0", name="ck_model_monitoring_snapshots_sample_size"),
        CheckConstraint(
            "severity IN ('healthy', 'warning', 'critical', 'insufficient_evidence')",
            name="ck_model_monitoring_snapshots_severity",
        ),
        CheckConstraint("window_ended_at > window_started_at", name="ck_model_monitoring_snapshots_window"),
        UniqueConstraint(
            "user_id",
            "model_version_id",
            "scope_key",
            "window_ended_at",
            name="uq_model_monitoring_snapshots_tenant_window",
        ),
        Index(
            "ix_model_monitoring_snapshots_user_version_scope",
            "user_id",
            "model_version_id",
            "scope_key",
            "window_ended_at",
        ),
        Index("ix_model_monitoring_snapshots_version_scope", "model_version_id", "scope_key", "window_ended_at"),
        Index("ix_model_monitoring_snapshots_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)
    model_certification_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_certifications.id", ondelete="SET NULL"), nullable=True
    )
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    reasons: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
