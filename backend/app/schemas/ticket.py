from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.prediction import ModelPredictionResponse, PredictionRunResponse


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
    prediction_run_id_snapshot: int | None = None
    model_probability_snapshot: float | None = None
    market_probability_snapshot: float | None = None
    market_probability_basis_snapshot: str | None = None
    expected_value_snapshot: float | None = None
    edge_pct_snapshot: float | None = None
    reliability_label_snapshot: str | None = None
    reliability_score_snapshot: float | None = None
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
    legs: list[TicketLegResponse] = Field(default_factory=list)


class TicketDetailResponse(TicketResponse):
    legs: list[TicketLegResponse] = Field(default_factory=list)
    placements: list[BetPlacementResponse] = Field(default_factory=list)


class TicketPageResponse(BaseModel):
    items: list[TicketResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20


class TicketBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bankroll_id: int | None = None
    source_prediction_run_id: int | None = None
    source_prediction_run_ids: list[int] = Field(default_factory=list)
    name: str | None = None
    strategy: str | None = None
    tickets_count: int = 0
    total_stake: float = 0.0
    revision: int = 1
    risk_policy_id: int | None = None
    risk_policy_version: int | None = None
    risk_assessment: dict | None = None
    staking_snapshot: dict | None = None
    activation_report: dict | None = None
    generation_report: dict | None = None
    created_at: datetime


class TicketLineageLegResponse(TicketLegResponse):
    """A ticket leg with the prediction/run that produced it, when available."""

    prediction: ModelPredictionResponse | None = None
    run: PredictionRunResponse | None = None


class TicketLineageTicketResponse(TicketResponse):
    legs: list[TicketLineageLegResponse] = Field(default_factory=list)


class TicketBatchLineageResponse(TicketBatchResponse):
    """Read-only generation lineage for a ticket batch.

    ``source_runs`` captures the explicit analysis runs used during ticket
    generation, while each leg includes the exact model prediction selected
    (if the leg still references one). This is intentionally a response-only
    view and does not add persistence requirements to existing ticket rows.
    """

    source_runs: list[PredictionRunResponse] = Field(default_factory=list)
    tickets: list[TicketLineageTicketResponse] = Field(default_factory=list)


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
    model_config = ConfigDict(extra="forbid")

    bankroll_id: int = Field(gt=0)
    run_id: int | None = Field(default=None, ge=1)
    run_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1, max_length=50)
    prediction_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1, max_length=500)
    ticket_count: int = Field(default=1, ge=1, le=50)
    ticket_format: Literal["single", "double", "treble"] = "single"
    difficulty: Literal["safe", "low", "balanced", "medium", "aggressive", "high"] | None = None
    accumulator_risk_acknowledged: bool = False
    market_types: list[Literal["1x2", "btts", "ou_2_5"]] = Field(
        default_factory=lambda: ["1x2"], min_length=1, max_length=3
    )
    min_odds: float = Field(default=1.01, gt=1)
    max_odds: float = Field(default=100.0, gt=1)

    @model_validator(mode="after")
    def validate_generation_scope_and_odds(self):
        if self.run_id is not None and self.run_ids is not None:
            raise ValueError("Provide either run_id or run_ids, not both")
        if self.run_id is None and self.run_ids is None:
            raise ValueError("Provide run_id or run_ids for explicit prediction lineage")
        if self.min_odds > self.max_odds:
            raise ValueError("min_odds must be lower than or equal to max_odds")
        if self.difficulty is not None:
            mapped = {
                "safe": "single",
                "low": "single",
                "balanced": "double",
                "medium": "double",
                "aggressive": "treble",
                "high": "treble",
            }[self.difficulty]
            if "ticket_format" in self.model_fields_set and self.ticket_format != mapped:
                raise ValueError("difficulty and ticket_format describe different ticket formats")
            self.ticket_format = mapped
        return self


class TicketGenerateResponse(BaseModel):
    batch_id: int
    revision: int = 1
    source_prediction_run_id: int | None = None
    source_prediction_run_ids: list[int] = Field(default_factory=list)
    risk_policy_version: int | None = None
    risk_assessment: dict | None = None
    staking_snapshot: dict | None = None
    generation_report: dict = Field(default_factory=dict)
    tickets: list[TicketResponse] = Field(default_factory=list)


