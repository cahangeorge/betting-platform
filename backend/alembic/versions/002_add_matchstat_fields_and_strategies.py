"""add_matchstat_fields_and_strategies

Revision ID: 002
Revises: 001
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("match_stats", sa.Column("yellow_cards_home", sa.Integer(), nullable=True))
    op.add_column("match_stats", sa.Column("yellow_cards_away", sa.Integer(), nullable=True))
    op.add_column("match_stats", sa.Column("red_cards_home", sa.Integer(), nullable=True))
    op.add_column("match_stats", sa.Column("red_cards_away", sa.Integer(), nullable=True))
    op.add_column("match_stats", sa.Column("fouls_home", sa.Integer(), nullable=True))
    op.add_column("match_stats", sa.Column("fouls_away", sa.Integer(), nullable=True))
    op.add_column("match_stats", sa.Column("offsides_home", sa.Integer(), nullable=True))
    op.add_column("match_stats", sa.Column("offsides_away", sa.Integer(), nullable=True))

    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("model_type", sa.String(length=100), nullable=False),
        sa.Column("parameters", JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("weights", JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("strategies")

    op.drop_column("match_stats", "offsides_away")
    op.drop_column("match_stats", "offsides_home")
    op.drop_column("match_stats", "fouls_away")
    op.drop_column("match_stats", "fouls_home")
    op.drop_column("match_stats", "red_cards_away")
    op.drop_column("match_stats", "red_cards_home")
    op.drop_column("match_stats", "yellow_cards_away")
    op.drop_column("match_stats", "yellow_cards_home")
