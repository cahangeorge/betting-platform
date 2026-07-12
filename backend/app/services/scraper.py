import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.live import broadcast_match_update, broadcast_odds_update
from app.models.match import Match, MatchSource, OddsEntry
from app.models.scrape import ScrapedDataset, ScrapeJob, ScrapeJobLog
from app.services.python_bridge import BridgeError, run_oddsharvester_json

logger = logging.getLogger(__name__)

ODDS_SOURCE = "OddsHarvester"
DEFAULT_MARKETS = ["1x2"]
FOOTBALL_ALL_MARKETS = [
    "1x2",
    "btts",
    "double_chance",
    "dnb",
    "over_under_0_5",
    "over_under_1",
    "over_under_1_25",
    "over_under_1_5",
    "over_under_1_75",
    "over_under_2",
    "over_under_2_25",
    "over_under_2_5",
    "over_under_2_75",
    "over_under_3",
    "over_under_3_25",
    "over_under_3_5",
    "over_under_3_75",
    "over_under_4",
    "over_under_4_25",
    "over_under_4_5",
    "over_under_4_75",
    "over_under_5",
    "over_under_5_25",
    "over_under_5_5",
    "over_under_5_75",
    "over_under_6",
    "over_under_6_25",
    "over_under_6_5",
    "over_under_6_75",
    "over_under_7_5",
    "over_under_8_5",
    "european_handicap_-4",
    "european_handicap_-3",
    "european_handicap_-2",
    "european_handicap_-1",
    "european_handicap_+1",
    "european_handicap_+2",
    "european_handicap_+3",
    "european_handicap_+4",
    "asian_handicap_-4",
    "asian_handicap_-3_75",
    "asian_handicap_-3_5",
    "asian_handicap_-3_25",
    "asian_handicap_-3",
    "asian_handicap_-2_75",
    "asian_handicap_-2_5",
    "asian_handicap_-2_25",
    "asian_handicap_-2",
    "asian_handicap_-1_75",
    "asian_handicap_-1_5",
    "asian_handicap_-1_25",
    "asian_handicap_-1",
    "asian_handicap_-0_75",
    "asian_handicap_-0_5",
    "asian_handicap_-0_25",
    "asian_handicap_0",
    "asian_handicap_+0_25",
    "asian_handicap_+0_5",
    "asian_handicap_+0_75",
    "asian_handicap_+1",
    "asian_handicap_+1_25",
    "asian_handicap_+1_5",
    "asian_handicap_+1_75",
    "asian_handicap_+2",
]

SCRAPE_DEDUP_CONTROL_KEYS = {
    "auto_interval_hours",
    "auto_scrape",
    "auto_scrape_requested",
    "avoid_rescraping",
    "dedup_skip",
    "dedup_skip_requested",
}

LIVE_RELEVANT_MATCH_STATUSES = {
    "live",
    "running",
    "active",
    "in_play",
    "halftime",
    "ht",
    "finished",
    "ft",
    "fulltime",
}

LIVE_RELEVANT_ODDS_MARKETS = {"1x2", "home_away", "homeaway", "match_winner", "matchwinner"}
FINAL_MATCH_STATUSES = {"finished", "ft", "fulltime", "completed", "final"}


def _normalize_scrape_value(value):
    if isinstance(value, dict):
        return {
            key: _normalize_scrape_value(value[key])
            for key in sorted(value)
            if key not in SCRAPE_DEDUP_CONTROL_KEYS and value[key] is not None
        }
    if isinstance(value, list):
        normalized = [_normalize_scrape_value(item) for item in value if item is not None]
        if all(not isinstance(item, (dict, list)) for item in normalized):
            return sorted(normalized)
        return normalized
    return value


def _normalize_status(value: str | None) -> str:
    return (value or "").strip().lower()


