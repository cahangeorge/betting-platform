"""add ticket-leg prediction run snapshot foreign key

Revision ID: 038
Revises: 037
"""

from collections.abc import Sequence

from alembic import op

revision = "038"
down_revision: str | None = "037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The 037 trigger protects governed records.  This FK closes the
    # concurrent insert/delete gap for every retained snapshot: PostgreSQL's
    # FK key-share lock prevents a run deletion from racing a new leg insert.
    # Keep this constraint NOT VALID until the known legacy orphan snapshot is
    # separately quarantined. PostgreSQL still enforces all new child writes
    # and all parent deletes, which is the safety property required here.
    # PostgreSQL does not index FK children automatically. Build this first,
    # outside the migration transaction, so parent-delete checks cannot force
    # a table scan and the index build does not block normal ticket writes.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_ticket_legs_prediction_run_id_snapshot",
            "ticket_legs",
            ["prediction_run_id_snapshot"],
            postgresql_concurrently=True,
        )
    op.execute(
        """
        ALTER TABLE ticket_legs
        ADD CONSTRAINT fk_ticket_legs_prediction_run_snapshot
        FOREIGN KEY (prediction_run_id_snapshot)
        REFERENCES prediction_runs (id)
        ON DELETE RESTRICT
        NOT VALID
        """
    )


def downgrade() -> None:
    raise RuntimeError("ticket-leg prediction-run lineage protection is expand-only")
