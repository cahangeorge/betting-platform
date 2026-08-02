"""Offline contracts for the restricted penaltyblog model-artifact runtime."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy", reason="penaltyblog runtime contract requires its isolated scientific venv")

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "app" / "bridges" / "penaltyblog_bridge.py"


def _bridge_module():
    spec = importlib.util.spec_from_file_location("penaltyblog_bridge_model_runtime_test", BRIDGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Grid:
    home_goal_expectation = 1.2
    away_goal_expectation = 0.9
    home_win = 0.5
    draw = 0.25
    away_win = 0.25
    home_draw_away = 1.0
    btts_yes = 0.5
    btts_no = 0.5
    double_chance_1x = 0.75
    double_chance_x2 = 0.5
    double_chance_12 = 0.75
    draw_no_bet_home = 0.6
    draw_no_bet_away = 0.4
    grid = np.ones((2, 2)) * 0.25

    def exact_score(self, _home, _away):
        return 0.25

    def total_goals(self, _side, _line):
        return 0.5

    def asian_handicap(self, _side, _line):
        return 0.5

    def total_goals_distribution(self):
        return [0.25, 0.75]


class _Model:
    def __init__(self, *_args, **_kwargs):
        self.fit_calls = 0

    def fit(self, **_kwargs):
        self.fit_calls += 1

    def get_params(self):
        return {"alpha": 1.0}

    def predict_many(self, home_teams, away_teams, **_kwargs):
        assert len(home_teams) == len(away_teams)
        return [_Grid() for _ in home_teams]


@pytest.fixture
def bridge(monkeypatch):
    module = _bridge_module()
    fake_penaltyblog = SimpleNamespace(
        __version__="test",
        models=SimpleNamespace(
            PoissonGoalsModel=_Model,
            DixonColesGoalModel=_Model,
            dixon_coles_weights=lambda *_args, **_kwargs: [1.0, 1.0],
        ),
    )
    monkeypatch.setitem(sys.modules, "penaltyblog", fake_penaltyblog)
    monkeypatch.setenv("BET_PENALTYBLOG_ROOT", str(BRIDGE_PATH.parents[3] / "penaltyblog"))
    return module


def _train_payload(bridge, artifact_path):
    matches = _matches()
    model_config = {"model_class": "PoissonGoalsModel", "model_kwargs": {}, "fit_kwargs": {}}
    payload = {"matches": matches, "artifact_path": artifact_path, "model_config": model_config}
    payload["expected_model_config_digest"] = bridge._training_config_digest(payload, model_config)
    payload["expected_training_data_digest"] = bridge._training_wire_digest(matches)
    return payload


def _matches():
    return [
        {
            "source_id": "one",
            "observed_at": "2025-01-01T01:00:00Z",
            "date": "2025-01-01T00:00:00Z",
            "team_home": "A",
            "team_away": "B",
            "goals_home": 1,
            "goals_away": 0,
        },
        {
            "source_id": "two",
            "observed_at": "2025-01-02T01:00:00Z",
            "date": "2025-01-02T00:00:00Z",
            "team_home": "B",
            "team_away": "A",
            "goals_home": 0,
            "goals_away": 1,
        },
    ]


def test_training_wire_digest_matches_backend_without_pandas_timestamp_representation(bridge):
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
    expected_digest = hashlib.sha256(
        json.dumps(expected_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    assert bridge._canonical_training_wire_rows(rows) == expected_rows
    assert bridge._training_wire_digest(rows) == expected_digest


def test_model_train_writes_only_under_configured_root_and_returns_digests(bridge, monkeypatch, tmp_path):
    monkeypatch.setenv("BET_MODEL_ARTIFACT_ROOT", str(tmp_path))

    result = bridge.run_model_train(_train_payload(bridge, "models/run-1.pkl"))

    assert (tmp_path / "models" / "run-1.pkl").is_file()
    assert len(result["artifact_digest"]) == 64
    assert len(result["params_npz_digest"]) == 64
    assert result["training_rows"] == 2


def test_model_train_rejects_oversized_artifact_before_publication(bridge, monkeypatch, tmp_path):
    monkeypatch.setenv("BET_MODEL_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr(bridge, "MAX_MODEL_ARTIFACT_BYTES", 8)

    def oversized_dump(_model, handle, **_kwargs):
        handle.write(b"x" * 9)

    monkeypatch.setattr(bridge.pickle, "dump", oversized_dump)

    with pytest.raises(ValueError, match="exceeds"):
        bridge.run_model_train(_train_payload(bridge, "safe.pkl"))

    assert not (tmp_path / "safe.pkl").exists()
    assert not (tmp_path / "safe.pkl.tmp").exists()


def test_runtime_attestation_accepts_image_injected_full_revision_without_git_metadata(bridge, monkeypatch, tmp_path):
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    monkeypatch.setenv("BET_PENALTYBLOG_ROOT", str(tmp_path))
    monkeypatch.setenv("BET_PENALTYBLOG_REVISION", "d" * 40)

    runtime = bridge.run_runtime_info({})

    assert runtime["penaltyblog_revision"] == "d" * 40
    assert len(runtime["lock_digest"]) == 64
    assert len(runtime["runtime_fingerprint"]) == 64
    assert runtime["thread_environment"] == {
        "OMP_NUM_THREADS": 1,
        "OPENBLAS_NUM_THREADS": 1,
        "MKL_NUM_THREADS": 1,
        "NUMEXPR_NUM_THREADS": 1,
    }


@pytest.mark.parametrize("artifact_path", ["../escape.pkl", "/tmp/escape.pkl", "models/not-a-pickle.json"])
def test_model_artifact_paths_reject_traversal_escape_and_untrusted_suffix(
    bridge, monkeypatch, tmp_path, artifact_path
):
    monkeypatch.setenv("BET_MODEL_ARTIFACT_ROOT", str(tmp_path))

    with pytest.raises(ValueError):
        bridge.run_model_train(_train_payload(bridge, artifact_path))


def test_model_training_digest_binds_time_decay_inputs(bridge, monkeypatch, tmp_path):
    monkeypatch.setenv("BET_MODEL_ARTIFACT_ROOT", str(tmp_path))
    model_config = {"model_class": "DixonColesGoalModel", "model_kwargs": {}, "fit_kwargs": {}}
    matches = _matches()
    payload = {
        "matches": matches,
        "artifact_path": "safe.pkl",
        "model_config": model_config,
        "use_time_decay": True,
        "xi": 0.0018,
        "base_date": "2025-01-02T00:00:00Z",
    }
    payload["expected_model_config_digest"] = bridge._training_config_digest(payload, model_config)
    payload["expected_training_data_digest"] = bridge._training_wire_digest(matches)
    assert payload["expected_model_config_digest"] == bridge._json_digest(
        {
            **model_config,
            "use_time_decay": True,
            "xi": 0.0018,
            "base_date": "2025-01-02T00:00:00Z",
        }
    )
    payload["xi"] = 0.002

    with pytest.raises(ValueError, match="model configuration digest"):
        bridge.run_model_train(payload)


def test_predict_batch_verifies_digest_before_loading_and_calls_predict_many_once(bridge, monkeypatch, tmp_path):
    monkeypatch.setenv("BET_MODEL_ARTIFACT_ROOT", str(tmp_path))
    trained = bridge.run_model_train(_train_payload(bridge, "safe.pkl"))

    result = bridge.run_model_predict_batch(
        {
            "artifact_path": "safe.pkl",
            "expected_artifact_digest": trained["artifact_digest"],
            "expected_runtime_fingerprint": trained["runtime_fingerprint"],
            "targets": [{"home_team": "A", "away_team": "B"}, {"home_team": "B", "away_team": "A"}],
        }
    )
    assert result["prediction_count"] == 2
    with pytest.raises(ValueError, match="digest verification failed"):
        bridge.run_model_predict_batch(
            {
                "artifact_path": "safe.pkl",
                "expected_artifact_digest": "0" * 64,
                "expected_runtime_fingerprint": trained["runtime_fingerprint"],
                "targets": [{"home_team": "A", "away_team": "B"}],
            }
        )


def test_predict_batch_deserializes_the_verified_opened_bytes(bridge, monkeypatch, tmp_path):
    monkeypatch.setenv("BET_MODEL_ARTIFACT_ROOT", str(tmp_path))
    trained = bridge.run_model_train(_train_payload(bridge, "safe.pkl"))
    loaded = []

    def capture_load(buffer):
        loaded.append(buffer.read())
        return _Model()

    monkeypatch.setattr(bridge.pickle, "load", capture_load)
    result = bridge.run_model_predict_batch(
        {
            "artifact_path": "safe.pkl",
            "expected_artifact_digest": trained["artifact_digest"],
            "expected_runtime_fingerprint": trained["runtime_fingerprint"],
            "targets": [{"home_team": "A", "away_team": "B"}],
        }
    )

    assert result["prediction_count"] == 1
    assert loaded == [(tmp_path / "safe.pkl").read_bytes()]


def test_predict_batch_rejects_runtime_mismatch_before_pickle_load(bridge, monkeypatch, tmp_path):
    monkeypatch.setenv("BET_MODEL_ARTIFACT_ROOT", str(tmp_path))
    trained = bridge.run_model_train(_train_payload(bridge, "safe.pkl"))

    with pytest.raises(ValueError, match="runtime verification failed"):
        bridge.run_model_predict_batch(
            {
                "artifact_path": "safe.pkl",
                "expected_artifact_digest": trained["artifact_digest"],
                "expected_runtime_fingerprint": "0" * 64,
                "targets": [{"home_team": "A", "away_team": "B"}],
            }
        )


def test_predict_batch_rejects_short_model_output(bridge, monkeypatch, tmp_path):
    class ShortModel(_Model):
        def predict_many(self, home_teams, away_teams, **_kwargs):
            assert len(home_teams) == len(away_teams)
            return [_Grid() for _ in home_teams[:-1]]

    monkeypatch.setenv("BET_MODEL_ARTIFACT_ROOT", str(tmp_path))
    trained = bridge.run_model_train(_train_payload(bridge, "safe.pkl"))
    monkeypatch.setattr(bridge.pickle, "load", lambda _artifact: ShortModel())

    with pytest.raises(ValueError, match="incomplete prediction batch"):
        bridge.run_model_predict_batch(
            {
                "artifact_path": "safe.pkl",
                "expected_artifact_digest": trained["artifact_digest"],
                "expected_runtime_fingerprint": trained["runtime_fingerprint"],
                "targets": [{"home_team": "A", "away_team": "B"}, {"home_team": "B", "away_team": "A"}],
            }
        )


def test_backtest_fold_requires_strictly_chronological_split(bridge):
    with pytest.raises(ValueError, match="strictly chronological"):
        bridge.run_model_backtest_fold(
            {"training_matches": _matches(), "test_matches": _matches(), "training_cutoff_at": "2025-01-01T12:00:00Z"}
        )


def test_backtest_fold_returns_bounded_metrics_and_predictions(bridge):
    result = bridge.run_model_backtest_fold(
        {
            "training_matches": _matches(),
            "test_matches": [
                {"date": "2025-01-03T00:00:00Z", "team_home": "A", "team_away": "B", "goals_home": 2, "goals_away": 0}
            ],
            "training_cutoff_at": "2025-01-02T12:00:00Z",
        }
    )
    assert result["metrics"]["multiclass_brier"] >= 0
    assert len(result["predictions"]) == 1
