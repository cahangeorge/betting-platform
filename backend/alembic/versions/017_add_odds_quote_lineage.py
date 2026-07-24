"""add canonical odds snapshots and ticket quote lineage

Revision ID: 017
Revises: 016
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "odds_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=True),
        sa.Column("scrape_job_id", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("quality", sa.String(length=32), nullable=False, server_default="complete"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "quality IN ('complete', 'partial', 'legacy_unknown')",
            name="ck_odds_snapshots_quality",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["scraped_datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scrape_job_id"], ["scrape_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_key", name="uq_odds_snapshots_source_key"),
    )
    op.create_index("ix_odds_snapshots_match_observed", "odds_snapshots", ["match_id", "observed_at"])
    op.create_index("ix_odds_snapshots_dataset_id", "odds_snapshots", ["dataset_id"])
    op.create_index("ix_odds_snapshots_scrape_job_id", "odds_snapshots", ["scrape_job_id"])

    with op.batch_alter_table("odds_entries") as batch_op:
        batch_op.add_column(sa.Column("odds_snapshot_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_odds_entries_odds_snapshot_id",
            "odds_snapshots",
            ["odds_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_odds_entries_odds_snapshot_id", ["odds_snapshot_id"])

    with op.batch_alter_table("model_predictions") as batch_op:
        batch_op.add_column(sa.Column("odds_snapshot_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_model_predictions_odds_snapshot_id",
            "odds_snapshots",
            ["odds_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_model_predictions_odds_snapshot_id", ["odds_snapshot_id"])

    with op.batch_alter_table("execution_intents") as batch_op:
        batch_op.add_column(sa.Column("odds_snapshot_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_execution_intents_odds_snapshot_id",
            "odds_snapshots",
            ["odds_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_execution_intents_odds_snapshot_id", ["odds_snapshot_id"])

    op.create_table(
        "ticket_leg_quote_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_leg_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("odds_entry_id", sa.Integer(), nullable=True),
        sa.Column("odds_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("market", sa.String(length=50), nullable=False),
        sa.Column("selection", sa.String(length=50), nullable=False),
        sa.Column("bookmaker", sa.String(length=100), nullable=True),
        sa.Column("price", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("model_probability", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("market_probability", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("market_probability_method", sa.String(length=50), nullable=True),
        sa.Column("fair_odds", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("probability_edge_pp", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("expected_value", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("expected_value_pct", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.CheckConstraint(
            "stage IN ('generation', 'activation', 'closing_same_book', 'closing_market')",
            name="ck_ticket_leg_quote_snapshots_stage",
        ),
        sa.CheckConstraint("price > 1", name="ck_ticket_leg_quote_snapshots_price"),
        sa.ForeignKeyConstraint(["odds_entry_id"], ["odds_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["odds_snapshot_id"], ["odds_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ticket_leg_id"], ["ticket_legs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_leg_id", "stage", name="uq_ticket_leg_quote_snapshots_leg_stage"),
    )
    op.create_index(
        "ix_ticket_leg_quote_snapshots_snapshot_id",
        "ticket_leg_quote_snapshots",
        ["odds_snapshot_id"],
    )
    op.create_index(
        "ix_ticket_leg_quote_snapshots_recorded_at",
        "ticket_leg_quote_snapshots",
        ["recorded_at"],
    )


def downgrade() -> None:
    op.drop_table("ticket_leg_quote_snapshots")

    with op.batch_alter_table("execution_intents") as batch_op:
        batch_op.drop_index("ix_execution_intents_odds_snapshot_id")
        batch_op.drop_constraint("fk_execution_intents_odds_snapshot_id", type_="foreignkey")
        batch_op.drop_column("odds_snapshot_id")

    with op.batch_alter_table("model_predictions") as batch_op:
        batch_op.drop_index("ix_model_predictions_odds_snapshot_id")
        batch_op.drop_constraint("fk_model_predictions_odds_snapshot_id", type_="foreignkey")
        batch_op.drop_column("odds_snapshot_id")

    with op.batch_alter_table("odds_entries") as batch_op:
        batch_op.drop_index("ix_odds_entries_odds_snapshot_id")
        batch_op.drop_constraint("fk_odds_entries_odds_snapshot_id", type_="foreignkey")
        batch_op.drop_column("odds_snapshot_id")

    op.drop_table("odds_snapshots")
