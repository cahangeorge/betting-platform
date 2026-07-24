from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    model_type: str
    parameters: dict = Field(default_factory=dict)
    weights: dict | None = None
    is_active: bool = True
    runnable: bool = True
    incompatibility_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class StrategyCreateRequest(BaseModel):
    name: str
    description: str | None = None
    model_type: str
    parameters: dict = Field(default_factory=dict)
    weights: dict | None = None
    is_active: bool = True


class StrategyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    model_type: str | None = None
    parameters: dict | None = None
    weights: dict | None = None
    is_active: bool | None = None


class StrategyDuplicateRequest(BaseModel):
    name: str | None = None


class StrategyRunFilters(BaseModel):
    countries: list[str] = Field(default_factory=list)
    leagues: list[str] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None


class StrategyRunRequest(BaseModel):
    match_ids: list[int] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)
    filters: StrategyRunFilters | None = None
    autopredict: bool = False
    avoid_reprediction: bool = False
    dataset_id: int | None = Field(default=None, gt=0)
    allow_partial_resolution: bool = False


class StrategyRunResponse(BaseModel):
    run_id: int
    status: str
    matches_count: int = 0
    error: str | None = None
    deduped: bool = False
    strategy_id: int | None = None
    dataset_id: int | None = None
    input_hash: str | None = None
    context: dict | None = None


class StrategyBatchRunRequest(BaseModel):
    strategy_ids: list[int] = Field(default_factory=list)
    dataset_id: int = Field(gt=0)
    markets: list[str] = Field(default_factory=list)
    filters: StrategyRunFilters | None = None
    autopredict: bool = False
    avoid_reprediction: bool = False
    allow_partial_resolution: bool = False


class StrategyBatchRunResponse(BaseModel):
    status: str
    dataset_id: int
    scrape_job_id: int | None = None
    scrape_job_status: str | None = None
    match_ids: list[int] = Field(default_factory=list)
    dataset_records_count: int = 0
    resolved_records_count: int = 0
    unresolved_records_count: int = 0
    resolution_counts: dict[str, int] = Field(default_factory=dict)
    unresolved_samples: list[dict] = Field(default_factory=list)
    strategy_count: int = 0
    runs: list[StrategyRunResponse] = Field(default_factory=list)
