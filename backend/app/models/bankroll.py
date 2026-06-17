from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.ticket import BetPlacement, Ticket, TicketBatch
    from app.models.user import User


class Bankroll(Base):
    __tablename__ = "bankrolls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="paper", nullable=False)
    balance: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)
    initial_balance: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="GBP", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="bankrolls")
    bookmaker_accounts: Mapped[list["BookmakerAccount"]] = relationship(
        "BookmakerAccount", back_populates="bankroll", cascade="all, delete-orphan"
    )
    ledger: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="bankroll", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="bankroll", cascade="all, delete-orphan")
    ticket_batches: Mapped[list["TicketBatch"]] = relationship(
        "TicketBatch", back_populates="bankroll", cascade="all, delete-orphan"
    )


class BookmakerAccount(Base):
    __tablename__ = "bookmaker_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bankroll_id: Mapped[int] = mapped_column(ForeignKey("bankrolls.id", ondelete="CASCADE"), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    bankroll: Mapped["Bankroll"] = relationship("Bankroll", back_populates="bookmaker_accounts")
    placements: Mapped[list["BetPlacement"]] = relationship(
        "BetPlacement", back_populates="bookmaker_account", cascade="all, delete-orphan"
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bankroll_id: Mapped[int] = mapped_column(ForeignKey("bankrolls.id", ondelete="CASCADE"), nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)
    placement_id: Mapped[int | None] = mapped_column(
        ForeignKey("bet_placements.id", ondelete="SET NULL"), nullable=True
    )
    entry_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    bankroll: Mapped["Bankroll"] = relationship("Bankroll", back_populates="ledger")
    ticket: Mapped["Ticket | None"] = relationship("Ticket", back_populates="ledger_entries")
    placement: Mapped["BetPlacement | None"] = relationship("BetPlacement", back_populates="ledger_entries")
