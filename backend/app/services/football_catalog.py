import re
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.football_catalog import FootballLeagueCatalog
from app.schemas.catalog import (
    CountryInfo,
    FootballCatalogDiscoveryValidationRequest,
    FootballCatalogDiscoveryValidationResponse,
    FootballCatalogRefreshRequest,
    FootballCatalogRefreshResponse,
    FootballCatalogValidationOutcome,
    FootballCatalogValidationResponse,
    FootballCatalogWorkflowAttempt,
    FootballLeagueDiscoveryInput,
    LeagueInfo,
)
from app.services.python_bridge import (
    discover_oddsharvester_football_catalog,
    validate_oddsharvester_football_catalog,
)


def merge_football_catalog(
    static_catalog: list[CountryInfo], discovered: list[FootballLeagueCatalog]
) -> list[CountryInfo]:
    """Overlay discovered rows on the in-repo catalog without hiding static fallback rows."""
    countries: dict[str, list[LeagueInfo]] = defaultdict(list)
    country_order: list[str] = []
    by_slug: dict[str, tuple[str, LeagueInfo]] = {}

    for country in static_catalog:
        country_order.append(country.country)
        for league in country.leagues:
            static_league = league.model_copy(update={"source": "static"})
            countries[country.country].append(static_league)
            if static_league.scrape_slug:
                by_slug[static_league.scrape_slug] = (country.country, static_league)

    for row in discovered:
        previous = by_slug.get(row.scrape_slug)
        # A live URL discovery proves that an OddsPortal page exists, not that
        # the installed OddsHarvester CLI accepts its slug. Do not let a
        # pending discovery hide a known, CLI-supported fallback league.
        if previous and row.status != "unavailable":
            continue
        if previous:
            countries[previous[0]].remove(previous[1])
        if row.country_name not in countries:
            country_order.append(row.country_name)
        league = LeagueInfo(
            id=previous[1].id if previous else row.scrape_slug.replace("-", "_"),
            name=row.league_name,
            scrape_slug=row.scrape_slug,
            source="discovered",
            status=row.status,
            source_url=row.source_url,
            last_seen_at=row.last_seen_at,
            scrape_capability="full",
        )
        countries[row.country_name].append(league)
        by_slug[row.scrape_slug] = (row.country_name, league)

    return [CountryInfo(country=country, leagues=countries[country]) for country in country_order if countries[country]]


async def load_football_catalog(db: AsyncSession, static_catalog: list[CountryInfo]) -> list[CountryInfo]:
    result = await db.execute(
        select(FootballLeagueCatalog).order_by(
            FootballLeagueCatalog.country_name,
            FootballLeagueCatalog.league_name,
        )
    )
    return merge_football_catalog(static_catalog, list(result.scalars().all()))


async def refresh_football_catalog(
    db: AsyncSession, request: FootballCatalogRefreshRequest
) -> FootballCatalogRefreshResponse:
    """Upsert a worker-produced catalog snapshot; no live network requests occur here."""
    incoming_by_slug = {league.scrape_slug: league for league in request.leagues}
    result = await db.execute(
        select(FootballLeagueCatalog).where(FootballLeagueCatalog.scrape_slug.in_(incoming_by_slug))
    )
    existing_by_slug = {league.scrape_slug: league for league in result.scalars().all()}
    now = datetime.now(UTC)
    created = 0
    updated = 0

    for slug, payload in incoming_by_slug.items():
        row = existing_by_slug.get(slug)
        if row is None:
            row = FootballLeagueCatalog(scrape_slug=slug, source=request.source)
            db.add(row)
            created += 1
        else:
            updated += 1
        row.country_slug = payload.country_slug
        row.country_name = payload.country_name
        row.league_name = payload.league_name
        row.source_url = payload.source_url
        row.source = request.source
        row.status = payload.status
        row.last_seen_at = now
        row.last_validated_at = payload.last_validated_at or now

    marked_unavailable = 0
    if request.complete_snapshot:
        missing_result = await db.execute(
            select(FootballLeagueCatalog).where(FootballLeagueCatalog.source == request.source)
        )
        for row in missing_result.scalars().all():
            if row.scrape_slug not in incoming_by_slug and row.status != "unavailable":
                row.status = "unavailable"
                marked_unavailable += 1

    await db.flush()
    return FootballCatalogRefreshResponse(
        created=created,
        updated=updated,
        marked_unavailable=marked_unavailable,
        refreshed_at=now,
    )


