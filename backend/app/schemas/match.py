from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class OddsEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_id: int
    bookmaker: str
    market: str
    home_odds: float | None = None
    draw_odds: float | None = None
    away_odds: float | None = None
    timestamp: datetime | None = None
    created_at: datetime


class MatchStatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_id: int
    source: str
    home_xg: float | None = None
    away_xg: float | None = None
    possession_home: float | None = None
    possession_away: float | None = None
    shots_home: int | None = None
    shots_away: int | None = None
    json_data: dict | None = None
    created_at: datetime


class MatchSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_id: int
    source: str
    source_id: str | None = None
    url: str | None = None
    created_at: datetime


class MatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None = None
    home_team: str
    away_team: str
    home_score: int | None = None
    away_score: int | None = None
    status: str = "scheduled"
    start_time: str | None = None
    league: str | None = None
    season: str | None = None
    odds: list[OddsEntryResponse] = []
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def map_fields(cls, data):
        """Map ORM fields to API fields."""
        if hasattr(data, "match_date"):
            md = data.match_date
            data_dict = {}
            for k in (
                "id",
                "external_id",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
                "status",
                "season",
                "created_at",
                "updated_at",
            ):
                data_dict[k] = getattr(data, k, None)
            data_dict["start_time"] = md.isoformat() if md else None
            data_dict["league"] = getattr(data, "competition", None)
            data_dict["odds"] = getattr(data, "odds", [])
            return data_dict
        if isinstance(data, dict):
            if "match_date" in data and "start_time" not in data:
                md = data.pop("match_date")
                data["start_time"] = md.isoformat() if md else None
            if "competition" in data and "league" not in data:
                data["league"] = data.pop("competition")
            return data
        return data


class MatchDetailResponse(MatchResponse):
    odds: list[OddsEntryResponse] = []
    stats: list[MatchStatResponse] = []
    sources: list[MatchSourceResponse] = []


class LiveValueCandidateResponse(BaseModel):
    market: str
    selection: str
    odds: float
    model_probability: float
    implied_probability: float
    edge: float
    expected_value: float
    spread: float | None = None
    source: str = "odds"
    prediction_age_seconds: int | None = None
    confidence_band: Literal["low", "medium", "high"] = "low"


class MatchListResponse(BaseModel):
    matches: list[MatchResponse]
    total: int
    page: int = 1
    per_page: int = 50


class LiveMatchResponse(MatchResponse):
    minute: int | None = None
    momentum: Literal["home", "away", "neutral"] = "neutral"
    momentum_intensity: Literal["weak", "moderate", "strong", "overwhelming"] = "weak"
    source: str = "cache"
    is_live_data: bool = False
    xg_home: float | None = None
    xg_away: float | None = None
    possession_home: float | None = None
    possession_away: float | None = None
    shots_home: int | None = None
    shots_away: int | None = None
    last_updated_at: datetime | None = None
    odds: list[OddsEntryResponse] = []
    live_value_candidates: list[LiveValueCandidateResponse] = []


class LiveOverviewResponse(BaseModel):
    matches: list[LiveMatchResponse]
    source: str = "cache"
    is_demo: bool = False
    generated_at: str
    data_age_seconds: int | None = None
    is_data_stale: bool = True
    jobs_active: int = 0


class LiveHeartbeatResponse(BaseModel):
    schema_version: str
    jobs_active: int = 0
    bridge_ready: bool = False
    bridge_issues: list[str] = []
    timestamp: str
    last_success: str | None = None
    source: str = "cache"
