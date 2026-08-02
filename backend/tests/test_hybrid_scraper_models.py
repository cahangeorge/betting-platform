from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models.scrape import ScraperRecipe, ScraperValidationCache
from app.services.scraper import SUPPORTED_SCRAPER_ENGINES, VALIDATION_CACHE_TTL


def test_hybrid_scraper_settings_and_contracts_are_bounded():
    assert Settings(_env_file=None, scrape_pipeline_v2_percent=100).scrape_pipeline_v2_percent == 100
    with pytest.raises(ValidationError):
        Settings(_env_file=None, scrape_pipeline_v2_percent=101)
    assert "camoufox" in SUPPORTED_SCRAPER_ENGINES
    assert VALIDATION_CACHE_TTL.total_seconds() == 24 * 60 * 60


def test_scraper_metadata_models_keep_only_explicit_recipe_and_validation_fields():
    now = datetime.now(timezone.utc)
    cache = ScraperValidationCache(
        scrape_slug="england-premier-league",
        season="2024-2025",
        status="available",
        historic_url="https://www.oddsportal.com/football/england/premier-league-2024/results/",
        validated_at=now,
        expires_at=now + VALIDATION_CACHE_TTL,
    )
    recipe = ScraperRecipe(
        recipe_key="oddsportal:football:results",
        engine="playwright",
        status="candidate",
        recipe={"endpoint": "/x/fixtures", "selectors": {"row": ".event"}},
    )
    assert cache.historic_url and cache.season == "2024-2025"
    assert recipe.status == "candidate"


def test_scraper_recipe_sanitizer_rejects_sensitive_browser_state():
    from app.services.scraper import sanitize_scraper_recipe

    assert sanitize_scraper_recipe({"endpoint": "/api", "headers": {"accept": "application/json"}}) == {
        "endpoint": "/api",
        "headers": {"accept": "application/json"},
    }
    with pytest.raises(ValueError, match="must not contain"):
        sanitize_scraper_recipe({"cookies": {"session": "secret"}})
    with pytest.raises(ValueError, match="must not contain"):
        sanitize_scraper_recipe({"request": {"authorization": "Bearer secret"}})
    for endpoint in (
        "https://user:secret@www.oddsportal.com/api",
        "https://www.oddsportal.com:8443/api",
        "https://www.oddsportal.com/api?token=value",
        "https://www.oddsportal.com/api#fragment",
        "/api?token=value",
    ):
        with pytest.raises(ValueError, match="endpoint"):
            sanitize_scraper_recipe({"endpoint": endpoint})


def test_scraper_recipe_sanitizer_bounds_total_shape():
    from app.services.scraper import MAX_RECIPE_BYTES, MAX_RECIPE_DEPTH, sanitize_scraper_recipe

    nested = {}
    cursor = nested
    for _ in range(MAX_RECIPE_DEPTH + 1):
        cursor["next"] = {}
        cursor = cursor["next"]
    with pytest.raises(ValueError, match="nesting"):
        sanitize_scraper_recipe(nested)
    with pytest.raises(ValueError, match="bytes"):
        sanitize_scraper_recipe({"selector": "x" * MAX_RECIPE_BYTES})


@pytest.mark.asyncio
async def test_create_recipe_sanitizes_and_preserves_lineage():
    from app.services.scraper import approve_scraper_recipe, create_scraper_recipe, retire_scraper_recipe

    class _DB:
        def __init__(self):
            self.added = []

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            return None

        async def execute(self, _statement):
            class _Scalars:
                def all(self):
                    return []

            class _Result:
                def scalars(self):
                    return _Scalars()

            return _Result()

    db = _DB()
    recipe = await create_scraper_recipe(
        db,
        recipe_key="oddsportal:fixtures",
        engine="playwright",
        recipe={"endpoint": "/api/fixtures", "method": "GET", "headers": {"accept": "application/json"}},
    )
    assert recipe.schema_version == "1.0"
    assert recipe.status == "candidate"
    verified_at = datetime.now(timezone.utc)
    await approve_scraper_recipe(db, recipe, approved_by="operator@example.test", verified_at=verified_at)
    assert recipe.status == "active"
    assert recipe.verified_at == verified_at
    assert recipe.approved_by == "operator@example.test"
    await retire_scraper_recipe(db, recipe)
    assert recipe.status == "disabled"
    assert recipe.retired_at is not None
    with pytest.raises(ValueError, match="OddsPortal"):
        await create_scraper_recipe(
            _DB(), recipe_key="bad", engine="playwright", recipe={"endpoint": "https://evil.test/"}
        )


def test_recipe_headers_are_strictly_allowlisted():
    from app.services.scraper import sanitize_scraper_recipe

    assert sanitize_scraper_recipe({"endpoint": "/api", "headers": {"accept": "application/json"}})["headers"] == {
        "accept": "application/json"
    }
    for headers in ({"x-api-key": "opaque"}, {"x-client": "opaque"}, {"authorization": "Bearer opaque"}):
        with pytest.raises(ValueError):
            sanitize_scraper_recipe({"endpoint": "/api", "headers": headers})


@pytest.mark.asyncio
async def test_approving_candidate_retires_existing_active_recipe():
    from app.services.scraper import approve_scraper_recipe

    active = ScraperRecipe(id=1, recipe_key="key", engine="playwright", schema_version="1", status="active", recipe={})
    candidate = ScraperRecipe(
        id=2, recipe_key="key", engine="playwright", schema_version="2", status="candidate", recipe={}
    )

    class _Scalars:
        def all(self):
            return [active]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _DB:
        async def execute(self, _statement):
            return _Result()

        async def flush(self):
            return None

    await approve_scraper_recipe(_DB(), candidate, approved_by="operator", verified_at=datetime.now(timezone.utc))
    assert candidate.status == "active"
    assert active.status == "disabled"
    assert active.retired_at is not None
