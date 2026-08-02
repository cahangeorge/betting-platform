import hashlib
import json
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, ProviderIngestionCheckpoint, ProviderObservation, ScrapedDataset
from app.providers import (
    DEFAULT_PROVIDER_REGISTRY,
    ProductionPolicy,
    ProviderCapability,
    ProviderRegistry,
    ProviderSourceDescriptor,
)
from app.providers.soccerdata import SoccerdataCacheMode, SoccerdataIngestionSpec, SoccerdataJobMode
from app.services.soccerdata_ingestion import (
    SoccerdataIngestionError,
    fetch_soccerdata_batch,
    ingest_soccerdata,
    replay_soccerdata_batch,
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


@pytest.fixture
def registry():
    source = ProviderSourceDescriptor(
        adapter_key="soccerdata",
        source_key="espn",
        capabilities=frozenset({ProviderCapability.FIXTURES, ProviderCapability.RESULTS}),
        production_policy=ProductionPolicy.ALLOWED,
        body_retention_days=1,
    )
    return ProviderRegistry((DEFAULT_PROVIDER_REGISTRY.get("soccerdata"),), (source,))


def spec():
    return SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition="ENG-Premier League",
        season="2025-2026",
        mode=SoccerdataJobMode.INCREMENTAL,
    )


NOW = datetime(2026, 8, 1, 12, 5, tzinfo=UTC)


def bridge_result(*, records, complete=True, cursor=None):
    return {
        "rows": records,
        "summary": {
            "cache": {
                "mode": "cold",
                "as_of": "2026-08-01T12:00:00Z",
                "cache_hits": 0,
                "upstream_requests": 1,
                "artifact_digest": "a" * 64,
            },
            "coverage_complete": complete,
        },
        "cursor": cursor,
    }


