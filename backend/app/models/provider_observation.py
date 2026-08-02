# ruff: noqa: E501
"""Immutable provider observation lineage tables (revision 030).

These models intentionally have no ORM delete cascades: provider facts are an
audit record and are removed only by the dependency-aware retention workflow.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ProviderObservationSlot(Base):
    __tablename__ = "provider_observation_slots"
    __table_args__ = (
        UniqueConstraint("observation_slot_key", name="uq_provider_observation_slots_key"),
        CheckConstraint(
            "conflict_state IN ('clear', 'conflicted')", name="ck_provider_observation_slots_conflict_state"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_slot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    conflict_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="clear")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProviderObservation(Base):
    __tablename__ = "provider_observations"
    __table_args__ = (
        UniqueConstraint("adapter_key", "source_key", "observation_key", name="uq_provider_observations_source_key"),
        CheckConstraint("normalization_state IN ('normalized')", name="ck_provider_observations_normalization_state"),
        CheckConstraint("conflict_state IN ('clear', 'conflicted')", name="ck_provider_observations_conflict_state"),
        CheckConstraint(
            "(payload_json IS NOT NULL AND envelope_json IS NOT NULL AND body_purged_at IS NULL) OR "
            "(payload_json IS NULL AND envelope_json IS NULL AND body_purged_at IS NOT NULL)",
            name="ck_provider_observations_body_purge_pair",
        ),
        CheckConstraint(
            "(converted_from_v1 AND envelope_version = '1.0' AND original_envelope_version IS NULL "
            "AND conversion_version IS NOT NULL) OR "
            "(NOT converted_from_v1 AND original_envelope_version = envelope_version "
            "AND conversion_version IS NULL)",
            name="ck_provider_observations_envelope_conversion",
        ),
        Index("ix_provider_observations_slot_key", "observation_slot_key"),
        Index("ix_provider_observations_source_id", "adapter_key", "source_key", "source_id"),
        Index("ix_provider_observations_recent", "ingested_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(
        ForeignKey("provider_observation_slots.id", ondelete="RESTRICT"), nullable=False
    )
    adapter_key: Mapped[str] = mapped_column(String(63), nullable=False)
    source_key: Mapped[str] = mapped_column(String(63), nullable=False)
    capability: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    envelope_version: Mapped[str] = mapped_column(String(32), nullable=False)
    original_envelope_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    converted_from_v1: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    conversion_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    freshness_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    envelope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    observation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    observation_slot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    normalization_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="normalized")
    conflict_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="clear")
    body_retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderObservationReceipt(Base):
    __tablename__ = "provider_observation_receipts"
    __table_args__ = (
        UniqueConstraint("receipt_key", name="uq_provider_observation_receipts_key"),
        CheckConstraint(
            "(received_envelope_json IS NOT NULL AND body_purged_at IS NULL) OR "
            "(received_envelope_json IS NULL AND body_purged_at IS NOT NULL)",
            name="ck_provider_observation_receipts_body_purge_pair",
        ),
        Index("ix_provider_observation_receipts_observation_id", "observation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("provider_observations.id", ondelete="RESTRICT"), nullable=False
    )
    receipt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(128), nullable=False)
    transport_version: Mapped[str] = mapped_column(String(128), nullable=False)
    conversion_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    received_envelope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_envelope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    scrape_job_id_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_job_run_id_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin_dataset_id_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scrape_job_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_jobs.id", ondelete="SET NULL"), nullable=True)
    scheduled_job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_job_runs.id", ondelete="SET NULL"), nullable=True
    )
    origin_dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("scraped_datasets.id", ondelete="SET NULL"), nullable=True
    )
    body_retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderObservationConflict(Base):
    __tablename__ = "provider_observation_conflicts"
    __table_args__ = (
        CheckConstraint("left_observation_id < right_observation_id", name="ck_provider_observation_conflicts_order"),
        UniqueConstraint("left_observation_id", "right_observation_id", name="uq_provider_observation_conflicts_pair"),
        Index("ix_provider_observation_conflicts_slot_key", "observation_slot_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_slot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    left_observation_id: Mapped[int] = mapped_column(
        ForeignKey("provider_observations.id", ondelete="RESTRICT"), nullable=False
    )
    right_observation_id: Mapped[int] = mapped_column(
        ForeignKey("provider_observations.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProviderObservationDatasetLink(Base):
    __tablename__ = "provider_observation_dataset_links"
    __table_args__ = (UniqueConstraint("observation_id", "dataset_id", name="uq_provider_observation_dataset_links"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("provider_observations.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_id: Mapped[int] = mapped_column(ForeignKey("scraped_datasets.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProviderObservationQuarantine(Base):
    __tablename__ = "provider_observation_quarantine"
    __table_args__ = (
        UniqueConstraint(
            "raw_digest", "reason_code", "reader_version", name="uq_provider_observation_quarantine_reason"
        ),
        CheckConstraint(
            "(diagnostic_metadata IS NOT NULL AND metadata_purged_at IS NULL) OR "
            "(diagnostic_metadata IS NULL AND metadata_purged_at IS NOT NULL)",
            name="ck_provider_observation_quarantine_metadata_purge_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    reader_version: Mapped[str] = mapped_column(String(128), nullable=False)
    diagnostic_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    metadata_retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
