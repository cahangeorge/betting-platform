"""Pydantic schemas for request/response validation."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, EmailStr


class MatchCreate(BaseModel):
    external_id: str = Field(..., max_length=120)
    home_team: str = Field(..., max_length=120)
    away_team: str = Field(..., max_length=120)
    league: str = Field(..., max_length=80)
    sport: str = Field(default="football", max_length=30)
    kickoff_time: datetime.datetime
    status: Literal["upcoming", "live", "finished", "postponed"] = "upcoming"
    home_score: int | None = None
    away_score: int | None = None
    betfair_market_id: str | None = Field(default=None, max_length=32)
    smarkets_market_id: str | None = Field(default=None, max_length=32)


class MatchOut(MatchCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class PredictionInput(BaseModel):
    home_team: str
    away_team: str
    league: str
    match_date: datetime.datetime | None = None


class PredictionOutput(BaseModel):
    model_name: str
    home_win_prob: Decimal
    draw_prob: Decimal
    away_win_prob: Decimal
    expected_goals_home: Decimal | None = None
    expected_goals_away: Decimal | None = None
    confidence: Literal["low", "medium", "high"] = "medium"
    timestamp: datetime.datetime


class BankrollCreate(BaseModel):
    name: str = Field(..., max_length=80)
    currency: str = Field(default="GBP")


class BankrollOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    name: str
    balance: Decimal
    currency: str
    is_active: bool
    created_at: datetime.datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserLoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BotStartIn(BaseModel):
    bankroll_id: str
    kelly_fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    edge_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    poll_interval_seconds: float = Field(default=5.0, ge=1.0)
    paper: bool = True
    exchange_whitelist: list[str] = Field(default=["betfair", "smarkets"])
    min_odds: float = Field(default=1.5, ge=1.01)
    max_odds: float = Field(default=20.0, ge=1.01)


class BotStatusOut(BaseModel):
    running: bool
    paper: bool
    cycles: int
    signals_found: int
    orders_placed: int
    orders_rejected: int
    errors: int
    last_cycle_at: str | None


class TradeLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    bankroll_id: str
    match_id: str | None
    market_id: str
    runner_id: int
    side: str
    status: str
    requested_odds: float
    requested_stake: Decimal
    average_price_matched: float | None
    size_matched: Decimal | None
    model_prob_at_entry: float | None
    edge_at_entry: float | None
    entry_time: datetime.datetime
    final_result: str | None
    profit_loss: Decimal | None


class PaperSettleIn(BaseModel):
    position_id: str
    result: str
    final_odds: float | None = None
    pnl: Decimal | None = None