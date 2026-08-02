"""enforce one active scraper recipe per key

Revision ID: 029
Revises: 028
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "029"
down_revision: str | None = "028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_scraper_recipes_one_active_key",
        "scraper_recipes",
        ["recipe_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_scraper_recipes_one_active_key", table_name="scraper_recipes")
