"""PostgreSQL trust boundary for governed prediction/ticket lineage."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import Match, ModelArtifact, ModelPrediction, PredictionRun
from app.models.ticket import Ticket, TicketLeg

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [pytest.mark.asyncio]


async def _governed_lineage(session: AsyncSession):
    """Create only the P4 records required by the database lineage checks."""
    from test_model_artifact_postgres import _lineage

    generation, feature, version = await _lineage(session, published=True)
    artifact = ModelArtifact(
        artifact_key=uuid4().hex * 2,
        artifact_digest="a" * 64,
        model_version_id=version.id,
        source_generation_id=generation.id,
        feature_set_id=feature.id,
        artifact_kind="prediction_manifest",
        state="completed",
        manifest_json={},
        runtime_dependency_fingerprint="3" * 64,
        expected_row_count=1,
        written_row_count=1,
        expected_output_count=1,
        written_output_count=1,
    )
    session.add(artifact)
    await session.flush()
    now = datetime.now(UTC)
    match = Match(
        external_id=f"g005-delete-{uuid4().hex}",
        home_team="Home",
        away_team="Away",
        status="scheduled",
        match_date=now + timedelta(days=1),
    )
    session.add(match)
    await session.flush()
    run = PredictionRun(
        model_type="PoissonGoalsModel",
        status="completed",
        model_version_id=version.id,
        model_artifact_id=artifact.id,
        source_generation_id=generation.id,
        forecast_at=now,
        output_fingerprint="b" * 64,
        strategy_config_hash="1" * 64,
        training_data_fingerprint="2" * 64,
        pipeline_contract_version="penaltyblog-model-pipeline/v1",
    )
    session.add(run)
    await session.flush()
    prediction = ModelPrediction(
        run_id=run.id,
        model_type="PoissonGoalsModel",
        match_id=match.id,
        market="1x2",
    )
    ticket = Ticket(ticket_type="single", stake=10, total_odds=2, potential_return=20, status="open")
    session.add_all([prediction, ticket])
    await session.flush()
    session.add(
        TicketLeg(
            ticket_id=ticket.id,
            model_prediction_id=prediction.id,
            match_id=match.id,
            selection="home",
            market="1x2",
            odds=2,
            prediction_run_id_snapshot=run.id,
        )
    )
    await session.flush()
    return run


@pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL")
async def test_governed_prediction_run_delete_is_blocked_when_ticket_leg_keeps_lineage():
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        run = await _governed_lineage(session)
        with pytest.raises(DBAPIError, match="governed prediction run cannot be deleted"):
            await session.execute(delete(PredictionRun).where(PredictionRun.id == run.id))
        if transaction.is_active:
            await transaction.rollback()
    await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL")
async def test_snapshot_fk_blocks_concurrent_ticket_leg_insert_and_run_delete_race():
    """The FK key-share lock closes the gap before the 037 trigger can see an insert."""
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    run_id = prediction_id = match_id = ticket_id = None
    try:
        async with engine.connect() as setup_connection:
            setup_transaction = await setup_connection.begin()
            setup_session = AsyncSession(bind=setup_connection, expire_on_commit=False)
            match = Match(
                external_id=f"g005-race-{uuid4().hex}",
                home_team="Race Home",
                away_team="Race Away",
                status="scheduled",
                match_date=datetime.now(UTC) + timedelta(days=1),
            )
            run = PredictionRun(model_type="legacy-race", status="completed")
            setup_session.add_all([match, run])
            await setup_session.flush()
            prediction = ModelPrediction(
                run_id=run.id,
                model_type="legacy-race",
                match_id=match.id,
                market="1x2",
            )
            setup_session.add(prediction)
            await setup_session.flush()
            run_id, prediction_id, match_id = run.id, prediction.id, match.id
            await setup_transaction.commit()

        async with engine.connect() as insert_connection, engine.connect() as delete_connection:
            insert_transaction = await insert_connection.begin()
            delete_transaction = await delete_connection.begin()
            insert_session = AsyncSession(bind=insert_connection, expire_on_commit=False)
            ticket = Ticket(ticket_type="single", stake=10, total_odds=2, potential_return=20, status="open")
            insert_session.add(ticket)
            await insert_session.flush()
            ticket_id = ticket.id
            insert_session.add(
                TicketLeg(
                    ticket_id=ticket.id,
                    model_prediction_id=prediction_id,
                    match_id=match_id,
                    selection="home",
                    market="1x2",
                    odds=2,
                    prediction_run_id_snapshot=run_id,
                )
            )
            await insert_session.flush()
            await delete_connection.execute(text("SET LOCAL lock_timeout = '250ms'"))
            with pytest.raises(DBAPIError, match="lock timeout"):
                await delete_connection.execute(delete(PredictionRun).where(PredictionRun.id == run_id))
            if delete_transaction.is_active:
                await delete_transaction.rollback()
            if insert_transaction.is_active:
                await insert_transaction.rollback()
    finally:
        if run_id is not None:
            async with engine.begin() as cleanup_connection:
                await cleanup_connection.execute(delete(TicketLeg).where(TicketLeg.ticket_id == ticket_id))
                await cleanup_connection.execute(delete(Ticket).where(Ticket.id == ticket_id))
                await cleanup_connection.execute(delete(PredictionRun).where(PredictionRun.id == run_id))
                await cleanup_connection.execute(delete(Match).where(Match.id == match_id))
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL")
async def test_snapshot_fk_is_not_validated_for_legacy_orphans_but_enforces_new_lineage():
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    async with engine.connect() as connection:
        validated = await connection.scalar(
            text("SELECT convalidated FROM pg_constraint WHERE conname = 'fk_ticket_legs_prediction_run_snapshot'")
        )
        assert validated is False
    await engine.dispose()


class _EndpointResult:
    def __init__(self, scalar):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _EndpointSession:
    def __init__(self, run, retained_leg):
        self.run = run
        self.retained_leg = retained_leg
        self.deleted = []

    async def execute(self, _statement):
        return _EndpointResult(self.run)

    async def scalar(self, _statement):
        return self.retained_leg

    async def delete(self, value):
        self.deleted.append(value)

    async def flush(self):
        raise AssertionError("retained runs must not reach deletion")


async def test_prediction_run_delete_endpoint_returns_conflict_for_any_retained_ticket_leg():
    from app.api.v1.predictions import delete_prediction_run

    run = type("Run", (), {"id": 71, "user_id": 5})()
    db = _EndpointSession(run, retained_leg=91)
    with pytest.raises(HTTPException) as exc_info:
        await delete_prediction_run(run_id=71, db=db, user=type("User", (), {"id": 5})())

    assert exc_info.value.status_code == 409
    assert "ticket-leg lineage" in exc_info.value.detail
    assert db.deleted == []
