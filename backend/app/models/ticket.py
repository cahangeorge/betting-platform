from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.bankroll import Bankroll, BookmakerAccount, LedgerEntry
    from app.models.match import Match
    from app.models.model_governance import ModelEvaluation
    from app.models.odds_lineage import TicketLegQuoteSnapshot
    from app.models.prediction import ModelPrediction
    from app.models.risk import BankrollRiskPolicy


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_user_id", "user_id"),
        Index("ix_tickets_bankroll_id", "bankroll_id"),
        Index("ix_tickets_batch_id", "batch_id"),
        Index("ix_tickets_user_status_created", "user_id", "status", "created_at"),
        Index("ix_tickets_open_exposure", "bankroll_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    bankroll_id: Mapped[int | None] = mapped_column(ForeignKey("bankrolls.id", ondelete="SET NULL"), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_batches.id", ondelete="SET NULL"), nullable=True)
    ticket_type: Mapped[str] = mapped_column(String(50), default="single", nullable=False)
    stake: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("10.00"), nullable=False)
    total_odds: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    potential_return: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    risk_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("bankroll_risk_policies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    risk_policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    staking_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    bankroll: Mapped["Bankroll | None"] = relationship("Bankroll", back_populates="tickets")
    batch: Mapped["TicketBatch | None"] = relationship("TicketBatch", back_populates="tickets")
    legs: Mapped[list["TicketLeg"]] = relationship("TicketLeg", back_populates="ticket", cascade="all, delete-orphan")
    placements: Mapped[list["BetPlacement"]] = relationship(
        "BetPlacement", back_populates="ticket", cascade="all, delete-orphan"
    )
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="ticket", cascade="all, delete-orphan"
    )
    risk_policy: Mapped["BankrollRiskPolicy | None"] = relationship("BankrollRiskPolicy")


class TicketBatch(Base):
    __tablename__ = "ticket_batches"
    __table_args__ = (
        Index("ix_ticket_batches_bankroll_revision", "bankroll_id", "revision"),
        UniqueConstraint("scheduled_job_run_id", name="uq_ticket_batches_scheduled_job_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bankroll_id: Mapped[int | None] = mapped_column(ForeignKey("bankrolls.id", ondelete="SET NULL"), nullable=True)
    source_prediction_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # A scheduled run may be delivered again after the business transaction
    # commits but before the worker persists its terminal state. This durable
    # key turns replay into a lookup instead of a second ticket batch.
    scheduled_job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_job_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tickets_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_stake: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    generation_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    risk_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("bankroll_risk_policies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    risk_policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    staking_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    activation_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_evaluation_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_evaluations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    bankroll: Mapped["Bankroll | None"] = relationship("Bankroll", back_populates="ticket_batches")
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="batch", cascade="all, delete-orphan")
    risk_policy: Mapped["BankrollRiskPolicy | None"] = relationship("BankrollRiskPolicy")
    model_evaluation: Mapped["ModelEvaluation | None"] = relationship("ModelEvaluation")

    @property
    def source_prediction_run_ids(self) -> list[int]:
        report = self.generation_report if isinstance(self.generation_report, dict) else {}
        values = report.get("prediction_run_ids")
        if isinstance(values, list):
            normalized = []
            for value in values:
                try:
                    run_id = int(value)
                except (TypeError, ValueError):
                    continue
                if run_id > 0:
                    normalized.append(run_id)
            if normalized:
                return list(dict.fromkeys(normalized))
        return [self.source_prediction_run_id] if self.source_prediction_run_id is not None else []


class TicketLeg(Base):
    __tablename__ = "ticket_legs"
    __table_args__ = (
        Index("ix_ticket_legs_ticket_id", "ticket_id"),
        Index("ix_ticket_legs_ticket_status", "ticket_id", "status"),
        Index("ix_ticket_legs_model_prediction_id", "model_prediction_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    model_prediction_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_predictions.id", ondelete="SET NULL"), nullable=True
    )
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    selection: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    odds: Mapped[float] = mapped_column(Float, nullable=False)
    bookmaker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Immutable generation-time evidence. These nullable snapshots keep old
    # rows valid and preserve the decision basis even when the linked model
    # prediction is later deleted or its quality payload evolves.
    prediction_run_id_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_probability_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_probability_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_probability_basis_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expected_value_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    edge_pct_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    reliability_label_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reliability_score_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="legs")
    match: Mapped["Match | None"] = relationship("Match", back_populates="ticket_legs")
    model_prediction: Mapped["ModelPrediction | None"] = relationship("ModelPrediction")
    quote_snapshots: Mapped[list["TicketLegQuoteSnapshot"]] = relationship(
        "TicketLegQuoteSnapshot", cascade="all, delete-orphan"
    )


class BetPlacement(Base):
    __tablename__ = "bet_placements"
    __table_args__ = (Index("ix_bet_placements_ticket_id", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    bookmaker_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookmaker_accounts.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="placements")
    bookmaker_account: Mapped["BookmakerAccount | None"] = relationship("BookmakerAccount", back_populates="placements")
    settlement: Mapped["Settlement | None"] = relationship(
        "Settlement", back_populates="placement", uselist=False, cascade="all, delete-orphan"
    )
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="placement", cascade="all, delete-orphan"
    )


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bet_placement_id: Mapped[int | None] = mapped_column(
        ForeignKey("bet_placements.id", ondelete="CASCADE"), nullable=True
    )
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    return_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)

    placement: Mapped["BetPlacement | None"] = relationship("BetPlacement", back_populates="settlement")
    ticket: Mapped["Ticket | None"] = relationship("Ticket")
