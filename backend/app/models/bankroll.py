"""Bankroll, BookmakerAccount, LedgerEntry, Ticket models."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant")


class Bankroll(Base):
    __tablename__ = "bankroll"

    user_id: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(10), default="paper", nullable=False, comment="paper | real | sandbox")
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    start_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=1000.00, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=1000.00, nullable=False)
    kelly_fraction: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="bankrolls")
    accounts: Mapped[list["BookmakerAccount"]] = relationship("BookmakerAccount", back_populates="bankroll")
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="bankroll_ref")


class BookmakerAccount(Base):
    __tablename__ = "bookmaker_account"

    bankroll_id: Mapped[str] = mapped_column(ForeignKey("bankroll.id", ondelete="CASCADE"), nullable=False, index=True)
    bookmaker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0.00, nullable=False)
    deposit_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    bankroll: Mapped["Bankroll"] = relationship("Bankroll", back_populates="accounts")
    placements: Mapped[list["BetPlacement"]] = relationship("BetPlacement", back_populates="bookmaker_account")


class LedgerEntry(Base):
    __tablename__ = "ledger_entry"

    bankroll_id: Mapped[str] = mapped_column(ForeignKey("bankroll.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("ticket.id", ondelete="SET NULL"), nullable=True)
    placement_id: Mapped[str | None] = mapped_column(ForeignKey("bet_placement.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, comment="deposit | withdraw | stake | win | loss | adjust")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)


class Ticket(Base):
    __tablename__ = "ticket"

    bankroll_id: Mapped[str] = mapped_column(ForeignKey("bankroll.id", ondelete="CASCADE"), nullable=False, index=True)
    reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="pending", nullable=False)
    total_stake: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0.00, nullable=False)
    total_odds: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    settled_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bankroll_ref: Mapped["Bankroll"] = relationship("Bankroll", back_populates="tickets")
    legs: Mapped[list["TicketLeg"]] = relationship("TicketLeg", back_populates="ticket")


class TicketLeg(Base):
    __tablename__ = "ticket_leg"

    ticket_id: Mapped[str] = mapped_column(ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False, index=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    market_type: Mapped[str] = mapped_column(String(30), default="1x2", nullable=False)
    selection: Mapped[str] = mapped_column(String(20), nullable=False, comment="home | draw | away")
    side: Mapped[str] = mapped_column(String(4), nullable=False, comment="back | lay")
    odds: Mapped[float] = mapped_column(Float, nullable=False)
    stake: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="pending", nullable=False)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="legs")
    match: Mapped["Match"] = relationship("Match", back_populates="ticket_legs")


class BetPlacement(Base):
    __tablename__ = "bet_placement"

    bookmaker_account_id: Mapped[str] = mapped_column(ForeignKey("bookmaker_account.id", ondelete="CASCADE"), nullable=False, index=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    odds: Mapped[float] = mapped_column(Float, nullable=False)
    stake: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="pending", nullable=False)
    placed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)

    bookmaker_account: Mapped["BookmakerAccount"] = relationship("BookmakerAccount", back_populates="placements")