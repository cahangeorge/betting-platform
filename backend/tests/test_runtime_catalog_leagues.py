import json
from types import SimpleNamespace

import pytest

from app.models.football_catalog import FootballLeagueCatalog
from app.services.scraper import _effective_oddsharvester_timeout, _runtime_catalog_league_env


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarResult(self._rows)


class _DB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _statement):
        return _Result(self.rows)


def _row(slug: str = "argentina-primera-c") -> FootballLeagueCatalog:
    league_slug = slug.removeprefix("argentina-")
    return FootballLeagueCatalog(
        scrape_slug=slug,
        country_slug="argentina",
        country_name="Argentina",
        league_name="Primera C",
        source_url=f"https://www.oddsportal.com/football/argentina/{league_slug}/",
        status="available",
    )


@pytest.mark.asyncio
async def test_upcoming_scrape_receives_only_runtime_validated_catalog_urls():
    job = SimpleNamespace(
        league=None,
        params={"sport": "football", "command": "upcoming", "leagues": ["argentina-primera-c"]},
    )

    resolution = await _runtime_catalog_league_env(_DB([_row()]), job)

    assert json.loads(resolution.env["ODDSHARVESTER_RUNTIME_FOOTBALL_LEAGUES"]) == {
        "argentina-primera-c": "https://www.oddsportal.com/football/argentina/primera-c/"
    }


@pytest.mark.asyncio
async def test_historic_scrape_validates_the_exact_season_and_passes_the_rendered_url(monkeypatch):
    job = SimpleNamespace(
        league=None,
        params={"sport": "football", "command": "historic", "leagues": ["argentina-primera-c"]},
    )

    job.params["season"] = "2023-2024"

    async def fake_validate(candidates, *, timeout=None, season=None):
        assert candidates[0]["scrape_slug"] == "argentina-primera-c"
        assert season == "2023-2024"
        return [
            {
                "scrape_slug": "argentina-primera-c",
                "status": "available",
                "historic_url": "https://www.oddsportal.com/football/argentina/primera-c-2023/results/",
            }
        ]

    monkeypatch.setattr("app.services.scraper.validate_oddsharvester_football_catalog", fake_validate)
    resolution = await _runtime_catalog_league_env(_DB([_row()]), job)

    assert json.loads(resolution.env["ODDSHARVESTER_RUNTIME_FOOTBALL_HISTORIC_URLS"]) == {
        "argentina-primera-c": {
            "2023-2024": "https://www.oddsportal.com/football/argentina/primera-c-2023/results/"
        }
    }
    assert resolution.league_override == ["argentina-primera-c"]


@pytest.mark.asyncio
async def test_historic_scrape_skips_only_dynamic_leagues_without_a_validated_season(monkeypatch):
    job = SimpleNamespace(
        league=None,
        params={
            "sport": "football",
            "command": "historic",
            "season": "2025-2026",
            "leagues": ["argentina-primera-c", "argentina-liga-profesional"],
        },
    )

    async def fake_validate(_candidates, *, timeout=None, season=None):
        return [
            {
                "scrape_slug": "argentina-primera-c",
                "status": "available",
                "historic_url": "https://www.oddsportal.com/football/argentina/primera-c-2025/results/",
            },
            {"scrape_slug": "argentina-liga-profesional", "status": "unavailable"},
        ]

    monkeypatch.setattr("app.services.scraper.validate_oddsharvester_football_catalog", fake_validate)
    resolution = await _runtime_catalog_league_env(
        _DB([_row(), _row("argentina-liga-profesional")]), job
    )

    assert resolution.league_override == ["argentina-primera-c"]
    assert resolution.skipped_historic_leagues == ["argentina-liga-profesional"]


def test_multi_league_historic_timeout_scales_above_the_generic_bridge_default():
    job = SimpleNamespace(params={"command": "historic"})

    assert _effective_oddsharvester_timeout(job, 5) == 2100
    assert _effective_oddsharvester_timeout(job, 6) == 2400
