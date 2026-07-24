from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"
    __table_args__ = (
        CheckConstraint(
            "quality IN ('complete', 'partial', 'legacy_unknown')",
            name="ck_odds_snapshots_quality",
        ),
        UniqueConstraint("source", "source_key", name="uq_odds_snapshots_source_key"),
        Index("ix_odds_snapshots_match_observed", "match_id", "observed_at"),
        Index("ix_odds_snapshots_dataset_id", "dataset_id"),
        Index("ix_odds_snapshots_scrape_job_id", "scrape_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("scraped_datasets.id", ondelete="SET NULL"), nullable=True
    )
    scrape_job_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_jobs.id", ondelete="SET NULL"), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    quality: Mapped[str] = mapped_column(String(32), default="complete", nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class TicketLegQuoteSnapshot(Base):
    __tablename__ = "ticket_leg_quote_snapshots"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('generation', 'refresh', 'activation', 'closing_same_book', 'closing_market')",
            name="ck_ticket_leg_quote_snapshots_stage",
        ),
        CheckConstraint("price > 1", name="ck_ticket_leg_quote_snapshots_price"),
        CheckConstraint("revision > 0", name="ck_ticket_leg_quote_snapshots_revision"),
        UniqueConstraint(
            "ticket_leg_id",
            "stage",
            "revision",
            name="uq_ticket_leg_quote_snapshots_leg_stage_revision",
        ),
        Index("ix_ticket_leg_quote_snapshots_ticket_leg_id", "ticket_leg_id"),
        Index("ix_ticket_leg_quote_snapshots_odds_snapshot_id", "odds_snapshot_id"),
        Index("ix_ticket_leg_quote_snapshots_recorded_at", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_leg_id: Mapped[int] = mapped_column(ForeignKey("ticket_legs.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    odds_entry_id: Mapped[int | None] = mapped_column(ForeignKey("odds_entries.id", ondelete="SET NULL"), nullable=True)
    odds_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("odds_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    selection: Mapped[str] = mapped_column(String(50), nullable=False)
    bookmaker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    model_probability: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    market_probability: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    market_probability_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fair_odds: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    probability_edge_pp: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    expected_value_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
