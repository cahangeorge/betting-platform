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
        assert timeout == 900
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
        "argentina-primera-c": {"2023-2024": "https://www.oddsportal.com/football/argentina/primera-c-2023/results/"}
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
    resolution = await _runtime_catalog_league_env(_DB([_row(), _row("argentina-liga-profesional")]), job)

    assert resolution.league_override == ["argentina-primera-c"]
    assert resolution.skipped_historic_leagues == ["argentina-liga-profesional"]


def test_multi_league_historic_timeout_scales_above_the_generic_bridge_default():
    job = SimpleNamespace(params={"command": "historic"})

    assert _effective_oddsharvester_timeout(job, 5) == 2100
    assert _effective_oddsharvester_timeout(job, 6) == 2400


def test_multi_league_upcoming_timeout_scales_without_exceeding_the_hard_limit():
    job = SimpleNamespace(params={"command": "upcoming"})

    assert _effective_oddsharvester_timeout(job, 1) is None
    assert _effective_oddsharvester_timeout(job, 5) == 1050
    assert _effective_oddsharvester_timeout(job, 50) == 3600


class _CacheDB:
    def __init__(self, catalog_rows, cache_rows):
        self.catalog_rows = catalog_rows
        self.cache_rows = cache_rows
        self.added = []
        self.calls = 0

    def add(self, row):
        self.added.append(row)

    async def execute(self, _statement):
        self.calls += 1
        return _Result(self.catalog_rows if self.calls == 1 else self.cache_rows)


@pytest.mark.asyncio
async def test_historic_validation_reuses_fresh_database_cache(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.models.scrape import ScraperValidationCache

    job = SimpleNamespace(
        league=None,
        params={"sport": "football", "command": "historic", "season": "2024-2025", "leagues": ["argentina-primera-c"]},
    )
    cached = ScraperValidationCache(
        scrape_slug="argentina-primera-c",
        season="2024-2025",
        status="available",
        historic_url="https://www.oddsportal.com/football/argentina/primera-c-2024/results/",
        validated_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=23),
    )

    async def fail_validator(*_args, **_kwargs):
        raise AssertionError("fresh validation cache must bypass the browser validator")

    monkeypatch.setattr("app.services.scraper.validate_oddsharvester_football_catalog", fail_validator)
    resolution = await _runtime_catalog_league_env(_CacheDB([_row()], [cached]), job)

    assert resolution.league_override == ["argentina-primera-c"]
    assert json.loads(resolution.env["ODDSHARVESTER_RUNTIME_FOOTBALL_HISTORIC_URLS"]) == {
        "argentina-primera-c": {"2024-2025": cached.historic_url}
    }


@pytest.mark.asyncio
async def test_historic_validation_refreshes_expired_cache_row_without_duplicate(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.models.scrape import ScraperValidationCache

    job = SimpleNamespace(
        league=None,
        params={"sport": "football", "command": "historic", "season": "2024-2025", "leagues": ["argentina-primera-c"]},
    )
    expired = ScraperValidationCache(
        scrape_slug="argentina-primera-c",
        season="2024-2025",
        status="unavailable",
        historic_url=None,
        validated_at=datetime.now(timezone.utc) - timedelta(days=2),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    async def validator(*_args, **_kwargs):
        return [
            {
                "scrape_slug": "argentina-primera-c",
                "status": "available",
                "historic_url": "https://example.test/results/",
            }
        ]

    monkeypatch.setattr("app.services.scraper.validate_oddsharvester_football_catalog", validator)
    db = _CacheDB([_row()], [expired])
    resolution = await _runtime_catalog_league_env(db, job)

    assert db.added == []
    assert expired.status == "available"
    assert expired.historic_url == "https://example.test/results/"
    assert expired.expires_at > datetime.now(timezone.utc)
    assert resolution.league_override == ["argentina-primera-c"]
