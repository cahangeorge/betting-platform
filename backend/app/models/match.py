"""Match, OddsEntry, MatchStat models."""
from __future__ import annotations

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Match(Base):
    __tablename__ = "match"

    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True, unique=True)
    home_team: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    away_team: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    league: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sport: Mapped[str] = mapped_column(String(30), nullable=False, default="football")
    kickoff_time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="upcoming", nullable=False)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    betfair_market_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    smarkets_market_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    odds: Mapped[list["OddsEntry"]] = relationship("OddsEntry", back_populates="match")
    stats: Mapped[list["MatchStat"]] = relationship("MatchStat", back_populates="match")
    ticket_legs: Mapped[list["TicketLeg"]] = relationship("TicketLeg", back_populates="match")


class OddsEntry(Base):
    __tablename__ = "odds_entry"

    match_id: Mapped[str] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    submarket: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    bookmaker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    odds_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_draw: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    match: Mapped["Match"] = relationship("Match", back_populates="odds")


class MatchStat(Base):
    __tablename__ = "match_stat"

    match_id: Mapped[str] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    elapsed: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Match minute")
    xg_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    xg_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    possession_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    possession_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    shots_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on_target_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on_target_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corners_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corners_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dangerous_attacks_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dangerous_attacks_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cards_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cards_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON: extra fields")
    match: Mapped["Match"] = relationship("Match", back_populates="stats")
    __table_args__ = (UniqueConstraint("match_id", "source", name="uq_match_stat_match_source"),)