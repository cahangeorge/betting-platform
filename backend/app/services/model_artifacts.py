"""Canonical dataset and artifact integrity boundary for model-cpu work."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_identity import MatchProviderMapping
from app.models.provider_ingestion import ProviderDatasetGeneration, ProviderDatasetGenerationPage
from app.models.provider_observation import ProviderObservation, ProviderObservationDatasetLink
from app.models.scrape import ScrapedDataset
from app.schemas.model_pipeline import FeatureSetSpecV1, RuntimeFingerprintV1

FreshnessMode = Literal["current", "historical"]


class ModelArtifactError(ValueError):
    """Model input or artifact evidence is incomplete, stale, or unsafe."""


@dataclass(frozen=True)
class CanonicalModelInput:
    generation_id: int
    generation_key: str
    dataset_ids: tuple[int, ...]
    observation_ids: tuple[int, ...]
    match_ids: tuple[int, ...]
    rows: tuple[dict[str, Any], ...]
    feature_set_fingerprint: str
    training_data_fingerprint: str
    source_as_of: datetime
    fresh_until: datetime


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ModelArtifactError("model timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return _utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ModelArtifactError("model fingerprints reject non-finite decimals")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ModelArtifactError("model fingerprints reject non-finite floats")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ModelArtifactError("model fingerprint objects require string keys")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, str | int | bool):
        return value
    raise ModelArtifactError(f"unsupported model fingerprint value: {type(value).__name__}")


def canonical_model_json(value: object) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def model_fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_model_json(value).encode()).hexdigest()


def _training_wire_timestamp(value: object) -> str:
    """Format a protocol timestamp without delegating representation to pandas."""
    if isinstance(value, datetime):
        return _utc(value).isoformat().replace("+00:00", "Z")
    try:
        return _utc(datetime.fromisoformat(str(value).replace("Z", "+00:00"))).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError) as exc:
        raise ModelArtifactError("training wire row has an invalid timestamp") from exc


def canonical_training_wire_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Project and order the exact records consumed by the model runtime.

    ``source_id`` and ``observed_at`` are ordering witnesses only; the digest
    deliberately covers the five fields passed to penaltyblog's model class.
    This small protocol is duplicated in the isolated bridge because it cannot
    import backend dependencies.
    """
    normalized: list[tuple[tuple[str, str, str], dict[str, Any]]] = []
    for row in rows:
        try:
            source_id = str(row["source_id"])
            observed_at = _training_wire_timestamp(row["observed_at"])
            date = _training_wire_timestamp(row["date"])
            projected = {
                "date": date,
                "team_home": str(row["team_home"]),
                "team_away": str(row["team_away"]),
                "goals_home": int(row["goals_home"]),
                "goals_away": int(row["goals_away"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelArtifactError("training wire row is incomplete") from exc
        normalized.append(((date, source_id, observed_at), projected))
    return tuple(projected for _order, projected in sorted(normalized, key=lambda item: item[0]))


def training_wire_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    """Fingerprint the versioned training wire projection, not pandas output."""
    return model_fingerprint(canonical_training_wire_rows(rows))


def feature_set_fingerprint(spec: FeatureSetSpecV1) -> str:
    return model_fingerprint(spec.model_dump(mode="python"))


def runtime_fingerprint(runtime: RuntimeFingerprintV1) -> str:
    payload = runtime.model_dump(mode="python")
    declared = payload.pop("runtime_fingerprint")
    calculated = model_fingerprint(payload)
    if declared != calculated:
        raise ModelArtifactError("model runtime attestation fingerprint is invalid")
    return calculated


def backend_artifact_path(root: Path, artifact_key: str, *, suffix: str = ".pkl") -> Path:
    if len(artifact_key) != 64 or any(character not in "0123456789abcdef" for character in artifact_key):
        raise ModelArtifactError("artifact key must be a lowercase SHA-256 digest")
    resolved_root = root.expanduser().resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    candidate = (resolved_root / artifact_key[:2] / f"{artifact_key}{suffix}").resolve()
    if candidate.parent.parent != resolved_root or not candidate.name.endswith(suffix):
        raise ModelArtifactError("artifact path escaped the backend-owned root")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def verify_artifact_digest(path: Path, expected_digest: str) -> None:
    if len(expected_digest) != 64:
        raise ModelArtifactError("artifact digest is invalid")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_digest:
        raise ModelArtifactError("artifact digest mismatch")


def assert_artifact_runtime(actual: str, expected: str) -> None:
    if actual != expected:
        raise ModelArtifactError("artifact runtime fingerprint mismatch; retraining is required")


async def validate_published_generation(
    session: AsyncSession,
    *,
    generation_id: int,
    freshness_mode: FreshnessMode,
    now: datetime | None = None,
) -> ProviderDatasetGeneration:
    """Fail closed unless a generation is a complete, attested published snapshot."""
    generation = await session.get(ProviderDatasetGeneration, generation_id)
    if generation is None or generation.state != "published":
        raise ModelArtifactError("model work requires a published canonical generation")
    if generation.source_as_of is None or generation.fresh_until is None:
        raise ModelArtifactError("canonical generation has no valid freshness attestation")
    source_as_of, fresh_until = _utc(generation.source_as_of), _utc(generation.fresh_until)
    if source_as_of >= fresh_until:
        raise ModelArtifactError("canonical generation has no valid freshness attestation")
    if freshness_mode == "current" and fresh_until <= _utc(now or datetime.now(UTC)):
        raise ModelArtifactError("canonical generation is stale for current model work")
    if generation.terminal_page is None or generation.terminal_page < 0:
        raise ModelArtifactError("empty canonical generations cannot train, predict, or evaluate a model")
    page_rows = (
        await session.execute(
            select(ProviderDatasetGenerationPage.page, ScrapedDataset)
            .join(ScrapedDataset, ScrapedDataset.id == ProviderDatasetGenerationPage.dataset_id)
            .where(ProviderDatasetGenerationPage.generation_id == generation.id)
            .order_by(ProviderDatasetGenerationPage.page)
        )
    ).all()
    if [page for page, _dataset in page_rows] != list(range(generation.terminal_page + 1)):
        raise ModelArtifactError("canonical generation page membership is incomplete")
    if any(
        dataset.publication_state != "published"
        or not dataset.dataset_digest
        or not dataset.dataset_schema_version
        or not dataset.matches_count
        or dataset.source_as_of is None
        or dataset.fresh_until is None
        for _page, dataset in page_rows
    ):
        raise ModelArtifactError("canonical generation contains incomplete dataset content")
    return generation


async def published_generation_evidence(
    session: AsyncSession,
    *,
    generation_id: int,
    freshness_mode: FreshnessMode,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the immutable page-membership evidence for a usable generation."""
    generation = await validate_published_generation(
        session, generation_id=generation_id, freshness_mode=freshness_mode, now=now
    )
    pages = (
        await session.execute(
            select(ProviderDatasetGenerationPage.page, ScrapedDataset)
            .join(ScrapedDataset, ScrapedDataset.id == ProviderDatasetGenerationPage.dataset_id)
            .where(ProviderDatasetGenerationPage.generation_id == generation.id)
            .order_by(ProviderDatasetGenerationPage.page)
        )
    ).all()
    return {
        "generation_id": generation.id,
        "generation_key": generation.generation_key,
        "artifact_digest": generation.artifact_digest,
        "terminal_page": generation.terminal_page,
        "source_as_of": _utc(generation.source_as_of),
        "fresh_until": _utc(generation.fresh_until),
        "pages": [
            {
                "page": page,
                "dataset_id": dataset.id,
                "dataset_key": dataset.dataset_key,
                "dataset_digest": dataset.dataset_digest,
                "dataset_schema_version": dataset.dataset_schema_version,
                "source_as_of": _utc(dataset.source_as_of),
                "fresh_until": _utc(dataset.fresh_until),
            }
            for page, dataset in pages
        ],
    }


def _first(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    raise ModelArtifactError(f"canonical observation is missing feature {keys[0]}")


def _normalized_feature_row(
    observation: ProviderObservation,
    fixture_cutoff: datetime,
    observation_cutoff: datetime,
) -> dict[str, Any] | None:
    if observation.normalization_state != "normalized" or observation.conflict_state != "clear":
        raise ModelArtifactError("model input contains an unnormalized or conflicted observation")
    if observation.payload_json is None or observation.body_purged_at is not None:
        raise ModelArtifactError("model input body is unavailable under retention policy")
    payload = json.loads(observation.payload_json)
    if not isinstance(payload, Mapping):
        raise ModelArtifactError("canonical observation payload must be an object")
    date_value = _first(payload, "date", "match_date", "matchDate", "kickoff_at")
    try:
        date = datetime.fromisoformat(str(date_value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ModelArtifactError("canonical observation has an invalid fixture timestamp") from exc
    date = _utc(date)
    if date > fixture_cutoff:
        return None
    observed_at = _utc(observation.observed_at)
    if observed_at > observation_cutoff:
        raise ModelArtifactError("training observation occurs after the declared cutoff")
    try:
        home_goals = int(_first(payload, "goals_home", "home_goals", "homeGoals"))
        away_goals = int(_first(payload, "goals_away", "away_goals", "awayGoals"))
    except (TypeError, ValueError) as exc:
        raise ModelArtifactError("canonical observation has invalid goal values") from exc
    if min(home_goals, away_goals) < 0:
        raise ModelArtifactError("training goals must be nonnegative")
    if observed_at < date:
        raise ModelArtifactError("training result observation predates its fixture")
    home_team = str(_first(payload, "team_home", "home_team", "homeTeam")).strip()
    away_team = str(_first(payload, "team_away", "away_team", "awayTeam")).strip()
    if not home_team or not away_team:
        raise ModelArtifactError("canonical observation has an empty team identity")
    return {
        "source_id": observation.source_id,
        "observed_at": observed_at,
        "date": date,
        "team_home": home_team,
        "team_away": away_team,
        "goals_home": home_goals,
        "goals_away": away_goals,
    }


async def load_canonical_model_input(
    session: AsyncSession,
    *,
    generation_id: int,
    feature_set: FeatureSetSpecV1,
    training_cutoff_at: datetime,
    freshness_mode: FreshnessMode = "current",
    now: datetime | None = None,
    observation_cutoff_at: datetime | None = None,
) -> CanonicalModelInput:
    """Load one published generation and its accepted observation bodies."""
    cutoff = _utc(training_cutoff_at)
    effective_now = _utc(now or datetime.now(UTC))
    generation = await validate_published_generation(
        session, generation_id=generation_id, freshness_mode=freshness_mode, now=effective_now
    )
    source_as_of, fresh_until = _utc(generation.source_as_of), _utc(generation.fresh_until)
    observation_cutoff = _utc(observation_cutoff_at or training_cutoff_at)
    if observation_cutoff != cutoff:
        raise ModelArtifactError("training observation cutoff must equal the training cutoff")
    page_rows = (
        await session.execute(
            select(ProviderDatasetGenerationPage.page, ScrapedDataset)
            .join(ScrapedDataset, ScrapedDataset.id == ProviderDatasetGenerationPage.dataset_id)
            .where(ProviderDatasetGenerationPage.generation_id == generation.id)
            .order_by(ProviderDatasetGenerationPage.page)
        )
    ).all()
    datasets = [dataset for _page, dataset in page_rows]

    dataset_ids = tuple(dataset.id for dataset in datasets)
    observations = (
        await session.scalars(
            select(ProviderObservation)
            .join(
                ProviderObservationDatasetLink,
                ProviderObservationDatasetLink.observation_id == ProviderObservation.id,
            )
            .where(ProviderObservationDatasetLink.dataset_id.in_(dataset_ids))
            .order_by(ProviderObservation.observed_at, ProviderObservation.source_id, ProviderObservation.id)
        )
    ).all()
    unique_observations = sorted(
        {observation.observation_key: observation for observation in observations}.values(),
        key=lambda item: (item.source_id, item.observation_key, item.payload_digest),
    )
    if not unique_observations:
        raise ModelArtifactError("canonical generation contains no accepted observations")
    selected = [
        (observation, row)
        for observation in unique_observations
        if (row := _normalized_feature_row(observation, cutoff, observation_cutoff)) is not None
    ]
    if not selected:
        raise ModelArtifactError("canonical generation has no resolved results before the training cutoff")
    selected.sort(key=lambda item: (item[1]["date"], item[1]["source_id"], item[1]["observed_at"]))
    selected_observations = [observation for observation, _row in selected]
    rows = tuple(row for _observation, row in selected)
    source_identities = list(
        dict.fromkeys(
            (observation.adapter_key, observation.source_key, observation.source_id)
            for observation in selected_observations
        )
    )
    mappings = (
        await session.scalars(
            select(MatchProviderMapping)
            .where(
                tuple_(
                    MatchProviderMapping.adapter_key,
                    MatchProviderMapping.source_key,
                    MatchProviderMapping.source_id,
                ).in_(source_identities),
                MatchProviderMapping.state == "accepted",
                MatchProviderMapping.valid_from <= cutoff,
                or_(MatchProviderMapping.valid_to.is_(None), MatchProviderMapping.valid_to > cutoff),
            )
            .order_by(
                MatchProviderMapping.adapter_key,
                MatchProviderMapping.source_key,
                MatchProviderMapping.source_id,
            )
        )
    ).all()
    mappings_by_source = {(mapping.adapter_key, mapping.source_key, mapping.source_id): mapping for mapping in mappings}
    if len(mappings_by_source) != len(source_identities):
        raise ModelArtifactError("canonical generation contains unresolved match identities")
    feature_fingerprint = feature_set_fingerprint(feature_set)
    training_fingerprint = model_fingerprint(
        {
            "generation_key": generation.generation_key,
            "pages": [
                {"dataset_key": dataset.dataset_key, "dataset_digest": dataset.dataset_digest} for dataset in datasets
            ],
            "observations": [
                {
                    "observation_key": observation.observation_key,
                    "payload_digest": observation.payload_digest,
                }
                for observation in selected_observations
            ],
            "mappings": [
                {
                    "source": identity,
                    "match_id": mappings_by_source[identity].match_id,
                    "decision_digest": mappings_by_source[identity].decision_digest,
                }
                for identity in source_identities
            ],
            "feature_set_fingerprint": feature_fingerprint,
            "training_cutoff_at": cutoff,
        }
    )
    return CanonicalModelInput(
        generation.id,
        generation.generation_key,
        dataset_ids,
        tuple(observation.id for observation in selected_observations),
        tuple(int(mappings_by_source[identity].match_id) for identity in source_identities),
        rows,
        feature_fingerprint,
        training_fingerprint,
        source_as_of,
        fresh_until,
    )


def ordered_output_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    return model_fingerprint(list(rows))
