"""add_scheduled_job_runs

Revision ID: 006
Revises: 005
Create Date: 2026-07-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_job_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheduled_job_id", sa.Integer(), nullable=True),
        sa.Column("scrape_job_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("taskiq_task_id", sa.String(length=255), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("artifacts", JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=50), nullable=False, server_default="scheduler"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["scheduled_job_id"], ["scheduled_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scrape_job_id"], ["scrape_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_job_runs_scheduled_job_id", "scheduled_job_runs", ["scheduled_job_id"])
    op.create_index("ix_scheduled_job_runs_scrape_job_id", "scheduled_job_runs", ["scrape_job_id"])
    op.create_index("ix_scheduled_job_runs_status", "scheduled_job_runs", ["status"])
    op.create_index(
        "uq_scheduled_job_runs_active_scrape_task",
        "scheduled_job_runs",
        ["task_type", "scrape_job_id"],
        unique=True,
        postgresql_where=sa.text("scrape_job_id IS NOT NULL AND status IN ('queued', 'running')"),
        sqlite_where=sa.text("scrape_job_id IS NOT NULL AND status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_scheduled_job_runs_job_created",
        "scheduled_job_runs",
        ["scheduled_job_id", "created_at"],
    )
    op.create_index("ix_scheduled_jobs_enabled_next_run", "scheduled_jobs", ["enabled", "next_run"])
    op.create_index("ix_scrape_jobs_status_created", "scrape_jobs", ["status", "created_at"])
    op.create_index("ix_scrape_job_logs_job_created", "scrape_job_logs", ["job_id", "created_at"])
    op.create_index("ix_prediction_runs_user_status_created", "prediction_runs", ["user_id", "status", "created_at"])
    op.create_index("ix_model_predictions_run_market", "model_predictions", ["run_id", "market"])
    op.create_index("ix_model_predictions_match_market", "model_predictions", ["match_id", "market"])
    op.create_index("ix_tickets_user_status_created", "tickets", ["user_id", "status", "created_at"])
    op.create_index("ix_ticket_legs_ticket_status", "ticket_legs", ["ticket_id", "status"])
    op.create_index("ix_ticket_legs_model_prediction_id", "ticket_legs", ["model_prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_ticket_legs_model_prediction_id", table_name="ticket_legs")
    op.drop_index("ix_ticket_legs_ticket_status", table_name="ticket_legs")
    op.drop_index("ix_tickets_user_status_created", table_name="tickets")
    op.drop_index("ix_model_predictions_match_market", table_name="model_predictions")
    op.drop_index("ix_model_predictions_run_market", table_name="model_predictions")
    op.drop_index("ix_prediction_runs_user_status_created", table_name="prediction_runs")
    op.drop_index("ix_scrape_job_logs_job_created", table_name="scrape_job_logs")
    op.drop_index("ix_scrape_jobs_status_created", table_name="scrape_jobs")
    op.drop_index("ix_scheduled_jobs_enabled_next_run", table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_job_runs_job_created", table_name="scheduled_job_runs")
    op.drop_index("uq_scheduled_job_runs_active_scrape_task", table_name="scheduled_job_runs")
    op.drop_index("ix_scheduled_job_runs_status", table_name="scheduled_job_runs")
    op.drop_index("ix_scheduled_job_runs_scrape_job_id", table_name="scheduled_job_runs")
    op.drop_index("ix_scheduled_job_runs_scheduled_job_id", table_name="scheduled_job_runs")
    op.drop_table("scheduled_job_runs")
