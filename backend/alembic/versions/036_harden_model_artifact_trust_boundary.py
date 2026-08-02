"""harden model artifact trust boundary

Revision ID: 036
Revises: 035
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "036"
down_revision: str | None = "035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy prediction runs remain valid; v1 pipeline rows must bind the
    # exact completed artifact used to produce their output.
    op.add_column("prediction_runs", sa.Column("model_artifact_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_prediction_runs_model_artifact",
        "prediction_runs",
        "model_artifacts",
        ["model_artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_prediction_runs_model_artifact_id", "prediction_runs", ["model_artifact_id"])
    op.drop_constraint("ck_prediction_runs_p4_lineage_complete", "prediction_runs", type_="check")
    op.create_check_constraint(
        "ck_prediction_runs_p4_lineage_complete",
        "prediction_runs",
        "pipeline_contract_version IS NULL OR pipeline_contract_version != 'penaltyblog-model-pipeline/v1' OR "
        "(model_version_id IS NOT NULL AND model_artifact_id IS NOT NULL AND source_generation_id IS NOT NULL "
        "AND forecast_at IS NOT NULL AND output_fingerprint IS NOT NULL AND strategy_config_hash IS NOT NULL "
        "AND training_data_fingerprint IS NOT NULL)",
    )

    op.execute(
        """
        CREATE FUNCTION enforce_model_artifact_immutability()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.state <> 'staged' THEN
                    RAISE EXCEPTION 'terminal model artifacts are immutable and cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;

            -- A staged artifact may be safely written or explicitly terminalized.
            -- Completed and failed rows are audit records, not mutable work items.
            IF OLD.state <> 'staged' THEN
                RAISE EXCEPTION 'completed or failed model artifacts are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_model_artifacts_immutable
        BEFORE UPDATE OR DELETE ON model_artifacts
        FOR EACH ROW EXECUTE FUNCTION enforce_model_artifact_immutability();
        """
    )


def downgrade() -> None:
    raise RuntimeError("model artifact trust-boundary migration is expand-only; destructive downgrade is not supported")
