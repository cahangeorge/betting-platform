"""guard scheduled ticket generation replay

Revision ID: 023
Revises: 022
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ticket_batches", sa.Column("scheduled_job_run_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_ticket_batches_scheduled_job_run_id_scheduled_job_runs",
        "ticket_batches",
        "scheduled_job_runs",
        ["scheduled_job_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_ticket_batches_scheduled_job_run_id", "ticket_batches", ["scheduled_job_run_id"])
    op.create_unique_constraint(
        "uq_ticket_batches_scheduled_job_run",
        "ticket_batches",
        ["scheduled_job_run_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_ticket_batches_scheduled_job_run", "ticket_batches", type_="unique")
    op.drop_index("ix_ticket_batches_scheduled_job_run_id", table_name="ticket_batches")
    op.drop_constraint(
        "fk_ticket_batches_scheduled_job_run_id_scheduled_job_runs",
        "ticket_batches",
        type_="foreignkey",
    )
    op.drop_column("ticket_batches", "scheduled_job_run_id")
