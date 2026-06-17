from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.bankroll import Bankroll, BookmakerAccount, LedgerEntry
    from app.models.match import Match
    from app.models.prediction import ModelPrediction


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    bankroll_id: Mapped[int | None] = mapped_column(ForeignKey("bankrolls.id", ondelete="SET NULL"), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_batches.id", ondelete="SET NULL"), nullable=True)
    ticket_type: Mapped[str] = mapped_column(String(50), default="single", nullable=False)
    stake: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    total_odds: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    potential_return: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
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


class TicketBatch(Base):
    __tablename__ = "ticket_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bankroll_id: Mapped[int | None] = mapped_column(ForeignKey("bankrolls.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tickets_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_stake: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    bankroll: Mapped["Bankroll | None"] = relationship("Bankroll", back_populates="ticket_batches")
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="batch", cascade="all, delete-orphan")


class TicketLeg(Base):
    __tablename__ = "ticket_legs"

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
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="legs")
    match: Mapped["Match | None"] = relationship("Match", back_populates="ticket_legs")
    model_prediction: Mapped["ModelPrediction | None"] = relationship("ModelPrediction")


class BetPlacement(Base):
    __tablename__ = "bet_placements"

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
    return_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    placement: Mapped["BetPlacement | None"] = relationship("BetPlacement", back_populates="settlement")
    ticket: Mapped["Ticket | None"] = relationship("Ticket")