class TicketPreflightRequest(BaseModel):
    """Validation-only scope for checking ticket availability before generation."""

    bankroll_id: int | None = Field(default=None, gt=0)
    run_id: int | None = Field(default=None, ge=1)
    run_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1, max_length=50)
    prediction_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1, max_length=500)
    market_types: list[Literal["1x2", "btts", "ou_2_5"]] = Field(
        default_factory=lambda: ["1x2"], min_length=1, max_length=3
    )
    min_odds: float = Field(default=1.01, gt=1)
    max_odds: float = Field(default=100.0, gt=1)
    ticket_format: Literal["single", "double", "treble"] = "single"
    accumulator_risk_acknowledged: bool = False

    @model_validator(mode="after")
    def validate_preflight_scope_and_odds(self):
        if self.run_id is not None and self.run_ids is not None:
            raise ValueError("Provide either run_id or run_ids, not both")
        if self.run_id is None and self.run_ids is None:
            raise ValueError("Provide run_id or run_ids for explicit prediction lineage")
        if self.min_odds > self.max_odds:
            raise ValueError("min_odds must be lower than or equal to max_odds")
        return self


class TicketPreflightRiskResponse(BaseModel):
    difficulty: Literal["safe", "low", "balanced", "medium", "aggressive", "high"]
    tier: Literal["safe", "balanced", "aggressive"]
    aliases: list[str] = Field(default_factory=list)
    required_legs: int
    eligible_candidates: int = 0
    eligible_unique_matches: int = 0
    can_generate: bool = False
    excluded_by_reason: dict[str, int] = Field(default_factory=dict)


class TicketPreflightResponse(BaseModel):
    source_prediction_run_id: int | None = None
    source_prediction_run_ids: list[int] = Field(default_factory=list)
    source_dataset_id: int | None = None
    scanned_predictions: int = 0
    eligible_candidates: int = 0
    eligible_unique_matches: int = 0
    eligible_prediction_ids: list[int] = Field(default_factory=list)
    excluded_predictions: int = 0
    excluded_by_reason: dict[str, int] = Field(default_factory=dict)
    governance_assessment: dict | None = None
    risk_assessment: dict | None = None
    staking_snapshot: dict | None = None
    risks: list[TicketPreflightRiskResponse] = Field(default_factory=list)


class TicketBatchActivateResponse(BaseModel):
    batch_id: int
    status: str
    debited_amount: float
    tickets: list[TicketResponse] = Field(default_factory=list)


class TicketBatchActivateRequest(BaseModel):
    expected_revision: int = Field(gt=0)
    review_acknowledged: bool
    accepted_warning_codes: list[str] = Field(default_factory=list, max_length=50)


class TicketBatchRefreshRequest(BaseModel):
    expected_revision: int = Field(gt=0)


class TicketBatchRefreshResponse(BaseModel):
    batch_id: int
    revision: int
    status: Literal["refreshed"] = "refreshed"
    generation_report: dict = Field(default_factory=dict)
    risk_assessment: dict | None = None
    staking_snapshot: dict | None = None
    tickets: list[TicketResponse] = Field(default_factory=list)


class TicketBatchDiscardResponse(BaseModel):
    batch_id: int
    status: Literal["discarded"] = "discarded"
    discarded_tickets: int


class TicketSwapLegsRequest(BaseModel):
    source_ticket_id: int = Field(gt=0)
    source_leg_id: int = Field(gt=0)
    target_ticket_id: int = Field(gt=0)
    target_leg_id: int = Field(gt=0)


class TicketSwapLegsResponse(BaseModel):
    source_ticket: TicketResponse
    target_ticket: TicketResponse


class TicketLegCreateRequest(BaseModel):
    model_prediction_id: int | None = Field(default=None, gt=0)
    match_id: int = Field(gt=0)
    selection: str = Field(min_length=1, max_length=50)
    market: str = Field(min_length=1, max_length=50)
    odds: float = Field(gt=1, allow_inf_nan=False)
    bookmaker: str | None = Field(default=None, min_length=1, max_length=100)


class TicketCreateRequest(BaseModel):
    ticket_type: str = Field(default="single", min_length=1, max_length=50)
    stake: float = Field(default=10.0, gt=0, allow_inf_nan=False)
    bankroll_id: int | None = Field(default=None, gt=0)
    accumulator_risk_acknowledged: bool = False
    legs: list[TicketLegCreateRequest] = Field(default_factory=list, min_length=1, max_length=20)
