import json
from datetime import datetime, timedelta, timezone
from functools import reduce
from operator import mul

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.match import Match, OddsEntry
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.scrape import ScrapeJob
from app.models.ticket import TicketBatch
from app.services.prediction_engine import execute_single_model_run, prediction_error_payload
from app.services.scraper import FOOTBALL_ALL_MARKETS, create_scrape_job, execute_scrape_job
from app.services.ticket_engine import create_ticket

WORLD_CUP_LEAGUE_SLUG = "world-cup"
WORLD_CUP_TRAINING_LEAGUE = "World Cup"
PREDICTION_MARKETS = ["1x2", "btts", "ou_2_5"]
TOP_MODEL_KEYS = [
    "PoissonGoalsModel",
    "DixonColesGoalModel",
    "BivariatePoissonGoalModel",
    "NegativeBinomialGoalModel",
]
DIFFICULTY_TIERS = [
    {"level": 1, "label": "Safest singles", "leg_count": 1, "difficulty": "safe"},
    {"level": 2, "label": "Low-risk doubles", "leg_count": 2, "difficulty": "low"},
    {"level": 3, "label": "Measured trebles", "leg_count": 3, "difficulty": "moderate"},
    {"level": 4, "label": "Balanced fourfolds", "leg_count": 4, "difficulty": "balanced"},
    {"level": 5, "label": "Ambitious fivefolds", "leg_count": 5, "difficulty": "hard"},
    {"level": 6, "label": "High-risk sixfolds", "leg_count": 6, "difficulty": "very_hard"},
    {"level": 7, "label": "Maximum sevenfolds", "leg_count": 7, "difficulty": "expert"},
]
COMBO_POOL_LIMIT = 80
WORLD_CUP_UPCOMING_LONG_TIMEOUT_SECONDS = 1800
WORLD_CUP_HISTORIC_MIN_PAGES = 3
WORLD_CUP_HISTORIC_TIMEOUT_SECONDS = 2400


def _parse_pipeline_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _publish_pipeline_progress(
    db: AsyncSession,
    parent_job_id: int | None,
    *,
    stage: str,
    scrape_jobs: list[ScrapeJob] | None = None,
    prediction_runs: list[PredictionRun] | None = None,
    skipped_historic_seasons: list[int] | None = None,
) -> None:
    if parent_job_id is None:
        await db.commit()
        return

    parent = await db.get(ScrapeJob, parent_job_id)
    if parent is None:
        await db.commit()
        return

    scrape_jobs = scrape_jobs or []
    prediction_runs = prediction_runs or []
    skipped_historic_seasons = skipped_historic_seasons or []
    parent.output = json.dumps(
        {
            "status": "running",
            "stage": stage,
            "summary": {
                "scrape_jobs": len(scrape_jobs),
                "pending_scrape_jobs": sum(1 for job in scrape_jobs if job.status == "pending"),
                "running_scrape_jobs": sum(1 for job in scrape_jobs if job.status == "running"),
                "completed_scrape_jobs": sum(1 for job in scrape_jobs if job.status == "completed"),
                "failed_scrape_jobs": sum(1 for job in scrape_jobs if job.status == "failed"),
                "skipped_historic_seasons": len(skipped_historic_seasons),
                "prediction_runs": len(prediction_runs),
                "completed_prediction_runs": sum(1 for run in prediction_runs if run.status == "completed"),
                "partial_prediction_runs": sum(1 for run in prediction_runs if run.status == "partial"),
                "failed_prediction_runs": sum(1 for run in prediction_runs if run.status == "failed"),
            },
            "scrape_job_ids": [job.id for job in scrape_jobs],
            "prediction_run_ids": [run.id for run in prediction_runs],
            "skipped_historic_seasons": skipped_historic_seasons,
            "errors": _pipeline_errors(scrape_jobs, prediction_runs),
        }
    )
    await db.commit()


