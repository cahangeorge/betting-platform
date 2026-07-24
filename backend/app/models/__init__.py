from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ruff: noqa: E402
from app.models.bankroll import Bankroll, BookmakerAccount, LedgerEntry
from app.models.football_catalog import FootballLeagueCatalog
from app.models.job import JobCreationIdempotency, ScheduledJob, ScheduledJobRun, TaskOutbox
from app.models.match import Match, MatchResultCorrection, MatchSource, MatchStat, OddsEntry
from app.models.model_governance import (
    ModelCertification,
    ModelEvaluation,
    ModelEvaluationFold,
    ModelEvaluationPrediction,
    ModelMonitoringSnapshot,
    ModelVersion,
    PredictionOutcome,
)
from app.models.odds_lineage import OddsSnapshot, TicketLegQuoteSnapshot
from app.models.prediction import EnsemblePrediction, ModelPrediction, Prediction, PredictionRun, PredictionSession
from app.models.risk import BankrollRiskPolicy, BankrollRiskState
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
    "OddsSnapshot",
    "TicketLegQuoteSnapshot",
    "MatchStat",
    "MatchSource",
    "PredictionRun",
    "ModelPrediction",
    "EnsemblePrediction",
    "PredictionSession",
    "Prediction",
    "ModelVersion",
    "ModelEvaluation",
    "ModelEvaluationFold",
    "ModelEvaluationPrediction",
    "PredictionOutcome",
    "ModelCertification",
    "ModelMonitoringSnapshot",
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
    "BankrollRiskPolicy",
    "BankrollRiskState",
    "ScheduledJob",
    "JobCreationIdempotency",
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
