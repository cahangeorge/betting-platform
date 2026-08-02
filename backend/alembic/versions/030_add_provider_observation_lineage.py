# ruff: noqa: E501
"""add immutable provider observation lineage

Revision ID: 030
Revises: 029
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "030"
down_revision: str | None = "029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_observation_slots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("observation_slot_key", sa.String(64), nullable=False),
        sa.Column("conflict_state", sa.String(16), nullable=False, server_default="clear"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "conflict_state IN ('clear', 'conflicted')", name="ck_provider_observation_slots_conflict_state"
        ),
        sa.UniqueConstraint("observation_slot_key", name="uq_provider_observation_slots_key"),
    )
    op.create_table(
        "provider_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "slot_id", sa.Integer(), sa.ForeignKey("provider_observation_slots.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("adapter_key", sa.String(63), nullable=False),
        sa.Column("source_key", sa.String(63), nullable=False),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("envelope_version", sa.String(32), nullable=False),
        sa.Column("original_envelope_version", sa.String(32)),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("converted_from_v1", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("conversion_version", sa.String(128)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("freshness_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text()),
        sa.Column("envelope_json", sa.Text()),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("envelope_digest", sa.String(64), nullable=False),
        sa.Column("observation_key", sa.String(64), nullable=False),
        sa.Column("observation_slot_key", sa.String(64), nullable=False),
        sa.Column("normalization_state", sa.String(16), nullable=False, server_default="normalized"),
        sa.Column("conflict_state", sa.String(16), nullable=False, server_default="clear"),
        sa.Column("body_retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body_purged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "normalization_state IN ('normalized')", name="ck_provider_observations_normalization_state"
        ),
        sa.CheckConstraint("conflict_state IN ('clear', 'conflicted')", name="ck_provider_observations_conflict_state"),
        sa.CheckConstraint(
            "(payload_json IS NOT NULL AND envelope_json IS NOT NULL AND body_purged_at IS NULL) OR (payload_json IS NULL AND envelope_json IS NULL AND body_purged_at IS NOT NULL)",
            name="ck_provider_observations_body_purge_pair",
        ),
        sa.CheckConstraint(
            "(converted_from_v1 AND envelope_version = '1.0' AND original_envelope_version IS NULL AND conversion_version IS NOT NULL) OR (NOT converted_from_v1 AND original_envelope_version = envelope_version AND conversion_version IS NULL)",
            name="ck_provider_observations_envelope_conversion",
        ),
        sa.UniqueConstraint("adapter_key", "source_key", "observation_key", name="uq_provider_observations_source_key"),
    )
    op.create_index("ix_provider_observations_slot_key", "provider_observations", ["observation_slot_key"])
    op.create_index(
        "ix_provider_observations_source_id", "provider_observations", ["adapter_key", "source_key", "source_id"]
    )
    op.create_table(
        "provider_observation_receipts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "observation_id",
            sa.Integer(),
            sa.ForeignKey("provider_observations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("receipt_key", sa.String(64), nullable=False),
        sa.Column("provider_job_id", sa.String(255), nullable=False),
        sa.Column("provider_run_id", sa.String(255), nullable=False),
        sa.Column("correlation_id", sa.String(255), nullable=False),
        sa.Column("adapter_version", sa.String(128), nullable=False),
        sa.Column("transport_version", sa.String(128), nullable=False),
        sa.Column("conversion_version", sa.String(128)),
        sa.Column("received_envelope_json", sa.Text()),
        sa.Column("received_envelope_digest", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("scrape_job_id_snapshot", sa.Integer()),
        sa.Column("scheduled_job_run_id_snapshot", sa.Integer()),
        sa.Column("origin_dataset_id_snapshot", sa.Integer()),
        sa.Column("scrape_job_id", sa.Integer(), sa.ForeignKey("scrape_jobs.id", ondelete="SET NULL")),
        sa.Column("scheduled_job_run_id", sa.Integer(), sa.ForeignKey("scheduled_job_runs.id", ondelete="SET NULL")),
        sa.Column("origin_dataset_id", sa.Integer(), sa.ForeignKey("scraped_datasets.id", ondelete="SET NULL")),
        sa.Column("body_retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body_purged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(received_envelope_json IS NOT NULL AND body_purged_at IS NULL) OR (received_envelope_json IS NULL AND body_purged_at IS NOT NULL)",
            name="ck_provider_observation_receipts_body_purge_pair",
        ),
        sa.UniqueConstraint("receipt_key", name="uq_provider_observation_receipts_key"),
    )
    op.create_index(
        "ix_provider_observation_receipts_observation_id", "provider_observation_receipts", ["observation_id"]
    )
    op.create_table(
        "provider_observation_conflicts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("observation_slot_key", sa.String(64), nullable=False),
        sa.Column(
            "left_observation_id",
            sa.Integer(),
            sa.ForeignKey("provider_observations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "right_observation_id",
            sa.Integer(),
            sa.ForeignKey("provider_observations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "left_observation_id < right_observation_id", name="ck_provider_observation_conflicts_order"
        ),
        sa.UniqueConstraint(
            "left_observation_id", "right_observation_id", name="uq_provider_observation_conflicts_pair"
        ),
    )
    op.create_index(
        "ix_provider_observation_conflicts_slot_key", "provider_observation_conflicts", ["observation_slot_key"]
    )
    op.create_table(
        "provider_observation_dataset_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "observation_id",
            sa.Integer(),
            sa.ForeignKey("provider_observations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id", sa.Integer(), sa.ForeignKey("scraped_datasets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("observation_id", "dataset_id", name="uq_provider_observation_dataset_links"),
    )
    op.create_table(
        "provider_observation_quarantine",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("raw_digest", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("reader_version", sa.String(128), nullable=False),
        sa.Column("diagnostic_metadata", sa.Text()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata_retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_purged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(diagnostic_metadata IS NOT NULL AND metadata_purged_at IS NULL) OR (diagnostic_metadata IS NULL AND metadata_purged_at IS NOT NULL)",
            name="ck_provider_observation_quarantine_metadata_purge_pair",
        ),
        sa.UniqueConstraint(
            "raw_digest", "reason_code", "reader_version", name="uq_provider_observation_quarantine_reason"
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_observation_quarantine")
    op.drop_table("provider_observation_dataset_links")
    op.drop_index("ix_provider_observation_conflicts_slot_key", table_name="provider_observation_conflicts")
    op.drop_table("provider_observation_conflicts")
    op.drop_index("ix_provider_observation_receipts_observation_id", table_name="provider_observation_receipts")
    op.drop_table("provider_observation_receipts")
    op.drop_index("ix_provider_observations_source_id", table_name="provider_observations")
    op.drop_index("ix_provider_observations_slot_key", table_name="provider_observations")
    op.drop_table("provider_observations")
    op.drop_table("provider_observation_slots")