def _is_timeout_error(error: str | None) -> bool:
    return bool(error and "timed out" in error.lower())


def _int_param(params: dict, key: str, default: int) -> int:
    value = params.get(key, default)
    if value in (None, ""):
        return default
    return int(value)


def _optional_int_param(params: dict, key: str) -> int | None:
    value = params.get(key)
    if value in (None, ""):
        return None
    return int(value)


def _bool_param(params: dict, key: str, default: bool) -> bool:
    value = params.get(key, default)
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _pipeline_errors(scrape_jobs: list[ScrapeJob], prediction_runs: list[PredictionRun]) -> list[dict]:
    return [
        {"type": "scrape", "id": job.id, "error": job.error}
        for job in scrape_jobs
        if job.status == "failed" and job.error
    ] + [
        {"type": "prediction", "id": run.id, "error": run.error}
        for run in prediction_runs
        if run.status in {"partial", "failed"} and run.error
    ]


def recent_world_cup_seasons(history_years: int, *, today: datetime | None = None) -> list[int]:
    now = today or datetime.now(timezone.utc)
    start_year = now.year - history_years
    return [year for year in range(now.year - 1, start_year - 1, -1) if year % 4 == 2]


def selected_world_cup_seasons(
    history_years: int,
    *,
    max_historic_seasons: int | None = None,
    today: datetime | None = None,
) -> list[int]:
    seasons = recent_world_cup_seasons(history_years, today=today)
    if max_historic_seasons is None:
        return seasons
    return seasons[: max(max_historic_seasons, 0)]


def _world_cup_historic_max_pages(max_historic_pages: int | None) -> int:
    if max_historic_pages is None:
        return WORLD_CUP_HISTORIC_MIN_PAGES
    return max(max_historic_pages, WORLD_CUP_HISTORIC_MIN_PAGES)


def _world_cup_upcoming_timeout(
    all_markets: bool,
    odds_history: bool,
    timeout_seconds: int | None = None,
) -> int | None:
    if timeout_seconds is not None:
        return timeout_seconds
    if all_markets or odds_history:
        return WORLD_CUP_UPCOMING_LONG_TIMEOUT_SECONDS
    return None


def _world_cup_competition_clause():
    return or_(
        Match.competition.ilike("%World Cup%"),
        Match.competition.ilike("%World Championship%"),
        Match.competition.ilike("%FIFA World Cup%"),
    )


async def _target_world_cup_match_ids(db: AsyncSession, future_days: int) -> list[int]:
    now = datetime.now(timezone.utc)
    upper = now + timedelta(days=max(future_days, 1))
    result = await db.execute(
        select(Match.id)
        .where(
            Match.sport == "football",
            Match.status == "scheduled",
            Match.match_date.is_not(None),
            Match.match_date >= now,
            Match.match_date <= upper,
            _world_cup_competition_clause(),
        )
        .order_by(Match.match_date.asc(), Match.id.asc())
    )
    return [row[0] for row in result.all()]


async def _target_world_cup_match_ids_for_window(
    db: AsyncSession,
    *,
    future_days: int,
    target_date_from: str | None = None,
    target_date_to: str | None = None,
) -> list[int]:
    start = _parse_pipeline_datetime(target_date_from)
    end = _parse_pipeline_datetime(target_date_to)
    if start is None or end is None:
        return await _target_world_cup_match_ids(db, future_days)

    result = await db.execute(
        select(Match.id)
        .where(
            Match.sport == "football",
            Match.status == "scheduled",
            Match.match_date.is_not(None),
            Match.match_date >= start,
            Match.match_date <= end,
            _world_cup_competition_clause(),
        )
        .order_by(Match.match_date.asc(), Match.id.asc())
    )
    return [row[0] for row in result.all()]