def generation_key(current_spec, artifact_digest="a" * 64):
    encoded = json.dumps(
        [current_spec.group_fingerprint, artifact_digest],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


@pytest.mark.asyncio
async def test_ingestion_persists_normalized_v2_observations_and_publishes_nonempty_dataset(session, registry):
    calls = 0

    async def bridge(payload):
        nonlocal calls
        calls += 1
        assert payload["operation"] == "espn_schedule"
        return bridge_result(
            records=[
                {
                    "source_id": "event-1",
                    "observed_at": "2026-08-01T12:00:00Z",
                    "payload": {"home_team": "A", "away_team": "B"},
                }
            ]
        )

    first = await ingest_soccerdata(
        session,
        spec(),
        bridge=bridge,
        registry=registry,
        run_id="run-1",
        require_identity_mappings=False,
        now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
    )
    second = await ingest_soccerdata(
        session,
        spec(),
        bridge=bridge,
        registry=registry,
        run_id="run-2",
        require_identity_mappings=False,
        now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
    )
    await session.commit()

    observation = await session.scalar(select(ProviderObservation))
    dataset = await session.scalar(select(ScrapedDataset))
    assert (first.state, first.record_count, first.observation_count) == ("completed", 1, 1)
    assert (second.replayed, second.dataset_id, calls) == (True, first.dataset_id, 1)
    assert first.generation_id is not None
    assert second.generation_id == first.generation_id
    assert observation.envelope_version == "2.0"
    assert observation.capability == "fixtures"
    assert dataset.publication_state == "published"
    assert dataset.matches_count == 1


@pytest.mark.asyncio
async def test_no_data_is_terminal_without_publishing_an_empty_dataset(session, registry):
    async def bridge(_payload):
        return bridge_result(records=[])

    result = await ingest_soccerdata(
        session, spec(), bridge=bridge, registry=registry, require_identity_mappings=False, now=NOW
    )
    await session.commit()

    checkpoint = await session.scalar(select(ProviderIngestionCheckpoint))
    assert (result.state, result.dataset_id, result.observation_count) == ("no_data", None, 0)
    assert result.generation_id is not None
    assert checkpoint.state == "no_data"
    assert await session.scalar(select(func.count()).select_from(ScrapedDataset)) == 0


@pytest.mark.asyncio
async def test_fresh_no_data_checkpoint_replays_without_recalling_the_bridge(session, registry):
    calls = 0

    async def bridge(_payload):
        nonlocal calls
        calls += 1
        return bridge_result(records=[])

    first = await ingest_soccerdata(
        session,
        spec(),
        bridge=bridge,
        registry=registry,
        require_identity_mappings=False,
        now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
    )
    replay = await ingest_soccerdata(
        session,
        spec(),
        bridge=bridge,
        registry=registry,
        require_identity_mappings=False,
        now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
    )

    assert (first.state, replay.state, replay.replayed, calls) == ("no_data", "no_data", True, 1)
    assert replay.generation_id == first.generation_id


@pytest.mark.asyncio
async def test_superseded_warm_checkpoint_is_not_replayed_as_the_current_generation(session, registry):
    warm = spec()
    refresh = SoccerdataIngestionSpec(
        operation=warm.operation,
        competition=warm.competition,
        season=warm.season,
        mode=warm.mode,
        cache_mode=SoccerdataCacheMode.REFRESH,
    )

    async def warm_bridge(_payload):
        return bridge_result(
            records=[
                {
                    "source_id": "event-warm",
                    "observed_at": "2026-08-01T12:00:00Z",
                    "payload": {"home_team": "A", "away_team": "B"},
                }
            ]
        )

    async def refresh_bridge(_payload):
        result = bridge_result(
            records=[
                {
                    "source_id": "event-refresh",
                    "observed_at": "2026-08-01T12:10:00Z",
                    "payload": {"home_team": "C", "away_team": "D"},
                }
            ]
        )
        result["summary"]["cache"]["as_of"] = "2026-08-01T12:10:00Z"
        result["summary"]["cache"]["artifact_digest"] = "b" * 64
        return result

    await ingest_soccerdata(
        session,
        warm,
        bridge=warm_bridge,
        registry=registry,
        run_id="warm",
        require_identity_mappings=False,
        now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
    )
    await session.commit()
    await ingest_soccerdata(
        session,
        refresh,
        bridge=refresh_bridge,
        registry=registry,
        run_id="refresh",
        require_identity_mappings=False,
        now=datetime(2026, 8, 1, 12, 12, tzinfo=UTC),
    )
    await session.commit()

    assert await replay_soccerdata_batch(session, warm, now=datetime(2026, 8, 1, 12, 12, tzinfo=UTC)) is None


@pytest.mark.asyncio
async def test_invalid_cache_telemetry_marks_checkpoint_failed_and_never_persists_data(session, registry):
    async def bridge(_payload):
        response = bridge_result(records=[])
        response["summary"]["cache"] = {
            "mode": "warm",
            "as_of": "2026-08-01T12:00:00Z",
            "cache_hits": 1,
            "upstream_requests": 1,
            "artifact_digest": "a" * 64,
        }
        return response

    with pytest.raises(SoccerdataIngestionError, match="warm cache"):
        await ingest_soccerdata(session, spec(), bridge=bridge, registry=registry)

    checkpoint = await session.scalar(select(ProviderIngestionCheckpoint))
    assert checkpoint.state == "failed"
    assert await session.scalar(select(func.count()).select_from(ProviderObservation)) == 0


@pytest.mark.asyncio
async def test_failed_partition_is_reclaimed_and_resumed_from_its_checkpoint(session, registry):
    async def invalid_bridge(_payload):
        return {"rows": [], "summary": {"cache": {"mode": "cold"}, "coverage_complete": True}}

    with pytest.raises(SoccerdataIngestionError):
        await ingest_soccerdata(
            session,
            spec(),
            bridge=invalid_bridge,
            registry=registry,
            run_id="first",
            require_identity_mappings=False,
            now=NOW,
        )
    await session.commit()

    async def valid_bridge(_payload):
        return bridge_result(records=[])

    result = await ingest_soccerdata(
        session,
        spec(),
        bridge=valid_bridge,
        registry=registry,
        run_id="second",
        require_identity_mappings=False,
        now=NOW,
    )
    checkpoint = await session.scalar(select(ProviderIngestionCheckpoint))
    assert (result.state, checkpoint.attempt, checkpoint.run_id_snapshot) == ("no_data", 2, "second")


@pytest.mark.asyncio
async def test_results_and_statistics_payload_schemas_are_accepted_by_the_registered_observation_validator(
    session, registry
):
    fixtures = [
        (
            "matchhistory_results_backfill",
            SoccerdataJobMode.BACKFILL,
            "football-data-co-uk",
            ProviderCapability.RESULTS,
        ),
        ("understat_team_stats_backfill", SoccerdataJobMode.BACKFILL, "understat", ProviderCapability.STATISTICS),
    ]
    sources = [
        ProviderSourceDescriptor(
            "soccerdata", source, frozenset({capability}), ProductionPolicy.ALLOWED, body_retention_days=1
        )
        for _, _, source, capability in fixtures
    ]
    allowed = ProviderRegistry((DEFAULT_PROVIDER_REGISTRY.get("soccerdata"),), tuple(sources))
    for operation, mode, _source, _capability in fixtures:
        season = "2023-2024" if operation == "matchhistory_results_backfill" else "2024"
        current = SoccerdataIngestionSpec(operation=operation, competition="ENG", season=season, mode=mode)

        async def bridge(_payload):
            return bridge_result(
                records=[{"source_id": operation, "observed_at": "2026-08-01T12:00:00Z", "payload": {"value": 1}}]
            )

        result = await ingest_soccerdata(
            session, current, bridge=bridge, registry=allowed, require_identity_mappings=False, now=NOW
        )
        assert result.state == "completed"
        await session.commit()


@pytest.mark.asyncio
async def test_raw_espn_game_id_row_becomes_a_stable_provider_source_identity(session, registry):
    raw_game_id = 401729018

    async def bridge(_payload):
        return bridge_result(
            records=[
                {
                    "league": "ENG-Premier League",
                    "season": "2025-2026",
                    "game": "Arsenal vs Chelsea",
                    "date": "2026-08-01T11:00:00Z",
                    "homeTeam": "Arsenal",
                    "awayTeam": "Chelsea",
                    "gameId": raw_game_id,
                    "leagueId": "eng.1",
                }
            ]
        )

    result = await ingest_soccerdata(
        session, spec(), bridge=bridge, registry=registry, require_identity_mappings=False, now=NOW
    )
    observation = await session.scalar(select(ProviderObservation))

    assert result.state == "completed"
    assert observation is not None
    assert observation.source_id == f"event:{raw_game_id}"


@pytest.mark.asyncio
async def test_identity_mapping_requirement_prevents_dataset_publication(session, registry):
    async def bridge(_payload):
        return bridge_result(
            records=[
                {
                    "gameId": 401729018,
                    "game": "Arsenal vs Chelsea",
                    "date": "2026-08-01T11:00:00Z",
                    "homeTeam": "Arsenal",
                    "awayTeam": "Chelsea",
                }
            ]
        )

    with pytest.raises(SoccerdataIngestionError, match="accepted current match identity mapping"):
        await ingest_soccerdata(session, spec(), bridge=bridge, registry=registry, now=NOW)

    checkpoint = await session.scalar(select(ProviderIngestionCheckpoint))
    assert checkpoint is not None
    assert checkpoint.state == "failed"
    assert await session.scalar(select(func.count()).select_from(ScrapedDataset)) == 0


@pytest.mark.asyncio
async def test_stale_checkpoint_reuses_a_matching_dataset_without_duplicate_persistence(session, registry):
    calls = 0

    async def bridge(_payload):
        nonlocal calls
        calls += 1
        response = bridge_result(records=[{"gameId": 401729018, "payload": {"home_team": "A", "away_team": "B"}}])
        response["summary"]["cache"]["as_of"] = "2026-08-01T12:00:00Z" if calls == 1 else "2026-08-01T12:20:00Z"
        return response

    stale_now = datetime(2026, 8, 1, 12, 5, tzinfo=UTC)
    refreshed_now = datetime(2026, 8, 1, 12, 20, tzinfo=UTC)
    first = await ingest_soccerdata(
        session,
        spec(),
        bridge=bridge,
        registry=registry,
        require_identity_mappings=False,
        now=stale_now,
    )
    await session.commit()
    second = await ingest_soccerdata(
        session,
        spec(),
        bridge=bridge,
        registry=registry,
        require_identity_mappings=False,
        now=refreshed_now,
    )
    await session.commit()

    assert (first.replayed, second.replayed, calls) == (False, False, 2)
    assert await session.scalar(select(func.count()).select_from(ScrapedDataset)) == 1
    assert await session.scalar(select(func.count()).select_from(ProviderObservation)) == 1


@pytest.mark.asyncio
async def test_pages_remain_staged_until_terminal_cursor_then_publish_as_one_group(session, registry):
    first_spec = SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition="ENG-Premier League",
        season="2025-2026",
        mode=SoccerdataJobMode.INCREMENTAL,
        limit=2,
        chunk_size=1,
    )

    async def first_bridge(_payload):
        return bridge_result(
            records=[{"gameId": 1, "payload": {"home_team": "A", "away_team": "B"}}],
            cursor={"page": 1, "start_cursor": 1},
        )

    async def second_bridge(_payload):
        return bridge_result(records=[{"gameId": 2, "payload": {"home_team": "C", "away_team": "D"}}])

    first = await ingest_soccerdata(
        session,
        first_spec,
        bridge=first_bridge,
        registry=registry,
        require_identity_mappings=False,
        now=NOW,
    )
    expected_generation = generation_key(first_spec)
    assert first.cursor == {"page": 1, "start_cursor": 1, "generation_key": expected_generation}
    assert (await session.get(ScrapedDataset, first.dataset_id)).publication_state == "staged"
    # A continuation fetch must start after the prior page's checkpoint is
    # durable.  This is also the boundary that lets the helper close its own
    # replay SELECT transaction before crossing the bridge boundary.
    await session.commit()
    replay = await replay_soccerdata_batch(session, first_spec, now=NOW)
    assert replay is not None and replay.replayed is True
    assert replay.generation_id == first.generation_id
    await session.rollback()

    second_spec = SoccerdataIngestionSpec.from_config(
        {
            **first_spec.to_config(),
            "page": 1,
            "start_cursor": 1,
            "generation_key": expected_generation,
        }
    )

    second = await ingest_soccerdata(
        session,
        second_spec,
        bridge=second_bridge,
        registry=registry,
        require_identity_mappings=False,
        now=NOW,
    )
    datasets = (await session.scalars(select(ScrapedDataset).order_by(ScrapedDataset.id))).all()

    assert second.cursor is None
    assert len(datasets) == 2
    assert {dataset.dataset_group_key for dataset in datasets} == {first_spec.group_fingerprint}
    assert {dataset.publication_state for dataset in datasets} == {"published"}


