"""prevent governed prediction run deletion with ticket lineage

Revision ID: 037
Revises: 036
"""

from collections.abc import Sequence

from alembic import op

revision = "037"
down_revision: str | None = "036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A P4 run is the source of immutable fixture/league evidence for ticket
    # legs.  Deleting it would cascade its ModelPrediction rows and turn those
    # legs into apparently-legacy records through SET NULL.  Keep the database
    # boundary authoritative for API, ORM, and direct-SQL deletion paths.
    op.execute(
        """
        CREATE FUNCTION prevent_governed_prediction_run_deletion()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.pipeline_contract_version = 'penaltyblog-model-pipeline/v1'
               AND EXISTS (
                    SELECT 1
                    FROM ticket_legs
                    WHERE prediction_run_id_snapshot = OLD.id
               ) THEN
                RAISE EXCEPTION
                    'governed prediction run cannot be deleted while ticket legs retain its lineage';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_prediction_runs_governed_ticket_lineage
        BEFORE DELETE ON prediction_runs
        FOR EACH ROW EXECUTE FUNCTION prevent_governed_prediction_run_deletion();
        """
    )


def downgrade() -> None:
    raise RuntimeError("governed prediction-run lineage protection is expand-only")
