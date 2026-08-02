"""version scraper recipe keys

Revision ID: 028
Revises: 027
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "028"
down_revision: str | None = "027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scraper_recipes") as batch_op:
        batch_op.drop_constraint("uq_scraper_recipes_recipe_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_scraper_recipes_key_version",
            ["recipe_key", "schema_version"],
        )


def downgrade() -> None:
    with op.batch_alter_table("scraper_recipes") as batch_op:
        batch_op.drop_constraint("uq_scraper_recipes_key_version", type_="unique")
        batch_op.create_unique_constraint("uq_scraper_recipes_recipe_key", ["recipe_key"])