def _safe_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _match_broadcast_snapshot(match: Match | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {
        "external_id": match.external_id,
        "sport": match.sport,
        "home_team": match.home_team,
        "away_team": match.away_team,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "status": match.status,
        "match_date": _safe_iso(match.match_date),
        "competition": match.competition,
    }


def _is_live_relevant_match(match: Match) -> bool:
    status = _normalize_status(match.status)
    if status in LIVE_RELEVANT_MATCH_STATUSES:
        return True

    now = datetime.now(timezone.utc)
    if match.home_score is not None and match.away_score is not None:
        return True
    return bool(match.match_date and match.match_date <= now)


def _is_live_relevant_market(market_name: str) -> bool:
    return market_name.split(":", 1)[0].strip().lower() in LIVE_RELEVANT_ODDS_MARKETS


def _build_match_update_payload(match: Match) -> dict[str, Any]:
    return {
        "id": match.id,
        "external_id": match.external_id,
        "sport": match.sport,
        "competition": match.competition,
        "home_team": match.home_team,
        "away_team": match.away_team,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "status": match.status,
        "match_date": _safe_iso(match.match_date),
        "updated_at": _safe_iso(getattr(match, "updated_at", None)),
    }


def _build_odds_update_payload(
    *,
    match: Match,
    bookmaker: str,
    market: str,
    home_odds: float | None,
    draw_odds: float | None,
    away_odds: float | None,
    timestamp: datetime | None,
) -> dict[str, Any]:
    return {
        "match_id": match.id,
        "status": match.status,
        "bookmaker": bookmaker,
        "market": market,
        "home_odds": home_odds,
        "draw_odds": draw_odds,
        "away_odds": away_odds,
        "timestamp": _safe_iso(timestamp),
        "home_team": match.home_team,
        "away_team": match.away_team,
    }


def _schedule_post_commit_live_broadcasts(
    db: AsyncSession,
    *,
    match_updates: dict[int, dict[str, Any]],
    odds_updates: dict[int, dict[str, Any]],
) -> None:
    if not match_updates and not odds_updates:
        return
    if not hasattr(db, "sync_session"):
        return

    loop = asyncio.get_running_loop()
    sync_session = db.sync_session
    queued_match_updates = dict(match_updates)
    queued_odds_updates = dict(odds_updates)

    async def _dispatch() -> None:
        for match_id, payload in queued_match_updates.items():
            try:
                await broadcast_match_update(match_id, "match_updated", payload)
            except Exception:
                logger.exception("Failed to broadcast live match update for match_id=%s", match_id)

        for match_id, payload in queued_odds_updates.items():
            try:
                await broadcast_odds_update(match_id, payload)
            except Exception:
                logger.exception("Failed to broadcast live odds update for match_id=%s", match_id)

    @event.listens_for(sync_session, "after_commit", once=True)
    def _after_commit(_session) -> None:
        loop.create_task(_dispatch())


def _scrape_dedup_key(job: ScrapeJob) -> str:
    return json.dumps(
        {
            "job_type": job.job_type,
            "league": job.league,
            "params": _normalize_scrape_value(job.params or {}),
        },
        sort_keys=True,
        default=str,
    )


def _avoid_rescraping_requested(job: ScrapeJob) -> bool:
    params = job.params or {}
    return bool(params.get("dedup_skip_requested") or params.get("dedup_skip") or params.get("avoid_rescraping"))


async def _find_completed_duplicate_scrape_job(db: AsyncSession, job: ScrapeJob) -> ScrapeJob | None:
    stmt = (
        select(ScrapeJob)
        .where(
            ScrapeJob.id != job.id,
            ScrapeJob.job_type == job.job_type,
            ScrapeJob.status == "completed",
        )
        .order_by(ScrapeJob.created_at.desc())
        .limit(100)
    )
    if job.league is None:
        stmt = stmt.where(ScrapeJob.league.is_(None))
    else:
        stmt = stmt.where(ScrapeJob.league == job.league)

    target_key = _scrape_dedup_key(job)
    result = await db.execute(stmt)
    for candidate in result.scalars().all():
        if _scrape_dedup_key(candidate) == target_key:
            return candidate
    return None


async def append_scrape_job_log(
    db: AsyncSession,
    job_id: int,
    *,
    action: str,
    message: str,
    level: str = "info",
    metadata: dict | None = None,
) -> ScrapeJobLog:
    log = ScrapeJobLog(
        job_id=job_id,
        level=level,
        action=action,
        message=message,
        metadata_json=metadata,
    )
    db.add(log)
    await db.flush()
    return log


async def create_scrape_job(
    db: AsyncSession,
    job_type: str,
    league: str | None = None,
    params: dict | None = None,
) -> ScrapeJob:
    job = ScrapeJob(
        job_type=job_type,
        status="pending",
        league=league,
        params=params,
    )
    db.add(job)
    await db.flush()
    await append_scrape_job_log(
        db,
        job.id,
        action="job_created",
        message=f"Created scrape job {job.id}",
        metadata={"job_type": job_type, "league": league, "params": params or {}},
    )
    return job


async def create_result_refresh_job(db: AsyncSession, match_ids: list[int], *, user_id: int) -> ScrapeJob:
    """Create a real, source-addressable result refresh job for known matches only."""
    requested_ids = sorted({int(match_id) for match_id in match_ids})
    if not requested_ids:
        raise ValueError("At least one match ID is required for result refresh")

    source_stmt = (
        select(Match, MatchSource.url)
        .join(MatchSource, MatchSource.match_id == Match.id)
        .where(
            Match.id.in_(requested_ids),
            MatchSource.source == ODDS_SOURCE,
            MatchSource.url.is_not(None),
        )
    )
    source_result = await db.execute(source_stmt)
    rows = list(source_result.all())
    sources_by_match_id = {match.id: url for match, url in rows if url}
    missing_ids = sorted(set(requested_ids) - set(sources_by_match_id))
    if missing_ids:
        joined_ids = ", ".join(str(match_id) for match_id in missing_ids)
        raise ValueError(f"Result refresh requires an OddsHarvester source URL for match IDs: {joined_ids}")

    sports = {match.sport for match, _url in rows if match.sport}
    if len(sports) > 1:
        raise ValueError("Result refresh match IDs must belong to one sport")

    return await create_scrape_job(
        db,
        "refresh_results",
        params={
            "_created_by_user_id": user_id,
            "command": "upcoming",
            "sport": next(iter(sports), "football"),
            "match_ids": requested_ids,
            "match_links": [sources_by_match_id[match_id] for match_id in requested_ids],
            "result_refresh": True,
        },
    )


def _coerce_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _coerce_int(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_source_id(match_link: str | None) -> str | None:
    if not match_link:
        return None
    parsed = urlparse(match_link)
    fragment = parsed.fragment.strip("/")
    if fragment:
        return fragment
    path_parts = [part for part in parsed.path.split("/") if part]
    return path_parts[-1] if path_parts else None


def _derive_match_status(record: dict, match_date: datetime | None) -> str:
    now = datetime.now(timezone.utc)
    if match_date and match_date > now:
        return "scheduled"
    if _coerce_int(record.get("home_score")) is not None and _coerce_int(record.get("away_score")) is not None:
        return "finished"
    if match_date and match_date <= now:
        return "live"
    return "scheduled"


def _has_final_result(match: Match) -> bool:
    return (
        match.home_score is not None
        and match.away_score is not None
        and _normalize_status(match.status) in FINAL_MATCH_STATUSES
    )


def _has_conflicting_final_score(match: Match | None, record: dict) -> bool:
    """Return whether a completed match received a different complete score pair."""
    if match is None or not _has_final_result(match):
        return False

    incoming_home_score = _coerce_int(record.get("home_score"))
    incoming_away_score = _coerce_int(record.get("away_score"))
    return (
        incoming_home_score is not None
        and incoming_away_score is not None
        and (incoming_home_score, incoming_away_score) != (match.home_score, match.away_score)
    )


def _resolve_match_result(
    match: Match | None, record: dict, match_date: datetime | None
) -> tuple[str, int | None, int | None]:
    """Keep a persisted final result stable across incomplete or conflicting refreshes."""
    incoming_home_score = _coerce_int(record.get("home_score"))
    incoming_away_score = _coerce_int(record.get("away_score"))
    if match is not None and _has_final_result(match):
        if _has_conflicting_final_score(match, record):
            logger.warning(
                "Ignored conflicting final score refresh for match_id=%s: persisted=%s-%s incoming=%s-%s",
                getattr(match, "id", None),
                match.home_score,
                match.away_score,
                incoming_home_score,
                incoming_away_score,
            )
        return match.status, match.home_score, match.away_score

    status = _derive_match_status(record, match_date)
    if status == "scheduled":
        return status, None, None
    return status, incoming_home_score, incoming_away_score


def _market_key_to_odds(
    market_key: str,
    bookmaker_market: dict,
) -> tuple[float | None, float | None, float | None]:
    key = market_key.removesuffix("_market")

    if key == "1x2":
        return (
            _coerce_float(bookmaker_market.get("1")),
            _coerce_float(bookmaker_market.get("X")),
            _coerce_float(bookmaker_market.get("2")),
        )

    if key == "double_chance":
        return (
            _coerce_float(bookmaker_market.get("1X")),
            _coerce_float(bookmaker_market.get("12")),
            _coerce_float(bookmaker_market.get("X2")),
        )

    if key == "dnb":
        return (
            _coerce_float(bookmaker_market.get("1")),
            None,
            _coerce_float(bookmaker_market.get("2")),
        )

    if key in {"home_away", "match_winner"}:
        return (
            _coerce_float(bookmaker_market.get("1")),
            None,
            _coerce_float(bookmaker_market.get("2")),
        )

    if key == "btts":
        return (
            _coerce_float(bookmaker_market.get("Yes") or bookmaker_market.get("odds_yes")),
            None,
            _coerce_float(bookmaker_market.get("No") or bookmaker_market.get("odds_no")),
        )

    if key.startswith("over_under"):
        return (
            _coerce_float(bookmaker_market.get("Over") or bookmaker_market.get("odds_over")),
            None,
            _coerce_float(bookmaker_market.get("Under") or bookmaker_market.get("odds_under")),
        )

    if key.startswith("european_handicap"):
        return (
            _coerce_float(bookmaker_market.get("1")),
            _coerce_float(bookmaker_market.get("X")),
            _coerce_float(bookmaker_market.get("2")),
        )

    if key.startswith("asian_handicap"):
        return (
            _coerce_float(bookmaker_market.get("1")),
            None,
            _coerce_float(bookmaker_market.get("2")),
        )

    return (None, None, None)


def _normalize_market_name(market_key: str, bookmaker_market: dict) -> str:
    period = bookmaker_market.get("period")
    base = market_key.removesuffix("_market")
    if period:
        return f"{base}:{period}"
    return base


def _job_label(job: ScrapeJob) -> str:
    if job.league:
        return f"{job.job_type}:{job.league}"
    return job.job_type


def _build_oddsharvester_args(job: ScrapeJob) -> list[str]:
    params = job.params or {}
    command = params.get("command", "upcoming")
    sport = str(params.get("sport", "football"))
    markets = params.get("markets")
    leagues = params.get("leagues")
    date = params.get("date")
    season = params.get("season")
    max_pages = params.get("max_pages")

    args = [str(command), "--sport", sport]

    if leagues:
        if isinstance(leagues, list):
            league_value = ",".join(str(league) for league in leagues if league)
        else:
            league_value = str(leagues)
        if league_value:
            args.extend(["--league", league_value])
    elif job.league:
        args.extend(["--league", job.league])

    if date:
        args.extend(["--date", str(date)])
    elif command == "upcoming" and not leagues and not job.league:
        future_days = int(params.get("future_days", 1) or 1)
        scrape_date = datetime.now(timezone.utc) + timedelta(days=max(future_days, 1))
        args.extend(["--date", scrape_date.strftime("%Y%m%d")])

    if command == "historic":
        if season:
            args.extend(["--season", str(season)])
        if max_pages:
            args.extend(["--max-pages", str(max_pages)])

    if params.get("all_markets") and sport == "football":
        markets = FOOTBALL_ALL_MARKETS

    if markets:
        if isinstance(markets, list):
            market_value = ",".join(str(market) for market in markets if market)
        else:
            market_value = str(markets)
        if market_value:
            args.extend(["--market", market_value])
    else:
        args.extend(["--market", ",".join(DEFAULT_MARKETS)])

    match_links = params.get("match_links")
    if match_links:
        if not isinstance(match_links, list):
            raise ValueError("match_links must be a list")
        for match_link in match_links:
            if match_link:
                args.extend(["--match-link", str(match_link)])

    if params.get("target_bookmaker"):
        args.extend(["--target-bookmaker", str(params["target_bookmaker"])])

    if params.get("odds_history"):
        args.append("--odds-history")

    if params.get("preview_submarkets_only") or params.get("preview_only"):
        args.append("--preview-only")

    if params.get("headless", True):
        args.append("--headless")

    if params.get("bookies_filter"):
        args.extend(["--bookies-filter", str(params["bookies_filter"])])

    if params.get("period"):
        args.extend(["--period", str(params["period"])])

    if params.get("concurrency"):
        args.extend(["--concurrency", str(params["concurrency"])])

    if params.get("request_delay"):
        args.extend(["--request-delay", str(params["request_delay"])])

    if params.get("scraper_engine"):
        args.extend(["--engine", str(params["scraper_engine"])])

    return args


def _job_oddsharvester_timeout(job: ScrapeJob) -> int | None:
    params = job.params or {}
    return _coerce_int(params.get("timeout_seconds") or params.get("oddsharvester_timeout_seconds"))


async def _upsert_match_from_record(db: AsyncSession, record: dict, sport: str) -> tuple[Match, bool, bool]:
    match_link = record.get("match_link")
    source_id = _extract_source_id(match_link)

    match: Match | None = None
    if match_link:
        source_stmt = select(MatchSource).where(MatchSource.source == ODDS_SOURCE, MatchSource.url == match_link)
        source_result = await db.execute(source_stmt)
        source = source_result.scalar_one_or_none()
        if source is not None:
            match = await db.get(Match, source.match_id)

    match_date = _coerce_datetime(record.get("match_date"))
    if match is None and source_id:
        match_stmt = select(Match).where(Match.external_id == source_id)
        match_result = await db.execute(match_stmt)
        match = match_result.scalar_one_or_none()

    previous_snapshot = _match_broadcast_snapshot(match)

    if match is None:
        match = Match(
            external_id=source_id,
            sport=sport,
            home_team=str(record.get("home_team", "Unknown Home")),
            away_team=str(record.get("away_team", "Unknown Away")),
        )
        db.add(match)
        await db.flush()

    final_score_conflict = _has_conflicting_final_score(match, record)
    status, home_score, away_score = _resolve_match_result(match, record, match_date)

    match.external_id = source_id or match.external_id
    match.sport = sport
    match.home_team = str(record.get("home_team") or match.home_team)
    match.away_team = str(record.get("away_team") or match.away_team)
    match.home_score = home_score
    match.away_score = away_score
    match.match_date = match_date or match.match_date
    match.competition = record.get("league_name") or match.competition
    match.status = status

    source_stmt = select(MatchSource).where(MatchSource.match_id == match.id, MatchSource.source == ODDS_SOURCE)
    source_result = await db.execute(source_stmt)
    existing_source = source_result.scalar_one_or_none()
    if existing_source is None:
        db.add(
            MatchSource(
                match_id=match.id,
                source=ODDS_SOURCE,
                source_id=source_id,
                url=match_link,
            )
        )
    else:
        existing_source.source_id = source_id or existing_source.source_id
        existing_source.url = match_link or existing_source.url

    await db.flush()
    current_snapshot = _match_broadcast_snapshot(match)
    return match, previous_snapshot != current_snapshot, final_score_conflict


async def _ingest_match_odds(db: AsyncSession, match: Match, record: dict) -> dict[str, int | dict[str, Any] | None]:
    written = 0
    changed = 0
    broadcast_payload: dict[str, Any] | None = None
    scrape_timestamp = _coerce_datetime(record.get("scraped_date"))

    for market_key, market_rows in record.items():
        if not market_key.endswith("_market") or not isinstance(market_rows, list):
            continue

        for bookmaker_market in market_rows:
            if not isinstance(bookmaker_market, dict):
                continue

            home_odds, draw_odds, away_odds = _market_key_to_odds(market_key, bookmaker_market)
            if home_odds is None and draw_odds is None and away_odds is None:
                continue

            market_name = _normalize_market_name(market_key, bookmaker_market)
            bookmaker = str(bookmaker_market.get("bookmaker_name", "Unknown"))

            existing_stmt = select(OddsEntry).where(
                OddsEntry.match_id == match.id,
                OddsEntry.bookmaker == bookmaker,
                OddsEntry.market == market_name,
                OddsEntry.timestamp == scrape_timestamp,
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()

            if existing is None:
                db.add(
                    OddsEntry(
                        match_id=match.id,
                        bookmaker=bookmaker,
                        market=market_name,
                        home_odds=home_odds,
                        draw_odds=draw_odds,
                        away_odds=away_odds,
                        timestamp=scrape_timestamp,
                    )
                )
                written += 1
                changed += 1
                if _is_live_relevant_market(market_name):
                    broadcast_payload = _build_odds_update_payload(
                        match=match,
                        bookmaker=bookmaker,
                        market=market_name,
                        home_odds=home_odds,
                        draw_odds=draw_odds,
                        away_odds=away_odds,
                        timestamp=scrape_timestamp,
                    )
            else:
                entry_changed = any(
                    (
                        existing.home_odds != home_odds,
                        existing.draw_odds != draw_odds,
                        existing.away_odds != away_odds,
                        existing.timestamp != scrape_timestamp,
                    )
                )
                existing.home_odds = home_odds
                existing.draw_odds = draw_odds
                existing.away_odds = away_odds
                existing.timestamp = scrape_timestamp
                if entry_changed:
                    changed += 1
                    if _is_live_relevant_market(market_name):
                        broadcast_payload = _build_odds_update_payload(
                            match=match,
                            bookmaker=bookmaker,
                            market=market_name,
                            home_odds=home_odds,
                            draw_odds=draw_odds,
                            away_odds=away_odds,
                            timestamp=scrape_timestamp,
                        )

    await db.flush()
    return {
        "written": written,
        "changed": changed,
        "broadcast_payload": broadcast_payload,
    }


async def _ingest_scraped_payload(
    db: AsyncSession, job: ScrapeJob, payload: list[dict]
) -> tuple[dict[str, int | str], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    params = job.params or {}
    sport = str(params.get("sport", "football"))

    await append_scrape_job_log(
        db,
        job.id,
        action="payload_received",
        message=f"Received {len(payload)} scraped records",
        metadata={"records": len(payload), "sport": sport},
    )

    dataset = ScrapedDataset(
        name=f"{_job_label(job)}:{datetime.now(timezone.utc).isoformat()}",
        source=ODDS_SOURCE,
        data={
            "job_id": job.id,
            "job_type": job.job_type,
            "league": job.league,
            "params": params,
            "matches": payload,
        },
        matches_count=len(payload),
    )
    db.add(dataset)
    await db.flush()
    await append_scrape_job_log(
        db,
        job.id,
        action="dataset_created",
        message=f"Created scraped dataset {dataset.id}",
        metadata={"dataset_id": dataset.id, "records": len(payload)},
    )

    matches_written = 0
    odds_written = 0
    skipped_records = 0
    final_score_conflicts = 0
    match_updates: dict[int, dict[str, Any]] = {}
    odds_updates: dict[int, dict[str, Any]] = {}
    for record in payload:
        if not isinstance(record, dict):
            skipped_records += 1
            continue
        match, match_changed, final_score_conflict = await _upsert_match_from_record(db, record, sport=sport)
        matches_written += 1
        if final_score_conflict:
            final_score_conflicts += 1
            await append_scrape_job_log(
                db,
                job.id,
                action="final_score_conflict",
                level="warning",
                message=f"Retained persisted final score for match {match.id}; refresh reported a conflicting score",
                metadata={
                    "match_id": match.id,
                    "persisted_score": {"home": match.home_score, "away": match.away_score},
                    "incoming_score": {
                        "home": _coerce_int(record.get("home_score")),
                        "away": _coerce_int(record.get("away_score")),
                    },
                },
            )
        odds_result = await _ingest_match_odds(db, match, record)
        odds_written += int(odds_result["written"])

        if _is_live_relevant_match(match):
            if match_changed:
                match_updates[match.id] = _build_match_update_payload(match)
            odds_payload = odds_result.get("broadcast_payload")
            if odds_payload:
                odds_updates[match.id] = odds_payload

    await append_scrape_job_log(
        db,
        job.id,
        action="records_upserted",
        message=f"Upserted {matches_written} matches and wrote {odds_written} odds rows",
        metadata={
            "matches_upserted": matches_written,
            "odds_written": odds_written,
            "skipped_records": skipped_records,
            "final_score_conflicts": final_score_conflicts,
        },
    )

    return (
        {
            "dataset_id": dataset.id,
            "matches_count": len(payload),
            "matches_upserted": matches_written,
            "odds_written": odds_written,
        },
        match_updates,
        odds_updates,
    )


async def execute_scrape_job(db: AsyncSession, job_id: int) -> ScrapeJob:
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise LookupError(f"ScrapeJob {job_id} not found")

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.flush()
    await append_scrape_job_log(
        db,
        job.id,
        action="job_started",
        message=f"Started scrape job {job.id}",
        metadata={"job_type": job.job_type, "league": job.league, "params": job.params or {}},
    )

    try:
        if _avoid_rescraping_requested(job):
            duplicate = await _find_completed_duplicate_scrape_job(db, job)
            if duplicate is not None:
                summary = {
                    "skipped": True,
                    "reason": "duplicate_completed_job",
                    "reused_job_id": duplicate.id,
                }
                job.status = "completed"
                job.output = json.dumps(summary)
                job.completed_at = datetime.now(timezone.utc)
                await append_scrape_job_log(
                    db,
                    job.id,
                    action="rescrape_skipped",
                    message=f"Skipped scrape job {job.id}; reused completed job {duplicate.id}",
                    metadata=summary,
                )
                await db.flush()
                return job

        if job.job_type in {"oddsportal", "scrape_odds", "refresh_results"}:
            if job.job_type == "refresh_results" and not (job.params or {}).get("match_links"):
                raise ValueError("Result refresh job is missing source match links")
            args = _build_oddsharvester_args(job)
            timeout_seconds = _job_oddsharvester_timeout(job)
            scraper_engine = (job.params or {}).get("scraper_engine") or "playwright"
            await append_scrape_job_log(
                db,
                job.id,
                action="engine_selected",
                message=f"Selected scraper engine: {scraper_engine}",
                metadata={"scraper_engine": scraper_engine},
            )
            await append_scrape_job_log(
                db,
                job.id,
                action="bridge_invocation",
                message="Invoking OddsHarvester bridge",
                metadata={"args": args, "timeout_seconds": timeout_seconds, "scraper_engine": scraper_engine},
            )
            payload = await run_oddsharvester_json(
                args,
                label=f"scrape_job_{job.id}",
                timeout=timeout_seconds,
            )
            ingestion_result = await _ingest_scraped_payload(db, job, payload)
            if isinstance(ingestion_result, tuple) and len(ingestion_result) == 3:
                summary, match_updates, odds_updates = ingestion_result
            else:
                summary = ingestion_result
                match_updates = {}
                odds_updates = {}
            job.status = "completed"
            job.output = json.dumps(summary)
            _schedule_post_commit_live_broadcasts(
                db,
                match_updates=match_updates,
                odds_updates=odds_updates,
            )
            await append_scrape_job_log(
                db,
                job.id,
                action="job_completed",
                message=f"Completed scrape job {job.id}",
                metadata=summary,
            )
        else:
            job.status = "completed"
            await append_scrape_job_log(
                db,
                job.id,
                action="job_completed",
                message=f"Completed scrape job {job.id} without scraper bridge",
                metadata={"job_type": job.job_type},
            )

        job.completed_at = datetime.now(timezone.utc)
    except BridgeError as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.now(timezone.utc)
        await append_scrape_job_log(
            db,
            job.id,
            action="job_failed",
            message=str(e),
            level="error",
            metadata={"error_type": e.__class__.__name__},
        )
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.now(timezone.utc)
        await append_scrape_job_log(
            db,
            job.id,
            action="job_failed",
            message=str(e),
            level="error",
            metadata={"error_type": e.__class__.__name__},
        )

    await db.flush()
    return job
