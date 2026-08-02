"""add durable provider quota reservation ledger

Revision ID: 042
Revises: 041
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "042"
down_revision: str | None = "041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_quota_reservations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("runtime_state_id", sa.Integer(), nullable=False),
        sa.Column("reservation_key", sa.String(length=128), nullable=False),
        sa.Column("adapter_key", sa.String(length=63), nullable=False),
        sa.Column("source_key", sa.String(length=63), nullable=False),
        sa.Column("task_run_id", sa.String(length=128), nullable=True),
        sa.Column("execution_token", sa.String(length=128), nullable=True),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="reserved"),
        sa.Column("quota_window_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("units > 0", name="ck_provider_quota_reservation_units"),
        sa.CheckConstraint(
            "status IN ('reserved', 'charged', 'released', 'uncertain')",
            name="ck_provider_quota_reservation_status",
        ),
        sa.ForeignKeyConstraint(["runtime_state_id"], ["provider_source_runtime_states.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("reservation_key", name="uq_provider_quota_reservation_key"),
    )
    op.create_index(
        "ix_provider_quota_reservation_expiry",
        "provider_quota_reservations",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_provider_quota_reservation_source",
        "provider_quota_reservations",
        ["adapter_key", "source_key", "status"],
    )


def downgrade() -> None:
    raise RuntimeError("provider quota reservation ledger is expand-only")
