"""Immutable feature specifications and backend-owned model artifact manifests."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ModelFeatureSet(Base):
    """A versioned, canonical feature-set specification used by model artifacts."""

    __tablename__ = "model_feature_sets"
    __table_args__ = (
        UniqueConstraint("feature_key", "version", "spec_fingerprint", name="uq_model_feature_sets_identity"),
        CheckConstraint("length(spec_fingerprint) = 64", name="ck_model_feature_sets_fingerprint_length"),
        Index("ix_model_feature_sets_key_version", "feature_key", "version"),
        Index("ix_model_feature_sets_fingerprint", "spec_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feature_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    spec_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    spec_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelArtifact(Base):
    """A digest-only manifest for a complete model-pipeline output.

    Artifact bytes remain in backend-controlled object storage; this table stores
    only immutable identity, provenance, and completeness evidence.
    """

    __tablename__ = "model_artifacts"
    __table_args__ = (
        UniqueConstraint("artifact_key", name="uq_model_artifacts_key"),
        CheckConstraint(
            "artifact_kind IN ('feature_matrix', 'training_manifest', 'backtest_manifest', 'prediction_manifest')",
            name="ck_model_artifacts_kind",
        ),
        CheckConstraint("state IN ('staged', 'completed', 'failed')", name="ck_model_artifacts_state"),
        CheckConstraint("length(artifact_key) = 64", name="ck_model_artifacts_key_length"),
        CheckConstraint("length(artifact_digest) = 64", name="ck_model_artifacts_digest_length"),
        CheckConstraint(
            "length(runtime_dependency_fingerprint) = 64",
            name="ck_model_artifacts_runtime_fingerprint_length",
        ),
        CheckConstraint(
            "expected_row_count >= 0 AND written_row_count >= 0 "
            "AND expected_output_count >= 0 AND written_output_count >= 0",
            name="ck_model_artifacts_nonnegative_counts",
        ),
        CheckConstraint(
            "state != 'completed' OR "
            "(expected_row_count = written_row_count AND expected_output_count = written_output_count)",
            name="ck_model_artifacts_completed_complete",
        ),
        Index("ix_model_artifacts_model_version_state", "model_version_id", "state"),
        Index("ix_model_artifacts_digest", "artifact_digest"),
        Index("ix_model_artifacts_source_generation", "source_generation_id"),
        Index("ix_model_artifacts_feature_set", "feature_set_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_key: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False)
    source_generation_id: Mapped[int] = mapped_column(
        ForeignKey("provider_dataset_generations.id", ondelete="RESTRICT"), nullable=False
    )
    feature_set_id: Mapped[int] = mapped_column(
        ForeignKey("model_feature_sets.id", ondelete="RESTRICT"), nullable=False
    )
    artifact_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="staged")
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    runtime_dependency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    written_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_output_count: Mapped[int] = mapped_column(Integer, nullable=False)
    written_output_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
