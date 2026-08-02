"""add soccerdata durable checkpoint and canonical dataset metadata

Revision ID: 034
Revises: 033
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "034"
down_revision: str | None = "033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_STAGED_COMPLETE = (
    "publication_state NOT IN ('staged', 'published') OR "
    "(dataset_key IS NOT NULL AND dataset_group_key IS NOT NULL "
    "AND dataset_schema_version IS NOT NULL "
    "AND dataset_digest IS NOT NULL AND matches_count IS NOT NULL AND matches_count > 0 "
    "AND source_as_of IS NOT NULL AND fresh_until IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "provider_ingestion_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("checkpoint_key", sa.String(length=64), nullable=False),
        sa.Column("spec_digest", sa.String(length=64), nullable=False),
        sa.Column("spec_version", sa.String(length=32), nullable=False),
        sa.Column("partition_key", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="claimed"),
        sa.Column("cursor_json", sa.JSON(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("observation_count", sa.Integer(), nullable=True),
        sa.Column("payload_digest", sa.String(length=64), nullable=True),
        sa.Column("dataset_generation_key", sa.String(length=64), nullable=True),
        sa.Column("cache_mode", sa.String(length=16), nullable=True),
        sa.Column("cache_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fresh_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_id_snapshot", sa.String(length=128), nullable=True),
        sa.Column(
            "scheduled_job_run_id",
            sa.Integer(),
            sa.ForeignKey("scheduled_job_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("checkpoint_key", name="uq_provider_ingestion_checkpoint_key"),
        sa.UniqueConstraint("spec_digest", "partition_key", name="uq_provider_ingestion_checkpoint_partition"),
        sa.CheckConstraint(
            "state IN ('claimed', 'completed', 'no_data', 'failed')", name="ck_provider_ingestion_checkpoint_state"
        ),
        sa.CheckConstraint(
            "cache_mode IS NULL OR cache_mode IN ('cold', 'warm', 'revalidated', 'no-store')",
            name="ck_provider_ingestion_checkpoint_cache_mode",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_provider_ingestion_checkpoint_attempt"),
        sa.CheckConstraint(
            "record_count IS NULL OR record_count >= 0", name="ck_provider_ingestion_checkpoint_record_count"
        ),
        sa.CheckConstraint(
            "observation_count IS NULL OR observation_count >= 0",
            name="ck_provider_ingestion_checkpoint_observation_count",
        ),
    )
    op.create_index(
        "ix_provider_ingestion_checkpoint_state", "provider_ingestion_checkpoints", ["state", "fresh_until"]
    )
    op.create_index(
        "ix_provider_ingestion_checkpoint_job_run", "provider_ingestion_checkpoints", ["scheduled_job_run_id"]
    )
    for name, type_ in (
        ("dataset_key", sa.String(length=64)),
        ("dataset_group_key", sa.String(length=64)),
        ("dataset_schema_version", sa.String(length=32)),
        ("dataset_digest", sa.String(length=64)),
        ("publication_state", sa.String(length=16)),
        ("origin_scheduled_job_run_id", sa.Integer()),
        ("origin_run_id_snapshot", sa.String(length=128)),
        ("source_as_of", sa.DateTime(timezone=True)),
        ("fresh_until", sa.DateTime(timezone=True)),
    ):
        op.add_column("scraped_datasets", sa.Column(name, type_, nullable=True))
    op.create_check_constraint(
        "ck_scraped_datasets_publication_state",
        "scraped_datasets",
        "publication_state IS NULL OR publication_state IN ('staged', 'published', 'quarantined')",
    )
    op.create_check_constraint(
        "ck_scraped_datasets_published_complete",
        "scraped_datasets",
        _STAGED_COMPLETE,
    )
    op.create_foreign_key(
        "fk_scraped_datasets_origin_job_run",
        "scraped_datasets",
        "scheduled_job_runs",
        ["origin_scheduled_job_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_scraped_datasets_dataset_key", "scraped_datasets", ["dataset_key"])
    op.create_index("ix_scraped_datasets_freshness", "scraped_datasets", ["publication_state", "fresh_until"])
    op.create_index("ix_scraped_datasets_group", "scraped_datasets", ["dataset_group_key", "publication_state"])
    op.create_table(
        "provider_dataset_generations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("generation_key", sa.String(length=64), nullable=False),
        sa.Column("dataset_group_key", sa.String(length=64), nullable=False),
        sa.Column("artifact_digest", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="staged"),
        sa.Column("terminal_page", sa.Integer(), nullable=True),
        sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fresh_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("generation_key", name="uq_provider_dataset_generation_key"),
        sa.CheckConstraint(
            "state IN ('staged', 'published', 'superseded')",
            name="ck_provider_dataset_generation_state",
        ),
        sa.CheckConstraint(
            "terminal_page IS NULL OR terminal_page >= -1",
            name="ck_provider_dataset_generation_terminal",
        ),
    )
    op.create_index(
        "ix_provider_dataset_generation_group",
        "provider_dataset_generations",
        ["dataset_group_key", "state"],
    )
    op.create_index(
        "uq_provider_dataset_generation_published_head",
        "provider_dataset_generations",
        ["dataset_group_key"],
        unique=True,
        postgresql_where=sa.text("state = 'published'"),
    )
    op.create_table(
        "provider_dataset_generation_pages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "generation_id",
            sa.Integer(),
            sa.ForeignKey("provider_dataset_generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column(
            "dataset_id",
            sa.Integer(),
            sa.ForeignKey("scraped_datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("generation_id", "page", name="uq_provider_dataset_generation_page"),
        sa.CheckConstraint("page >= 0", name="ck_provider_dataset_generation_page_nonnegative"),
    )
    op.create_index(
        "ix_provider_dataset_generation_page_dataset",
        "provider_dataset_generation_pages",
        ["dataset_id"],
    )


def downgrade() -> None:
    raise RuntimeError("soccerdata ingestion contract migration is expand-only; destructive downgrade is not supported")
