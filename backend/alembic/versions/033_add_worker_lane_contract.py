"""add durable provider worker lane and fencing contract

Revision ID: 033
Revises: 032
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "033"
down_revision: str | None = "032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LANES = "'control', 'provider-http', 'provider-browser', 'model-cpu'"
_CONTRACT = "legacy-control/v0"


def upgrade() -> None:
    # Defaults make this an expand-only migration: existing durable history is
    # legacy control work and remains publishable without a queue rewrite.
    op.add_column(
        "scheduled_job_runs",
        sa.Column("queue_lane", sa.String(length=32), nullable=False, server_default="control"),
    )
    op.add_column(
        "scheduled_job_runs",
        sa.Column("queue_contract_version", sa.String(length=32), nullable=False, server_default=_CONTRACT),
    )
    op.add_column("scheduled_job_runs", sa.Column("execution_token", sa.String(length=64), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("queue_wait_ms", sa.Integer(), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("peak_rss_bytes", sa.BigInteger(), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("peak_pid_count", sa.Integer(), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("failure_kind", sa.String(length=64), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("retry_disposition", sa.String(length=32), nullable=True))
    op.add_column("scheduled_job_runs", sa.Column("metrics", sa.JSON(), nullable=True))
    op.create_check_constraint("ck_scheduled_job_runs_queue_lane", "scheduled_job_runs", f"queue_lane IN ({_LANES})")
    op.create_check_constraint(
        "ck_scheduled_job_runs_queue_wait_nonnegative",
        "scheduled_job_runs",
        "queue_wait_ms IS NULL OR queue_wait_ms >= 0",
    )
    op.create_check_constraint(
        "ck_scheduled_job_runs_peak_rss_nonnegative",
        "scheduled_job_runs",
        "peak_rss_bytes IS NULL OR peak_rss_bytes >= 0",
    )
    op.create_check_constraint(
        "ck_scheduled_job_runs_peak_pid_nonnegative",
        "scheduled_job_runs",
        "peak_pid_count IS NULL OR peak_pid_count >= 0",
    )
    op.create_unique_constraint(
        "uq_scheduled_job_runs_id_lane_contract",
        "scheduled_job_runs",
        ["id", "queue_lane", "queue_contract_version"],
    )
    op.create_index(
        "ix_scheduled_job_runs_lane_status_queued",
        "scheduled_job_runs",
        ["queue_lane", "status", "queued_at"],
    )

    op.add_column(
        "task_outbox", sa.Column("queue_lane", sa.String(length=32), nullable=False, server_default="control")
    )
    op.add_column(
        "task_outbox",
        sa.Column("queue_contract_version", sa.String(length=32), nullable=False, server_default=_CONTRACT),
    )
    op.add_column("task_outbox", sa.Column("delivery_generation", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_task_outbox_queue_lane", "task_outbox", f"queue_lane IN ({_LANES})")
    op.create_check_constraint("ck_task_outbox_delivery_generation", "task_outbox", "delivery_generation >= 1")
    op.create_index("ix_task_outbox_lane_pending", "task_outbox", ["queue_lane", "status", "available_at"])
    op.create_foreign_key(
        "fk_task_outbox_run_lane_contract",
        "task_outbox",
        "scheduled_job_runs",
        ["run_id", "queue_lane", "queue_contract_version"],
        ["id", "queue_lane", "queue_contract_version"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    raise RuntimeError("worker lane contract migration is expand-only; destructive downgrade is not supported")
