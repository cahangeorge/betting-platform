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
