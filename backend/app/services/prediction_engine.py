import asyncio
import json
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, OddsEntry
from app.models.prediction import ModelPrediction, PredictionRun
from app.services.odds_quotes import QuoteSet, load_odds_entries, select_quote_set
from app.services.prediction_quality import (
    best_market_odds_by_outcome,
    evaluate_prediction_quality,
    market_outcomes,
)
from app.services.python_bridge import BridgeError, run_penaltyblog

MODEL_TYPE_ALIASES = {
    "poisson": "PoissonGoalsModel",
    "PoissonGoalsModel": "PoissonGoalsModel",
    "bivariate_poisson": "BivariatePoissonGoalModel",
    "BivariatePoissonGoalModel": "BivariatePoissonGoalModel",
    "dixon_coles": "DixonColesGoalModel",
    "DixonColesGoalModel": "DixonColesGoalModel",
    "negbin": "NegativeBinomialGoalModel",
    "NegativeBinomialGoalModel": "NegativeBinomialGoalModel",
    "zip": "ZeroInflatedPoissonGoalsModel",
    "ZeroInflatedPoissonGoalsModel": "ZeroInflatedPoissonGoalsModel",
    "weibull": "WeibullCopulaGoalsModel",
    "WeibullCopulaGoalsModel": "WeibullCopulaGoalsModel",
    "bayesian_goal": "BayesianGoalModel",
    "BayesianGoalModel": "BayesianGoalModel",
    "bayesian_hierarchical": "HierarchicalBayesianGoalModel",
    "HierarchicalBayesianGoalModel": "HierarchicalBayesianGoalModel",
}


def prediction_error_payload(summary: dict) -> str:
    return json.dumps(
        {
            "written": summary.get("written", 0),
            "failed": summary.get("failed", 0),
            "fallbacks": summary.get("fallbacks", 0),
            "target_errors": summary.get("target_errors", []),
        },
        ensure_ascii=False,
    )


def _is_missing_training_team_error(error: str) -> bool:
    return "both teams must have been in the training data" in error.lower()


def _fallback_market_probabilities(market: str, market_consensus: dict) -> dict[str, float]:
    probabilities = market_consensus.get("probabilities") or {}
    outcomes = market_outcomes(market)
    if outcomes and all(outcome in probabilities for outcome in outcomes):
        return {outcome: float(probabilities[outcome]) for outcome in outcomes}

    if market == "1x2":
        return {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}
    if market == "btts":
        return {"yes": 0.5, "no": 0.5}
    if market in {"ou_2_5", "over_under_2_5"}:
        return {"over": 0.5, "under": 0.5}
    return {outcome: 1 / len(outcomes) for outcome in outcomes} if outcomes else {}


def _mark_quality_as_fallback(quality_report: dict, reason: str) -> dict:
    quality_report["model"]["fallback"] = "market_consensus_or_neutral"
    quality_report["model"]["fallback_reason"] = reason
    reliability = quality_report["reliability"]
    block_reasons = reliability.setdefault("block_reasons", [])
    if "model_training_team_missing" not in block_reasons:
        block_reasons.append("model_training_team_missing")
    reliability["label"] = "unreliable"
    reliability["is_ticket_eligible"] = False
    reliability["score"] = min(int(reliability.get("score", 0) or 0), 25)
    return quality_report


def _to_datetime(val: str | None) -> datetime | None:
    """Convert a date or datetime string to a timezone-aware datetime."""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        try:
            d = date_type.fromisoformat(val)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        except ValueError:
            return None


def _is_world_cup_competition(league: str) -> bool:
    normalized = league.lower()
    return "world" in normalized and ("cup" in normalized or "championship" in normalized)


def _competition_clause(league: str):
    if _is_world_cup_competition(league):
        return or_(
            Match.competition.ilike("%World Cup%"),
            Match.competition.ilike("%World Championship%"),
            Match.competition.ilike("%FIFA World Cup%"),
        )
    return Match.competition.ilike(f"%{league}%")


