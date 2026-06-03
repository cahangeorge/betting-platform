"""Live betting engine tables."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LiveOdds(Base):
    __tablename__ = "live_odds"

    match_id: Mapped[str] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    runner: Mapped[str] = mapped_column(String(50), nullable=False)
    available_to_back: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    available_to_lay: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    traded_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_traded: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_matched: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_play: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bet_delay: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    received_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("match_id", "exchange", "market", "runner", name="uq_live_odds_match_exch_market_runner"),)


class TradingPosition(Base):
    __tablename__ = "trading_position"

    bankroll_id: Mapped[str] = mapped_column(ForeignKey("bankroll.id", ondelete="CASCADE"), nullable=False, index=True)
    match_id: Mapped[str | None] = mapped_column(ForeignKey("match.id", ondelete="SET NULL"), nullable=True, index=True)
    market_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    runner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False, comment="BACK | LAY")
    status: Mapped[str] = mapped_column(String(15), default="open", nullable=False, comment="open | filled | settled | void | error")
    requested_odds: Mapped[float] = mapped_column(Float, nullable=False)
    requested_stake: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    average_price_matched: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_matched: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    size_remaining: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    betfair_bet_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    persistence: Mapped[str] = mapped_column(String(10), nullable=False)
    model_prob_at_entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    implied_prob_at_entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    edge_at_entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    matched_time: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_time: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_result: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="won | lost | void")
    profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)