async def _run_scrape_jobs(
    db: AsyncSession,
    *,
    future_days: int,
    history_years: int,
    all_markets: bool,
    odds_history: bool,
    max_historic_pages: int | None,
    max_historic_seasons: int | None = None,
    upcoming_timeout_seconds: int | None = None,
    historic_timeout_seconds: int | None = None,
    scraper_engine: str = "playwright",
    target_date: str | None = None,
    parent_job_id: int | None = None,
) -> tuple[list[ScrapeJob], list[int]]:
    jobs = []
    skipped_historic_seasons: list[int] = []
    now = datetime.now(timezone.utc)
    markets = FOOTBALL_ALL_MARKETS if all_markets else ["1x2", "btts", "over_under_2_5"]

    scrape_dates = (
        [target_date.replace("-", "")]
        if target_date
        else [(now + timedelta(days=offset)).strftime("%Y%m%d") for offset in range(max(future_days, 1))]
    )

    upcoming_timeout = _world_cup_upcoming_timeout(all_markets, odds_history, upcoming_timeout_seconds)
    for scrape_date_value in scrape_dates:
        params = {
            "command": "upcoming",
            "sport": "football",
            "leagues": [WORLD_CUP_LEAGUE_SLUG],
            "date": scrape_date_value,
            "markets": markets,
            "all_markets": all_markets,
            "odds_history": odds_history,
            "headless": True,
            "bookies_filter": "all",
            "concurrency": 2,
            "request_delay": 1.0,
            "scraper_engine": scraper_engine,
        }
        if upcoming_timeout is not None:
            params["timeout_seconds"] = upcoming_timeout
        job = await create_scrape_job(
            db,
            "scrape_odds",
            WORLD_CUP_LEAGUE_SLUG,
            params,
        )
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        jobs.append(job)
        await db.flush()
        await _publish_pipeline_progress(
            db,
            parent_job_id,
            stage=f"scraping_upcoming_{scrape_date_value}",
            scrape_jobs=jobs,
        )
        jobs[-1] = await execute_scrape_job(db, job.id)
        await _publish_pipeline_progress(
            db,
            parent_job_id,
            stage=f"scraped_upcoming_{scrape_date_value}",
            scrape_jobs=jobs,
            skipped_historic_seasons=skipped_historic_seasons,
        )

    historic_max_pages = _world_cup_historic_max_pages(max_historic_pages)
    historic_timeout = historic_timeout_seconds or WORLD_CUP_HISTORIC_TIMEOUT_SECONDS
    for season in selected_world_cup_seasons(
        history_years,
        max_historic_seasons=max_historic_seasons,
        today=now,
    ):
        job = await create_scrape_job(
            db,
            "scrape_odds",
            WORLD_CUP_LEAGUE_SLUG,
            {
                "command": "historic",
                "sport": "football",
                "leagues": [WORLD_CUP_LEAGUE_SLUG],
                "season": str(season),
                "markets": markets,
                "all_markets": all_markets,
                "odds_history": odds_history,
                "headless": True,
                "bookies_filter": "all",
                "concurrency": 2,
                "request_delay": 1.0,
                "scraper_engine": scraper_engine,
                "max_pages": historic_max_pages,
                "timeout_seconds": historic_timeout,
            },
        )
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        jobs.append(job)
        await db.flush()
        await _publish_pipeline_progress(
            db,
            parent_job_id,
            stage=f"scraping_historic_{season}",
            scrape_jobs=jobs,
            skipped_historic_seasons=skipped_historic_seasons,
        )
        jobs[-1] = await execute_scrape_job(db, job.id)
        await _publish_pipeline_progress(
            db,
            parent_job_id,
            stage=f"scraped_historic_{season}",
            scrape_jobs=jobs,
            skipped_historic_seasons=skipped_historic_seasons,
        )
        if jobs[-1].status == "failed" and _is_timeout_error(jobs[-1].error):
            await _publish_pipeline_progress(
                db,
                parent_job_id,
                stage=f"historic_timeout_continuing_after_{season}",
                scrape_jobs=jobs,
                skipped_historic_seasons=skipped_historic_seasons,
            )

    return jobs, skipped_historic_seasons


