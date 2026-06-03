"""Momentum scorer — computes live momentum from match statistics.

Implements the formula from Case Study 1 (Momentum Edge Detection):
  M(t) = w1*xG_diff + w2*SoT_diff*0.1 + w3*(possession-50)*0.02
       + w4*dangerous_attacks_diff*0.005 + w5*cards_diff*(-0.05)

Where weights default to w=[0.5, 0.2, 0.1, 0.15, 0.05].
"""
from __future__ import annotations

from typing import Any


class MomentumScore:
    """Live momentum score for a match at a given minute."""

    def __init__(
        self,
        match_id: str,
        elapsed: int,
        home: float,
        away: float,
        raw_components: dict[str, float] | None = None,
    ) -> None:
        self.match_id = match_id
        self.elapsed = elapsed
        self.home = home
        self.away = away
        self.raw_components = raw_components or {}

    @property
    def differential(self) -> float:
        """Positive = home dominating, negative = away dominating."""
        return self.home - self.away

    @property
    def home_intensity(self) -> str:
        if self.home > 2.0:
            return "overwhelming"
        if self.home > 1.0:
            return "strong"
        if self.home > 0.3:
            return "moderate"
        return "neutral"

    @property
    def away_intensity(self) -> str:
        if self.away > 2.0:
            return "overwhelming"
        if self.away > 1.0:
            return "strong"
        if self.away > 0.3:
            return "moderate"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "elapsed": self.elapsed,
            "home_score": round(self.home, 3),
            "away_score": round(self.away, 3),
            "differential": round(self.differential, 3),
            "home_intensity": self.home_intensity,
            "away_intensity": self.away_intensity,
        }


class LiveMomentumScorer:
    """Computes momentum from a MatchStat row or raw stat dict.

    Formula:
      M_home = w1 * xG_diff + w2 * (SoT_home - SoT_away) * 0.1
             + w3 * (possession_home - 50) * 0.02
             + w4 * (dangerous_attacks_home - dangerous_attacks_away) * 0.005
             + w5 * (cards_home - cards_away) * (-0.05)

      M_away = -M_home (mirror)

    Each weight can be customized. Defaults tuned for Premier League.
    """

    def __init__(
        self,
        w_xg: float = 0.5,
        w_sot: float = 0.2,
        w_possession: float = 0.1,
        w_attacks: float = 0.15,
        w_cards: float = 0.05,
    ) -> None:
        self.w = [w_xg, w_sot, w_possession, w_attacks, w_cards]

    def score(self, match_id: str, stats: dict[str, Any]) -> MomentumScore:
        """Compute momentum from a flat stat dict.

        Expected keys:
          elapsed, xg_home, xg_away, shots_on_target_home, shots_on_target_away,
          possession_home, possession_away, dangerous_attacks_home, dangerous_attacks_away,
          cards_home, cards_away
        """
        elapsed = stats.get("elapsed", 0) or 0
        xg_h = stats.get("xg_home", 0.0) or 0.0
        xg_a = stats.get("xg_away", 0.0) or 0.0
        sot_h = stats.get("shots_on_target_home", 0) or 0
        sot_a = stats.get("shots_on_target_away", 0) or 0
        poss_h = stats.get("possession_home", 50.0) or 50.0
        poss_a = stats.get("possession_away", 50.0) or 50.0
        att_h = stats.get("dangerous_attacks_home", 0) or 0
        att_a = stats.get("dangerous_attacks_away", 0) or 0
        cards_h = stats.get("cards_home", 0) or 0
        cards_a = stats.get("cards_away", 0) or 0

        # Component deltas (home - away)
        dxg = xg_h - xg_a
        dsot = sot_h - sot_a
        dposs = poss_h - poss_a
        datt = att_h - att_a
        dcards = cards_h - cards_a

        w1, w2, w3, w4, w5 = self.w
        home_score = (
            w1 * dxg
            + w2 * dsot * 0.1
            + w3 * dposs * 0.02
            + w4 * datt * 0.005
            + w5 * dcards * (-0.05)
        )
        # Away is mirror
        away_score = -home_score

        components = {
            "dxg": round(dxg, 3),
            "dsot": dsot,
            "dposs": round(dposs, 1),
            "datt": datt,
            "dcards": dcards,
        }

        if home_score < 0:
            home_score = max(home_score, -5.0)
        else:
            home_score = min(home_score, 5.0)
        if away_score < 0:
            away_score = max(away_score, -5.0)
        else:
            away_score = min(away_score, 5.0)

        return MomentumScore(
            match_id=match_id,
            elapsed=elapsed,
            home=home_score,
            away=away_score,
            raw_components=components,
        )

    def score_from_matchstat(self, match_id: str, stat_row: Any) -> MomentumScore:
        """Compute momentum from a MatchStat ORM object."""
        stats = {
            "elapsed": stat_row.elapsed,
            "xg_home": stat_row.xg_home,
            "xg_away": stat_row.xg_away,
            "shots_on_target_home": stat_row.shots_on_target_home,
            "shots_on_target_away": stat_row.shots_on_target_away,
            "possession_home": stat_row.possession_home,
            "possession_away": stat_row.possession_away,
            "dangerous_attacks_home": stat_row.dangerous_attacks_home,
            "dangerous_attacks_away": stat_row.dangerous_attacks_away,
            "cards_home": stat_row.cards_home,
            "cards_away": stat_row.cards_away,
        }
        return self.score(match_id, stats)