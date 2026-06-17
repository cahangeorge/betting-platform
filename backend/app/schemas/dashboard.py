from datetime import datetime

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_matches: int = 0
    total_tickets: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    active_bankroll: float = 0.0
    pending_bets: int = 0


class DashboardTicketLeg(BaseModel):
    match_id: int | None = None
    home_team: str | None = None
    away_team: str | None = None
    market: str
    selection: str
    odds: float
    status: str = "pending"
    home_score: int | None = None
    away_score: int | None = None


class DashboardTicket(BaseModel):
    id: int
    ticket_type: str = "single"
    status: str = "open"
    stake: float
    total_odds: float
    potential_return: float
    actual_return: float | None = None
    legs: list[DashboardTicketLeg] = []
    created_at: datetime


class DashboardUpcomingMatch(BaseModel):
    id: int
    home_team: str
    away_team: str
    start_time: str | None = None
    league: str | None = None
    home_odds: float | None = None
    draw_odds: float | None = None
    away_odds: float | None = None


class DashboardJobLog(BaseModel):
    id: int
    job_type: str
    status: str
    league: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    created_at: datetime