PREDICT_MODELS = [
    {"key": "PoissonGoalsModel", "label": "Poisson", "description": "Independent Poisson goals model."},
    {
        "key": "BivariatePoissonGoalModel",
        "label": "Bivariate Poisson",
        "description": "Karlis-Ntzoufras bivariate Poisson.",
    },
    {
        "key": "DixonColesGoalModel",
        "label": "Dixon-Coles",
        "description": "Poisson with low-score dependency correction.",
    },
    {
        "key": "NegativeBinomialGoalModel",
        "label": "Negative Binomial",
        "description": "Overdispersed Poisson alternative.",
    },
    {
        "key": "ZeroInflatedPoissonGoalsModel",
        "label": "Zero-Inflated Poisson",
        "description": "Poisson with zero-inflation component.",
    },
    {
        "key": "WeibullCopulaGoalsModel",
        "label": "Weibull Copula",
        "description": "Weibull-count goals with copula dependency.",
    },
    {"key": "BayesianGoalModel", "label": "Bayesian Goal", "description": "Bayesian Poisson goals model (MCMC)."},
    {
        "key": "HierarchicalBayesianGoalModel",
        "label": "Bayesian Hierarchical",
        "description": "Hierarchical Bayesian goals model (MCMC).",
    },
]

MARKET_OUTCOMES = {
    "1x2": ["home", "draw", "away"],
    "btts": ["yes", "no"],
    "ou_2_5": ["over", "under"],
}

DEFAULT_TRAINING_HISTORY_DAYS = 365


def resolve_prediction_model_key(model_type: str) -> str:
    resolved = MODEL_TYPE_ALIASES.get(model_type)
    if resolved:
        return resolved

    supported = sorted({alias for alias in MODEL_TYPE_ALIASES if alias == MODEL_TYPE_ALIASES[alias]})
    raise ValueError(f"Unsupported strategy model '{model_type}'. Supported penaltyblog models: {', '.join(supported)}")


