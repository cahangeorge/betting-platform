"""add_model_prediction_quality_report

Revision ID: 004
Revises: 003
Create Date: 2026-06-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("model_predictions", sa.Column("quality_report", JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("model_predictions", "quality_report")
