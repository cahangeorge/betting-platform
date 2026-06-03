"""Calibration evaluation metrics for 1X2 predictions."""
from __future__ import annotations

from typing import Any


def expected_calibration_error(
    predictions: list[dict[str, float]],
    outcomes: list[str],
    n_bins: int = 10,
) -> float:
    """Compute ECE for 1X2 predictions with flexible key naming."""
    if not predictions or len(predictions) != len(outcomes):
        return 1.0
    ece = 0.0
    for outcome in ["home", "draw", "away"]:
        prob_key = f"{outcome}_win" if outcome != "draw" else "draw"
        probs = [p.get(prob_key, p.get(outcome, 0.0)) for p in predictions]
        correct = [1 if o == outcome else 0 for o in outcomes]
        bin_edges = [i / n_bins for i in range(n_bins + 1)]
        for i in range(n_bins):
            lo, hi = bin_edges[i], bin_edges[i + 1]
            mask = [lo <= p < hi for p in probs]
            n = sum(mask)
            if n == 0:
                continue
            avg_prob = sum(p for p, m in zip(probs, mask) if m) / n
            acc = sum(c for c, m in zip(correct, mask) if m) / n
            ece += (n / len(predictions)) * abs(avg_prob - acc)
    return ece


def backtest_1x2(
    predictions: list[dict[str, float]],
    outcomes: list[str],
    threshold_ev: float = 0.05,
    stake: float = 1.0,
) -> dict[str, Any]:
    """Simple P&L backtest: bet on any outcome with positive expected value."""
    trades = 0
    wins = 0
    pnl = 0.0

    for pred, outcome in zip(predictions, outcomes):
        for runner in ["home", "draw", "away"]:
            prob_key = f"{runner}_win" if runner != "draw" else "draw"
            prob = pred.get(prob_key, pred.get(runner, 0.0))
            if prob <= 0 or prob >= 0.99:
                continue
            fair_odds = 1.0 / prob
            market_odds = fair_odds * 0.95
            ev = (market_odds * prob) - 1.0
            if ev > threshold_ev:
                trades += 1
                if runner == outcome:
                    wins += 1
                    pnl += (market_odds - 1.0) * stake
                else:
                    pnl -= stake

    return {
        "trades": trades,
        "wins": wins,
        "win_rate": wins / trades if trades else 0.0,
        "pnl": round(pnl, 2),
        "roi": round(pnl / (trades * stake), 4) if trades else 0.0,
    }