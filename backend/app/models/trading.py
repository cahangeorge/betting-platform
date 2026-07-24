from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.match import OddsEntry
    from app.models.model_governance import ModelEvaluation
    from app.models.odds_lineage import OddsSnapshot
    from app.models.ticket import Ticket
    from app.models.user import User


class TradingAccount(Base):
    __tablename__ = "trading_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="paper-local", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="paper", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("1000.00"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User")
    intents: Mapped[list["ExecutionIntent"]] = relationship(
        "ExecutionIntent", back_populates="account", cascade="all, delete-orphan"
    )


class ExecutionIntent(Base):
    __tablename__ = "execution_intents"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_execution_intents_user_key"),
        UniqueConstraint("user_id", "ticket_id", name="uq_execution_intents_user_ticket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    trading_account_id: Mapped[int] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True)
    odds_entry_id: Mapped[int] = mapped_column(
        ForeignKey("odds_entries.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    odds_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("odds_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_evaluation_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_evaluations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="paper", nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    selection: Mapped[str] = mapped_column(String(50), nullable=False)
    side: Mapped[str] = mapped_column(String(10), default="BACK", nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), default="LIMIT", nullable=False)
    stake: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False, index=True)
    transport: Mapped[str] = mapped_column(String(20), default="inprocess", nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    transport_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped["TradingAccount"] = relationship("TradingAccount", back_populates="intents")
    ticket: Mapped["Ticket"] = relationship("Ticket")
    odds_entry: Mapped["OddsEntry"] = relationship("OddsEntry")
    odds_snapshot: Mapped["OddsSnapshot | None"] = relationship("OddsSnapshot")
    model_evaluation: Mapped["ModelEvaluation | None"] = relationship("ModelEvaluation")
    orders: Mapped[list["ExecutionOrder"]] = relationship(
        "ExecutionOrder", back_populates="intent", cascade="all, delete-orphan"
    )
    events: Mapped[list["ExecutionEvent"]] = relationship(
        "ExecutionEvent", back_populates="intent", cascade="all, delete-orphan", order_by="ExecutionEvent.id"
    )


class ExecutionOrder(Base):
    __tablename__ = "execution_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_intent_id: Mapped[int] = mapped_column(
        ForeignKey("execution_intents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), default="paper-local", nullable=False)
    external_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="filled", nullable=False)
    requested_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    requested_size: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    matched_size: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    intent: Mapped["ExecutionIntent"] = relationship("ExecutionIntent", back_populates="orders")


class ExecutionEvent(Base):
    __tablename__ = "execution_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_intent_id: Mapped[int] = mapped_column(
        ForeignKey("execution_intents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    intent: Mapped["ExecutionIntent"] = relationship("ExecutionIntent", back_populates="events")
