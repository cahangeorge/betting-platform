"""bound provider runtime observability scans

Revision ID: 043
Revises: 042
"""

from collections.abc import Sequence

from alembic import op

revision: str = "043"
down_revision: str | None = "042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_provider_observations_recent",
            "provider_observations",
            ["ingested_at", "id"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_provider_ingestion_checkpoint_recent",
            "provider_ingestion_checkpoints",
            ["updated_at", "id"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_scheduled_job_runs_recent",
            "scheduled_job_runs",
            ["created_at", "id"],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    raise RuntimeError("provider runtime observability indexes are expand-only")
