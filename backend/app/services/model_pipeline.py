"""Governed penaltyblog train and batch-predict orchestration over canonical data."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.match import OddsEntry
from app.models.model_artifact import ModelArtifact, ModelFeatureSet
from app.models.model_governance import (
    ModelEvaluation,
    ModelEvaluationFold,
    ModelEvaluationPrediction,
    ModelVersion,
)
from app.models.odds_lineage import OddsSnapshot
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.provider_identity import MatchProviderMapping
from app.models.provider_ingestion import ProviderDatasetGeneration, ProviderDatasetGenerationPage
from app.models.provider_observation import ProviderObservation, ProviderObservationDatasetLink
from app.providers.contracts import ProviderExecutionContext
from app.providers.registry import DEFAULT_PROVIDER_REGISTRY, ProviderRegistry
from app.schemas.model_pipeline import (
    MODEL_PIPELINE_CONTRACT_VERSION,
    BacktestModelCommandV1,
    PredictionTargetV1,
    PredictModelCommandV1,
    RuntimeFingerprintV1,
    TrainModelCommandV1,
)
from app.services.model_artifacts import (
    ModelArtifactError,
    assert_artifact_runtime,
    backend_artifact_path,
    canonical_model_json,
    feature_set_fingerprint,
    load_canonical_model_input,
    model_fingerprint,
    ordered_output_fingerprint,
    published_generation_evidence,
    runtime_fingerprint,
    training_wire_fingerprint,
    validate_published_generation,
    verify_artifact_digest,
)
from app.services.python_bridge import run_penaltyblog

BridgeCall = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
FenceCall = Callable[[], Awaitable[None]]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ModelArtifactError("model pipeline timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _advisory_lock_value(identity: str) -> int:
    return int.from_bytes(bytes.fromhex(identity)[:8], byteorder="big", signed=True)


async def _acquire_artifact_lock(session: AsyncSession, artifact_key: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:identity)"),
            {"identity": _advisory_lock_value(artifact_key)},
        )


def _unwrap_bridge(response: Mapping[str, Any], expected_operation: str) -> dict[str, Any]:
    operation = response.get("operation")
    result = response.get("result")
    if operation != expected_operation or not isinstance(result, dict):
        raise ModelArtifactError(f"penaltyblog returned an invalid {expected_operation} response")
    return result


async def _call_operation(
    operation: str,
    payload: dict[str, Any],
    *,
    bridge: BridgeCall,
    registry: ProviderRegistry,
) -> dict[str, Any]:
    registry.require_operation(
        "penaltyblog",
        "local-model",
        operation,
        context=ProviderExecutionContext.PRODUCTION,
    )
    return _unwrap_bridge(await bridge({"operation": operation, "payload": payload}), operation)


async def _attested_runtime(*, bridge: BridgeCall, registry: ProviderRegistry) -> tuple[RuntimeFingerprintV1, str]:
    result = await _call_operation("runtime_info", {}, bridge=bridge, registry=registry)
    try:
        runtime = RuntimeFingerprintV1.model_validate(result)
    except ValueError as exc:
        raise ModelArtifactError("penaltyblog runtime attestation is incomplete") from exc
    return runtime, runtime_fingerprint(runtime)


def _write_feature_artifact(root: Path, artifact_key: str, rows: tuple[dict[str, Any], ...]) -> tuple[Path, str]:
    path = backend_artifact_path(root, artifact_key, suffix=".json")
    payload = canonical_model_json(rows).encode()
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    digest = model_fingerprint(rows)
    verify_artifact_digest(path, digest)
    return path, digest


async def _feature_set_row(session: AsyncSession, command: TrainModelCommandV1) -> ModelFeatureSet:
    fingerprint = feature_set_fingerprint(command.feature_set)
    row = (
        await session.scalars(
            select(ModelFeatureSet).where(
                ModelFeatureSet.feature_key == command.feature_set.feature_set_key,
                ModelFeatureSet.version == command.feature_set.schema_version,
                ModelFeatureSet.spec_fingerprint == fingerprint,
            )
        )
    ).one_or_none()
    if row is None:
        row = ModelFeatureSet(
            feature_key=command.feature_set.feature_set_key,
            version=command.feature_set.schema_version,
            schema_version=command.feature_set.schema_version,
            spec_json=command.feature_set.model_dump(mode="json"),
            spec_fingerprint=fingerprint,
        )
        session.add(row)
        await session.flush()
    return row


async def train_model(
    session: AsyncSession,
    command: TrainModelCommandV1,
    *,
    artifact_root: Path | None = None,
    bridge: BridgeCall = run_penaltyblog,
    registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
    now: datetime | None = None,
    fence: FenceCall | None = None,
) -> ModelArtifact:
    """Create immutable feature and trained-model artifacts for one pinned generation."""
    effective_now = _utc(now or datetime.now(UTC))
    canonical = await load_canonical_model_input(
        session,
        generation_id=command.source_generation_id,
        feature_set=command.feature_set,
        training_cutoff_at=command.training_cutoff_at,
        freshness_mode="historical",
        now=effective_now,
    )
    runtime, runtime_hash = await _attested_runtime(bridge=bridge, registry=registry)
    config_hash = model_fingerprint(command.model_spec.model_dump(mode="python"))
    artifact_key = model_fingerprint(
        {
            "contract": MODEL_PIPELINE_CONTRACT_VERSION,
            "kind": "model",
            "generation_key": canonical.generation_key,
            "feature_set": canonical.feature_set_fingerprint,
            "training_data": canonical.training_data_fingerprint,
            "model_key": command.model_spec.model_class,
            "model_version": command.model_version,
            "model_config": config_hash,
            "runtime": runtime_hash,
        }
    )
    await _acquire_artifact_lock(session, artifact_key)
    existing = (
        await session.scalars(
            select(ModelArtifact).where(ModelArtifact.artifact_key == artifact_key, ModelArtifact.state == "completed")
        )
    ).one_or_none()
    if existing is not None:
        return existing

    feature_set = await _feature_set_row(session, command)
    model_version = (
        await session.scalars(
            select(ModelVersion).where(
                ModelVersion.model_key == command.model_spec.model_class,
                ModelVersion.version == command.model_version,
                ModelVersion.strategy_config_hash == config_hash,
                ModelVersion.training_data_fingerprint == canonical.training_data_fingerprint,
            )
        )
    ).one_or_none()
    if model_version is not None and model_version.runtime_dependency_fingerprint != runtime_hash:
        raise ModelArtifactError("model version identity is bound to a different runtime; use a new model version")
    if model_version is None:
        model_version = ModelVersion(
            model_key=command.model_spec.model_class,
            version=command.model_version,
            build_revision=runtime.penaltyblog_revision,
            engine_version=runtime.penaltyblog_version,
            feature_set_id=feature_set.id,
            feature_schema_hash=canonical.feature_set_fingerprint,
            strategy_config_hash=config_hash,
            training_data_fingerprint=canonical.training_data_fingerprint,
            training_cutoff_at=command.training_cutoff_at,
            runtime_dependency_fingerprint=runtime_hash,
            status="candidate",
            metadata_json={"pipeline_contract_version": MODEL_PIPELINE_CONTRACT_VERSION},
        )
        session.add(model_version)
        await session.flush()

    root = (artifact_root or Path(get_settings().resolved_model_artifact_root)).expanduser().resolve()
    feature_key = model_fingerprint(
        {
            "kind": "feature_matrix",
            "generation_key": canonical.generation_key,
            "feature_set": canonical.feature_set_fingerprint,
            "training_data": canonical.training_data_fingerprint,
            "model_key": command.model_spec.model_class,
            "model_version": command.model_version,
            "model_config": config_hash,
            "runtime": runtime_hash,
        }
    )
    await _acquire_artifact_lock(session, feature_key)
    _feature_path, feature_digest = _write_feature_artifact(root, feature_key, canonical.rows)
    feature_artifact = (
        await session.scalars(select(ModelArtifact).where(ModelArtifact.artifact_key == feature_key))
    ).one_or_none()
    if feature_artifact is None:
        feature_artifact = ModelArtifact(
            artifact_key=feature_key,
            artifact_digest=feature_digest,
            model_version_id=model_version.id,
            source_generation_id=canonical.generation_id,
            feature_set_id=feature_set.id,
            artifact_kind="feature_matrix",
            state="completed",
            manifest_json={
                "contract_version": MODEL_PIPELINE_CONTRACT_VERSION,
                "generation_key": canonical.generation_key,
                "training_data_fingerprint": canonical.training_data_fingerprint,
                "model_config_fingerprint": config_hash,
                "runtime_fingerprint": runtime_hash,
            },
            runtime_dependency_fingerprint=runtime_hash,
            expected_row_count=len(canonical.rows),
            written_row_count=len(canonical.rows),
            expected_output_count=0,
            written_output_count=0,
        )
        session.add(feature_artifact)
        await session.flush()

    model_path = backend_artifact_path(root, artifact_key)
    expected_model_config_digest = model_fingerprint(
        {
            "model_class": command.model_spec.model_class,
            "model_kwargs": command.model_spec.model_kwargs,
            "fit_kwargs": command.model_spec.fit_kwargs,
            "base_date": _utc(command.training_cutoff_at),
            "use_time_decay": command.model_spec.time_decay_xi is not None,
            "xi": command.model_spec.time_decay_xi,
        }
    )
    expected_training_data_digest = training_wire_fingerprint(canonical.rows)
    expected_artifact_path = str(model_path.relative_to(root))
    if fence is not None:
        await fence()
    result = await _call_operation(
        "model_train",
        {
            "matches": list(canonical.rows),
            "artifact_path": expected_artifact_path,
            "model_config": command.model_spec.model_dump(mode="python"),
            "training_cutoff_at": _utc(command.training_cutoff_at).isoformat(),
            "base_date": _utc(command.training_cutoff_at).isoformat(),
            "use_time_decay": command.model_spec.time_decay_xi is not None,
            "xi": command.model_spec.time_decay_xi,
            "expected_model_config_digest": expected_model_config_digest,
            "expected_training_data_digest": expected_training_data_digest,
        },
        bridge=bridge,
        registry=registry,
    )
    if (
        result.get("training_rows") != len(canonical.rows)
        or result.get("runtime_fingerprint") != runtime_hash
        or result.get("model_class") != command.model_spec.model_class
        or result.get("artifact_path") != expected_artifact_path
        or result.get("model_config_digest") != expected_model_config_digest
        or result.get("training_data_digest") != expected_training_data_digest
        or not isinstance(result.get("params_digest"), str)
        or len(result["params_digest"]) != 64
    ):
        raise ModelArtifactError("penaltyblog training attestation is incomplete or does not match the requested input")
    digest = result.get("artifact_digest")
    if not isinstance(digest, str):
        raise ModelArtifactError("penaltyblog omitted the model artifact digest")
    verify_artifact_digest(model_path, digest)
    if fence is not None:
        await fence()
    artifact = ModelArtifact(
        artifact_key=artifact_key,
        artifact_digest=digest,
        model_version_id=model_version.id,
        source_generation_id=canonical.generation_id,
        feature_set_id=feature_set.id,
        artifact_kind="training_manifest",
        state="completed",
        manifest_json={
            "contract_version": MODEL_PIPELINE_CONTRACT_VERSION,
            "feature_artifact_key": feature_artifact.artifact_key,
            "generation_key": canonical.generation_key,
            "feature_set_fingerprint": canonical.feature_set_fingerprint,
            "training_data_fingerprint": canonical.training_data_fingerprint,
            "model_config_fingerprint": config_hash,
            "model_config_digest": expected_model_config_digest,
            "training_data_digest": expected_training_data_digest,
            "max_goals": command.model_spec.max_goals,
            "runtime_fingerprint": runtime_hash,
            "params_digest": result.get("params_digest"),
        },
        runtime_dependency_fingerprint=runtime_hash,
        expected_row_count=len(canonical.rows),
        written_row_count=len(canonical.rows),
        expected_output_count=1,
        written_output_count=1,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def _validate_prediction_targets(
    session: AsyncSession,
    command: PredictModelCommandV1,
) -> list[tuple[PredictionTargetV1, OddsSnapshot, OddsEntry]]:
    validated: list[tuple[PredictionTargetV1, OddsSnapshot, OddsEntry]] = []
    for target in command.targets:
        snapshot = await session.get(OddsSnapshot, target.odds_snapshot_id)
        forecast_at, kickoff_at = _utc(target.forecast_at), _utc(target.kickoff_at)
        if snapshot is None or snapshot.match_id != target.match_id or snapshot.quality != "complete":
            raise ModelArtifactError("prediction target requires a complete same-match odds snapshot")
        if not _utc(snapshot.observed_at) <= forecast_at < kickoff_at:
            raise ModelArtifactError("prediction odds violate the forecast-time cutoff")
        entry = await session.get(OddsEntry, target.odds_entry_id)
        if (
            entry is None
            or any(
                value is None or not math.isfinite(float(value)) or float(value) <= 1
                for value in (entry.home_odds, entry.draw_odds, entry.away_odds)
            )
            or (entry.odds_snapshot_id != snapshot.id or entry.match_id != target.match_id or entry.market != "1x2")
        ):
            raise ModelArtifactError("prediction target requires complete same-match 1x2 odds")
        validated.append((target, snapshot, entry))
    return validated


async def _pinned_generation_targets(
    session: AsyncSession,
    *,
    generation_id: int,
    targets: tuple[PredictionTargetV1, ...],
    effective_at: datetime,
    require_results: bool,
) -> dict[int, dict[str, Any]]:
    """Resolve target metadata and final scores from immutable generation observations."""
    await validate_published_generation(
        session,
        generation_id=generation_id,
        freshness_mode="historical" if require_results else "current",
        now=effective_at,
    )
    targets_by_match = {target.match_id: target for target in targets}
    observations = (
        await session.scalars(
            select(ProviderObservation)
            .join(
                ProviderObservationDatasetLink,
                ProviderObservationDatasetLink.observation_id == ProviderObservation.id,
            )
            .join(
                ProviderDatasetGenerationPage,
                ProviderDatasetGenerationPage.dataset_id == ProviderObservationDatasetLink.dataset_id,
            )
            .join(
                MatchProviderMapping,
                and_(
                    MatchProviderMapping.adapter_key == ProviderObservation.adapter_key,
                    MatchProviderMapping.source_key == ProviderObservation.source_key,
                    MatchProviderMapping.source_id == ProviderObservation.source_id,
                ),
            )
            .where(
                ProviderDatasetGenerationPage.generation_id == generation_id,
                MatchProviderMapping.match_id.in_(targets_by_match),
                MatchProviderMapping.state == "accepted",
                MatchProviderMapping.valid_from <= effective_at,
                or_(MatchProviderMapping.valid_to.is_(None), MatchProviderMapping.valid_to > effective_at),
            )
            .order_by(ProviderObservation.id)
        )
    ).all()
    resolved: dict[int, dict[str, Any]] = {}
    for observation in observations:
        if observation.normalization_state != "normalized" or observation.conflict_state != "clear":
            continue
        if observation.payload_json is None or observation.body_purged_at is not None:
            continue
        if not require_results and _utc(observation.observed_at) > effective_at:
            raise ModelArtifactError("prediction target metadata occurs after the forecast cutoff")
        try:
            payload = json.loads(observation.payload_json)
            fixture_at = _utc(datetime.fromisoformat(str(payload["date"]).replace("Z", "+00:00")))
            home_team = str(payload["team_home"]).strip()
            away_team = str(payload["team_away"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelArtifactError("pinned generation target has invalid canonical payload") from exc
        mapping = await session.scalar(
            select(MatchProviderMapping.match_id).where(
                MatchProviderMapping.adapter_key == observation.adapter_key,
                MatchProviderMapping.source_key == observation.source_key,
                MatchProviderMapping.source_id == observation.source_id,
                MatchProviderMapping.state == "accepted",
                MatchProviderMapping.valid_from <= effective_at,
                or_(MatchProviderMapping.valid_to.is_(None), MatchProviderMapping.valid_to > effective_at),
            )
        )
        if mapping is None or mapping not in targets_by_match:
            continue
        target = targets_by_match[mapping]
        if fixture_at != _utc(target.kickoff_at) or (home_team, away_team) != (target.home_team, target.away_team):
            raise ModelArtifactError("prediction target does not match pinned canonical generation metadata")
        if require_results:
            try:
                payload["goals_home"] = int(payload["goals_home"])
                payload["goals_away"] = int(payload["goals_away"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ModelArtifactError("backtest target requires pinned canonical result scores") from exc
            if _utc(observation.observed_at) < fixture_at:
                raise ModelArtifactError("backtest result observation predates its fixture")
        result = {
            "payload": payload,
            "observation_id": observation.id,
            "observation_key": observation.observation_key,
            "observed_at": _utc(observation.observed_at),
        }
        existing = resolved.get(mapping)
        if existing is not None and existing["payload"] != payload:
            raise ModelArtifactError("pinned generation has conflicting target observations")
        if existing is None:
            resolved[mapping] = result
    if set(resolved) != set(targets_by_match):
        raise ModelArtifactError("prediction target is not resolved in the pinned canonical generation")
    return resolved


def _canonical_competition_key(payload: Mapping[str, Any]) -> str | None:
    """Return the provider-normalized competition identity used for ticket risk."""
    for key in ("league", "competition"):
        value = payload.get(key)
        if isinstance(value, str):
            normalized = " ".join(value.split())
            if normalized:
                return normalized
    return None


async def predict_model(
    session: AsyncSession,
    command: PredictModelCommandV1,
    *,
    user_id: int | None = None,
    artifact_root: Path | None = None,
    bridge: BridgeCall = run_penaltyblog,
    registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
    now: datetime | None = None,
    fence: FenceCall | None = None,
) -> PredictionRun:
    """Load one verified artifact once and persist an exact batch prediction run."""
    effective_now = _utc(now or datetime.now(UTC))
    artifact = await session.get(ModelArtifact, command.model_artifact_id)
    if artifact is None or artifact.state != "completed" or artifact.artifact_kind != "training_manifest":
        raise ModelArtifactError("prediction requires a completed trained-model artifact")
    model_version = await session.get(ModelVersion, artifact.model_version_id)
    if model_version is None or model_version.runtime_dependency_fingerprint is None:
        raise ModelArtifactError("prediction artifact has incomplete model-version lineage")
    generation = await session.get(ProviderDatasetGeneration, command.source_generation_id)
    if generation is None or generation.state != "published" or _utc(generation.fresh_until) <= effective_now:
        raise ModelArtifactError("prediction requires a current published canonical generation")
    # The durable command may wait in a queue, so its requested timestamp cannot
    # be authoritative. Bind every target to the backend execution time instead
    # of allowing a caller to manufacture historical forecast lineage.
    forecast_at = effective_now
    effective_targets = tuple(target.model_copy(update={"forecast_at": forecast_at}) for target in command.targets)
    effective_command = command.model_copy(update={"targets": effective_targets})
    if not _utc(generation.source_as_of) <= forecast_at < _utc(generation.fresh_until):
        raise ModelArtifactError("prediction forecast falls outside canonical freshness")
    pinned_targets = await _pinned_generation_targets(
        session,
        generation_id=generation.id,
        targets=effective_targets,
        effective_at=forecast_at,
        require_results=False,
    )
    validated_targets = await _validate_prediction_targets(session, effective_command)
    odds_by_match = {target.match_id: entry for target, _snapshot, entry in validated_targets}

    _runtime, runtime_hash = await _attested_runtime(bridge=bridge, registry=registry)
    assert_artifact_runtime(runtime_hash, artifact.runtime_dependency_fingerprint)
    root = (artifact_root or Path(get_settings().resolved_model_artifact_root)).expanduser().resolve()
    path = backend_artifact_path(root, artifact.artifact_key)
    verify_artifact_digest(path, artifact.artifact_digest)
    if fence is not None:
        await fence()
    result = await _call_operation(
        "model_predict_batch",
        {
            "artifact_path": str(path.relative_to(root)),
            "expected_artifact_digest": artifact.artifact_digest,
            "expected_runtime_fingerprint": runtime_hash,
            "targets": [{"home_team": target.home_team, "away_team": target.away_team} for target in effective_targets],
            "max_goals": artifact.manifest_json.get("max_goals", 10),
        },
        bridge=bridge,
        registry=registry,
    )
    predictions = result.get("predictions")
    if (
        result.get("runtime_fingerprint") != runtime_hash
        or result.get("artifact_digest") != artifact.artifact_digest
        or result.get("prediction_count") != len(effective_targets)
        or not isinstance(predictions, list)
        or len(predictions) != len(effective_targets)
    ):
        raise ModelArtifactError("penaltyblog returned an incomplete prediction batch")

    output_rows: list[dict[str, Any]] = []
    for target, prediction in zip(effective_targets, predictions, strict=True):
        if not isinstance(prediction, dict):
            raise ModelArtifactError("penaltyblog returned an invalid prediction")
        try:
            home, draw, away = (float(prediction[key]) for key in ("homeWin", "draw", "awayWin"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelArtifactError("penaltyblog returned invalid 1x2 probabilities") from exc
        if (
            not all(math.isfinite(value) for value in (home, draw, away))
            or min(home, draw, away) < 0
            or max(home, draw, away) > 1
            or abs(home + draw + away - 1) > 1e-6
        ):
            raise ModelArtifactError("penaltyblog probabilities violate the 1x2 contract")
        competition_key = _canonical_competition_key(pinned_targets[target.match_id]["payload"])
        canonical_fixture = {
            "match_id": target.match_id,
            "home_team": target.home_team,
            "away_team": target.away_team,
            "kickoff_at": _utc(target.kickoff_at).isoformat(),
        }
        if competition_key is not None:
            canonical_fixture["competition_key"] = competition_key
        output_rows.append(
            {
                "match_id": target.match_id,
                "odds_snapshot_id": target.odds_snapshot_id,
                "odds_entry_id": odds_by_match[target.match_id].id,
                "home_odds": odds_by_match[target.match_id].home_odds,
                "draw_odds": odds_by_match[target.match_id].draw_odds,
                "away_odds": odds_by_match[target.match_id].away_odds,
                "canonical_fixture": canonical_fixture,
                "home": home,
                "draw": draw,
                "away": away,
            }
        )
    output_hash = ordered_output_fingerprint(output_rows)
    if fence is not None:
        await fence()
    completed_at = effective_now if now is not None else datetime.now(UTC)
    if any(_utc(target.kickoff_at) <= completed_at for target in effective_targets):
        raise ModelArtifactError("prediction target kickoff passed before persistence")
    run = PredictionRun(
        user_id=user_id,
        name=f"penaltyblog:{model_version.version}",
        model_type=model_version.model_key,
        status="completed",
        matches_count=len(output_rows),
        started_at=effective_now,
        completed_at=completed_at,
        model_version_id=model_version.id,
        model_artifact_id=artifact.id,
        strategy_config_hash=model_version.strategy_config_hash,
        training_data_fingerprint=model_version.training_data_fingerprint,
        training_cutoff_at=model_version.training_cutoff_at,
        pipeline_contract_version=MODEL_PIPELINE_CONTRACT_VERSION,
        source_generation_id=command.source_generation_id,
        forecast_at=forecast_at,
        output_fingerprint=output_hash,
        input_hash=model_fingerprint(effective_command.model_dump(mode="python")),
        input_context={
            "model_artifact_id": artifact.id,
            "runtime_fingerprint": runtime_hash,
            "requested_command_fingerprint": model_fingerprint(command.model_dump(mode="python")),
        },
        governance_snapshot={"pipeline_complete": True, "artifact_id": artifact.id},
    )
    session.add(run)
    await session.flush()
    ticket_eligible = model_version.status == "active"
    for target, output in zip(effective_targets, output_rows, strict=True):
        competition_missing = "competition_key" not in output["canonical_fixture"]
        is_ticket_eligible = ticket_eligible and not competition_missing
        block_reasons = []
        if model_version.status != "active":
            block_reasons.append("model_version_not_active")
        if competition_missing:
            block_reasons.append("canonical_competition_missing")
        session.add(
            ModelPrediction(
                run_id=run.id,
                model_type=model_version.model_key,
                match_id=target.match_id,
                model_version_id=model_version.id,
                odds_snapshot_id=target.odds_snapshot_id,
                market="1x2",
                home_prob=output["home"],
                draw_prob=output["draw"],
                away_prob=output["away"],
                home_odds=odds_by_match[target.match_id].home_odds,
                draw_odds=odds_by_match[target.match_id].draw_odds,
                away_odds=odds_by_match[target.match_id].away_odds,
                quality_report={
                    "pipeline_contract_version": MODEL_PIPELINE_CONTRACT_VERSION,
                    "output_fingerprint": output_hash,
                    "odds_entry_id": odds_by_match[target.match_id].id,
                    "canonical_fixture": output["canonical_fixture"],
                    "reliability": {
                        "is_ticket_eligible": is_ticket_eligible,
                        "label": "governed" if is_ticket_eligible else "candidate_analysis_only",
                        "score": 100 if is_ticket_eligible else 0,
                        "block_reasons": block_reasons,
                    },
                },
            )
        )
    await session.flush()
    return run


async def backtest_model(
    session: AsyncSession,
    command: BacktestModelCommandV1,
    *,
    user_id: int | None = None,
    artifact_root: Path | None = None,
    bridge: BridgeCall = run_penaltyblog,
    registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
    now: datetime | None = None,
    fence: FenceCall | None = None,
) -> ModelEvaluation:
    """Run one observation-time-safe chronological fold and persist its evidence."""
    effective_now = _utc(now or datetime.now(UTC))
    artifact = await session.get(ModelArtifact, command.model_artifact_id)
    if artifact is None or artifact.state != "completed" or artifact.artifact_kind != "training_manifest":
        raise ModelArtifactError("backtest requires a completed trained-model artifact")
    model_version = await session.get(ModelVersion, artifact.model_version_id)
    if model_version is None or model_version.runtime_dependency_fingerprint is None:
        raise ModelArtifactError("backtest artifact has incomplete model-version lineage")
    config_hash = model_fingerprint(command.model_spec.model_dump(mode="python"))
    if config_hash != model_version.strategy_config_hash:
        raise ModelArtifactError("backtest model config does not match the trained model version")
    if _utc(model_version.training_cutoff_at) != _utc(command.training_cutoff_at):
        raise ModelArtifactError("backtest cutoff does not match the pinned trained model")
    if artifact.manifest_json.get("training_data_fingerprint") != model_version.training_data_fingerprint:
        raise ModelArtifactError("backtest artifact training fingerprint does not match its model version")
    feature_artifact_key = artifact.manifest_json.get("feature_artifact_key")
    feature_artifact = (
        await session.scalars(select(ModelArtifact).where(ModelArtifact.artifact_key == feature_artifact_key))
    ).one_or_none()
    if (
        feature_artifact is None
        or feature_artifact.state != "completed"
        or feature_artifact.artifact_kind != "feature_matrix"
        or feature_artifact.model_version_id != model_version.id
        or feature_artifact.source_generation_id != artifact.source_generation_id
        or feature_artifact.feature_set_id != artifact.feature_set_id
    ):
        raise ModelArtifactError("backtest model has no completed feature artifact with matching lineage")
    _runtime, runtime_hash = await _attested_runtime(bridge=bridge, registry=registry)
    assert_artifact_runtime(runtime_hash, artifact.runtime_dependency_fingerprint)
    root = (artifact_root or Path(get_settings().resolved_model_artifact_root)).expanduser().resolve()
    artifact_path = backend_artifact_path(root, artifact.artifact_key)
    verify_artifact_digest(artifact_path, artifact.artifact_digest)
    feature_path = backend_artifact_path(root, feature_artifact.artifact_key, suffix=".json")
    verify_artifact_digest(feature_path, feature_artifact.artifact_digest)
    pinned_results = await _pinned_generation_targets(
        session,
        generation_id=command.source_generation_id,
        targets=command.targets,
        effective_at=min(_utc(target.forecast_at) for target in command.targets),
        require_results=True,
    )
    generation_evidence = await published_generation_evidence(
        session,
        generation_id=command.source_generation_id,
        freshness_mode="historical",
        now=effective_now,
    )
    generation_scope = json.loads(canonical_model_json(generation_evidence))
    validated = await _validate_prediction_targets(
        session,
        PredictModelCommandV1(
            model_artifact_id=artifact.id,
            source_generation_id=command.source_generation_id,
            targets=command.targets,
        ),
    )
    actuals: list[str] = []
    odds_entries: dict[int, OddsEntry] = {}
    snapshots: dict[int, OddsSnapshot] = {}
    for target, (_target, snapshot, quote) in zip(command.targets, validated, strict=True):
        if not _utc(command.test_started_at) <= _utc(target.forecast_at) < _utc(command.test_ended_at):
            raise ModelArtifactError("backtest target is outside the declared fold")
        odds_entries[target.match_id] = quote
        snapshots[target.match_id] = snapshot
        result = pinned_results[target.match_id]["payload"]
        actuals.append(
            "home"
            if result["goals_home"] > result["goals_away"]
            else "away"
            if result["goals_home"] < result["goals_away"]
            else "draw"
        )
    if fence is not None:
        await fence()
    result = await _call_operation(
        "model_predict_batch",
        {
            "artifact_path": str(artifact_path.relative_to(root)),
            "expected_artifact_digest": artifact.artifact_digest,
            "expected_runtime_fingerprint": runtime_hash,
            "targets": [{"home_team": target.home_team, "away_team": target.away_team} for target in command.targets],
            "max_goals": artifact.manifest_json.get("max_goals", 10),
        },
        bridge=bridge,
        registry=registry,
    )
    outputs = result.get("predictions")
    if (
        result.get("runtime_fingerprint") != runtime_hash
        or result.get("artifact_digest") != artifact.artifact_digest
        or result.get("prediction_count") != len(command.targets)
        or not isinstance(outputs, list)
        or len(outputs) != len(command.targets)
    ):
        raise ModelArtifactError("penaltyblog returned incomplete backtest evidence")
    evaluation_hash = model_fingerprint(
        {
            "contract": MODEL_PIPELINE_CONTRACT_VERSION,
            "generation": generation_scope,
            "artifact": {
                "id": artifact.id,
                "key": artifact.artifact_key,
                "digest": artifact.artifact_digest,
                "model_version_id": model_version.id,
                "runtime_fingerprint": artifact.runtime_dependency_fingerprint,
                "training_data_fingerprint": model_version.training_data_fingerprint,
            },
            "feature_artifact": {
                "id": feature_artifact.id,
                "key": feature_artifact.artifact_key,
                "digest": feature_artifact.artifact_digest,
            },
            "targets": [
                {
                    **target.model_dump(mode="python"),
                    "actual": pinned_results[target.match_id]["payload"],
                    "result_observation": {
                        key: pinned_results[target.match_id][key]
                        for key in ("observation_id", "observation_key", "observed_at")
                    },
                    "odds_entry": {
                        "id": odds_entries[target.match_id].id,
                        "home": odds_entries[target.match_id].home_odds,
                        "draw": odds_entries[target.match_id].draw_odds,
                        "away": odds_entries[target.match_id].away_odds,
                    },
                }
                for target in command.targets
            ],
            "outputs": outputs,
        }
    )
    prospective_reasons = [
        "generation_target_evidence_after_forecast"
        for target in command.targets
        if generation_evidence["source_as_of"] > _utc(target.forecast_at)
        or any(page["source_as_of"] > _utc(target.forecast_at) for page in generation_evidence["pages"])
    ]
    prospective_reasons.extend(
        "result_observation_after_forecast"
        for target in command.targets
        if pinned_results[target.match_id]["observed_at"] > _utc(target.forecast_at)
    )
    if fence is not None:
        await fence()
    evaluation = ModelEvaluation(
        model_version_id=model_version.id,
        user_id=user_id,
        evaluation_kind="walk_forward",
        status="insufficient_evidence" if prospective_reasons else "passed",
        scope_key=f"generation:{command.source_generation_id}",
        scope_json={
            "source_generation_id": command.source_generation_id,
            "artifact_id": artifact.id,
            "artifact_digest": artifact.artifact_digest,
            "feature_artifact_id": feature_artifact.id,
            "feature_artifact_digest": feature_artifact.artifact_digest,
            "generation_key": generation_scope["generation_key"],
            "generation_artifact_digest": generation_scope["artifact_digest"],
            "generation_pages": generation_scope["pages"],
        },
        parameters=command.model_dump(mode="json"),
        pipeline_contract_version=MODEL_PIPELINE_CONTRACT_VERSION,
        evaluation_fingerprint=evaluation_hash,
        sample_size=len(outputs),
        resolved_count=len(outputs),
        valid_folds=1,
        coverage=Decimal("1"),
        metrics={},
        leakage_detected=False,
        quote_cutoff_violations=0,
        fallback_count=0,
        failure_reasons=list(dict.fromkeys(prospective_reasons)),
        started_at=effective_now,
        completed_at=datetime.now(UTC),
    )
    session.add(evaluation)
    await session.flush()
    parsed_outputs: list[tuple[dict[str, Decimal], str]] = []
    for actual, output in zip(actuals, outputs, strict=True):
        probabilities = output.get("probabilities") if isinstance(output, dict) else None
        if probabilities is None and isinstance(output, dict):
            probabilities = {"home": output.get("homeWin"), "draw": output.get("draw"), "away": output.get("awayWin")}
        if not isinstance(probabilities, dict):
            raise ModelArtifactError("backtest output probabilities are invalid")
        try:
            parsed = {selection: Decimal(str(probabilities[selection])) for selection in ("home", "draw", "away")}
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise ModelArtifactError("backtest output probabilities are invalid") from exc
        if any(
            not probability.is_finite() or not Decimal("0") <= probability <= Decimal("1")
            for probability in parsed.values()
        ) or abs(sum(parsed.values()) - Decimal("1")) > Decimal("0.000001"):
            raise ModelArtifactError("backtest probabilities violate the 1x2 contract")
        parsed_outputs.append((parsed, actual))
    squared_errors = sum(
        sum((probability - Decimal(selection == actual)) ** 2 for selection, probability in probabilities.items())
        for probabilities, actual in parsed_outputs
    )
    correct = 0
    log_loss = 0.0
    calibration_bins: dict[int, list[tuple[float, float]]] = {}
    for probabilities, actual in parsed_outputs:
        predicted = max(probabilities, key=probabilities.__getitem__)
        correct += int(predicted == actual)
        actual_probability = max(float(probabilities[actual]), 1e-15)
        log_loss -= math.log(actual_probability)
        confidence = float(probabilities[predicted])
        bin_index = min(int(confidence * 10), 9)
        calibration_bins.setdefault(bin_index, []).append((confidence, float(predicted == actual)))
    sample_size = len(parsed_outputs)
    expected_calibration_error = sum(
        (len(values) / sample_size)
        * abs(
            sum(confidence for confidence, _correct in values) / len(values)
            - sum(is_correct for _confidence, is_correct in values) / len(values)
        )
        for values in calibration_bins.values()
    )
    evaluation.metrics = {
        "multiclass_brier": float(squared_errors / sample_size),
        "multiclass_log_loss": log_loss / sample_size,
        "accuracy": correct / sample_size,
        "expected_calibration_error": expected_calibration_error,
        "resolved_quality_rate": evaluation.resolved_count / evaluation.sample_size,
    }
    fold = ModelEvaluationFold(
        evaluation_id=evaluation.id,
        fold_number=0,
        feature_artifact_id=feature_artifact.id,
        training_cutoff_at=command.training_cutoff_at,
        test_started_at=command.test_started_at,
        test_ended_at=command.test_ended_at,
        training_count=artifact.written_row_count,
        test_count=len(outputs),
        resolved_count=len(outputs),
        metrics=evaluation.metrics,
    )
    session.add(fold)
    await session.flush()
    for target, (parsed_probabilities, actual) in zip(command.targets, parsed_outputs, strict=True):
        quote = odds_entries[target.match_id]
        for selection, quote_value in (
            ("home", quote.home_odds),
            ("draw", quote.draw_odds),
            ("away", quote.away_odds),
        ):
            probability = parsed_probabilities[selection]
            if not Decimal("0") <= probability <= Decimal("1"):
                raise ModelArtifactError("backtest probability is outside the valid range")
            session.add(
                ModelEvaluationPrediction(
                    fold_id=fold.id,
                    match_id=target.match_id,
                    odds_snapshot_id=target.odds_snapshot_id,
                    market="1x2",
                    selection=selection,
                    predicted_probability=probability,
                    fair_odds=(
                        Decimal("999999") if probability == 0 else max(Decimal("1.0001"), Decimal("1") / probability)
                    ),
                    quoted_odds=Decimal(str(quote_value)) if quote_value is not None else None,
                    quote_observed_at=snapshots[target.match_id].observed_at,
                    forecast_at=target.forecast_at,
                    kickoff_at=target.kickoff_at,
                    actual_selection=str(actual),
                    is_correct=selection == actual,
                    resolved_at=pinned_results[target.match_id]["observed_at"],
                )
            )
    await session.flush()
    return evaluation