def apply_football_catalog_validation(
    rows: list[FootballLeagueCatalog], results: list[dict]
) -> FootballCatalogValidationResponse:
    """Persist validator outcomes without equating URL reachability to CLI support."""
    by_slug = {str(item.get("scrape_slug")): item for item in results if item.get("scrape_slug")}
    outcomes: list[FootballCatalogValidationOutcome] = []
    now = datetime.now(UTC)
    for row in rows:
        result = by_slug.get(row.scrape_slug)
        if result is None:
            continue
        status = str(result.get("status"))
        if status not in {"available", "validation_pending", "unavailable"}:
            status = "validation_pending"
        detail = str(result.get("detail") or "No validator detail returned.")[:500]
        raw_match_count = result.get("match_count", 0)
        match_count = raw_match_count if isinstance(raw_match_count, int) and raw_match_count >= 0 else 0
        row.status = status
        row.last_validated_at = now
        outcomes.append(
            FootballCatalogValidationOutcome(
                scrape_slug=row.scrape_slug,
                status=status,
                detail=detail,
                match_count=match_count,
            )
        )

    return FootballCatalogValidationResponse(
        requested=len(rows),
        checked=len(outcomes),
        results_page_ok=sum(outcome.status == "available" for outcome in outcomes),
        unavailable=sum(outcome.status == "unavailable" for outcome in outcomes),
        pending=sum(outcome.status == "validation_pending" for outcome in outcomes),
        outcomes=outcomes,
    )


async def validate_pending_football_catalog(
    db: AsyncSession, *, country: str | None, limit: int
) -> FootballCatalogValidationResponse:
    stmt = (
        select(FootballLeagueCatalog)
        .where(FootballLeagueCatalog.status.in_({"validation_pending", "validation_passed"}))
        .order_by(FootballLeagueCatalog.country_name, FootballLeagueCatalog.league_name)
        .limit(limit)
    )
    if country:
        stmt = stmt.where(FootballLeagueCatalog.country_name.ilike(country.strip()))
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    if not rows:
        return FootballCatalogValidationResponse(
            requested=0, checked=0, results_page_ok=0, unavailable=0, pending=0
        )

    validator_payload = [
        {"scrape_slug": row.scrape_slug, "source_url": row.source_url}
        for row in rows
    ]
    results = await validate_oddsharvester_football_catalog(validator_payload)
    response = apply_football_catalog_validation(rows, results)
    await db.flush()
    return response


def _country_key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value.strip().casefold()).encode(
        "ascii", "ignore"
    ).decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def filter_discovered_football_leagues(payload: dict, countries: list[str]) -> list[dict]:
    """Filter and de-duplicate discovery output for user-selected country names or slugs."""
    selected = {_country_key(country) for country in countries}
    filtered: dict[str, dict] = {}
    for item in payload.get("leagues", []):
        if not isinstance(item, dict):
            continue
        country_slug = str(item.get("country_slug") or "")
        country_name = str(item.get("country_name") or "")
        scrape_slug = str(item.get("scrape_slug") or "")
        if not scrape_slug or not (
            _country_key(country_slug) in selected or _country_key(country_name) in selected
        ):
            continue
        filtered[scrape_slug] = {**item, "status": "validation_pending"}
    return list(filtered.values())


