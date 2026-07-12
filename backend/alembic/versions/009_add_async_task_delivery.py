"""add durable async task delivery metadata and outbox

Revision ID: 009
Revises: 008
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheduled_job_runs",
        sa.Column("transport", sa.String(length=32), nullable=False, server_default="inprocess"),
    )
    op.add_column("scheduled_job_runs", sa.Column("transport_task_id", sa.String(length=255), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("scheduled_job_runs", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    # SQLite cannot add a UNIQUE constraint to an existing table without
    # rebuilding it. A unique index provides the same cross-database guarantee.
    op.create_index(
        "uq_scheduled_job_runs_idempotency_key",
        "scheduled_job_runs",
        ["idempotency_key"],
        unique=True,
    )
    op.execute(
        "UPDATE scheduled_job_runs SET transport = 'taskiq', transport_task_id = taskiq_task_id "
        "WHERE taskiq_task_id IS NOT NULL"
    )

    op.create_table(
        "task_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("task_name", sa.String(length=100), nullable=False),
        sa.Column("transport", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("transport_task_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["run_id"], ["scheduled_job_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_task_outbox_run_id"),
    )
    op.create_index("ix_task_outbox_run_id", "task_outbox", ["run_id"])
    op.create_index("ix_task_outbox_status", "task_outbox", ["status"])
    op.create_index("ix_task_outbox_pending", "task_outbox", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_task_outbox_pending", table_name="task_outbox")
    op.drop_index("ix_task_outbox_status", table_name="task_outbox")
    op.drop_index("ix_task_outbox_run_id", table_name="task_outbox")
    op.drop_table("task_outbox")
    op.drop_index("uq_scheduled_job_runs_idempotency_key", table_name="scheduled_job_runs")
    op.drop_column("scheduled_job_runs", "lease_expires_at")
    op.drop_column("scheduled_job_runs", "heartbeat_at")
    op.drop_column("scheduled_job_runs", "next_attempt_at")
    op.drop_column("scheduled_job_runs", "max_attempts")
    op.drop_column("scheduled_job_runs", "idempotency_key")
    op.drop_column("scheduled_job_runs", "transport_task_id")
    op.drop_column("scheduled_job_runs", "transport")
