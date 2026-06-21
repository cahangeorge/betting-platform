from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1 import strategies as strategies_api
from app.services import prediction_engine
from app.services.python_bridge import BridgeError


def test_normalize_strategy_markets_maps_ui_aliases():
    assert strategies_api._normalize_strategy_markets(["1X2", "over_under_2.5", "BTTS"]) == [
        "1x2",
        "ou_2_5",
        "btts",
    ]


def test_build_strategy_execution_config_resolves_penaltyblog_model_and_parameters():
    strategy = SimpleNamespace(
        model_type="dixon_coles",
        parameters={
            "training_limit": 220,
            "target_limit": 12,
            "max_goals": 7,
            "use_time_decay": True,
            "time_decay_xi": 0.0025,
            "model_kwargs": {"rho": 0.05},
            "fit_kwargs": {"minimizer_options": {"maxiter": 25}},
        },
    )

    config = strategies_api._build_strategy_execution_config(strategy)

    assert config == {
        "model_key": "DixonColesGoalModel",
        "training_limit": 220,
        "target_limit": 12,
        "max_goals": 7,
        "model_kwargs": {"rho": 0.05},
        "fit_kwargs": {"minimizer_options": {"maxiter": 25}},
        "use_time_decay": True,
        "time_decay_xi": 0.0025,
    }


def test_resolve_prediction_model_key_supports_ui_aliases():
    assert prediction_engine.resolve_prediction_model_key("poisson") == "PoissonGoalsModel"
    assert prediction_engine.resolve_prediction_model_key("PoissonGoalsModel") == "PoissonGoalsModel"


@pytest.mark.asyncio
async def test_execute_single_model_run_forwards_penaltyblog_options(monkeypatch):
    class _FakeSession:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

    training = [
        SimpleNamespace(
            id=index,
            home_team=f"Home {index % 4}",
            away_team=f"Away {index % 4}",
            home_score=1,
            away_score=0,
            match_date=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
        )
        for index in range(20)
    ]
    targets = [SimpleNamespace(id=91, home_team="Alpha FC", away_team="Beta United")]
    captured_payloads: list[dict] = []

    async def fake_fetch_training_matches(*args, **kwargs):
        return training

    async def fake_fetch_target_matches(*args, **kwargs):
        return targets

    async def fake_fetch_target_odds_map(*args, **kwargs):
        return {
            91: [
                SimpleNamespace(
                    match_id=91,
                    market="1x2:FullTime",
                    home_odds=2.05,
                    draw_odds=3.4,
                    away_odds=4.2,
                    bookmaker="Book",
                )
            ]
        }

    async def fake_calculate_implied_probabilities_with_penaltyblog(*args, **kwargs):
        return {"home": 0.48, "draw": 0.29, "away": 0.23}

    async def fake_run_penaltyblog(payload):
        captured_payloads.append(payload)
        if payload["operation"] == "dixon_coles_weights":
            return {"operation": "dixon_coles_weights", "result": {"weights": [1.0] * len(training)}}
        if payload["operation"] == "model_fit_predict":
            return {
                "operation": "model_fit_predict",
                "result": {
                    "prediction": {
                        "homeWin": 0.5,
                        "draw": 0.3,
                        "awayWin": 0.2,
                        "bttsYes": 0.6,
                        "bttsNo": 0.4,
                        "totals": {"over_2_5": 0.55, "under_2_5": 0.45},
                    }
                },
            }
        raise AssertionError(f"Unexpected operation {payload['operation']}")

    monkeypatch.setattr(prediction_engine, "fetch_training_matches", fake_fetch_training_matches)
    monkeypatch.setattr(prediction_engine, "fetch_target_matches", fake_fetch_target_matches)
    monkeypatch.setattr(prediction_engine, "fetch_target_odds_map", fake_fetch_target_odds_map)
    monkeypatch.setattr(
        prediction_engine,
        "calculate_implied_probabilities_with_penaltyblog",
        fake_calculate_implied_probabilities_with_penaltyblog,
    )
    monkeypatch.setattr(prediction_engine, "run_penaltyblog", fake_run_penaltyblog)

    db = _FakeSession()
    summary = await prediction_engine.execute_single_model_run(
        db=db,
        run_id=12,
        model_key="dixon_coles",
        league="Premier League",
        markets=["1x2", "ou_2_5"],
        use_time_decay=True,
        time_decay_xi=0.003,
        model_kwargs={"rho": 0.05},
        fit_kwargs={"minimizer_options": {"maxiter": 20}},
        max_goals=6,
    )

    assert summary["written"] == 2
    assert captured_payloads[0]["operation"] == "dixon_coles_weights"
    assert captured_payloads[0]["payload"]["xi"] == 0.003
    assert captured_payloads[1]["payload"]["model"] == "DixonColesGoalModel"
    assert captured_payloads[1]["payload"]["model_kwargs"] == {"rho": 0.05}
    assert captured_payloads[1]["payload"]["fit_kwargs"] == {"minimizer_options": {"maxiter": 20}}
    assert captured_payloads[1]["payload"]["weights"] == [1.0] * len(training)
    assert captured_payloads[1]["payload"]["prediction"]["max_goals"] == 6
    predictions = [obj for obj in db.added if obj.__class__.__name__ == "ModelPrediction"]
    assert predictions[0].home_odds == 2.05
    assert predictions[0].expected_value == 0.025
    assert predictions[0].quality_report["market"]["implied_source"] == "penaltyblog.implied.calculate_implied"


