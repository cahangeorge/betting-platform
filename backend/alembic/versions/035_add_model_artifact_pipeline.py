"""add model artifact and feature-set lineage contract

Revision ID: 035
Revises: 034
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "035"
down_revision: str | None = "034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_feature_sets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("feature_key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("spec_json", sa.JSON(), nullable=False),
        sa.Column("spec_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("feature_key", "version", "spec_fingerprint", name="uq_model_feature_sets_identity"),
        sa.CheckConstraint("length(spec_fingerprint) = 64", name="ck_model_feature_sets_fingerprint_length"),
    )
    op.create_index("ix_model_feature_sets_key_version", "model_feature_sets", ["feature_key", "version"])
    op.create_index("ix_model_feature_sets_fingerprint", "model_feature_sets", ["spec_fingerprint"])

    # Existing model versions predate feature-set and runtime-lock provenance.
    op.add_column("model_versions", sa.Column("feature_set_id", sa.Integer(), nullable=True))
    op.add_column("model_versions", sa.Column("runtime_dependency_fingerprint", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_model_versions_feature_set",
        "model_versions",
        "model_feature_sets",
        ["feature_set_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_model_versions_runtime_fingerprint_length",
        "model_versions",
        "runtime_dependency_fingerprint IS NULL OR length(runtime_dependency_fingerprint) = 64",
    )
    op.create_index("ix_model_versions_feature_set", "model_versions", ["feature_set_id"])

    op.create_table(
        "model_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("artifact_key", sa.String(length=64), nullable=False),
        sa.Column("artifact_digest", sa.String(length=64), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column("source_generation_id", sa.Integer(), nullable=False),
        sa.Column("feature_set_id", sa.Integer(), nullable=False),
        sa.Column("artifact_kind", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="staged"),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("runtime_dependency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("expected_row_count", sa.Integer(), nullable=False),
        sa.Column("written_row_count", sa.Integer(), nullable=False),
        sa.Column("expected_output_count", sa.Integer(), nullable=False),
        sa.Column("written_output_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("artifact_key", name="uq_model_artifacts_key"),
        sa.CheckConstraint(
            "artifact_kind IN ('feature_matrix', 'training_manifest', 'backtest_manifest', 'prediction_manifest')",
            name="ck_model_artifacts_kind",
        ),
        sa.CheckConstraint("state IN ('staged', 'completed', 'failed')", name="ck_model_artifacts_state"),
        sa.CheckConstraint("length(artifact_key) = 64", name="ck_model_artifacts_key_length"),
        sa.CheckConstraint("length(artifact_digest) = 64", name="ck_model_artifacts_digest_length"),
        sa.CheckConstraint(
            "length(runtime_dependency_fingerprint) = 64",
            name="ck_model_artifacts_runtime_fingerprint_length",
        ),
        sa.CheckConstraint(
            "expected_row_count >= 0 AND written_row_count >= 0 "
            "AND expected_output_count >= 0 AND written_output_count >= 0",
            name="ck_model_artifacts_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "state != 'completed' OR "
            "(expected_row_count = written_row_count AND expected_output_count = written_output_count)",
            name="ck_model_artifacts_completed_complete",
        ),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_generation_id"], ["provider_dataset_generations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["feature_set_id"], ["model_feature_sets.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_model_artifacts_model_version_state", "model_artifacts", ["model_version_id", "state"])
    op.create_index("ix_model_artifacts_digest", "model_artifacts", ["artifact_digest"])
    op.create_index("ix_model_artifacts_source_generation", "model_artifacts", ["source_generation_id"])
    op.create_index("ix_model_artifacts_feature_set", "model_artifacts", ["feature_set_id"])
    op.execute(
        """
        CREATE FUNCTION enforce_model_artifact_published_generation()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM provider_dataset_generations
                WHERE id = NEW.source_generation_id AND state = 'published'
            ) THEN
                RAISE EXCEPTION 'model artifacts require a published provider dataset generation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.add_column("prediction_runs", sa.Column("pipeline_contract_version", sa.String(length=64), nullable=True))
    op.add_column("prediction_runs", sa.Column("source_generation_id", sa.Integer(), nullable=True))
    op.add_column("prediction_runs", sa.Column("forecast_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prediction_runs", sa.Column("output_fingerprint", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_prediction_runs_source_generation",
        "prediction_runs",
        "provider_dataset_generations",
        ["source_generation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_prediction_runs_source_generation_id", "prediction_runs", ["source_generation_id"])
    op.create_check_constraint(
        "ck_prediction_runs_output_fingerprint_length",
        "prediction_runs",
        "output_fingerprint IS NULL OR length(output_fingerprint) = 64",
    )
    op.create_check_constraint(
        "ck_prediction_runs_p4_lineage_complete",
        "prediction_runs",
        "pipeline_contract_version IS NULL OR pipeline_contract_version != 'penaltyblog-model-pipeline/v1' OR "
        "(model_version_id IS NOT NULL AND source_generation_id IS NOT NULL AND forecast_at IS NOT NULL "
        "AND output_fingerprint IS NOT NULL AND strategy_config_hash IS NOT NULL "
        "AND training_data_fingerprint IS NOT NULL)",
    )

    op.add_column("model_evaluations", sa.Column("pipeline_contract_version", sa.String(length=64), nullable=True))
    op.add_column("model_evaluations", sa.Column("evaluation_fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_model_evaluations_evaluation_fingerprint", "model_evaluations", ["evaluation_fingerprint"])
    op.create_check_constraint(
        "ck_model_evaluations_fingerprint_length",
        "model_evaluations",
        "evaluation_fingerprint IS NULL OR length(evaluation_fingerprint) = 64",
    )
    op.create_check_constraint(
        "ck_model_evaluations_p4_fingerprint_required",
        "model_evaluations",
        "pipeline_contract_version IS NULL OR pipeline_contract_version != 'penaltyblog-model-pipeline/v1' "
        "OR evaluation_fingerprint IS NOT NULL",
    )
    op.add_column("model_evaluation_folds", sa.Column("feature_artifact_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_model_evaluation_folds_feature_artifact",
        "model_evaluation_folds",
        "model_artifacts",
        ["feature_artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("model_evaluation_predictions", sa.Column("forecast_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        CREATE TRIGGER trg_model_artifacts_published_generation
        BEFORE INSERT OR UPDATE OF source_generation_id ON model_artifacts
        FOR EACH ROW EXECUTE FUNCTION enforce_model_artifact_published_generation();
        """
    )


def downgrade() -> None:
    raise RuntimeError("model artifact pipeline migration is expand-only; destructive downgrade is not supported")
