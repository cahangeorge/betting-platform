"""PostgreSQL-only concurrency and fencing gates for soccerdata ingestion.

Run with ``BET_TEST_POSTGRES_URL`` pointing at an isolated database migrated to
Alembic head. The default unit suite skips these tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    ProviderDatasetGeneration,
    ProviderDatasetGenerationPage,
    ProviderIngestionCheckpoint,
    ProviderObservation,
    ProviderObservationDatasetLink,
    ProviderObservationReceipt,
    ProviderObservationSlot,
    ScrapedDataset,
)
from app.providers import (
    DEFAULT_PROVIDER_REGISTRY,
    ProductionPolicy,
    ProviderCapability,
    ProviderRegistry,
    ProviderSourceDescriptor,
)
from app.providers.soccerdata import SoccerdataCacheMode, SoccerdataIngestionSpec, SoccerdataJobMode
from app.services.soccerdata_ingestion import (
    SoccerdataBatch,
    SoccerdataIngestionError,
    ingest_soccerdata,
    persist_soccerdata_batch,
    replay_soccerdata_batch,
)

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL"),
]


def _registry() -> ProviderRegistry:
    source = ProviderSourceDescriptor(
        adapter_key="soccerdata",
        source_key="espn",
        capabilities=frozenset({ProviderCapability.FIXTURES}),
        production_policy=ProductionPolicy.ALLOWED,
        body_retention_days=1,
    )
    return ProviderRegistry((DEFAULT_PROVIDER_REGISTRY.get("soccerdata"),), (source,))


def _spec(competition: str) -> SoccerdataIngestionSpec:
    return SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition=competition,
        season="2025-2026",
        mode=SoccerdataJobMode.INCREMENTAL,
    )


def _batch(
    source_id: str,
    *,
    artifact_digest: str = "a" * 64,
    cache_mode: str = "cold",
    as_of: str = "2026-08-01T12:00:00Z",
) -> SoccerdataBatch:
    return SoccerdataBatch(
        rows=[
            {
                "source_id": source_id,
                "observed_at": datetime(2026, 8, 1, 12, tzinfo=UTC),
                "payload": {"home_team": "A", "away_team": "B"},
            }
        ],
        cache={
            "mode": cache_mode,
            "as_of": as_of,
            "cache_hits": 0,
            "upstream_requests": 1,
            "artifact_digest": artifact_digest,
        },
        coverage_complete=True,
        cursor=None,
    )


def _generation_key(spec: SoccerdataIngestionSpec, artifact_digest: str = "a" * 64) -> str:
    return hashlib.sha256(
        json.dumps([spec.group_fingerprint, artifact_digest], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def _cleanup(sessions, *, competition: str, source_id: str) -> None:
    """Remove only UUID-scoped rows created by this test module."""
    async with sessions() as session, session.begin():
        dataset_ids = list(
            (
                await session.scalars(
                    select(ScrapedDataset.id).where(ScrapedDataset.name.like(f"%:{competition}:2025-2026"))
                )
            ).all()
        )
        group_keys = list(
            (
                await session.scalars(
                    select(ScrapedDataset.dataset_group_key).where(ScrapedDataset.id.in_(dataset_ids))
                )
            ).all()
        )
        generation_ids = list(
            (
                await session.scalars(
                    select(ProviderDatasetGeneration.id).where(
                        ProviderDatasetGeneration.dataset_group_key.in_(group_keys)
                    )
                )
            ).all()
        )
        observation_ids = list(
            (
                await session.scalars(
                    select(ProviderObservation.id).where(ProviderObservation.source_id.like(f"{source_id}%"))
                )
            ).all()
        )
        slot_ids = list(
            (
                await session.scalars(
                    select(ProviderObservation.slot_id).where(ProviderObservation.id.in_(observation_ids))
                )
            ).all()
        )
        if dataset_ids:
            await session.execute(
                delete(ProviderDatasetGenerationPage).where(ProviderDatasetGenerationPage.dataset_id.in_(dataset_ids))
            )
            if generation_ids:
                await session.execute(
                    delete(ProviderDatasetGeneration).where(ProviderDatasetGeneration.id.in_(generation_ids))
                )
            await session.execute(
                delete(ProviderObservationDatasetLink).where(ProviderObservationDatasetLink.dataset_id.in_(dataset_ids))
            )
            await session.execute(delete(ScrapedDataset).where(ScrapedDataset.id.in_(dataset_ids)))
        if observation_ids:
            await session.execute(
                delete(ProviderObservationReceipt).where(ProviderObservationReceipt.observation_id.in_(observation_ids))
            )
            await session.execute(delete(ProviderObservation).where(ProviderObservation.id.in_(observation_ids)))
        if slot_ids:
            await session.execute(delete(ProviderObservationSlot).where(ProviderObservationSlot.id.in_(slot_ids)))
        await session.execute(
            delete(ProviderIngestionCheckpoint).where(
                ProviderIngestionCheckpoint.partition_key.like(f"%:{competition}:%")
            )
        )


async def test_concurrent_same_spec_publishes_one_dataset_and_one_observation() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = str(uuid4())
    competition, source_id = f"g004-{suffix}", f"event:{suffix}"
    current_spec, batch = _spec(competition), _batch(source_id)

    async def persist(run_id: str):
        async with sessions() as session, session.begin():
            return await persist_soccerdata_batch(
                session,
                current_spec,
                batch,
                registry=_registry(),
                run_id=run_id,
                require_identity_mappings=False,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )

    try:
        left, right = await asyncio.wait_for(asyncio.gather(persist("left"), persist("right")), timeout=15)
        async with sessions() as session:
            datasets = await session.scalar(
                select(func.count())
                .select_from(ScrapedDataset)
                .where(ScrapedDataset.name.like(f"%:{competition}:2025-2026"))
            )
            observations = await session.scalar(
                select(func.count()).select_from(ProviderObservation).where(ProviderObservation.source_id == source_id)
            )
            checkpoint = await session.scalar(
                select(ProviderIngestionCheckpoint).where(
                    ProviderIngestionCheckpoint.partition_key.like(f"%:{competition}:%")
                )
            )
        assert sorted(result.replayed for result in (left, right)) == [False, True]
        assert left.generation_id is not None
        assert right.generation_id == left.generation_id
        assert (datasets, observations, checkpoint.state) == (1, 1, "completed")
    finally:
        await _cleanup(sessions, competition=competition, source_id=source_id)
        await engine.dispose()


async def test_ingest_replay_miss_closes_transaction_before_initial_and_continuation_bridge_fetches() -> None:
    """A combined caller may reuse one session across a paginated generation.

    Each helper call first probes the durable replay checkpoint.  PostgreSQL
    starts a transaction for that probe, so both the initial page and the next
    cursor page must enter their bridge calls with no transaction held.
    """
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = str(uuid4())
    competition, source_id = f"g009-{suffix}", f"event:{suffix}"
    initial_spec = replace(_spec(competition), limit=2, chunk_size=1)
    continuation_spec = replace(
        initial_spec,
        page=1,
        start_cursor=initial_spec.chunk_size,
        generation_key=_generation_key(initial_spec, "9" * 64),
    )
    observed_pages: list[int] = []

    async def bridge(payload: dict[str, object]) -> dict[str, object]:
        # This assertion is intentionally inside the external boundary, rather
        # than after the helper returns, so it detects transaction leakage.
        assert not session.in_transaction()
        page = int(payload["page"])
        observed_pages.append(page)
        return {
            "rows": [
                {
                    "source_id": f"{source_id}:{page}",
                    "observed_at": "2026-08-01T12:00:00Z",
                    "payload": {"home_team": "A", "away_team": "B", "page": page},
                }
            ],
            "summary": {
                "cache": {
                    "mode": "cold",
                    "as_of": "2026-08-01T12:00:00Z",
                    "cache_hits": 0,
                    "upstream_requests": 1,
                    "artifact_digest": "9" * 64,
                },
                "coverage_complete": True,
            },
            "cursor": {"page": 1} if page == 0 else None,
        }

    try:
        async with sessions() as session:
            first = await ingest_soccerdata(
                session,
                initial_spec,
                bridge=bridge,
                registry=_registry(),
                run_id="g009-initial",
                require_identity_mappings=False,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )
            # The runner's durable page boundary: a continuation may only
            # replay a checkpoint after the preceding page is committed.
            await session.commit()
            second = await ingest_soccerdata(
                session,
                continuation_spec,
                bridge=bridge,
                registry=_registry(),
                run_id="g009-continuation",
                require_identity_mappings=False,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )
            await session.commit()
        assert (first.state, second.state, observed_pages) == ("completed", "completed", [0, 1])
    finally:
        await _cleanup(sessions, competition=competition, source_id=source_id)
        await engine.dispose()


async def test_stale_fence_rolls_back_then_a_resumed_claim_publishes_once() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = str(uuid4())
    competition, source_id = f"g004-{suffix}", f"event:{suffix}"
    current_spec, batch = _spec(competition), _batch(source_id)

    async def stale_fence() -> None:
        raise SoccerdataIngestionError("stale execution token")

    try:
        async with sessions() as session, session.begin():
            with pytest.raises(SoccerdataIngestionError, match="stale execution token"):
                await persist_soccerdata_batch(
                    session,
                    current_spec,
                    batch,
                    registry=_registry(),
                    run_id="stale-run",
                    fence=stale_fence,
                    require_identity_mappings=False,
                    now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
                )
        async with sessions() as session, session.begin():
            resumed = await persist_soccerdata_batch(
                session,
                current_spec,
                batch,
                registry=_registry(),
                run_id="resume-run",
                require_identity_mappings=False,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )
        async with sessions() as session:
            checkpoint = await session.scalar(
                select(ProviderIngestionCheckpoint).where(
                    ProviderIngestionCheckpoint.partition_key.like(f"%:{competition}:%")
                )
            )
            datasets = await session.scalar(
                select(func.count())
                .select_from(ScrapedDataset)
                .where(ScrapedDataset.name.like(f"%:{competition}:2025-2026"))
            )
        assert (resumed.state, checkpoint.state, checkpoint.attempt, datasets) == ("completed", "completed", 2, 1)
    finally:
        await _cleanup(sessions, competition=competition, source_id=source_id)
        await engine.dispose()


async def test_committed_page_replays_without_fetch_then_terminal_page_publishes_group() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = str(uuid4())
    competition, source_prefix = f"g004-page-{suffix}", f"event:{suffix}"
    first_spec = SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition=competition,
        season="2025-2026",
        mode=SoccerdataJobMode.INCREMENTAL,
        limit=2,
        chunk_size=1,
    )
    expected_generation = _generation_key(first_spec)
    second_spec = SoccerdataIngestionSpec.from_config(
        {
            **first_spec.to_config(),
            "page": 1,
            "start_cursor": 1,
            "generation_key": expected_generation,
        }
    )
    first_batch = _batch(f"{source_prefix}:0")
    first_batch = SoccerdataBatch(
        first_batch.rows,
        first_batch.cache,
        True,
        {"page": 1, "start_cursor": 1},
    )
    second_batch = _batch(f"{source_prefix}:1")

    try:
        async with sessions() as session, session.begin():
            first = await persist_soccerdata_batch(
                session,
                first_spec,
                first_batch,
                registry=_registry(),
                run_id="page-run-first",
                require_identity_mappings=False,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )
        async with sessions() as session, session.begin():
            replay = await replay_soccerdata_batch(
                session,
                first_spec,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )
        async with sessions() as session, session.begin():
            terminal = await persist_soccerdata_batch(
                session,
                second_spec,
                second_batch,
                registry=_registry(),
                run_id="page-run-resumed",
                require_identity_mappings=False,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )
        async with sessions() as session:
            datasets = (
                await session.scalars(
                    select(ScrapedDataset).where(ScrapedDataset.dataset_group_key == first_spec.group_fingerprint)
                )
            ).all()

        assert first.cursor == {"page": 1, "start_cursor": 1, "generation_key": expected_generation}
        assert replay is not None and replay.replayed is True
        assert first.generation_id is not None
        assert replay.generation_id == first.generation_id
        assert replay.cursor == {"page": 1, "start_cursor": 1, "generation_key": expected_generation}
        assert terminal.cursor is None
        assert len(datasets) == 2
        assert {dataset.publication_state for dataset in datasets} == {"published"}
    finally:
        await _cleanup(sessions, competition=competition, source_id=source_prefix)
        await engine.dispose()


async def test_concurrent_warm_and_refresh_are_idempotent_on_one_dataset() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = str(uuid4())
    competition, source_id = f"g004-cache-{suffix}", f"event:{suffix}"
    common = {
        "operation": "espn_schedule_incremental",
        "competition": competition,
        "season": "2025-2026",
        "mode": SoccerdataJobMode.INCREMENTAL,
    }
    warm = SoccerdataIngestionSpec(**common, cache_mode=SoccerdataCacheMode.WARM)
    refresh = SoccerdataIngestionSpec(**common, cache_mode=SoccerdataCacheMode.REFRESH)

    async def persist(current_spec: SoccerdataIngestionSpec, cache_mode: str):
        async with sessions() as session, session.begin():
            return await persist_soccerdata_batch(
                session,
                current_spec,
                _batch(source_id, cache_mode=cache_mode),
                registry=_registry(),
                run_id=cache_mode,
                require_identity_mappings=False,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )

    try:
        left, right = await asyncio.wait_for(
            asyncio.gather(persist(warm, "warm"), persist(refresh, "cold")),
            timeout=15,
        )
        async with sessions() as session:
            datasets = await session.scalar(
                select(func.count())
                .select_from(ScrapedDataset)
                .where(ScrapedDataset.name.like(f"%:{competition}:2025-2026"))
            )
            observations = await session.scalar(
                select(func.count()).select_from(ProviderObservation).where(ProviderObservation.source_id == source_id)
            )
        assert {left.state, right.state} == {"completed"}
        assert left.dataset_id == right.dataset_id
        assert (datasets, observations) == (1, 1)
    finally:
        await _cleanup(sessions, competition=competition, source_id=source_id)
        await engine.dispose()


async def test_generation_mismatch_cannot_mix_old_or_current_pages() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = str(uuid4())
    competition, source_prefix = f"g004-generation-{suffix}", f"event:{suffix}"
    common = {
        "operation": "espn_schedule_incremental",
        "competition": competition,
        "season": "2025-2026",
        "mode": SoccerdataJobMode.INCREMENTAL,
        "limit": 2,
        "chunk_size": 1,
    }
    old_first = SoccerdataIngestionSpec(**common, cache_mode=SoccerdataCacheMode.WARM)
    old_generation = _generation_key(old_first, "a" * 64)
    old_second = SoccerdataIngestionSpec(
        **common,
        cache_mode=SoccerdataCacheMode.WARM,
        page=1,
        start_cursor=1,
        generation_key=old_generation,
    )
    new_first = SoccerdataIngestionSpec(**common, cache_mode=SoccerdataCacheMode.REFRESH)
    new_generation = _generation_key(new_first, "b" * 64)
    new_second = SoccerdataIngestionSpec(
        **common,
        cache_mode=SoccerdataCacheMode.REFRESH,
        page=1,
        start_cursor=1,
        generation_key=new_generation,
    )

    def paged_batch(source_id: str, artifact: str, *, terminal: bool, as_of: str) -> SoccerdataBatch:
        batch = _batch(source_id, artifact_digest=artifact, as_of=as_of)
        return SoccerdataBatch(
            batch.rows,
            batch.cache,
            True,
            None if terminal else {"page": 1, "start_cursor": 1},
        )

    async def persist(current_spec, batch, run_id):
        async with sessions() as session, session.begin():
            return await persist_soccerdata_batch(
                session,
                current_spec,
                batch,
                registry=_registry(),
                run_id=run_id,
                require_identity_mappings=False,
                now=datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
            )

    try:
        await persist(
            old_first,
            paged_batch(f"{source_prefix}:old:0", "a" * 64, terminal=False, as_of="2026-08-01T12:00:00Z"),
            "old-0",
        )
        await persist(
            old_second,
            paged_batch(f"{source_prefix}:old:1", "a" * 64, terminal=True, as_of="2026-08-01T12:00:00Z"),
            "old-1",
        )
        await persist(
            new_first,
            paged_batch(f"{source_prefix}:new:0", "b" * 64, terminal=False, as_of="2026-08-01T12:10:00Z"),
            "new-0",
        )

        with pytest.raises(SoccerdataIngestionError, match="artifact changed"):
            await persist(
                new_second,
                paged_batch(f"{source_prefix}:new:1", "c" * 64, terminal=True, as_of="2026-08-01T12:10:00Z"),
                "new-1-mismatch",
            )

        async with sessions() as session:
            before = (
                await session.scalars(
                    select(ProviderDatasetGeneration)
                    .where(ProviderDatasetGeneration.dataset_group_key == old_first.group_fingerprint)
                    .order_by(ProviderDatasetGeneration.id)
                )
            ).all()
        assert [generation.state for generation in before] == ["published", "staged"]

        await persist(
            new_second,
            paged_batch(f"{source_prefix}:new:1", "b" * 64, terminal=True, as_of="2026-08-01T12:10:00Z"),
            "new-1",
        )
        async with sessions() as session:
            after = (
                await session.scalars(
                    select(ProviderDatasetGeneration)
                    .where(ProviderDatasetGeneration.dataset_group_key == old_first.group_fingerprint)
                    .order_by(ProviderDatasetGeneration.id)
                )
            ).all()
        assert [generation.state for generation in after] == ["superseded", "published"]
        assert after[-1].generation_key == new_generation
        async with sessions() as session:
            assert (
                await replay_soccerdata_batch(
                    session,
                    old_first,
                    now=datetime(2026, 8, 1, 12, 12, tzinfo=UTC),
                )
                is None
            )
    finally:
        await _cleanup(sessions, competition=competition, source_id=source_prefix)
        await engine.dispose()


async def test_generation_membership_supports_identical_reverted_and_empty_heads() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = str(uuid4())
    competition, source_prefix = f"g004-lifecycle-{suffix}", f"event:{suffix}"
    current_spec = _spec(competition)

    async def persist(batch: SoccerdataBatch, run_id: str, now: datetime):
        async with sessions() as session, session.begin():
            return await persist_soccerdata_batch(
                session,
                current_spec,
                batch,
                registry=_registry(),
                run_id=run_id,
                require_identity_mappings=False,
                now=now,
            )

    def empty_batch(artifact: str, as_of: str) -> SoccerdataBatch:
        return SoccerdataBatch(
            [],
            {
                "mode": "cold",
                "as_of": as_of,
                "cache_hits": 0,
                "upstream_requests": 1,
                "artifact_digest": artifact,
            },
            True,
            None,
        )

    try:
        a_first = await persist(
            _batch(f"{source_prefix}:a", artifact_digest="a" * 64, as_of="2026-08-01T12:00:00Z"),
            "generation-a-1",
            datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
        )
        b = await persist(
            _batch(f"{source_prefix}:b", artifact_digest="b" * 64, as_of="2026-08-01T12:20:00Z"),
            "generation-b",
            datetime(2026, 8, 1, 12, 20, tzinfo=UTC),
        )
        a_reverted = await persist(
            _batch(f"{source_prefix}:a", artifact_digest="c" * 64, as_of="2026-08-01T12:40:00Z"),
            "generation-a-2",
            datetime(2026, 8, 1, 12, 40, tzinfo=UTC),
        )
        empty = await persist(
            empty_batch("d" * 64, "2026-08-01T13:00:00Z"),
            "generation-empty",
            datetime(2026, 8, 1, 13, 0, tzinfo=UTC),
        )

        async with sessions() as session:
            generations = (
                await session.scalars(
                    select(ProviderDatasetGeneration)
                    .where(ProviderDatasetGeneration.dataset_group_key == current_spec.group_fingerprint)
                    .order_by(ProviderDatasetGeneration.source_as_of)
                )
            ).all()
            dataset_count = await session.scalar(
                select(func.count())
                .select_from(ScrapedDataset)
                .where(ScrapedDataset.dataset_group_key == current_spec.group_fingerprint)
            )
            page_count = await session.scalar(
                select(func.count())
                .select_from(ProviderDatasetGenerationPage)
                .join(ProviderDatasetGeneration)
                .where(ProviderDatasetGeneration.dataset_group_key == current_spec.group_fingerprint)
            )

        assert a_first.dataset_id == a_reverted.dataset_id
        assert b.dataset_id != a_first.dataset_id
        assert empty.state == "no_data" and empty.dataset_id is None
        assert (dataset_count, page_count) == (2, 3)
        assert [generation.state for generation in generations] == [
            "superseded",
            "superseded",
            "superseded",
            "published",
        ]
        assert generations[-1].terminal_page == -1
    finally:
        await _cleanup(sessions, competition=competition, source_id=source_prefix)
        await engine.dispose()
