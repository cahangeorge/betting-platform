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