@pytest.mark.asyncio
async def test_execute_single_model_run_falls_back_when_time_decay_bridge_fails(monkeypatch):
    class _FakeSession:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

    training = [
        SimpleNamespace(
            id=index,
            home_team=f"Home {index % 4}",
            away_team=f"Away {index % 4}",
            home_score=1,
            away_score=0,
            match_date=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
        )
        for index in range(20)
    ]
    targets = [SimpleNamespace(id=92, home_team="Alpha FC", away_team="Beta United")]
    captured_payloads: list[dict] = []

    async def fake_fetch_training_matches(*args, **kwargs):
        return training

    async def fake_fetch_target_matches(*args, **kwargs):
        return targets

    async def fake_fetch_target_odds_map(*args, **kwargs):
        return {
            92: [
                SimpleNamespace(
                    match_id=92,
                    market="1x2:FullTime",
                    home_odds=2.05,
                    draw_odds=3.4,
                    away_odds=4.2,
                    bookmaker="Book",
                )
            ]
        }

    async def fake_calculate_implied_probabilities_with_penaltyblog(*args, **kwargs):
        return {"home": 0.48, "draw": 0.29, "away": 0.23}

    async def fake_run_penaltyblog(payload):
        captured_payloads.append(payload)
        if payload["operation"] == "dixon_coles_weights":
            raise BridgeError("weights unavailable")
        if payload["operation"] == "model_fit_predict":
            return {
                "operation": "model_fit_predict",
                "result": {
                    "prediction": {
                        "homeWin": 0.5,
                        "draw": 0.3,
                        "awayWin": 0.2,
                    }
                },
            }
        raise AssertionError(f"Unexpected operation {payload['operation']}")

    monkeypatch.setattr(prediction_engine, "fetch_training_matches", fake_fetch_training_matches)
    monkeypatch.setattr(prediction_engine, "fetch_target_matches", fake_fetch_target_matches)
    monkeypatch.setattr(prediction_engine, "fetch_target_odds_map", fake_fetch_target_odds_map)
    monkeypatch.setattr(
        prediction_engine,
        "calculate_implied_probabilities_with_penaltyblog",
        fake_calculate_implied_probabilities_with_penaltyblog,
    )
    monkeypatch.setattr(prediction_engine, "run_penaltyblog", fake_run_penaltyblog)

    db = _FakeSession()
    summary = await prediction_engine.execute_single_model_run(
        db=db,
        run_id=13,
        model_key="DixonColesGoalModel",
        league="Premier League",
        markets=["1x2"],
        use_time_decay=True,
    )

    assert summary["written"] == 1
    assert captured_payloads[0]["operation"] == "dixon_coles_weights"
    assert captured_payloads[1]["operation"] == "model_fit_predict"
    assert captured_payloads[1]["payload"]["weights"] is None


