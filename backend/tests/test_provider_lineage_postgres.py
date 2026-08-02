"""PostgreSQL-only concurrency gates for provider lineage.

Run explicitly with ``BET_TEST_POSTGRES_URL`` pointing at an isolated database
already migrated to Alembic head. The default unit suite skips these tests.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.provider_identity import Team, TeamProviderMapping, TeamProviderMappingCandidate
from app.models.provider_observation import (
    ProviderObservation,
    ProviderObservationConflict,
    ProviderObservationQuarantine,
    ProviderObservationReceipt,
    ProviderObservationSlot,
)
from app.providers import ProviderCapability, ProviderEnvelopeQuarantine, ProviderRecordEnvelopeV2
from app.services.e2e_cleanup import CleanupPlan, apply_cleanup_plan
from app.services.provider_identity import (
    EXACT_SINGLETON_RULE_VERSION,
    IdentityCandidateProposal,
    IdentityDecision,
    InvalidIdentityTransitionError,
    StaleIdentityDecisionError,
    add_identity_candidate,
    apply_identity_decision,
    auto_accept_exact_singletons,
)
from app.services.provider_observations import persist_provider_envelope, purge_expired_provider_bodies

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL"),
]


def _envelope(source_id: str, *, home_goals: float, run_id: str) -> ProviderRecordEnvelopeV2:
    return ProviderRecordEnvelopeV2.from_payload(
        adapter_key="penaltyblog",
        source_key="local-model",
        capability=ProviderCapability.PREDICTIONS,
        source_id=source_id,
        observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        payload={"home_goals": home_goals},
        adapter_version="g002-test",
        transport_version="python",
        job_id="g002-concurrency",
        run_id=run_id,
        correlation_id=run_id,
        freshness={"ttl_seconds": 30},
        provenance={"model": "g002-test"},
        schema_version="7.3",
    )


async def _delete_observation_lineage(sessions, source_id: str) -> None:
    """Remove only UUID-scoped rows created by this PostgreSQL gate file."""
    async with sessions() as session, session.begin():
        observation_ids = list(
            (
                await session.scalars(select(ProviderObservation.id).where(ProviderObservation.source_id == source_id))
            ).all()
        )
        slot_ids = list(
            (
                await session.scalars(
                    select(ProviderObservation.slot_id).where(ProviderObservation.id.in_(observation_ids))
                )
            ).all()
        )
        if observation_ids:
            await session.execute(
                delete(ProviderObservationConflict).where(
                    ProviderObservationConflict.left_observation_id.in_(observation_ids)
                    | ProviderObservationConflict.right_observation_id.in_(observation_ids)
                )
            )
            await session.execute(
                delete(ProviderObservationReceipt).where(ProviderObservationReceipt.observation_id.in_(observation_ids))
            )
            await session.execute(delete(ProviderObservation).where(ProviderObservation.id.in_(observation_ids)))
        if slot_ids:
            await session.execute(delete(ProviderObservationSlot).where(ProviderObservationSlot.id.in_(slot_ids)))


async def _delete_team_lineage(sessions, source_id: str, *, delete_teams: bool = True) -> None:
    """Delete only the temporal mappings and canonical teams created by a gate."""
    async with sessions() as session, session.begin():
        mapping_ids = list(
            (
                await session.scalars(select(TeamProviderMapping.id).where(TeamProviderMapping.source_id == source_id))
            ).all()
        )
        if mapping_ids:
            await session.execute(
                update(TeamProviderMapping)
                .where(TeamProviderMapping.id.in_(mapping_ids))
                .values(selected_candidate_id=None)
            )
            await session.execute(
                delete(TeamProviderMappingCandidate).where(TeamProviderMappingCandidate.mapping_id.in_(mapping_ids))
            )
            await session.execute(delete(TeamProviderMapping).where(TeamProviderMapping.id.in_(mapping_ids)))
        if delete_teams:
            await session.execute(delete(Team).where(Team.display_name.like(f"{source_id}%")))


async def test_concurrent_first_slot_payloads_keep_both_facts_and_conflict() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-observation-{uuid4()}"

    async def ingest(home_goals: float, run_id: str) -> int:
        async with sessions() as session, session.begin():
            row = await persist_provider_envelope(
                session,
                _envelope(source_id, home_goals=home_goals, run_id=run_id),
                now=datetime(2026, 8, 1, 13, tzinfo=UTC),
            )
            return row.id

    try:
        left_id, right_id = await asyncio.wait_for(
            asyncio.gather(ingest(1.1, "run-left"), ingest(1.2, "run-right")), timeout=15
        )
        assert left_id != right_id
        async with sessions() as session:
            observations = list(
                (
                    await session.scalars(select(ProviderObservation).where(ProviderObservation.source_id == source_id))
                ).all()
            )
            assert len(observations) == 2
            assert {row.conflict_state for row in observations} == {"conflicted"}
            conflict = await session.scalar(
                select(ProviderObservationConflict).where(
                    ProviderObservationConflict.left_observation_id.in_((left_id, right_id)),
                    ProviderObservationConflict.right_observation_id.in_((left_id, right_id)),
                )
            )
            assert conflict is not None
            assert (conflict.left_observation_id, conflict.right_observation_id) == tuple(sorted((left_id, right_id)))
    finally:
        async with sessions() as session, session.begin():
            observation_ids = list(
                (
                    await session.scalars(
                        select(ProviderObservation.id).where(ProviderObservation.source_id == source_id)
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
            if observation_ids:
                await session.execute(
                    delete(ProviderObservationConflict).where(
                        ProviderObservationConflict.left_observation_id.in_(observation_ids)
                    )
                )
                await session.execute(
                    delete(ProviderObservationReceipt).where(
                        ProviderObservationReceipt.observation_id.in_(observation_ids)
                    )
                )
                await session.execute(delete(ProviderObservation).where(ProviderObservation.id.in_(observation_ids)))
            if slot_ids:
                await session.execute(delete(ProviderObservationSlot).where(ProviderObservationSlot.id.in_(slot_ids)))
        await engine.dispose()


async def test_concurrent_exact_replay_keeps_one_fact_and_two_receipts() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-replay-{uuid4()}"

    async def ingest(run_id: str) -> int:
        async with sessions() as session, session.begin():
            row = await persist_provider_envelope(
                session,
                _envelope(source_id, home_goals=1.1, run_id=run_id),
                now=datetime(2026, 8, 1, 13, tzinfo=UTC),
            )
            return row.id

    try:
        left_id, right_id = await asyncio.wait_for(
            asyncio.gather(ingest("replay-left"), ingest("replay-right")), timeout=15
        )
        assert left_id == right_id
        async with sessions() as session:
            fact_count = await session.scalar(
                select(func.count()).select_from(ProviderObservation).where(ProviderObservation.source_id == source_id)
            )
            receipt_count = await session.scalar(
                select(func.count())
                .select_from(ProviderObservationReceipt)
                .join(ProviderObservation)
                .where(ProviderObservation.source_id == source_id)
            )
            assert (fact_count, receipt_count) == (1, 2)
    finally:
        async with sessions() as session, session.begin():
            observation_ids = list(
                (
                    await session.scalars(
                        select(ProviderObservation.id).where(ProviderObservation.source_id == source_id)
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
            if observation_ids:
                await session.execute(
                    delete(ProviderObservationReceipt).where(
                        ProviderObservationReceipt.observation_id.in_(observation_ids)
                    )
                )
                await session.execute(delete(ProviderObservation).where(ProviderObservation.id.in_(observation_ids)))
            if slot_ids:
                await session.execute(delete(ProviderObservationSlot).where(ProviderObservationSlot.id.in_(slot_ids)))
        await engine.dispose()


async def test_concurrent_first_pending_proposals_leave_one_current_mapping() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-first-pending-{uuid4()}"

    async def propose() -> TeamProviderMapping:
        async with sessions() as session, session.begin():
            return await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                    reason="concurrent first proposal",
                ),
            )

    try:
        outcomes = await asyncio.wait_for(asyncio.gather(propose(), propose(), return_exceptions=True), timeout=15)
        assert all(isinstance(outcome, TeamProviderMapping) for outcome in outcomes)
        assert len({outcome.id for outcome in outcomes if isinstance(outcome, TeamProviderMapping)}) == 1
        async with sessions() as session:
            current = list(
                (
                    await session.scalars(
                        select(TeamProviderMapping).where(
                            TeamProviderMapping.source_id == source_id,
                            TeamProviderMapping.valid_to.is_(None),
                        )
                    )
                ).all()
            )
            assert len(current) == 1
            assert current[0].state == "pending_review"
    finally:
        await _delete_team_lineage(sessions, source_id)
        await engine.dispose()


async def test_rejected_mapping_reopens_as_pending_without_losing_temporal_history() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-reopen-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                ),
            )
            rejected = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="decide",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="rejected",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=pending.id,
                ),
            )
            reopened = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="reopen",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=rejected.id,
                ),
            )
            assert pending.valid_to == rejected.valid_from
            assert rejected.valid_to == reopened.valid_from
            assert reopened.valid_to is None
        async with sessions() as session:
            states = list(
                (
                    await session.scalars(
                        select(TeamProviderMapping.state)
                        .where(TeamProviderMapping.source_id == source_id)
                        .order_by(TeamProviderMapping.id)
                    )
                ).all()
            )
            assert states == ["pending_review", "rejected", "pending_review"]
    finally:
        await _delete_team_lineage(sessions, source_id)
        await engine.dispose()


async def test_competing_accepted_remaps_leave_exactly_one_current_successor() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-remap-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            teams = [
                Team(sport="football", display_name=f"{source_id}-{suffix}", normalized_name=f"{source_id}-{suffix}")
                for suffix in ("one", "two", "three")
            ]
            session.add_all(teams)
            await session.flush()
            pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                ),
            )
            accepted = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="decide",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="accepted",
                    canonical_target_id=teams[0].id,
                    expected_predecessor_mapping_id=pending.id,
                ),
            )
            accepted_id = accepted.id
            candidate_ids = (teams[1].id, teams[2].id)

        async def remap(target_id: int) -> TeamProviderMapping:
            async with sessions() as session, session.begin():
                return await apply_identity_decision(
                    session,
                    IdentityDecision(
                        entity_type="team",
                        command_kind="remap",
                        adapter_key="soccerdata",
                        source_key="fbref",
                        source_id=source_id,
                        state="accepted",
                        canonical_target_id=target_id,
                        expected_predecessor_mapping_id=accepted_id,
                    ),
                )

        outcomes = await asyncio.wait_for(
            asyncio.gather(*(remap(target_id) for target_id in candidate_ids), return_exceptions=True), timeout=15
        )
        assert sum(isinstance(outcome, TeamProviderMapping) for outcome in outcomes) == 1
        assert sum(isinstance(outcome, StaleIdentityDecisionError) for outcome in outcomes) == 1
        async with sessions() as session:
            current = list(
                (
                    await session.scalars(
                        select(TeamProviderMapping).where(
                            TeamProviderMapping.source_id == source_id,
                            TeamProviderMapping.valid_to.is_(None),
                        )
                    )
                ).all()
            )
            assert len(current) == 1
            assert current[0].state == "accepted"
            assert current[0].team_id in candidate_ids
    finally:
        await _delete_team_lineage(sessions, source_id)
        await engine.dispose()


async def test_explicit_stale_predecessor_leaves_mapping_history_unchanged() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-stale-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                ),
            )
            rejected = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="decide",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="rejected",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=pending.id,
                ),
            )
            assert rejected.valid_to is None

        async with sessions() as session, session.begin():
            with pytest.raises(StaleIdentityDecisionError, match="expected predecessor"):
                await apply_identity_decision(
                    session,
                    IdentityDecision(
                        entity_type="team",
                        command_kind="decide",
                        adapter_key="soccerdata",
                        source_key="fbref",
                        source_id=source_id,
                        state="accepted",
                        canonical_target_id=1,
                        expected_predecessor_mapping_id=pending.id,
                    ),
                )
        async with sessions() as session:
            rows = list(
                (
                    await session.scalars(select(TeamProviderMapping).where(TeamProviderMapping.source_id == source_id))
                ).all()
            )
            assert len(rows) == 2
            assert {row.id for row in rows} == {pending.id, rejected.id}
            assert next(row for row in rows if row.id == rejected.id).valid_to is None
    finally:
        await _delete_team_lineage(sessions, source_id)
        await engine.dispose()


async def test_concurrent_mapping_decisions_leave_one_current_successor() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-team-{uuid4()}"

    async with sessions() as session, session.begin():
        team = Team(sport="football", display_name=source_id, normalized_name=source_id)
        session.add(team)
        await session.flush()
        team_id = team.id
        pending = await apply_identity_decision(
            session,
            IdentityDecision(
                entity_type="team",
                command_kind="propose",
                adapter_key="soccerdata",
                source_key="fbref",
                source_id=source_id,
                state="pending_review",
                canonical_target_id=None,
                expected_predecessor_mapping_id=None,
                reason="concurrency candidate",
            ),
        )
        pending_id = pending.id

    async def decide(*, accepted: bool):
        async with sessions() as session, session.begin():
            return await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="decide",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="accepted" if accepted else "rejected",
                    canonical_target_id=team_id if accepted else None,
                    expected_predecessor_mapping_id=pending_id,
                    reason="accept" if accepted else "reject",
                ),
            )

    try:
        outcomes = await asyncio.wait_for(
            asyncio.gather(decide(accepted=True), decide(accepted=False), return_exceptions=True), timeout=15
        )
        assert sum(isinstance(value, TeamProviderMapping) for value in outcomes) == 1
        assert sum(isinstance(value, StaleIdentityDecisionError) for value in outcomes) == 1
        async with sessions() as session:
            current_count = await session.scalar(
                select(func.count())
                .select_from(TeamProviderMapping)
                .where(TeamProviderMapping.source_id == source_id, TeamProviderMapping.valid_to.is_(None))
            )
            total_count = await session.scalar(
                select(func.count()).select_from(TeamProviderMapping).where(TeamProviderMapping.source_id == source_id)
            )
            assert (current_count, total_count) == (1, 2)
    finally:
        async with sessions() as session, session.begin():
            await session.execute(delete(TeamProviderMapping).where(TeamProviderMapping.source_id == source_id))
            await session.execute(delete(Team).where(Team.id == team_id))
        await engine.dispose()


async def test_exact_singleton_resolver_and_candidate_insert_do_not_deadlock_or_accept_ambiguity() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-resolver-race-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            teams = [
                Team(sport="football", display_name=f"{source_id}-{suffix}", normalized_name=f"{source_id}-{suffix}")
                for suffix in ("exact", "competing")
            ]
            session.add_all(teams)
            await session.flush()
            pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                ),
            )
            await add_identity_candidate(
                session,
                IdentityCandidateProposal(
                    entity_type="team",
                    mapping_id=pending.id,
                    canonical_target_id=teams[0].id,
                    rank=1,
                    confidence=Decimal("1"),
                    evidence={"rule": "exact"},
                ),
            )
            pending_id = pending.id
            competing_team_id = teams[1].id

        async def resolve():
            async with sessions() as session, session.begin():
                return await auto_accept_exact_singletons(
                    session,
                    entity_type="team",
                    rule_version=EXACT_SINGLETON_RULE_VERSION,
                )

        async def add_competing_candidate():
            async with sessions() as session, session.begin():
                return await add_identity_candidate(
                    session,
                    IdentityCandidateProposal(
                        entity_type="team",
                        mapping_id=pending_id,
                        canonical_target_id=competing_team_id,
                        rank=2,
                        confidence=Decimal("0.5"),
                        evidence={"rule": "competing"},
                    ),
                )

        resolved, inserted = await asyncio.wait_for(
            asyncio.gather(resolve(), add_competing_candidate(), return_exceptions=True), timeout=15
        )
        assert not isinstance(resolved, BaseException)
        assert not isinstance(inserted, (TimeoutError, asyncio.TimeoutError))
        async with sessions() as session:
            current = await session.scalar(
                select(TeamProviderMapping).where(
                    TeamProviderMapping.source_id == source_id,
                    TeamProviderMapping.valid_to.is_(None),
                )
            )
            candidate_count = await session.scalar(
                select(func.count())
                .select_from(TeamProviderMappingCandidate)
                .where(TeamProviderMappingCandidate.mapping_id == pending_id)
            )
            assert current is not None
            if current.state == "accepted":
                assert len(resolved) == 1
                assert isinstance(inserted, InvalidIdentityTransitionError)
                assert candidate_count == 1
            else:
                assert current.state == "pending_review"
                assert resolved == []
                assert isinstance(inserted, TeamProviderMappingCandidate)
                assert candidate_count == 2
    finally:
        await _delete_team_lineage(sessions, source_id)
        await engine.dispose()


async def test_conflict_insert_fault_rolls_back_fact_then_clean_retry_succeeds() -> None:
    """A conflict-write fault cannot strand the second fact or its receipt."""
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-atomic-conflict-{uuid4()}"
    function_name = f"g002_reject_conflict_{uuid4().hex}"
    trigger_name = f"g002_reject_conflict_trigger_{uuid4().hex}"

    try:
        async with sessions() as session, session.begin():
            first = await persist_provider_envelope(
                session,
                _envelope(source_id, home_goals=1.1, run_id="initial"),
                now=datetime(2026, 8, 1, 13, tzinfo=UTC),
            )
            first_id = first.id
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"CREATE FUNCTION {function_name}() RETURNS trigger LANGUAGE plpgsql AS "
                    "$$ BEGIN RAISE EXCEPTION 'g002 injected conflict failure'; END; $$"
                )
            )
            await connection.execute(
                text(
                    f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON provider_observation_conflicts "
                    f"FOR EACH ROW EXECUTE FUNCTION {function_name}()"
                )
            )
        async with sessions() as session:
            with pytest.raises(DBAPIError, match="g002 injected conflict failure"):
                async with session.begin():
                    await persist_provider_envelope(
                        session,
                        _envelope(source_id, home_goals=1.2, run_id="faulted"),
                        now=datetime(2026, 8, 1, 13, tzinfo=UTC),
                    )
        async with sessions() as session:
            observations = list(
                (
                    await session.scalars(select(ProviderObservation).where(ProviderObservation.source_id == source_id))
                ).all()
            )
            receipts = await session.scalar(
                select(func.count())
                .select_from(ProviderObservationReceipt)
                .join(ProviderObservation)
                .where(ProviderObservation.source_id == source_id)
            )
            assert [row.id for row in observations] == [first_id]
            assert receipts == 1
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TRIGGER {trigger_name} ON provider_observation_conflicts"))
            await connection.execute(text(f"DROP FUNCTION {function_name}()"))
        async with sessions() as session, session.begin():
            retried = await persist_provider_envelope(
                session,
                _envelope(source_id, home_goals=1.2, run_id="clean-retry"),
                now=datetime(2026, 8, 1, 13, tzinfo=UTC),
            )
            assert retried.id != first_id
        async with sessions() as session:
            conflict_count = await session.scalar(
                select(func.count())
                .select_from(ProviderObservationConflict)
                .where(
                    (ProviderObservationConflict.left_observation_id == first_id)
                    | (ProviderObservationConflict.right_observation_id == first_id)
                )
            )
            assert conflict_count == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name} ON provider_observation_conflicts"))
            await connection.execute(text(f"DROP FUNCTION IF EXISTS {function_name}()"))
        await _delete_observation_lineage(sessions, source_id)
        await engine.dispose()


async def test_purge_tombstones_postgres_bodies_but_preserves_keys_digests_and_snapshots() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-purge-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            observation = await persist_provider_envelope(
                session,
                _envelope(source_id, home_goals=1.1, run_id="purge-run"),
                now=datetime(2026, 8, 1, 13, tzinfo=UTC),
            )
            quarantine = await persist_provider_envelope(
                session,
                ProviderEnvelopeQuarantine.from_raw({"source": source_id}, reason="g002-purge-test"),
                reader_version=source_id,
                now=datetime(2026, 8, 1, 13, tzinfo=UTC),
            )
            assert isinstance(quarantine, ProviderObservationQuarantine)
            receipt = await session.scalar(
                select(ProviderObservationReceipt).where(ProviderObservationReceipt.observation_id == observation.id)
            )
            assert receipt is not None
            # Snapshot columns are immutable external lineage values and do
            # not require the nullable convenience FK target to remain alive.
            await session.execute(
                update(ProviderObservationReceipt)
                .where(ProviderObservationReceipt.id == receipt.id)
                .values(
                    scrape_job_id_snapshot=101,
                    scheduled_job_run_id_snapshot=202,
                    origin_dataset_id_snapshot=303,
                )
            )
            await session.refresh(receipt)
            persisted = (
                observation.id,
                observation.observation_key,
                observation.payload_digest,
                receipt.id,
                receipt.receipt_key,
                receipt.received_envelope_digest,
                receipt.scrape_job_id_snapshot,
                receipt.scheduled_job_run_id_snapshot,
                receipt.origin_dataset_id_snapshot,
                quarantine.id,
                quarantine.raw_digest,
            )
            await session.execute(
                update(ProviderObservation)
                .where(ProviderObservation.id == observation.id)
                .values(body_retention_until=datetime(2026, 8, 1, 12, tzinfo=UTC))
            )
            await session.execute(
                update(ProviderObservationReceipt)
                .where(ProviderObservationReceipt.id == receipt.id)
                .values(body_retention_until=datetime(2026, 8, 1, 12, tzinfo=UTC))
            )
            await session.execute(
                update(ProviderObservationQuarantine)
                .where(ProviderObservationQuarantine.id == quarantine.id)
                .values(metadata_retention_until=datetime(2026, 8, 1, 12, tzinfo=UTC))
            )
            assert await purge_expired_provider_bodies(session, now=datetime(2026, 8, 1, 14, tzinfo=UTC)) == (1, 1, 1)
        async with sessions() as session:
            observation = await session.get(ProviderObservation, persisted[0])
            receipt = await session.get(ProviderObservationReceipt, persisted[3])
            quarantine = await session.get(ProviderObservationQuarantine, persisted[9])
            assert observation is not None and receipt is not None and quarantine is not None
            assert (observation.payload_json, observation.envelope_json, observation.body_purged_at is not None) == (
                None,
                None,
                True,
            )
            assert (receipt.received_envelope_json, receipt.body_purged_at is not None) == (None, True)
            assert (quarantine.diagnostic_metadata, quarantine.metadata_purged_at is not None) == (None, True)
            assert (observation.observation_key, observation.payload_digest) == persisted[1:3]
            assert (receipt.receipt_key, receipt.received_envelope_digest) == persisted[4:6]
            assert (
                receipt.scrape_job_id_snapshot,
                receipt.scheduled_job_run_id_snapshot,
                receipt.origin_dataset_id_snapshot,
            ) == persisted[6:9]
            assert quarantine.raw_digest == persisted[10]
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(ProviderObservationQuarantine).where(ProviderObservationQuarantine.reader_version == source_id)
            )
        await _delete_observation_lineage(sessions, source_id)
        await engine.dispose()


async def test_selected_candidate_must_belong_to_pending_predecessor_and_target() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-candidate-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            team = Team(sport="football", display_name=source_id, normalized_name=source_id)
            session.add(team)
            await session.flush()
            team_id = team.id
            pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                ),
            )
            candidate = await add_identity_candidate(
                session,
                IdentityCandidateProposal(
                    entity_type="team",
                    mapping_id=pending.id,
                    canonical_target_id=team_id,
                    rank=1,
                    confidence=Decimal("0.9000"),
                    evidence={"rule": "exact-provider-id"},
                ),
            )
            with pytest.raises(InvalidIdentityTransitionError, match="canonical target"):
                await apply_identity_decision(
                    session,
                    IdentityDecision(
                        entity_type="team",
                        command_kind="decide",
                        adapter_key="soccerdata",
                        source_key="fbref",
                        source_id=source_id,
                        state="accepted",
                        canonical_target_id=team_id + 1_000_000,
                        expected_predecessor_mapping_id=pending.id,
                    ),
                )
            assert pending.valid_to is None
            accepted = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="decide",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="accepted",
                    canonical_target_id=team_id,
                    expected_predecessor_mapping_id=pending.id,
                    selected_candidate_id=candidate.id,
                ),
            )
            assert accepted.predecessor_mapping_id == pending.id
            assert accepted.selected_candidate_id == candidate.id
    finally:
        async with sessions() as session, session.begin():
            mapping_ids = list(
                (
                    await session.scalars(
                        select(TeamProviderMapping.id).where(TeamProviderMapping.source_id == source_id)
                    )
                ).all()
            )
            if mapping_ids:
                await session.execute(
                    update(TeamProviderMapping)
                    .where(TeamProviderMapping.id.in_(mapping_ids))
                    .values(selected_candidate_id=None)
                )
                await session.execute(
                    delete(TeamProviderMappingCandidate).where(TeamProviderMappingCandidate.mapping_id.in_(mapping_ids))
                )
                await session.execute(delete(TeamProviderMapping).where(TeamProviderMapping.id.in_(mapping_ids)))
            await session.execute(delete(Team).where(Team.display_name == source_id))
        await engine.dispose()


async def test_database_rejects_selected_candidate_from_other_predecessor_or_target() -> None:
    """The composite FK protects raw writes that bypass the command service."""
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-db-candidate-{uuid4()}"
    other_source_id = f"g002-db-candidate-other-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            teams = [
                Team(sport="football", display_name=f"{source_id}-{suffix}", normalized_name=f"{source_id}-{suffix}")
                for suffix in ("accepted", "mismatch")
            ]
            session.add_all(teams)
            await session.flush()
            pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                ),
            )
            candidate = await add_identity_candidate(
                session,
                IdentityCandidateProposal(
                    entity_type="team",
                    mapping_id=pending.id,
                    canonical_target_id=teams[0].id,
                    rank=1,
                    confidence=Decimal("0.9000"),
                    evidence={"rule": "exact"},
                ),
            )
            accepted = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="decide",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="accepted",
                    canonical_target_id=teams[0].id,
                    expected_predecessor_mapping_id=pending.id,
                    selected_candidate_id=candidate.id,
                ),
            )
            other_pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=other_source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                ),
            )
            other_candidate = await add_identity_candidate(
                session,
                IdentityCandidateProposal(
                    entity_type="team",
                    mapping_id=other_pending.id,
                    canonical_target_id=teams[0].id,
                    rank=1,
                    confidence=Decimal("0.8000"),
                    evidence={"rule": "other"},
                ),
            )

        async with sessions() as session, session.begin():
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        update(TeamProviderMapping)
                        .where(TeamProviderMapping.id == accepted.id)
                        .values(predecessor_mapping_id=None)
                    )
                    await session.flush()
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        update(TeamProviderMapping)
                        .where(TeamProviderMapping.id == accepted.id)
                        .values(selected_candidate_id=other_candidate.id)
                    )
                    await session.flush()
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        update(TeamProviderMapping)
                        .where(TeamProviderMapping.id == accepted.id)
                        .values(team_id=teams[1].id)
                    )
                    await session.flush()
        async with sessions() as session:
            persisted = await session.get(TeamProviderMapping, accepted.id)
            assert persisted is not None
            assert (persisted.predecessor_mapping_id, persisted.team_id, persisted.selected_candidate_id) == (
                pending.id,
                teams[0].id,
                candidate.id,
            )
    finally:
        await _delete_team_lineage(sessions, source_id, delete_teams=False)
        await _delete_team_lineage(sessions, other_source_id, delete_teams=False)
        async with sessions() as session, session.begin():
            await session.execute(
                delete(Team).where(
                    Team.display_name.like(f"{source_id}%") | Team.display_name.like(f"{other_source_id}%")
                )
            )
        await engine.dispose()


async def test_postgres_restricts_canonical_team_and_evidence_observation_deletion() -> None:
    """Canonical targets and evidence facts remain undeletable while history references them."""
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source_id = f"g002-restrict-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            observation = await persist_provider_envelope(
                session,
                _envelope(source_id, home_goals=1.1, run_id="restrict-evidence"),
                now=datetime(2026, 8, 1, 13, tzinfo=UTC),
            )
            team = Team(sport="football", display_name=source_id, normalized_name=source_id)
            session.add(team)
            await session.flush()
            pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                    evidence_observation_id=observation.id,
                ),
            )
            accepted = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="decide",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="accepted",
                    canonical_target_id=team.id,
                    expected_predecessor_mapping_id=pending.id,
                    evidence_observation_id=observation.id,
                ),
            )
            team_id, observation_id = team.id, observation.id
            assert accepted.evidence_observation_id == observation_id

        async with sessions() as session, session.begin():
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(delete(Team).where(Team.id == team_id))
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    # Remove the receipt only inside this savepoint so the FK failure
                    # below is specifically against mapping evidence history.
                    await session.execute(
                        delete(ProviderObservationReceipt).where(
                            ProviderObservationReceipt.observation_id == observation_id
                        )
                    )
                    await session.execute(delete(ProviderObservation).where(ProviderObservation.id == observation_id))
    finally:
        await _delete_team_lineage(sessions, source_id)
        await _delete_observation_lineage(sessions, source_id)
        await engine.dispose()


async def test_cleanup_plan_breaks_selected_candidate_cycle_before_deleting_history() -> None:
    """The real cleanup executor clears selection FKs before candidate and mapping deletes."""
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    namespace = f"1752481234567-{uuid4().hex[:8]}"
    source_id = f"g002-cleanup-cycle-{uuid4()}"

    try:
        async with sessions() as session, session.begin():
            team = Team(sport="football", display_name=source_id, normalized_name=source_id)
            session.add(team)
            await session.flush()
            pending = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="propose",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="pending_review",
                    canonical_target_id=None,
                    expected_predecessor_mapping_id=None,
                ),
            )
            candidate = await add_identity_candidate(
                session,
                IdentityCandidateProposal(
                    entity_type="team",
                    mapping_id=pending.id,
                    canonical_target_id=team.id,
                    rank=1,
                    confidence=Decimal("0.9000"),
                    evidence={"rule": "cleanup-cycle"},
                ),
            )
            accepted = await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type="team",
                    command_kind="decide",
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id=source_id,
                    state="accepted",
                    canonical_target_id=team.id,
                    expected_predecessor_mapping_id=pending.id,
                    selected_candidate_id=candidate.id,
                ),
            )

        plan = CleanupPlan(namespaces={namespace})
        plan.add_ids("provider_team_mapping_candidates", [candidate.id])
        plan.add_ids("provider_team_mappings", [pending.id, accepted.id])
        async with sessions() as session, session.begin():
            deleted = await apply_cleanup_plan(session, plan)
        assert deleted == {"provider_team_mapping_candidates": 1, "provider_team_mappings": 2}
        async with sessions() as session:
            assert await session.get(TeamProviderMappingCandidate, candidate.id) is None
            assert await session.get(TeamProviderMapping, pending.id) is None
            assert await session.get(TeamProviderMapping, accepted.id) is None
    finally:
        await _delete_team_lineage(sessions, source_id)
        await engine.dispose()
