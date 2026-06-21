from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ScrapeJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    status: str = "pending"
    league: str | None = None
    params: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output: str | None = None
    error: str | None = None
    created_at: datetime


class ScrapeJobCreateRequest(BaseModel):
    job_type: str = Field(validation_alias=AliasChoices("job_type", "type"))
    league: str | None = None
    params: dict | None = None


class ScrapedDatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    source: str
    data: dict
    matches_count: int | None = None
    created_at: datetime


class WorldCupPipelineRequest(BaseModel):
    target_date: str | None = None
    target_date_from: str | None = None
    target_date_to: str | None = None
    future_days: int = Field(default=7, ge=1, le=31)
    history_years: int = Field(default=10, ge=0, le=40)
    all_markets: bool = True
    odds_history: bool = True
    max_historic_pages: int | None = Field(default=None, ge=1, le=50)
    ticket_count: int = Field(default=10, ge=1, le=50)
    ticket_stake: float = Field(default=10.0, ge=0)
    create_tickets: bool = True
    allow_experimental_tickets: bool = False
    training_limit: int = Field(default=240, ge=20, le=1000)


class WorldCupTicketCandidate(BaseModel):
    match_id: int
    match: str
    league: str | None = None
    kickoff: str | None = None
    market: str
    selection: str
    probability: float
    odds: float
    bookmaker: str | None = None
    model_types: list[str]
    model_prediction_id: int
    expected_return_score: float


class WorldCupDifficultyTicket(BaseModel):
    rank: int
    ticket_id: int | None = None
    ticket_type: str
    leg_count: int
    combined_probability: float
    total_odds: float
    expected_return_score: float
    legs: list[WorldCupTicketCandidate]


class WorldCupDifficultyTier(BaseModel):
    level: int
    label: str
    leg_count: int
    difficulty: str
    tickets: list[WorldCupDifficultyTicket]


class WorldCupPipelineResponse(BaseModel):
    status: str
    summary: dict
    scrape_job_ids: list[int]
    prediction_run_ids: list[int]
    created_ticket_ids: list[int]
    top_candidates: list[WorldCupTicketCandidate]
    difficulty_tiers: list[WorldCupDifficultyTier] = []
    errors: list[dict] = []
