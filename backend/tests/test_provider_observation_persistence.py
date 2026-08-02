# ruff: noqa: E501
import json
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base
from app.models.provider_observation import (
    ProviderObservation,
    ProviderObservationConflict,
    ProviderObservationQuarantine,
    ProviderObservationReceipt,
)
from app.providers import (
    DEFAULT_PROVIDER_REGISTRY,
    ProductionPolicy,
    ProviderCapability,
    ProviderEnvelopeQuarantine,
    ProviderRecordEnvelope,
    ProviderRecordEnvelopeV2,
    ProviderRegistry,
    ProviderSourceDescriptor,
)
from app.providers.odds import OddsEventObservationV1, OddsQuoteV1
from app.providers.oddsharvester_odds import oddsharvester_record_envelope
from app.providers.sportmonks_odds import SPORTMONKS_ADAPTER_KEY, SPORTMONKS_SOURCE_KEY
from app.services.provider_observations import (
    ProviderObservationPersistenceError,
    persist_provider_envelope,
    purge_expired_provider_bodies,
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


def envelope(*, payload: dict[str, float], run_id: str = "run-1") -> ProviderRecordEnvelopeV2:
    return ProviderRecordEnvelopeV2.from_payload(
        adapter_key="penaltyblog",
        source_key="local-model",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-42",
        observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        payload=payload,
        adapter_version="1",
        transport_version="python",
        job_id="job-1",
        run_id=run_id,
        correlation_id="corr-1",
        freshness={"ttl_seconds": 30},
        provenance={"model": "dc"},
        schema_version="7.3",
    )


@pytest.mark.asyncio
async def test_exact_replay_reuses_fact_and_records_distinct_receipt(session):
    first = await persist_provider_envelope(
        session, envelope(payload={"home_goals": 1.2}), now=datetime(2026, 8, 1, tzinfo=UTC)
    )
    second = await persist_provider_envelope(
        session, envelope(payload={"home_goals": 1.2}, run_id="run-2"), now=datetime(2026, 8, 1, tzinfo=UTC)
    )
    await session.commit()

    assert first.id == second.id
    assert await session.scalar(select(func.count()).select_from(ProviderObservation)) == 1
    assert await session.scalar(select(func.count()).select_from(ProviderObservationReceipt)) == 2


@pytest.mark.asyncio
async def test_slot_conflict_retains_both_facts_and_canonical_pair(session):
    first = await persist_provider_envelope(
        session, envelope(payload={"home_goals": 1.2}), now=datetime(2026, 8, 1, tzinfo=UTC)
    )
    second = await persist_provider_envelope(
        session, envelope(payload={"home_goals": 1.3}), now=datetime(2026, 8, 1, tzinfo=UTC)
    )
    await session.commit()
    conflict = await session.scalar(select(ProviderObservationConflict))

    assert first.observation_slot_key == second.observation_slot_key
    assert first.conflict_state == second.conflict_state == "conflicted"
    assert (conflict.left_observation_id, conflict.right_observation_id) == tuple(sorted((first.id, second.id)))


@pytest.mark.asyncio
async def test_v1_requires_explicit_source_and_conversion_then_preserves_original_version(session):
    v1 = ProviderRecordEnvelope.from_payload(
        provider_key="penaltyblog",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-42",
        observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        payload={"home_goals": 1.2},
        schema_version="7.3",
    )
    quarantined = await persist_provider_envelope(session, v1)
    accepted = await persist_provider_envelope(session, v1, source_key="local-model", conversion_version="bridge-v1")
    untrusted = ProviderRecordEnvelope.from_payload(
        provider_key="soccerdata",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-42",
        observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        payload={"home_goals": 1.2},
        schema_version="7.3",
    )
    rejected = await persist_provider_envelope(
        session, untrusted, source_key="local-model", conversion_version="bridge-v1"
    )
    await session.commit()

    assert isinstance(quarantined, ProviderObservationQuarantine)
    assert isinstance(rejected, ProviderObservationQuarantine)
    assert rejected.reason_code == "untrusted_source_identity"
    assert accepted.envelope_version == "1.0"
    assert accepted.original_envelope_version is None
    assert accepted.converted_from_v1 is True
    assert accepted.envelope_json == json.dumps(
        {
            "capability": "predictions",
            "observed_at": "2026-08-01T12:00:00Z",
            "payload_digest": v1.payload_digest,
            "payload_json": v1.payload_json,
            "provider_key": "penaltyblog",
            "schema_version": "7.3",
            "source_id": "match-42",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


@pytest.mark.asyncio
async def test_quarantine_is_digest_only_and_production_requires_retention_policy(session):
    result = await persist_provider_envelope(
        session,
        ProviderEnvelopeQuarantine.from_raw({"headers": {"Authorization": "secret"}}, reason="invalid_envelope"),
    )
    assert isinstance(result, ProviderObservationQuarantine)
    assert "secret" not in (result.diagnostic_metadata or "")
    with pytest.raises(ProviderObservationPersistenceError, match="retention"):
        await persist_provider_envelope(session, envelope(payload={"home_goals": 1.2}), context="production")
    trusted_source = ProviderSourceDescriptor(
        adapter_key="penaltyblog",
        source_key="local-model",
        capabilities=frozenset({ProviderCapability.PREDICTIONS}),
        production_policy=ProductionPolicy.ALLOWED,
        body_retention_days=1,
    )
    registry = ProviderRegistry((DEFAULT_PROVIDER_REGISTRY.get("penaltyblog"),), (trusted_source,))
    accepted = await persist_provider_envelope(
        session,
        envelope(payload={"home_goals": 1.2}),
        context="production",
        source_descriptor=trusted_source,
        registry=registry,
    )
    assert accepted.body_retention_until is not None
    with pytest.raises(ProviderObservationPersistenceError, match="context"):
        await persist_provider_envelope(session, envelope(payload={"home_goals": 1.2}), context="prodution")


@pytest.mark.asyncio
async def test_invalid_supported_envelopes_are_quarantined_without_raw_bodies(session):
    unsupported = ProviderRecordEnvelopeV2.from_payload(
        adapter_key="penaltyblog",
        source_key="local-model",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-unsupported",
        observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        payload={"home_goals": 1.2},
        adapter_version="1",
        transport_version="python",
        job_id="job",
        run_id="run",
        correlation_id="corr",
        freshness={"ttl_seconds": 30},
        provenance={"model": "dc"},
        schema_version="7.4",
    )
    result = await persist_provider_envelope(session, unsupported)
    assert isinstance(result, ProviderObservationQuarantine)
    assert result.reason_code == "unsupported_payload_schema"
    assert "home_goals" not in (result.diagnostic_metadata or "")


@pytest.mark.asyncio
async def test_sportmonks_odds_payload_requires_the_common_strict_contract(session):
    event = OddsEventObservationV1(
        source_event_id="fixture-42",
        sport_key="football",
        competition_key="league-8",
        commence_time=datetime(2026, 8, 2, 12, tzinfo=UTC),
        home_team="Home FC",
        away_team="Away FC",
        observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        scope="prematch",
        quality="complete",
        quotes=(
            OddsQuoteV1(
                source_quote_id="quote-1",
                provider_bookmaker_key="book-1",
                provider_bookmaker_name="Book",
                provider_market_key="market-1",
                market_key="1x2",
                period_key="full_time",
                selection_key="home",
                selection_name="Home",
                price="2.1",
                provider_updated_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
            ),
        ),
    )
    accepted = await persist_provider_envelope(
        session,
        ProviderRecordEnvelopeV2.from_payload(
            adapter_key=SPORTMONKS_ADAPTER_KEY,
            source_key=SPORTMONKS_SOURCE_KEY,
            capability=ProviderCapability.ODDS,
            source_id="fixture-42",
            observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
            payload=event.payload,
            adapter_version="sportmonks-odds/v1",
            transport_version="httpx-json/v1",
            job_id="job-1",
            run_id="run-1",
            correlation_id="corr-1",
            freshness={"ttl_seconds": 300},
            provenance={"source_revision": "sportmonks-odds/v1"},
        ),
    )
    invalid_payload = {**event.payload, "quotes": []}
    rejected = await persist_provider_envelope(
        session,
        ProviderRecordEnvelopeV2.from_payload(
            adapter_key=SPORTMONKS_ADAPTER_KEY,
            source_key=SPORTMONKS_SOURCE_KEY,
            capability=ProviderCapability.ODDS,
            source_id="fixture-43",
            observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
            payload=invalid_payload,
            adapter_version="sportmonks-odds/v1",
            transport_version="httpx-json/v1",
            job_id="job-2",
            run_id="run-2",
            correlation_id="corr-2",
            freshness={"ttl_seconds": 300},
            provenance={"source_revision": "sportmonks-odds/v1"},
        ),
    )
    assert isinstance(accepted, ProviderObservation)
    assert isinstance(rejected, ProviderObservationQuarantine)
    assert rejected.reason_code == "invalid_payload"


@pytest.mark.asyncio
async def test_oddsharvester_fallback_uses_the_same_strict_odds_contract(session):
    accepted = await persist_provider_envelope(
        session,
        oddsharvester_record_envelope(
            {
                "scraped_date": "2026-08-01 12:00:00 UTC",
                "match_date": "2026-08-02 12:00:00 UTC",
                "match_link": "https://www.oddsportal.com/football/test/league/home-away-AbC123xy/",
                "home_team": "Home FC",
                "away_team": "Away FC",
                "league_name": "Test League",
                "1x2_market": [
                    {
                        "bookmaker_name": "Book",
                        "period": "FullTime",
                        "1": "2.1",
                        "X": "3.2",
                        "2": "4.3",
                    }
                ],
            },
            job_id="job-1",
            run_id="run-1",
            correlation_id="corr-1",
        ),
    )

    assert isinstance(accepted, ProviderObservation)
    assert (accepted.adapter_key, accepted.source_key) == ("oddsharvester", "oddsportal")


@pytest.mark.asyncio
async def test_purge_tombstones_bodies_but_keeps_observation_key_and_digest(session):
    created = await persist_provider_envelope(
        session,
        envelope(payload={"home_goals": 1.2}),
        now=datetime(2026, 8, 1, tzinfo=UTC),
    )
    key, digest = created.observation_key, created.payload_digest
    await purge_expired_provider_bodies(session, now=datetime(2026, 9, 2, tzinfo=UTC))
    await session.refresh(created)

    assert (created.payload_json, created.envelope_json) == (None, None)
    assert created.body_purged_at is not None
    assert created.body_purged_at.replace(tzinfo=UTC) == datetime(2026, 9, 2, tzinfo=UTC)
    assert (created.observation_key, created.payload_digest) == (key, digest)
