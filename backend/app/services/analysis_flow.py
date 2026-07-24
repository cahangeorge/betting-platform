import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, MatchSource
from app.models.scrape import ScrapedDataset, ScrapeJob
from app.models.strategy import Strategy
from app.models.user import User
from app.services.run_authorization import can_read_scrape_job

DATASET_SOURCE_CHUNK_SIZE = 500
UNRESOLVED_SAMPLE_LIMIT = 10
T = TypeVar("T")


@dataclass(frozen=True)
class DatasetMatchResolution:
    dataset: ScrapedDataset
    scrape_job_id: int
    scrape_job_status: str
    match_ids: list[int]
    total_records: int
    resolved_records: int
    unresolved_records: int
    resolution_counts: dict[str, int]
    unresolved_samples: list[dict[str, object]]


def _source_id_from_match_link(match_link: str) -> str | None:
    parsed = urlparse(match_link)
    fragment = parsed.fragment.strip("/")
    if fragment:
        return fragment
    path_parts = [part for part in parsed.path.split("/") if part]
    return path_parts[-1] if path_parts else None


def _unique(values: Iterable[T]) -> list[T]:
    return list(dict.fromkeys(values))


def _normalize_text(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _coerce_match_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        parsed = None
        for fmt in ("%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _minute_key(value: object) -> str:
    parsed = _coerce_match_datetime(value)
    return parsed.replace(second=0, microsecond=0).isoformat() if parsed is not None else ""


def _date_key(value: object) -> str:
    parsed = _coerce_match_datetime(value)
    return parsed.date().isoformat() if parsed is not None else ""


def _fixture_key(
    *,
    match_date: object,
    league: object,
    home_team: object,
    away_team: object,
    date_only: bool,
    include_league: bool,
) -> tuple[str, ...] | None:
    date_value = _date_key(match_date) if date_only else _minute_key(match_date)
    home_value = _normalize_text(home_team)
    away_value = _normalize_text(away_team)
    if not date_value or not home_value or not away_value:
        return None
    values = [date_value]
    if include_league:
        league_value = _normalize_text(league)
        if not league_value:
            return None
        values.append(league_value)
    values.extend((home_value, away_value))
    return tuple(values)


def _record_summary(index: int, record: dict, reason: str) -> dict[str, object]:
    return {
        "record_index": index,
        "home_team": str(record.get("home_team") or ""),
        "away_team": str(record.get("away_team") or ""),
        "match_date": str(record.get("match_date") or ""),
        "league_name": str(record.get("league_name") or ""),
        "match_link": str(record.get("match_link") or ""),
        "reason": reason,
    }


async def load_analysis_strategies(db: AsyncSession, strategy_ids: list[int]) -> list[Strategy]:
    """Resolve an explicit strategy selection, or every active strategy.

    Explicit selections retain caller order and may include inactive strategies.
    Empty selections intentionally mean all active strategies.
    """

    if strategy_ids:
        ordered_ids = [int(value) for value in _unique(strategy_ids)]
        result = await db.execute(select(Strategy).where(Strategy.id.in_(ordered_ids)))
        by_id = {strategy.id: strategy for strategy in result.scalars().all()}
        missing = [strategy_id for strategy_id in ordered_ids if strategy_id not in by_id]
        if missing:
            raise LookupError(f"Strategies not found: {', '.join(str(value) for value in missing)}")
        return [by_id[strategy_id] for strategy_id in ordered_ids]

    result = await db.execute(
        select(Strategy).where(Strategy.is_active.is_(True)).order_by(Strategy.created_at.asc(), Strategy.id.asc())
    )
    return list(result.scalars().all())


async def resolve_dataset_match_ids(
    db: AsyncSession,
    dataset_id: int,
    *,
    user: User | None = None,
) -> DatasetMatchResolution:
    """Resolve dataset records to persisted matches without silent guesswork.

    Stable source URLs and external ids win. Records that cannot use those keys
    fall back to normalized fixture identity (teams, kickoff, competition), with
    reversed orientation support for source/import flips. Every fallback must be
    unique; ambiguous or incomplete records remain explicitly unresolved.
    """

    dataset = await db.get(ScrapedDataset, dataset_id)
    if dataset is None:
        raise LookupError(f"Dataset {dataset_id} not found")

    data = dataset.data if isinstance(dataset.data, dict) else {}
    raw_job_id = data.get("job_id")
    if not isinstance(raw_job_id, int) or raw_job_id <= 0:
        raise ValueError(f"Dataset {dataset.id} has no originating scrape job lineage")
    scrape_job = await db.get(ScrapeJob, raw_job_id)
    if scrape_job is None:
        raise ValueError(f"Dataset {dataset.id} references missing scrape job {raw_job_id}")
    if user is not None and not can_read_scrape_job(scrape_job, user):
        raise PermissionError(f"Dataset {dataset.id} is not owned by the current user")
    if scrape_job.status not in {"completed", "partial"}:
        raise ValueError(
            f"Dataset {dataset.id} belongs to scrape job {scrape_job.id} with status '{scrape_job.status}'"
        )

    stored_match_ids = data.get("match_ids")
    if isinstance(stored_match_ids, list) and stored_match_ids:
        candidate_ids = [int(value) for value in _unique(stored_match_ids) if int(value) > 0]
        result = await db.execute(select(Match.id).where(Match.id.in_(candidate_ids)))
        existing_ids = {row[0] for row in result.all()}
        missing_ids = [match_id for match_id in candidate_ids if match_id not in existing_ids]
        unresolved_samples = [
            {"match_id": match_id, "reason": "stored_match_id_missing"}
            for match_id in missing_ids[:UNRESOLVED_SAMPLE_LIMIT]
        ]
        resolved_ids = [match_id for match_id in candidate_ids if match_id in existing_ids]
        return DatasetMatchResolution(
            dataset=dataset,
            scrape_job_id=scrape_job.id,
            scrape_job_status=scrape_job.status,
            match_ids=resolved_ids,
            total_records=len(candidate_ids),
            resolved_records=len(resolved_ids),
            unresolved_records=len(missing_ids),
            resolution_counts={"stored_match_id": len(resolved_ids)},
            unresolved_samples=unresolved_samples,
        )

    raw_records = data.get("matches")
    if not isinstance(raw_records, list):
        raise ValueError(f"Dataset {dataset.id} has no match records")
    records = [record for record in raw_records if isinstance(record, dict)]
    invalid_record_count = len(raw_records) - len(records)

    ordered_links = _unique(
        str(record["match_link"])
        for record in records
        if isinstance(record.get("match_link"), str) and record["match_link"]
    )
    match_ids_by_link: dict[str, set[int]] = defaultdict(set)
    for offset in range(0, len(ordered_links), DATASET_SOURCE_CHUNK_SIZE):
        link_chunk = ordered_links[offset : offset + DATASET_SOURCE_CHUNK_SIZE]
        result = await db.execute(
            select(MatchSource.url, MatchSource.match_id).where(
                MatchSource.source == dataset.source,
                MatchSource.url.in_(link_chunk),
            )
        )
        for url, match_id in result.all():
            if url:
                match_ids_by_link[url].add(match_id)

    source_ids = _unique(
        source_id for link in ordered_links if (source_id := _source_id_from_match_link(link)) is not None
    )
    match_ids_by_source_id: dict[str, set[int]] = defaultdict(set)
    for offset in range(0, len(source_ids), DATASET_SOURCE_CHUNK_SIZE):
        source_chunk = source_ids[offset : offset + DATASET_SOURCE_CHUNK_SIZE]
        result = await db.execute(select(Match.external_id, Match.id).where(Match.external_id.in_(source_chunk)))
        for source_id, match_id in result.all():
            if source_id:
                match_ids_by_source_id[source_id].add(match_id)

    needs_fixture_fallback = False
    for record in records:
        link = str(record.get("match_link") or "")
        url_candidates = match_ids_by_link.get(link, set()) if link else set()
        source_id = _source_id_from_match_link(link) if link else None
        source_candidates = match_ids_by_source_id.get(source_id or "", set())
        if len(url_candidates) != 1 and len(source_candidates) != 1:
            needs_fixture_fallback = True
            break

    persisted_matches: list[Match] = []
    if needs_fixture_fallback:
        matches_result = await db.execute(select(Match).where(Match.sport == "football"))
        persisted_matches = list(matches_result.scalars().all())
    fixture_indexes: dict[tuple[bool, bool], dict[tuple[str, ...], set[int]]] = {}
    for date_only in (False, True):
        for include_league in (True, False):
            index: dict[tuple[str, ...], set[int]] = defaultdict(set)
            for match in persisted_matches:
                key = _fixture_key(
                    match_date=match.match_date,
                    league=match.competition,
                    home_team=match.home_team,
                    away_team=match.away_team,
                    date_only=date_only,
                    include_league=include_league,
                )
                if key is not None:
                    index[key].add(match.id)
            fixture_indexes[(date_only, include_league)] = index

    resolved_match_ids: list[int] = []
    resolution_counts: dict[str, int] = defaultdict(int)
    unresolved_samples: list[dict[str, object]] = []
    unresolved_count = invalid_record_count
    if invalid_record_count:
        unresolved_samples.append({"reason": "record_is_not_an_object", "count": invalid_record_count})

    for record_index, record in enumerate(records):
        link = str(record.get("match_link") or "")
        resolved_match_id: int | None = None
        resolved_by: str | None = None
        ambiguity_reason: str | None = None

        if link:
            url_candidates = match_ids_by_link.get(link, set())
            if len(url_candidates) == 1:
                resolved_match_id = next(iter(url_candidates))
                resolved_by = "source_url"
            elif len(url_candidates) > 1:
                ambiguity_reason = "ambiguous_source_url"

        if resolved_match_id is None and link:
            source_id = _source_id_from_match_link(link)
            source_candidates = match_ids_by_source_id.get(source_id or "", set())
            if len(source_candidates) == 1:
                resolved_match_id = next(iter(source_candidates))
                resolved_by = "source_id"
            elif len(source_candidates) > 1:
                ambiguity_reason = "ambiguous_source_id"

        if resolved_match_id is None:
            for date_only, include_league in ((False, True), (True, True), (False, False), (True, False)):
                for reversed_orientation in (False, True):
                    home_team = record.get("away_team") if reversed_orientation else record.get("home_team")
                    away_team = record.get("home_team") if reversed_orientation else record.get("away_team")
                    key = _fixture_key(
                        match_date=record.get("match_date"),
                        league=record.get("league_name"),
                        home_team=home_team,
                        away_team=away_team,
                        date_only=date_only,
                        include_league=include_league,
                    )
                    if key is None:
                        continue
                    candidates = fixture_indexes[(date_only, include_league)].get(key, set())
                    if len(candidates) == 1:
                        resolved_match_id = next(iter(candidates))
                        precision = "date" if date_only else "kickoff"
                        league_scope = "league" if include_league else "all_leagues"
                        orientation = "reversed" if reversed_orientation else "direct"
                        resolved_by = f"normalized_fixture_{precision}_{league_scope}_{orientation}"
                        break
                    if len(candidates) > 1:
                        ambiguity_reason = "ambiguous_normalized_fixture"
                if resolved_match_id is not None:
                    break

        if resolved_match_id is None:
            unresolved_count += 1
            if len(unresolved_samples) < UNRESOLVED_SAMPLE_LIMIT:
                unresolved_samples.append(
                    _record_summary(record_index, record, ambiguity_reason or "no_deterministic_match")
                )
            continue

        resolved_match_ids.append(resolved_match_id)
        resolution_counts[resolved_by or "unknown"] += 1

    return DatasetMatchResolution(
        dataset=dataset,
        scrape_job_id=scrape_job.id,
        scrape_job_status=scrape_job.status,
        match_ids=_unique(resolved_match_ids),
        total_records=len(raw_records),
        resolved_records=len(records) - (unresolved_count - invalid_record_count),
        unresolved_records=unresolved_count,
        resolution_counts=dict(resolution_counts),
        unresolved_samples=unresolved_samples,
    )


def summarize_analysis_batch_status(statuses: list[str]) -> str:
    if not statuses or all(status == "no_matches" for status in statuses):
        return "no_matches"
    if all(status == "deduped" for status in statuses):
        return "deduped"
    if all(status in {"completed", "deduped"} for status in statuses):
        return "completed"
    if all(status == "failed" for status in statuses):
        return "failed"
    return "partial"
