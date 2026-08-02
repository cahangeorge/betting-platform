"""add generic provider-backed odds quote contract

Revision ID: 039
Revises: 038
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "039"
down_revision: str | None = "038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # All additions are nullable: pre-contract snapshots are intentionally
    # retained without fabricated provider provenance.
    op.add_column("odds_snapshots", sa.Column("provider_observation_id", sa.Integer(), nullable=True))
    op.add_column("odds_snapshots", sa.Column("contract_version", sa.String(length=32), nullable=True))
    op.add_column("odds_snapshots", sa.Column("payload_digest", sa.String(length=64), nullable=True))
    op.add_column("odds_snapshots", sa.Column("mapping_version", sa.String(length=128), nullable=True))
    op.create_foreign_key(
        "fk_odds_snapshots_provider_observation",
        "odds_snapshots",
        "provider_observations",
        ["provider_observation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_odds_snapshots_provider_observation_id", "odds_snapshots", ["provider_observation_id"])
    op.create_table(
        "odds_quotes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "odds_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("odds_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("bookmaker_key", sa.String(length=128), nullable=False),
        sa.Column("market_key", sa.String(length=128), nullable=False),
        sa.Column("selection_key", sa.String(length=255), nullable=False),
        sa.Column("identity_digest", sa.String(length=64), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("line", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("price > 1", name="ck_odds_quotes_price"),
        sa.UniqueConstraint("odds_snapshot_id", "identity_digest", name="uq_odds_quotes_snapshot_identity"),
    )
    op.create_index("ix_odds_quotes_snapshot_id", "odds_quotes", ["odds_snapshot_id"])
    op.create_index("ix_odds_quotes_market", "odds_quotes", ["market_key", "selection_key"])


def downgrade() -> None:
    raise RuntimeError("generic odds quote contract is expand-only")
