"""Prediction model wrappers — penaltyblog-based Poisson + Dixon-Coles."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

import joblib
from pathlib import Path

from penaltyblog.models import DixonColesGoalModel, PoissonGoalsModel

from app.schemas import PredictionInput, PredictionOutput

MODEL_DIR = Path(__file__).resolve().parents[3] / "models"


class PoissonModel:
    """Wraps penaltyblog PoissonGoalsModel for single predictions."""

    def __init__(self, fitted: PoissonGoalsModel | None = None) -> None:
        self._model = fitted

    async def predict(self, payload: PredictionInput) -> PredictionOutput:
        if self._model is None:
            return self._heuristic()

        grid = self._model.predict(payload.home_team, payload.away_team)

        return PredictionOutput(
            model_name="poisson",
            home_win_prob=Decimal(str(round(float(grid.home_win), 4))),
            draw_prob=Decimal(str(round(float(grid.draw), 4))),
            away_win_prob=Decimal(str(round(float(grid.away_win), 4))),
            expected_goals_home=Decimal(str(round(float(grid.home_goal_expectation), 4))),
            expected_goals_away=Decimal(str(round(float(grid.away_goal_expectation), 4))),
            confidence="medium",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @staticmethod
    def _heuristic() -> PredictionOutput:
        return PredictionOutput(
            model_name="poisson",
            home_win_prob=Decimal("0.3333"),
            draw_prob=Decimal("0.3333"),
            away_win_prob=Decimal("0.3333"),
            expected_goals_home=Decimal("1.2"),
            expected_goals_away=Decimal("1.0"),
            confidence="low",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )


class DixonColesModel:
    """Wraps penaltyblog DixonColesGoalModel for single predictions."""

    def __init__(self, fitted: DixonColesGoalModel | None = None) -> None:
        self._model = fitted

    async def predict(self, payload: PredictionInput) -> PredictionOutput:
        if self._model is None:
            return self._heuristic()

        try:
            grid = self._model.predict(payload.home_team, payload.away_team)
            return PredictionOutput(
                model_name="dixon-coles",
                home_win_prob=Decimal(str(round(float(grid.home_win), 4))),
                draw_prob=Decimal(str(round(float(grid.draw), 4))),
                away_win_prob=Decimal(str(round(float(grid.away_win), 4))),
                expected_goals_home=Decimal(str(round(float(grid.home_goal_expectation), 4))),
                expected_goals_away=Decimal(str(round(float(grid.away_goal_expectation), 4))),
                confidence="medium",
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
        except (ValueError, RuntimeError):
            return self._heuristic()

    @staticmethod
    def _heuristic() -> PredictionOutput:
        return PredictionOutput(
            model_name="dixon-coles",
            home_win_prob=Decimal("0.3333"),
            draw_prob=Decimal("0.3333"),
            away_win_prob=Decimal("0.3333"),
            confidence="low",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )


class EnsembleModel:
    """Averages Poisson + Dixon-Coles predictions."""

    def __init__(self, poisson: PoissonGoalsModel | None = None, dc: DixonColesGoalModel | None = None) -> None:
        self._poisson = PoissonModel(poisson) if poisson else None
        self._dc = DixonColesModel(dc) if dc else None

    async def predict(self, payload: PredictionInput) -> PredictionOutput:
        if not self._poisson and not self._dc:
            return PoissonModel._heuristic()

        results = []
        if self._poisson:
            results.append(await self._poisson.predict(payload))
        if self._dc:
            results.append(await self._dc.predict(payload))

        n = len(results)
        home = sum(float(r.home_win_prob) for r in results) / n
        draw = sum(float(r.draw_prob) for r in results) / n
        away = sum(float(r.away_win_prob) for r in results) / n
        eg_h = sum(float(r.expected_goals_home or 0)) / n if any(r.expected_goals_home for r in results) else None
        eg_a = sum(float(r.expected_goals_away or 0)) / n if any(r.expected_goals_away for r in results) else None

        return PredictionOutput(
            model_name="ensemble",
            home_win_prob=Decimal(str(round(home, 4))),
            draw_prob=Decimal(str(round(draw, 4))),
            away_win_prob=Decimal(str(round(away, 4))),
            expected_goals_home=Decimal(str(round(eg_h, 4))) if eg_h else None,
            expected_goals_away=Decimal(str(round(eg_a, 4))) if eg_a else None,
            confidence="high" if n == 2 else "medium",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )