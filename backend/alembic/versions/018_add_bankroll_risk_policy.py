"""add explicit bankroll risk policies and decimal money storage

Revision ID: 018
Revises: 017
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(precision=14, scale=2)


def _money_column(
    table: str,
    column: str,
    *,
    nullable: bool,
    default: str | None = None,
) -> None:
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            column,
            existing_type=sa.Float(),
            type_=MONEY,
            existing_nullable=nullable,
            existing_server_default=default,
            postgresql_using=f"ROUND({column}::numeric, 2)",
        )


def _float_column(
    table: str,
    column: str,
    *,
    nullable: bool,
    default: str | None = None,
) -> None:
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            column,
            existing_type=MONEY,
            type_=sa.Float(),
            existing_nullable=nullable,
            existing_server_default=default,
            postgresql_using=f"{column}::double precision",
        )


def upgrade() -> None:
    for table, column, nullable, default in (
        ("bankrolls", "balance", False, "1000.0"),
        ("bankrolls", "initial_balance", False, "1000.0"),
        ("bookmaker_accounts", "balance", True, None),
        ("ticket_batches", "total_stake", False, "0.0"),
        ("tickets", "stake", False, "10.0"),
        ("tickets", "potential_return", False, "0.0"),
        ("settlements", "return_amount", False, "0.0"),
        ("settlements", "pnl", False, "0.0"),
        ("ledger_entries", "amount", False, None),
        ("ledger_entries", "balance_after", False, None),
    ):
        _money_column(table, column, nullable=nullable, default=default)

    op.create_table(
        "bankroll_risk_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bankroll_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("staking_mode", sa.String(length=32), nullable=False),
        sa.Column("flat_stake_pct", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("kelly_fraction", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("max_ticket_pct", sa.Numeric(precision=7, scale=6), nullable=False),
        sa.Column("max_open_exposure_pct", sa.Numeric(precision=7, scale=6), nullable=False),
        sa.Column("max_match_pct", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("max_team_pct", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("max_league_window_pct", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("league_window_hours", sa.Integer(), nullable=False),
        sa.Column("max_daily_stake_pct", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("max_weekly_stake_pct", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("max_daily_ticket_count", sa.Integer(), nullable=True),
        sa.Column("max_weekly_ticket_count", sa.Integer(), nullable=True),
        sa.Column("accumulators_enabled", sa.Boolean(), nullable=False),
        sa.Column("automation_enabled", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("version > 0", name="ck_bankroll_risk_policies_version"),
        sa.CheckConstraint(
            "staking_mode IN ('flat_percent', 'fractional_kelly')",
            name="ck_bankroll_risk_policies_staking_mode",
        ),
        sa.CheckConstraint(
            "(staking_mode = 'flat_percent' AND flat_stake_pct IS NOT NULL AND kelly_fraction IS NULL) "
            "OR (staking_mode = 'fractional_kelly' AND kelly_fraction IS NOT NULL AND flat_stake_pct IS NULL)",
            name="ck_bankroll_risk_policies_staking_fields",
        ),
        sa.CheckConstraint(
            "flat_stake_pct IS NULL OR (flat_stake_pct > 0 AND flat_stake_pct <= 0.05)",
            name="ck_bankroll_risk_policies_flat_stake_pct",
        ),
        sa.CheckConstraint(
            "kelly_fraction IS NULL OR (kelly_fraction > 0 AND kelly_fraction <= 0.5)",
            name="ck_bankroll_risk_policies_kelly_fraction",
        ),
        sa.CheckConstraint(
            "max_ticket_pct > 0 AND max_ticket_pct <= 0.05",
            name="ck_bankroll_risk_policies_max_ticket_pct",
        ),
        sa.CheckConstraint(
            "max_open_exposure_pct > 0 AND max_open_exposure_pct <= 0.20",
            name="ck_bankroll_risk_policies_max_open_exposure_pct",
        ),
        sa.CheckConstraint(
            "max_match_pct IS NULL OR (max_match_pct > 0 AND max_match_pct <= 0.20)",
            name="ck_bankroll_risk_policies_max_match_pct",
        ),
        sa.CheckConstraint(
            "max_team_pct IS NULL OR (max_team_pct > 0 AND max_team_pct <= 0.20)",
            name="ck_bankroll_risk_policies_max_team_pct",
        ),
        sa.CheckConstraint(
            "max_league_window_pct IS NULL OR (max_league_window_pct > 0 AND max_league_window_pct <= 0.20)",
            name="ck_bankroll_risk_policies_max_league_window_pct",
        ),
        sa.CheckConstraint(
            "max_daily_stake_pct IS NULL OR (max_daily_stake_pct > 0 AND max_daily_stake_pct <= 1.0)",
            name="ck_bankroll_risk_policies_max_daily_stake_pct",
        ),
        sa.CheckConstraint(
            "max_weekly_stake_pct IS NULL OR (max_weekly_stake_pct > 0 AND max_weekly_stake_pct <= 1.0)",
            name="ck_bankroll_risk_policies_max_weekly_stake_pct",
        ),
        sa.CheckConstraint("league_window_hours > 0", name="ck_bankroll_risk_policies_league_window_hours"),
        sa.ForeignKeyConstraint(["bankroll_id"], ["bankrolls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bankroll_id", "version", name="uq_bankroll_risk_policies_bankroll_version"),
    )
    op.create_index("ix_bankroll_risk_policies_bankroll_id", "bankroll_risk_policies", ["bankroll_id"])
    op.create_index(
        "uq_bankroll_risk_policies_active",
        "bankroll_risk_policies",
        ["bankroll_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
        sqlite_where=sa.text("superseded_at IS NULL"),
    )

    op.create_table(
        "bankroll_risk_states",
        sa.Column("bankroll_id", sa.Integer(), nullable=False),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pause_reason", sa.String(length=255), nullable=True),
        sa.Column("pending_policy", sa.JSON(), nullable=True),
        sa.Column("pending_effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["bankroll_id"], ["bankrolls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("bankroll_id"),
    )

    with op.batch_alter_table("ticket_batches") as batch_op:
        batch_op.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("risk_policy_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("risk_policy_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("risk_assessment", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("staking_snapshot", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("activation_report", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        )
        batch_op.create_foreign_key(
            "fk_ticket_batches_risk_policy_id",
            "bankroll_risk_policies",
            ["risk_policy_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_ticket_batches_risk_policy_id", ["risk_policy_id"])
        batch_op.create_index("ix_ticket_batches_bankroll_revision", ["bankroll_id", "revision"])

    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("risk_policy_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("risk_policy_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("risk_assessment", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("staking_snapshot", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tickets_risk_policy_id",
            "bankroll_risk_policies",
            ["risk_policy_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_tickets_risk_policy_id", ["risk_policy_id"])
        batch_op.create_index("ix_tickets_open_exposure", ["bankroll_id", "status", "created_at"])

    op.create_index(
        "ix_ledger_entries_bankroll_created_at",
        "ledger_entries",
        ["bankroll_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_bankroll_created_at", table_name="ledger_entries")

    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_index("ix_tickets_open_exposure")
        batch_op.drop_index("ix_tickets_risk_policy_id")
        batch_op.drop_constraint("fk_tickets_risk_policy_id", type_="foreignkey")
        batch_op.drop_column("staking_snapshot")
        batch_op.drop_column("risk_assessment")
        batch_op.drop_column("risk_policy_version")
        batch_op.drop_column("risk_policy_id")

    with op.batch_alter_table("ticket_batches") as batch_op:
        batch_op.drop_index("ix_ticket_batches_bankroll_revision")
        batch_op.drop_index("ix_ticket_batches_risk_policy_id")
        batch_op.drop_constraint("fk_ticket_batches_risk_policy_id", type_="foreignkey")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("activation_report")
        batch_op.drop_column("staking_snapshot")
        batch_op.drop_column("risk_assessment")
        batch_op.drop_column("risk_policy_version")
        batch_op.drop_column("risk_policy_id")
        batch_op.drop_column("revision")

    op.drop_table("bankroll_risk_states")
    op.drop_table("bankroll_risk_policies")

    for table, column, nullable, default in (
        ("ledger_entries", "balance_after", False, None),
        ("ledger_entries", "amount", False, None),
        ("settlements", "pnl", False, "0.0"),
        ("settlements", "return_amount", False, "0.0"),
        ("tickets", "potential_return", False, "0.0"),
        ("tickets", "stake", False, "10.0"),
        ("ticket_batches", "total_stake", False, "0.0"),
        ("bookmaker_accounts", "balance", True, None),
        ("bankrolls", "initial_balance", False, "1000.0"),
        ("bankrolls", "balance", False, "1000.0"),
    ):
        _float_column(table, column, nullable=nullable, default=default)
