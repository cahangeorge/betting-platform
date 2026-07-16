from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    quality_report: dict | None = None
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
    source_dataset_id: int | None = None
    strategy_id: int | None = None
    strategy_name: str | None = None
    input_hash: str | None = None
    input_context: dict | None = None
    created_at: datetime


class PredictionRunDetailResponse(PredictionRunResponse):
    model_predictions: list[ModelPredictionResponse] = []
    ensemble_predictions: list[EnsemblePredictionResponse] = []


class PredictionRunPageResponse(BaseModel):
    items: list[PredictionRunResponse] = []
    total: int = 0
    page: int = 1
    per_page: int = 20


class RunSingleRequest(BaseModel):
    league: str
    sport: str = "football"
    model_key: str = "PoissonGoalsModel"
    markets: list[str] = ["1x2"]
    training_mode: str = "recent"
    training_limit: int = 380
    training_history_days: int = Field(default=365, ge=30, le=3650)
    target_mode: str = "future"
    target_limit: int = 50
    target_match_ids: list[int] | None = None
    date_from: str | None = None
    date_to: str | None = None
    max_goals: int = 10


class RunEnsembleRequest(BaseModel):
    league: str
    sport: str = "football"
    model_keys: list[str]
    markets: list[str] = ["1x2"]
    training_mode: str = "recent"
    training_limit: int = 380
    training_history_days: int = Field(default=365, ge=30, le=3650)
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
    reliability: str | None = None
    quality_reasons: list[str] = []
    source: str = "prediction"
    prediction_age_seconds: int | None = None
    selection_age_seconds: int | None = None
    odds_freshness_seconds: int | None = None
    data_age_seconds: int | None = None
    source_ok: bool = False
    model_drift_flag: bool = True
    is_betslip_eligible: bool = False
    block_reasons: list[str] = []


class ValueBetResponse(BaseModel):
    items: list[ValueBetItem]
    source: str = "prediction"
    is_demo: bool = False
    generated_at: str


class PredictionVerificationItem(BaseModel):
    prediction_id: int
    run_id: int
    match_id: int
    model_type: str | None = None
    league: str | None = None
    kickoff: datetime | None = None
    market: str
    predicted_selection: str | None = None
    actual_selection: str | None = None
    model_probability: float | None = None
    market_odds: float | None = None
    status: str
    home_team: str
    away_team: str
    home_score: int | None = None
    away_score: int | None = None


class PredictionVerificationResponse(BaseModel):
    checked_predictions: int = 0
    resolved_predictions: int = 0
    correct_predictions: int = 0
    incorrect_predictions: int = 0
    pending_predictions: int = 0
    void_predictions: int = 0
    unsupported_predictions: int = 0
    accuracy: float | None = None
    items: list[PredictionVerificationItem] = []


class PredictionCalibrationBucket(BaseModel):
    lower_bound: float
    upper_bound: float
    mean_predicted_probability: float
    observed_frequency: float
    calibration_gap: float
    samples: int


class PredictionCalibrationGroup(BaseModel):
    model_type: str
    market: str
    resolved_predictions: int
    accuracy: float
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    buckets: list[PredictionCalibrationBucket] = []


class PredictionCalibrationResponse(BaseModel):
    resolved_predictions: int = 0
    groups: list[PredictionCalibrationGroup] = []


class PredictionScoreGridCell(BaseModel):
    home_goals: int
    away_goals: int
    probability: float


class PredictionScoreGridItem(BaseModel):
    match_id: int
    home_team: str
    away_team: str
    kickoff: datetime | None = None
    league: str | None = None
    model_type: str
    prediction_ids: list[int] = Field(default_factory=list)
    source_markets: list[str] = Field(default_factory=list)
    available: bool = False
    unavailable_reason: str | None = None
    home_expected_goals: float | None = None
    away_expected_goals: float | None = None
    max_displayed_goals: int = 5
    displayed_probability_mass: float | None = None
    cells: list[PredictionScoreGridCell] = Field(default_factory=list)
    top_scores: list[PredictionScoreGridCell] = Field(default_factory=list)
    usage: str = "analysis_only"
    ticket_generation_eligible: bool = False


class PredictionScoreGridResponse(BaseModel):
    run_id: int
    source_dataset_id: int | None = None
    items: list[PredictionScoreGridItem] = Field(default_factory=list)
    disclaimer: str = (
        "Exact-score probabilities are model explanations for analysis only. "
        "They are not eligible inputs for ticket generation."
    )
