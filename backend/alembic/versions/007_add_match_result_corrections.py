"""add_match_result_corrections

Revision ID: 007
Revises: 006
Create Date: 2026-07-12

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "match_result_corrections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("corrected_by_user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_home_score", sa.Integer(), nullable=True),
        sa.Column("previous_away_score", sa.Integer(), nullable=True),
        sa.Column("previous_status", sa.String(length=50), nullable=False),
        sa.Column("corrected_home_score", sa.Integer(), nullable=False),
        sa.Column("corrected_away_score", sa.Integer(), nullable=False),
        sa.Column("corrected_status", sa.String(length=50), nullable=False, server_default="finished"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["corrected_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_result_corrections_match_id", "match_result_corrections", ["match_id"])
    op.create_index(
        "ix_match_result_corrections_corrected_by_user_id",
        "match_result_corrections",
        ["corrected_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_match_result_corrections_corrected_by_user_id", table_name="match_result_corrections")
    op.drop_index("ix_match_result_corrections_match_id", table_name="match_result_corrections")
    op.drop_table("match_result_corrections")
