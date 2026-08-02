import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict
from urllib.parse import urlparse, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import event, inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.live import broadcast_match_update, broadcast_odds_update
from app.config import get_settings
from app.models.football_catalog import FootballLeagueCatalog
from app.models.job import ScheduledJobRun
from app.models.match import Match, MatchSource, OddsEntry
from app.models.odds_lineage import OddsSnapshot
from app.models.scrape import ScrapedDataset, ScrapeJob, ScrapeJobLog, ScraperRecipe, ScraperValidationCache
from app.services.python_bridge import (
    BridgeError,
    OddsHarvesterJsonResult,
    run_oddsharvester_json,
    validate_oddsharvester_football_catalog,
)

logger = logging.getLogger(__name__)

ODDS_SOURCE = "OddsHarvester"
settings = get_settings()
DEFAULT_INGESTION_BATCH_SIZE = 250
DEFAULT_MARKETS = ["1x2"]


class OddsIngestResult(TypedDict):
    written: int
    changed: int
    broadcast_payload: dict[str, Any] | None


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
LOCALE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
ANTI_BOT_MARKERS = ("anti-bot", "antibot", "captcha", "cloudflare", "challenge", "rate limit", "blocked")


def _pipeline_v2_enabled_for_job(job_id: int | None, *, percent: int | None = None) -> bool:
    configured_percent = getattr(settings, "scrape_pipeline_v2_percent", 0) if percent is None else percent
    try:
        if job_id is None:
            return False
        bucket_key = f"scrape-pipeline-v2:{int(job_id)}".encode()
        bucket = int.from_bytes(hashlib.sha256(bucket_key).digest()[:8], "big") % 100
        return bucket < int(configured_percent)
    except (TypeError, ValueError):
        return False


def _selected_scraper_engine(job: ScrapeJob, *, v2_percent: int | None = None) -> tuple[str, bool]:
    """Keep an explicit operator choice stable; canary jobs enter the auto cascade."""
    configured = (job.params or {}).get("scraper_engine")
    # `auto` is the normal UI default, not an opt-out: it only reaches the
    # hybrid cascade for the deterministic rollout cohort.
    if configured and str(configured) != "auto":
        return str(configured), False
    v2_active = _pipeline_v2_enabled_for_job(job.id, percent=v2_percent)
    return ("auto", True) if v2_active else ("playwright", False)


SUPPORTED_SCRAPE_JOB_TYPES = {"oddsportal", "scrape_odds", "refresh_results", "world_cup_pipeline"}
BRIDGE_SCRAPE_JOB_TYPES = {"oddsportal", "scrape_odds", "refresh_results"}
SUPPORTED_SCRAPE_COMMANDS = {"upcoming", "historic"}
UPCOMING_DEDUP_MAX_AGE = timedelta(minutes=10)
MAX_MATCH_LINKS = 100
MAX_LEAGUES = 50
MAX_HISTORIC_LEAGUES_PER_JOB = 5
MAX_UPCOMING_LEAGUES_PER_JOB = 10
MAX_MARKETS = 100
MAX_SCRAPE_PARAMS_BYTES = 64 * 1024
MAX_SCRAPE_PARAM_STRING_LENGTH = 2048
MAX_SCRAPE_PARAM_KEY_LENGTH = 100
MAX_SCRAPE_PARAM_COLLECTION_ITEMS = 100
MAX_SCRAPE_PARAM_DEPTH = 8
SUPPORTED_SCRAPER_ENGINES = {"playwright", "auto", "scrapling-http", "scrapling-stealth", "camoufox"}

SENSITIVE_ARG_FLAGS = {
    "--password",
    "--proxy-pass",
    "--proxy-user",
    "--proxy-url",
    "--token",
}


