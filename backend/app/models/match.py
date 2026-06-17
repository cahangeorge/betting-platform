from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.prediction import EnsemblePrediction, ModelPrediction
    from app.models.ticket import TicketLeg


class Match(Base):
    __tablename__ = "matches"

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
    season: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    odds: Mapped[list["OddsEntry"]] = relationship("OddsEntry", back_populates="match", cascade="all, delete-orphan")
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


class OddsEntry(Base):
    __tablename__ = "odds_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    home_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    draw_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    match: Mapped["Match"] = relationship("Match", back_populates="odds")


class MatchStat(Base):
    __tablename__ = "match_stats"

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    match: Mapped["Match"] = relationship("Match", back_populates="sources")
