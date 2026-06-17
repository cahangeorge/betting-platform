import asyncio
from datetime import date as date_type
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.prediction import ModelPrediction, PredictionRun
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
        stmt = stmt.where(Match.match_date <= dt)
    stmt = stmt.order_by(Match.match_date.asc(), Match.created_at.asc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


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
    model_kwargs: dict | None = None,
    fit_kwargs: dict | None = None,
    use_time_decay: bool = False,
    time_decay_xi: float = 0.0018,
) -> dict:
    canonical_model_key = resolve_prediction_model_key(model_key)
    training = await fetch_training_matches(db, league, sport, training_limit)
    if len(training) < 20:
        raise ValueError(f"Insufficient training data: {len(training)} matches (need >=20)")

    targets = await fetch_target_matches(db, league, sport, target_mode, target_limit, target_match_ids)
    if not targets:
        raise ValueError("No target matches found for this selection.")

    goals_home = [m.home_score for m in training]
    goals_away = [m.away_score for m in training]
    teams_home = [m.home_team for m in training]
    teams_away = [m.away_team for m in training]
    weights: list[float] | None = None

    if use_time_decay:
        dated_training = [m for m in training if m.match_date is not None]
        if len(dated_training) != len(training):
            raise ValueError("Time-decay weighting requires match dates for all training matches")

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

    written = 0
    failed = 0
    concurrency = 3

    async def predict_one(target: Match) -> None:
        nonlocal written, failed
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
                return

            for market in markets:
                probs = extract_market_probabilities(grid, market)
                if not probs:
                    continue

                outcome_lookup = {entry["outcome"]: entry["probability"] for entry in probs}
                market_key = market.lower()
                if market_key == "1x2":
                    home_prob = outcome_lookup.get("home", 0)
                    draw_prob = outcome_lookup.get("draw")
                    away_prob = outcome_lookup.get("away", 0)
                    value_home = home_prob
                    value_draw = draw_prob
                    value_away = away_prob
                elif market_key == "btts":
                    home_prob = outcome_lookup.get("yes", 0)
                    draw_prob = None
                    away_prob = outcome_lookup.get("no", 0)
                    value_home = home_prob
                    value_draw = None
                    value_away = away_prob
                elif market_key in {"ou_2_5", "over_under", "overunder", "totals"}:
                    home_prob = outcome_lookup.get("over", 0)
                    draw_prob = None
                    away_prob = outcome_lookup.get("under", 0)
                    value_home = home_prob
                    value_draw = None
                    value_away = away_prob
                else:
                    # Fallback for unexpected market definitions.
                    home_prob = outcome_lookup.get("home", 0)
                    draw_prob = outcome_lookup.get("draw")
                    away_prob = outcome_lookup.get("away", 0)
                    value_home = home_prob
                    value_draw = draw_prob
                    value_away = away_prob

                row = ModelPrediction(
                    run_id=run_id,
                    model_type=model_key,
                    match_id=target.id,
                    market=market,
                    home_prob=home_prob,
                    draw_prob=draw_prob,
                    away_prob=away_prob,
                    value_home=value_home,
                    value_away=value_away,
                    value_draw=value_draw,
                )
                db.add(row)
                written += 1
        except BridgeError:
            failed += 1

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
        "target_matches": len(targets),
        "written": written,
        "failed": failed,
        "markets": markets,
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
    max_goals: int = 10,
    user_id: int | None = None,
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
        )
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.matches_count = summary["target_matches"]
        await db.flush()
        return {"run_id": run.id, "status": run.status}
    except Exception as e:
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(e)
        await db.flush()
        return {"run_id": run.id, "status": run.status, "error": str(e)}
