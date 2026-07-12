"""add football league catalog cache

Revision ID: 008
Revises: 007
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "football_league_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scrape_slug", sa.String(length=255), nullable=False),
        sa.Column("country_slug", sa.String(length=120), nullable=False),
        sa.Column("country_name", sa.String(length=255), nullable=False),
        sa.Column("league_name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scrape_slug"),
    )
    op.create_index("ix_football_league_catalog_scrape_slug", "football_league_catalog", ["scrape_slug"])
    op.create_index("ix_football_league_catalog_country_slug", "football_league_catalog", ["country_slug"])
    op.create_index("ix_football_league_catalog_status", "football_league_catalog", ["status"])


def downgrade() -> None:
    op.drop_index("ix_football_league_catalog_status", table_name="football_league_catalog")
    op.drop_index("ix_football_league_catalog_country_slug", table_name="football_league_catalog")
    op.drop_index("ix_football_league_catalog_scrape_slug", table_name="football_league_catalog")
    op.drop_table("football_league_catalog")
