"""PostgreSQL gates for immutable licensed-odds materialisation.

The file is opt-in: use an already migrated isolated database through
``BET_TEST_POSTGRES_URL``.  Each test rolls its outer transaction back, so it
never removes or commits pre-existing local development data.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.match import Match, OddsEntry
from app.models.odds_lineage import OddsQuote, OddsSnapshot
from app.models.provider_observation import ProviderObservation
from app.providers import ProviderCapability, ProviderRecordEnvelopeV2
from app.providers.odds import OddsEventObservationV1, OddsQuoteV1
from app.services.odds_ingestion import materialize_odds_observation
from app.services.provider_identity import (
    IdentityCandidateProposal,
    IdentityDecision,
    add_identity_candidate,
    apply_identity_decision,
)
from app.services.provider_observations import persist_provider_envelope

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL"),
]


def _event(source_id: str, *, market_key: str = "1x2") -> OddsEventObservationV1:
    observed_at = datetime(2026, 8, 1, 12, tzinfo=UTC)
    return OddsEventObservationV1(
        source_event_id=source_id,
        sport_key="football",
        competition_key="league-1",
        commence_time=datetime(2026, 8, 2, 15, tzinfo=UTC),
        home_team="Home",
        away_team="Away",
        observed_at=observed_at,
        scope="prematch",
        quality="complete",
        expected_bookmaker_count=1,
        expected_market_count=1,
        quotes=tuple(
            OddsQuoteV1(
                source_quote_id=f"quote-{selection}",
                provider_bookmaker_key="book-1",
                provider_bookmaker_name="Book One",
                provider_market_key="market-1",
                market_key=market_key,
                period_key="full_time",
                selection_key=selection,
                selection_name=selection.title(),
                price=Decimal(price),
                provider_updated_at=observed_at,
            )
            for selection, price in (("home", "2.10"), ("draw", "3.20"), ("away", "3.40"))
        ),
    )


def _envelope(event: OddsEventObservationV1, *, run_id: str) -> ProviderRecordEnvelopeV2:
    return ProviderRecordEnvelopeV2.from_payload(
        adapter_key="sportmonks-v3-odds",
        source_key="sportmonks-football-v3-standard-odds",
        capability=ProviderCapability.ODDS,
        source_id=event.source_event_id,
        observed_at=event.observed_at,
        payload=event.payload,
        adapter_version="g006-test",
        transport_version="mock",
        job_id="g006-odds-materialization",
        run_id=run_id,
        correlation_id=run_id,
        freshness={"ttl_seconds": 30},
        provenance={"source_revision": "g006"},
        schema_version="1.0",
    )


async def _accepted_mapping(session: AsyncSession, *, source_id: str) -> int:
    match = Match(
        external_id=f"g006-{source_id}",
        sport="football",
        home_team="Home",
        away_team="Away",
        status="scheduled",
        match_date=datetime(2026, 8, 2, 15, tzinfo=UTC),
        competition="League 1",
    )
    session.add(match)
    await session.flush()
    pending = await apply_identity_decision(
        session,
        IdentityDecision(
            entity_type="match",
            command_kind="propose",
            adapter_key="sportmonks-v3-odds",
            source_key="sportmonks-football-v3-standard-odds",
            source_id=source_id,
            state="pending_review",
            canonical_target_id=None,
            expected_predecessor_mapping_id=None,
        ),
    )
    candidate = await add_identity_candidate(
        session,
        IdentityCandidateProposal(
            entity_type="match",
            mapping_id=pending.id,
            canonical_target_id=match.id,
            rank=1,
            confidence=Decimal("1"),
            evidence={"rule": "g006-exact-test"},
        ),
    )
    await apply_identity_decision(
        session,
        IdentityDecision(
            entity_type="match",
            command_kind="decide",
            adapter_key="sportmonks-v3-odds",
            source_key="sportmonks-football-v3-standard-odds",
            source_id=source_id,
            state="accepted",
            canonical_target_id=match.id,
            expected_predecessor_mapping_id=pending.id,
            selected_candidate_id=candidate.id,
        ),
    )
    return match.id


async def _persist(session: AsyncSession, event: OddsEventObservationV1, *, run_id: str) -> ProviderObservation:
    observation = await persist_provider_envelope(session, _envelope(event, run_id=run_id))
    assert isinstance(observation, ProviderObservation)
    return observation


async def test_postgres_materializes_exact_1x2_and_replays_idempotently() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    source_id = f"g006-odds-{uuid4()}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                await _accepted_mapping(session, source_id=source_id)
                observation = await _persist(session, _event(source_id), run_id="first")

                first = await materialize_odds_observation(
                    session, observation, bookmaker_mapping={"book-1": "canonical-book"}
                )
                replay = await materialize_odds_observation(
                    session, observation, bookmaker_mapping={"book-1": "canonical-book"}
                )

                assert first.created is True
                assert (first.quotes_written, first.legacy_entries_written, first.snapshot.quality) == (
                    3,
                    1,
                    "complete",
                )
                assert replay.created is False
                assert replay.snapshot.id == first.snapshot.id
                assert replay.quotes_written == 3
                assert replay.legacy_entries_written == 1
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(OddsSnapshot)
                        .where(OddsSnapshot.provider_observation_id == observation.id)
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(OddsQuote)
                        .where(OddsQuote.odds_snapshot_id == first.snapshot.id)
                    )
                    == 3
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(OddsEntry)
                        .where(OddsEntry.odds_snapshot_id == first.snapshot.id)
                    )
                    == 1
                )
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


async def test_postgres_preserves_unmapped_quotes_in_partial_snapshot_without_legacy_projection() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    source_id = f"g006-odds-partial-{uuid4()}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                await _accepted_mapping(session, source_id=source_id)
                observation = await _persist(
                    session, _event(source_id, market_key="unmapped:provider-market"), run_id="partial"
                )
                result = await materialize_odds_observation(
                    session, observation, bookmaker_mapping={"book-1": "canonical-book"}
                )

                assert result.created is True
                assert (result.snapshot.quality, result.quotes_written, result.legacy_entries_written) == (
                    "partial",
                    3,
                    0,
                )
                quotes = list(
                    (
                        await session.scalars(select(OddsQuote).where(OddsQuote.odds_snapshot_id == result.snapshot.id))
                    ).all()
                )
                assert {quote.market_key for quote in quotes} == {"unmapped:provider-market"}
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(OddsEntry)
                        .where(OddsEntry.odds_snapshot_id == result.snapshot.id)
                    )
                    == 0
                )
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()
