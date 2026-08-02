"""PostgreSQL concurrency gates for generic provider quota/circuit state."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.provider import _cache_summaries, _observation_summaries
from app.models.job import ScheduledJob, ScheduledJobRun
from app.models.provider_ingestion import ProviderIngestionCheckpoint
from app.models.provider_observation import (
    ProviderObservation,
    ProviderObservationDatasetLink,
    ProviderObservationReceipt,
    ProviderObservationSlot,
)
from app.models.provider_runtime import ProviderQuotaReservation, ProviderSourceRuntimeState
from app.models.scrape import ScrapedDataset
from app.providers import ProviderCapability, ProviderExecutionContext, ProviderRecordEnvelopeV2
from app.services.provider_observations import persist_provider_envelope
from app.services.provider_runtime import (
    ProviderRuntimeUnavailableError,
    reap_expired_provider_reservations,
    reconcile_provider_reservation,
    reserve_provider_quota,
)

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL"),
]


async def _seed(sessions, *, adapter_key: str, source_key: str, **values) -> None:
    async with sessions() as session, session.begin():
        state_values = {
            "adapter_key": adapter_key,
            "source_key": source_key,
            "quota_reserved": 0,
            "quota_consumed": 0,
            "consecutive_failures": 0,
            "circuit_state": "closed",
        }
        state_values.update(values)
        session.add(ProviderSourceRuntimeState(**state_values))


async def _reserve_once(sessions, *, adapter_key: str, source_key: str) -> bool:
    try:
        async with sessions() as session, session.begin():
            await reserve_provider_quota(session, adapter_key=adapter_key, source_key=source_key)
            # Hold the row lock long enough for the other contender to wait.
            await asyncio.sleep(0.05)
        return True
    except ProviderRuntimeUnavailableError:
        return False


async def _cleanup(sessions, *, adapter_key: str) -> None:
    async with sessions() as session, session.begin():
        await session.execute(
            delete(ProviderQuotaReservation).where(ProviderQuotaReservation.adapter_key == adapter_key)
        )
        await session.execute(
            delete(ProviderSourceRuntimeState).where(ProviderSourceRuntimeState.adapter_key == adapter_key)
        )


async def test_postgres_quota_cap_allows_exactly_one_concurrent_reservation() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter_key = f"g006-runtime-{uuid4().hex}"
    try:
        await _seed(sessions, adapter_key=adapter_key, source_key="quota", quota_limit=1)
        results = await asyncio.gather(
            _reserve_once(sessions, adapter_key=adapter_key, source_key="quota"),
            _reserve_once(sessions, adapter_key=adapter_key, source_key="quota"),
        )
        assert results.count(True) == 1
        async with sessions() as session:
            state = await session.scalar(
                select(ProviderSourceRuntimeState).where(
                    ProviderSourceRuntimeState.adapter_key == adapter_key,
                    ProviderSourceRuntimeState.source_key == "quota",
                )
            )
        assert (state.quota_reserved, state.quota_consumed) == (1, 0)
    finally:
        await _cleanup(sessions, adapter_key=adapter_key)
        await engine.dispose()


async def test_postgres_half_open_circuit_allows_exactly_one_probe() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter_key = f"g006-runtime-{uuid4().hex}"
    try:
        await _seed(
            sessions,
            adapter_key=adapter_key,
            source_key="circuit",
            circuit_state="open",
            circuit_open_until=datetime.now(UTC) - timedelta(seconds=1),
        )
        results = await asyncio.gather(
            _reserve_once(sessions, adapter_key=adapter_key, source_key="circuit"),
            _reserve_once(sessions, adapter_key=adapter_key, source_key="circuit"),
        )
        assert results.count(True) == 1
        async with sessions() as session:
            state = await session.scalar(
                select(ProviderSourceRuntimeState).where(
                    ProviderSourceRuntimeState.adapter_key == adapter_key,
                    ProviderSourceRuntimeState.source_key == "circuit",
                )
            )
        assert (state.circuit_state, state.quota_reserved) == ("half_open", 1)
    finally:
        await _cleanup(sessions, adapter_key=adapter_key)
        await engine.dispose()


async def test_postgres_reservation_is_durable_idempotent_and_cas_reconciled() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter_key = f"g006-ledger-{uuid4().hex}"
    key = uuid4().hex
    try:
        await _seed(sessions, adapter_key=adapter_key, source_key="ledger", quota_limit=2)
        async with sessions() as session, session.begin():
            first = await reserve_provider_quota(
                session,
                adapter_key=adapter_key,
                source_key="ledger",
                reservation_key=key,
                task_run_id="run-1",
                execution_token="fence-1",
            )
        async with sessions() as session, session.begin():
            replay = await reserve_provider_quota(
                session,
                adapter_key=adapter_key,
                source_key="ledger",
                reservation_key=key,
                task_run_id="run-1",
                execution_token="fence-2-retry",
            )
            assert replay.reservation_key == first.reservation_key
            assert replay.created is False
            await reconcile_provider_reservation(session, first, charged=True)
        async with sessions() as session, session.begin():
            # Exact terminal replay does not count units a second time.
            await reconcile_provider_reservation(session, first, charged=True)
        async with sessions() as session, session.begin():
            with pytest.raises(ProviderRuntimeUnavailableError, match="different provider acquisition"):
                await reconcile_provider_reservation(
                    session,
                    first.__class__(
                        adapter_key="different-adapter",
                        source_key=first.source_key,
                        units=first.units,
                        reservation_key=first.reservation_key,
                    ),
                    charged=True,
                )
        async with sessions() as session:
            state = await session.scalar(
                select(ProviderSourceRuntimeState).where(ProviderSourceRuntimeState.adapter_key == adapter_key)
            )
            record = await session.scalar(
                select(ProviderQuotaReservation).where(ProviderQuotaReservation.reservation_key == key)
            )
        assert (state.quota_reserved, state.quota_consumed, record.status, record.execution_token) == (
            0,
            1,
            "charged",
            "fence-1",
        )
        async with sessions() as session, session.begin():
            with pytest.raises(ProviderRuntimeUnavailableError, match="different outcome"):
                await reconcile_provider_reservation(session, first, charged=False)
    finally:
        await _cleanup(sessions, adapter_key=adapter_key)
        await engine.dispose()


async def test_postgres_same_acquisition_key_concurrently_reserves_once() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter_key = f"g006-dedupe-{uuid4().hex}"
    reservation_key = uuid4().hex

    async def reserve_same_key() -> str:
        async with sessions() as session, session.begin():
            reservation = await reserve_provider_quota(
                session,
                adapter_key=adapter_key,
                source_key="dedupe",
                reservation_key=reservation_key,
            )
            await asyncio.sleep(0.05)
            return reservation.reservation_key

    try:
        await _seed(sessions, adapter_key=adapter_key, source_key="dedupe", quota_limit=2)
        assert await asyncio.gather(reserve_same_key(), reserve_same_key()) == [reservation_key, reservation_key]
        async with sessions() as session:
            state = await session.scalar(
                select(ProviderSourceRuntimeState).where(ProviderSourceRuntimeState.adapter_key == adapter_key)
            )
            records = (
                (
                    await session.execute(
                        select(ProviderQuotaReservation).where(
                            ProviderQuotaReservation.reservation_key == reservation_key
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert (state.quota_reserved, len(records), records[0].status) == (1, 1, "reserved")
    finally:
        await _cleanup(sessions, adapter_key=adapter_key)
        await engine.dispose()


async def test_postgres_reaper_charges_crashed_reservation_and_opens_circuit() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter_key = f"g006-reaper-{uuid4().hex}"
    now = datetime.now(UTC)
    try:
        await _seed(sessions, adapter_key=adapter_key, source_key="crash", quota_limit=2)
        async with sessions() as session, session.begin():
            reservation = await reserve_provider_quota(
                session,
                adapter_key=adapter_key,
                source_key="crash",
                reservation_ttl_seconds=1,
                now=now,
            )
        async with sessions() as session, session.begin():
            assert await reap_expired_provider_reservations(session, now=now + timedelta(seconds=2)) == 1
        async with sessions() as session:
            state = await session.scalar(
                select(ProviderSourceRuntimeState).where(ProviderSourceRuntimeState.adapter_key == adapter_key)
            )
            record = await session.scalar(
                select(ProviderQuotaReservation).where(
                    ProviderQuotaReservation.reservation_key == reservation.reservation_key
                )
            )
        assert (state.quota_reserved, state.quota_consumed, state.circuit_state, record.status) == (
            0,
            1,
            "open",
            "uncertain",
        )
    finally:
        await _cleanup(sessions, adapter_key=adapter_key)
        await engine.dispose()


async def test_postgres_non_odds_dataset_lineage_counts_as_complete_coverage() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g007-coverage-{uuid4().hex}"
    now = datetime.now(UTC)
    observation_id = slot_id = dataset_id = None
    try:
        async with sessions() as session:
            before = (await _observation_summaries(session, observed_at=now)).get(("soccerdata", "understat"))

        async with sessions() as session, session.begin():
            dataset = ScrapedDataset(
                name=source_id,
                source="soccerdata",
                data={},
                matches_count=1,
                dataset_key=uuid4().hex + uuid4().hex,
                dataset_group_key=uuid4().hex + uuid4().hex,
                dataset_schema_version="1.0",
                dataset_digest=uuid4().hex + uuid4().hex,
                publication_state="staged",
                source_as_of=now,
                fresh_until=now + timedelta(hours=1),
            )
            session.add(dataset)
            await session.flush()
            dataset_id = dataset.id
            envelope = ProviderRecordEnvelopeV2.from_payload(
                adapter_key="soccerdata",
                source_key="understat",
                capability=ProviderCapability.FIXTURES,
                source_id=source_id,
                observed_at=now,
                payload={"fixture": source_id},
                adapter_version="g007-test",
                transport_version="test",
                job_id="g007",
                run_id=source_id,
                correlation_id=source_id,
                freshness={"as_of": now.isoformat(), "ttl_seconds": 3600},
                provenance={"source_revision": "g007"},
                schema_version="1.0",
            )
            observation = await persist_provider_envelope(
                session,
                envelope,
                context=ProviderExecutionContext.TEST,
                dataset_ids=(dataset.id,),
                now=now,
            )
            observation_id, slot_id = observation.id, observation.slot_id

        async with sessions() as session:
            after = (await _observation_summaries(session, observed_at=now)).get(("soccerdata", "understat"))

        assert after is not None
        assert after.observation_count == (before.observation_count if before else 0) + 1
        assert after.complete_snapshot_count == (before.complete_snapshot_count if before else 0) + 1
        assert after.unmapped_observation_count == (before.unmapped_observation_count if before else 0)
    finally:
        async with sessions() as session, session.begin():
            if observation_id is not None:
                await session.execute(
                    delete(ProviderObservationDatasetLink).where(
                        ProviderObservationDatasetLink.observation_id == observation_id
                    )
                )
                await session.execute(
                    delete(ProviderObservationReceipt).where(
                        ProviderObservationReceipt.observation_id == observation_id
                    )
                )
                await session.execute(delete(ProviderObservation).where(ProviderObservation.id == observation_id))
            if slot_id is not None:
                await session.execute(delete(ProviderObservationSlot).where(ProviderObservationSlot.id == slot_id))
            if dataset_id is not None:
                await session.execute(delete(ScrapedDataset).where(ScrapedDataset.id == dataset_id))
        await engine.dispose()


async def test_postgres_cache_summary_distinguishes_hit_and_mixed_evidence() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    marker = uuid4().hex
    job_id = None
    try:
        config = {
            "operation": "understat_schedule_backfill",
            "competition": f"g007-{marker}",
            "season": "2025",
            "mode": "backfill",
            "cache_mode": "warm",
        }
        async with sessions() as session, session.begin():
            job = ScheduledJob(
                name=f"g007-cache-{marker}",
                task_type="soccerdata_http_ingest",
                cron_expression="0 0 * * *",
                config=config,
            )
            session.add(job)
            await session.flush()
            job_id = job.id
            run = ScheduledJobRun(
                scheduled_job_id=job.id,
                task_type=job.task_type,
                status="completed",
                queue_lane="provider-http",
                queue_contract_version="worker-lanes/v1",
            )
            session.add(run)
            await session.flush()
            session.add(
                ProviderIngestionCheckpoint(
                    checkpoint_key=marker + marker,
                    spec_digest=uuid4().hex + uuid4().hex,
                    spec_version="soccerdata-ingestion/v1",
                    partition_key=marker,
                    state="completed",
                    cache_mode="warm",
                    scheduled_job_run_id=run.id,
                    attempt=1,
                )
            )

        async with sessions() as session:
            hit = await _cache_summaries(session)
        assert hit[("soccerdata", "understat")].cache_state == "hit"

        async with sessions() as session, session.begin():
            run = ScheduledJobRun(
                scheduled_job_id=job_id,
                task_type="soccerdata_http_ingest",
                status="completed",
                queue_lane="provider-http",
                queue_contract_version="worker-lanes/v1",
            )
            session.add(run)
            await session.flush()
            session.add(
                ProviderIngestionCheckpoint(
                    checkpoint_key=uuid4().hex + uuid4().hex,
                    spec_digest=uuid4().hex + uuid4().hex,
                    spec_version="soccerdata-ingestion/v1",
                    partition_key=f"{marker}-revalidated",
                    state="completed",
                    cache_mode="revalidated",
                    scheduled_job_run_id=run.id,
                    attempt=1,
                )
            )

        async with sessions() as session:
            revalidated = await _cache_summaries(session)
        assert revalidated[("soccerdata", "understat")].cache_state == "mixed"

        async with sessions() as session, session.begin():
            run = ScheduledJobRun(
                scheduled_job_id=job_id,
                task_type="soccerdata_http_ingest",
                status="completed",
                queue_lane="provider-http",
                queue_contract_version="worker-lanes/v1",
            )
            session.add(run)
            await session.flush()
            session.add(
                ProviderIngestionCheckpoint(
                    checkpoint_key=uuid4().hex + uuid4().hex,
                    spec_digest=uuid4().hex + uuid4().hex,
                    spec_version="soccerdata-ingestion/v1",
                    partition_key=f"{marker}-miss",
                    state="completed",
                    cache_mode="cold",
                    scheduled_job_run_id=run.id,
                    attempt=1,
                )
            )

        async with sessions() as session:
            mixed = await _cache_summaries(session)
        assert mixed[("soccerdata", "understat")].cache_state == "mixed"
    finally:
        async with sessions() as session, session.begin():
            run_ids = (
                list(
                    (
                        await session.scalars(
                            select(ScheduledJobRun.id).where(ScheduledJobRun.scheduled_job_id == job_id)
                        )
                    ).all()
                )
                if job_id is not None
                else []
            )
            if run_ids:
                await session.execute(
                    delete(ProviderIngestionCheckpoint).where(
                        ProviderIngestionCheckpoint.scheduled_job_run_id.in_(run_ids)
                    )
                )
            if job_id is not None:
                await session.execute(delete(ScheduledJob).where(ScheduledJob.id == job_id))
        await engine.dispose()
