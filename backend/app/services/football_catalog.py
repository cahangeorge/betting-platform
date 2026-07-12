from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.football_catalog import FootballLeagueCatalog
from app.schemas.catalog import (
    CountryInfo,
    FootballCatalogRefreshRequest,
    FootballCatalogRefreshResponse,
    LeagueInfo,
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
        )
        countries[row.country_name].append(league)
        by_slug[row.scrape_slug] = (row.country_name, league)

    return [CountryInfo(country=country, leagues=countries[country]) for country in country_order if countries[country]]


async def load_football_catalog(db: AsyncSession, static_catalog: list[CountryInfo]) -> list[CountryInfo]:
    result = await db.execute(select(FootballLeagueCatalog).order_by(FootballLeagueCatalog.country_name, FootballLeagueCatalog.league_name))
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
