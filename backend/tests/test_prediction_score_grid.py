from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import predictions as predictions_api
from app.services.prediction_engine import _score_grid_analysis_payload


def _prediction(*, prediction_id: int, market: str, quality_report: dict | None):
    match = SimpleNamespace(
        home_team="Alpha FC",
        away_team="Beta United",
        match_date=datetime(2026, 7, 17, 18, 30, tzinfo=timezone.utc),
        competition="A-League",
    )
    return SimpleNamespace(
        id=prediction_id,
        match_id=91,
        model_type="PoissonGoalsModel",
        market=market,
        quality_report=quality_report,
        match=match,
    )


def test_score_grid_payload_is_explicitly_analysis_only():
    payload = _score_grid_analysis_payload(
        {
            "homeGoalExpectation": 1.6,
            "awayGoalExpectation": 1.1,
            "scoreGrid": {
                "maxDisplayedGoals": 1,
                "probabilities": [[0.1, 0.2], [0.3, 0.4]],
                "displayedProbabilityMass": 1.0,
            },
        }
    )

    assert payload == {
        "usage": "analysis_only",
        "ticket_generation_eligible": False,
        "home_expected_goals": 1.6,
        "away_expected_goals": 1.1,
        "max_displayed_goals": 1,
        "displayed_probability_mass": 1.0,
        "probabilities": [[0.1, 0.2], [0.3, 0.4]],
    }


def test_score_grid_contract_groups_markets_and_ranks_scores():
    report = {
        "analysis_only": {
            "score_grid": {
                "usage": "analysis_only",
                "ticket_generation_eligible": False,
                "home_expected_goals": 1.6,
                "away_expected_goals": 1.1,
                "max_displayed_goals": 1,
                "displayed_probability_mass": 0.9,
                "probabilities": [[0.2, 0.1], [0.4, 0.2]],
            }
        }
    }
    item = predictions_api._build_score_grid_item(
        [
            _prediction(prediction_id=11, market="1x2", quality_report=report),
            _prediction(prediction_id=12, market="btts", quality_report=report),
        ]
    )

    assert item.available is True
    assert item.prediction_ids == [11, 12]
    assert item.source_markets == ["1x2", "btts"]
    assert item.top_scores[0].home_goals == 1
    assert item.top_scores[0].away_goals == 0
    assert item.top_scores[0].probability == 0.4
    assert item.usage == "analysis_only"
    assert item.ticket_generation_eligible is False


def test_score_grid_contract_marks_legacy_predictions_unavailable():
    item = predictions_api._build_score_grid_item([_prediction(prediction_id=11, market="1x2", quality_report={})])

    assert item.available is False
    assert item.unavailable_reason == "score_grid_not_persisted_for_prediction"
    assert item.cells == []


@pytest.mark.asyncio
async def test_score_grid_endpoint_is_user_scoped_and_has_no_ticket_side_effects():
    prediction = _prediction(prediction_id=11, market="1x2", quality_report={})
    run = SimpleNamespace(id=7, source_dataset_id=3, model_predictions=[prediction])

    class _Result:
        def scalar_one_or_none(self):
            return run

    class _Db:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            return _Result()

    db = _Db()
    response = await predictions_api.get_prediction_score_grids(
        run_id=7,
        db=db,
        user=SimpleNamespace(id=42),
    )

    sql = str(db.statement)
    assert "prediction_runs.user_id" in sql
    assert response.run_id == 7
    assert response.items[0].available is False
    assert "Ticket" not in sql


@pytest.mark.asyncio
async def test_score_grid_endpoint_hides_foreign_or_missing_run():
    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Db:
        async def execute(self, _statement):
            return _Result()

    with pytest.raises(HTTPException) as exc_info:
        await predictions_api.get_prediction_score_grids(
            run_id=7,
            db=_Db(),
            user=SimpleNamespace(id=42),
        )

    assert exc_info.value.status_code == 404
