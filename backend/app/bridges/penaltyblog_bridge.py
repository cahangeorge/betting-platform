# ruff: noqa
# Kept mechanically aligned with the legacy subprocess contract; refactor separately.
import argparse
import json
import os
import signal
import sys
import traceback
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

# Keep child Python isolated from the Vite dev server process group.
try:
    os.setsid()
except OSError:
    pass
signal.signal(signal.SIGINT, signal.SIG_IGN)


def serialize_value(value):
    try:
        if value != value:
            return None
    except Exception:
        pass

    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, pd.DataFrame):
        frame = value.reset_index()
        frame.columns = [str(column) for column in frame.columns]
        return {
            "rows": [serialize_value(record) for record in frame.to_dict(orient="records")],
            "columns": [str(column) for column in frame.columns],
            "count": int(len(frame)),
        }

    if isinstance(value, pd.Series):
        return {
            "name": str(value.name),
            "values": [serialize_value(item) for item in value.tolist()],
        }

    if is_dataclass(value):
        return {key: serialize_value(item) for key, item in asdict(value).items()}

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [serialize_value(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if hasattr(value, "__dict__"):
        return {key: serialize_value(item) for key, item in value.__dict__.items() if not key.startswith("_")}

    return str(value)


def serialize_probability_grid(grid):
    score_limit = min(5, grid.grid.shape[0] - 1, grid.grid.shape[1] - 1)
    score_matrix = [
        [serialize_value(grid.exact_score(home_goals, away_goals)) for away_goals in range(score_limit + 1)]
        for home_goals in range(score_limit + 1)
    ]
    return {
        "homeGoalExpectation": serialize_value(grid.home_goal_expectation),
        "awayGoalExpectation": serialize_value(grid.away_goal_expectation),
        # A deliberately bounded analytics payload. Exact-score probabilities
        # are exposed for explanation/visualisation, never as ticket candidates.
        "scoreGrid": {
            "maxDisplayedGoals": score_limit,
            "probabilities": score_matrix,
            "displayedProbabilityMass": serialize_value(sum(sum(row) for row in score_matrix)),
        },
        "homeWin": serialize_value(grid.home_win),
        "draw": serialize_value(grid.draw),
        "awayWin": serialize_value(grid.away_win),
        "homeDrawAway": serialize_value(grid.home_draw_away),
        "bttsYes": serialize_value(grid.btts_yes),
        "bttsNo": serialize_value(grid.btts_no),
        "doubleChance": {
            "1X": serialize_value(grid.double_chance_1x),
            "X2": serialize_value(grid.double_chance_x2),
            "12": serialize_value(grid.double_chance_12),
        },
        "drawNoBet": {
            "home": serialize_value(grid.draw_no_bet_home),
            "away": serialize_value(grid.draw_no_bet_away),
        },
        "totals": {
            "over_1_5": serialize_value(grid.total_goals("over", 1.5)),
            "over_2_5": serialize_value(grid.total_goals("over", 2.5)),
            "over_3_5": serialize_value(grid.total_goals("over", 3.5)),
            "under_1_5": serialize_value(grid.total_goals("under", 1.5)),
            "under_2_5": serialize_value(grid.total_goals("under", 2.5)),
            "under_3_5": serialize_value(grid.total_goals("under", 3.5)),
        },
        "asianHandicap": {
            "home_-0_5": serialize_value(grid.asian_handicap("home", -0.5)),
            "away_+0_5": serialize_value(grid.asian_handicap("away", 0.5)),
        },
        "totalGoalsDistribution": serialize_value(grid.total_goals_distribution()),
        "grid": serialize_value(grid.grid),
    }


def load_penaltyblog_paths():
    configured_root = os.environ.get("BET_PENALTYBLOG_ROOT")
    if not configured_root:
        raise RuntimeError("BET_PENALTYBLOG_ROOT must point to the penaltyblog checkout")

    penaltyblog_root = Path(configured_root).expanduser().resolve()
    if not penaltyblog_root.is_dir():
        raise RuntimeError(f"BET_PENALTYBLOG_ROOT does not exist: {penaltyblog_root}")

    os.environ.setdefault("MPLBACKEND", "Agg")
    sys.path.insert(0, str(penaltyblog_root))
    return penaltyblog_root


def catalog(payload=None):  # noqa: ARG001 — payload accepted for uniform dispatch
    return {
        "groups": [
            {
                "id": "models",
                "label": "Models",
                "operations": [
                    {
                        "id": "model_fit_predict",
                        "label": "Fit + Predict",
                        "description": "Fit a penaltyblog goals model and produce a probability grid.",
                    },
                    {
                        "id": "goal_expectancy",
                        "label": "Goal Expectancy",
                        "description": "Infer implied goal expectancies from 1X2 probabilities.",
                    },
                    {
                        "id": "goal_expectancy_extended",
                        "label": "Goal Expectancy Extended",
                        "description": "Infer goal expectancies and rho from 1X2 and O/U 2.5 probabilities.",
                    },
                    {
                        "id": "dixon_coles_weights",
                        "label": "Dixon-Coles Weights",
                        "description": "Generate time-decay weights from dates.",
                    },
                ],
            },
            {
                "id": "betting",
                "label": "Betting",
                "operations": [
                    {
                        "id": "calculate_implied",
                        "label": "Calculate Implied",
                        "description": "Convert odds into implied probabilities.",
                    },
                    {
                        "id": "kelly_criterion",
                        "label": "Kelly Criterion",
                        "description": "Compute optimal Kelly stake for one bet.",
                    },
                    {
                        "id": "multiple_kelly_criterion",
                        "label": "Multiple Kelly",
                        "description": "Compute Kelly stakes for a portfolio.",
                    },
                    {
                        "id": "identify_value_bet",
                        "label": "Identify Value Bet",
                        "description": "Compare model probabilities to bookmaker odds.",
                    },
                    {
                        "id": "find_arbitrage_opportunities",
                        "label": "Find Arbitrage",
                        "description": "Scan multi-bookmaker odds for arbitrage.",
                    },
                    {
                        "id": "arbitrage_hedge",
                        "label": "Arbitrage Hedge",
                        "description": "Compute hedge stakes for an existing position.",
                    },
                    {"id": "convert_odds", "label": "Convert Odds", "description": "Convert odds into decimal format."},
                ],
            },
            {
                "id": "ratings",
                "label": "Ratings",
                "operations": [
                    {
                        "id": "elo_ratings",
                        "label": "Elo",
                        "description": "Run Elo updates and optional match prediction.",
                    },
                    {
                        "id": "pi_ratings",
                        "label": "Pi Ratings",
                        "description": "Run Pi updates and optional match prediction.",
                    },
                    {
                        "id": "colley_ratings",
                        "label": "Colley",
                        "description": "Compute Colley team ratings from results.",
                    },
                    {
                        "id": "massey_ratings",
                        "label": "Massey",
                        "description": "Compute Massey team ratings from results.",
                    },
                ],
            },
            {
                "id": "metrics",
                "label": "Metrics",
                "operations": [
                    {
                        "id": "score_predictions",
                        "label": "Score Predictions",
                        "description": "Calculate Brier, RPS, and ignorance scores.",
                    },
                ],
            },
            {
                "id": "backtest",
                "label": "Backtest",
                "operations": [
                    {
                        "id": "backtest_run",
                        "label": "Backtest Strategy",
                        "description": "Run a simple model-driven backtest over dated fixtures.",
                    },
                ],
            },
            {
                "id": "scrapers",
                "label": "Scrapers",
                "operations": [
                    {
                        "id": "scraper_footballdata_fixtures",
                        "label": "FootballData Fixtures",
                        "description": "Fetch football-data.co.uk fixtures.",
                    },
                    {
                        "id": "scraper_fbref_fixtures",
                        "label": "FBRef Fixtures",
                        "description": "Fetch FBRef fixtures/results.",
                    },
                    {
                        "id": "scraper_fbref_stats",
                        "label": "FBRef Stats",
                        "description": "Fetch FBRef squad and player stats.",
                    },
                    {
                        "id": "scraper_understat_fixtures",
                        "label": "Understat Fixtures",
                        "description": "Fetch Understat fixtures with xG.",
                    },
                    {
                        "id": "scraper_understat_shots",
                        "label": "Understat Shots",
                        "description": "Fetch Understat shot events for one match.",
                    },
                    {
                        "id": "scraper_clubelo_by_date",
                        "label": "ClubElo by Date",
                        "description": "Fetch ClubElo ratings by date.",
                    },
                    {
                        "id": "scraper_clubelo_by_team",
                        "label": "ClubElo by Team",
                        "description": "Fetch ClubElo team history.",
                    },
                    {
                        "id": "scraper_clubelo_team_names",
                        "label": "ClubElo Team Names",
                        "description": "Fetch ClubElo team catalogue.",
                    },
                ],
            },
            {
                "id": "fpl",
                "label": "Fantasy Premier League",
                "operations": [
                    {
                        "id": "fpl_current_gameweek",
                        "label": "Current Gameweek",
                        "description": "Fetch the active FPL gameweek.",
                    },
                    {
                        "id": "fpl_gameweek_info",
                        "label": "Gameweek Info",
                        "description": "Fetch FPL gameweek metadata.",
                    },
                    {
                        "id": "fpl_player_id_mappings",
                        "label": "Player ID Mappings",
                        "description": "Fetch FPL player ID mappings.",
                    },
                    {"id": "fpl_player_data", "label": "Player Data", "description": "Fetch FPL player stats."},
                    {
                        "id": "fpl_player_history",
                        "label": "Player History",
                        "description": "Fetch FPL history for one player.",
                    },
                    {"id": "fpl_rankings", "label": "Rankings", "description": "Fetch FPL rankings page."},
                    {
                        "id": "fpl_entry_picks",
                        "label": "Entry Picks",
                        "description": "Fetch FPL entry picks for a gameweek.",
                    },
                ],
            },
            {
                "id": "matchflow",
                "label": "Matchflow Pipeline",
                "operations": [
                    {
                        "id": "matchflow_execute",
                        "label": "Execute Pipeline",
                        "description": "Run a matchflow data pipeline and collect results.",
                    },
                    {
                        "id": "matchflow_schema",
                        "label": "Infer Schema",
                        "description": "Infer field types from pipeline output.",
                    },
                    {
                        "id": "matchflow_explain",
                        "label": "Explain Plan",
                        "description": "Show the optimized execution plan.",
                    },
                ],
            },
            {
                "id": "visualization",
                "label": "Visualization",
                "operations": [
                    {
                        "id": "pitch_render",
                        "label": "Pitch Visualization",
                        "description": "Render a football pitch with data layers.",
                    },
                    {
                        "id": "bayesian_diagnostic_plots",
                        "label": "Bayesian Diagnostic Plots",
                        "description": "Generate MCMC diagnostic plots.",
                    },
                ],
            },
            {
                "id": "opta",
                "label": "Opta",
                "operations": [
                    {
                        "id": "opta_mappings",
                        "label": "Event & Qualifier Mappings",
                        "description": "Get Opta event type and qualifier definitions.",
                    },
                ],
            },
            {
                "id": "bayesian",
                "label": "Bayesian Diagnostics",
                "operations": [
                    {
                        "id": "bayesian_diagnostics",
                        "label": "Numerical Diagnostics",
                        "description": "Compute R-hat, ESS, and autocorrelation for Bayesian models.",
                    },
                ],
            },
        ]
    }


def _ensure_training_arrays(payload):
    return (
        payload["goals_home"],
        payload["goals_away"],
        payload["teams_home"],
        payload["teams_away"],
    )


def _normalize_match_rows(rows):
    frame = pd.DataFrame(rows)
    rename_map = {
        "homeTeam": "team_home",
        "awayTeam": "team_away",
        "homeGoals": "goals_home",
        "awayGoals": "goals_away",
        "matchDate": "date",
        "homeOdds": "home_odds",
        "drawOdds": "draw_odds",
        "awayOdds": "away_odds",
    }
    frame = frame.rename(columns={key: value for key, value in rename_map.items() if key in frame.columns})
    if "date" not in frame.columns:
        raise ValueError("matches must include a date column")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def run_model_fit_predict(payload):
    import penaltyblog as pb

    model_name = payload.get("model", "PoissonGoalsModel")
    model_class = getattr(pb.models, model_name)
    goals_home, goals_away, teams_home, teams_away = _ensure_training_arrays(payload)
    model_kwargs = payload.get("model_kwargs", {})
    fit_kwargs = payload.get("fit_kwargs", {})

    weights = payload.get("weights")
    if weights is not None:
        model = model_class(goals_home, goals_away, teams_home, teams_away, weights=weights, **model_kwargs)
    else:
        model = model_class(goals_home, goals_away, teams_home, teams_away, **model_kwargs)

    model.fit(**fit_kwargs)

    # Per-team match counts for diagnostics
    from collections import Counter

    all_teams_list = list(teams_home) + list(teams_away)
    team_counts = Counter(all_teams_list)

    result = {
        "model": model_name,
        "fittedTeamCount": len(set(teams_home) | set(teams_away)),
        "fittedMatchCount": len(goals_home),
        "perTeamMatchCounts": {team: count for team, count in sorted(team_counts.items(), key=lambda x: x[1])},
    }

    if hasattr(model, "get_params"):
        try:
            result["params"] = serialize_value(model.get_params())
        except Exception as error:
            result["paramsError"] = str(error)

    # Forward team warnings from the frontend payload
    team_warnings = payload.get("_teamWarnings")
    if team_warnings:
        result["teamWarnings"] = team_warnings

    prediction = payload.get("prediction")
    if prediction:
        home_team = prediction["home_team"]
        away_team = prediction["away_team"]
        home_count = team_counts.get(home_team, 0)
        away_count = team_counts.get(away_team, 0)
        min_count = min(home_count, away_count)
        total_matches = len(goals_home)

        # Data quality assessment
        if min_count >= 20 and total_matches >= 100:
            quality_level = "reliable"
            quality_recommendation = None
        elif min_count >= 10 and total_matches >= 50:
            quality_level = "moderate"
            quality_recommendation = (
                f"Moderate data quality. For better accuracy, scrape 2+ seasons of history. "
                f"Currently {total_matches} training matches."
            )
        elif min_count >= 5:
            quality_level = "low"
            quality_recommendation = (
                f"Low data quality — predictions may be unreliable. "
                f"{home_team} has {home_count} matches, {away_team} has {away_count}. "
                f"Scrape more seasons or use soccerdata as supplement."
            )
        else:
            quality_level = "very-low"
            quality_recommendation = (
                f"Very low data quality — predictions are unreliable. "
                f"{home_team} has only {home_count} matches, {away_team} has {away_count}. "
                f"The Dixon-Coles model needs at least 10-20 matches per team. "
                f"Scrape 2-3 seasons of history or switch to a league with more data."
            )

        result["dataQuality"] = {
            "level": quality_level,
            "homeTeamCount": home_count,
            "awayTeamCount": away_count,
            "totalMatches": total_matches,
            "recommendation": quality_recommendation,
        }

        if min_count < 5:
            result.setdefault("warnings", []).append(
                f"⚠ Very sparse data: {home_team} ({home_count} matches), "
                f"{away_team} ({away_count} matches). "
                f"Need at least 10-20 per team for reliable predictions. "
                f"Consider scraping more seasons."
            )
        elif min_count < 10:
            result.setdefault("warnings", []).append(
                f"⚠ Limited data: {home_team} ({home_count} matches), "
                f"{away_team} ({away_count} matches). "
                f"Predictions may be inaccurate — 10+ matches per team recommended."
            )

        grid = model.predict(
            home_team,
            away_team,
            max_goals=int(prediction.get("max_goals", 10)),
        )
        result["prediction"] = serialize_probability_grid(grid)

        # Close-call / toss-up detection
        serialized = result["prediction"]
        hw = serialized.get("homeWin", 0)
        dr = serialized.get("draw", 0)
        aw = serialized.get("awayWin", 0)
        probs = sorted([(hw, "Home"), (dr, "Draw"), (aw, "Away")], reverse=True)
        top_diff = probs[0][0] - probs[1][0]
        if top_diff < 0.05:
            result.setdefault("warnings", []).append(
                f"🔀 Toss-up: {probs[0][1]} ({probs[0][0]:.1%}) vs {probs[1][1]} ({probs[1][0]:.1%}) "
                f"are very close — this match is hard to call."
            )
        elif top_diff < 0.10:
            result.setdefault("warnings", []).append(
                f"⚖ Close call: {probs[0][1]} ({probs[0][0]:.1%}) is only slightly favoured over "
                f"{probs[1][1]} ({probs[1][0]:.1%})."
            )

        # Derive first-half and second-half grids by scaling goal expectations
        from penaltyblog.models.football_probability_grid import create_dixon_coles_grid

        ft_home_lambda = grid.home_goal_expectation
        ft_away_lambda = grid.away_goal_expectation
        HT_FACTOR = 0.47  # ~47% of goals scored in first half (empirical)
        SH_FACTOR = 0.53  # ~53% of goals scored in second half

        ht_home = ft_home_lambda * HT_FACTOR
        ht_away = ft_away_lambda * HT_FACTOR
        sh_home = ft_home_lambda * SH_FACTOR
        sh_away = ft_away_lambda * SH_FACTOR

        # Guard against extremely low lambdas
        MIN_LAMBDA = 0.001
        if ht_home > MIN_LAMBDA and ht_away > MIN_LAMBDA:
            ht_grid = create_dixon_coles_grid(ht_home, ht_away, rho=0.0, max_goals=7)
            result["predictionFirstHalf"] = serialize_probability_grid(ht_grid)
        if sh_home > MIN_LAMBDA and sh_away > MIN_LAMBDA:
            sh_grid = create_dixon_coles_grid(sh_home, sh_away, rho=0.0, max_goals=7)
            result["predictionSecondHalf"] = serialize_probability_grid(sh_grid)

    return result


def run_goal_expectancy(payload):
    import penaltyblog as pb

    return pb.models.goal_expectancy(
        payload["home"],
        payload["draw"],
        payload["away"],
        dc_adj=bool(payload.get("dc_adj", True)),
        rho=float(payload.get("rho", 0.001)),
        max_goals=int(payload.get("max_goals", 15)),
        remove_overround=bool(payload.get("remove_overround", False)),
        objective=payload.get("objective", "brier"),
        return_details=bool(payload.get("return_details", True)),
    )


def run_goal_expectancy_extended(payload):
    import penaltyblog as pb

    return pb.models.goal_expectancy_extended(
        payload["home"],
        payload["draw"],
        payload["away"],
        payload["over25"],
        payload["under25"],
        max_goals=int(payload.get("max_goals", 15)),
        remove_overround=bool(payload.get("remove_overround", True)),
        objective=payload.get("objective", "brier"),
        return_details=bool(payload.get("return_details", True)),
    )


def run_dixon_coles_weights(payload):
    import penaltyblog as pb

    return {
        "weights": serialize_value(
            pb.models.dixon_coles_weights(
                payload["dates"],
                xi=float(payload.get("xi", 0.0018)),
                base_date=payload.get("base_date"),
            )
        )
    }


def run_calculate_implied(payload):
    import penaltyblog as pb

    return pb.implied.calculate_implied(
        payload["odds"],
        method=payload.get("method", "multiplicative"),
        odds_format=payload.get("odds_format", "decimal"),
        market_names=payload.get("market_names"),
    )


def run_kelly(payload):
    import penaltyblog as pb

    return pb.betting.kelly_criterion(
        payload["decimal_odds"],
        payload["true_prob"],
        fraction=float(payload.get("fraction", 1.0)),
    )


def run_multiple_kelly(payload):
    import penaltyblog as pb

    return pb.betting.multiple_kelly_criterion(
        payload["decimal_odds"],
        payload["true_probs"],
        fraction=float(payload.get("fraction", 1.0)),
        max_total_stake=float(payload.get("max_total_stake", 1.0)),
        method=payload.get("method", "simultaneous"),
    )


def run_identify_value(payload):
    import penaltyblog as pb

    return pb.betting.identify_value_bet(
        payload["bookmaker_odds"],
        payload["estimated_probability"],
        kelly_fraction=float(payload.get("kelly_fraction", 1.0)),
        min_edge_threshold=float(payload.get("min_edge_threshold", 0.0)),
    )


def run_find_arbitrage(payload):
    import penaltyblog as pb

    return pb.betting.find_arbitrage_opportunities(
        payload["bookmaker_odds_list"],
        outcome_labels=payload.get("outcome_labels"),
    )


def run_arbitrage_hedge(payload):
    import penaltyblog as pb

    return pb.betting.arbitrage_hedge(
        payload["existing_stakes"],
        payload["existing_odds"],
        payload["hedge_odds"],
        target_profit=payload.get("target_profit"),
        hedge_all=bool(payload.get("hedge_all", True)),
        allow_lay=bool(payload.get("allow_lay", False)),
    )


def run_convert_odds(payload):
    import penaltyblog as pb

    return {
        "decimal_odds": pb.betting.convert_odds(
            payload["odds"],
            payload.get("odds_format", "decimal"),
            market_names=payload.get("market_names"),
        )
    }


def _sort_rating_dict(ratings):
    return sorted(
        [{"team": team, "rating": rating} for team, rating in ratings.items()],
        key=lambda item: item["rating"],
        reverse=True,
    )


def run_elo_ratings(payload):
    import penaltyblog as pb

    elo = pb.ratings.Elo(
        k=float(payload.get("k", 20.0)),
        home_field_advantage=float(payload.get("home_field_advantage", 100.0)),
    )
    for match in payload.get("matches", []):
        elo.update_ratings(match["home"], match["away"], int(match["result"]))

    result = {"ratings": _sort_rating_dict(elo.ratings)}
    prediction = payload.get("prediction")
    if prediction:
        result["prediction"] = elo.calculate_match_probabilities(
            prediction["home"],
            prediction["away"],
            draw_base=float(prediction.get("draw_base", 0.3)),
            draw_width=float(prediction.get("draw_width", 200.0)),
        )
    return result


def run_pi_ratings(payload):
    import penaltyblog as pb

    system = pb.ratings.PiRatingSystem(
        alpha=float(payload.get("alpha", 0.15)),
        beta=float(payload.get("beta", 0.10)),
        k=float(payload.get("k", 0.75)),
        sigma=float(payload.get("sigma", 1.0)),
    )
    for match in payload.get("matches", []):
        if "observed_goal_difference" in match:
            observed = int(match["observed_goal_difference"])
        else:
            observed = int(match["goals_home"]) - int(match["goals_away"])
        system.update_ratings(match["home"], match["away"], observed, date=match.get("date"))

    result = {
        "ratings": sorted(
            [
                {
                    "team": team,
                    "home": values["home"],
                    "away": values["away"],
                    "average": system.get_team_rating(team),
                }
                for team, values in system.team_ratings.items()
            ],
            key=lambda item: item["average"],
            reverse=True,
        ),
        "history": serialize_value(system.rating_history),
    }
    prediction = payload.get("prediction")
    if prediction:
        result["prediction"] = system.calculate_match_probabilities(prediction["home"], prediction["away"])
    return result


def run_colley_ratings(payload):
    import penaltyblog as pb

    ratings = pb.ratings.Colley(
        payload["goals_home"],
        payload["goals_away"],
        payload["teams_home"],
        payload["teams_away"],
        include_draws=bool(payload.get("include_draws", True)),
        draw_weight=float(payload.get("draw_weight", 0.5)),
    ).get_ratings()
    return ratings


def run_massey_ratings(payload):
    import penaltyblog as pb

    return pb.ratings.Massey(
        payload["goals_home"],
        payload["goals_away"],
        payload["teams_home"],
        payload["teams_away"],
    ).get_ratings()


def run_score_predictions(payload):
    import penaltyblog as pb

    probs = payload["probs"]
    outcomes = payload["outcomes"]
    return {
        "brier": pb.metrics.multiclass_brier_score(probs, outcomes),
        "rps": pb.metrics.rps_average(probs, outcomes),
        "ignorance": pb.metrics.ignorance_score(probs, outcomes),
    }


def run_backtest(payload):
    import penaltyblog as pb

    frame = _normalize_match_rows(payload["matches"])
    required_columns = {"team_home", "team_away", "goals_home", "goals_away", "date"}
    missing = sorted(required_columns.difference(frame.columns))
    if missing:
        raise ValueError(f"backtest dataset missing columns: {', '.join(missing)}")

    model_name = payload.get("model", "PoissonGoalsModel")
    market = payload.get("market", "home_win")
    odds_field = payload.get(
        "odds_field",
        {
            "home_win": "home_odds",
            "draw": "draw_odds",
            "away_win": "away_odds",
        }.get(market, "home_odds"),
    )
    threshold = float(payload.get("threshold", 0.45))
    bankroll = float(payload.get("bankroll", 1000.0))
    stake = float(payload.get("stake", 50.0))
    use_time_decay = bool(payload.get("use_time_decay", False))
    xi = float(payload.get("xi", 0.0018))
    model_class = getattr(pb.models, model_name)
    start_date = str(payload.get("start_date") or frame["date"].min().date())
    end_date = str(payload.get("end_date") or frame["date"].max().date())

    def trainer(ctx):
        lookback = ctx.lookback.copy()
        if len(lookback) < 2:
            return None
        goals_home = lookback["goals_home"].astype(float).tolist()
        goals_away = lookback["goals_away"].astype(float).tolist()
        teams_home = lookback["team_home"].astype(str).tolist()
        teams_away = lookback["team_away"].astype(str).tolist()
        weights = None
        if use_time_decay and "date" in lookback.columns:
            weights = pb.models.dixon_coles_weights(list(lookback["date"]), xi=xi)
        if weights is not None:
            model = model_class(
                goals_home,
                goals_away,
                teams_home,
                teams_away,
                weights=weights,
            )
        else:
            model = model_class(
                goals_home,
                goals_away,
                teams_home,
                teams_away,
            )
        model.fit()
        return model

    def logic(ctx):
        if ctx.model is None:
            return
        fixture = ctx.fixture
        if odds_field not in fixture or pd.isna(fixture[odds_field]):
            return
        try:
            grid = ctx.model.predict(fixture["team_home"], fixture["team_away"])
        except ValueError as error:
            if "training data" in str(error):
                return
            raise
        probability = float(getattr(grid, market))
        odds = float(fixture[odds_field])
        if probability < threshold or odds <= 1.0:
            return

        if fixture["goals_home"] > fixture["goals_away"]:
            result = "home_win"
        elif fixture["goals_home"] < fixture["goals_away"]:
            result = "away_win"
        else:
            result = "draw"
        outcome = 1 if result == market else 0
        ctx.account.place_bet(odds=odds, stake=stake, outcome=outcome)

    backtest = pb.backtest.Backtest(frame, start_date=start_date, end_date=end_date)
    backtest.start(bankroll=bankroll, logic=logic, trainer=trainer)
    return {
        "summary": backtest.results(),
        "history": serialize_value(backtest.account.history),
        "tracker": serialize_value(backtest.account.tracker),
        "market": market,
        "oddsField": odds_field,
    }


def run_scraper_footballdata_fixtures(payload):
    import penaltyblog as pb

    scraper = pb.scrapers.FootballData(payload["competition"], payload["season"])
    return scraper.get_fixtures().head(int(payload.get("limit", 25)))


def run_scraper_fbref_fixtures(payload):
    import penaltyblog as pb

    scraper = pb.scrapers.FBRef(payload["competition"], payload["season"])
    return scraper.get_fixtures().head(int(payload.get("limit", 25)))


def run_scraper_fbref_stats(payload):
    import penaltyblog as pb

    scraper = pb.scrapers.FBRef(payload["competition"], payload["season"])
    stats = scraper.get_stats(payload.get("stat_type", "standard"))
    return {key: value.head(int(payload.get("limit", 25))) for key, value in stats.items()}


def run_scraper_understat_fixtures(payload):
    import penaltyblog as pb

    scraper = pb.scrapers.Understat(payload["competition"], payload["season"])
    return scraper.get_fixtures().head(int(payload.get("limit", 25)))


def run_scraper_understat_shots(payload):
    import penaltyblog as pb

    scraper = pb.scrapers.Understat(payload["competition"], payload["season"])
    return scraper.get_shots(payload["understat_id"]).head(int(payload.get("limit", 50)))


def run_scraper_clubelo_by_date(payload):
    import penaltyblog as pb

    scraper = pb.scrapers.ClubElo()
    return scraper.get_elo_by_date(payload.get("date")).head(int(payload.get("limit", 25)))


def run_scraper_clubelo_by_team(payload):
    import penaltyblog as pb

    scraper = pb.scrapers.ClubElo()
    return scraper.get_elo_by_team(payload["team"]).head(int(payload.get("limit", 50)))


def run_scraper_clubelo_team_names(payload):
    import penaltyblog as pb

    scraper = pb.scrapers.ClubElo()
    return scraper.get_team_names().head(int(payload.get("limit", 100)))


def run_fpl_current_gameweek(_payload):
    import penaltyblog as pb

    return {"current_gameweek": pb.fpl.get_current_gameweek()}


def run_fpl_gameweek_info(_payload):
    import penaltyblog as pb

    return pb.fpl.get_gameweek_info()


def run_fpl_player_id_mappings(_payload):
    import penaltyblog as pb

    return pb.fpl.get_player_id_mappings()


def run_fpl_player_data(_payload):
    import penaltyblog as pb

    return pb.fpl.get_player_data()


def run_fpl_player_history(payload):
    import penaltyblog as pb

    return pb.fpl.get_player_history(payload["player_id"])


def run_fpl_rankings(payload):
    import penaltyblog as pb

    return pb.fpl.get_rankings(page=int(payload.get("page", 1)))


def run_fpl_entry_picks(payload):
    import penaltyblog as pb

    return pb.fpl.get_entry_picks_by_gameweek(payload["entry_id"], gameweek=int(payload.get("gameweek", 1)))


# ── Matchflow operations ──────────────────────────────────────────────────────


def _build_predicate(spec):
    """Reconstruct a predicate callable from a JSON spec."""
    from penaltyblog.matchflow import (
        and_,
        not_,
        or_,
        where_contains,
        where_equals,
        where_exists,
        where_gt,
        where_gte,
        where_in,
        where_is_null,
        where_lt,
        where_lte,
        where_not_equals,
        where_not_in,
    )

    builders = {
        "where_equals": lambda s: where_equals(s["field"], s["value"]),
        "where_not_equals": lambda s: where_not_equals(s["field"], s["value"]),
        "where_in": lambda s: where_in(s["field"], s["values"]),
        "where_not_in": lambda s: where_not_in(s["field"], s["values"]),
        "where_contains": lambda s: where_contains(s["field"], s["substring"]),
        "where_exists": lambda s: where_exists(s["field"]),
        "where_is_null": lambda s: where_is_null(s["field"]),
        "where_gt": lambda s: where_gt(s["field"], s["threshold"]),
        "where_gte": lambda s: where_gte(s["field"], s["threshold"]),
        "where_lt": lambda s: where_lt(s["field"], s["threshold"]),
        "where_lte": lambda s: where_lte(s["field"], s["threshold"]),
        "and": lambda s: and_(*[_build_predicate(p) for p in s["predicates"]]),
        "or": lambda s: or_(*[_build_predicate(p) for p in s["predicates"]]),
        "not": lambda s: not_(_build_predicate(s["predicate"])),
    }
    kind = spec["type"]
    if kind not in builders:
        raise ValueError(f"Unknown predicate type: {kind}")
    return builders[kind](spec)


def _apply_steps(flow, steps):
    """Apply a list of transform step dicts to a Flow."""
    from penaltyblog.matchflow import Flow

    for step in steps:
        op = step["op"]
        if op == "filter":
            if "query" in step:
                flow = flow.query(step["query"])
            elif "predicate" in step:
                flow = flow.filter(_build_predicate(step["predicate"]))
        elif op == "select":
            flow = flow.select(*step["fields"])
        elif op == "rename":
            flow = flow.rename(**step["mapping"])
        elif op == "drop":
            flow = flow.drop(*step["keys"])
        elif op == "dropna":
            flow = flow.dropna(*(step.get("fields") or []))
        elif op == "flatten":
            flow = flow.flatten()
        elif op == "explode":
            flow = flow.explode(*step["fields"])
        elif op == "distinct":
            flow = flow.distinct(*step.get("keys", []), keep=step.get("keep", "first"))
        elif op == "sort":
            asc = step.get("ascending", True)
            flow = flow.sort_by(*step["keys"], ascending=asc)
        elif op == "limit":
            flow = flow.limit(step["count"])
        elif op == "sample_n":
            flow = flow.sample_n(step["n"], seed=step.get("seed"))
        elif op == "sample_fraction":
            flow = flow.sample_fraction(step["p"], seed=step.get("seed"))
        elif op == "group_summary":
            agg_spec = {}
            for name, spec_val in step["aggregations"].items():
                if isinstance(spec_val, str):
                    agg_spec[name] = spec_val
                elif isinstance(spec_val, list) and len(spec_val) == 2:
                    agg_spec[name] = tuple(spec_val)
                else:
                    agg_spec[name] = spec_val
            flow = flow.group_by(*step["keys"]).summary(agg_spec)
        elif op == "pivot":
            flow = flow.pivot(
                index=step["index"],
                columns=step["columns"],
                values=step["values"],
            )
        elif op == "split_array":
            flow = flow.split_array(step["field"], into=step.get("into"))
        elif op == "opta_filter":
            # Filter by Opta event type IDs and/or qualifier IDs
            from penaltyblog.matchflow import get_opta_mappings

            mappings = get_opta_mappings()
            event_ids = step.get("event_type_ids", [])
            qualifier_ids = step.get("qualifier_ids", [])
            event_field = step.get("event_type_field", "type_id")
            qualifier_field = step.get("qualifier_field", "qualifier_id")
            if event_ids:
                ids_set = set(int(x) for x in event_ids)
                flow = flow.filter(lambda row, _ids=ids_set, _f=event_field: row.get(_f) in _ids)
            if qualifier_ids:
                ids_set_q = set(int(x) for x in qualifier_ids)
                flow = flow.filter(lambda row, _ids=ids_set_q, _f=qualifier_field: row.get(_f) in _ids)
        elif op == "join":
            right = _run_matchflow_pipeline(step["right"])
            flow = flow.join(right, on=step["on"], how=step.get("how", "left"))
        elif op == "concat":
            others = [_run_matchflow_pipeline(p) for p in step["others"]]
            flow = flow.concat(*others)
        else:
            raise ValueError(f"Unknown matchflow step: {op}")
    return flow


def _run_matchflow_pipeline(spec):
    """Build and return a Flow from a pipeline spec (source + steps)."""
    from penaltyblog.matchflow import Flow

    source = spec["source"]
    src_type = source["type"]
    if src_type == "list":
        flow = Flow.from_list(source["records"])
    elif src_type == "json":
        flow = Flow.from_json(source["path"])
    elif src_type == "jsonl":
        flow = Flow.from_jsonl(source["path"])
    elif src_type == "folder":
        flow = Flow.from_folder(source["path"])
    elif src_type == "glob":
        flow = Flow.from_glob(source["pattern"])
    else:
        raise ValueError(f"Unknown matchflow source type: {src_type}")

    return _apply_steps(flow, spec.get("steps", []))


def run_matchflow_execute(payload):
    """Execute a matchflow pipeline and return collected rows."""
    flow = _run_matchflow_pipeline(payload["pipeline"])
    limit = int(payload.get("limit", 500))
    results = flow.head(limit) if limit else flow.collect()
    return {"rows": results, "count": len(results)}


def run_matchflow_schema(payload):
    """Infer schema of a matchflow pipeline output."""
    flow = _run_matchflow_pipeline(payload["pipeline"])
    schema = flow.schema()
    return {k: v.__name__ if hasattr(v, "__name__") else str(v) for k, v in schema.items()}


def run_matchflow_explain(payload):
    """Return the optimized plan for a pipeline."""
    import io

    flow = _run_matchflow_pipeline(payload["pipeline"])
    buf = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(buf):
        flow.explain()
    return {"plan": buf.getvalue()}


# ── Opta mappings ─────────────────────────────────────────────────────────────


def run_opta_mappings(_payload):
    from penaltyblog.matchflow import get_opta_mappings

    return get_opta_mappings()


# ── Pitch visualization ──────────────────────────────────────────────────────


def run_pitch_render(payload):
    """Render a pitch visualization and return Plotly HTML."""
    from penaltyblog.viz import Pitch

    cfg = payload.get("config", {})
    pitch = Pitch(
        provider=cfg.get("provider", "statsbomb"),
        width=int(cfg.get("width", 700)),
        height=int(cfg.get("height", 500)),
        theme=cfg.get("theme", "minimal"),
        orientation=cfg.get("orientation", "horizontal"),
        view=cfg.get("view", "full"),
        title=cfg.get("title"),
        subtitle=cfg.get("subtitle"),
        show_axis=bool(cfg.get("show_axis", False)),
        show_legend=bool(cfg.get("show_legend", False)),
        show_spots=bool(cfg.get("show_spots", True)),
    )

    for layer in payload.get("layers", []):
        ltype = layer["type"]
        data = layer.get("data", [])
        opts = {k: v for k, v in layer.items() if k not in ("type", "data")}
        if ltype == "scatter":
            pitch.plot_scatter(data, **opts)
        elif ltype == "heatmap":
            pitch.plot_heatmap(data, **opts)
        elif ltype == "arrows":
            pitch.plot_arrows(data, **opts)
        elif ltype == "comets":
            pitch.plot_comets(data, **opts)
        elif ltype == "kde":
            pitch.plot_kde(data, **opts)

    html = pitch.fig.to_html(full_html=False, include_plotlyjs="cdn")
    return {"html": html}


# ── Bayesian diagnostics ─────────────────────────────────────────────────────


def run_bayesian_diagnostics(payload):
    """Run numerical diagnostics on a fitted Bayesian model."""
    import penaltyblog as pb

    goals_home = payload["goals_home"]
    goals_away = payload["goals_away"]
    teams_home = payload["teams_home"]
    teams_away = payload["teams_away"]
    model_name = payload.get("model", "BayesianGoalModel")

    model_class = getattr(pb.models, model_name)
    model = model_class(goals_home, goals_away, teams_home, teams_away)
    model.fit()

    diagnostics = model.get_diagnostics()
    return diagnostics


def run_bayesian_diagnostic_plots(payload):
    """Generate Bayesian diagnostic plots and return Plotly HTML."""
    import penaltyblog as pb
    from penaltyblog.viz import (
        plot_autocorr,
        plot_convergence,
        plot_diagnostics,
        plot_posterior,
        plot_trace,
    )

    goals_home = payload["goals_home"]
    goals_away = payload["goals_away"]
    teams_home = payload["teams_home"]
    teams_away = payload["teams_away"]
    model_name = payload.get("model", "BayesianGoalModel")
    plot_type = payload.get("plot_type", "diagnostics")

    model_class = getattr(pb.models, model_name)
    model = model_class(goals_home, goals_away, teams_home, teams_away)
    model.fit()

    plot_fns = {
        "trace": plot_trace,
        "autocorr": plot_autocorr,
        "posterior": plot_posterior,
        "convergence": plot_convergence,
        "diagnostics": plot_diagnostics,
    }
    plot_fn = plot_fns.get(plot_type, plot_diagnostics)
    params = payload.get("params")
    kwargs = {}
    if params:
        kwargs["params"] = params

    fig = plot_fn(model, **kwargs)
    html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    return {"html": html}


OPERATIONS = {
    "catalog": catalog,
    "model_fit_predict": run_model_fit_predict,
    "goal_expectancy": run_goal_expectancy,
    "goal_expectancy_extended": run_goal_expectancy_extended,
    "dixon_coles_weights": run_dixon_coles_weights,
    "calculate_implied": run_calculate_implied,
    "kelly_criterion": run_kelly,
    "multiple_kelly_criterion": run_multiple_kelly,
    "identify_value_bet": run_identify_value,
    "find_arbitrage_opportunities": run_find_arbitrage,
    "arbitrage_hedge": run_arbitrage_hedge,
    "convert_odds": run_convert_odds,
    "elo_ratings": run_elo_ratings,
    "pi_ratings": run_pi_ratings,
    "colley_ratings": run_colley_ratings,
    "massey_ratings": run_massey_ratings,
    "score_predictions": run_score_predictions,
    "backtest_run": run_backtest,
    "scraper_footballdata_fixtures": run_scraper_footballdata_fixtures,
    "scraper_fbref_fixtures": run_scraper_fbref_fixtures,
    "scraper_fbref_stats": run_scraper_fbref_stats,
    "scraper_understat_fixtures": run_scraper_understat_fixtures,
    "scraper_understat_shots": run_scraper_understat_shots,
    "scraper_clubelo_by_date": run_scraper_clubelo_by_date,
    "scraper_clubelo_by_team": run_scraper_clubelo_by_team,
    "scraper_clubelo_team_names": run_scraper_clubelo_team_names,
    "fpl_current_gameweek": run_fpl_current_gameweek,
    "fpl_gameweek_info": run_fpl_gameweek_info,
    "fpl_player_id_mappings": run_fpl_player_id_mappings,
    "fpl_player_data": run_fpl_player_data,
    "fpl_player_history": run_fpl_player_history,
    "fpl_rankings": run_fpl_rankings,
    "fpl_entry_picks": run_fpl_entry_picks,
    "matchflow_execute": run_matchflow_execute,
    "matchflow_schema": run_matchflow_schema,
    "matchflow_explain": run_matchflow_explain,
    "opta_mappings": run_opta_mappings,
    "pitch_render": run_pitch_render,
    "bayesian_diagnostics": run_bayesian_diagnostics,
    "bayesian_diagnostic_plots": run_bayesian_diagnostic_plots,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        load_penaltyblog_paths()
        request = json.loads(args.payload)
        operation = request["operation"]
        payload = request.get("payload", {})

        if operation not in OPERATIONS:
            raise ValueError(f"Unknown penaltyblog operation: {operation}")

        result = OPERATIONS[operation](payload)
        response = {
            "ok": True,
            "result": {
                "operation": operation,
                "result": serialize_value(result),
            },
        }
    except Exception as error:
        response = {
            "ok": False,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }

    Path(args.output).write_text(json.dumps(response), encoding="utf-8")
    if not response["ok"]:
        print(response["traceback"], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
