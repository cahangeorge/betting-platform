"""Prediction quality and market-consensus guardrails.

The prediction models come from penaltyblog, match/odds data comes from
OddsHarvester/soccerdata-backed storage, and this module turns those signals
into a stable report that the API/UI can expose and ticket generation can trust.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

MIN_TEAM_HISTORY_MATCHES = 8
MIN_GLOBAL_TRAINING_MATCHES = 50
HIGH_MARKET_DISAGREEMENT_PP = 20.0
MIN_TICKET_EDGE_PCT = 2.5

OutcomeOdds = dict[str, dict[str, float | str] | None]


def _normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9_:.]+", "", (value or "").strip().lower())


def _market_base(value: str | None) -> str:
    normalized = _normalize(value)
    return normalized.split(":", 1)[0]


def _line_token(value: str | None) -> str:
    match = re.search(r"\d+_\d+|\d+\.\d+|\d+", _normalize(value))
    return match.group(0).replace("_", ".") if match else ""


def _market_aliases(prediction_market: str) -> set[str]:
    base = _market_base(prediction_market)
    aliases = {base}
    if base in {"1x2", "match_winner", "home_away", "matchwinner"}:
        aliases.update({"1x2", "match_winner", "home_away", "matchwinner"})
    if base in {"btts", "both_teams_to_score", "bothteams", "bt_ts", "btts_yes_no"}:
        aliases.update({"btts", "both_teams_to_score", "bothteams", "bt_ts", "btts_yes_no"})
    if base in {"ou_2_5", "ou25", "ou2_5", "over_under", "overunder", "totals"}:
        aliases.update({"ou_2_5", "ou25", "ou2_5", "over_under", "overunder", "totals"})
    return aliases


def market_matches(prediction_market: str, odds_market: str | None) -> bool:
    candidate_base = _market_base(odds_market)
    if candidate_base not in _market_aliases(prediction_market):
        return False

    prediction_base = _market_base(prediction_market)
    if prediction_base in {"ou_2_5", "ou25", "ou2_5", "over_under", "overunder", "totals"}:
        return _line_token(prediction_market) in {"", "2.5", "2.50"} and _line_token(odds_market) in {
            "2.5",
            "2.50",
        }
    return True


def market_outcomes(market: str) -> list[str]:
    base = _market_base(market)
    if base in _market_aliases("1x2"):
        return ["home", "draw", "away"]
    if base in _market_aliases("btts"):
        return ["yes", "no"]
    if base in _market_aliases("ou_2_5"):
        return ["over", "under"]
    return []


def outcome_odds_field(outcome: str) -> str | None:
    return {
        "home": "home_odds",
        "draw": "draw_odds",
        "away": "away_odds",
        "yes": "home_odds",
        "no": "away_odds",
        "over": "home_odds",
        "under": "away_odds",
    }.get(outcome)


def team_training_stats(training_matches: Iterable[Any], team: str) -> dict[str, int]:
    stats = {"matches": 0, "wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0}
    for match in training_matches:
        home = getattr(match, "home_team", None)
        away = getattr(match, "away_team", None)
        home_score = getattr(match, "home_score", None)
        away_score = getattr(match, "away_score", None)
        if home_score is None or away_score is None:
            continue
        if home == team:
            gf, ga = int(home_score), int(away_score)
        elif away == team:
            gf, ga = int(away_score), int(home_score)
        else:
            continue

        stats["matches"] += 1
        stats["goals_for"] += gf
        stats["goals_against"] += ga
        if gf > ga:
            stats["wins"] += 1
        elif gf < ga:
            stats["losses"] += 1
        else:
            stats["draws"] += 1
    return stats


def best_market_odds_by_outcome(prediction_market: str, odds_entries: Iterable[Any]) -> OutcomeOdds:
    best: OutcomeOdds = {outcome: None for outcome in market_outcomes(prediction_market)}
    for odds in odds_entries:
        if not market_matches(prediction_market, getattr(odds, "market", None)):
            continue
        for outcome in list(best):
            field = outcome_odds_field(outcome)
            value = getattr(odds, field, None) if field else None
            if value is None or value <= 1:
                continue
            current = best[outcome]
            if current is None or float(value) > float(current["odds"]):
                best[outcome] = {"odds": float(value), "bookmaker": getattr(odds, "bookmaker", "") or ""}
    return best


def _fallback_implied_probabilities(odds_by_outcome: OutcomeOdds) -> dict[str, float]:
    raw = {outcome: 1.0 / float(payload["odds"]) for outcome, payload in odds_by_outcome.items() if payload}
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {outcome: value / total for outcome, value in raw.items()}


def build_market_consensus(
    prediction_market: str,
    odds_entries: Iterable[Any],
    *,
    implied_probabilities: dict[str, float] | None = None,
) -> dict[str, Any]:
    odds = best_market_odds_by_outcome(prediction_market, odds_entries)
    probabilities = implied_probabilities or _fallback_implied_probabilities(odds)
    pick = max(probabilities.items(), key=lambda item: item[1])[0] if probabilities else None
    return {
        "pick": pick,
        "probabilities": {key: round(float(value), 6) for key, value in probabilities.items()},
        "odds": odds,
    }


def _model_pick(probabilities: dict[str, float]) -> str | None:
    valid = {outcome: float(prob) for outcome, prob in probabilities.items() if prob is not None}
    return max(valid.items(), key=lambda item: item[1])[0] if valid else None


def _edge_for_outcomes(
    model_probabilities: dict[str, float],
    odds_by_outcome: OutcomeOdds | None,
) -> dict[str, float | None]:
    odds_by_outcome = odds_by_outcome or {}
    edge: dict[str, float | None] = {}
    for outcome, probability in model_probabilities.items():
        payload = odds_by_outcome.get(outcome)
        edge[outcome] = round((float(probability) * float(payload["odds"]) - 1.0) * 100, 3) if payload else None
    return edge


def evaluate_prediction_quality(
    *,
    training_matches: Iterable[Any],
    target_match: Any,
    market: str,
    model_probabilities: dict[str, float],
    market_consensus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    training_list = list(training_matches)
    home_team = getattr(target_match, "home_team", "")
    away_team = getattr(target_match, "away_team", "")
    home_stats = team_training_stats(training_list, home_team)
    away_stats = team_training_stats(training_list, away_team)
    model_pick = _model_pick(model_probabilities)
    consensus = market_consensus or {"pick": None, "probabilities": {}, "odds": {}}
    market_probs = consensus.get("probabilities") or {}
    odds = consensus.get("odds") or {}
    edge = _edge_for_outcomes(model_probabilities, odds)

    block_reasons: list[str] = []
    reliability_reasons: list[str] = []
    if len(training_list) < MIN_GLOBAL_TRAINING_MATCHES:
        block_reasons.append("insufficient_global_training_history")
        reliability_reasons.append("insufficient_global_training_history")
    if home_stats["matches"] < MIN_TEAM_HISTORY_MATCHES:
        block_reasons.append("insufficient_home_team_history")
        reliability_reasons.append("insufficient_home_team_history")
    if away_stats["matches"] < MIN_TEAM_HISTORY_MATCHES:
        block_reasons.append("insufficient_away_team_history")
        reliability_reasons.append("insufficient_away_team_history")

    market_pick = consensus.get("pick")
    pick_market_probability = float(market_probs.get(model_pick, 0.0) or 0.0) if model_pick else 0.0
    pick_model_probability = float(model_probabilities.get(model_pick, 0.0) or 0.0) if model_pick else 0.0
    market_gap_pp = round((pick_model_probability - pick_market_probability) * 100, 3)
    if market_pick and model_pick and market_pick != model_pick and abs(market_gap_pp) >= HIGH_MARKET_DISAGREEMENT_PP:
        block_reasons.append("market_disagreement")
        reliability_reasons.append("market_disagreement")

    pick_edge_pct = edge.get(model_pick) if model_pick else None
    if pick_edge_pct is None:
        block_reasons.append("missing_market_odds")
    elif pick_edge_pct < MIN_TICKET_EDGE_PCT:
        block_reasons.append("edge_below_ticket_threshold")

    if reliability_reasons:
        label = "unreliable"
    elif min(home_stats["matches"], away_stats["matches"]) < 15:
        label = "moderate"
    else:
        label = "reliable"

    score = 100
    score -= max(0, MIN_GLOBAL_TRAINING_MATCHES - len(training_list))
    score -= max(0, MIN_TEAM_HISTORY_MATCHES - home_stats["matches"]) * 6
    score -= max(0, MIN_TEAM_HISTORY_MATCHES - away_stats["matches"]) * 6
    if "market_disagreement" in block_reasons:
        score -= 25
    if "edge_below_ticket_threshold" in block_reasons:
        score -= 10
    score = max(0, min(100, score))

    return {
        "schema_version": 1,
        "training": {
            "total_matches": len(training_list),
            "min_team_history_matches": MIN_TEAM_HISTORY_MATCHES,
            "min_global_training_matches": MIN_GLOBAL_TRAINING_MATCHES,
            "home_team": home_stats,
            "away_team": away_stats,
        },
        "model": {
            "pick": model_pick,
            "probabilities": {key: round(float(value), 6) for key, value in model_probabilities.items()},
        },
        "market": consensus,
        "edge": {**edge, "pick_edge_pct": pick_edge_pct, "market_gap_pct": market_gap_pp},
        "reliability": {
            "label": label,
            "score": score,
            "is_ticket_eligible": not block_reasons,
            "block_reasons": block_reasons,
        },
    }
