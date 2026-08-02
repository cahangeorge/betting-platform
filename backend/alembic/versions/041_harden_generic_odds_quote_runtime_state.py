"""harden generic odds quote and runtime contracts

Revision ID: 041
Revises: 040
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "041"
down_revision: str | None = "040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A single immutable provider observation can materialize at most one
    # canonical snapshot; NULL remains available for retained legacy rows.
    op.create_index(
        "uq_odds_snapshots_provider_observation_id",
        "odds_snapshots",
        ["provider_observation_id"],
        unique=True,
    )
    # Preserve the existing provider bookmaker key; new provider identity
    # fields below are intentionally not fabricated for interim rows.
    op.alter_column("odds_quotes", "bookmaker_key", new_column_name="provider_bookmaker_key")
    op.add_column("odds_quotes", sa.Column("source_quote_id", sa.String(length=255), nullable=True))
    op.add_column("odds_quotes", sa.Column("bookmaker_key", sa.String(length=128), nullable=True))
    op.add_column("odds_quotes", sa.Column("provider_market_key", sa.String(length=128), nullable=True))
    op.add_column(
        "odds_quotes", sa.Column("period_key", sa.String(length=64), nullable=False, server_default="full_time")
    )
    op.add_column("odds_quotes", sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("odds_quotes", sa.Column("status", sa.String(length=16), nullable=False, server_default="active"))
    op.alter_column("odds_quotes", "price", type_=sa.Numeric(precision=18, scale=8))
    op.alter_column("odds_quotes", "line", type_=sa.Numeric(precision=18, scale=8))
    # Do not fabricate provider lineage for any interim row.  A deployment
    # with such rows must explicitly resolve them before accepting this typed
    # contract, rather than silently treating partial data as canonical.
    op.alter_column("odds_quotes", "source_quote_id", nullable=False)
    op.alter_column("odds_quotes", "provider_market_key", nullable=False)
    op.alter_column("odds_quotes", "provider_updated_at", nullable=False)
    op.create_check_constraint("ck_odds_quotes_status", "odds_quotes", "status IN ('active', 'suspended', 'stopped')")
    op.drop_index("ix_odds_quotes_market", table_name="odds_quotes")
    op.create_index("ix_odds_quotes_market", "odds_quotes", ["market_key", "period_key", "selection_key"])

    op.add_column(
        "provider_source_runtime_states",
        sa.Column("quota_window_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("provider_source_runtime_states", sa.Column("quota_window_seconds", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_provider_source_runtime_state_quota_window_seconds",
        "provider_source_runtime_states",
        "quota_window_seconds IS NULL OR quota_window_seconds > 0",
    )


def downgrade() -> None:
    raise RuntimeError("generic odds/runtime hardening is expand-only")
