from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RiskPolicyWriteRequest(BaseModel):
    staking_mode: Literal["flat_percent", "fractional_kelly"]
    flat_stake_pct: Decimal | None = Field(default=None, gt=0, le=Decimal("0.05"))
    kelly_fraction: Decimal | None = Field(default=None, gt=0, le=Decimal("0.50"))
    max_ticket_pct: Decimal = Field(gt=0, le=Decimal("0.05"))
    max_open_exposure_pct: Decimal = Field(gt=0, le=Decimal("0.20"))
    max_match_pct: Decimal = Field(gt=0, le=Decimal("0.20"))
    max_team_pct: Decimal = Field(gt=0, le=Decimal("0.20"))
    max_league_window_pct: Decimal = Field(gt=0, le=Decimal("0.20"))
    league_window_hours: int = Field(gt=0, le=24)
    max_daily_stake_pct: Decimal = Field(gt=0, le=Decimal("1.00"))
    max_weekly_stake_pct: Decimal = Field(gt=0, le=Decimal("1.00"))
    max_daily_ticket_count: int = Field(gt=0, le=1000)
    max_weekly_ticket_count: int = Field(gt=0, le=5000)
    accumulators_enabled: bool
    automation_enabled: bool

    @model_validator(mode="after")
    def validate_complete_policy(self):
        if self.staking_mode == "flat_percent":
            if self.flat_stake_pct is None or self.kelly_fraction is not None:
                raise ValueError("flat_percent requires flat_stake_pct and forbids kelly_fraction")
        elif self.kelly_fraction is None or self.flat_stake_pct is not None:
            raise ValueError("fractional_kelly requires kelly_fraction and forbids flat_stake_pct")
        if self.max_daily_stake_pct > self.max_weekly_stake_pct:
            raise ValueError("max_daily_stake_pct cannot exceed max_weekly_stake_pct")
        if self.max_daily_ticket_count > self.max_weekly_ticket_count:
            raise ValueError("max_daily_ticket_count cannot exceed max_weekly_ticket_count")
        for value, field in (
            (self.max_match_pct, "max_match_pct"),
            (self.max_team_pct, "max_team_pct"),
            (self.max_league_window_pct, "max_league_window_pct"),
        ):
            if value > self.max_open_exposure_pct:
                raise ValueError(f"{field} cannot exceed max_open_exposure_pct")
        if self.flat_stake_pct is not None and self.flat_stake_pct > self.max_ticket_pct:
            raise ValueError("flat_stake_pct cannot exceed max_ticket_pct")
        return self


class RiskPolicyResponse(RiskPolicyWriteRequest):
    id: int
    bankroll_id: int
    version: int
    effective_from: datetime
    created_at: datetime


class RiskUsageResponse(BaseModel):
    bankroll_balance: Decimal | None = None
    available_balance: Decimal | None = None
    open_exposure_amount: Decimal = Decimal("0.00")
    open_exposure_pct: Decimal | None = None
    staked_last_24h: Decimal = Decimal("0.00")
    staked_last_7d: Decimal = Decimal("0.00")
    ticket_count_last_24h: int = 0
    ticket_count_last_7d: int = 0


class RiskPauseStateResponse(BaseModel):
    paused_until: datetime | None = None
    pause_reason: str | None = None
    updated_at: datetime | None = None


class RiskPolicyEnvelope(BaseModel):
    policy: RiskPolicyResponse | None = None
    pending_policy: RiskPolicyWriteRequest | None = None
    pending_effective_at: datetime | None = None
    state: RiskPauseStateResponse | None = None
    usage: RiskUsageResponse = Field(default_factory=RiskUsageResponse)
    hard_max_ticket_pct: Decimal = Decimal("0.05")
    hard_max_open_exposure_pct: Decimal = Decimal("0.20")


class RiskPauseRequest(BaseModel):
    paused_until: datetime
    pause_reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_timezone(self):
        if self.paused_until.tzinfo is None or self.paused_until.utcoffset() is None:
            raise ValueError("paused_until must be timezone-aware")
        return self
