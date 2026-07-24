from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.v1.catalog import CATALOG
from app.models.football_catalog import FootballLeagueCatalog
from app.schemas.catalog import FootballCatalogRefreshRequest
from app.services.football_catalog import merge_football_catalog


def _discovered(**overrides) -> FootballLeagueCatalog:
    values = {
        "scrape_slug": "australia-npl-victoria",
        "country_slug": "australia",
        "country_name": "Australia",
        "league_name": "NPL Victoria",
        "source_url": "https://www.oddsportal.com/football/australia/npl-victoria/",
        "source": "oddsharvester-discovery",
        "status": "available",
        "last_seen_at": datetime(2026, 7, 12, tzinfo=UTC),
    }
    values.update(overrides)
    return FootballLeagueCatalog(**values)


def test_discovered_leagues_extend_static_catalog_without_hiding_fallback_leagues():
    catalog = merge_football_catalog(CATALOG, [_discovered()])
    australia = next(country for country in catalog if country.country == "Australia")

    assert {league.scrape_slug for league in australia.leagues} == {"australia-a-league", "australia-npl-victoria"}
    added = next(league for league in australia.leagues if league.scrape_slug == "australia-npl-victoria")
    assert added.source == "discovered"
    assert added.source_url == "https://www.oddsportal.com/football/australia/npl-victoria/"


def test_discovered_row_overrides_static_row_with_status_metadata():
    catalog = merge_football_catalog(
        CATALOG,
        [_discovered(scrape_slug="australia-a-league", league_name="A-League Men", status="unavailable")],
    )
    australia = next(country for country in catalog if country.country == "Australia")

    assert len(australia.leagues) == 1
    assert australia.leagues[0].name == "A-League Men"
    assert australia.leagues[0].source == "discovered"
    assert australia.leagues[0].status == "unavailable"


def test_pending_discovery_does_not_hide_a_static_cli_supported_league():
    catalog = merge_football_catalog(
        CATALOG,
        [
            _discovered(
                scrape_slug="australia-a-league",
                league_name="A-League Men",
                status="validation_pending",
            ),
            _discovered(
                scrape_slug="australia-npl-victoria",
                status="available",
            ),
        ],
    )
    australia = next(country for country in catalog if country.country == "Australia")
    by_slug = {league.scrape_slug: league for league in australia.leagues}

    assert by_slug["australia-a-league"].source == "static"
    assert by_slug["australia-a-league"].status == "available"
    assert by_slug["australia-npl-victoria"].source == "discovered"
    assert by_slug["australia-npl-victoria"].status == "available"


def test_refresh_payload_rejects_non_oddsportal_or_mismatched_urls():
    with pytest.raises(ValidationError, match="source_url"):
        FootballCatalogRefreshRequest.model_validate(
            {
                "leagues": [
                    {
                        "scrape_slug": "australia-npl-victoria",
                        "country_slug": "australia",
                        "country_name": "Australia",
                        "league_name": "NPL Victoria",
                        "source_url": "https://example.com/football/australia/npl-victoria/",
                    }
                ]
            }
        )
