from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ModelPredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    model_type: str
    match_id: int
    market: str
    home_prob: float
    draw_prob: float | None = None
    away_prob: float
    home_odds: float | None = None
    draw_odds: float | None = None
    away_odds: float | None = None
    value_home: float | None = None
    value_draw: float | None = None
    value_away: float | None = None
    expected_value: float | None = None
    created_at: datetime


class EnsemblePredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    match_id: int
    market: str
    home_prob: float
    draw_prob: float | None = None
    away_prob: float
    model_weights: dict | None = None
    brier_score: float | None = None
    created_at: datetime


class PredictionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    name: str | None = None
    model_type: str
    ensemble: bool = False
    status: str = "pending"
    matches_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    created_at: datetime


class PredictionRunDetailResponse(PredictionRunResponse):
    model_predictions: list[ModelPredictionResponse] = []
    ensemble_predictions: list[EnsemblePredictionResponse] = []


class RunSingleRequest(BaseModel):
    league: str
    sport: str = "football"
    model_key: str = "PoissonGoalsModel"
    markets: list[str] = ["1x2"]
    training_mode: str = "recent"
    training_limit: int = 380
    target_mode: str = "future"
    target_limit: int = 50
    max_goals: int = 10


class RunEnsembleRequest(BaseModel):
    league: str
    sport: str = "football"
    model_keys: list[str]
    markets: list[str] = ["1x2"]
    training_mode: str = "recent"
    training_limit: int = 380
    target_mode: str = "future"
    target_limit: int = 50
    weighting: str = "uniform"
    max_goals: int = 10


class PredictionCatalogResponse(BaseModel):
    models: list[dict]
    markets: list[str]


class ValueBetItem(BaseModel):
    id: int
    match_id: int
    league: str | None = None
    home_team: str
    away_team: str
    kickoff: str | None = None
    market: str
    selection: str
    model_prob: float
    odds: float
    edge: float
    model_type: str
    confidence: float
    source: str = "prediction"


class ValueBetResponse(BaseModel):
    items: list[ValueBetItem]
    source: str = "prediction"
    is_demo: bool = False
    generated_at: str
