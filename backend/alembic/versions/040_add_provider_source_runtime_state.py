"""add generic provider source runtime state

Revision ID: 040
Revises: 039
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "040"
down_revision: str | None = "039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_source_runtime_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("adapter_key", sa.String(length=63), nullable=False),
        sa.Column("source_key", sa.String(length=63), nullable=False),
        sa.Column("quota_limit", sa.Integer(), nullable=True),
        sa.Column("quota_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quota_consumed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_remaining", sa.Integer(), nullable=True),
        sa.Column("circuit_state", sa.String(length=16), nullable=False, server_default="closed"),
        sa.Column("circuit_open_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quota_reserved >= 0", name="ck_provider_source_runtime_state_quota_reserved"),
        sa.CheckConstraint("quota_consumed >= 0", name="ck_provider_source_runtime_state_quota_consumed"),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_provider_source_runtime_state_failures"),
        sa.CheckConstraint(
            "circuit_state IN ('closed', 'open', 'half_open')",
            name="ck_provider_source_runtime_state_circuit",
        ),
        sa.UniqueConstraint("adapter_key", "source_key", name="uq_provider_source_runtime_state_source"),
    )
    op.create_index(
        "ix_provider_source_runtime_state_circuit",
        "provider_source_runtime_states",
        ["circuit_state", "circuit_open_until"],
    )


def downgrade() -> None:
    raise RuntimeError("provider source runtime state is expand-only")
