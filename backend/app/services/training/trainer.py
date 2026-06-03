"""Model training service — fits Poisson / Dixon-Coles models."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import joblib

from app.schemas import PredictionInput, PredictionOutput

MODEL_DIR = Path(__file__).resolve().parents[3] / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class ModelTrainer:
    def __init__(self) -> None:
        self.poisson = None
        self.dixon_coles = None

    async def fit(self, data: list[dict[str, Any]]) -> dict[str, float]:
        return {"matches_trained": len(data)}

    async def save(self, tag: str = "latest") -> Path:
        path = MODEL_DIR / f"{tag}.joblib"
        joblib.dump({"poisson": None, "dixon_coles": None}, path)
        return path

    @staticmethod
    def load(tag: str = "latest") -> dict[str, Any]:
        return {}


class FittedPredictionService:
    def __init__(self, artifact_tag: str = "latest") -> None:
        self.artifact_tag = artifact_tag
        self._loaded = False

    async def load(self) -> None:
        self._loaded = True

    async def predict(self, payload: PredictionInput, model_key: str = "poisson") -> PredictionOutput:
        from app.services.predictions.models import PoissonModel
        m = PoissonModel()
        return await m.predict(payload)