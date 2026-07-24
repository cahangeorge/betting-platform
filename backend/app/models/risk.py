from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class BankrollRiskPolicy(Base):
    __tablename__ = "bankroll_risk_policies"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_bankroll_risk_policies_version"),
        CheckConstraint(
            "staking_mode IN ('flat_percent', 'fractional_kelly')",
            name="ck_bankroll_risk_policies_staking_mode",
        ),
        CheckConstraint(
            "(staking_mode = 'flat_percent' AND flat_stake_pct IS NOT NULL AND kelly_fraction IS NULL) "
            "OR (staking_mode = 'fractional_kelly' AND kelly_fraction IS NOT NULL AND flat_stake_pct IS NULL)",
            name="ck_bankroll_risk_policies_staking_fields",
        ),
        CheckConstraint(
            "flat_stake_pct IS NULL OR (flat_stake_pct > 0 AND flat_stake_pct <= 0.05)",
            name="ck_bankroll_risk_policies_flat_stake_pct",
        ),
        CheckConstraint(
            "kelly_fraction IS NULL OR (kelly_fraction > 0 AND kelly_fraction <= 0.5)",
            name="ck_bankroll_risk_policies_kelly_fraction",
        ),
        CheckConstraint(
            "max_ticket_pct > 0 AND max_ticket_pct <= 0.05",
            name="ck_bankroll_risk_policies_max_ticket_pct",
        ),
        CheckConstraint(
            "max_open_exposure_pct > 0 AND max_open_exposure_pct <= 0.20",
            name="ck_bankroll_risk_policies_max_open_exposure_pct",
        ),
        CheckConstraint(
            "max_match_pct IS NULL OR (max_match_pct > 0 AND max_match_pct <= 0.20)",
            name="ck_bankroll_risk_policies_max_match_pct",
        ),
        CheckConstraint(
            "max_team_pct IS NULL OR (max_team_pct > 0 AND max_team_pct <= 0.20)",
            name="ck_bankroll_risk_policies_max_team_pct",
        ),
        CheckConstraint(
            "max_league_window_pct IS NULL OR (max_league_window_pct > 0 AND max_league_window_pct <= 0.20)",
            name="ck_bankroll_risk_policies_max_league_window_pct",
        ),
        CheckConstraint(
            "max_daily_stake_pct IS NULL OR (max_daily_stake_pct > 0 AND max_daily_stake_pct <= 1.0)",
            name="ck_bankroll_risk_policies_max_daily_stake_pct",
        ),
        CheckConstraint(
            "max_weekly_stake_pct IS NULL OR (max_weekly_stake_pct > 0 AND max_weekly_stake_pct <= 1.0)",
            name="ck_bankroll_risk_policies_max_weekly_stake_pct",
        ),
        CheckConstraint("league_window_hours > 0", name="ck_bankroll_risk_policies_league_window_hours"),
        UniqueConstraint("bankroll_id", "version", name="uq_bankroll_risk_policies_bankroll_version"),
        Index(
            "uq_bankroll_risk_policies_active",
            "bankroll_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
            sqlite_where=text("superseded_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bankroll_id: Mapped[int] = mapped_column(ForeignKey("bankrolls.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    staking_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    flat_stake_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    kelly_fraction: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    max_ticket_pct: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    max_open_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    max_match_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    max_team_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    max_league_window_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    league_window_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    max_daily_stake_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    max_weekly_stake_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    max_daily_ticket_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_weekly_ticket_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accumulators_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BankrollRiskState(Base):
    __tablename__ = "bankroll_risk_states"

    bankroll_id: Mapped[int] = mapped_column(ForeignKey("bankrolls.id", ondelete="CASCADE"), primary_key=True)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pending_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pending_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
