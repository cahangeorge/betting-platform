from pydantic import BaseModel


class PnlTimeSeriesPoint(BaseModel):
    date: str
    pnl: float = 0.0
    cumulative_pnl: float = 0.0
    bets_count: int = 0
    wins: int = 0


class PnlByLeague(BaseModel):
    league: str
    total_pnl: float = 0.0
    bets_count: int = 0
    wins: int = 0
    win_rate: float = 0.0


class PnlByModel(BaseModel):
    model_type: str
    total_pnl: float = 0.0
    bets_count: int = 0
    wins: int = 0
    win_rate: float = 0.0


class EquityCurvePoint(BaseModel):
    date: str
    balance: float


class ClvLegResult(BaseModel):
    ticket_id: int
    ticket_leg_id: int
    reference_stage: str | None = None
    same_book_clv_pct: float | None = None
    market_best_clv_pct: float | None = None
    consensus_clv_pp: float | None = None
    coverage: dict[str, bool]
    unavailable_reasons: dict[str, tuple[str, ...]]


class ClvSummary(BaseModel):
    leg_count: int = 0
    same_book_coverage_pct: float = 0.0
    market_best_coverage_pct: float = 0.0
    consensus_coverage_pct: float = 0.0
    average_same_book_clv_pct: float | None = None
    average_market_best_clv_pct: float | None = None
    average_consensus_clv_pp: float | None = None
    positive_same_book_pct: float | None = None
    positive_market_best_pct: float | None = None
    positive_consensus_pct: float | None = None


class ClvReport(BaseModel):
    summary: ClvSummary
    items: list[ClvLegResult]
