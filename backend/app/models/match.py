from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.odds_lineage import OddsSnapshot, TicketLegQuoteSnapshot
    from app.models.prediction import EnsemblePrediction, ModelPrediction
    from app.models.ticket import TicketLeg


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_status", "status"),
        Index("ix_matches_match_date", "match_date"),
        Index("ix_matches_competition", "competition"),
        Index("ix_matches_home_team_id", "home_team_id"),
        Index("ix_matches_away_team_id", "away_team_id"),
        Index("ix_matches_competition_id", "competition_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sport: Mapped[str] = mapped_column(String(50), default="football", nullable=False)
    home_team: Mapped[str] = mapped_column(String(255), nullable=False)
    away_team: Mapped[str] = mapped_column(String(255), nullable=False)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="scheduled", nullable=False)
    match_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    competition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True)
    away_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True)
    competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=True
    )
    season: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    odds: Mapped[list["OddsEntry"]] = relationship("OddsEntry", back_populates="match", cascade="all, delete-orphan")
    odds_snapshots: Mapped[list["OddsSnapshot"]] = relationship("OddsSnapshot", cascade="all, delete-orphan")
    stats: Mapped[list["MatchStat"]] = relationship("MatchStat", back_populates="match", cascade="all, delete-orphan")
    sources: Mapped[list["MatchSource"]] = relationship(
        "MatchSource", back_populates="match", cascade="all, delete-orphan"
    )
    model_predictions: Mapped[list["ModelPrediction"]] = relationship(
        "ModelPrediction", back_populates="match", cascade="all, delete-orphan"
    )
    ensemble_predictions: Mapped[list["EnsemblePrediction"]] = relationship(
        "EnsemblePrediction", back_populates="match", cascade="all, delete-orphan"
    )
    ticket_legs: Mapped[list["TicketLeg"]] = relationship(
        "TicketLeg", back_populates="match", cascade="all, delete-orphan"
    )
    result_corrections: Mapped[list["MatchResultCorrection"]] = relationship(
        "MatchResultCorrection", back_populates="match", cascade="all, delete-orphan"
    )


class MatchResultCorrection(Base):
    """An explicit, attributable correction to a persisted final match result."""

    __tablename__ = "match_result_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True)
    corrected_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_status: Mapped[str] = mapped_column(String(50), nullable=False)
    corrected_home_score: Mapped[int] = mapped_column(Integer, nullable=False)
    corrected_away_score: Mapped[int] = mapped_column(Integer, nullable=False)
    corrected_status: Mapped[str] = mapped_column(String(50), nullable=False, default="finished")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    match: Mapped["Match"] = relationship("Match", back_populates="result_corrections")


class OddsEntry(Base):
    __tablename__ = "odds_entries"
    __table_args__ = (Index("ix_odds_entries_match_id", "match_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    odds_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("odds_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    home_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    draw_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    match: Mapped["Match"] = relationship("Match", back_populates="odds")
    odds_snapshot: Mapped["OddsSnapshot | None"] = relationship("OddsSnapshot")
    quote_snapshots: Mapped[list["TicketLegQuoteSnapshot"]] = relationship("TicketLegQuoteSnapshot")


class MatchStat(Base):
    __tablename__ = "match_stats"
    __table_args__ = (Index("ix_match_stats_match_id", "match_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    home_xg: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_xg: Mapped[float | None] = mapped_column(Float, nullable=True)
    possession_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    possession_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    shots_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offsides_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offsides_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    json_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    match: Mapped["Match"] = relationship("Match", back_populates="stats")


class MatchSource(Base):
    __tablename__ = "match_sources"
    __table_args__ = (Index("ix_match_sources_match_id", "match_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    match: Mapped["Match"] = relationship("Match", back_populates="sources")
