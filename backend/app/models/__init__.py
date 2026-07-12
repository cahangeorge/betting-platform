from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ruff: noqa: E402
from app.models.bankroll import Bankroll, BookmakerAccount, LedgerEntry
from app.models.football_catalog import FootballLeagueCatalog
from app.models.job import ScheduledJob, ScheduledJobRun, TaskOutbox
from app.models.match import Match, MatchResultCorrection, MatchSource, MatchStat, OddsEntry
from app.models.prediction import EnsemblePrediction, ModelPrediction, Prediction, PredictionRun, PredictionSession
from app.models.scrape import ScrapedDataset, ScrapeJob, ScrapeJobLog
from app.models.strategy import Strategy
from app.models.ticket import BetPlacement, Settlement, Ticket, TicketBatch, TicketLeg
from app.models.todo import Todo
from app.models.trading import ExecutionEvent, ExecutionIntent, ExecutionOrder, TradingAccount
from app.models.user import Session, User

__all__ = [
    "Base",
    "User",
    "Session",
    "Match",
    "MatchResultCorrection",
    "OddsEntry",
    "MatchStat",
    "MatchSource",
    "PredictionRun",
    "ModelPrediction",
    "EnsemblePrediction",
    "PredictionSession",
    "Prediction",
    "Ticket",
    "TicketBatch",
    "TicketLeg",
    "BetPlacement",
    "Settlement",
    "ScrapeJob",
    "ScrapeJobLog",
    "ScrapedDataset",
    "Bankroll",
    "BookmakerAccount",
    "LedgerEntry",
    "ScheduledJob",
    "ScheduledJobRun",
    "TaskOutbox",
    "Strategy",
    "Todo",
    "FootballLeagueCatalog",
    "TradingAccount",
    "ExecutionIntent",
    "ExecutionOrder",
    "ExecutionEvent",
]
