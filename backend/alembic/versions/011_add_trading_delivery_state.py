"""add durable trading delivery state

Revision ID: 011
Revises: 010
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "execution_intents", sa.Column("transport", sa.String(length=20), nullable=False, server_default="inprocess")
    )
    op.add_column(
        "execution_intents",
        sa.Column("delivery_status", sa.String(length=30), nullable=False, server_default="pending"),
    )
    op.add_column("execution_intents", sa.Column("transport_task_id", sa.String(length=255), nullable=True))
    op.add_column(
        "execution_intents", sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("execution_intents", sa.Column("last_delivery_error", sa.Text(), nullable=True))
    op.create_index("ix_execution_intents_delivery_status", "execution_intents", ["delivery_status"])


def downgrade() -> None:
    op.drop_index("ix_execution_intents_delivery_status", table_name="execution_intents")
    op.drop_column("execution_intents", "last_delivery_error")
    op.drop_column("execution_intents", "delivery_attempts")
    op.drop_column("execution_intents", "transport_task_id")
    op.drop_column("execution_intents", "delivery_status")
    op.drop_column("execution_intents", "transport")
