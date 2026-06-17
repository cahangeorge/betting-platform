from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ruff: noqa: E402
from app.models.bankroll import Bankroll, BookmakerAccount, LedgerEntry
from app.models.job import ScheduledJob
from app.models.match import Match, MatchSource, MatchStat, OddsEntry
from app.models.prediction import EnsemblePrediction, ModelPrediction, Prediction, PredictionRun, PredictionSession
from app.models.scrape import ScrapedDataset, ScrapeJob
from app.models.strategy import Strategy
from app.models.ticket import BetPlacement, Settlement, Ticket, TicketBatch, TicketLeg
from app.models.todo import Todo
from app.models.user import Session, User

__all__ = [
    "Base",
    "User",
    "Session",
    "Match",
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
    "ScrapedDataset",
    "Bankroll",
    "BookmakerAccount",
    "LedgerEntry",
    "ScheduledJob",
    "Strategy",
    "Todo",
]