async def _run_top_predictions(
    db: AsyncSession,
    *,
    user_id: int,
    target_match_ids: list[int],
    training_limit: int,
) -> list[PredictionRun]:
    runs: list[PredictionRun] = []
    if not target_match_ids:
        return runs

    for model_key in TOP_MODEL_KEYS:
        run = PredictionRun(
            user_id=user_id,
            name=f"World Cup top model: {model_key}",
            model_type=model_key,
            ensemble=False,
            status="running",
            matches_count=len(target_match_ids),
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        try:
            summary = await execute_single_model_run(
                db=db,
                run_id=run.id,
                model_key=model_key,
                league=WORLD_CUP_TRAINING_LEAGUE,
                markets=PREDICTION_MARKETS,
                training_limit=training_limit,
                target_limit=len(target_match_ids),
                target_mode="matches",
                max_goals=10,
                target_match_ids=target_match_ids,
                use_time_decay=model_key == "DixonColesGoalModel",
            )
            run.status = (
                "completed" if summary.get("failed", 0) == 0 and summary.get("fallbacks", 0) == 0 else "partial"
            )
            run.matches_count = summary.get("targets", len(target_match_ids))
            if summary.get("failed", 0) or summary.get("fallbacks", 0):
                run.error = prediction_error_payload(summary)
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
        finally:
            run.completed_at = datetime.now(timezone.utc)
            runs.append(run)
            await db.flush()

    return runs


def _normalize_market(value: str) -> str:
    return value.strip().lower().replace(".", "_")


def _market_matches(prediction_market: str, odds_market: str) -> bool:
    prediction_market = _normalize_market(prediction_market)
    odds_market = _normalize_market(odds_market)

    if prediction_market == "1x2":
        return odds_market.startswith("1x2")
    if prediction_market == "btts":
        return odds_market.startswith("btts")
    if prediction_market in {"ou_2_5", "over_under_2_5"}:
        return odds_market.startswith("over_under_2_5") or odds_market.startswith("ou_2_5")
    return prediction_market == odds_market


def _probability_options(prediction: ModelPrediction) -> list[tuple[str, float]]:
    market = _normalize_market(prediction.market)
    if market == "1x2":
        return [
            ("home", prediction.home_prob),
            ("draw", prediction.draw_prob or 0.0),
            ("away", prediction.away_prob),
        ]
    if market == "btts":
        return [("yes", prediction.home_prob), ("no", prediction.away_prob)]
    if market in {"ou_2_5", "over_under_2_5"}:
        return [("over", prediction.home_prob), ("under", prediction.away_prob)]
    return []


def _best_odds_for_selection(
    prediction_market: str,
    selection: str,
    odds_entries: list[OddsEntry],
) -> tuple[float | None, str | None]:
    outcome_field = {
        "home": "home_odds",
        "draw": "draw_odds",
        "away": "away_odds",
        "yes": "home_odds",
        "no": "away_odds",
        "over": "home_odds",
        "under": "away_odds",
    }.get(selection)
    if not outcome_field:
        return None, None

    best_value: float | None = None
    best_bookmaker: str | None = None
    for odds in odds_entries:
        if not _market_matches(prediction_market, odds.market):
            continue
        value = getattr(odds, outcome_field, None)
        if value is None or value <= 1:
            continue
        if best_value is None or value > best_value:
            best_value = value
            best_bookmaker = odds.bookmaker
    return best_value, best_bookmaker


def _prediction_is_ticket_eligible(prediction: ModelPrediction) -> bool:
    quality = getattr(prediction, "quality_report", None)
    if not quality:
        return False
    reliability = quality.get("reliability", {}) if isinstance(quality, dict) else {}
    return bool(reliability.get("is_ticket_eligible", False))


def _prediction_reliability(prediction: ModelPrediction) -> dict:
    quality = getattr(prediction, "quality_report", None)
    if not isinstance(quality, dict):
        return {"label": "unknown", "score": 0, "block_reasons": ["missing_quality_report"]}
    reliability = quality.get("reliability", {})
    if not isinstance(reliability, dict):
        return {"label": "unknown", "score": 0, "block_reasons": ["missing_reliability_report"]}
    return {
        "label": reliability.get("label", "unknown"),
        "score": reliability.get("score", 0),
        "block_reasons": reliability.get("block_reasons", []),
    }


async def _build_top_ticket_candidates(
    db: AsyncSession,
    *,
    run_ids: list[int],
    limit: int,
    include_unreliable: bool = False,
) -> list[dict]:
    if not run_ids:
        return []

    result = await db.execute(
        select(ModelPrediction)
        .options(
            selectinload(ModelPrediction.match).selectinload(Match.odds),
            selectinload(ModelPrediction.run),
        )
        .where(ModelPrediction.run_id.in_(run_ids))
    )
    predictions = result.scalars().unique().all()
    aggregated: dict[tuple[int, str, str], dict] = {}

    for prediction in predictions:
        is_ticket_eligible = _prediction_is_ticket_eligible(prediction)
        if not include_unreliable and not is_ticket_eligible:
            continue

        match = prediction.match
        if not match:
            continue

        reliability = _prediction_reliability(prediction)

        for selection, probability in _probability_options(prediction):
            if probability <= 0:
                continue
            odds, bookmaker = _best_odds_for_selection(prediction.market, selection, match.odds)
            if odds is None:
                continue

            key = (match.id, prediction.market, selection)
            current = aggregated.get(key)
            if current is None:
                aggregated[key] = {
                    "match_id": match.id,
                    "match": f"{match.home_team} vs {match.away_team}",
                    "league": match.competition,
                    "kickoff": match.match_date.isoformat() if match.match_date else None,
                    "market": prediction.market,
                    "selection": selection,
                    "probability_sum": probability,
                    "probability_count": 1,
                    "odds": odds,
                    "bookmaker": bookmaker,
                    "model_types": {prediction.model_type},
                    "model_prediction_id": prediction.id,
                    "is_ticket_eligible": is_ticket_eligible,
                    "reliability": reliability,
                }
                continue

            current["probability_sum"] += probability
            current["probability_count"] += 1
            current["model_types"].add(prediction.model_type)
            current["is_ticket_eligible"] = current["is_ticket_eligible"] or is_ticket_eligible
            if reliability.get("score", 0) > current["reliability"].get("score", 0):
                current["reliability"] = reliability
            if odds > current["odds"]:
                current["odds"] = odds
                current["bookmaker"] = bookmaker
            if probability > current["probability_sum"] / current["probability_count"]:
                current["model_prediction_id"] = prediction.id

    candidates = []
    for item in aggregated.values():
        probability = item["probability_sum"] / item["probability_count"]
        candidates.append(
            {
                "match_id": item["match_id"],
                "match": item["match"],
                "league": item["league"],
                "kickoff": item["kickoff"],
                "market": item["market"],
                "selection": item["selection"],
                "probability": probability,
                "odds": item["odds"],
                "bookmaker": item["bookmaker"],
                "model_types": sorted(item["model_types"]),
                "model_prediction_id": item["model_prediction_id"],
                "expected_return_score": probability * item["odds"],
                "is_ticket_eligible": item["is_ticket_eligible"],
                "reliability": item["reliability"].get("label", "unknown"),
                "reliability_score": item["reliability"].get("score", 0),
                "quality_reasons": item["reliability"].get("block_reasons", []),
            }
        )

    candidates.sort(key=lambda entry: (entry["probability"], entry["expected_return_score"]), reverse=True)
    return candidates[:limit]


def _product(values: list[float]) -> float:
    return reduce(mul, values, 1.0)


def _ticket_combo(combo: tuple[dict, ...], *, rank: int) -> dict:
    legs = list(combo)
    combined_probability = _product([leg["probability"] for leg in legs])
    total_odds = _product([leg["odds"] for leg in legs])
    return {
        "rank": rank,
        "ticket_id": None,
        "ticket_type": "single" if len(legs) == 1 else "accumulator",
        "leg_count": len(legs),
        "combined_probability": combined_probability,
        "total_odds": total_odds,
        "expected_return_score": combined_probability * total_odds,
        "legs": legs,
    }


def _combo_sort_key(combo: tuple[dict, ...]) -> tuple[float, float, float]:
    probabilities = [leg["probability"] for leg in combo]
    odds = [leg["odds"] for leg in combo]
    combined_probability = _product(probabilities)
    total_odds = _product(odds)
    return combined_probability, combined_probability * total_odds, total_odds


def _unique_match_combinations(candidates: list[dict], leg_count: int, limit: int) -> list[tuple[dict, ...]]:
    pool = candidates[:COMBO_POOL_LIMIT]
    beam: list[tuple[dict, ...]] = [()]
    beam_size = max(limit * 25, 160)
    candidate_positions = {id(candidate): index for index, candidate in enumerate(pool)}

    for _ in range(leg_count):
        expanded: list[tuple[dict, ...]] = []
        seen: set[tuple[int, ...]] = set()
        for combo in beam:
            used_match_ids = {leg["match_id"] for leg in combo}
            for candidate in pool:
                if candidate["match_id"] in used_match_ids:
                    continue
                ordered = tuple(sorted((*combo, candidate), key=lambda leg: candidate_positions[id(leg)]))
                key = tuple(leg["model_prediction_id"] for leg in ordered)
                if key in seen:
                    continue
                seen.add(key)
                expanded.append(ordered)

        expanded.sort(key=_combo_sort_key, reverse=True)
        beam = expanded[:beam_size]
        if not beam:
            break

    return beam[:limit]


def _build_difficulty_ticket_tiers(candidates: list[dict], *, per_tier_count: int = 10) -> list[dict]:
    tiers: list[dict] = []

    for tier in DIFFICULTY_TIERS:
        combos = _unique_match_combinations(candidates, tier["leg_count"], per_tier_count)
        tickets = [_ticket_combo(combo, rank=index + 1) for index, combo in enumerate(combos)]
        tiers.append({**tier, "tickets": tickets})

    return tiers


async def _create_tiered_tickets(
    db: AsyncSession,
    *,
    user_id: int,
    tiers: list[dict],
    stake: float,
    batch_name: str = "World Cup probability tickets by difficulty",
    strategy: str = "world_cup_probability_7_tiers",
    ticket_status: str = "open",
) -> list[int]:
    ticket_candidates = [ticket for tier in tiers for ticket in tier["tickets"]]
    if not ticket_candidates:
        return []

    batch = TicketBatch(
        name=batch_name,
        strategy=strategy,
        tickets_count=0,
        total_stake=0.0,
    )
    db.add(batch)
    await db.flush()

    ticket_ids: list[int] = []
    for ticket_candidate in ticket_candidates:
        ticket = await create_ticket(
            db=db,
            user_id=user_id,
            ticket_type=ticket_candidate["ticket_type"],
            stake=stake,
            bankroll_id=None,
            legs_data=[
                {
                    "model_prediction_id": leg["model_prediction_id"],
                    "match_id": leg["match_id"],
                    "selection": leg["selection"],
                    "market": leg["market"],
                    "odds": leg["odds"],
                    "bookmaker": leg["bookmaker"],
                }
                for leg in ticket_candidate["legs"]
            ],
        )
        ticket.batch_id = batch.id
        ticket.status = ticket_status
        ticket_candidate["ticket_id"] = ticket.id
        ticket_ids.append(ticket.id)
        batch.tickets_count += 1
        batch.total_stake += stake

    await db.flush()
    return ticket_ids


async def run_world_cup_pipeline(
    db: AsyncSession,
    *,
    user_id: int,
    parent_job_id: int | None = None,
    future_days: int = 7,
    history_years: int = 10,
    all_markets: bool = True,
    odds_history: bool = True,
    max_historic_pages: int | None = None,
    max_historic_seasons: int | None = None,
    upcoming_timeout_seconds: int | None = None,
    historic_timeout_seconds: int | None = None,
    scraper_engine: str = "playwright",
    ticket_count: int = 10,
    ticket_stake: float = 10.0,
    create_tickets: bool = True,
    allow_experimental_tickets: bool = False,
    training_limit: int = 240,
    target_date: str | None = None,
    target_date_from: str | None = None,
    target_date_to: str | None = None,
) -> dict:
    scrape_jobs, skipped_historic_seasons = await _run_scrape_jobs(
        db,
        future_days=future_days,
        history_years=history_years,
        all_markets=all_markets,
        odds_history=odds_history,
        max_historic_pages=max_historic_pages,
        max_historic_seasons=max_historic_seasons,
        upcoming_timeout_seconds=upcoming_timeout_seconds,
        historic_timeout_seconds=historic_timeout_seconds,
        scraper_engine=scraper_engine,
        target_date=target_date,
        parent_job_id=parent_job_id,
    )
    target_match_ids = await _target_world_cup_match_ids_for_window(
        db,
        future_days=future_days,
        target_date_from=target_date_from,
        target_date_to=target_date_to,
    )
    prediction_runs = await _run_top_predictions(
        db,
        user_id=user_id,
        target_match_ids=target_match_ids,
        training_limit=training_limit,
    )
    await _publish_pipeline_progress(
        db,
        parent_job_id,
        stage="predictions_complete",
        scrape_jobs=scrape_jobs,
        prediction_runs=prediction_runs,
        skipped_historic_seasons=skipped_historic_seasons,
    )
    completed_run_ids = [run.id for run in prediction_runs if run.status in {"completed", "partial"}]
    candidate_pool = await _build_top_ticket_candidates(
        db,
        run_ids=completed_run_ids,
        limit=max(ticket_count * len(DIFFICULTY_TIERS) * 2, COMBO_POOL_LIMIT),
    )
    watchlist_candidates = []
    if not candidate_pool:
        watchlist_candidates = await _build_top_ticket_candidates(
            db,
            run_ids=completed_run_ids,
            limit=max(ticket_count * len(DIFFICULTY_TIERS) * 2, COMBO_POOL_LIMIT),
            include_unreliable=True,
        )
    difficulty_tiers = _build_difficulty_ticket_tiers(candidate_pool, per_tier_count=ticket_count)
    ticket_ids = (
        await _create_tiered_tickets(db, user_id=user_id, tiers=difficulty_tiers, stake=ticket_stake)
        if create_tickets
        else []
    )
    experimental_ticket_ids: list[int] = []
    experimental_difficulty_tiers: list[dict] = []
    if create_tickets and allow_experimental_tickets and not ticket_ids and watchlist_candidates:
        experimental_difficulty_tiers = _build_difficulty_ticket_tiers(
            watchlist_candidates, per_tier_count=ticket_count
        )
        experimental_ticket_ids = await _create_tiered_tickets(
            db,
            user_id=user_id,
            tiers=experimental_difficulty_tiers,
            stake=ticket_stake,
            batch_name="World Cup experimental watchlist tickets",
            strategy="world_cup_watchlist_experimental",
            ticket_status="watchlist",
        )

    return {
        "status": "completed",
        "summary": {
            "future_days": future_days,
            "target_date": target_date,
            "target_date_from": target_date_from,
            "target_date_to": target_date_to,
            "history_years": history_years,
            "historic_seasons": selected_world_cup_seasons(
                history_years,
                max_historic_seasons=max_historic_seasons,
            ),
            "max_historic_seasons": max_historic_seasons,
            "upcoming_timeout_seconds": _world_cup_upcoming_timeout(
                all_markets,
                odds_history,
                upcoming_timeout_seconds,
            ),
            "historic_timeout_seconds": historic_timeout_seconds or WORLD_CUP_HISTORIC_TIMEOUT_SECONDS,
            "scrape_jobs": len(scrape_jobs),
            "completed_scrape_jobs": sum(1 for job in scrape_jobs if job.status == "completed"),
            "failed_scrape_jobs": sum(1 for job in scrape_jobs if job.status == "failed"),
            "skipped_historic_seasons": len(skipped_historic_seasons),
            "target_matches": len(target_match_ids),
            "prediction_runs": len(prediction_runs),
            "completed_prediction_runs": sum(1 for run in prediction_runs if run.status == "completed"),
            "partial_prediction_runs": sum(1 for run in prediction_runs if run.status == "partial"),
            "failed_prediction_runs": sum(1 for run in prediction_runs if run.status == "failed"),
            "top_candidates": len(candidate_pool),
            "watchlist_candidates": len(watchlist_candidates),
            "ticket_generation_blocked": bool(watchlist_candidates and not candidate_pool),
            "difficulty_tiers": len(difficulty_tiers),
            "tiered_ticket_candidates": sum(len(tier["tickets"]) for tier in difficulty_tiers),
            "created_tickets": len(ticket_ids),
            "created_experimental_tickets": len(experimental_ticket_ids),
            "ticket_generation_mode": "experimental_watchlist" if experimental_ticket_ids else "safe",
            "scraped_markets": "all_football" if all_markets else "core_prediction",
        },
        "scrape_job_ids": [job.id for job in scrape_jobs],
        "prediction_run_ids": [run.id for run in prediction_runs],
        "created_ticket_ids": ticket_ids,
        "created_experimental_ticket_ids": experimental_ticket_ids,
        "skipped_historic_seasons": skipped_historic_seasons,
        "top_candidates": candidate_pool[:ticket_count],
        "watchlist_candidates": watchlist_candidates[:ticket_count],
        "difficulty_tiers": difficulty_tiers,
        "experimental_difficulty_tiers": experimental_difficulty_tiers,
        "errors": _pipeline_errors(scrape_jobs, prediction_runs),
    }


async def execute_world_cup_pipeline_job(job_id: int, user_id: int) -> None:
    async with async_session_factory() as db:
        job = await db.get(ScrapeJob, job_id)
        if job is None:
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        params = job.params or {}
        try:
            result = await run_world_cup_pipeline(
                db,
                user_id=user_id,
                parent_job_id=job.id,
                future_days=_int_param(params, "future_days", 7),
                history_years=_int_param(params, "history_years", 10),
                all_markets=_bool_param(params, "all_markets", True),
                odds_history=_bool_param(params, "odds_history", True),
                max_historic_pages=_optional_int_param(params, "max_historic_pages"),
                max_historic_seasons=_optional_int_param(params, "max_historic_seasons"),
                upcoming_timeout_seconds=_optional_int_param(params, "upcoming_timeout_seconds"),
                historic_timeout_seconds=_optional_int_param(params, "historic_timeout_seconds"),
                scraper_engine=str(params.get("scraper_engine") or "playwright"),
                ticket_count=_int_param(params, "ticket_count", 10),
                ticket_stake=float(params.get("ticket_stake", 10.0) or 10.0),
                create_tickets=_bool_param(params, "create_tickets", True),
                allow_experimental_tickets=_bool_param(params, "allow_experimental_tickets", False),
                training_limit=_int_param(params, "training_limit", 240),
                target_date=params.get("target_date"),
                target_date_from=params.get("target_date_from"),
                target_date_to=params.get("target_date_to"),
            )
            job.status = "completed"
            job.output = json.dumps(result)
            job.error = None
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
