"""add_prediction_links_to_ticket_legs

Revision ID: 003
Revises: 002
Create Date: 2026-06-13

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "model_predictions",
        sa.Column("model_type", sa.String(length=100), nullable=True),
    )
    op.execute("UPDATE model_predictions SET model_type = 'unknown' WHERE model_type IS NULL")
    op.alter_column("model_predictions", "model_type", nullable=False)

    op.add_column(
        "ticket_legs",
        sa.Column("model_prediction_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ticket_legs_model_prediction_id_model_predictions",
        "ticket_legs",
        "model_predictions",
        ["model_prediction_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_ticket_legs_model_prediction_id_model_predictions", "ticket_legs", type_="foreignkey")
    op.drop_column("ticket_legs", "model_prediction_id")
    op.drop_column("model_predictions", "model_type")
