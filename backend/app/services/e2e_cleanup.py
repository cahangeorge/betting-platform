"""Safely inventory or remove unmistakable Playwright E2E fixtures.

The command is dry-run by default. Applying a plan requires both ``--apply``
and the exact confirmation phrase, supplied through ``--confirm-token`` or
``BET_E2E_CLEANUP_CONFIRMATION``. Discovery and deletion share one transaction;
any safety blocker aborts the apply before the first DELETE.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.bankroll import Bankroll, BookmakerAccount, LedgerEntry
from app.models.job import ScheduledJob, ScheduledJobRun, TaskOutbox
from app.models.match import Match, MatchResultCorrection, MatchSource, MatchStat, OddsEntry
from app.models.prediction import (
    EnsemblePrediction,
    ModelPrediction,
    Prediction,
    PredictionRun,
    PredictionSession,
)
from app.models.provider_identity import (
    CompetitionProviderMapping,
    CompetitionProviderMappingCandidate,
    MatchProviderMapping,
    MatchProviderMappingCandidate,
    TeamProviderMapping,
    TeamProviderMappingCandidate,
)
from app.models.provider_observation import (
    ProviderObservation,
    ProviderObservationConflict,
    ProviderObservationDatasetLink,
    ProviderObservationReceipt,
    ProviderObservationSlot,
)
from app.models.scrape import ScrapedDataset, ScrapeJob, ScrapeJobLog
from app.models.strategy import Strategy
from app.models.ticket import BetPlacement, Settlement, Ticket, TicketBatch, TicketLeg
from app.models.trading import ExecutionEvent, ExecutionIntent, ExecutionOrder, TradingAccount
from app.models.user import Session, User
from app.services.run_authorization import owner_id_from_mapping

CONFIRMATION_PHRASE = "DELETE-ONLY-E2E-FIXTURES"
CONFIRMATION_ENV = "BET_E2E_CLEANUP_CONFIRMATION"
MAX_E2E_USERS = 500
NAMESPACE_PATTERN = r"(?P<namespace>\d{13}-[a-z0-9]{8})"
NAMESPACE_RE = re.compile(rf"^{NAMESPACE_PATTERN}$")
USER_EMAIL_RE = re.compile(rf"^e2e-{NAMESPACE_PATTERN}@example\.com$")
STRATEGY_RE = re.compile(rf"^E2E (?:Strategy|Lineage) {NAMESPACE_PATTERN}$")
DATASET_RE = re.compile(rf"^E2E (?:Analysis Dataset|Ticket Lifecycle) {NAMESPACE_PATTERN}$")
COMPETITION_RE = re.compile(rf"^E2E(?: Ticket Lifecycle)? {NAMESPACE_PATTERN}$")
SCHEDULED_JOB_RE = re.compile(rf"^E2E (?:orchestration|verification) {NAMESPACE_PATTERN}$")
RUN_RE = re.compile(
    rf"^(?:E2E(?: selected (?:one|two|three))?|Strategy: E2E (?:Strategy|Lineage)) "
    rf"{NAMESPACE_PATTERN}(?: \| input:[a-f0-9]{{24}})?$"
)
SCRAPE_JOB_RE = re.compile(rf"^e2e-[a-z0-9-]*{NAMESPACE_PATTERN}$")


class CleanupGuardError(RuntimeError):
    """The requested cleanup is not safe to apply."""


def _matched_namespace(pattern: re.Pattern[str], value: str | None) -> str | None:
    match = pattern.fullmatch(str(value or ""))
    return match.group("namespace") if match else None


def e2e_user_namespace(email: str | None, _name: str | None) -> str | None:
    email_namespace = _matched_namespace(USER_EMAIL_RE, email)
    if email_namespace is None:
        return None
    # The generated email shape is already an unmistakable fixture identifier.
    # Accept legacy rows whose display name drifted, while never matching a broad
    # ``e2e-*`` address without the exact timestamp/random namespace contract.
    return email_namespace


def e2e_named_namespace(kind: str, value: str | None) -> str | None:
    patterns = {
        "strategy": STRATEGY_RE,
        "dataset": DATASET_RE,
        "competition": COMPETITION_RE,
        "scheduled_job": SCHEDULED_JOB_RE,
        "prediction_run": RUN_RE,
        "scrape_job": SCRAPE_JOB_RE,
    }
    try:
        pattern = patterns[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown E2E fixture kind: {kind}") from exc
    return _matched_namespace(pattern, value)


def require_apply_confirmation(*, apply: bool, confirmation: str | None) -> None:
    if not apply:
        return
    if confirmation != CONFIRMATION_PHRASE:
        raise CleanupGuardError(
            f"Apply requires --confirm-token {CONFIRMATION_PHRASE} or {CONFIRMATION_ENV}={CONFIRMATION_PHRASE}"
        )


@dataclass
class CleanupPlan:
    namespaces: set[str] = field(default_factory=set)
    ids: dict[str, list[int]] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {name: len(values) for name, values in self.ids.items() if values}

    def add_ids(self, name: str, values: list[int]) -> None:
        self.ids[name] = sorted(set(int(value) for value in values))


def validate_plan_for_apply(plan: CleanupPlan) -> None:
    if plan.blockers:
        raise CleanupGuardError("Cleanup plan has blockers: " + " | ".join(plan.blockers))
    if len(plan.ids.get("users", [])) > MAX_E2E_USERS:
        raise CleanupGuardError(f"Refusing to delete {len(plan.ids['users'])} users; safety limit is {MAX_E2E_USERS}")
    invalid_namespaces = sorted(namespace for namespace in plan.namespaces if not NAMESPACE_RE.fullmatch(namespace))
    if invalid_namespaces:
        raise CleanupGuardError("Cleanup plan contains invalid namespaces: " + ", ".join(invalid_namespaces))


async def _ids(session: AsyncSession, stmt) -> list[int]:
    return [int(value) for value in (await session.execute(stmt)).scalars().all()]


async def _rows(session: AsyncSession, stmt) -> list[Any]:
    return list((await session.execute(stmt)).scalars().all())


def _owner_namespace(mapping: dict | None, users_by_id: dict[int, str]) -> str | None:
    owner_id = owner_id_from_mapping(mapping if isinstance(mapping, dict) else {})
    return users_by_id.get(owner_id) if owner_id is not None else None


async def build_cleanup_plan(session: AsyncSession) -> CleanupPlan:
    plan = CleanupPlan()

    candidate_users = await _rows(session, select(User).where(User.email.like("e2e-%@example.com")))
    users_by_id: dict[int, str] = {}
    for user in candidate_users:
        namespace = e2e_user_namespace(user.email, user.name)
        if namespace:
            users_by_id[user.id] = namespace
            plan.namespaces.add(namespace)
    plan.add_ids("users", list(users_by_id))

    candidate_strategies = await _rows(session, select(Strategy).where(Strategy.name.like("E2E %")))
    strategies = []
    for strategy in candidate_strategies:
        namespace = e2e_named_namespace("strategy", strategy.name)
        if namespace:
            strategies.append(strategy)
            plan.namespaces.add(namespace)
    plan.add_ids("strategies", [strategy.id for strategy in strategies])

    candidate_datasets = await _rows(session, select(ScrapedDataset).where(ScrapedDataset.name.like("E2E %")))
    datasets = []
    for dataset in candidate_datasets:
        namespace = e2e_named_namespace("dataset", dataset.name)
        if namespace:
            datasets.append(dataset)
            plan.namespaces.add(namespace)
    plan.add_ids("scraped_datasets", [dataset.id for dataset in datasets])

    candidate_matches = await _rows(session, select(Match).where(Match.competition.like("E2E%")))
    matches = []
    for match in candidate_matches:
        namespace = e2e_named_namespace("competition", match.competition)
        if namespace:
            matches.append(match)
            plan.namespaces.add(namespace)
    plan.add_ids("matches", [match.id for match in matches])

    candidate_scheduled_jobs = await _rows(session, select(ScheduledJob).where(ScheduledJob.name.like("E2E %")))
    scheduled_jobs = []
    for job in candidate_scheduled_jobs:
        namespace = e2e_named_namespace("scheduled_job", job.name) or _owner_namespace(job.config, users_by_id)
        if namespace:
            scheduled_jobs.append(job)
            plan.namespaces.add(namespace)
    plan.add_ids("scheduled_jobs", [job.id for job in scheduled_jobs])

    candidate_scrape_jobs = await _rows(session, select(ScrapeJob).where(ScrapeJob.job_type.like("e2e-%")))
    scrape_jobs = []
    for job in candidate_scrape_jobs:
        namespace = e2e_named_namespace("scrape_job", job.job_type) or _owner_namespace(job.params, users_by_id)
        params_namespace = (job.params or {}).get("namespace") if isinstance(job.params, dict) else None
        if namespace is None and isinstance(params_namespace, str) and NAMESPACE_RE.fullmatch(params_namespace):
            namespace = params_namespace
        if namespace:
            scrape_jobs.append(job)
            plan.namespaces.add(namespace)
    plan.add_ids("scrape_jobs", [job.id for job in scrape_jobs])

    user_ids = plan.ids["users"]
    dataset_ids = plan.ids["scraped_datasets"]
    strategy_ids = plan.ids["strategies"]
    run_conditions = [PredictionRun.name.like("E2E %"), PredictionRun.name.like("Strategy: E2E %")]
    if user_ids:
        run_conditions.append(PredictionRun.user_id.in_(user_ids))
    candidate_runs = await _rows(session, select(PredictionRun).where(or_(*run_conditions)))
    runs = []
    for run in candidate_runs:
        namespace = e2e_named_namespace("prediction_run", run.name)
        if run.user_id in users_by_id:
            namespace = users_by_id[run.user_id]
        if namespace:
            runs.append(run)
            plan.namespaces.add(namespace)
    plan.add_ids("prediction_runs", [run.id for run in runs])

    bankroll_ids = await _ids(session, select(Bankroll.id).where(Bankroll.user_id.in_(user_ids))) if user_ids else []
    plan.add_ids("bankrolls", bankroll_ids)
    ticket_ids = await _ids(session, select(Ticket.id).where(Ticket.user_id.in_(user_ids))) if user_ids else []
    plan.add_ids("tickets", ticket_ids)
    ticket_batch_conditions = []
    if bankroll_ids:
        ticket_batch_conditions.append(TicketBatch.bankroll_id.in_(bankroll_ids))
    if ticket_ids:
        ticket_batch_conditions.append(Ticket.id.in_(ticket_ids))
    batch_ids: list[int] = []
    if ticket_batch_conditions:
        batch_ids = await _ids(
            session,
            select(TicketBatch.id)
            .outerjoin(Ticket, Ticket.batch_id == TicketBatch.id)
            .where(or_(*ticket_batch_conditions)),
        )
    plan.add_ids("ticket_batches", batch_ids)

    prediction_session_ids = (
        await _ids(session, select(PredictionSession.id).where(PredictionSession.user_id.in_(user_ids)))
        if user_ids
        else []
    )
    plan.add_ids("prediction_sessions", prediction_session_ids)
    plan.add_ids(
        "sessions",
        await _ids(session, select(Session.id).where(Session.user_id.in_(user_ids))) if user_ids else [],
    )
    plan.add_ids(
        "match_result_corrections",
        await _ids(
            session,
            select(MatchResultCorrection.id).where(MatchResultCorrection.corrected_by_user_id.in_(user_ids)),
        )
        if user_ids
        else [],
    )
    trading_account_ids = (
        await _ids(session, select(TradingAccount.id).where(TradingAccount.user_id.in_(user_ids))) if user_ids else []
    )
    plan.add_ids("trading_accounts", trading_account_ids)
    bookmaker_account_ids = (
        await _ids(session, select(BookmakerAccount.id).where(BookmakerAccount.bankroll_id.in_(bankroll_ids)))
        if bankroll_ids
        else []
    )
    plan.add_ids("bookmaker_accounts", bookmaker_account_ids)

    scheduled_job_ids = plan.ids["scheduled_jobs"]
    scrape_job_ids = plan.ids["scrape_jobs"]
    scheduled_run_conditions = []
    if scheduled_job_ids:
        scheduled_run_conditions.append(ScheduledJobRun.scheduled_job_id.in_(scheduled_job_ids))
    if scrape_job_ids:
        scheduled_run_conditions.append(ScheduledJobRun.scrape_job_id.in_(scrape_job_ids))
    scheduled_run_ids = (
        await _ids(session, select(ScheduledJobRun.id).where(or_(*scheduled_run_conditions)))
        if scheduled_run_conditions
        else []
    )
    plan.add_ids("scheduled_job_runs", scheduled_run_ids)
    plan.add_ids(
        "task_outbox",
        await _ids(session, select(TaskOutbox.id).where(TaskOutbox.run_id.in_(scheduled_run_ids)))
        if scheduled_run_ids
        else [],
    )
    plan.add_ids(
        "scrape_job_logs",
        await _ids(session, select(ScrapeJobLog.id).where(ScrapeJobLog.job_id.in_(scrape_job_ids)))
        if scrape_job_ids
        else [],
    )

    receipt_conditions = []
    if scrape_job_ids:
        receipt_conditions.append(ProviderObservationReceipt.scrape_job_id.in_(scrape_job_ids))
        receipt_conditions.append(ProviderObservationReceipt.scrape_job_id_snapshot.in_(scrape_job_ids))
    if scheduled_run_ids:
        receipt_conditions.append(ProviderObservationReceipt.scheduled_job_run_id.in_(scheduled_run_ids))
        receipt_conditions.append(ProviderObservationReceipt.scheduled_job_run_id_snapshot.in_(scheduled_run_ids))
    if dataset_ids:
        receipt_conditions.append(ProviderObservationReceipt.origin_dataset_id.in_(dataset_ids))
        receipt_conditions.append(ProviderObservationReceipt.origin_dataset_id_snapshot.in_(dataset_ids))
    provider_receipts = (
        await _rows(session, select(ProviderObservationReceipt).where(or_(*receipt_conditions)))
        if receipt_conditions
        else []
    )
    plan.add_ids("provider_observation_receipts", [row.id for row in provider_receipts])

    provider_dataset_links = (
        await _rows(
            session,
            select(ProviderObservationDatasetLink).where(ProviderObservationDatasetLink.dataset_id.in_(dataset_ids)),
        )
        if dataset_ids
        else []
    )
    plan.add_ids("provider_observation_dataset_links", [row.id for row in provider_dataset_links])
    provider_observation_ids = {
        *(row.observation_id for row in provider_receipts),
        *(row.observation_id for row in provider_dataset_links),
    }
    provider_target_match_ids = plan.ids["matches"]

    async def _mapping_history(model, *, target_match: bool = False):
        conditions = []
        if provider_observation_ids:
            conditions.append(model.evidence_observation_id.in_(provider_observation_ids))
        if target_match and provider_target_match_ids:
            conditions.append(model.match_id.in_(provider_target_match_ids))
        seeds = await _rows(session, select(model).where(or_(*conditions))) if conditions else []
        identities = {(row.adapter_key, row.source_key, row.source_id) for row in seeds}
        if not identities:
            return []
        return await _rows(
            session,
            select(model).where(
                or_(
                    *(
                        and_(
                            model.adapter_key == adapter_key,
                            model.source_key == source_key,
                            model.source_id == source_id,
                        )
                        for adapter_key, source_key, source_id in identities
                    )
                )
            ),
        )

    provider_team_mappings = await _mapping_history(TeamProviderMapping)
    provider_competition_mappings = await _mapping_history(CompetitionProviderMapping)
    provider_match_mappings = await _mapping_history(MatchProviderMapping, target_match=True)
    if any(row.state == "accepted" for row in provider_team_mappings):
        plan.blockers.append("provider team mapping history includes a canonical target outside E2E ownership")
    if any(row.state == "accepted" for row in provider_competition_mappings):
        plan.blockers.append("provider competition mapping history includes a canonical target outside E2E ownership")
    external_match_targets = sorted(
        {
            row.match_id
            for row in provider_match_mappings
            if row.state == "accepted" and row.match_id not in provider_target_match_ids
        }
    )
    if external_match_targets:
        plan.blockers.append(
            f"provider match mapping history includes non-E2E canonical matches: {external_match_targets[:10]}"
        )
    for name, rows in (
        ("provider_team_mappings", provider_team_mappings),
        ("provider_competition_mappings", provider_competition_mappings),
        ("provider_match_mappings", provider_match_mappings),
    ):
        plan.add_ids(name, [row.id for row in rows])
        provider_observation_ids.update(
            row.evidence_observation_id for row in rows if row.evidence_observation_id is not None
        )

    for name, candidate_model, mappings in (
        ("provider_team_mapping_candidates", TeamProviderMappingCandidate, provider_team_mappings),
        (
            "provider_competition_mapping_candidates",
            CompetitionProviderMappingCandidate,
            provider_competition_mappings,
        ),
        ("provider_match_mapping_candidates", MatchProviderMappingCandidate, provider_match_mappings),
    ):
        mapping_ids = [row.id for row in mappings]
        plan.add_ids(
            name,
            await _ids(session, select(candidate_model.id).where(candidate_model.mapping_id.in_(mapping_ids)))
            if mapping_ids
            else [],
        )

    plan.add_ids("provider_observations", list(provider_observation_ids))
    if provider_observation_ids:
        conflicts = await _rows(
            session,
            select(ProviderObservationConflict).where(
                or_(
                    ProviderObservationConflict.left_observation_id.in_(provider_observation_ids),
                    ProviderObservationConflict.right_observation_id.in_(provider_observation_ids),
                )
            ),
        )
        plan.add_ids("provider_observation_conflicts", [row.id for row in conflicts])
        external_conflict_observations = sorted(
            {
                observation_id
                for row in conflicts
                for observation_id in (row.left_observation_id, row.right_observation_id)
                if observation_id not in provider_observation_ids
            }
        )
        if external_conflict_observations:
            plan.blockers.append(
                f"provider observations conflict with non-E2E observations: {external_conflict_observations[:10]}"
            )
        selected_observations = await _rows(
            session, select(ProviderObservation).where(ProviderObservation.id.in_(provider_observation_ids))
        )
        candidate_slot_ids = {row.slot_id for row in selected_observations}
        slots_with_external_observations = set(
            await _ids(
                session,
                select(ProviderObservation.slot_id).where(
                    ProviderObservation.slot_id.in_(candidate_slot_ids),
                    ProviderObservation.id.not_in(provider_observation_ids),
                ),
            )
        )
        plan.add_ids("provider_observation_slots", list(candidate_slot_ids - slots_with_external_observations))
    else:
        plan.add_ids("provider_observation_conflicts", [])
        plan.add_ids("provider_observation_slots", [])

    run_ids = plan.ids["prediction_runs"]
    match_ids = plan.ids["matches"]
    plan.add_ids(
        "model_predictions",
        await _ids(session, select(ModelPrediction.id).where(ModelPrediction.run_id.in_(run_ids))) if run_ids else [],
    )
    plan.add_ids(
        "ensemble_predictions",
        await _ids(session, select(EnsemblePrediction.id).where(EnsemblePrediction.run_id.in_(run_ids)))
        if run_ids
        else [],
    )
    plan.add_ids(
        "predictions",
        await _ids(session, select(Prediction.id).where(Prediction.session_id.in_(prediction_session_ids)))
        if prediction_session_ids
        else [],
    )

    plan.add_ids(
        "ticket_legs",
        await _ids(session, select(TicketLeg.id).where(TicketLeg.ticket_id.in_(ticket_ids))) if ticket_ids else [],
    )
    placement_ids = (
        await _ids(session, select(BetPlacement.id).where(BetPlacement.ticket_id.in_(ticket_ids))) if ticket_ids else []
    )
    plan.add_ids("bet_placements", placement_ids)
    settlement_conditions = []
    if ticket_ids:
        settlement_conditions.append(Settlement.ticket_id.in_(ticket_ids))
    if placement_ids:
        settlement_conditions.append(Settlement.bet_placement_id.in_(placement_ids))
    plan.add_ids(
        "settlements",
        await _ids(session, select(Settlement.id).where(or_(*settlement_conditions))) if settlement_conditions else [],
    )
    ledger_conditions = []
    if bankroll_ids:
        ledger_conditions.append(LedgerEntry.bankroll_id.in_(bankroll_ids))
    if ticket_ids:
        ledger_conditions.append(LedgerEntry.ticket_id.in_(ticket_ids))
    if placement_ids:
        ledger_conditions.append(LedgerEntry.placement_id.in_(placement_ids))
    plan.add_ids(
        "ledger_entries",
        await _ids(session, select(LedgerEntry.id).where(or_(*ledger_conditions))) if ledger_conditions else [],
    )

    execution_conditions = []
    if user_ids:
        execution_conditions.append(ExecutionIntent.user_id.in_(user_ids))
    if ticket_ids:
        execution_conditions.append(ExecutionIntent.ticket_id.in_(ticket_ids))
    if trading_account_ids:
        execution_conditions.append(ExecutionIntent.trading_account_id.in_(trading_account_ids))
    execution_intent_ids = (
        await _ids(session, select(ExecutionIntent.id).where(or_(*execution_conditions)))
        if execution_conditions
        else []
    )
    plan.add_ids("execution_intents", execution_intent_ids)
    plan.add_ids(
        "execution_orders",
        await _ids(
            session, select(ExecutionOrder.id).where(ExecutionOrder.execution_intent_id.in_(execution_intent_ids))
        )
        if execution_intent_ids
        else [],
    )
    plan.add_ids(
        "execution_events",
        await _ids(
            session, select(ExecutionEvent.id).where(ExecutionEvent.execution_intent_id.in_(execution_intent_ids))
        )
        if execution_intent_ids
        else [],
    )

    plan.add_ids(
        "odds_entries",
        await _ids(session, select(OddsEntry.id).where(OddsEntry.match_id.in_(match_ids))) if match_ids else [],
    )
    plan.add_ids(
        "match_stats",
        await _ids(session, select(MatchStat.id).where(MatchStat.match_id.in_(match_ids))) if match_ids else [],
    )
    plan.add_ids(
        "match_sources",
        await _ids(session, select(MatchSource.id).where(MatchSource.match_id.in_(match_ids))) if match_ids else [],
    )

    await _add_reference_blockers(session, plan, dataset_ids=dataset_ids, strategy_ids=strategy_ids)
    return plan


async def _add_reference_blockers(
    session: AsyncSession,
    plan: CleanupPlan,
    *,
    dataset_ids: list[int],
    strategy_ids: list[int],
) -> None:
    run_ids = set(plan.ids.get("prediction_runs", []))
    ticket_ids = set(plan.ids.get("tickets", []))
    match_ids = plan.ids.get("matches", [])
    batch_ids = plan.ids.get("ticket_batches", [])
    provider_observation_ids = plan.ids.get("provider_observations", [])

    if strategy_ids:
        external = await _ids(
            session,
            select(PredictionRun.id).where(
                PredictionRun.strategy_id.in_(strategy_ids), PredictionRun.id.not_in(run_ids)
            ),
        )
        if external:
            plan.blockers.append(f"strategies referenced by non-E2E prediction runs: {external[:10]}")
    if dataset_ids:
        external = await _ids(
            session,
            select(PredictionRun.id).where(
                PredictionRun.source_dataset_id.in_(dataset_ids), PredictionRun.id.not_in(run_ids)
            ),
        )
        if external:
            plan.blockers.append(f"datasets referenced by non-E2E prediction runs: {external[:10]}")
    if batch_ids:
        external = await _ids(
            session,
            select(Ticket.id).where(Ticket.batch_id.in_(batch_ids), Ticket.id.not_in(ticket_ids)),
        )
        if external:
            plan.blockers.append(f"ticket batches contain non-E2E tickets: {external[:10]}")
    if match_ids:
        external_ticket_legs = await _ids(
            session,
            select(TicketLeg.id).where(TicketLeg.match_id.in_(match_ids), TicketLeg.ticket_id.not_in(ticket_ids)),
        )
        if external_ticket_legs:
            plan.blockers.append(f"matches referenced by non-E2E ticket legs: {external_ticket_legs[:10]}")
        external_model_predictions = await _ids(
            session,
            select(ModelPrediction.id).where(
                ModelPrediction.match_id.in_(match_ids), ModelPrediction.run_id.not_in(run_ids)
            ),
        )
        if external_model_predictions:
            plan.blockers.append(f"matches referenced by non-E2E model predictions: {external_model_predictions[:10]}")
        external_ensemble_predictions = await _ids(
            session,
            select(EnsemblePrediction.id).where(
                EnsemblePrediction.match_id.in_(match_ids), EnsemblePrediction.run_id.not_in(run_ids)
            ),
        )
        if external_ensemble_predictions:
            plan.blockers.append(
                f"matches referenced by non-E2E ensemble predictions: {external_ensemble_predictions[:10]}"
            )
    if provider_observation_ids:
        selected_receipts = set(plan.ids.get("provider_observation_receipts", []))
        selected_links = set(plan.ids.get("provider_observation_dataset_links", []))
        external_receipts = await _ids(
            session,
            select(ProviderObservationReceipt.id).where(
                ProviderObservationReceipt.observation_id.in_(provider_observation_ids),
                ProviderObservationReceipt.id.not_in(selected_receipts),
            ),
        )
        external_links = await _ids(
            session,
            select(ProviderObservationDatasetLink.id).where(
                ProviderObservationDatasetLink.observation_id.in_(provider_observation_ids),
                ProviderObservationDatasetLink.id.not_in(selected_links),
            ),
        )
        if external_receipts:
            plan.blockers.append(f"provider observations have non-E2E receipts: {external_receipts[:10]}")
        if external_links:
            plan.blockers.append(f"provider observations have non-E2E dataset links: {external_links[:10]}")


DELETE_ORDER = (
    ("task_outbox", TaskOutbox),
    ("execution_events", ExecutionEvent),
    ("execution_orders", ExecutionOrder),
    ("execution_intents", ExecutionIntent),
    ("provider_observation_conflicts", ProviderObservationConflict),
    ("provider_observation_dataset_links", ProviderObservationDatasetLink),
    ("provider_observation_receipts", ProviderObservationReceipt),
    ("provider_team_mapping_candidates", TeamProviderMappingCandidate),
    ("provider_competition_mapping_candidates", CompetitionProviderMappingCandidate),
    ("provider_match_mapping_candidates", MatchProviderMappingCandidate),
    ("provider_team_mappings", TeamProviderMapping),
    ("provider_competition_mappings", CompetitionProviderMapping),
    ("provider_match_mappings", MatchProviderMapping),
    ("provider_observations", ProviderObservation),
    ("provider_observation_slots", ProviderObservationSlot),
    ("settlements", Settlement),
    ("ledger_entries", LedgerEntry),
    ("bet_placements", BetPlacement),
    ("ticket_legs", TicketLeg),
    ("tickets", Ticket),
    ("ticket_batches", TicketBatch),
    ("model_predictions", ModelPrediction),
    ("ensemble_predictions", EnsemblePrediction),
    ("prediction_runs", PredictionRun),
    ("predictions", Prediction),
    ("prediction_sessions", PredictionSession),
    ("odds_entries", OddsEntry),
    ("match_stats", MatchStat),
    ("match_sources", MatchSource),
    ("match_result_corrections", MatchResultCorrection),
    ("matches", Match),
    ("scrape_job_logs", ScrapeJobLog),
    ("scheduled_job_runs", ScheduledJobRun),
    ("scheduled_jobs", ScheduledJob),
    ("scrape_jobs", ScrapeJob),
    ("scraped_datasets", ScrapedDataset),
    ("bookmaker_accounts", BookmakerAccount),
    ("trading_accounts", TradingAccount),
    ("bankrolls", Bankroll),
    ("sessions", Session),
    ("strategies", Strategy),
    ("users", User),
)


async def apply_cleanup_plan(session: AsyncSession, plan: CleanupPlan) -> dict[str, int]:
    validate_plan_for_apply(plan)
    deleted: dict[str, int] = {}
    for name, model in (
        ("provider_team_mappings", TeamProviderMapping),
        ("provider_competition_mappings", CompetitionProviderMapping),
        ("provider_match_mappings", MatchProviderMapping),
    ):
        ids = plan.ids.get(name, [])
        if ids:
            await session.execute(update(model).where(model.id.in_(ids)).values(selected_candidate_id=None))
    for name, model in DELETE_ORDER:
        ids = plan.ids.get(name, [])
        if not ids:
            continue
        result = await session.execute(delete(model).where(model.id.in_(ids)))
        deleted[name] = int(result.rowcount or 0)
    return deleted


def render_plan(plan: CleanupPlan, *, applied: bool, deleted: dict[str, int] | None = None) -> str:
    mode = "APPLIED" if applied else "DRY-RUN"
    lines = [f"E2E fixture cleanup: {mode}", f"Namespaces: {len(plan.namespaces)}"]
    for name, count in sorted(plan.counts.items()):
        lines.append(f"  {name}: {count}")
    if plan.blockers:
        lines.append("Blockers:")
        lines.extend(f"  - {blocker}" for blocker in plan.blockers)
    if deleted is not None:
        lines.append("Deleted:")
        lines.extend(f"  {name}: {count}" for name, count in sorted(deleted.items()))
    if not applied:
        lines.append(f"No rows changed. Apply only with --apply --confirm-token {CONFIRMATION_PHRASE}.")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the discovered deletion plan")
    parser.add_argument(
        "--confirm-token",
        default=os.getenv(CONFIRMATION_ENV),
        help=f"Required with --apply; may also be supplied through {CONFIRMATION_ENV}",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    require_apply_confirmation(apply=args.apply, confirmation=args.confirm_token)
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                plan = await build_cleanup_plan(session)
                if args.apply:
                    validate_plan_for_apply(plan)
                    deleted = await apply_cleanup_plan(session, plan)
                    print(render_plan(plan, applied=True, deleted=deleted))
                else:
                    print(render_plan(plan, applied=False))
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    args = _parse_args()
    try:
        return asyncio.run(_run(args))
    except CleanupGuardError as exc:
        print(f"Cleanup refused: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
