"""index and validate provider match identity foreign keys

Revision ID: 032
Revises: 031
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "032"
down_revision: str | None = "031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_INDEXES = (
    ("ix_matches_home_team_id", "home_team_id"),
    ("ix_matches_away_team_id", "away_team_id"),
    ("ix_matches_competition_id", "competition_id"),
)


def upgrade() -> None:
    # The names are migration constants. Query validity first, then issue a
    # top-level concurrent DROP only for a failed retry artifact.
    context = op.get_context()
    with context.autocommit_block():
        bind = op.get_bind()
        for index, column in _INDEXES:
            if context.as_sql:
                op.execute(sa.text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index} ON matches ({column})"))
                continue
            invalid = bind.execute(
                sa.text("""
                SELECT NOT i.indisvalid FROM pg_class c
                JOIN pg_index i ON i.indexrelid = c.oid
                WHERE c.relnamespace = 'public'::regnamespace AND c.relname = :name
            """),
                {"name": index},
            ).scalar()
            if invalid is True:
                bind.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS public.{index}"))
            bind.execute(sa.text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index} ON matches ({column})"))
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '10s'")
    for constraint in ("fk_matches_home_team_id", "fk_matches_away_team_id", "fk_matches_competition_id"):
        op.execute(sa.text(f"ALTER TABLE matches VALIDATE CONSTRAINT {constraint}"))


def downgrade() -> None:
    raise RuntimeError("provider identity migration is expand-only; destructive downgrade is not supported")
