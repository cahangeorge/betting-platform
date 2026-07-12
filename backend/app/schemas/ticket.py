from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TicketLegResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    model_prediction_id: int | None = None
    match_id: int | None = None
    selection: str
    market: str
    odds: float
    bookmaker: str | None = None
    status: str = "pending"
    created_at: datetime
    match: dict | None = None


class BetPlacementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    bookmaker: str
    placed_at: datetime
    reference: str | None = None
    status: str = "pending"


class SettlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bet_placement_id: int | None = None
    ticket_id: int | None = None
    settled_at: datetime
    outcome: str
    return_amount: float
    pnl: float


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str | None = None
    user_id: int | None = None
    bankroll_id: int | None = None
    batch_id: int | None = None
    ticket_type: str = "single"
    stake: float
    total_odds: float
    potential_return: float
    actual_return: float | None = None
    status: str = "open"
    created_at: datetime
    updated_at: datetime
    settled_at: datetime | None = None
    legs: list[TicketLegResponse] = []


class TicketDetailResponse(TicketResponse):
    legs: list[TicketLegResponse] = []
    placements: list[BetPlacementResponse] = []


class TicketPageResponse(BaseModel):
    items: list[TicketResponse] = []
    total: int = 0
    page: int = 1
    per_page: int = 20


class TicketBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bankroll_id: int | None = None
    name: str | None = None
    strategy: str | None = None
    tickets_count: int = 0
    total_stake: float = 0.0
    created_at: datetime


class TicketStatsResponse(BaseModel):
    total: int = 0
    won: int = 0
    lost: int = 0
    profit_loss: float = 0.0


class TicketSettlementRunResponse(BaseModel):
    checked_tickets: int = 0
    settled_tickets: int = 0
    won_tickets: int = 0
    lost_tickets: int = 0
    void_tickets: int = 0
    pending_tickets: int = 0
    updated_legs: int = 0


class TicketGenerateRequest(BaseModel):
    bankroll_id: int | None = None
    run_id: int | None = Field(default=None, ge=1)
    ticket_count: int = 5
    difficulty: str = "balanced"
    market_types: list[str] = ["1x2"]
    min_odds: float = 1.01
    max_odds: float = 100.0
    stake: float = 10.0


class TicketGenerateResponse(BaseModel):
    batch_id: int
    tickets: list[TicketResponse] = []


class TicketSwapLegsRequest(BaseModel):
    source_ticket_id: int
    source_leg_id: int
    target_ticket_id: int
    target_leg_id: int


class TicketSwapLegsResponse(BaseModel):
    source_ticket: TicketResponse
    target_ticket: TicketResponse


class TicketCreateRequest(BaseModel):
    ticket_type: str = "single"
    stake: float = 10.0
    bankroll_id: int | None = None
    legs: list[dict] = []
