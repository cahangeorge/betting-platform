"""Prediction routes — fitted model predictions."""
from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas import PredictionInput, PredictionOutput
from app.services.training.trainer import FittedPredictionService

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("/predict", response_model=PredictionOutput)
async def predict_match(
    payload: PredictionInput,
    model_key: str = "poisson",
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Run a single prediction using fitted model."""
    service = FittedPredictionService("latest")
    try:
        await service.load()
    except Exception:
        # Fallback heuristic
        return {
            "model_name": "heuristic",
            "home_win_prob": "0.3333",
            "draw_prob": "0.3333",
            "away_win_prob": "0.3333",
            "confidence": "low",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    result = await service.predict(payload, model_key=model_key)
    return {
        "model_name": result.model_name,
        "home_win_prob": str(result.home_win_prob),
        "draw_prob": str(result.draw_prob),
        "away_win_prob": str(result.away_win_prob),
        "expected_goals_home": str(result.expected_goals_home) if result.expected_goals_home else None,
        "expected_goals_away": str(result.expected_goals_away) if result.expected_goals_away else None,
        "confidence": result.confidence,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }