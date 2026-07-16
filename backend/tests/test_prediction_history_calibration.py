from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.api.v1 import predictions as predictions_api
from app.services import prediction_engine


@pytest.mark.asyncio
async def test_execute_single_model_run_uses_one_year_before_earliest_target(monkeypatch):
    target = SimpleNamespace(
        id=91,
        home_team="Alpha FC",
        away_team="Beta United",
        match_date=datetime(2026, 7, 17, 18, 30, tzinfo=timezone.utc),
    )
    training = [
        SimpleNamespace(
            id=index,
            home_team=f"Home {index}",
            away_team=f"Away {index}",
            home_score=1,
            away_score=0,
            match_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        for index in range(20)
    ]
    captured: dict = {}

    async def fake_fetch_targets(*args, **kwargs):
        return [target]

    async def fake_fetch_training(*args, **kwargs):
        captured.update(kwargs)
        return training

    async def fake_fetch_odds(*args, **kwargs):
        observed_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        return {
            91: [
                SimpleNamespace(
                    id=811,
                    odds_snapshot_id=812,
                    snapshot=SimpleNamespace(
                        id=812,
                        observed_at=observed_at,
                        ingested_at=observed_at,
                    ),
                    bookmaker="SnapshotBook",
                    market="1x2",
                    home_odds=2.1,
                    draw_odds=3.2,
                    away_odds=3.8,
                    timestamp=observed_at,
                    created_at=observed_at,
                )
            ]
        }

    async def fake_bridge(_payload):
        return {
            "result": {
                "prediction": {
                    "homeWin": 0.5,
                    "draw": 0.3,
                    "awayWin": 0.2,
                }
            }
        }

    monkeypatch.setattr(prediction_engine, "fetch_target_matches", fake_fetch_targets)
    monkeypatch.setattr(prediction_engine, "fetch_training_matches", fake_fetch_training)
    monkeypatch.setattr(prediction_engine, "fetch_target_odds_map", fake_fetch_odds)
    monkeypatch.setattr(prediction_engine, "run_penaltyblog", fake_bridge)

    class _Db:
        added = []

        def add(self, value):
            self.added.append(value)

    db = _Db()
    summary = await prediction_engine.execute_single_model_run(
        db=db,
        run_id=12,
        model_key="poisson",
        league="Liga Profesional",
        markets=["1x2"],
    )

    assert captured["date_from"] == "2025-07-17T18:30:00+00:00"
    assert captured["date_to"] == "2026-07-17T18:30:00+00:00"
    assert summary["training_window"] == {
        "days": 365,
        "date_from": "2025-07-17T18:30:00+00:00",
        "date_to_exclusive": "2026-07-17T18:30:00+00:00",
    }
    assert db.added[0].odds_snapshot_id == 812


@pytest.mark.asyncio
async def test_fetch_training_matches_uses_closed_open_history_window():
    class _Scalars:
        def all(self):
            return []

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Db:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            return _Result()

    db = _Db()
    await prediction_engine.fetch_training_matches(
        db,
        "Liga Profesional",
        date_from="2025-07-17T18:30:00+00:00",
        date_to="2026-07-17T18:30:00+00:00",
    )

    sql = str(db.statement)
    assert "matches.match_date >=" in sql
    assert "matches.match_date <" in sql


def test_build_calibration_summary_reports_brier_accuracy_and_bins():
    finished_home = SimpleNamespace(home_score=2, away_score=0, status="finished")
    finished_away = SimpleNamespace(home_score=0, away_score=1, status="finished")
    predictions = [
        SimpleNamespace(
            model_type="PoissonGoalsModel",
            market="1x2",
            home_prob=0.7,
            draw_prob=0.2,
            away_prob=0.1,
            match=finished_home,
        ),
        SimpleNamespace(
            model_type="PoissonGoalsModel",
            market="1x2",
            home_prob=0.6,
            draw_prob=0.2,
            away_prob=0.2,
            match=finished_away,
        ),
    ]

    summary = predictions_api._build_calibration_summary(predictions, bin_count=5)

    assert summary.resolved_predictions == 2
    assert len(summary.groups) == 1
    group = summary.groups[0]
    assert group.model_type == "PoissonGoalsModel"
    assert group.market == "1x2"
    assert group.resolved_predictions == 2
    assert group.accuracy == 0.5
    assert group.brier_score == pytest.approx(0.59)
    assert group.log_loss == pytest.approx(0.9831, abs=0.0001)
    assert sum(bucket.samples for bucket in group.buckets) == 6
    assert 0 <= group.expected_calibration_error <= 1


@pytest.mark.asyncio
async def test_calibration_endpoint_scopes_predictions_to_current_user():
    class _Scalars:
        def all(self):
            return []

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Db:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            return _Result()

    db = _Db()
    response = await predictions_api.get_prediction_calibration(
        run_id=44,
        max_results=500,
        bin_count=10,
        db=db,
        user=SimpleNamespace(id=9),
    )

    sql = str(db.statement)
    assert "prediction_runs.user_id" in sql
    assert "prediction_runs.id" in sql
    assert response.resolved_predictions == 0
    assert response.groups == []
