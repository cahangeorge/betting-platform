"""add scraper recipe approval and retirement lineage

Revision ID: 027
Revises: 026
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "027"
down_revision: str | None = "026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scraper_recipes", sa.Column("schema_version", sa.String(length=32), server_default="1.0", nullable=False)
    )
    op.add_column("scraper_recipes", sa.Column("approved_by", sa.String(length=255), nullable=True))
    op.add_column("scraper_recipes", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scraper_recipes", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("scraper_recipes", "retired_at")
    op.drop_column("scraper_recipes", "approved_at")
    op.drop_column("scraper_recipes", "approved_by")
    op.drop_column("scraper_recipes", "schema_version")
