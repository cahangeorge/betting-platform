"""add durable user-scoped API job creation idempotency

Revision ID: 024
Revises: 023
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "024"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_creation_idempotency",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "scheduled_job_id",
            sa.Integer(),
            sa.ForeignKey("scheduled_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scrape_job_id", sa.Integer(), sa.ForeignKey("scrape_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_job_creation_idempotency_user_operation_key",
        ),
    )
    op.create_index("ix_job_creation_idempotency_scheduled_job_id", "job_creation_idempotency", ["scheduled_job_id"])
    op.create_index("ix_job_creation_idempotency_scrape_job_id", "job_creation_idempotency", ["scrape_job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_creation_idempotency_scrape_job_id", table_name="job_creation_idempotency")
    op.drop_index("ix_job_creation_idempotency_scheduled_job_id", table_name="job_creation_idempotency")
    op.drop_table("job_creation_idempotency")
