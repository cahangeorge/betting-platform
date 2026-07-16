"""make ticket quote evidence append-only and revisioned

Revision ID: 021
Revises: 020
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_ticket_leg_quote_snapshots_leg_stage",
        "ticket_leg_quote_snapshots",
        type_="unique",
    )
    op.drop_constraint(
        "ck_ticket_leg_quote_snapshots_stage",
        "ticket_leg_quote_snapshots",
        type_="check",
    )

    op.add_column(
        "ticket_leg_quote_snapshots",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_ticket_leg_quote_snapshots_revision",
        "ticket_leg_quote_snapshots",
        "revision > 0",
    )
    op.create_check_constraint(
        "ck_ticket_leg_quote_snapshots_stage",
        "ticket_leg_quote_snapshots",
        "stage IN ('generation', 'refresh', 'activation', 'closing_same_book', 'closing_market')",
    )
    op.create_unique_constraint(
        "uq_ticket_leg_quote_snapshots_leg_stage_revision",
        "ticket_leg_quote_snapshots",
        ["ticket_leg_id", "stage", "revision"],
    )
    op.drop_index(
        "ix_ticket_leg_quote_snapshots_snapshot_id",
        table_name="ticket_leg_quote_snapshots",
    )
    op.create_index(
        "ix_ticket_leg_quote_snapshots_ticket_leg_id",
        "ticket_leg_quote_snapshots",
        ["ticket_leg_id"],
    )
    op.create_index(
        "ix_ticket_leg_quote_snapshots_odds_snapshot_id",
        "ticket_leg_quote_snapshots",
        ["odds_snapshot_id"],
    )


def downgrade() -> None:
    # Preserve the latest row for every legacy one-row stage before restoring
    # the old uniqueness contract. Refresh evidence has no legacy stage and is
    # intentionally removed only during this explicit downgrade.
    op.execute("DELETE FROM ticket_leg_quote_snapshots WHERE stage = 'refresh'")
    op.execute(
        """
        DELETE FROM ticket_leg_quote_snapshots AS older
        USING ticket_leg_quote_snapshots AS newer
        WHERE older.ticket_leg_id = newer.ticket_leg_id
          AND older.stage = newer.stage
          AND (
            older.revision < newer.revision
            OR (older.revision = newer.revision AND older.id < newer.id)
          )
        """
    )

    op.drop_index(
        "ix_ticket_leg_quote_snapshots_odds_snapshot_id",
        table_name="ticket_leg_quote_snapshots",
    )
    op.drop_index(
        "ix_ticket_leg_quote_snapshots_ticket_leg_id",
        table_name="ticket_leg_quote_snapshots",
    )
    op.create_index(
        "ix_ticket_leg_quote_snapshots_snapshot_id",
        "ticket_leg_quote_snapshots",
        ["odds_snapshot_id"],
    )
    op.drop_constraint(
        "uq_ticket_leg_quote_snapshots_leg_stage_revision",
        "ticket_leg_quote_snapshots",
        type_="unique",
    )
    op.drop_constraint(
        "ck_ticket_leg_quote_snapshots_stage",
        "ticket_leg_quote_snapshots",
        type_="check",
    )
    op.drop_constraint(
        "ck_ticket_leg_quote_snapshots_revision",
        "ticket_leg_quote_snapshots",
        type_="check",
    )
    op.drop_column("ticket_leg_quote_snapshots", "revision")

    op.create_check_constraint(
        "ck_ticket_leg_quote_snapshots_stage",
        "ticket_leg_quote_snapshots",
        "stage IN ('generation', 'activation', 'closing_same_book', 'closing_market')",
    )
    op.create_unique_constraint(
        "uq_ticket_leg_quote_snapshots_leg_stage",
        "ticket_leg_quote_snapshots",
        ["ticket_leg_id", "stage"],
    )
