from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.model_pipeline import (
    BacktestModelCommandV1,
    FeatureSetSpecV1,
    ModelArtifactManifestV1,
    ModelConfigV1,
    PredictionTargetV1,
    RuntimeFingerprintV1,
    TrainModelCommandV1,
)
from app.services.model_artifacts import (
    ModelArtifactError,
    _normalized_feature_row,
    backend_artifact_path,
    canonical_model_json,
    feature_set_fingerprint,
    model_fingerprint,
    runtime_fingerprint,
    training_wire_fingerprint,
)
from app.services.model_pipeline import _unwrap_bridge


def _runtime_payload() -> dict:
    payload = {
        "runtime_version": "penaltyblog-model-runtime/v1",
        "python_version": "3.13.1",
        "penaltyblog_version": "1.11.0",
        "penaltyblog_revision": "d" * 40,
        "numpy_version": "2.0.0",
        "scipy_version": "1.14.0",
        "pandas_version": "2.2.0",
        "lock_digest": "a" * 64,
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
    payload["runtime_fingerprint"] = model_fingerprint(payload)
    return payload


def test_understat_statistics_payload_projects_to_penaltyblog_goal_features():
    observation = SimpleNamespace(
        normalization_state="normalized",
        conflict_state="clear",
        payload_json=json.dumps(
            {
                "date": "2025-01-02T15:00:00Z",
                "homeTeam": "Alpha",
                "awayTeam": "Beta",
                "homeGoals": 2,
                "awayGoals": 1,
                "homeXg": 1.8,
                "awayXg": 0.7,
            }
        ),
        body_purged_at=None,
        observed_at=datetime(2025, 1, 2, 18, tzinfo=UTC),
        source_id="understat-match-1",
    )

    row = _normalized_feature_row(
        observation,
        fixture_cutoff=datetime(2025, 1, 3, tzinfo=UTC),
        observation_cutoff=datetime(2025, 1, 3, tzinfo=UTC),
    )

    assert row == {
        "source_id": "understat-match-1",
        "observed_at": datetime(2025, 1, 2, 18, tzinfo=UTC),
        "date": datetime(2025, 1, 2, 15, tzinfo=UTC),
        "team_home": "Alpha",
        "team_away": "Beta",
        "goals_home": 2,
        "goals_away": 1,
    }


def test_strict_fingerprints_are_order_stable_and_mutation_sensitive():
    left = {"b": [2, 3], "a": {"value": 1}}
    right = {"a": {"value": 1}, "b": [2, 3]}

    assert canonical_model_json(left) == canonical_model_json(right)
    assert model_fingerprint(left) == model_fingerprint(right)
    assert model_fingerprint(left) != model_fingerprint({"a": {"value": 2}, "b": [2, 3]})


def test_training_wire_fingerprint_has_a_dependency_free_canonical_projection():
    rows = [
        {
            "source_id": "z-source",
            "observed_at": "2025-01-03T02:00:00+00:00",
            "date": "2025-01-03T00:00:00+00:00",
            "team_home": "Z",
            "team_away": "A",
            "goals_home": 3,
            "goals_away": 1,
        },
        {
            "source_id": "a-source",
            "observed_at": "2025-01-01T04:00:00Z",
            "date": "2025-01-01T00:00:00Z",
            "team_home": "A",
            "team_away": "Z",
            "goals_home": 0,
            "goals_away": 2,
        },
    ]
    expected_rows = [
        {"date": "2025-01-01T00:00:00Z", "team_home": "A", "team_away": "Z", "goals_home": 0, "goals_away": 2},
        {"date": "2025-01-03T00:00:00Z", "team_home": "Z", "team_away": "A", "goals_home": 3, "goals_away": 1},
    ]
    expected = hashlib.sha256(json.dumps(expected_rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    assert training_wire_fingerprint(rows) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object()])
def test_strict_fingerprints_reject_noncanonical_values(value):
    with pytest.raises(ModelArtifactError):
        model_fingerprint({"value": value})


def test_feature_and_runtime_fingerprints_are_attested():
    feature = FeatureSetSpecV1()
    runtime = RuntimeFingerprintV1.model_validate(_runtime_payload())

    assert len(feature_set_fingerprint(feature)) == 64
    assert runtime_fingerprint(runtime) == runtime.runtime_fingerprint
    with pytest.raises(ModelArtifactError, match="attestation fingerprint"):
        runtime_fingerprint(runtime.model_copy(update={"python_version": "3.14.0"}))


@pytest.mark.parametrize(
    "thread_environment",
    [
        {"OMP_NUM_THREADS": 1},
        {
            "OMP_NUM_THREADS": 1,
            "OPENBLAS_NUM_THREADS": 0,
            "MKL_NUM_THREADS": 1,
            "NUMEXPR_NUM_THREADS": 1,
        },
    ],
)
def test_runtime_attestation_requires_all_positive_thread_limits(thread_environment):
    payload = _runtime_payload()
    payload["thread_environment"] = thread_environment
    payload["runtime_fingerprint"] = model_fingerprint(
        {key: value for key, value in payload.items() if key != "runtime_fingerprint"}
    )

    with pytest.raises(ValidationError, match="thread environment"):
        RuntimeFingerprintV1.model_validate(payload)


def test_artifact_manifest_key_is_exact_lowercase_sha256():
    payload = dict(
        artifact_key="a" * 64,
        artifact_digest="b" * 64,
        params_digest="c" * 64,
        runtime_fingerprint="d" * 64,
        feature_set_fingerprint="e" * 64,
        training_data_fingerprint="f" * 64,
        model_config_fingerprint="0" * 64,
        training_rows=2,
    )
    assert ModelArtifactManifestV1(**payload).artifact_key == "a" * 64
    with pytest.raises(ValidationError):
        ModelArtifactManifestV1(**{**payload, "artifact_key": "short"})


def test_model_commands_are_strict_allowlisted_and_chronological():
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    config = ModelConfigV1(model_class="PoissonGoalsModel")
    command = TrainModelCommandV1(
        source_generation_id=1,
        model_spec=config,
        model_version="golden-v1",
        training_cutoff_at=cutoff,
    )
    assert command.model_spec.model_class == "PoissonGoalsModel"
    with pytest.raises(ValidationError):
        ModelConfigV1(model_class="BayesianGoalModel")
    with pytest.raises(ValidationError):
        ModelConfigV1(model_class="PoissonGoalsModel", model_kwargs={"alpha": float("nan")})
    with pytest.raises(ValidationError):
        ModelConfigV1(model_class="PoissonGoalsModel", time_decay_xi=0.0018)
    assert ModelConfigV1(model_class="DixonColesGoalModel", time_decay_xi=0.0018).time_decay_xi == 0.0018
    with pytest.raises(ValidationError):
        TrainModelCommandV1(
            source_generation_id=1,
            model_spec=config,
            model_version="golden-v1",
            training_cutoff_at=cutoff,
            unexpected=True,
        )

    target = PredictionTargetV1(
        match_id=1,
        home_team="A",
        away_team="B",
        forecast_at=cutoff + timedelta(days=2),
        kickoff_at=cutoff + timedelta(days=3),
        odds_snapshot_id=1,
        odds_entry_id=1,
    )
    assert BacktestModelCommandV1(
        model_artifact_id=1,
        source_generation_id=1,
        model_spec=config,
        training_cutoff_at=cutoff,
        test_started_at=cutoff + timedelta(days=1),
        test_ended_at=cutoff + timedelta(days=4),
        targets=(target,),
    ).targets == (target,)


def test_backend_artifact_path_is_content_addressed_and_root_confined(tmp_path: Path):
    key = "a" * 64
    path = backend_artifact_path(tmp_path, key)

    assert path == tmp_path / "aa" / f"{key}.pkl"
    with pytest.raises(ModelArtifactError):
        backend_artifact_path(tmp_path, "../escape")


def test_bridge_response_must_match_the_requested_operation():
    assert _unwrap_bridge({"operation": "runtime_info", "result": {"ok": True}}, "runtime_info") == {"ok": True}
    with pytest.raises(ModelArtifactError):
        _unwrap_bridge({"operation": "model_train", "result": {}}, "runtime_info")