@pytest.mark.asyncio
async def test_replay_miss_preserves_caller_transaction_and_fails_before_external_fetch(session, registry):
    first_spec = SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition="ENG-Premier League",
        season="2025-2026",
        mode=SoccerdataJobMode.INCREMENTAL,
        limit=2,
        chunk_size=1,
    )

    async def first_bridge(_payload):
        return bridge_result(
            records=[{"gameId": 1, "payload": {"home_team": "A", "away_team": "B"}}],
            cursor={"page": 1, "start_cursor": 1},
        )

    first = await ingest_soccerdata(
        session,
        first_spec,
        bridge=first_bridge,
        registry=registry,
        require_identity_mappings=False,
        now=NOW,
    )
    continuation_spec = SoccerdataIngestionSpec.from_config(
        {
            **first_spec.to_config(),
            "page": 1,
            "start_cursor": 1,
            "generation_key": generation_key(first_spec),
        }
    )

    bridge_called = False

    async def continuation_bridge(_payload):
        nonlocal bridge_called
        bridge_called = True
        return bridge_result(records=[{"gameId": 2, "payload": {"home_team": "C", "away_team": "D"}}])

    with pytest.raises(SoccerdataIngestionError, match="external soccerdata fetch requires a clean session"):
        await ingest_soccerdata(
            session,
            continuation_spec,
            bridge=continuation_bridge,
            registry=registry,
            require_identity_mappings=False,
            now=NOW,
        )

    # The helper neither crosses the external boundary nor commits/rolls back
    # the caller's staged work. Transaction ownership remains with the caller.
    assert bridge_called is False
    assert session.in_transaction()
    dataset = await session.get(ScrapedDataset, first.dataset_id)
    assert dataset is not None and dataset.publication_state == "staged"


