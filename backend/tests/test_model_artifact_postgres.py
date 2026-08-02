"""PostgreSQL-only database gates for the governed model artifact pipeline."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import (
    Match,
    MatchProviderMapping,
    ModelArtifact,
    ModelEvaluationFold,
    ModelEvaluationPrediction,
    ModelFeatureSet,
    ModelPrediction,
    ModelVersion,
    OddsEntry,
    OddsSnapshot,
    PredictionRun,
    ProviderDatasetGeneration,
    ProviderDatasetGenerationPage,
    ProviderObservation,
    ProviderObservationDatasetLink,
    ProviderObservationSlot,
    ScrapedDataset,
)
from app.schemas.model_pipeline import (
    BacktestModelCommandV1,
    FeatureSetSpecV1,
    ModelConfigV1,
    PredictionTargetV1,
    PredictModelCommandV1,
    TrainModelCommandV1,
)
from app.services.model_artifacts import ModelArtifactError, load_canonical_model_input, model_fingerprint
from app.services.model_governance import _pipeline_prediction_output_is_complete
from app.services.model_pipeline import backtest_model, predict_model, train_model

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL"),
]


async def _lineage(session: AsyncSession, *, published: bool):
    suffix = uuid4().hex
    now = datetime.now(UTC)
    generation = ProviderDatasetGeneration(
        generation_key=("a" if published else "b") * 32 + suffix[:32],
        dataset_group_key=("c" if published else "d") * 32 + suffix[:32],
        artifact_digest="e" * 64,
        state="published" if published else "staged",
        terminal_page=0,
        source_as_of=now - timedelta(days=1),
        fresh_until=now + timedelta(days=1),
    )
    feature = ModelFeatureSet(
        feature_key=f"g005-{suffix}",
        version="v1",
        schema_version="football-goals-features/v1",
        spec_json={},
        spec_fingerprint="f" * 64,
    )
    session.add_all([generation, feature])
    await session.flush()
    version = ModelVersion(
        model_key=f"PoissonGoalsModel-{suffix}",
        version="v1",
        build_revision="d" * 40,
        engine_version="1.11.0",
        feature_set_id=feature.id,
        feature_schema_hash="f" * 64,
        strategy_config_hash="1" * 64,
        training_data_fingerprint="2" * 64,
        training_cutoff_at=now - timedelta(days=2),
        runtime_dependency_fingerprint="3" * 64,
    )
    session.add(version)
    await session.flush()
    return generation, feature, version


async def test_model_artifact_trigger_rejects_unpublished_generation():
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        generation, feature, version = await _lineage(session, published=False)
        session.add(
            ModelArtifact(
                artifact_key="4" * 64,
                artifact_digest="5" * 64,
                model_version_id=version.id,
                source_generation_id=generation.id,
                feature_set_id=feature.id,
                artifact_kind="training_manifest",
                state="completed",
                manifest_json={},
                runtime_dependency_fingerprint="3" * 64,
                expected_row_count=1,
                written_row_count=1,
                expected_output_count=1,
                written_output_count=1,
            )
        )
        with pytest.raises(DBAPIError, match="published provider dataset generation"):
            await session.flush()
        if transaction.is_active:
            await transaction.rollback()
    await engine.dispose()


async def test_completed_artifact_and_pipeline_run_are_database_fail_closed():
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        generation, feature, version = await _lineage(session, published=True)
        session.add(
            ModelArtifact(
                artifact_key="6" * 64,
                artifact_digest="7" * 64,
                model_version_id=version.id,
                source_generation_id=generation.id,
                feature_set_id=feature.id,
                artifact_kind="training_manifest",
                state="completed",
                manifest_json={},
                runtime_dependency_fingerprint="3" * 64,
                expected_row_count=2,
                written_row_count=1,
                expected_output_count=1,
                written_output_count=1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        if transaction.is_active:
            await transaction.rollback()

    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        session.add(
            PredictionRun(
                model_type="PoissonGoalsModel",
                status="completed",
                pipeline_contract_version="penaltyblog-model-pipeline/v1",
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        if transaction.is_active:
            await transaction.rollback()
    await engine.dispose()


async def test_model_artifact_trigger_allows_staged_writes_but_freezes_terminal_rows():
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        generation, feature, version = await _lineage(session, published=True)
        artifact = ModelArtifact(
            artifact_key="8" * 64,
            artifact_digest="9" * 64,
            model_version_id=version.id,
            source_generation_id=generation.id,
            feature_set_id=feature.id,
            artifact_kind="training_manifest",
            state="staged",
            manifest_json={},
            runtime_dependency_fingerprint="3" * 64,
            expected_row_count=1,
            written_row_count=0,
            expected_output_count=1,
            written_output_count=0,
        )
        session.add(artifact)
        await session.flush()
        await session.execute(
            update(ModelArtifact)
            .where(ModelArtifact.id == artifact.id)
            .values(written_row_count=1, written_output_count=1, state="completed")
        )
        await session.flush()
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                update(ModelArtifact).where(ModelArtifact.id == artifact.id).values(artifact_digest="a" * 64)
            )
        if transaction.is_active:
            await transaction.rollback()
    await engine.dispose()


@pytest.mark.parametrize("terminal_state", ["completed", "failed"])
async def test_model_artifact_trigger_rejects_terminal_deletion(terminal_state):
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        generation, feature, version = await _lineage(session, published=True)
        complete = terminal_state == "completed"
        artifact = ModelArtifact(
            artifact_key=hashlib.sha256(f"delete:{terminal_state}:{uuid4()}".encode()).hexdigest(),
            artifact_digest="9" * 64,
            model_version_id=version.id,
            source_generation_id=generation.id,
            feature_set_id=feature.id,
            artifact_kind="training_manifest",
            state=terminal_state,
            manifest_json={},
            runtime_dependency_fingerprint="3" * 64,
            expected_row_count=1,
            written_row_count=1 if complete else 0,
            expected_output_count=1,
            written_output_count=1 if complete else 0,
        )
        session.add(artifact)
        await session.flush()
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(delete(ModelArtifact).where(ModelArtifact.id == artifact.id))
        if transaction.is_active:
            await transaction.rollback()
    await engine.dispose()


async def test_canonical_model_input_is_generation_bound_and_observation_time_safe(tmp_path):
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        suffix = uuid4().hex
        acquired_at = datetime(2026, 1, 10, tzinfo=UTC)
        cutoff = datetime(2025, 6, 1, tzinfo=UTC)
        dataset = ScrapedDataset(
            name=f"g005:{suffix}",
            source="soccerdata",
            data={},
            matches_count=1,
            dataset_key="8" * 32 + suffix[:32],
            dataset_group_key="9" * 32 + suffix[:32],
            dataset_schema_version="soccerdata/v1",
            dataset_digest="a" * 64,
            publication_state="published",
            source_as_of=acquired_at,
            fresh_until=acquired_at + timedelta(days=1),
        )
        generation = ProviderDatasetGeneration(
            generation_key="b" * 32 + suffix[:32],
            dataset_group_key=dataset.dataset_group_key,
            artifact_digest="a" * 64,
            state="published",
            terminal_page=0,
            source_as_of=acquired_at,
            fresh_until=acquired_at + timedelta(days=1),
        )
        slot = ProviderObservationSlot(observation_slot_key="c" * 32 + suffix[:32])
        match = Match(
            external_id=f"g005-{suffix}",
            home_team="A",
            away_team="B",
            home_score=1,
            away_score=0,
            status="finished",
            match_date=datetime(2025, 1, 2, tzinfo=UTC),
        )
        session.add_all([dataset, generation, slot, match])
        await session.flush()
        session.add(ProviderDatasetGenerationPage(generation_id=generation.id, page=0, dataset_id=dataset.id))
        payload = {
            "date": "2025-01-02T00:00:00Z",
            "team_home": "A",
            "team_away": "B",
            "goals_home": 1,
            "goals_away": 0,
        }
        observation = ProviderObservation(
            slot_id=slot.id,
            adapter_key="soccerdata",
            source_key="football-data-co-uk",
            capability="results",
            source_id=f"event-{suffix}",
            envelope_version="2.0",
            original_envelope_version="2.0",
            schema_version="soccerdata/v1",
            converted_from_v1=False,
            observed_at=acquired_at,
            freshness_json="{}",
            provenance_json="{}",
            payload_json=json.dumps(payload),
            envelope_json=json.dumps({"payload": payload}),
            payload_digest="d" * 64,
            envelope_digest="e" * 64,
            observation_key="f" * 32 + suffix[:32],
            observation_slot_key=slot.observation_slot_key,
            normalization_state="normalized",
            conflict_state="clear",
            body_retention_until=acquired_at + timedelta(days=365),
        )
        session.add(observation)
        await session.flush()
        session.add_all(
            [
                ProviderObservationDatasetLink(observation_id=observation.id, dataset_id=dataset.id),
                MatchProviderMapping(
                    adapter_key=observation.adapter_key,
                    source_key=observation.source_key,
                    source_id=observation.source_id,
                    state="accepted",
                    confidence=1,
                    resolver_kind="g005-test",
                    rule_version="v1",
                    decision_digest="1" * 32 + suffix[:32],
                    evidence_observation_id=observation.id,
                    valid_from=datetime(2024, 1, 1, tzinfo=UTC),
                    match_id=match.id,
                ),
            ]
        )
        await session.flush()

        with pytest.raises(ModelArtifactError, match="observation occurs after"):
            await load_canonical_model_input(
                session,
                generation_id=generation.id,
                feature_set=FeatureSetSpecV1(),
                training_cutoff_at=cutoff,
                freshness_mode="historical",
                now=acquired_at,
            )
        observation.observed_at = datetime(2025, 1, 1, tzinfo=UTC)
        await session.flush()
        with pytest.raises(ModelArtifactError, match="predates its fixture"):
            await load_canonical_model_input(
                session,
                generation_id=generation.id,
                feature_set=FeatureSetSpecV1(),
                training_cutoff_at=cutoff,
                freshness_mode="historical",
                now=acquired_at,
            )
        observation.observed_at = datetime(2025, 1, 3, tzinfo=UTC)
        await session.flush()
        first = await load_canonical_model_input(
            session,
            generation_id=generation.id,
            feature_set=FeatureSetSpecV1(),
            training_cutoff_at=cutoff,
            freshness_mode="historical",
            now=acquired_at,
        )
        second = await load_canonical_model_input(
            session,
            generation_id=generation.id,
            feature_set=FeatureSetSpecV1(),
            training_cutoff_at=cutoff,
            freshness_mode="historical",
            now=acquired_at,
        )
        assert first.training_data_fingerprint == second.training_data_fingerprint
        assert first.match_ids == (match.id,)
        observation.observed_at = datetime(2025, 1, 1, tzinfo=UTC)
        await session.flush()
        with pytest.raises(ModelArtifactError, match="result observation predates"):
            await load_canonical_model_input(
                session,
                generation_id=generation.id,
                feature_set=FeatureSetSpecV1(),
                training_cutoff_at=cutoff,
                freshness_mode="historical",
                now=acquired_at,
            )
        observation.observed_at = datetime(2025, 1, 3, tzinfo=UTC)
        await session.flush()
        with pytest.raises(ModelArtifactError, match="observation cutoff must equal"):
            await load_canonical_model_input(
                session,
                generation_id=generation.id,
                feature_set=FeatureSetSpecV1(),
                training_cutoff_at=cutoff,
                freshness_mode="historical",
                observation_cutoff_at=acquired_at,
                now=acquired_at,
            )

        runtime = {
            "runtime_version": "penaltyblog-model-runtime/v1",
            "python_version": "3.13.1",
            "penaltyblog_version": "1.11.0",
            "penaltyblog_revision": "d" * 40,
            "numpy_version": "2.0.0",
            "scipy_version": "1.14.0",
            "pandas_version": "2.2.0",
            "lock_digest": "2" * 64,
            "image_digest": None,
            "blas_threads": 1,
            "thread_environment": {
                "OMP_NUM_THREADS": 1,
                "OPENBLAS_NUM_THREADS": 1,
                "MKL_NUM_THREADS": 1,
                "NUMEXPR_NUM_THREADS": 1,
            },
            "reproducible_model_allowlist": ["PoissonGoalsModel"],
        }
        runtime["runtime_fingerprint"] = model_fingerprint(runtime)
        train_calls = 0
        prediction_payloads: list[dict] = []

        async def fake_bridge(request):
            nonlocal train_calls
            operation, bridge_payload = request["operation"], request["payload"]
            if operation == "runtime_info":
                result = runtime
            elif operation == "model_train":
                train_calls += 1
                artifact_path = tmp_path / bridge_payload["artifact_path"]
                artifact_path.write_bytes(b"trusted-pickle-fixture")
                result = {
                    "training_rows": len(bridge_payload["matches"]),
                    "runtime_fingerprint": runtime["runtime_fingerprint"],
                    "artifact_digest": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                    "params_digest": "3" * 64,
                    "model_class": bridge_payload["model_config"]["model_class"],
                    "artifact_path": bridge_payload["artifact_path"],
                    "model_config_digest": bridge_payload["expected_model_config_digest"],
                    "training_data_digest": bridge_payload["expected_training_data_digest"],
                }
            elif operation == "model_predict_batch":
                prediction_payloads.append(bridge_payload)
                result = {
                    "runtime_fingerprint": runtime["runtime_fingerprint"],
                    "artifact_digest": bridge_payload["expected_artifact_digest"],
                    "prediction_count": len(bridge_payload["targets"]),
                    "predictions": [{"homeWin": 0.5, "draw": 0.25, "awayWin": 0.25}],
                }
            else:
                raise AssertionError(operation)
            return {"operation": operation, "result": result}

        command = TrainModelCommandV1(
            source_generation_id=generation.id,
            model_spec=ModelConfigV1(model_class="PoissonGoalsModel"),
            model_version=f"g005-{suffix}",
            training_cutoff_at=cutoff,
        )
        trained = await train_model(
            session,
            command,
            artifact_root=tmp_path,
            bridge=fake_bridge,
            now=acquired_at,
        )
        replayed = await train_model(
            session,
            command,
            artifact_root=tmp_path,
            bridge=fake_bridge,
            now=acquired_at,
        )
        assert trained.id == replayed.id
        assert trained.state == "completed"
        assert trained.manifest_json["training_data_fingerprint"] == first.training_data_fingerprint
        assert train_calls == 1

        forecast_at = acquired_at + timedelta(hours=1)
        kickoff_at = acquired_at + timedelta(hours=12)
        fixture_dataset = ScrapedDataset(
            name=f"g005-fixture:{suffix}",
            source="soccerdata",
            data={},
            matches_count=1,
            dataset_key="4" * 32 + suffix[:32],
            dataset_group_key="5" * 32 + suffix[:32],
            dataset_schema_version="soccerdata/v1",
            dataset_digest="6" * 64,
            publication_state="published",
            source_as_of=acquired_at,
            fresh_until=acquired_at + timedelta(days=1),
        )
        fixture_generation = ProviderDatasetGeneration(
            generation_key="7" * 32 + suffix[:32],
            dataset_group_key=fixture_dataset.dataset_group_key,
            artifact_digest="6" * 64,
            state="published",
            terminal_page=0,
            source_as_of=acquired_at,
            fresh_until=acquired_at + timedelta(days=1),
        )
        fixture_slot = ProviderObservationSlot(observation_slot_key="8" * 32 + suffix[:32])
        upcoming = Match(
            external_id=f"g005-upcoming-{suffix}",
            home_team="A",
            away_team="B",
            status="scheduled",
            match_date=kickoff_at,
        )
        session.add_all([fixture_dataset, fixture_generation, fixture_slot, upcoming])
        await session.flush()
        session.add(
            ProviderDatasetGenerationPage(
                generation_id=fixture_generation.id,
                page=0,
                dataset_id=fixture_dataset.id,
            )
        )
        fixture_payload = {
            "date": kickoff_at.isoformat(),
            "team_home": "A",
            "team_away": "B",
            "league": "Canonical League",
        }
        fixture_observation = ProviderObservation(
            slot_id=fixture_slot.id,
            adapter_key="soccerdata",
            source_key="espn",
            capability="fixtures",
            source_id=f"fixture-{suffix}",
            envelope_version="2.0",
            original_envelope_version="2.0",
            schema_version="soccerdata/v1",
            converted_from_v1=False,
            observed_at=acquired_at,
            freshness_json="{}",
            provenance_json="{}",
            payload_json=json.dumps(fixture_payload),
            envelope_json=json.dumps({"payload": fixture_payload}),
            payload_digest="9" * 64,
            envelope_digest="a" * 64,
            observation_key="b" * 32 + suffix[:32],
            observation_slot_key=fixture_slot.observation_slot_key,
            normalization_state="normalized",
            conflict_state="clear",
            body_retention_until=acquired_at + timedelta(days=365),
        )
        session.add(fixture_observation)
        await session.flush()
        session.add_all(
            [
                ProviderObservationDatasetLink(
                    observation_id=fixture_observation.id,
                    dataset_id=fixture_dataset.id,
                ),
                MatchProviderMapping(
                    adapter_key=fixture_observation.adapter_key,
                    source_key=fixture_observation.source_key,
                    source_id=fixture_observation.source_id,
                    state="accepted",
                    confidence=1,
                    resolver_kind="g005-test",
                    rule_version="v1",
                    decision_digest="c" * 32 + suffix[:32],
                    evidence_observation_id=fixture_observation.id,
                    valid_from=acquired_at,
                    match_id=upcoming.id,
                ),
            ]
        )
        await session.flush()
        snapshot = OddsSnapshot(
            match_id=upcoming.id,
            source="g005-test",
            source_key=f"quote-{suffix}",
            observed_at=acquired_at + timedelta(minutes=30),
            quality="complete",
        )
        session.add(snapshot)
        await session.flush()
        entry = OddsEntry(
            match_id=upcoming.id,
            odds_snapshot_id=snapshot.id,
            bookmaker="g005-test",
            market="1x2",
            home_odds=2.0,
            draw_odds=3.0,
            away_odds=4.0,
            timestamp=snapshot.observed_at,
        )
        session.add(entry)
        await session.flush()
        prediction_command = PredictModelCommandV1(
            model_artifact_id=trained.id,
            source_generation_id=fixture_generation.id,
            targets=(
                PredictionTargetV1(
                    match_id=upcoming.id,
                    home_team="A",
                    away_team="B",
                    forecast_at=forecast_at,
                    kickoff_at=kickoff_at,
                    odds_snapshot_id=snapshot.id,
                    odds_entry_id=entry.id,
                ),
            ),
        )
        prediction_run = await predict_model(
            session,
            prediction_command,
            artifact_root=tmp_path,
            bridge=fake_bridge,
            now=forecast_at,
        )
        persisted_prediction = await session.scalar(
            select(ModelPrediction).where(ModelPrediction.run_id == prediction_run.id)
        )
        assert prediction_run.status == "completed"
        assert prediction_run.output_fingerprint is not None
        assert persisted_prediction is not None
        assert persisted_prediction.odds_snapshot_id == snapshot.id
        assert persisted_prediction.model_version_id == trained.model_version_id
        assert persisted_prediction.quality_report["canonical_fixture"] == {
            "match_id": upcoming.id,
            "home_team": "A",
            "away_team": "B",
            "kickoff_at": kickoff_at.isoformat(),
            "competition_key": "Canonical League",
        }
        # P4 prediction evidence is pinned: mutable operational fixture fields
        # cannot change output governance or candidate identity.
        upcoming.home_team = "mutated home"
        upcoming.away_team = "mutated away"
        upcoming.match_date = forecast_at - timedelta(minutes=1)
        upcoming.competition = "mutated competition"
        await session.flush()
        assert await _pipeline_prediction_output_is_complete(session, prediction_run, trained.model_version_id)
        # A valid-looking fixture is not trusted independently from the run's
        # exact output attestation; otherwise league exposure could be edited.
        original_report = dict(persisted_prediction.quality_report)
        tampered_fixture = dict(original_report["canonical_fixture"])
        tampered_fixture["competition_key"] = "Tampered League"
        persisted_prediction.quality_report = {**original_report, "canonical_fixture": tampered_fixture}
        await session.flush()
        assert not await _pipeline_prediction_output_is_complete(session, prediction_run, trained.model_version_id)
        persisted_prediction.quality_report = original_report
        await session.flush()
        delayed_run = await predict_model(
            session,
            prediction_command,
            artifact_root=tmp_path,
            bridge=fake_bridge,
            now=forecast_at + timedelta(seconds=1),
        )
        assert delayed_run.forecast_at == forecast_at + timedelta(seconds=1)
        assert prediction_command.targets[0].forecast_at == forecast_at

        evaluation_dataset = ScrapedDataset(
            name=f"g005-evaluation:{suffix}",
            source="soccerdata",
            data={},
            matches_count=2,
            dataset_key="d" * 32 + suffix[:32],
            dataset_group_key="e" * 32 + suffix[:32],
            dataset_schema_version="soccerdata/v1",
            dataset_digest="f" * 64,
            publication_state="published",
            source_as_of=datetime(2025, 6, 30, tzinfo=UTC),
            fresh_until=datetime(2025, 7, 4, tzinfo=UTC),
        )
        evaluation_generation = ProviderDatasetGeneration(
            generation_key="0" * 32 + suffix[:32],
            dataset_group_key=evaluation_dataset.dataset_group_key,
            artifact_digest="f" * 64,
            state="published",
            terminal_page=0,
            source_as_of=evaluation_dataset.source_as_of,
            fresh_until=evaluation_dataset.fresh_until,
        )
        evaluation_slot = ProviderObservationSlot(observation_slot_key="1" * 32 + suffix[:32])
        evaluated_match = Match(
            external_id=f"g005-evaluated-{suffix}",
            home_team="C",
            away_team="D",
            home_score=2,
            away_score=1,
            status="finished",
            match_date=datetime(2025, 7, 2, tzinfo=UTC),
        )
        session.add_all([evaluation_dataset, evaluation_generation, evaluation_slot, evaluated_match])
        await session.flush()
        session.add(
            ProviderDatasetGenerationPage(
                generation_id=evaluation_generation.id,
                page=0,
                dataset_id=evaluation_dataset.id,
            )
        )
        result_payload = {
            "date": "2025-07-02T00:00:00Z",
            "team_home": "C",
            "team_away": "D",
            "goals_home": 2,
            "goals_away": 1,
        }
        result_observation = ProviderObservation(
            slot_id=evaluation_slot.id,
            adapter_key="soccerdata",
            source_key="football-data-co-uk",
            capability="results",
            source_id=f"evaluated-{suffix}",
            envelope_version="2.0",
            original_envelope_version="2.0",
            schema_version="soccerdata/v1",
            converted_from_v1=False,
            observed_at=datetime(2025, 7, 3, tzinfo=UTC),
            freshness_json="{}",
            provenance_json="{}",
            payload_json=json.dumps(result_payload),
            envelope_json=json.dumps({"payload": result_payload}),
            payload_digest="2" * 64,
            envelope_digest="3" * 64,
            observation_key="4" * 32 + suffix[:32],
            observation_slot_key=evaluation_slot.observation_slot_key,
            normalization_state="normalized",
            conflict_state="clear",
            body_retention_until=datetime(2027, 1, 1, tzinfo=UTC),
        )
        session.add(result_observation)
        await session.flush()
        session.add_all(
            [
                ProviderObservationDatasetLink(observation_id=observation.id, dataset_id=evaluation_dataset.id),
                ProviderObservationDatasetLink(
                    observation_id=result_observation.id,
                    dataset_id=evaluation_dataset.id,
                ),
                MatchProviderMapping(
                    adapter_key=result_observation.adapter_key,
                    source_key=result_observation.source_key,
                    source_id=result_observation.source_id,
                    state="accepted",
                    confidence=1,
                    resolver_kind="g005-test",
                    rule_version="v1",
                    decision_digest="5" * 32 + suffix[:32],
                    evidence_observation_id=result_observation.id,
                    valid_from=datetime(2025, 1, 1, tzinfo=UTC),
                    match_id=evaluated_match.id,
                ),
            ]
        )
        await session.flush()
        evaluation_snapshot = OddsSnapshot(
            match_id=evaluated_match.id,
            source="g005-test",
            source_key=f"evaluation-quote-{suffix}",
            observed_at=datetime(2025, 7, 1, tzinfo=UTC),
            quality="complete",
        )
        session.add(evaluation_snapshot)
        await session.flush()
        evaluation_entry = OddsEntry(
            match_id=evaluated_match.id,
            odds_snapshot_id=evaluation_snapshot.id,
            bookmaker="g005-test",
            market="1x2",
            home_odds=2.0,
            draw_odds=3.0,
            away_odds=4.0,
            timestamp=evaluation_snapshot.observed_at,
        )
        session.add(evaluation_entry)
        await session.flush()
        evaluated_match.home_team = "mutable-home"
        evaluated_match.away_team = "mutable-away"
        evaluated_match.match_date = datetime(2030, 1, 1, tzinfo=UTC)
        evaluated_match.home_score = 0
        evaluated_match.away_score = 3
        await session.flush()
        backtest_command = BacktestModelCommandV1(
            model_artifact_id=trained.id,
            source_generation_id=evaluation_generation.id,
            model_spec=ModelConfigV1(model_class="PoissonGoalsModel"),
            training_cutoff_at=cutoff,
            test_started_at=datetime(2025, 6, 15, tzinfo=UTC),
            test_ended_at=datetime(2025, 8, 1, tzinfo=UTC),
            targets=(
                PredictionTargetV1(
                    match_id=evaluated_match.id,
                    home_team="C",
                    away_team="D",
                    forecast_at=datetime(2025, 7, 1, tzinfo=UTC),
                    kickoff_at=datetime(2025, 7, 2, tzinfo=UTC),
                    odds_snapshot_id=evaluation_snapshot.id,
                    odds_entry_id=evaluation_entry.id,
                ),
            ),
        )
        result_observation.observed_at = datetime(2025, 7, 1, tzinfo=UTC)
        await session.flush()
        with pytest.raises(ModelArtifactError, match="result observation predates"):
            await backtest_model(
                session,
                backtest_command,
                artifact_root=tmp_path,
                bridge=fake_bridge,
                now=acquired_at,
            )
        result_observation.observed_at = datetime(2025, 7, 3, tzinfo=UTC)
        await session.flush()
        evaluation = await backtest_model(
            session,
            backtest_command,
            artifact_root=tmp_path,
            bridge=fake_bridge,
            now=acquired_at,
        )
        fold_id = await session.scalar(
            select(ModelEvaluationFold.id).where(ModelEvaluationFold.evaluation_id == evaluation.id)
        )
        evaluation_predictions = list(
            (
                await session.scalars(
                    select(ModelEvaluationPrediction).where(ModelEvaluationPrediction.fold_id == fold_id)
                )
            ).all()
        )
        assert evaluation.status == "insufficient_evidence"
        assert evaluation.failure_reasons == ["result_observation_after_forecast"]
        assert evaluation.coverage == 1
        assert evaluation.metrics["multiclass_brier"] == 0.375
        assert evaluation.metrics["multiclass_log_loss"] == pytest.approx(0.6931471805599453)
        assert evaluation.metrics["accuracy"] == 1
        assert evaluation.metrics["expected_calibration_error"] == 0.5
        assert evaluation.metrics["resolved_quality_rate"] == 1
        assert evaluation.scope_json["artifact_digest"] == trained.artifact_digest
        assert len(evaluation_predictions) >= 3
        assert {prediction.resolved_at for prediction in evaluation_predictions} == {result_observation.observed_at}
        assert prediction_payloads[-1]["expected_artifact_digest"] == trained.artifact_digest
        assert prediction_payloads[-1]["expected_runtime_fingerprint"] == runtime["runtime_fingerprint"]
        assert prediction_payloads[-1]["targets"] == [{"home_team": "C", "away_team": "D"}]
        if transaction.is_active:
            await transaction.rollback()
    await engine.dispose()
