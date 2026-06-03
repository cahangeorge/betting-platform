"""Model training service — fits Poisson / Dixon-Coles on historical data."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.match import Match  # historical_match not rebuilt; use match table
from app.schemas import PredictionInput, PredictionOutput
from app.services.predictions.models import EnsembleModel, PoissonModel, DixonColesModel

MODEL_DIR = Path(__file__).resolve().parents[3] / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _compute_attack_defense(
    data: list[dict[str, Any]],
    team: str,
) -> tuple[float, float]:
    """Compute rolling attack/defense strength for a team."""
    matches = [r for r in data if r["home_team"] == team or r["away_team"] == team]
    if not matches:
        return 1.0, 1.0
    recent = matches[-10:] if len(matches) > 10 else matches
    gf = sum(r["FTHG"] for r in recent if r["home_team"] == team) + \
         sum(r["FTAG"] for r in recent if r["away_team"] == team)
    ga = sum(r["FTAG"] for r in recent if r["home_team"] == team) + \
         sum(r["FTHG"] for r in recent if r["away_team"] == team)
    per_game_gf = gf / len(recent)
    per_game_ga = ga / len(recent)
    league_avg = sum(r["FTHG"] + r["FTAG"] for r in recent) / (2 * len(recent))
    if league_avg == 0:
        return 1.0, 1.0
    return per_game_gf / league_avg, per_game_ga / league_avg


class ModelTrainer:
    """Train, persist, and load penaltyblog models."""

    def __init__(self) -> None:
        self.poisson = None
        self.dixon_coles = None

    async def fit(self, data: list[dict[str, Any]]) -> dict[str, float]:
        """Fit Poisson and Dixon-Coles models on data.

        Each row must have: home_team, away_team, FTHG, FTAG.
        """
        if not data or len(data) < 10:
            raise ValueError(f"Need >=10 matches for training, got {len(data)}")

        gh = [r["FTHG"] for r in data]
        ga = [r["FTAG"] for r in data]
        th = [r["home_team"] for r in data]
        ta = [r["away_team"] for r in data]

        from penaltyblog.models import DixonColesGoalModel, PoissonGoalsModel

        self.poisson = PoissonGoalsModel(gh, ga, th, ta)
        self.poisson.fit()
        self.dixon_coles = DixonColesGoalModel(gh, ga, th, ta)
        self.dixon_coles.fit()

        avg_hg = sum(gh) / len(gh)
        avg_ag = sum(ga) / len(ga)
        return {
            "matches_trained": len(data),
            "avg_home_goals": round(avg_hg, 3),
            "avg_away_goals": round(avg_ag, 3),
        }

    async def save(self, tag: str = "latest") -> Path:
        if self.poisson is None or self.dixon_coles is None:
            raise RuntimeError("Models not fitted — call fit() first")
        out = MODEL_DIR / f"{tag}.joblib"
        joblib.dump({"poisson": self.poisson, "dixon_coles": self.dixon_coles}, out)
        return out

    @staticmethod
    def load(tag: str = "latest") -> dict[str, Any]:
        path = MODEL_DIR / f"{tag}.joblib"
        if not path.exists():
            raise FileNotFoundError(f"No model artifact at {path}")
        return joblib.load(path)


class FittedPredictionService:
    """Drop-in for the unfitted wrappers — loads fitted models from disk."""

    def __init__(self, artifact_tag: str = "latest") -> None:
        self.artifact_tag = artifact_tag
        self._poisson = None
        self._dixon_coles = None
        self._loaded = False

    async def load(self) -> None:
        try:
            artifact = ModelTrainer.load(self.artifact_tag)
            self._poisson = artifact.get("poisson")
            self._dixon_coles = artifact.get("dixon_coles")
            self._loaded = True
        except FileNotFoundError:
            self._loaded = False

    async def predict(self, payload: PredictionInput, model_key: str = "poisson") -> PredictionOutput:
        try:
            if model_key == "dixon-coles" and self._dixon_coles:
                m = DixonColesModel(self._dixon_coles)
            elif model_key in ("poisson", "dixon-coles") and self._poisson:
                m = PoissonModel(self._poisson)
            elif model_key == "ensemble":
                m = EnsembleModel(self._poisson, self._dixon_coles)
            else:
                m = PoissonModel()
            return await m.predict(payload)
        except Exception:
            from app.services.predictions.models import PoissonModel as Heuristic
            return await Heuristic().predict(payload)


async def fetch_training_data(league: str | None = None) -> list[dict[str, Any]]:
    """Fetch finished matches from DB as training rows."""
    async with async_session_factory() as db:
        query = select(Match).where(Match.status == "finished", Match.is_deleted.is_(False))
        if league:
            query = query.where(Match.league == league)
        result = await db.execute(query)
        rows = []
        for m in result.scalars().all():
            if m.home_score is not None and m.away_score is not None:
                rows.append({
                    "home_team": m.home_team,
                    "away_team": m.away_team,
                    "FTHG": m.home_score,
                    "FTAG": m.away_score,
                    "league": m.league,
                })
        return rows