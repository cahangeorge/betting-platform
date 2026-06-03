"""Prediction model wrappers (heuristic fallback)."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from app.schemas import PredictionInput, PredictionOutput


class PoissonModel:
    async def predict(self, payload: PredictionInput) -> PredictionOutput:
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