@dataclass(frozen=True)
class RuntimeCatalogResolution:
    env: dict[str, str]
    league_override: list[str] | None = None
    skipped_historic_leagues: list[str] | None = None


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
    # Server-generated/on-update columns can be expired by a flush. Reading an
    # expired ORM descriptor from AsyncSession code attempts implicit sync IO
    # and raises MissingGreenlet. Broadcasts are best-effort snapshots, so use
    # only values already loaded on the instance and never trigger a refresh.
    loaded = inspect(match).dict
    return {
        "id": loaded.get("id"),
        "external_id": loaded.get("external_id"),
        "sport": loaded.get("sport"),
        "competition": loaded.get("competition"),
        "home_team": loaded.get("home_team"),
        "away_team": loaded.get("away_team"),
        "home_score": loaded.get("home_score"),
        "away_score": loaded.get("away_score"),
        "status": loaded.get("status"),
        "match_date": _safe_iso(loaded.get("match_date")),
        "updated_at": _safe_iso(loaded.get("updated_at")),
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


def _scrape_output_summary(job: ScrapeJob) -> dict[str, Any]:
    output = getattr(job, "output", None)
    if not isinstance(output, str) or not output:
        return {}
    try:
        summary = json.loads(output)
    except (TypeError, ValueError):
        return {}
    return summary if isinstance(summary, dict) else {}


def _scrape_output_dataset_id(job: ScrapeJob) -> int | None:
    summary = _scrape_output_summary(job)
    dataset_id = _coerce_int(summary.get("dataset_id"))
    return dataset_id if dataset_id is not None and dataset_id > 0 else None


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
    target_params = job.params or {}
    command = target_params.get("command", "upcoming")
    explicit_historic_season = command == "historic" and bool(target_params.get("season"))
    now = datetime.now(timezone.utc)
    result = await db.execute(stmt)
    for candidate in result.scalars().all():
        if _scrape_dedup_key(candidate) != target_key:
            continue
        # A duplicate is never useful without a concrete persisted dataset.
        dataset_id = _scrape_output_dataset_id(candidate)
        if dataset_id is None or await db.get(ScrapedDataset, dataset_id) is None:
            continue
        if explicit_historic_season:
            return candidate
        # Upcoming data becomes stale quickly. Only reuse a recently-completed
        # candidate, and never let missing timestamps qualify it.
        completed_at = getattr(candidate, "completed_at", None)
        if not isinstance(completed_at, datetime):
            continue
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        if now - completed_at.astimezone(timezone.utc) <= UPCOMING_DEDUP_MAX_AGE:
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
    if league is not None and (not isinstance(league, str) or not league.strip() or len(league.strip()) > 255):
        raise ValueError("league must be a non-empty string of at most 255 characters")
    normalized_params = _normalize_scrape_params(job_type, params)
    job = ScrapeJob(
        job_type=job_type,
        status="pending",
        league=league.strip() if league is not None else None,
        params=normalized_params,
    )
    db.add(job)
    await db.flush()
    await append_scrape_job_log(
        db,
        job.id,
        action="job_created",
        message=f"Created scrape job {job.id}",
        metadata={"job_type": job_type, "league": league, "params": normalized_params},
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
            _coerce_float(
                bookmaker_market.get("Yes") or bookmaker_market.get("odds_yes") or bookmaker_market.get("btts_yes")
            ),
            None,
            _coerce_float(
                bookmaker_market.get("No") or bookmaker_market.get("odds_no") or bookmaker_market.get("btts_no")
            ),
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


def _validated_base_url(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("base_url must be a string")
    normalized = value.strip().rstrip("/")
    if len(normalized) > MAX_SCRAPE_PARAM_STRING_LENGTH:
        raise ValueError(f"base_url must be at most {MAX_SCRAPE_PARAM_STRING_LENGTH} characters")
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("base_url has an invalid port") from exc
    allowed_host = (
        hostname == "oddsportal.com" or hostname.endswith(".oddsportal.com") or hostname == "www.centroquote.it"
    )
    if (
        parsed.scheme != "https"
        or not hostname
        or not allowed_host
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "base_url must be an allowlisted HTTPS host-only URL without credentials, path, query, or fragment"
        )
    return normalized


def _validated_match_links(value: Any) -> list[str] | None:
    if value in (None, []):
        return None
    if not isinstance(value, list) or len(value) > MAX_MATCH_LINKS:
        raise ValueError(f"match_links must be a list of at most {MAX_MATCH_LINKS} URLs")
    normalized: list[str] = []
    for value_item in value:
        if not isinstance(value_item, str):
            raise ValueError("match_links must contain URLs")
        link = value_item.strip()
        if len(link) > MAX_SCRAPE_PARAM_STRING_LENGTH:
            raise ValueError(f"match_links URLs must be at most {MAX_SCRAPE_PARAM_STRING_LENGTH} characters")
        parsed = urlsplit(link)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("match_links contain an invalid port") from exc
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() != "www.oddsportal.com"
            or port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or not parsed.path.strip("/")
        ):
            raise ValueError("match_links must use HTTPS www.oddsportal.com URLs")
        normalized.append(link)
    return normalized


def _bounded_int(params: dict, key: str, *, minimum: int, maximum: int) -> int | None:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    parsed = _coerce_int(value)
    if parsed is None or not minimum <= parsed <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return parsed


def _bounded_float(params: dict, key: str, *, minimum: float, maximum: float) -> float | None:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number")
    parsed = _coerce_float(value)
    if parsed is None or not minimum <= parsed <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return parsed


def _validate_scrape_param_shape(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_SCRAPE_PARAM_DEPTH:
        raise ValueError(f"scrape params nesting must not exceed {MAX_SCRAPE_PARAM_DEPTH} levels")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value) > MAX_SCRAPE_PARAM_STRING_LENGTH:
            raise ValueError(f"scrape param strings must be at most {MAX_SCRAPE_PARAM_STRING_LENGTH} characters")
        return
    if isinstance(value, list):
        if len(value) > MAX_SCRAPE_PARAM_COLLECTION_ITEMS:
            raise ValueError(f"scrape param lists must contain at most {MAX_SCRAPE_PARAM_COLLECTION_ITEMS} items")
        for item in value:
            _validate_scrape_param_shape(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_SCRAPE_PARAM_COLLECTION_ITEMS:
            raise ValueError(f"scrape param objects must contain at most {MAX_SCRAPE_PARAM_COLLECTION_ITEMS} keys")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > MAX_SCRAPE_PARAM_KEY_LENGTH:
                raise ValueError(
                    f"scrape param keys must be non-empty strings of at most {MAX_SCRAPE_PARAM_KEY_LENGTH} characters"
                )
            _validate_scrape_param_shape(item, depth=depth + 1)
        return
    raise ValueError("scrape params may contain only JSON-compatible values")


def _enforce_scrape_params_size(params: dict) -> None:
    try:
        serialized_params = json.dumps(
            params,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("scrape params must be finite JSON-compatible values") from exc
    if len(serialized_params) > MAX_SCRAPE_PARAMS_BYTES:
        raise ValueError(f"scrape params must be at most {MAX_SCRAPE_PARAMS_BYTES} serialized bytes")


def _normalize_scrape_params(job_type: str, params: dict | None, *, now: datetime | None = None) -> dict:
    if job_type not in SUPPORTED_SCRAPE_JOB_TYPES:
        raise ValueError(f"Unsupported scrape job type: {job_type}")
    if params is not None and not isinstance(params, dict):
        raise ValueError("scrape params must be an object")
    _validate_scrape_param_shape(params or {})
    _enforce_scrape_params_size(params or {})

    normalized = dict(params or {})
    if job_type == "world_cup_pipeline":
        return normalized

    command = normalized.get("command", "upcoming")
    if not isinstance(command, str) or command not in SUPPORTED_SCRAPE_COMMANDS:
        raise ValueError("Unsupported scrape command")
    normalized["command"] = command
    sport = normalized.get("sport", "football")
    if not isinstance(sport, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", sport.strip()):
        raise ValueError("sport must be a 1-50 character slug")
    normalized["sport"] = sport.strip()

    for key, minimum, maximum in (
        ("concurrency", 1, 10),
        ("max_pages", 1, 100),
        ("timeout_seconds", 30, 3600),
        ("oddsharvester_timeout_seconds", 30, 3600),
        ("future_days", 1, 31),
    ):
        value = _bounded_int(normalized, key, minimum=minimum, maximum=maximum)
        if value is not None:
            normalized[key] = value
    request_delay = _bounded_float(normalized, "request_delay", minimum=0.0, maximum=60.0)
    if request_delay is not None:
        normalized["request_delay"] = request_delay

    for key, limit, item_limit in (
        ("countries", MAX_LEAGUES, 100),
        ("leagues", MAX_LEAGUES, 255),
        ("markets", MAX_MARKETS, 100),
    ):
        value = normalized.get(key)
        if value is not None:
            if (
                not isinstance(value, list)
                or len(value) > limit
                or any(
                    not isinstance(item, str) or not item.strip() or len(item.strip()) > item_limit for item in value
                )
            ):
                raise ValueError(
                    f"{key} must be a list of at most {limit} non-empty strings up to {item_limit} characters"
                )
            normalized[key] = [item.strip() for item in value]

    leagues = normalized.get("leagues") or []
    league_limit = MAX_HISTORIC_LEAGUES_PER_JOB if command == "historic" else MAX_UPCOMING_LEAGUES_PER_JOB
    if len(leagues) > league_limit:
        raise ValueError(
            f"{command} scrape jobs support at most {league_limit} leagues; split broader selections into bounded jobs"
        )

    scraper_engine = normalized.get("scraper_engine")
    if scraper_engine is not None:
        if not isinstance(scraper_engine, str) or scraper_engine not in SUPPORTED_SCRAPER_ENGINES:
            raise ValueError("scraper_engine is unsupported")

    season = normalized.get("season")
    if season is not None and (
        isinstance(season, bool)
        or not isinstance(season, (str, int))
        or not str(season).strip()
        or len(str(season).strip()) > 20
    ):
        raise ValueError("season must be a string or integer of at most 20 characters")

    match_links = _validated_match_links(normalized.get("match_links"))
    if match_links is not None:
        normalized["match_links"] = match_links
    base_url = _validated_base_url(normalized.get("base_url"))
    if base_url is not None:
        normalized["base_url"] = base_url
    locale = _validated_locale(normalized.get("locale"))
    if locale is not None:
        normalized["locale"] = locale
    browser_timezone = _validated_timezone(normalized.get("timezone"))
    if browser_timezone is not None:
        normalized["timezone"] = browser_timezone

    date = normalized.get("date")
    if date is not None:
        if not isinstance(date, str) or not re.fullmatch(r"\d{8}", date):
            raise ValueError("date must use YYYYMMDD format")
        try:
            normalized["date"] = datetime.strptime(date, "%Y%m%d").strftime("%Y%m%d")
        except ValueError as exc:
            raise ValueError("date must be a valid calendar date in YYYYMMDD format") from exc
    if command == "upcoming" and date is None and not match_links:
        future_days = normalized.get("future_days", 1)
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        target_timezone = ZoneInfo(browser_timezone or "UTC")
        target = reference.astimezone(target_timezone) + timedelta(days=future_days)
        normalized["date"] = target.strftime("%Y%m%d")
    _enforce_scrape_params_size(normalized)
    return normalized


def _validated_locale(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not LOCALE_PATTERN.fullmatch(value.strip()):
        raise ValueError("locale must be a valid language tag such as en-GB")
    return value.strip()


def _validated_timezone(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("timezone must be an IANA timezone name")
    normalized = value.strip()
    try:
        ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone name") from exc
    return normalized


def _redact_sensitive_args(args: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for arg in args:
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
            continue
        flag, separator, _value = arg.partition("=")
        if separator and flag.lower() in SENSITIVE_ARG_FLAGS:
            redacted.append(f"{flag}=[REDACTED]")
            continue
        redacted.append(arg)
        redact_next = arg.lower() in SENSITIVE_ARG_FLAGS
    return redacted


def _build_oddsharvester_args(
    job: ScrapeJob, *, league_override: list[str] | None = None, scraper_engine: str | None = None
) -> list[str]:
    params = job.params or {}
    command = params.get("command", "upcoming")
    sport = str(params.get("sport", "football"))
    markets = params.get("markets")
    leagues = league_override if league_override is not None else params.get("leagues")
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

    effective_engine = scraper_engine or params.get("scraper_engine")
    if effective_engine:
        args.extend(["--engine", str(effective_engine)])

    base_url = _validated_base_url(params.get("base_url"))
    locale = _validated_locale(params.get("locale"))
    browser_timezone = _validated_timezone(params.get("timezone"))
    if base_url:
        args.extend(["--base-url", base_url])
    if locale:
        args.extend(["--locale", locale])
    if browser_timezone:
        args.extend(["--timezone", browser_timezone])

    return args


def _job_oddsharvester_timeout(job: ScrapeJob) -> int | None:
    params = job.params or {}
    return _coerce_int(params.get("timeout_seconds") or params.get("oddsharvester_timeout_seconds"))


def _effective_oddsharvester_timeout(job: ScrapeJob, league_count: int) -> int | None:
    configured = _job_oddsharvester_timeout(job)
    command = str((job.params or {}).get("command", "upcoming"))
    if command != "historic" and league_count <= 1:
        return configured
    # Multi-league jobs launch a browser across every selected competition.
    # Historic runs also paginate Results pages, so they need a larger
    # per-league allowance. Keep both paths bounded by the validated maximum.
    seconds_per_league = 300 if command == "historic" else 90
    adaptive = min(3600, 600 + max(1, league_count) * seconds_per_league)
    return max(configured or 0, adaptive)


def _scrape_report_summary(report: dict, records: list[dict], *, cli_error: str | None = None) -> dict[str, Any]:
    schema_version = report.get("schema_version")
    if schema_version not in {"1.0", "1.1"}:
        raise BridgeError("Unsupported OddsHarvester scrape report schema_version")

    scraper_status = report.get("status")
    if scraper_status not in {"success", "partial", "failed"}:
        raise BridgeError("OddsHarvester scrape report has an invalid status")

    stats = report.get("stats")
    failures = report.get("failures")
    warnings = report.get("warnings")
    engines = report.get("engines")
    source = report.get("source")
    timing = report.get("timing")
    if not isinstance(stats, dict) or not isinstance(failures, list) or not isinstance(warnings, list):
        raise BridgeError("OddsHarvester scrape report is missing stats, failures, or warnings")
    if not isinstance(engines, dict) or not isinstance(source, dict) or not isinstance(timing, dict):
        raise BridgeError("OddsHarvester scrape report is missing engines, source, or timing")

    failure_types = sorted(
        {str(item.get("error_type")) for item in failures if isinstance(item, dict) and item.get("error_type")}
    )
    diagnostic_text = json.dumps({"failures": failures, "warnings": warnings}, default=str).lower()
    anti_bot_detected = any(marker in diagnostic_text for marker in ANTI_BOT_MARKERS)
    failure_count = max(_coerce_int(stats.get("failed")) or 0, len(failures))
    partial_count = _coerce_int(stats.get("partial")) or 0

    source_command = source.get("command") or report.get("command")
    legacy_empty_upcoming = (
        source_command == "upcoming"
        and not records
        and not failure_count
        and not partial_count
        and not anti_bot_detected
        and (stats.get("total_urls") or 0) == 0
        and cli_error is not None
    )
    # v1.1 must explicitly attest the benign outcome; otherwise a missing
    # output is indistinguishable from a bridge/parser failure.
    if schema_version == "1.1" and report.get("outcome") == "no_fixtures":
        no_fixtures_invariants = (
            source_command == "upcoming"
            and scraper_status == "success"
            and not records
            and (_coerce_int(stats.get("total_urls")) or 0) == 0
            and (_coerce_int(stats.get("successful")) or 0) == 0
            and failure_count == 0
            and partial_count == 0
            and not anti_bot_detected
            and cli_error is None
        )
        if not no_fixtures_invariants:
            raise BridgeError("OddsHarvester scrape report has inconsistent no_fixtures attestation")
        empty_upcoming = True
    else:
        empty_upcoming = legacy_empty_upcoming if schema_version == "1.0" else False

    if empty_upcoming:
        # OddsHarvester exits non-zero when a date has no match links. That is
        # a valid, auditable outcome for a targeted upcoming-day scrape, not a
        # bridge outage or anti-bot failure.
        health = "no_fixtures"
    elif scraper_status == "failed" or (not records and (failure_count or anti_bot_detected or cli_error)):
        health = "failed"
    elif scraper_status == "partial" or failure_count or partial_count:
        health = "degraded"
    else:
        health = "healthy"

    safe_source = {
        key: value
        for key, value in source.items()
        if key in {"sport", "date", "leagues", "markets", "season", "max_pages", "include_started", "base_url"}
    }
    match_links = source.get("match_links")
    if isinstance(match_links, list):
        safe_source["match_link_count"] = len(match_links)

    summary = {
        "schema_version": schema_version,
        "health": health,
        "scraper_status": scraper_status,
        "records": len(records),
        "stats": {
            "total_urls": _coerce_int(stats.get("total_urls")) or 0,
            "successful": _coerce_int(stats.get("successful")) or 0,
            "failed": failure_count,
            "partial": partial_count,
            "success_rate_pct": _coerce_float(stats.get("success_rate_pct")) or 0.0,
        },
        "failure_count": failure_count,
        "failure_types": failure_types,
        "warning_count": len(warnings),
        "anti_bot_detected": anti_bot_detected,
        "engines": {
            "requested": engines.get("requested"),
            "used": engines.get("used") if isinstance(engines.get("used"), list) else [],
        },
        "source": safe_source,
        "locale": report.get("locale"),
        "timezone": report.get("timezone"),
        "timing": {
            "started_at": timing.get("started_at"),
            "finished_at": timing.get("finished_at"),
            "duration_seconds": _coerce_float(timing.get("duration_seconds")) or 0.0,
        },
        "cli_error": bool(cli_error),
        "no_fixtures": empty_upcoming,
    }

    if schema_version == "1.1":
        known_fields = {
            "schema_version",
            "status",
            "stats",
            "failures",
            "warnings",
            "engines",
            "source",
            "timing",
            "locale",
            "timezone",
            "command",
            "outcome",
        }
        additive_metadata = {key: value for key, value in report.items() if key not in known_fields}
        if additive_metadata:
            summary["metadata"] = additive_metadata
        # v1.1 has additive telemetry both at the top level and inside the
        # engines object; preserve stable categories without dropping future keys.
        expected_types = {
            "attempts": list,
            "fallbacks": list,
            "cache": dict,
            "recipe": dict,
            "repair": dict,
        }
        for key, expected_type in expected_types.items():
            value = additive_metadata.get(key, engines.get(key))
            if value is not None:
                if not isinstance(value, expected_type):
                    raise BridgeError(f"OddsHarvester scrape report has invalid {key} telemetry")
                summary[key] = value
                if key in engines:
                    summary["engines"][key] = value

    return summary


async def _persist_scrape_report_artifact(db: AsyncSession, scrape_job_id: int, report_summary: dict[str, Any]) -> None:
    result = await db.execute(select(ScheduledJobRun).where(ScheduledJobRun.scrape_job_id == scrape_job_id))
    for run in result.scalars().all():
        artifacts = dict(run.artifacts or {})
        artifacts["scrape_report"] = report_summary
        run.artifacts = artifacts


async def _run_oddsharvester_with_report(
    args: list[str], *, label: str, timeout: int | None, extra_env: dict[str, str] | None = None
) -> list[dict] | OddsHarvesterJsonResult:
    """Run once with the report and rollout environment; never silently downgrade."""
    kwargs: dict[str, Any] = {"label": label, "timeout": timeout, "include_report": True}
    if extra_env:
        kwargs["extra_env"] = extra_env
    return await run_oddsharvester_json(args, **kwargs)


def _requested_scrape_league_slugs(job: ScrapeJob) -> set[str]:
    params = job.params or {}
    raw_leagues = params.get("leagues")
    if isinstance(raw_leagues, list):
        return {str(slug) for slug in raw_leagues if slug}
    if isinstance(raw_leagues, str):
        return {slug.strip() for slug in raw_leagues.split(",") if slug.strip()}
    return {job.league} if job.league else set()


VALIDATION_CACHE_TTL = timedelta(hours=24)


SENSITIVE_RECIPE_KEYS = {"cookie", "cookies", "authorization", "token", "password", "proxy", "secret"}
MAX_RECIPE_BYTES = 32 * 1024
MAX_RECIPE_DEPTH = 8
MAX_RECIPE_ITEMS = 500


def sanitize_scraper_recipe(value: Any) -> dict[str, Any]:
    """Validate a persistable recipe: no browser state, bounded request metadata."""
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("scraper recipe must be bounded JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_RECIPE_BYTES:
        raise ValueError(f"scraper recipe must be at most {MAX_RECIPE_BYTES} bytes")
    if _recipe_item_count(value) > MAX_RECIPE_ITEMS:
        raise ValueError(f"scraper recipe must contain at most {MAX_RECIPE_ITEMS} items")
    cleaned = _sanitize_recipe_value(value)
    if not isinstance(cleaned, dict):
        raise ValueError("scraper recipe must be an object")
    endpoint = cleaned.get("endpoint")
    if endpoint is not None:
        cleaned["endpoint"] = _validate_recipe_endpoint(endpoint)
    method = cleaned.get("method", "GET")
    if not isinstance(method, str) or method.upper() not in {"GET", "POST"}:
        raise ValueError("scraper recipe method must be GET or POST")
    headers = cleaned.get("headers", {})
    cleaned["headers"] = _validate_recipe_headers(headers)
    body = cleaned.get("body")
    if body is not None and len(json.dumps(body, separators=(",", ":"))) > 8192:
        raise ValueError("scraper recipe body must be at most 8192 bytes")
    return cleaned


def _validate_recipe_headers(value: Any) -> dict[str, str]:
    """Persist only deterministic, non-secret content negotiation headers."""
    if not isinstance(value, dict) or len(value) > 3:
        raise ValueError("scraper recipe headers must contain only safe allowlisted values")
    safe: dict[str, str] = {}
    for key, header_value in value.items():
        normalized = str(key).strip().lower()
        if normalized not in {"accept", "accept-language", "content-type"}:
            raise ValueError("scraper recipe headers must contain only safe allowlisted values")
        if not isinstance(header_value, str) or not header_value.strip() or len(header_value) > 256:
            raise ValueError("scraper recipe headers must contain only safe allowlisted values")
        value_normalized = header_value.strip().lower()
        if normalized == "content-type" and value_normalized not in {
            "application/json",
            "application/json; charset=utf-8",
        }:
            raise ValueError("scraper recipe headers must contain only safe allowlisted values")
        if any(marker in value_normalized for marker in ("bearer", "token", "key=", "secret", "session")):
            raise ValueError("scraper recipe headers must contain only safe allowlisted values")
        safe[normalized] = header_value.strip()
    return safe


def _recipe_item_count(value: Any, *, depth: int = 0) -> int:
    if depth > MAX_RECIPE_DEPTH:
        raise ValueError(f"scraper recipe nesting must not exceed {MAX_RECIPE_DEPTH}")
    if isinstance(value, dict):
        return len(value) + sum(_recipe_item_count(item, depth=depth + 1) for item in value.values())
    if isinstance(value, list):
        return len(value) + sum(_recipe_item_count(item, depth=depth + 1) for item in value)
    return 1


def _sanitize_recipe_value(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if any(marker in normalized_key for marker in SENSITIVE_RECIPE_KEYS):
                raise ValueError("scraper recipes must not contain cookies, credentials, tokens, or proxy secrets")
            cleaned[str(key)] = _sanitize_recipe_value(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_recipe_value(item) for item in value]
    if isinstance(value, str):
        if len(value) > 8192 or any(marker in value.lower() for marker in ("bearer ", "session=", "password=")):
            raise ValueError("scraper recipes must not contain secret values")
        return value
    if value is None or isinstance(value, (int, float, bool)):
        return value
    raise ValueError("scraper recipes must be JSON-compatible")


def _validate_recipe_endpoint(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("scraper recipe endpoint is invalid")
    parsed = urlsplit(value)
    if (
        value.startswith("/")
        and not value.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
        and not parsed.query
        and not parsed.fragment
    ):
        return parsed.path
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("scraper recipe endpoint has an invalid port") from exc
    hostname = parsed.hostname.lower() if parsed.hostname else None
    if (
        parsed.scheme == "https"
        and hostname
        and (hostname == "oddsportal.com" or hostname.endswith(".oddsportal.com"))
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
        and not parsed.query
        and not parsed.fragment
    ):
        return urlunsplit(("https", hostname, parsed.path or "/", "", ""))
    raise ValueError("scraper recipe endpoint must be relative or HTTPS OddsPortal")


async def create_scraper_recipe(
    db: AsyncSession, *, recipe_key: str, engine: str, recipe: dict[str, Any], schema_version: str = "1.0"
) -> ScraperRecipe:
    sanitized = sanitize_scraper_recipe(recipe)
    entry = ScraperRecipe(
        recipe_key=recipe_key, engine=engine, schema_version=schema_version, status="candidate", recipe=sanitized
    )
    db.add(entry)
    await db.flush()
    return entry


async def approve_scraper_recipe(
    db: AsyncSession,
    recipe: ScraperRecipe,
    *,
    approved_by: str,
    verified_at: datetime,
) -> ScraperRecipe:
    if recipe.status != "candidate":
        raise ValueError("only candidate scraper recipes can be approved")
    if not approved_by.strip():
        raise ValueError("scraper recipe approval requires an operator")
    now = datetime.now(timezone.utc)
    active_result = await db.execute(
        select(ScraperRecipe)
        .where(ScraperRecipe.recipe_key == recipe.recipe_key, ScraperRecipe.status == "active")
        .with_for_update()
    )
    for active_recipe in active_result.scalars().all():
        if active_recipe.id != recipe.id:
            active_recipe.status = "disabled"
            active_recipe.retired_at = now
    recipe.status = "active"
    recipe.verified_at = verified_at
    recipe.approved_by = approved_by.strip()
    recipe.approved_at = now
    recipe.retired_at = None
    await db.flush()
    return recipe


async def retire_scraper_recipe(db: AsyncSession, recipe: ScraperRecipe) -> ScraperRecipe:
    if recipe.status != "active":
        raise ValueError("only active scraper recipes can be retired")
    recipe.status = "disabled"
    recipe.retired_at = datetime.now(timezone.utc)
    await db.flush()
    return recipe


def _validation_cache_is_fresh(entry: ScraperValidationCache, now: datetime) -> bool:
    expires_at = entry.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now


async def _persist_validation_cache(
    db: AsyncSession,
    *,
    scrape_slug: str,
    season: str,
    status: str,
    historic_url: str | None,
    validated_at: datetime,
    expires_at: datetime,
) -> None:
    get_bind = getattr(db, "get_bind", None)
    bind = get_bind() if callable(get_bind) else None
    if getattr(getattr(bind, "dialect", None), "name", None) == "postgresql":
        statement = pg_insert(ScraperValidationCache).values(
            scrape_slug=scrape_slug,
            season=season,
            status=status,
            historic_url=historic_url,
            validated_at=validated_at,
            expires_at=expires_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ScraperValidationCache.scrape_slug, ScraperValidationCache.season],
            set_={
                "status": statement.excluded.status,
                "historic_url": statement.excluded.historic_url,
                "validated_at": statement.excluded.validated_at,
                "expires_at": statement.excluded.expires_at,
            },
        )
        await db.execute(statement)
        return
    add = getattr(db, "add", None)
    if callable(add):
        add(
            ScraperValidationCache(
                scrape_slug=scrape_slug,
                season=season,
                status=status,
                historic_url=historic_url,
                validated_at=validated_at,
                expires_at=expires_at,
            )
        )


async def _runtime_catalog_league_env(db: AsyncSession, job: ScrapeJob) -> RuntimeCatalogResolution:
    """Inject validated football catalog URLs and reuse fresh historic Results-page checks.

    The cache contains only slug/season/status/URL timestamps. Browser cookies, headers,
    and credentials remain process-local and are deliberately never persisted.
    """
    params = job.params or {}
    if str(params.get("sport", "football")) != "football":
        return RuntimeCatalogResolution({})
    slugs = _requested_scrape_league_slugs(job)
    if not slugs:
        return RuntimeCatalogResolution({})
    result = await db.execute(
        select(FootballLeagueCatalog).where(
            FootballLeagueCatalog.scrape_slug.in_(slugs),
            FootballLeagueCatalog.status == "available",
        )
    )
    rows = [row for row in result.scalars().all() if isinstance(row, FootballLeagueCatalog)]
    mapping = {row.scrape_slug: row.source_url for row in rows}
    if not mapping:
        return RuntimeCatalogResolution({})

    env = {"ODDSHARVESTER_RUNTIME_FOOTBALL_LEAGUES": json.dumps(mapping)}
    if str(params.get("command", "upcoming")) != "historic":
        return RuntimeCatalogResolution(env)

    season = str(params.get("season") or "").strip()
    if not season:
        raise ValueError("Historic scraping requires a season for runtime-validated leagues")
    now = datetime.now(timezone.utc)
    cached_result = await db.execute(
        select(ScraperValidationCache).where(
            ScraperValidationCache.scrape_slug.in_(mapping),
            ScraperValidationCache.season == season,
        )
    )
    cache_rows = {
        row.scrape_slug: row for row in cached_result.scalars().all() if isinstance(row, ScraperValidationCache)
    }
    cached = {slug: row for slug, row in cache_rows.items() if _validation_cache_is_fresh(row, now)}
    missing = {slug: url for slug, url in mapping.items() if slug not in cached}
    validated_results: dict[str, dict[str, Any]] = {
        slug: {"scrape_slug": slug, "status": row.status, "historic_url": row.historic_url}
        for slug, row in cached.items()
    }
    if missing:
        results = await validate_oddsharvester_football_catalog(
            [{"scrape_slug": slug, "source_url": url} for slug, url in missing.items()],
            timeout=_effective_oddsharvester_timeout(job, len(missing)),
            season=season,
        )
        by_slug = {str(item.get("scrape_slug")): item for item in results if isinstance(item, dict)}
        for slug in missing:
            result_item = by_slug.get(slug, {"scrape_slug": slug, "status": "unavailable"})
            status = str(result_item.get("status") or "unavailable")
            historic_url = result_item.get("historic_url") if status == "available" else None
            cache_entry = cache_rows.get(slug)
            if cache_entry is None:
                normalized_historic_url = str(historic_url) if isinstance(historic_url, str) and historic_url else None
                await _persist_validation_cache(
                    db,
                    scrape_slug=slug,
                    season=season,
                    status=status,
                    historic_url=normalized_historic_url,
                    validated_at=now,
                    expires_at=now + VALIDATION_CACHE_TTL,
                )
                cache_entry = ScraperValidationCache(
                    scrape_slug=slug,
                    season=season,
                    status=status,
                    historic_url=normalized_historic_url,
                    validated_at=now,
                    expires_at=now + VALIDATION_CACHE_TTL,
                )
            cache_entry.status = status
            cache_entry.historic_url = str(historic_url) if isinstance(historic_url, str) and historic_url else None
            cache_entry.validated_at = now
            cache_entry.expires_at = now + VALIDATION_CACHE_TTL
            validated_results[slug] = {
                "scrape_slug": slug,
                "status": status,
                "historic_url": cache_entry.historic_url,
            }

    unavailable = sorted(slug for slug in mapping if validated_results.get(slug, {}).get("status") != "available")
    validated_dynamic_slugs = sorted(set(mapping) - set(unavailable))
    passthrough_slugs = sorted(slugs - set(mapping))
    validated_slugs = [*passthrough_slugs, *validated_dynamic_slugs]
    if not validated_slugs:
        raise ValueError("No selected league passed historic Results-page validation")
    mapping = {slug: mapping[slug] for slug in validated_dynamic_slugs}
    env["ODDSHARVESTER_RUNTIME_FOOTBALL_LEAGUES"] = json.dumps(mapping)
    historic_urls = {
        slug: {season: historic_url}
        for slug, result_item in validated_results.items()
        if slug in validated_dynamic_slugs
        and isinstance(historic_url := result_item.get("historic_url"), str)
        and historic_url
    }
    if len(historic_urls) != len(validated_dynamic_slugs):
        missing_urls = sorted(set(validated_dynamic_slugs) - set(historic_urls))
        raise ValueError("Historic validator returned no exact Results URL for: " + ", ".join(missing_urls))
    env["ODDSHARVESTER_RUNTIME_FOOTBALL_HISTORIC_URLS"] = json.dumps(historic_urls)
    return RuntimeCatalogResolution(
        env,
        league_override=validated_slugs,
        skipped_historic_leagues=unavailable,
    )


def _chunked(iterable: list[Any], size: int):
    for offset in range(0, len(iterable), size):
        yield iterable[offset : offset + size]


async def _preload_match_context(
    db: AsyncSession,
    records: list[dict],
) -> tuple[dict[str, Match], dict[str, Match], dict[int, MatchSource | None]]:
    match_links: set[str] = set()
    source_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        link = record.get("match_link")
        if isinstance(link, str):
            link = link.strip()
            if link:
                match_links.add(link)
        source_id = _extract_source_id(record.get("match_link"))
        if source_id:
            source_ids.add(source_id)

    source_map: dict[str, Match] = {}
    external_map: dict[str, Match] = {}
    if match_links:
        source_rows = await db.execute(
            select(MatchSource, Match)
            .join(Match, Match.id == MatchSource.match_id)
            .where(MatchSource.source == ODDS_SOURCE, MatchSource.url.in_(sorted(match_links)))
        )
        for source, match in source_rows.all():
            if source.url:
                source_map[source.url] = match

    if source_ids:
        external_rows = await db.execute(select(Match).where(Match.external_id.in_(sorted(source_ids))))
        for match in external_rows.scalars().all():
            if match.external_id:
                external_map[match.external_id] = match

    match_ids = {match.id for match in source_map.values()} | {match.id for match in external_map.values()}
    source_by_match: dict[int, MatchSource | None] = {}
    if match_ids:
        rows = await db.execute(
            select(MatchSource).where(MatchSource.source == ODDS_SOURCE, MatchSource.match_id.in_(sorted(match_ids)))
        )
        source_by_match = {source.match_id: source for source in rows.scalars().all()}
    return source_map, external_map, source_by_match


def _iter_record_odds(
    record: dict, match: Match | None
) -> list[tuple[int, str, str, datetime, float | None, float | None, float | None]]:
    if match is None or match.id is None:
        return []
    scrape_timestamp = _coerce_datetime(record.get("scraped_date")) or datetime.now(timezone.utc)
    rows: list[tuple[int, str, str, datetime, float | None, float | None, float | None]] = []
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
            rows.append((match.id, bookmaker, market_name, scrape_timestamp, home_odds, draw_odds, away_odds))
    return rows


def _snapshot_source_key(
    match_id: int,
    observed_at: datetime,
    *,
    dataset_id: int | None,
    scrape_job_id: int | None,
) -> str:
    if scrape_job_id is not None:
        scope = f"job:{scrape_job_id}"
    elif dataset_id is not None:
        scope = f"dataset:{dataset_id}"
    else:
        scope = "legacy"
    return f"{scope}:match:{match_id}:observed:{observed_at.isoformat()}"


async def _preload_odds_context(
    db: AsyncSession,
    odds_rows: list[tuple[int, str, str, datetime, float | None, float | None, float | None]],
    *,
    dataset_id: int | None,
    scrape_job_id: int | None,
) -> tuple[dict[tuple[str, str, str, datetime], OddsEntry], dict[str, OddsSnapshot]]:
    existing_odds: dict[tuple[str, str, str, datetime], OddsEntry] = {}
    existing_snapshots: dict[str, OddsSnapshot] = {}

    if odds_rows:
        snapshot_keys = list(
            {
                _snapshot_source_key(
                    match_id,
                    timestamp,
                    dataset_id=dataset_id,
                    scrape_job_id=scrape_job_id,
                )
                for match_id, _, _, timestamp, *_ in odds_rows
            }
        )
        for key_chunk in _chunked(snapshot_keys, DEFAULT_INGESTION_BATCH_SIZE):
            snapshot_result = await db.execute(
                select(OddsSnapshot).where(OddsSnapshot.source == ODDS_SOURCE, OddsSnapshot.source_key.in_(key_chunk))
            )
            existing_snapshots.update({snapshot.source_key: snapshot for snapshot in snapshot_result.scalars().all()})

        snapshots_by_id = {snapshot.id: snapshot for snapshot in existing_snapshots.values() if snapshot.id is not None}
        for id_chunk in _chunked(list(snapshots_by_id), DEFAULT_INGESTION_BATCH_SIZE):
            odds_result = await db.execute(select(OddsEntry).where(OddsEntry.odds_snapshot_id.in_(id_chunk)))
            for entry in odds_result.scalars().all():
                snapshot = snapshots_by_id.get(entry.odds_snapshot_id)
                if snapshot is not None and entry.timestamp is not None:
                    existing_odds[(snapshot.source_key, entry.bookmaker, entry.market, entry.timestamp)] = entry

    return existing_odds, existing_snapshots


async def _ingest_record_odds(
    db: AsyncSession,
    *,
    record: dict,
    match: Match,
    dataset_id: int | None,
    scrape_job_id: int | None,
    existing_odds: dict[tuple[str, str, str, datetime], OddsEntry],
    existing_snapshots: dict[str, OddsSnapshot],
) -> OddsIngestResult:
    written = 0
    changed = 0
    broadcast_payload: dict[str, Any] | None = None

    for match_id, bookmaker, market_name, scrape_timestamp, home_odds, draw_odds, away_odds in _iter_record_odds(
        record, match
    ):
        source_key = _snapshot_source_key(
            match_id,
            scrape_timestamp,
            dataset_id=dataset_id,
            scrape_job_id=scrape_job_id,
        )
        snapshot = existing_snapshots.get(source_key)
        if snapshot is None:
            snapshot = OddsSnapshot(
                match_id=match.id,
                source=ODDS_SOURCE,
                source_key=source_key,
                dataset_id=dataset_id,
                scrape_job_id=scrape_job_id,
                observed_at=scrape_timestamp,
                quality="complete",
                metadata_json={"match_link": record.get("match_link")},
            )
            db.add(snapshot)
            existing_snapshots[source_key] = snapshot

        odds_key = (source_key, bookmaker, market_name, scrape_timestamp)
        existing = existing_odds.get(odds_key)
        if existing is None:
            entry = OddsEntry(
                match_id=match.id,
                odds_snapshot_id=snapshot.id,
                odds_snapshot=snapshot,
                bookmaker=bookmaker,
                market=market_name,
                home_odds=home_odds,
                draw_odds=draw_odds,
                away_odds=away_odds,
                timestamp=scrape_timestamp,
            )
            db.add(entry)
            existing_odds[odds_key] = entry
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
            entry_changed = existing.odds_snapshot_id != snapshot.id or any(
                (
                    existing.home_odds != home_odds,
                    existing.draw_odds != draw_odds,
                    existing.away_odds != away_odds,
                    existing.timestamp != scrape_timestamp,
                )
            )
            existing.odds_snapshot = snapshot
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

    return {
        "written": written,
        "changed": changed,
        "broadcast_payload": broadcast_payload,
    }


async def _ingest_match_odds(
    db: AsyncSession,
    match: Match,
    record: dict,
    *,
    dataset_id: int | None = None,
    scrape_job_id: int | None = None,
) -> OddsIngestResult:
    """Compatibility entrypoint for single-record callers.

    Batched ingestion uses the preloaded helper below; this keeps the prior
    public-internal helper semantics (including snapshot lineage) for focused
    callers and regression tests.
    """
    rows = _iter_record_odds(record, match)
    if not rows:
        return {"written": 0, "changed": 0, "broadcast_payload": None}
    timestamp = rows[0][3]
    source_key = _snapshot_source_key(
        match.id,
        timestamp,
        dataset_id=dataset_id,
        scrape_job_id=scrape_job_id,
    )
    snapshot_result = await db.execute(
        select(OddsSnapshot).where(OddsSnapshot.source == ODDS_SOURCE, OddsSnapshot.source_key == source_key)
    )
    snapshot = snapshot_result.scalar_one_or_none()
    if snapshot is None:
        snapshot = OddsSnapshot(
            match_id=match.id,
            source=ODDS_SOURCE,
            source_key=source_key,
            dataset_id=dataset_id,
            scrape_job_id=scrape_job_id,
            observed_at=timestamp,
            quality="complete",
            metadata_json={"match_link": record.get("match_link")},
        )
        db.add(snapshot)
        await db.flush()
    existing_odds: dict[tuple[str, str, str, datetime], OddsEntry] = {}
    existing_snapshots = {source_key: snapshot}
    return await _ingest_record_odds(
        db,
        record=record,
        match=match,
        dataset_id=dataset_id,
        scrape_job_id=scrape_job_id,
        existing_odds=existing_odds,
        existing_snapshots=existing_snapshots,
    )


async def _upsert_match_from_record(
    db: AsyncSession,
    record: dict,
    sport: str,
    *,
    source_by_url: dict[str, Match],
    external_by_source_id: dict[str, Match],
    source_by_match_id: dict[int, MatchSource | None],
) -> tuple[Match, bool, bool]:
    match_link = record.get("match_link")
    if isinstance(match_link, str) and match_link.strip() in source_by_url:
        match = source_by_url[match_link.strip()]
    else:
        match = None

    source_id = _extract_source_id(match_link)
    if match is None and source_id and source_id in external_by_source_id:
        match = external_by_source_id[source_id]

    match_date = _coerce_datetime(record.get("match_date"))

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
        # Populate match caches so follow-up records in the same chunk reuse it.
        if source_id:
            external_by_source_id[source_id] = match
        if match_link and isinstance(match_link, str):
            source_by_url[match_link.strip()] = match

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

    existing_source = source_by_match_id.get(match.id)
    if existing_source is None:
        existing_source = MatchSource(
            match_id=match.id,
            source=ODDS_SOURCE,
            source_id=source_id,
            url=match_link,
        )
        source_by_match_id[match.id] = existing_source
        db.add(existing_source)
    else:
        existing_source.source_id = source_id or existing_source.source_id
        if match_link:
            existing_source.url = str(match_link)

    if match_link and isinstance(match_link, str):
        source_by_url[match_link.strip()] = match
    if source_id:
        external_by_source_id[source_id] = match

    await db.flush()
    current_snapshot = _match_broadcast_snapshot(match)
    return match, previous_snapshot != current_snapshot, final_score_conflict


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

    valid_records: list[dict] = [record for record in payload if isinstance(record, dict)]
    skipped_records = len(payload) - len(valid_records)

    for chunk in _chunked(valid_records, DEFAULT_INGESTION_BATCH_SIZE):
        source_by_url, external_by_source_id, source_by_match_id = await _preload_match_context(db, chunk)

        prepared: list[tuple[dict, Match, bool]] = []
        for record in chunk:
            match, match_changed, final_score_conflict = await _upsert_match_from_record(
                db,
                record,
                sport,
                source_by_url=source_by_url,
                external_by_source_id=external_by_source_id,
                source_by_match_id=source_by_match_id,
            )
            prepared.append((record, match, match_changed))
            matches_written += 1
            if final_score_conflict:
                final_score_conflicts += 1
                await append_scrape_job_log(
                    db,
                    job.id,
                    action="final_score_conflict",
                    level="warning",
                    message=(
                        f"Retained persisted final score for match {match.id}; refresh reported a conflicting score"
                    ),
                    metadata={
                        "match_id": match.id,
                        "persisted_score": {"home": match.home_score, "away": match.away_score},
                        "incoming_score": {
                            "home": _coerce_int(record.get("home_score")),
                            "away": _coerce_int(record.get("away_score")),
                        },
                    },
                )

            if _is_live_relevant_match(match) and match_changed:
                match_updates[match.id] = _build_match_update_payload(match)

        chunk_odds_rows: list[tuple[int, str, str, datetime, float | None, float | None, float | None]] = []
        for record, match, _ in prepared:
            chunk_odds_rows.extend(_iter_record_odds(record, match))
        existing_odds, existing_snapshots = await _preload_odds_context(
            db,
            chunk_odds_rows,
            dataset_id=dataset.id,
            scrape_job_id=job.id,
        )

        for record, match, _ in prepared:
            if not _is_live_relevant_match(match):
                continue
            odds_result = await _ingest_record_odds(
                db,
                record=record,
                match=match,
                dataset_id=dataset.id,
                scrape_job_id=job.id,
                existing_odds=existing_odds,
                existing_snapshots=existing_snapshots,
            )
            odds_written += int(odds_result["written"])
            odds_payload = odds_result.get("broadcast_payload")
            if odds_payload:
                odds_updates[match.id] = odds_payload

        # For non-live matches we still need to persist odds and snapshot lineage.
        for record, match, _ in prepared:
            if _is_live_relevant_match(match):
                continue
            odds_result = await _ingest_record_odds(
                db,
                record=record,
                match=match,
                dataset_id=dataset.id,
                scrape_job_id=job.id,
                existing_odds=existing_odds,
                existing_snapshots=existing_snapshots,
            )
            odds_written += int(odds_result["written"])
            if (odds_payload := odds_result.get("broadcast_payload")) is not None:
                odds_updates[match.id] = odds_payload

        await db.flush()

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


def _scrape_exception_failure_kind(exc: Exception) -> str:
    """Reduce scraper failures to the bounded worker retry taxonomy."""
    if isinstance(exc, TimeoutError):
        return "timeout"
    if not isinstance(exc, BridgeError):
        return "validation" if isinstance(exc, ValueError) else "internal"

    if exc.failure_kind:
        return exc.failure_kind

    message = str(exc).lower()
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if "429" in message or "rate limit" in message:
        return "provider_429"
    if any(code in message for code in ("500", "502", "503", "504", "5xx")):
        return "provider_5xx"
    if any(marker in message for marker in ("anti-bot", "antibot", "captcha", "cloudflare", "challenge")):
        return "anti_bot"
    if "403" in message or "forbidden" in message:
        return "forbidden"
    if any(marker in message for marker in ("invalid json", "invalid report", "schema_version", "schema")):
        return "schema"
    if any(marker in message for marker in ("not configured", "not found", "runtime is not ready", "unsupported")):
        return "contract_mismatch"
    return "transport"


def _scrape_report_failure_kind(report_summary: dict[str, Any]) -> str:
    if report_summary.get("anti_bot_detected") is True:
        return "anti_bot"
    failure_types = {str(item).strip().lower() for item in report_summary.get("failure_types") or []}
    if failure_types & {"rate_limited", "rate_limit", "http_429", "429"}:
        return "provider_429"
    if any(kind in failure_types for kind in {"http_500", "http_502", "http_503", "http_504", "server_error"}):
        return "provider_5xx"
    return "transport"


async def _persist_scrape_job_failure(
    db: AsyncSession,
    *,
    job_id: int,
    exc: Exception,
    prior_output: str | None,
) -> ScrapeJob:
    """Discard partial ingestion, then persist only the bounded failure fact."""
    failure_kind = _scrape_exception_failure_kind(exc)
    message = str(exc)
    try:
        safe_output = json.loads(prior_output) if prior_output else {}
    except (TypeError, ValueError):
        safe_output = {}
    if not isinstance(safe_output, dict):
        safe_output = {}
    report = safe_output.get("scrape_report")
    if failure_kind == "transport" and isinstance(report, dict):
        failure_kind = _scrape_exception_failure_kind(BridgeError(json.dumps(report, sort_keys=True)))
    safe_output["failure"] = {"kind": failure_kind}

    await db.rollback()
    job = await db.get(ScrapeJob, job_id)
    if job is None:
        raise LookupError(f"ScrapeJob {job_id} disappeared while recording failure") from exc
    job.status = "failed"
    job.error = message
    job.output = json.dumps(safe_output)
    job.completed_at = datetime.now(timezone.utc)
    await append_scrape_job_log(
        db,
        job.id,
        action="job_failed",
        message=message,
        level="error",
        metadata={"error_type": exc.__class__.__name__, "failure_kind": failure_kind},
    )
    await db.flush()
    return job


async def execute_scrape_job(db: AsyncSession, job_id: int) -> ScrapeJob:
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise LookupError(f"ScrapeJob {job_id} not found")

    job.status = "running"
    job.error = None
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
        # Jobs can also be created by scheduled/internal callers or predate
        # request-schema validation, so validate the persisted payload again.
        job.params = _normalize_scrape_params(job.job_type, job.params)
        if job.job_type not in BRIDGE_SCRAPE_JOB_TYPES:
            raise ValueError(f"Unsupported executable scrape job type: {job.job_type}")

        if _avoid_rescraping_requested(job):
            duplicate = await _find_completed_duplicate_scrape_job(db, job)
            if duplicate is not None:
                summary = {
                    "skipped": True,
                    "reason": "duplicate_completed_job",
                    "reused_job_id": duplicate.id,
                }
                duplicate_dataset_id = _scrape_output_dataset_id(duplicate)
                if duplicate_dataset_id is not None:
                    summary["dataset_id"] = duplicate_dataset_id
                duplicate_report = _scrape_output_summary(duplicate).get("scrape_report")
                if isinstance(duplicate_report, dict):
                    summary["scrape_report"] = dict(duplicate_report)
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

        if job.job_type in BRIDGE_SCRAPE_JOB_TYPES:
            if job.job_type == "refresh_results" and not (job.params or {}).get("match_links"):
                raise ValueError("Result refresh job is missing source match links")
            scraper_engine, pipeline_v2_enabled = _selected_scraper_engine(job)
            runtime_catalog = await _runtime_catalog_league_env(db, job)
            runtime_catalog_env = {
                **runtime_catalog.env,
                "ODDSHARVESTER_PIPELINE_V2": "1" if pipeline_v2_enabled else "0",
                "ODDSHARVESTER_PIPELINE_V2_PERCENT": str(settings.scrape_pipeline_v2_percent),
            }
            args = _build_oddsharvester_args(
                job,
                league_override=runtime_catalog.league_override,
                scraper_engine=scraper_engine,
            )
            effective_leagues = runtime_catalog.league_override or sorted(_requested_scrape_league_slugs(job))
            timeout_seconds = _effective_oddsharvester_timeout(job, len(effective_leagues))
            runtime_catalog_league_count = len(
                json.loads(runtime_catalog_env.get("ODDSHARVESTER_RUNTIME_FOOTBALL_LEAGUES", "{}"))
            )
            if runtime_catalog.skipped_historic_leagues:
                await append_scrape_job_log(
                    db,
                    job.id,
                    action="historic_leagues_skipped",
                    message="Skipped leagues without a validated Results page for this season",
                    level="warning",
                    metadata={"leagues": runtime_catalog.skipped_historic_leagues},
                )
            await append_scrape_job_log(
                db,
                job.id,
                action="engine_selected",
                message=f"Selected scraper engine: {scraper_engine}",
                metadata={
                    "scraper_engine": scraper_engine,
                    "pipeline_v2_enabled": pipeline_v2_enabled,
                    "pipeline_v2_percent": settings.scrape_pipeline_v2_percent,
                },
            )
            await append_scrape_job_log(
                db,
                job.id,
                action="bridge_invocation",
                message="Invoking OddsHarvester bridge",
                metadata={
                    "args": _redact_sensitive_args(args),
                    "timeout_seconds": timeout_seconds,
                    "scraper_engine": scraper_engine,
                    "pipeline_v2_enabled": pipeline_v2_enabled,
                    "report_requested": True,
                    "runtime_catalog_league_count": runtime_catalog_league_count,
                },
            )
            # Do not hold one database transaction/connection while a live
            # OddsHarvester subprocess runs for tens of minutes. Persist the
            # running state and reopen a fresh transaction for ingestion.
            commit = getattr(db, "commit", None)
            if commit is not None:
                await commit()
            try:
                bridge_result = await _run_oddsharvester_with_report(
                    args,
                    label=f"scrape_job_{job_id}",
                    timeout=timeout_seconds,
                    extra_env=runtime_catalog_env,
                )
            finally:
                # Some worker/session factories expire ORM instances on commit.
                # Reload explicitly after the long subprocess so later logging
                # and ingestion never trigger implicit async IO from attributes.
                refreshed_job = await db.get(ScrapeJob, job_id)
                if refreshed_job is None:
                    raise ValueError(f"Scrape job {job_id} disappeared during bridge execution")
                job = refreshed_job
            if isinstance(bridge_result, OddsHarvesterJsonResult):
                payload = bridge_result.records
                report = bridge_result.report
                cli_error = bridge_result.cli_error
            else:
                payload = bridge_result
                report = None
                cli_error = None

            report_summary = None
            if report is not None:
                report_summary = _scrape_report_summary(report, payload, cli_error=cli_error)
                await _persist_scrape_report_artifact(db, job.id, report_summary)
                await append_scrape_job_log(
                    db,
                    job.id,
                    action="scrape_report",
                    message=f"OddsHarvester report classified the scrape as {report_summary['health']}",
                    level="warning" if report_summary["health"] == "degraded" else "info",
                    metadata=report_summary,
                )
                if report_summary["health"] == "failed":
                    job.output = json.dumps({"scrape_report": report_summary})
                    raise BridgeError(
                        "OddsHarvester scrape report classified the run as failed",
                        failure_kind=_scrape_report_failure_kind(report_summary),
                    )

            ingestion_result = await _ingest_scraped_payload(db, job, payload)
            if isinstance(ingestion_result, tuple) and len(ingestion_result) == 3:
                summary, match_updates, odds_updates = ingestion_result
            else:
                summary = ingestion_result
                match_updates = {}
                odds_updates = {}
            if report_summary is not None:
                summary = {**summary, "scrape_report": report_summary}
                if report_summary["health"] == "no_fixtures":
                    await append_scrape_job_log(
                        db,
                        job.id,
                        action="no_fixtures",
                        message="No fixtures were published for the requested upcoming date",
                        level="warning",
                        metadata=report_summary,
                    )
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
            # Guard retained for exhaustiveness if supported types change.
            raise ValueError(f"Unsupported executable scrape job type: {job.job_type}")

        job.completed_at = datetime.now(timezone.utc)
    except BridgeError as e:
        job = await _persist_scrape_job_failure(db, job_id=job_id, exc=e, prior_output=job.output)
    except Exception as e:
        job = await _persist_scrape_job_failure(db, job_id=job_id, exc=e, prior_output=job.output)

    await db.flush()
    return job
