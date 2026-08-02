"""add hybrid scraper validation cache and recipe metadata

Revision ID: 026
Revises: 025
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "026"
down_revision: str | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scraper_validation_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scrape_slug", sa.String(length=255), nullable=False),
        sa.Column("season", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("historic_url", sa.Text(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('available', 'unavailable')", name="ck_scraper_validation_cache_status"),
        sa.UniqueConstraint("scrape_slug", "season", name="uq_scraper_validation_cache_slug_season"),
    )
    op.create_index("ix_scraper_validation_cache_expires_at", "scraper_validation_cache", ["expires_at"])
    op.create_table(
        "scraper_recipes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recipe_key", sa.String(length=255), nullable=False),
        sa.Column("engine", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("recipe", sa.JSON(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('candidate', 'active', 'disabled')", name="ck_scraper_recipes_status"),
        sa.UniqueConstraint("recipe_key", name="uq_scraper_recipes_recipe_key"),
    )
    op.create_index("ix_scraper_recipes_status", "scraper_recipes", ["status"])


def downgrade() -> None:
    op.drop_index("ix_scraper_recipes_status", table_name="scraper_recipes")
    op.drop_table("scraper_recipes")
    op.drop_index("ix_scraper_validation_cache_expires_at", table_name="scraper_validation_cache")
    op.drop_table("scraper_validation_cache")
