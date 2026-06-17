from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    model_type: str
    parameters: dict = {}
    weights: dict | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class StrategyCreateRequest(BaseModel):
    name: str
    description: str | None = None
    model_type: str
    parameters: dict = {}
    weights: dict | None = None
    is_active: bool = True


class StrategyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    model_type: str | None = None
    parameters: dict | None = None
    weights: dict | None = None
    is_active: bool | None = None


class StrategyRunFilters(BaseModel):
    countries: list[str] = []
    leagues: list[str] = []
    date_from: str | None = None
    date_to: str | None = None


class StrategyRunRequest(BaseModel):
    match_ids: list[int] = []
    markets: list[str] = []
    parameters: dict = {}
    filters: StrategyRunFilters | None = None


class StrategyRunResponse(BaseModel):
    run_id: int
    status: str
    matches_count: int = 0
    error: str | None = None
