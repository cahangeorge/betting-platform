from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models.football_catalog import FootballLeagueCatalog
from app.schemas.catalog import (
    FootballCatalogDiscoveryValidationRequest,
    FootballCatalogRefreshResponse,
)
from app.services import football_catalog as football_catalog_service
from app.services.football_catalog import (
    apply_football_catalog_validation,
    discover_and_validate_football_catalog,
    filter_discovered_football_leagues,
)


def _row(slug: str) -> FootballLeagueCatalog:
    return FootballLeagueCatalog(
        scrape_slug=slug,
        country_slug="argentina",
        country_name="Argentina",
        league_name=slug,
        source_url=f"https://www.oddsportal.com/football/argentina/{slug}/",
        status="validation_pending",
        last_seen_at=datetime(2026, 7, 12, tzinfo=UTC),
    )


def test_validation_marks_reachable_results_verified_and_missing_results_unavailable():
    reachable = _row("argentina-primera-c")
    missing = _row("argentina-torneo-federal")

    summary = apply_football_catalog_validation(
        [reachable, missing],
        [
            {
                "scrape_slug": reachable.scrape_slug,
                "status": "available",
                "detail": "Results page passed and was promoted for upcoming scraping.",
                "match_count": 12,
            },
            {
                "scrape_slug": missing.scrape_slug,
                "status": "unavailable",
                "detail": "Rendered results page contained no match links.",
                "match_count": 0,
            },
        ],
    )

    assert reachable.status == "available"
    assert missing.status == "unavailable"
    assert summary.results_page_ok == 1
    assert summary.unavailable == 1
    assert summary.pending == 0


def test_discovery_filter_accepts_country_names_or_slugs_and_deduplicates():
    payload = {
        "leagues": [
            {
                "scrape_slug": "argentina-liga-profesional",
                "country_slug": "argentina",
                "country_name": "Argentina",
            },
            {
                "scrape_slug": "north-central-america-concacaf-champions-cup",
                "country_slug": "north-central-america",
                "country_name": "North Central America",
            },
            {
                "scrape_slug": "argentina-liga-profesional",
                "country_slug": "argentina",
                "country_name": "Argentina",
            },
            {
                "scrape_slug": "curacao-promer-divishon",
                "country_slug": "curacao",
                "country_name": "Curacao",
            },
        ]
    }

    result = filter_discovered_football_leagues(payload, ["Argentina", "North & Central America", "Curaçao"])

    assert [item["scrape_slug"] for item in result] == [
        "argentina-liga-profesional",
        "north-central-america-concacaf-champions-cup",
        "curacao-promer-divishon",
    ]
    assert all(item["status"] == "validation_pending" for item in result)


def test_discovery_request_normalizes_and_deduplicates_countries():
    request = FootballCatalogDiscoveryValidationRequest(
        countries=[" Argentina ", "argentina", "Brazil"],
        max_attempts=3,
        batch_size=20,
    )

    assert request.countries == ["Argentina", "Brazil"]


@pytest.mark.asyncio
async def test_discovery_workflow_retries_rejected_leagues_until_all_are_validated(monkeypatch):
    rows: dict[str, FootballLeagueCatalog] = {}
    validation_round = 0
    discovery_payload = {
        "leagues": [
            {
                "scrape_slug": "argentina-liga-profesional",
                "country_slug": "argentina",
                "country_name": "Argentina",
                "league_name": "Liga Profesional",
                "source_url": "https://www.oddsportal.com/football/argentina/liga-profesional/",
            },
            {
                "scrape_slug": "brazil-serie-a",
                "country_slug": "brazil",
                "country_name": "Brazil",
                "league_name": "Serie A",
                "source_url": "https://www.oddsportal.com/football/brazil/serie-a-betano/",
            },
        ]
    }

    async def fake_discover():
        return discovery_payload

    async def fake_load(_db, slugs):
        return [rows[slug] for slug in slugs if slug in rows]

    async def fake_refresh(_db, request):
        created = 0
        for league in request.leagues:
            row = rows.get(league.scrape_slug)
            if row is None:
                row = FootballLeagueCatalog(scrape_slug=league.scrape_slug)
                rows[league.scrape_slug] = row
                created += 1
            row.country_slug = league.country_slug
            row.country_name = league.country_name
            row.league_name = league.league_name
            row.source_url = league.source_url
            row.status = league.status
        return FootballCatalogRefreshResponse(
            created=created,
            updated=len(request.leagues) - created,
            marked_unavailable=0,
            refreshed_at=datetime.now(UTC),
        )

    async def fake_validate(_db, pending_rows, *, batch_size):
        nonlocal validation_round
        assert batch_size == 20
        validation_round += 1
        for row in pending_rows:
            row.status = "available" if row.country_name == "Argentina" or validation_round > 1 else "unavailable"
        return len(pending_rows)

    monkeypatch.setattr(football_catalog_service, "discover_oddsharvester_football_catalog", fake_discover)
    monkeypatch.setattr(football_catalog_service, "_load_catalog_rows_by_slugs", fake_load)
    monkeypatch.setattr(football_catalog_service, "refresh_football_catalog", fake_refresh)
    monkeypatch.setattr(football_catalog_service, "_validate_catalog_rows", fake_validate)

    response = await discover_and_validate_football_catalog(
        SimpleNamespace(),
        FootballCatalogDiscoveryValidationRequest(countries=["Argentina", "Brazil"], max_attempts=3, batch_size=20),
    )

    assert response.stop_reason == "all_validated"
    assert response.attempts_used == 2
    assert response.discovered == 2
    assert response.available == 2
    assert response.unavailable == 0
    assert [attempt.checked for attempt in response.attempts] == [2, 1]
