"""Value detection engine."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


class ValueSignal:
    def __init__(self, match_id: str, exchange: str, market_id: str, runner: str,
                 side: str, model_prob: float, implied_prob: float, edge: float,
                 odds: float, available_size: float, kelly_fraction: float = 0.5,
                 max_bet: Decimal = Decimal("100.0")) -> None:
        self.match_id = match_id
        self.exchange = exchange
        self.market_id = market_id
        self.runner = runner
        self.side = side
        self.model_prob = model_prob
        self.implied_prob = implied_prob
        self.edge = edge
        self.odds = odds
        self.available_size = available_size
        self.kelly_fraction = kelly_fraction
        self.max_bet = max_bet

    @property
    def expected_value(self) -> float:
        return (self.odds * self.model_prob) - 1.0

    @property
    def kelly_stake_fraction(self) -> float:
        if self.odds <= 1.0 or self.model_prob <= 0.0:
            return 0.0
        b = self.odds - 1.0
        q = 1.0 - self.model_prob
        return self.model_prob - (q / b)

    @property
    def recommended_stake(self) -> Decimal:
        full_kelly = self.kelly_stake_fraction
        if full_kelly <= 0:
            return Decimal("0")
        stake = Decimal(str(full_kelly * self.kelly_fraction))
        if stake > self.max_bet:
            stake = self.max_bet
        if stake < Decimal("0.01"):
            return Decimal("0")
        return stake.quantize(Decimal("0.01"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id, "exchange": self.exchange,
            "market_id": self.market_id, "runner": self.runner,
            "side": self.side, "model_prob": round(self.model_prob, 4),
            "implied_prob": round(self.implied_prob, 4),
            "edge": round(self.edge, 4), "odds": self.odds,
            "available_size": self.available_size,
            "expected_value": round(self.expected_value, 4),
            "kelly_stake_fraction": round(self.kelly_stake_fraction, 4),
            "recommended_stake": float(self.recommended_stake),
        }


class ValueDetector:
    def __init__(self, edge_threshold: float = 0.15) -> None:
        self.edge_threshold = edge_threshold

    @staticmethod
    def implied_probability(odds: float, margin: float = 0.02) -> float:
        if odds <= 1.0:
            return 0.0
        raw = 1.0 / odds
        return raw / (1.0 + margin)

    @staticmethod
    def best_back_odds(available_to_back: list[dict[str, Any]]) -> tuple[float, float]:
        if not available_to_back:
            return 0.0, 0.0
        best = max(available_to_back, key=lambda x: x.get("price", 0.0))
        return best.get("price", 0.0), best.get("size", 0.0)

    def detect(self, match_id: str, model_probs: dict[str, float],
               live_odds_rows: list[dict[str, Any]], exchange: str,
               market_id: str, kelly_fraction: float = 0.5,
               max_bet: Decimal = Decimal("100.0")) -> list[ValueSignal]:
        signals: list[ValueSignal] = []
        for row in live_odds_rows:
            runner_key = row.get("runner", "").lower()
            if model_probs.get(runner_key, 0.0) <= 0:
                continue
            price, size = self.best_back_odds(row.get("available_to_back", []))
            if price <= 1.0:
                continue
            implied = self.implied_probability(price)
            edge = model_probs[runner_key] - implied
            if edge < self.edge_threshold:
                continue
            signals.append(ValueSignal(
                match_id=match_id, exchange=exchange, market_id=market_id,
                runner=runner_key, side="BACK",
                model_prob=model_probs[runner_key], implied_prob=implied,
                edge=edge, odds=price, available_size=size,
                kelly_fraction=kelly_fraction, max_bet=max_bet,
            ))
        return signals