async def _load_catalog_rows_by_slugs(
    db: AsyncSession, slugs: list[str]
) -> list[FootballLeagueCatalog]:
    if not slugs:
        return []
    result = await db.execute(
        select(FootballLeagueCatalog)
        .where(FootballLeagueCatalog.scrape_slug.in_(slugs))
        .order_by(FootballLeagueCatalog.country_name, FootballLeagueCatalog.league_name)
    )
    return list(result.scalars().all())


async def _validate_catalog_rows(
    db: AsyncSession,
    rows: list[FootballLeagueCatalog],
    *,
    batch_size: int,
) -> int:
    checked = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        validator_payload = [
            {"scrape_slug": row.scrape_slug, "source_url": row.source_url}
            for row in batch
        ]
        results = await validate_oddsharvester_football_catalog(validator_payload)
        checked += apply_football_catalog_validation(batch, results).checked
        await db.flush()
    return checked


async def discover_and_validate_football_catalog(
    db: AsyncSession,
    request: FootballCatalogDiscoveryValidationRequest,
) -> FootballCatalogDiscoveryValidationResponse:
    """Repeat live discovery and rendered Results-page validation within explicit safety bounds."""
    attempts: list[FootballCatalogWorkflowAttempt] = []
    final_discovered = 0
    final_available = 0
    final_unavailable = 0
    final_pending = 0

    for attempt_number in range(1, request.max_attempts + 1):
        discovery = await discover_oddsharvester_football_catalog()
        candidates = filter_discovered_football_leagues(discovery, request.countries)
        final_discovered = len(candidates)
        if not candidates:
            return FootballCatalogDiscoveryValidationResponse(
                countries=request.countries,
                attempts_used=len(attempts),
                discovered=0,
                available=0,
                unavailable=0,
                pending=0,
                stop_reason="no_candidates",
                attempts=attempts,
            )

        slugs = [str(candidate["scrape_slug"]) for candidate in candidates]
        existing = {
            row.scrape_slug: row for row in await _load_catalog_rows_by_slugs(db, slugs)
        }
        discovery_inputs = [
            FootballLeagueDiscoveryInput.model_validate(
                {
                    **candidate,
                    # A previously validated league remains trusted. Rejected
                    # and transient candidates are deliberately retried.
                    "status": "available"
                    if existing.get(str(candidate["scrape_slug"]), None)
                    and existing[str(candidate["scrape_slug"])].status == "available"
                    else "validation_pending",
                }
            )
            for candidate in candidates
        ]
        refresh = await refresh_football_catalog(
            db,
            FootballCatalogRefreshRequest(
                source="oddsharvester-live-discovery",
                leagues=discovery_inputs,
                complete_snapshot=False,
            ),
        )

        rows = await _load_catalog_rows_by_slugs(db, slugs)
        pending_rows = [row for row in rows if row.status != "available"]
        checked = await _validate_catalog_rows(db, pending_rows, batch_size=request.batch_size)

        final_available = sum(row.status == "available" for row in rows)
        final_unavailable = sum(row.status == "unavailable" for row in rows)
        final_pending = sum(row.status not in {"available", "unavailable"} for row in rows)
        attempts.append(
            FootballCatalogWorkflowAttempt(
                attempt=attempt_number,
                discovered=len(rows),
                created=refresh.created,
                updated=refresh.updated,
                checked=checked,
                available=final_available,
                unavailable=final_unavailable,
                pending=final_pending,
            )
        )

        if final_available == len(rows):
            return FootballCatalogDiscoveryValidationResponse(
                countries=request.countries,
                attempts_used=len(attempts),
                discovered=final_discovered,
                available=final_available,
                unavailable=final_unavailable,
                pending=final_pending,
                stop_reason="all_validated",
                attempts=attempts,
            )

    return FootballCatalogDiscoveryValidationResponse(
        countries=request.countries,
        attempts_used=len(attempts),
        discovered=final_discovered,
        available=final_available,
        unavailable=final_unavailable,
        pending=final_pending,
        stop_reason="attempt_limit",
        attempts=attempts,
    )