async def fetch_training_matches(
    db: AsyncSession,
    league: str,
    sport: str = "football",
    limit: int = 380,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[Match]:
    df = _to_datetime(date_from)
    dt = _to_datetime(date_to)
    stmt = select(Match).where(
        Match.sport == sport,
        Match.home_score.isnot(None),
        Match.away_score.isnot(None),
        _competition_clause(league),
    )
    if df:
        stmt = stmt.where(Match.match_date >= df)
    if dt:
        # Training must stop before the target kickoff to prevent result leakage.
        stmt = stmt.where(Match.match_date < dt)
    stmt = stmt.order_by(
        Match.match_date.desc().nulls_last(),
        Match.created_at.desc(),
        Match.id.desc(),
    ).limit(limit)
    result = await db.execute(stmt)
    # Limit against the newest available history, then restore chronological
    # order because penaltyblog fitting and time-decay weights expect it.
    return list(reversed(result.scalars().all()))


async def fetch_target_matches(
    db: AsyncSession,
    league: str,
    sport: str = "football",
    target_mode: str = "future",
    limit: int = 50,
    target_match_ids: list[int] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[Match]:
    if target_mode == "matches" and target_match_ids:
        stmt = select(Match).where(Match.id.in_(target_match_ids))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    df = _to_datetime(date_from)
    dt = _to_datetime(date_to)
    today_dt = datetime.now(timezone.utc)

    stmt = select(Match).where(Match.sport == sport, _competition_clause(league))

    if target_mode == "future":
        stmt = stmt.where(Match.home_score.is_(None), Match.match_date >= (df or today_dt))
        if dt:
            stmt = stmt.where(Match.match_date <= dt)
    else:
        stmt = stmt.where(Match.home_score.isnot(None))
        if df:
            stmt = stmt.where(Match.match_date >= df)
        if dt:
            stmt = stmt.where(Match.match_date <= dt)
        else:
            stmt = stmt.where(Match.match_date < today_dt)

    stmt = stmt.order_by(Match.match_date.asc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


def extract_market_probabilities(grid: dict, market: str) -> list[dict]:
    mapping = {
        "1x2": [
            {"outcome": "home", "probability": float(grid.get("homeWin", 0))},
            {"outcome": "draw", "probability": float(grid.get("draw", 0))},
            {"outcome": "away", "probability": float(grid.get("awayWin", 0))},
        ],
        "btts": [
            {"outcome": "yes", "probability": float(grid.get("bttsYes", 0))},
            {"outcome": "no", "probability": float(grid.get("bttsNo", 0))},
        ],
        "ou_2_5": [
            {"outcome": "over", "probability": float(grid.get("totals", {}).get("over_2_5", 0))},
            {"outcome": "under", "probability": float(grid.get("totals", {}).get("under_2_5", 0))},
        ],
    }
    return mapping.get(market, [])


async def fetch_target_odds_map(db: AsyncSession, target_ids: list[int]) -> dict[int, list[OddsEntry]]:
    odds_by_match: dict[int, list[OddsEntry]] = {}
    for odds in await load_odds_entries(db, match_ids=target_ids):
        odds_by_match.setdefault(odds.match_id, []).append(odds)
    return odds_by_match


def _canonical_market_consensus(quote_set: QuoteSet) -> dict:
    probabilities = dict(quote_set.consensus_probabilities)
    pick = max(probabilities.items(), key=lambda item: item[1])[0] if probabilities else None
    odds = {
        outcome: {
            "odds": quote.price,
            "bookmaker": quote.bookmaker,
            "odds_entry_id": quote.entry_id,
            "odds_snapshot_id": quote.snapshot_id,
            "observed_at": quote.observed_at.isoformat(),
        }
        for outcome, quote in quote_set.best_quotes.items()
    }
    return {
        "pick": pick,
        "probabilities": {key: round(float(value), 6) for key, value in probabilities.items()},
        "odds": odds,
        "implied_source": "canonical_snapshot_median_devig" if probabilities else "unavailable",
        "quote_snapshot": {
            "snapshot_id": quote_set.snapshot_id,
            "snapshot_key": (
                [
                    quote_set.snapshot_key[0],
                    quote_set.snapshot_key[1].isoformat()
                    if isinstance(quote_set.snapshot_key[1], (date_type, datetime))
                    else quote_set.snapshot_key[1],
                ]
                if quote_set.snapshot_key is not None
                else None
            ),
            "observed_at": quote_set.observed_at.isoformat() if quote_set.observed_at is not None else None,
            "ticket_eligible": quote_set.is_ticket_eligible,
            "reason_codes": list(quote_set.reason_codes),
        },
    }


def _apply_quote_eligibility(quality_report: dict, quote_set: QuoteSet) -> dict:
    if quote_set.is_ticket_eligible:
        return quality_report
    reliability = quality_report.setdefault("reliability", {})
    block_reasons = reliability.setdefault("block_reasons", [])
    for reason in quote_set.reason_codes:
        if reason not in block_reasons:
            block_reasons.append(reason)
    reliability["is_ticket_eligible"] = False
    reliability["label"] = "unreliable"
    reliability["score"] = min(int(reliability.get("score", 0) or 0), 25)
    return quality_report


async def calculate_implied_probabilities_with_penaltyblog(
    market: str,
    odds_entries: list[OddsEntry],
) -> dict[str, float] | None:
    """Convert best market odds into no-vig probabilities via penaltyblog.implied."""
    odds_by_outcome = best_market_odds_by_outcome(market, odds_entries)
    outcomes = [outcome for outcome in market_outcomes(market) if odds_by_outcome.get(outcome)]
    if len(outcomes) < 2:
        return None

    try:
        response = await run_penaltyblog(
            {
                "operation": "calculate_implied",
                "payload": {
                    "odds": [float(odds_by_outcome[outcome]["odds"]) for outcome in outcomes],
                    "method": "multiplicative",
                    "odds_format": "decimal",
                    "market_names": outcomes,
                },
            }
        )
    except BridgeError:
        return None

    result = response.get("result", {})
    probabilities = result.get("probabilities")
    names = result.get("market_names") or outcomes
    if not isinstance(probabilities, list) or len(probabilities) != len(outcomes):
        return None
    return {str(name): float(probability) for name, probability in zip(names, probabilities)}


def _market_model_probability_map(market: str, outcome_lookup: dict[str, float]) -> dict[str, float]:
    market_key = market.lower()
    if market_key == "1x2":
        return {
            "home": float(outcome_lookup.get("home", 0.0)),
            "draw": float(outcome_lookup.get("draw", 0.0) or 0.0),
            "away": float(outcome_lookup.get("away", 0.0)),
        }
    if market_key == "btts":
        return {
            "yes": float(outcome_lookup.get("yes", 0.0)),
            "no": float(outcome_lookup.get("no", 0.0)),
        }
    if market_key in {"ou_2_5", "over_under", "overunder", "totals"}:
        return {
            "over": float(outcome_lookup.get("over", 0.0)),
            "under": float(outcome_lookup.get("under", 0.0)),
        }
    return {
        "home": float(outcome_lookup.get("home", 0.0)),
        "draw": float(outcome_lookup.get("draw", 0.0) or 0.0),
        "away": float(outcome_lookup.get("away", 0.0)),
    }


def _row_probability_fields(market: str, probabilities: dict[str, float]) -> tuple[float, float | None, float]:
    market_key = market.lower()
    if market_key == "1x2":
        return probabilities.get("home", 0.0), probabilities.get("draw"), probabilities.get("away", 0.0)
    if market_key == "btts":
        return probabilities.get("yes", 0.0), None, probabilities.get("no", 0.0)
    if market_key in {"ou_2_5", "over_under", "overunder", "totals"}:
        return probabilities.get("over", 0.0), None, probabilities.get("under", 0.0)
    return probabilities.get("home", 0.0), probabilities.get("draw"), probabilities.get("away", 0.0)


def _row_odds_and_value_fields(
    market: str,
    quality_report: dict,
) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None, float | None]:
    market_key = market.lower()
    odds = quality_report.get("market", {}).get("odds", {}) or {}
    edge = quality_report.get("edge", {}) or {}
    pick = quality_report.get("model", {}).get("pick")

    if market_key == "1x2":
        outcome_fields = ("home", "draw", "away")
    elif market_key == "btts":
        outcome_fields = ("yes", None, "no")
    elif market_key in {"ou_2_5", "over_under", "overunder", "totals"}:
        outcome_fields = ("over", None, "under")
    else:
        outcome_fields = ("home", "draw", "away")

    def odds_value(outcome: str | None) -> float | None:
        if not outcome:
            return None
        payload = odds.get(outcome)
        return float(payload["odds"]) if payload else None

    def edge_value(outcome: str | None) -> float | None:
        if not outcome:
            return None
        value = edge.get(outcome)
        return float(value) / 100 if value is not None else None

    home_outcome, draw_outcome, away_outcome = outcome_fields
    expected_value = edge_value(pick) if pick else None
    return (
        odds_value(home_outcome),
        odds_value(draw_outcome),
        odds_value(away_outcome),
        edge_value(home_outcome),
        edge_value(draw_outcome),
        edge_value(away_outcome),
        expected_value,
    )


def _score_grid_analysis_payload(grid: dict) -> dict | None:
    """Extract the bounded exact-score explanation emitted by the model bridge.

    This payload is intentionally nested under ``analysis_only`` in persisted
    quality reports. Ticket eligibility continues to be derived exclusively
    from supported market rows and never from exact-score cells.
    """
    raw_score_grid = grid.get("scoreGrid")
    home_xg = grid.get("homeGoalExpectation")
    away_xg = grid.get("awayGoalExpectation")
    if not isinstance(raw_score_grid, dict) or home_xg is None or away_xg is None:
        return None

    probabilities = raw_score_grid.get("probabilities")
    if not isinstance(probabilities, list) or not probabilities:
        return None

    try:
        sanitized = [[float(probability) for probability in row] for row in probabilities if isinstance(row, list)]
        if not sanitized or any(len(row) != len(sanitized[0]) for row in sanitized):
            return None
        displayed_mass = sum(sum(row) for row in sanitized)
        return {
            "usage": "analysis_only",
            "ticket_generation_eligible": False,
            "home_expected_goals": float(home_xg),
            "away_expected_goals": float(away_xg),
            "max_displayed_goals": int(raw_score_grid.get("maxDisplayedGoals", len(sanitized) - 1)),
            "displayed_probability_mass": float(raw_score_grid.get("displayedProbabilityMass", displayed_mass)),
            "probabilities": sanitized,
        }
    except (TypeError, ValueError):
        return None


async def execute_single_model_run(
    db: AsyncSession,
    run_id: int,
    model_key: str,
    league: str,
    markets: list[str],
    sport: str = "football",
    training_limit: int = 380,
    target_limit: int = 50,
    target_mode: str = "future",
    max_goals: int = 10,
    target_match_ids: list[int] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    model_kwargs: dict | None = None,
    fit_kwargs: dict | None = None,
    use_time_decay: bool = False,
    time_decay_xi: float = 0.0018,
    training_history_days: int = DEFAULT_TRAINING_HISTORY_DAYS,
) -> dict:
    canonical_model_key = resolve_prediction_model_key(model_key)
    targets = await fetch_target_matches(
        db,
        league,
        sport,
        target_mode,
        target_limit,
        target_match_ids,
        date_from=date_from,
        date_to=date_to,
    )
    if not targets:
        raise ValueError("No target matches found for this selection.")

    dated_targets = [
        match_date for target in targets if (match_date := getattr(target, "match_date", None)) is not None
    ]
    target_anchor = min(dated_targets) if dated_targets else (_to_datetime(date_from) or datetime.now(timezone.utc))
    if target_anchor.tzinfo is None:
        target_anchor = target_anchor.replace(tzinfo=timezone.utc)
    quote_as_of = min(target_anchor, datetime.now(timezone.utc))
    history_days = max(1, int(training_history_days))
    training_date_from = target_anchor - timedelta(days=history_days)
    training = await fetch_training_matches(
        db,
        league,
        sport,
        training_limit,
        date_from=training_date_from.isoformat(),
        date_to=target_anchor.isoformat(),
    )
    if len(training) < 20:
        raise ValueError(
            f"Insufficient training data in the {history_days}-day window before "
            f"{target_anchor.isoformat()}: {len(training)} matches (need >=20)"
        )

    target_odds_map = await fetch_target_odds_map(db, [target.id for target in targets])

    goals_home = [m.home_score for m in training]
    goals_away = [m.away_score for m in training]
    teams_home = [m.home_team for m in training]
    teams_away = [m.away_team for m in training]
    weights: list[float] | None = None

    if use_time_decay:
        dated_training = [m for m in training if m.match_date is not None]
        if len(dated_training) != len(training):
            raise ValueError("Time-decay weighting requires match dates for all training matches")

        try:
            weights_response = await run_penaltyblog(
                {
                    "operation": "dixon_coles_weights",
                    "payload": {
                        "dates": [m.match_date.isoformat() for m in dated_training],
                        "xi": float(time_decay_xi),
                    },
                }
            )
            weights_result = weights_response.get("result", {})
            serialized_weights = weights_result.get("weights")
            if not isinstance(serialized_weights, list) or len(serialized_weights) != len(training):
                raise ValueError("Penaltyblog time-decay weights response was invalid")
            weights = [float(weight) for weight in serialized_weights]
        except BridgeError:
            weights = None

    written = 0
    failed = 0
    fallbacks = 0
    target_errors: list[dict] = []
    concurrency = 3

    async def predict_one(target: Match) -> None:
        nonlocal written, failed, fallbacks

        async def write_fallback_predictions(reason: str) -> int:
            rows_written = 0
            odds_entries = target_odds_map.get(target.id) or []
            for market in markets:
                quote_set = select_quote_set(odds_entries, market=market, as_of=quote_as_of)
                market_consensus = _canonical_market_consensus(quote_set)
                model_probabilities = _fallback_market_probabilities(market, market_consensus)
                if not model_probabilities:
                    continue
                home_prob, draw_prob, away_prob = _row_probability_fields(market, model_probabilities)
                quality_report = evaluate_prediction_quality(
                    training_matches=training,
                    target_match=target,
                    market=market,
                    model_probabilities=model_probabilities,
                    market_consensus=market_consensus,
                )
                quality_report = _apply_quote_eligibility(quality_report, quote_set)
                quality_report.setdefault("training", {})["window"] = {
                    "days": history_days,
                    "date_from": training_date_from.isoformat(),
                    "date_to_exclusive": target_anchor.isoformat(),
                }
                quality_report = _mark_quality_as_fallback(quality_report, reason)
                (
                    home_odds,
                    draw_odds,
                    away_odds,
                    value_home,
                    value_draw,
                    value_away,
                    expected_value,
                ) = _row_odds_and_value_fields(market, quality_report)
                db.add(
                    ModelPrediction(
                        run_id=run_id,
                        model_type=model_key,
                        match_id=target.id,
                        odds_snapshot_id=(quote_set.snapshot_id if isinstance(quote_set.snapshot_id, int) else None),
                        market=market,
                        home_prob=home_prob,
                        draw_prob=draw_prob,
                        away_prob=away_prob,
                        home_odds=home_odds,
                        draw_odds=draw_odds,
                        away_odds=away_odds,
                        value_home=value_home,
                        value_away=value_away,
                        value_draw=value_draw,
                        expected_value=expected_value,
                        quality_report=quality_report,
                    )
                )
                rows_written += 1
            return rows_written

        try:
            response = await run_penaltyblog(
                {
                    "operation": "model_fit_predict",
                    "payload": {
                        "model": canonical_model_key,
                        "goals_home": goals_home,
                        "goals_away": goals_away,
                        "teams_home": teams_home,
                        "teams_away": teams_away,
                        "model_kwargs": model_kwargs or {},
                        "fit_kwargs": fit_kwargs or {},
                        "weights": weights,
                        "prediction": {
                            "home_team": target.home_team,
                            "away_team": target.away_team,
                            "max_goals": max_goals,
                        },
                    },
                }
            )
            result = response.get("result", {})
            grid = result.get("prediction")
            if not grid:
                failed += 1
                target_errors.append(
                    {
                        "match_id": target.id,
                        "home_team": target.home_team,
                        "away_team": target.away_team,
                        "error": "Penaltyblog returned no prediction grid",
                    }
                )
                return

            for market in markets:
                probs = extract_market_probabilities(grid, market)
                if not probs:
                    continue

                outcome_lookup = {entry["outcome"]: entry["probability"] for entry in probs}
                model_probabilities = _market_model_probability_map(market, outcome_lookup)
                home_prob, draw_prob, away_prob = _row_probability_fields(market, model_probabilities)
                odds_entries = target_odds_map.get(target.id) or []
                quote_set = select_quote_set(odds_entries, market=market, as_of=quote_as_of)
                market_consensus = _canonical_market_consensus(quote_set)
                quality_report = evaluate_prediction_quality(
                    training_matches=training,
                    target_match=target,
                    market=market,
                    model_probabilities=model_probabilities,
                    market_consensus=market_consensus,
                )
                quality_report = _apply_quote_eligibility(quality_report, quote_set)
                quality_report.setdefault("training", {})["window"] = {
                    "days": history_days,
                    "date_from": training_date_from.isoformat(),
                    "date_to_exclusive": target_anchor.isoformat(),
                }
                score_grid_payload = _score_grid_analysis_payload(grid)
                if score_grid_payload is not None:
                    quality_report.setdefault("analysis_only", {})["score_grid"] = score_grid_payload
                (
                    home_odds,
                    draw_odds,
                    away_odds,
                    value_home,
                    value_draw,
                    value_away,
                    expected_value,
                ) = _row_odds_and_value_fields(market, quality_report)

                row = ModelPrediction(
                    run_id=run_id,
                    model_type=model_key,
                    match_id=target.id,
                    odds_snapshot_id=(quote_set.snapshot_id if isinstance(quote_set.snapshot_id, int) else None),
                    market=market,
                    home_prob=home_prob,
                    draw_prob=draw_prob,
                    away_prob=away_prob,
                    home_odds=home_odds,
                    draw_odds=draw_odds,
                    away_odds=away_odds,
                    value_home=value_home,
                    value_away=value_away,
                    value_draw=value_draw,
                    expected_value=expected_value,
                    quality_report=quality_report,
                )
                db.add(row)
                written += 1
        except BridgeError as exc:
            if _is_missing_training_team_error(str(exc)):
                fallback_written = await write_fallback_predictions(str(exc))
                if fallback_written:
                    written += fallback_written
                    fallbacks += 1
                    target_errors.append(
                        {
                            "match_id": target.id,
                            "home_team": target.home_team,
                            "away_team": target.away_team,
                            "error": str(exc),
                            "fallback": "market_consensus_or_neutral",
                            "fallback_predictions": fallback_written,
                        }
                    )
                    return
            failed += 1
            target_errors.append(
                {
                    "match_id": target.id,
                    "home_team": target.home_team,
                    "away_team": target.away_team,
                    "error": str(exc),
                }
            )
        except Exception as exc:
            failed += 1
            target_errors.append(
                {
                    "match_id": target.id,
                    "home_team": target.home_team,
                    "away_team": target.away_team,
                    "error": str(exc),
                }
            )

    index = 0

    async def worker() -> None:
        nonlocal index
        while index < len(targets):
            i = index
            index += 1
            await predict_one(targets[i])

    workers = [worker() for _ in range(min(concurrency, len(targets)))]
    await asyncio.gather(*workers)

    return {
        "training_matches": len(training),
        "training_window": {
            "days": history_days,
            "date_from": training_date_from.isoformat(),
            "date_to_exclusive": target_anchor.isoformat(),
        },
        "target_matches": len(targets),
        "written": written,
        "failed": failed,
        "fallbacks": fallbacks,
        "markets": markets,
        "target_errors": target_errors,
    }


async def run_single_prediction(
    db: AsyncSession,
    league: str,
    model_key: str,
    markets: list[str] = None,
    sport: str = "football",
    training_limit: int = 380,
    target_limit: int = 50,
    target_mode: str = "future",
    target_match_ids: list[int] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    max_goals: int = 10,
    user_id: int | None = None,
    training_history_days: int = DEFAULT_TRAINING_HISTORY_DAYS,
) -> dict:
    if markets is None:
        markets = ["1x2"]

    run = PredictionRun(
        user_id=user_id,
        model_type=model_key,
        ensemble=False,
        status="running",
        matches_count=0,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    try:
        summary = await execute_single_model_run(
            db,
            run.id,
            model_key,
            league,
            markets,
            sport,
            training_limit,
            target_limit,
            target_mode,
            max_goals,
            target_match_ids=target_match_ids,
            date_from=date_from,
            date_to=date_to,
            training_history_days=training_history_days,
        )
        if summary.get("written", 0) <= 0:
            run.status = "failed"
        elif summary.get("failed", 0) > 0 or summary.get("fallbacks", 0) > 0:
            run.status = "partial"
        else:
            run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.matches_count = summary["target_matches"]
        run.input_context = {
            **(run.input_context or {}),
            "training_matches": summary.get("training_matches", 0),
            "training_window": summary.get("training_window"),
        }
        run.error = None
        if run.status != "completed":
            run.error = prediction_error_payload(summary)
        await db.flush()
        response = {"run_id": run.id, "status": run.status}
        if run.error:
            response["error"] = run.error
        return response
    except Exception as e:
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(e)
        await db.flush()
        return {"run_id": run.id, "status": run.status, "error": str(e)}
