"""Live probability updater — adjusts model priors using live match context.

Applies Bayesian-style updates:
- Each goal scored: multiply implied prob by factor (0.6 for conceding, min(1.5, 0.95) for scoring)
- Momentum offset: M(t) * momentum_scale added to probabilities
- Elapsed time: residuals decay toward final odds as match progresses
"""
from __future__ import annotations

from typing import Any


class LiveProbabilityUpdater:
    """Adjusts a pre-match model prediction using live match state.

    Produces updated probabilities that reflect what's happened so far.
    """

    def __init__(
        self,
        goal_concede_factor: float = 0.6,
        goal_score_cap: float = 0.95,
        momentum_scale: float = 0.08,
        near_end_odds_decay: float = 0.3,
    ) -> None:
        self.goal_concede_factor = goal_concede_factor
        self.goal_score_cap = goal_score_cap
        self.momentum_scale = momentum_scale
        self.near_end_odds_decay = near_end_odds_decay

    def update(
        self,
        base_probs: dict[str, float],  # pre-match from model
        home_score: int,
        away_score: int,
        momentum_diff: float,  # from MomentumScore.differential
        elapsed: int = 0,
        total_minutes: int = 90,
    ) -> dict[str, float]:
        """Return updated {home, draw, away} probabilities."""
        h, d, a = base_probs["home"], base_probs["draw"], base_probs["away"]

        # 1. Scoreline adjustment — goals are strong signals
        for _ in range(home_score):
            a *= self.goal_concede_factor
            h = min(h * 1.4, self.goal_score_cap)
        for _ in range(away_score):
            h *= self.goal_concede_factor
            a = min(a * 1.4, self.goal_score_cap)

        # 2. Momentum adjustment
        if momentum_diff > 0:
            # Home has momentum → shift probability from away/draw to home
            shift = momentum_diff * self.momentum_scale
            h += shift
            a -= shift * 0.5
            d -= shift * 0.5
        elif momentum_diff < 0:
            shift = abs(momentum_diff) * self.momentum_scale
            a += shift
            h -= shift * 0.5
            d -= shift * 0.5

        # 3. Scoreline rebalancing — if one team is up by 2+ in 2nd half,
        #    overweight their win probability
        goal_diff = home_score - away_score
        time_ratio = elapsed / max(total_minutes, 1)
        if time_ratio > 0.5 and abs(goal_diff) >= 2:
            leader_bonus = abs(goal_diff) * 0.05 * time_ratio
            if goal_diff > 0:
                h += leader_bonus
                d -= leader_bonus * 0.4
                a -= leader_bonus * 0.6
            else:
                a += leader_bonus
                d -= leader_bonus * 0.4
                h -= leader_bonus * 0.6

        # 4. Clamp + renormalize
        h, d, a = max(0.01, h), max(0.01, d), max(0.01, a)
        total = h + d + a
        return {"home": h / total, "draw": d / total, "away": a / total}

    def update_from_match(
        self,
        base_probs: dict[str, float],
        match: Any,  # Match ORM object
        momentum_diff: float = 0.0,
        elapsed: int = 0,
    ) -> dict[str, float]:
        """Update using a Match ORM row (which has home_score/away_score)."""
        return self.update(
            base_probs=base_probs,
            home_score=match.home_score or 0,
            away_score=match.away_score or 0,
            momentum_diff=momentum_diff,
            elapsed=elapsed,
        )