@pytest.mark.asyncio
async def test_execute_single_model_run_reports_target_bridge_errors(monkeypatch):
    class _FakeSession:
        def add(self, obj):
            raise AssertionError(f"Should not add prediction rows when bridge fails: {obj}")

        async def flush(self):
            return None

    training = [
        SimpleNamespace(
            id=index,
            home_team=f"Home {index % 4}",
            away_team=f"Away {index % 4}",
            home_score=1,
            away_score=0,
            match_date=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
        )
        for index in range(20)
    ]
    targets = [SimpleNamespace(id=551, home_team="Netherlands", away_team="Sweden")]

    async def fake_fetch_training_matches(*args, **kwargs):
        return training

    async def fake_fetch_target_matches(*args, **kwargs):
        return targets

    async def fake_fetch_target_odds_map(*args, **kwargs):
        return {551: []}

    async def fake_run_penaltyblog(_payload):
        raise BridgeError("penaltyblog model failed for Netherlands vs Sweden")

    monkeypatch.setattr(prediction_engine, "fetch_training_matches", fake_fetch_training_matches)
    monkeypatch.setattr(prediction_engine, "fetch_target_matches", fake_fetch_target_matches)
    monkeypatch.setattr(prediction_engine, "fetch_target_odds_map", fake_fetch_target_odds_map)
    monkeypatch.setattr(prediction_engine, "run_penaltyblog", fake_run_penaltyblog)

    summary = await prediction_engine.execute_single_model_run(
        db=_FakeSession(),
        run_id=14,
        model_key="PoissonGoalsModel",
        league="World Championship",
        markets=["1x2"],
        target_mode="matches",
        target_match_ids=[551],
    )

    assert summary["written"] == 0
    assert summary["failed"] == 1
    assert summary["target_errors"] == [
        {
            "match_id": 551,
            "home_team": "Netherlands",
            "away_team": "Sweden",
            "error": "penaltyblog model failed for Netherlands vs Sweden",
        }
    ]


@pytest.mark.asyncio
async def test_execute_single_model_run_writes_unreliable_fallback_when_team_missing(monkeypatch):
    class _FakeSession:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

    training = [
        SimpleNamespace(
            id=index,
            home_team=f"Home {index % 4}",
            away_team=f"Away {index % 4}",
            home_score=1,
            away_score=0,
            match_date=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
        )
        for index in range(20)
    ]
    targets = [SimpleNamespace(id=551, home_team="Netherlands", away_team="Sweden")]

    async def fake_fetch_training_matches(*args, **kwargs):
        return training

    async def fake_fetch_target_matches(*args, **kwargs):
        return targets

    async def fake_fetch_target_odds_map(*args, **kwargs):
        return {
            551: [
                SimpleNamespace(
                    match_id=551,
                    market="1x2:FullTime",
                    home_odds=2.0,
                    draw_odds=3.5,
                    away_odds=4.0,
                    bookmaker="Book",
                )
            ]
        }

    async def fake_run_penaltyblog(_payload):
        raise BridgeError("ValueError: Both teams must have been in the training data.")

    monkeypatch.setattr(prediction_engine, "fetch_training_matches", fake_fetch_training_matches)
    monkeypatch.setattr(prediction_engine, "fetch_target_matches", fake_fetch_target_matches)
    monkeypatch.setattr(prediction_engine, "fetch_target_odds_map", fake_fetch_target_odds_map)
    monkeypatch.setattr(prediction_engine, "run_penaltyblog", fake_run_penaltyblog)

    db = _FakeSession()
    summary = await prediction_engine.execute_single_model_run(
        db=db,
        run_id=15,
        model_key="PoissonGoalsModel",
        league="World Championship",
        markets=["1x2"],
        target_mode="matches",
        target_match_ids=[551],
    )

    predictions = [obj for obj in db.added if obj.__class__.__name__ == "ModelPrediction"]
    assert summary["written"] == 1
    assert summary["failed"] == 0
    assert summary["fallbacks"] == 1
    assert summary["target_errors"][0]["fallback"] == "market_consensus_or_neutral"
    assert predictions[0].quality_report["model"]["fallback"] == "market_consensus_or_neutral"
    assert predictions[0].quality_report["reliability"]["is_ticket_eligible"] is False
    assert "model_training_team_missing" in predictions[0].quality_report["reliability"]["block_reasons"]
