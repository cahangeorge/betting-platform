from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BankrollResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    type: str = "paper"
    balance: float
    initial_balance: float
    currency: str = "GBP"
    created_at: datetime
    updated_at: datetime


class BankrollCreateRequest(BaseModel):
    name: str
    type: str = "paper"
    initial_balance: float = 1000.0
    currency: str = "GBP"


class BookmakerAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bankroll_id: int
    bookmaker: str
    account_name: str | None = None
    balance: float | None = None
    created_at: datetime


class BookmakerAccountCreateRequest(BaseModel):
    bookmaker: str
    account_name: str | None = None
    balance: float | None = None


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bankroll_id: int
    ticket_id: int | None = None
    placement_id: int | None = None
    entry_type: str
    amount: float
    balance_after: float
    reference_type: str | None = None
    reference_id: int | None = None
    description: str | None = None
    created_at: datetime
