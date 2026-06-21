import json

import pytest

from app.services import prediction_engine


class _FakeSession:
    def __init__(self):
        self.added = []
        self._prediction_run_id = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "PredictionRun" and getattr(obj, "id", None) is None:
                self._prediction_run_id += 1
                obj.id = self._prediction_run_id


@pytest.mark.asyncio
async def test_run_single_prediction_marks_completed_on_success(monkeypatch):
    async def fake_execute(*args, **kwargs):
        return {"target_matches": 7, "written": 7, "failed": 0}

    monkeypatch.setattr(prediction_engine, "execute_single_model_run", fake_execute)
    db = _FakeSession()

    result = await prediction_engine.run_single_prediction(
        db=db,
        league="Premier League",
        model_key="PoissonGoalsModel",
        user_id=4,
    )

    run = next(obj for obj in db.added if obj.__class__.__name__ == "PredictionRun")
    assert result == {"run_id": 1, "status": "completed"}
    assert run.status == "completed"
    assert run.matches_count == 7
    assert run.error is None
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_run_single_prediction_forwards_explicit_targets(monkeypatch):
    captured = {}

    async def fake_execute(*args, **kwargs):
        captured.update(kwargs)
        return {"target_matches": 2, "written": 2, "failed": 0, "target_errors": []}

    monkeypatch.setattr(prediction_engine, "execute_single_model_run", fake_execute)
    db = _FakeSession()

    result = await prediction_engine.run_single_prediction(
        db=db,
        league="World Championship",
        model_key="PoissonGoalsModel",
        user_id=4,
        target_mode="matches",
        target_match_ids=[551, 552],
        date_from="2026-06-20T00:00:00+00:00",
        date_to="2026-06-21T00:00:00+00:00",
    )

    assert result == {"run_id": 1, "status": "completed"}
    assert captured["target_match_ids"] == [551, 552]
    assert captured["date_from"] == "2026-06-20T00:00:00+00:00"
    assert captured["date_to"] == "2026-06-21T00:00:00+00:00"


@pytest.mark.asyncio
async def test_run_single_prediction_marks_failed_when_all_targets_fail(monkeypatch):
    async def fake_execute(*args, **kwargs):
        return {
            "target_matches": 2,
            "written": 0,
            "failed": 2,
            "target_errors": [{"match_id": 551, "error": "model failed"}],
        }

    monkeypatch.setattr(prediction_engine, "execute_single_model_run", fake_execute)
    db = _FakeSession()

    result = await prediction_engine.run_single_prediction(
        db=db,
        league="World Championship",
        model_key="PoissonGoalsModel",
        user_id=4,
    )

    run = next(obj for obj in db.added if obj.__class__.__name__ == "PredictionRun")
    assert result["run_id"] == 1
    assert result["status"] == "failed"
    assert "model failed" in result["error"]
    assert run.status == "failed"
    assert "model failed" in run.error


@pytest.mark.asyncio
async def test_run_single_prediction_marks_partial_when_fallbacks_are_used(monkeypatch):
    async def fake_execute(*args, **kwargs):
        return {
            "target_matches": 2,
            "written": 6,
            "failed": 0,
            "fallbacks": 2,
            "target_errors": [{"match_id": 551, "fallback": "market_consensus_or_neutral"}],
        }

    monkeypatch.setattr(prediction_engine, "execute_single_model_run", fake_execute)
    db = _FakeSession()

    result = await prediction_engine.run_single_prediction(
        db=db,
        league="World Championship",
        model_key="PoissonGoalsModel",
        user_id=4,
    )

    run = next(obj for obj in db.added if obj.__class__.__name__ == "PredictionRun")
    assert result["status"] == "partial"
    payload = json.loads(result["error"])
    assert payload["fallbacks"] == 2
    assert payload["target_errors"] == [{"match_id": 551, "fallback": "market_consensus_or_neutral"}]
    assert run.status == "partial"


@pytest.mark.asyncio
async def test_run_single_prediction_marks_failed_with_error(monkeypatch):
    async def fake_execute(*args, **kwargs):
        raise ValueError("No target matches found for this selection.")

    monkeypatch.setattr(prediction_engine, "execute_single_model_run", fake_execute)
    db = _FakeSession()

    result = await prediction_engine.run_single_prediction(
        db=db,
        league="Premier League",
        model_key="PoissonGoalsModel",
        user_id=4,
    )

    run = next(obj for obj in db.added if obj.__class__.__name__ == "PredictionRun")
    assert result == {
        "run_id": 1,
        "status": "failed",
        "error": "No target matches found for this selection.",
    }
    assert run.status == "failed"
    assert run.error == "No target matches found for this selection."
    assert run.completed_at is not None
