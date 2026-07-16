"""add ticket batch prediction lineage and generation report

Revision ID: 013
Revises: 012
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ticket_batches") as batch_op:
        batch_op.add_column(sa.Column("source_prediction_run_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("generation_report", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_ticket_batches_source_prediction_run_id",
            "prediction_runs",
            ["source_prediction_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_ticket_batches_source_prediction_run_id", ["source_prediction_run_id"])


def downgrade() -> None:
    with op.batch_alter_table("ticket_batches") as batch_op:
        batch_op.drop_index("ix_ticket_batches_source_prediction_run_id")
        batch_op.drop_constraint("fk_ticket_batches_source_prediction_run_id", type_="foreignkey")
        batch_op.drop_column("generation_report")
        batch_op.drop_column("source_prediction_run_id")
