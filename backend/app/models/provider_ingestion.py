"""Durable provider ingestion checkpoint contract."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ProviderIngestionCheckpoint(Base):
    __tablename__ = "provider_ingestion_checkpoints"
    __table_args__ = (
        UniqueConstraint("checkpoint_key", name="uq_provider_ingestion_checkpoint_key"),
        UniqueConstraint("spec_digest", "partition_key", name="uq_provider_ingestion_checkpoint_partition"),
        CheckConstraint(
            "state IN ('claimed', 'completed', 'no_data', 'failed')", name="ck_provider_ingestion_checkpoint_state"
        ),
        CheckConstraint(
            "cache_mode IS NULL OR cache_mode IN ('cold', 'warm', 'revalidated', 'no-store')",
            name="ck_provider_ingestion_checkpoint_cache_mode",
        ),
        CheckConstraint("attempt >= 1", name="ck_provider_ingestion_checkpoint_attempt"),
        CheckConstraint(
            "record_count IS NULL OR record_count >= 0", name="ck_provider_ingestion_checkpoint_record_count"
        ),
        CheckConstraint(
            "observation_count IS NULL OR observation_count >= 0",
            name="ck_provider_ingestion_checkpoint_observation_count",
        ),
        Index("ix_provider_ingestion_checkpoint_state", "state", "fresh_until"),
        Index("ix_provider_ingestion_checkpoint_job_run", "scheduled_job_run_id"),
        Index("ix_provider_ingestion_checkpoint_recent", "updated_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checkpoint_key: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_version: Mapped[str] = mapped_column(String(32), nullable=False)
    partition_key: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="claimed")
    cursor_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_generation_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cache_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cache_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fresh_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_id_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scheduled_job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_job_runs.id", ondelete="SET NULL"), nullable=True
    )
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProviderDatasetGeneration(Base):
    """One immutable upstream snapshot and the authoritative head for a logical dataset group."""

    __tablename__ = "provider_dataset_generations"
    __table_args__ = (
        UniqueConstraint("generation_key", name="uq_provider_dataset_generation_key"),
        CheckConstraint("state IN ('staged', 'published', 'superseded')", name="ck_provider_dataset_generation_state"),
        CheckConstraint("terminal_page IS NULL OR terminal_page >= -1", name="ck_provider_dataset_generation_terminal"),
        Index("ix_provider_dataset_generation_group", "dataset_group_key", "state"),
        Index(
            "uq_provider_dataset_generation_published_head",
            "dataset_group_key",
            unique=True,
            postgresql_where=text("state = 'published'"),
            sqlite_where=text("state = 'published'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_group_key: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="staged")
    terminal_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fresh_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProviderDatasetGenerationPage(Base):
    """Generation membership separated from deduplicated canonical dataset content."""

    __tablename__ = "provider_dataset_generation_pages"
    __table_args__ = (
        UniqueConstraint("generation_id", "page", name="uq_provider_dataset_generation_page"),
        CheckConstraint("page >= 0", name="ck_provider_dataset_generation_page_nonnegative"),
        Index("ix_provider_dataset_generation_page_dataset", "dataset_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generation_id: Mapped[int] = mapped_column(
        ForeignKey("provider_dataset_generations.id", ondelete="CASCADE"), nullable=False
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("scraped_datasets.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
