"""add paper trading execution domain

Revision ID: 010
Revises: 009
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trading_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="paper-local"),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="paper"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("balance", sa.Numeric(precision=14, scale=2), nullable=False, server_default="1000.00"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trading_accounts_user_id", "trading_accounts", ["user_id"])

    op.create_table(
        "execution_intents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trading_account_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("odds_entry_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="paper"),
        sa.Column("market", sa.String(length=50), nullable=False),
        sa.Column("selection", sa.String(length=50), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False, server_default="BACK"),
        sa.Column("order_type", sa.String(length=20), nullable=False, server_default="LIMIT"),
        sa.Column("stake", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["odds_entry_id"], ["odds_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trading_account_id"], ["trading_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_execution_intents_user_key"),
    )
    for column in ("user_id", "trading_account_id", "ticket_id", "odds_entry_id", "status"):
        op.create_index(f"ix_execution_intents_{column}", "execution_intents", [column])

    op.create_table(
        "execution_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("execution_intent_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="paper-local"),
        sa.Column("external_order_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="filled"),
        sa.Column("requested_price", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("requested_size", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("matched_size", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["execution_intent_id"], ["execution_intents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_orders_execution_intent_id", "execution_orders", ["execution_intent_id"])

    op.create_table(
        "execution_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("execution_intent_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["execution_intent_id"], ["execution_intents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_events_execution_intent_id", "execution_events", ["execution_intent_id"])


def downgrade() -> None:
    op.drop_table("execution_events")
    op.drop_table("execution_orders")
    op.drop_table("execution_intents")
    op.drop_table("trading_accounts")
