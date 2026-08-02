from datetime import UTC, datetime

import pytest

from app.providers.contracts import ProductionPolicy, ProviderCapability
from app.providers.registry import DEFAULT_PROVIDER_REGISTRY, ProviderPolicyError, capability_for_operation
from app.providers.soccerdata import (
    SOCCERDATA_JOB_SPEC_VERSION,
    SOCCERDATA_OPERATIONS,
    SoccerdataCacheMode,
    SoccerdataIngestionSpec,
    SoccerdataJobMode,
)


def test_primary_sources_and_operations_are_explicit_and_fail_closed():
    expected = {
        "football-data-co-uk": {ProviderCapability.RESULTS},
        "espn": {ProviderCapability.FIXTURES, ProviderCapability.RESULTS},
        "fbref": {
            ProviderCapability.FIXTURES,
            ProviderCapability.RESULTS,
            ProviderCapability.STATISTICS,
            ProviderCapability.LINEUPS,
        },
        "understat": {
            ProviderCapability.FIXTURES,
            ProviderCapability.RESULTS,
            ProviderCapability.STATISTICS,
        },
    }
    for source_key, capabilities in expected.items():
        descriptor = DEFAULT_PROVIDER_REGISTRY.get_source("soccerdata", source_key)
        assert descriptor.production_policy is ProductionPolicy.APPROVAL_REQUIRED
        assert descriptor.capabilities == frozenset(capabilities)

    for operation in SOCCERDATA_OPERATIONS.values():
        assert (
            capability_for_operation(
                operation.key,
                adapter_key="soccerdata",
                source_key=operation.source_key,
            )
            is operation.capability
        )
        with pytest.raises(ProviderPolicyError, match="approved rights and retention record"):
            DEFAULT_PROVIDER_REGISTRY.require_operation("soccerdata", operation.source_key, operation.key)


@pytest.mark.parametrize(
    ("operation", "mode", "task_type"),
    [
        ("matchhistory_results_backfill", "backfill", "soccerdata_http_ingest"),
        ("espn_schedule_incremental", "incremental", "soccerdata_http_ingest"),
        ("fbref_schedule_backfill", "backfill", "soccerdata_browser_ingest"),
        ("fbref_team_stats_backfill", "backfill", "soccerdata_browser_ingest"),
        ("understat_schedule_backfill", "backfill", "soccerdata_http_ingest"),
        ("understat_team_stats_backfill", "backfill", "soccerdata_http_ingest"),
    ],
)
def test_job_specs_map_source_transport_to_the_correct_worker_lane(operation, mode, task_type):
    spec = SoccerdataIngestionSpec(
        operation=operation,
        competition="ENG-Premier League",
        season="2024-2025",
        mode=mode,
    )

    assert spec.task_type == task_type
    assert spec.bridge_payload()["operation"] == SOCCERDATA_OPERATIONS[operation].bridge_operation


def test_job_spec_fingerprint_is_stable_across_cache_execution_modes():
    common = {
        "operation": "espn_schedule_incremental",
        "competition": "ENG-Premier League",
        "season": "2025-2026",
        "mode": SoccerdataJobMode.INCREMENTAL,
        "limit": 500,
        "chunk_size": 50,
    }

    cold = SoccerdataIngestionSpec(**common, cache_mode=SoccerdataCacheMode.REFRESH)
    warm = SoccerdataIngestionSpec(**common, cache_mode=SoccerdataCacheMode.WARM)

    assert cold.request_fingerprint == warm.request_fingerprint
    assert cold.spec_digest != warm.spec_digest
    assert cold.bridge_payload()["refresh"] is True
    assert warm.bridge_payload()["refresh"] is False


def test_continuation_requires_an_internal_generation_and_initial_page_rejects_one():
    common = {
        "operation": "espn_schedule_incremental",
        "competition": "ENG-Premier League",
        "season": "2025-2026",
        "mode": SoccerdataJobMode.INCREMENTAL,
        "limit": 2,
        "chunk_size": 1,
    }
    with pytest.raises(ValueError, match="continuation page requires"):
        SoccerdataIngestionSpec(**common, page=1, start_cursor=1)
    with pytest.raises(ValueError, match="initial page cannot supply"):
        SoccerdataIngestionSpec(**common, generation_key="a" * 64)

    continuation = SoccerdataIngestionSpec(
        **common,
        page=1,
        start_cursor=1,
        generation_key="a" * 64,
    )
    assert continuation.to_config()["generation_key"] == "a" * 64


@pytest.mark.parametrize(
    "config",
    [
        {},
        {
            "operation": "espn_schedule_incremental",
            "competition": "ENG-Premier League",
            "season": "2025-2026",
            "mode": "backfill",
        },
        {
            "operation": "espn_schedule_incremental",
            "competition": "ENG-Premier League",
            "season": "2025-2026",
            "mode": "incremental",
            "limit": 99_999,
        },
        {
            "operation": "espn_schedule_incremental",
            "competition": "ENG-Premier League",
            "season": "2025-2026",
            "mode": "incremental",
            "secret": "forbidden",
        },
    ],
)
def test_job_spec_rejects_missing_mismatched_unbounded_or_unknown_config(config):
    with pytest.raises(ValueError):
        SoccerdataIngestionSpec.from_config(config)


def test_job_spec_round_trips_the_versioned_public_config():
    spec = SoccerdataIngestionSpec.from_config(
        {
            "spec_version": SOCCERDATA_JOB_SPEC_VERSION,
            "operation": "matchhistory_results_backfill",
            "competition": "ENG-Premier League",
            "season": "2024-2025",
            "mode": "backfill",
            "cache_mode": "no-store",
            "limit": 500,
            "chunk_size": 100,
        }
    )

    assert spec.cache_mode is SoccerdataCacheMode.NO_STORE
    assert spec.bridge_payload() == {
        "operation": "matchhistory_games",
        "league": "ENG-Premier League",
        "season": "2024-2025",
        "limit": 500,
        "chunk_size": 100,
        "page": 0,
        "start_cursor": 0,
        "source_key": "football-data-co-uk",
        "requests_per_minute": 10,
        "ttl_seconds": 86_400,
        "refresh": False,
        "no_store": True,
    }


def test_matchhistory_rejects_current_season_but_accepts_completed_history():
    current = datetime(2026, 8, 1, tzinfo=UTC)
    completed = SoccerdataIngestionSpec(
        operation="matchhistory_results_backfill",
        competition="ENG-Premier League",
        season="2025-2026",
        mode="backfill",
    )
    current_season = SoccerdataIngestionSpec(
        operation="matchhistory_results_backfill",
        competition="ENG-Premier League",
        season="2026-2027",
        mode="backfill",
    )

    completed.validate_source_window(now=current)
    with pytest.raises(ValueError, match="completed-season"):
        current_season.validate_source_window(now=current)


def test_penaltyblog_scraper_operations_have_no_implicit_provider_capability_mapping():
    for operation in (
        "scraper_footballdata_fixtures",
        "scraper_fbref_fixtures",
        "scraper_fbref_stats",
        "scraper_understat_fixtures",
        "scraper_understat_shots",
    ):
        with pytest.raises(ValueError, match="Unknown provider operation"):
            capability_for_operation(operation, adapter_key="penaltyblog", source_key="local-model")
