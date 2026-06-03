"""Risk manager."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.live_engine.value_detector import ValueSignal


class RiskManager:
    def __init__(self, bankroll_balance: Decimal, kelly_fraction: float = 0.5,
                 max_exposure_per_match: Decimal = Decimal("50.0"),
                 max_daily_loss: Decimal = Decimal("200.0"),
                 max_concurrent_positions: int = 5,
                 min_odds: float = 1.5, max_odds: float = 20.0) -> None:
        self.bankroll_balance = bankroll_balance
        self.kelly_fraction = kelly_fraction
        self.max_exposure_per_match = max_exposure_per_match
        self.max_daily_loss = max_daily_loss
        self.max_concurrent_positions = max_concurrent_positions
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.daily_pnl: Decimal = Decimal("0")
        self.open_positions: int = 0
        self.exposure_by_match: dict[str, Decimal] = {}

    def approve(self, signal: ValueSignal) -> tuple[bool, str]:
        if signal.kelly_stake_fraction <= 0:
            return False, "kelly_negative"
        if signal.odds < self.min_odds:
            return False, "odds_too_low"
        if signal.odds > self.max_odds:
            return False, "odds_too_high"
        stake = signal.recommended_stake
        if stake < Decimal("0.01"):
            return False, "stake_too_small"
        current = self.exposure_by_match.get(signal.match_id, Decimal("0"))
        if current + stake > self.max_exposure_per_match:
            return False, "max_exposure_per_match"
        if self.open_positions >= self.max_concurrent_positions:
            return False, "max_concurrent_positions"
        if self.daily_pnl - stake < -self.max_daily_loss:
            return False, "daily_loss_limit"
        if signal.available_size < float(stake):
            return False, "insufficient_liquidity"
        return True, "approved"

    def record_position(self, signal: ValueSignal) -> None:
        self.open_positions += 1
        self.exposure_by_match[signal.match_id] = self.exposure_by_match.get(signal.match_id, Decimal("0")) + signal.recommended_stake

    def to_dict(self) -> dict[str, Any]:
        return {"bankroll_balance": float(self.bankroll_balance), "kelly_fraction": self.kelly_fraction,
                "daily_pnl": float(self.daily_pnl), "open_positions": self.open_positions,
                "max_concurrent_positions": self.max_concurrent_positions,
                "exposure_by_match": {k: float(v) for k, v in self.exposure_by_match.items()}}