"""Real transaction-boundary gate for licensed odds acquisition."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.models.provider_observation import ProviderObservation, ProviderObservationReceipt, ProviderObservationSlot
from app.models.provider_runtime import ProviderQuotaReservation, ProviderSourceRuntimeState
from app.providers import (
    ProductionPolicy,
    ProviderCapability,
    ProviderDescriptor,
    ProviderFreshnessPolicy,
    ProviderKind,
    ProviderQuotaPolicy,
    ProviderRecordEnvelopeV2,
    ProviderRegistry,
    ProviderSourceDescriptor,
    ProviderTransport,
)
from app.providers.odds import OddsEventObservationV1, OddsQuoteV1
from app.providers.sportmonks_odds import SPORTMONKS_ADAPTER_KEY, SPORTMONKS_SOURCE_KEY
from app.services import licensed_odds
from app.services.licensed_odds import LicensedOddsAcquisitionStatus, LicensedOddsService

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL"),
]


class _BlockingAdapter:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch_latest_odds(self, **_kwargs):
        self.started.set()
        await self.release.wait()
        return ()


def _registry(adapter_key: str, source_key: str) -> ProviderRegistry:
    adapter = ProviderDescriptor(
        key=adapter_key,
        display_name="Test licensed odds",
        kind=ProviderKind.ODDS,
        transport=ProviderTransport.API,
        capabilities=frozenset({ProviderCapability.ODDS}),
        production_policy=ProductionPolicy.ALLOWED,
    )
    source = ProviderSourceDescriptor(
        adapter_key=adapter_key,
        source_key=source_key,
        capabilities=frozenset({ProviderCapability.ODDS}),
        production_policy=ProductionPolicy.ALLOWED,
        quota_policy=ProviderQuotaPolicy(requests_per_minute=1),
        freshness_policy=ProviderFreshnessPolicy(max_age_seconds=300),
        body_retention_days=30,
    )
    return ProviderRegistry(
        (adapter,),
        (source,),
        operation_capabilities={(adapter_key, source_key, "fetch_latest_odds"): ProviderCapability.ODDS},
    )


async def test_committed_reservation_holds_no_database_lock_during_http(monkeypatch) -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter_key = f"g006-http-{uuid4().hex}"
    source_key = f"source-{uuid4().hex}"
    monkeypatch.setattr(licensed_odds, "SPORTMONKS_ADAPTER_KEY", adapter_key)
    monkeypatch.setattr(licensed_odds, "SPORTMONKS_SOURCE_KEY", source_key)
    adapter = _BlockingAdapter()
    service = LicensedOddsService(
        Settings(_env_file=None, sportmonks_api_token="test-only-token"),
        registry=_registry(adapter_key, source_key),
        adapter=adapter,
    )
    try:
        async with sessions() as acquisition_session:
            task = asyncio.create_task(
                service.acquire_sportmonks_latest(
                    acquisition_session,
                    scope="prematch",
                    job_id="job-1",
                    run_id="run-1",
                    correlation_id="corr-1",
                    execution_token="fence-1",
                )
            )
            await asyncio.wait_for(adapter.started.wait(), timeout=2)

            # The admission row and ledger entry are committed and lockable
            # while the fake upstream remains blocked.
            async with sessions() as observer:
                state = await asyncio.wait_for(
                    observer.scalar(
                        select(ProviderSourceRuntimeState)
                        .where(
                            ProviderSourceRuntimeState.adapter_key == adapter_key,
                            ProviderSourceRuntimeState.source_key == source_key,
                        )
                        .with_for_update()
                    ),
                    timeout=1,
                )
                assert (state.quota_reserved, state.quota_consumed) == (1, 0)
                reservation = await observer.scalar(
                    select(ProviderQuotaReservation).where(ProviderQuotaReservation.runtime_state_id == state.id)
                )
                assert reservation.status == "reserved"
                await observer.rollback()

            adapter.release.set()
            outcome = await asyncio.wait_for(task, timeout=2)
            assert outcome.telemetry.status is LicensedOddsAcquisitionStatus.ACQUIRED

        async with sessions() as observer:
            state = await observer.scalar(
                select(ProviderSourceRuntimeState).where(
                    ProviderSourceRuntimeState.adapter_key == adapter_key,
                    ProviderSourceRuntimeState.source_key == source_key,
                )
            )
            reservation = await observer.scalar(
                select(ProviderQuotaReservation).where(ProviderQuotaReservation.runtime_state_id == state.id)
            )
            assert (state.quota_reserved, state.quota_consumed, reservation.status) == (0, 1, "charged")
    finally:
        async with sessions() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ProviderQuotaReservation).where(ProviderQuotaReservation.adapter_key == adapter_key)
            )
            await cleanup.execute(
                delete(ProviderSourceRuntimeState).where(ProviderSourceRuntimeState.adapter_key == adapter_key)
            )
        await engine.dispose()


class _StaticAdapter:
    def __init__(self, records):
        self.records = records
        self.called = 0

    async def fetch_latest_odds(self, **_kwargs):
        self.called += 1
        return self.records


def _odds_envelope(*, run_id: str, correlation_id: str) -> ProviderRecordEnvelopeV2:
    now = datetime.now(UTC)
    event = OddsEventObservationV1(
        source_event_id=f"fixture-{uuid4().hex}",
        sport_key="football",
        competition_key="league-8",
        commence_time=now + timedelta(days=1),
        home_team="Home",
        away_team="Away",
        observed_at=now,
        scope="prematch",
        quality="complete",
        quotes=(
            OddsQuoteV1(
                source_quote_id=f"quote-{uuid4().hex}",
                provider_bookmaker_key="bookmaker-1",
                provider_bookmaker_name="Bookmaker",
                provider_market_key="market-1",
                market_key="1x2",
                period_key="full_time",
                line=None,
                selection_key="home",
                selection_name="Home",
                price=Decimal("2.10"),
                provider_updated_at=now,
                status="active",
            ),
        ),
        expected_bookmaker_count=1,
        expected_market_count=1,
    )
    return ProviderRecordEnvelopeV2.from_payload(
        adapter_key=SPORTMONKS_ADAPTER_KEY,
        source_key=SPORTMONKS_SOURCE_KEY,
        capability=ProviderCapability.ODDS,
        source_id=event.source_event_id,
        observed_at=now,
        payload=event.payload,
        adapter_version="test/v1",
        transport_version="test/v1",
        job_id="job-stage",
        run_id=run_id,
        correlation_id=correlation_id,
        freshness={"as_of": now.isoformat(), "ttl_seconds": 300},
        provenance={"source_revision": "test"},
    )


async def test_staged_observation_replays_after_reconciliation_crash_without_second_egress(monkeypatch) -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    run_id = f"run-{uuid4().hex}"
    correlation_id = f"corr-{uuid4().hex}"
    envelope = _odds_envelope(run_id=run_id, correlation_id=correlation_id)
    first_adapter = _StaticAdapter((envelope,))
    registry = _registry(SPORTMONKS_ADAPTER_KEY, SPORTMONKS_SOURCE_KEY)
    real_reconcile = licensed_odds.reconcile_provider_reservation

    async def crash_after_staging(*_args, **_kwargs):
        raise RuntimeError("simulated reconciliation crash")

    try:
        async with sessions() as session:
            monkeypatch.setattr(licensed_odds, "reconcile_provider_reservation", crash_after_staging)
            first = await LicensedOddsService(
                Settings(_env_file=None, sportmonks_api_token="test-only-token"),
                registry=registry,
                adapter=first_adapter,
            ).acquire_sportmonks_latest(
                session,
                scope="prematch",
                job_id="job-stage",
                run_id=run_id,
                correlation_id=correlation_id,
                execution_token="fence-1",
            )
            assert first.telemetry.reason_code == "reconciliation_deferred"
            assert len(first.observation_ids) == 1

        second_adapter = _StaticAdapter(())
        async with sessions() as session:
            monkeypatch.setattr(licensed_odds, "reconcile_provider_reservation", real_reconcile)
            replay = await LicensedOddsService(
                Settings(_env_file=None, sportmonks_api_token="test-only-token"),
                registry=registry,
                adapter=second_adapter,
            ).acquire_sportmonks_latest(
                session,
                scope="prematch",
                job_id="job-stage",
                run_id=run_id,
                correlation_id=correlation_id,
                execution_token="fence-2",
            )
            assert replay.telemetry.status is LicensedOddsAcquisitionStatus.ACQUIRED
            assert replay.telemetry.reason_code == "staged_observations_replayed"
            assert replay.observation_ids == first.observation_ids
            assert replay.replayed is True
            assert second_adapter.called == 0

        async with sessions() as observer:
            reservation = await observer.scalar(
                select(ProviderQuotaReservation).where(ProviderQuotaReservation.task_run_id == run_id)
            )
            assert reservation.status == "charged"
            assert await observer.get(ProviderObservation, first.observation_ids[0]) is not None
    finally:
        async with sessions() as cleanup, cleanup.begin():
            persisted_ids = tuple(
                (
                    await cleanup.scalars(
                        select(ProviderObservationReceipt.observation_id).where(
                            ProviderObservationReceipt.provider_run_id == run_id
                        )
                    )
                ).all()
            )
            slot_ids = tuple(
                (
                    await cleanup.scalars(
                        select(ProviderObservation.slot_id).where(ProviderObservation.id.in_(persisted_ids))
                    )
                ).all()
            )
            await cleanup.execute(
                delete(ProviderObservationReceipt).where(ProviderObservationReceipt.provider_run_id == run_id)
            )
            await cleanup.execute(delete(ProviderObservation).where(ProviderObservation.id.in_(persisted_ids)))
            await cleanup.execute(delete(ProviderObservationSlot).where(ProviderObservationSlot.id.in_(slot_ids)))
            await cleanup.execute(
                delete(ProviderQuotaReservation).where(ProviderQuotaReservation.task_run_id == run_id)
            )
            state = await cleanup.scalar(
                select(ProviderSourceRuntimeState).where(
                    ProviderSourceRuntimeState.adapter_key == SPORTMONKS_ADAPTER_KEY,
                    ProviderSourceRuntimeState.source_key == SPORTMONKS_SOURCE_KEY,
                )
            )
            if state is not None:
                await cleanup.delete(state)
        await engine.dispose()
