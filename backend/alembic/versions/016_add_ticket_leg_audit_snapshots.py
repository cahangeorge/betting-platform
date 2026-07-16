"""add immutable ticket-leg audit snapshots

Revision ID: 016
Revises: 015
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ticket_legs") as batch_op:
        batch_op.add_column(sa.Column("prediction_run_id_snapshot", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("model_probability_snapshot", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("market_probability_snapshot", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("market_probability_basis_snapshot", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("expected_value_snapshot", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("edge_pct_snapshot", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("reliability_label_snapshot", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("reliability_score_snapshot", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ticket_legs") as batch_op:
        batch_op.drop_column("reliability_score_snapshot")
        batch_op.drop_column("reliability_label_snapshot")
        batch_op.drop_column("edge_pct_snapshot")
        batch_op.drop_column("expected_value_snapshot")
        batch_op.drop_column("market_probability_basis_snapshot")
        batch_op.drop_column("market_probability_snapshot")
        batch_op.drop_column("model_probability_snapshot")
        batch_op.drop_column("prediction_run_id_snapshot")
