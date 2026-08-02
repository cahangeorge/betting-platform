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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"
    __table_args__ = (
        Index("ix_scrape_jobs_status", "status"),
        Index("ix_scrape_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    league: Mapped[str | None] = mapped_column(String(255), nullable=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    logs: Mapped[list["ScrapeJobLog"]] = relationship(
        "ScrapeJobLog", back_populates="job", cascade="all, delete-orphan"
    )


class ScrapeJobLog(Base):
    __tablename__ = "scrape_job_logs"
    __table_args__ = (
        Index("ix_scrape_job_logs_job_id", "job_id"),
        Index("ix_scrape_job_logs_job_created", "job_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("scrape_jobs.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job: Mapped["ScrapeJob"] = relationship("ScrapeJob", back_populates="logs")


class ScrapedDataset(Base):
    __tablename__ = "scraped_datasets"
    __table_args__ = (
        Index("ix_scraped_datasets_source", "source"),
        UniqueConstraint("dataset_key", name="uq_scraped_datasets_dataset_key"),
        Index("ix_scraped_datasets_freshness", "publication_state", "fresh_until"),
        Index("ix_scraped_datasets_group", "dataset_group_key", "publication_state"),
        CheckConstraint(
            "publication_state IS NULL OR publication_state IN ('staged', 'published', 'quarantined')",
            name="ck_scraped_datasets_publication_state",
        ),
        CheckConstraint(
            "publication_state NOT IN ('staged', 'published') OR "
            "(dataset_key IS NOT NULL AND dataset_group_key IS NOT NULL "
            "AND dataset_schema_version IS NOT NULL AND dataset_digest IS NOT NULL "
            "AND matches_count IS NOT NULL AND matches_count > 0 "
            "AND source_as_of IS NOT NULL AND fresh_until IS NOT NULL)",
            name="ck_scraped_datasets_published_complete",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    matches_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_group_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dataset_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    origin_scheduled_job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_job_runs.id", ondelete="SET NULL"), nullable=True
    )
    origin_run_id_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fresh_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScraperValidationCache(Base):
    """Short-lived Results-page validation outcomes; never stores browser state."""

    __tablename__ = "scraper_validation_cache"
    __table_args__ = (
        UniqueConstraint("scrape_slug", "season", name="uq_scraper_validation_cache_slug_season"),
        CheckConstraint("status IN ('available', 'unavailable')", name="ck_scraper_validation_cache_status"),
        Index("ix_scraper_validation_cache_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    historic_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScraperRecipe(Base):
    """Versioned selector/XHR recipe metadata. Sensitive browser state is forbidden."""

    __tablename__ = "scraper_recipes"
    __table_args__ = (
        UniqueConstraint("recipe_key", "schema_version", name="uq_scraper_recipes_key_version"),
        CheckConstraint("status IN ('candidate', 'active', 'disabled')", name="ck_scraper_recipes_status"),
        Index("ix_scraper_recipes_status", "status"),
        Index(
            "uq_scraper_recipes_one_active_key", "recipe_key", unique=True, postgresql_where=text("status = 'active'")
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate")
    recipe: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
