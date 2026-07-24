"""add immutable prediction run input lineage

Revision ID: 012
Revises: 011
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prediction_runs") as batch_op:
        batch_op.add_column(sa.Column("source_dataset_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("strategy_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("input_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("input_context", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_prediction_runs_source_dataset_id",
            "scraped_datasets",
            ["source_dataset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_prediction_runs_strategy_id",
            "strategies",
            ["strategy_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_prediction_runs_source_dataset_id", ["source_dataset_id"])
        batch_op.create_index("ix_prediction_runs_strategy_id", ["strategy_id"])
        batch_op.create_index("ix_prediction_runs_input_hash", ["input_hash"])


def downgrade() -> None:
    with op.batch_alter_table("prediction_runs") as batch_op:
        batch_op.drop_index("ix_prediction_runs_input_hash")
        batch_op.drop_index("ix_prediction_runs_strategy_id")
        batch_op.drop_index("ix_prediction_runs_source_dataset_id")
        batch_op.drop_constraint("fk_prediction_runs_strategy_id", type_="foreignkey")
        batch_op.drop_constraint("fk_prediction_runs_source_dataset_id", type_="foreignkey")
        batch_op.drop_column("input_context")
        batch_op.drop_column("input_hash")
        batch_op.drop_column("strategy_id")
        batch_op.drop_column("source_dataset_id")
