from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TradingAccountCreateRequest(BaseModel):
    name: str = Field(default="Local paper account", min_length=1, max_length=120)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    initial_balance: float = Field(default=1000.0, ge=0)


class TradingAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider: str
    mode: str
    currency: str
    balance: float
    enabled: bool
    created_at: datetime
    updated_at: datetime


class TradingAccountHealthResponse(BaseModel):
    account_id: int
    status: str
    mode: str
    provider: str
    enabled: bool
    paper_execution_enabled: bool
    live_execution_enabled: bool = False
    betfair_read_only_status: str
    message: str


class ExecutionCreateRequest(BaseModel):
    trading_account_id: int = Field(ge=1)
    ticket_id: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)
    side: str = "BACK"
    order_type: str = "LIMIT"


class ExecutionOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    external_order_id: str | None = None
    status: str
    requested_price: float
    average_price: float | None = None
    requested_size: float
    matched_size: float
    created_at: datetime


class ExecutionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    from_status: str | None = None
    to_status: str
    message: str | None = None
    payload: dict | None = None
    created_at: datetime


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trading_account_id: int
    ticket_id: int
    odds_entry_id: int
    idempotency_key: str
    mode: str
    market: str
    selection: str
    side: str
    order_type: str
    stake: float
    limit_price: float
    status: str
    transport: str
    delivery_status: str
    transport_task_id: str | None = None
    delivery_attempts: int
    last_delivery_error: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    orders: list[ExecutionOrderResponse] = []
    events: list[ExecutionEventResponse] = []
