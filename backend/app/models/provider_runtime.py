"""Generic runtime controls for quota-aware provider adapters."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ProviderSourceRuntimeState(Base):
    """One lockable state record per adapter/source, never per provider product."""

    __tablename__ = "provider_source_runtime_states"
    __table_args__ = (
        UniqueConstraint("adapter_key", "source_key", name="uq_provider_source_runtime_state_source"),
        CheckConstraint("quota_reserved >= 0", name="ck_provider_source_runtime_state_quota_reserved"),
        CheckConstraint("quota_consumed >= 0", name="ck_provider_source_runtime_state_quota_consumed"),
        CheckConstraint("consecutive_failures >= 0", name="ck_provider_source_runtime_state_failures"),
        CheckConstraint(
            "quota_window_seconds IS NULL OR quota_window_seconds > 0",
            name="ck_provider_source_runtime_state_quota_window_seconds",
        ),
        CheckConstraint(
            "circuit_state IN ('closed', 'open', 'half_open')",
            name="ck_provider_source_runtime_state_circuit",
        ),
        Index("ix_provider_source_runtime_state_circuit", "circuit_state", "circuit_open_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    adapter_key: Mapped[str] = mapped_column(String(63), nullable=False)
    source_key: Mapped[str] = mapped_column(String(63), nullable=False)
    quota_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quota_reserved: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    quota_consumed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    provider_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quota_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quota_window_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    circuit_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="closed")
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProviderQuotaReservation(Base):
    """Durable intent for one provider acquisition before any network egress.

    The ledger is deliberately separate from the aggregate runtime counter:
    the short reservation transaction can commit before an adapter leaves the
    process, and a later transaction can reconcile the exact same acquisition
    key without guessing whether an earlier worker already did so.
    """

    __tablename__ = "provider_quota_reservations"
    __table_args__ = (
        UniqueConstraint("reservation_key", name="uq_provider_quota_reservation_key"),
        CheckConstraint("units > 0", name="ck_provider_quota_reservation_units"),
        CheckConstraint(
            "status IN ('reserved', 'charged', 'released', 'uncertain')",
            name="ck_provider_quota_reservation_status",
        ),
        Index("ix_provider_quota_reservation_expiry", "status", "expires_at"),
        Index("ix_provider_quota_reservation_source", "adapter_key", "source_key", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    runtime_state_id: Mapped[int] = mapped_column(
        ForeignKey("provider_source_runtime_states.id", ondelete="RESTRICT"), nullable=False
    )
    reservation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(63), nullable=False)
    source_key: Mapped[str] = mapped_column(String(63), nullable=False)
    task_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="reserved")
    quota_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
