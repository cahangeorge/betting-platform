from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.user import User


class PredictionRun(Base):
    __tablename__ = "prediction_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_type: Mapped[str] = mapped_column(String(100), nullable=False)
    ensemble: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    matches_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User | None"] = relationship("User", back_populates="prediction_runs")
    model_predictions: Mapped[list["ModelPrediction"]] = relationship(
        "ModelPrediction", back_populates="run", cascade="all, delete-orphan"
    )
    ensemble_predictions: Mapped[list["EnsemblePrediction"]] = relationship(
        "EnsemblePrediction", back_populates="run", cascade="all, delete-orphan"
    )


class ModelPrediction(Base):
    __tablename__ = "model_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("prediction_runs.id", ondelete="CASCADE"), nullable=False)
    model_type: Mapped[str] = mapped_column(String(100), nullable=False)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    home_prob: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    draw_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_prob: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    home_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    draw_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_draw: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run: Mapped["PredictionRun"] = relationship("PredictionRun", back_populates="model_predictions")
    match: Mapped["Match"] = relationship("Match", back_populates="model_predictions")


class EnsemblePrediction(Base):
    __tablename__ = "ensemble_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("prediction_runs.id", ondelete="CASCADE"), nullable=False)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    home_prob: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    draw_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_prob: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    brier_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run: Mapped["PredictionRun"] = relationship("PredictionRun", back_populates="ensemble_predictions")
    match: Mapped["Match"] = relationship("Match", back_populates="ensemble_predictions")


class PredictionSession(Base):
    __tablename__ = "prediction_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    predictions: Mapped[list["Prediction"]] = relationship(
        "Prediction", back_populates="session", cascade="all, delete-orphan"
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("prediction_sessions.id", ondelete="CASCADE"), nullable=False)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    home_prob: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    draw_prob: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    away_prob: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    home_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    draw_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session: Mapped["PredictionSession"] = relationship("PredictionSession", back_populates="predictions")
    match: Mapped["Match"] = relationship("Match")