@pytest.mark.asyncio
async def test_prefetched_batch_persists_inside_caller_transaction_without_ending_it(session, registry):
    current_spec = spec()

    async def bridge(_payload):
        return bridge_result(records=[])

    batch = await fetch_soccerdata_batch(current_spec, bridge)
    assert not session.in_transaction()
    await session.scalar(select(func.count()).select_from(ScrapedDataset))
    assert session.in_transaction()

    result = await ingest_soccerdata(
        session,
        current_spec,
        batch=batch,
        registry=registry,
        require_identity_mappings=False,
        now=NOW,
    )

    assert result.state == "no_data"
    assert session.in_transaction()


@pytest.mark.asyncio
async def test_terminal_page_cannot_publish_when_an_earlier_page_is_missing(session, registry):
    terminal_spec = SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition="ENG-Premier League",
        season="2025-2026",
        mode=SoccerdataJobMode.INCREMENTAL,
        limit=2,
        chunk_size=1,
        page=1,
        start_cursor=1,
        generation_key=generation_key(
            SoccerdataIngestionSpec(
                operation="espn_schedule_incremental",
                competition="ENG-Premier League",
                season="2025-2026",
                mode=SoccerdataJobMode.INCREMENTAL,
                limit=2,
                chunk_size=1,
            )
        ),
    )

    async def terminal_bridge(_payload):
        return bridge_result(records=[{"gameId": 2, "payload": {"home_team": "C", "away_team": "D"}}])

    with pytest.raises(SoccerdataIngestionError, match="incomplete staged page group"):
        await ingest_soccerdata(
            session,
            terminal_spec,
            bridge=terminal_bridge,
            registry=registry,
            require_identity_mappings=False,
            now=NOW,
        )

    dataset = await session.scalar(select(ScrapedDataset))
    checkpoint = await session.scalar(select(ProviderIngestionCheckpoint))
    assert dataset.publication_state == "staged"
    assert checkpoint.state == "failed"


@pytest.mark.asyncio
async def test_expired_or_future_cache_attestation_is_rejected(session, registry):
    async def expired(_payload):
        return bridge_result(records=[])

    with pytest.raises(SoccerdataIngestionError, match="already expired"):
        await ingest_soccerdata(
            session,
            spec(),
            bridge=expired,
            registry=registry,
            require_identity_mappings=False,
            now=datetime(2026, 8, 1, 12, 16, tzinfo=UTC),
        )
    await session.rollback()

    async def future(_payload):
        response = bridge_result(records=[])
        response["summary"]["cache"]["as_of"] = "2026-08-01T12:11:00Z"
        return response

    with pytest.raises(SoccerdataIngestionError, match="future skew"):
        await ingest_soccerdata(
            session,
            spec(),
            bridge=future,
            registry=registry,
            require_identity_mappings=False,
            now=NOW,
        )
