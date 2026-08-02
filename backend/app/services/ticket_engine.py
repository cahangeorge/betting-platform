from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import isfinite

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bankroll import Bankroll, LedgerEntry
from app.models.match import Match, OddsEntry
from app.models.odds_lineage import TicketLegQuoteSnapshot
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.ticket import BetPlacement, Settlement, Ticket, TicketBatch, TicketLeg
from app.models.trading import ExecutionIntent
from app.services.model_governance import assess_prediction_runs_governance, pipeline_prediction_output_is_complete
from app.services.odds_quotes import PREMATCH_MAX_AGE, select_quote_set
from app.services.portfolio_risk import (
    LeagueExposure,
    PortfolioExposure,
    RiskAssessment,
    RiskCandidate,
    RiskContext,
    assess_portfolio_risk,
)
from app.services.risk_policy import load_active_policy, load_risk_state, orm_policy_to_domain
from app.services.staking import StakeCalculation, StakingError, calculate_stake, quantize_money

NOT_STARTED_MATCH_STATUSES = {"scheduled", "upcoming", "not_started", "not started", "pending"}
SUPPORTED_TICKET_MARKETS = {"1x2", "btts", "ou_2_5"}
DIFFICULTY_LEGS = {
    "safe": 1,
    "low": 1,
    "balanced": 2,
    "medium": 2,
    "aggressive": 3,
    "high": 3,
}
SETTLEMENT_OUTCOMES = {"won", "lost", "void"}
TICKET_LEG_SNAPSHOT_FIELDS = (
    "prediction_run_id_snapshot",
    "model_probability_snapshot",
    "market_probability_snapshot",
    "market_probability_basis_snapshot",
    "expected_value_snapshot",
    "edge_pct_snapshot",
    "reliability_label_snapshot",
    "reliability_score_snapshot",
)


class TicketGenerationError(ValueError):
    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


class TicketRiskPolicyRequiredError(TicketGenerationError):
    """Generation cannot continue until an explicit bankroll policy exists."""


class TicketManualRiskConflictError(ValueError):
    """A manual ticket cannot be opened because its current risk assessment blocks it."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


class TicketActivationConflictError(ValueError):
    """The batch exists but cannot transition from its current draft state."""


class TicketRefreshConflictError(ValueError):
    """A generated batch cannot be refreshed from its current revision/state."""


TICKET_FORMAT_LEGS = {"single": 1, "double": 2, "treble": 3}


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _p4_canonical_fixture(prediction) -> tuple[dict | None, str | None]:
    """Return immutable P4 fixture evidence; legacy predictions retain match reads."""
    report = getattr(prediction, "quality_report", None)
    if not isinstance(report, dict) or report.get("pipeline_contract_version") != "penaltyblog-model-pipeline/v1":
        return None, None
    snapshot = report.get("canonical_fixture")
    if not isinstance(snapshot, dict) or snapshot.get("match_id") != getattr(prediction, "match_id", None):
        return None, "canonical_fixture_missing_or_invalid"
    home, away, kickoff, competition_key = (
        snapshot.get("home_team"),
        snapshot.get("away_team"),
        snapshot.get("kickoff_at"),
        snapshot.get("competition_key"),
    )
    if (
        not isinstance(home, str)
        or not home.strip()
        or not isinstance(away, str)
        or not away.strip()
        or not isinstance(kickoff, str)
        or not isinstance(competition_key, str)
        or not (competition_key := " ".join(competition_key.split()))
    ):
        return None, "canonical_fixture_missing_or_invalid"
    try:
        normalized_kickoff = _utc(datetime.fromisoformat(kickoff.replace("Z", "+00:00")))
    except ValueError:
        return None, "canonical_fixture_missing_or_invalid"
    return {
        "home_team": home,
        "away_team": away,
        "kickoff": normalized_kickoff,
        "competition_key": competition_key,
    }, None


def _risk_finding_payload(finding) -> dict:
    payload = asdict(finding)
    return {key: (str(value) if isinstance(value, Decimal) else value) for key, value in payload.items()}


def _risk_assessment_payload(assessment: RiskAssessment) -> dict:
    return {
        "policy_version": assessment.policy_version,
        "allowed": assessment.allowed,
        "blockers": [_risk_finding_payload(item) for item in assessment.blockers],
        "warnings": [_risk_finding_payload(item) for item in assessment.warnings],
    }


def _staking_payload(calculation: StakeCalculation) -> dict:
    return {
        "mode": calculation.mode.value,
        "eligible": calculation.eligible,
        "stake": str(calculation.stake),
        "stake_percent": str(calculation.stake_percent),
        "full_kelly_fraction": (
            str(calculation.full_kelly_fraction) if calculation.full_kelly_fraction is not None else None
        ),
        "applied_kelly_fraction": (
            str(calculation.applied_kelly_fraction) if calculation.applied_kelly_fraction is not None else None
        ),
        "reason_code": calculation.reason_code,
    }


def _governance_blocker_payload(assessment: dict) -> dict:
    mode = assessment.get("mode", "manual")
    blocked_runs = [item for item in assessment.get("runs", []) if not item.get("allowed")]
    return {
        "code": f"model_governance_{mode}_blocked",
        "scope": "model_governance",
        "message": f"Versioned prediction runs are not certified for {mode} paper use",
        "runs": blocked_runs,
    }


async def _revalidate_batch_governance(
    db: AsyncSession,
    *,
    batch: TicketBatch,
    user_id: int,
    automated: bool,
    now: datetime,
) -> dict | None:
    report = batch.generation_report if isinstance(batch.generation_report, dict) else {}
    generated_assessment = report.get("governance_assessment")
    generated_runs = generated_assessment.get("runs", []) if isinstance(generated_assessment, dict) else []
    versioned_run_ids = [
        int(item["run_id"])
        for item in generated_runs
        if isinstance(item, dict) and item.get("model_version_id") is not None and item.get("run_id") is not None
    ]
    if not versioned_run_ids:
        return None
    result = await db.execute(
        select(PredictionRun).where(
            PredictionRun.id.in_(versioned_run_ids),
            PredictionRun.user_id == user_id,
        )
    )
    runs_by_id = {run.id: run for run in result.scalars().all()}
    if any(run_id not in runs_by_id for run_id in versioned_run_ids):
        return {
            "allowed": False,
            "mode": "scheduled" if automated else "manual",
            "checked_at": now.isoformat(),
            "runs": [
                {
                    "run_id": run_id,
                    "allowed": False,
                    "reason": "versioned_prediction_run_missing_or_foreign",
                }
                for run_id in versioned_run_ids
                if run_id not in runs_by_id
            ],
            "model_evaluation_ids": [],
        }
    return await assess_prediction_runs_governance(
        db,
        user_id=user_id,
        runs=[runs_by_id[run_id] for run_id in versioned_run_ids],
        automated=automated,
        now=now,
    )


def _format_from_difficulty(difficulty: str | None) -> str:
    if difficulty is None:
        return "single"
    return {1: "single", 2: "double", 3: "treble"}[_legs_for_difficulty(difficulty)]


class TicketBatchDiscardConflictError(ValueError):
    """The batch exists but contains non-draft state or financial/execution artifacts."""


class TicketSettlementConflictError(ValueError):
    """The ticket cannot transition from open to a terminal settlement state."""


def _market_probability_and_odds_fields(market: str, selection: str) -> tuple[str, str] | None:
    market_key = (market or "").lower()
    selection_key = (selection or "").lower()
    if market_key == "1x2":
        return {
            "home": ("home_prob", "home_odds"),
            "draw": ("draw_prob", "draw_odds"),
            "away": ("away_prob", "away_odds"),
        }.get(selection_key)
    if market_key in {"btts", "both_score", "both_teams_to_score"}:
        return {
            "yes": ("home_prob", "home_odds"),
            "no": ("away_prob", "away_odds"),
        }.get(selection_key)
    if market_key in {"ou_2_5", "over_under", "over_under_2_5", "overunder", "totals"}:
        return {
            "over": ("home_prob", "home_odds"),
            "under": ("away_prob", "away_odds"),
        }.get(selection_key)
    return None


def _fallback_selection_for_prediction(prediction: ModelPrediction) -> str:
    market_key = (prediction.market or "").lower()
    if market_key == "1x2":
        candidates = [
            ("home", prediction.home_prob or 0),
            ("draw", prediction.draw_prob or 0),
            ("away", prediction.away_prob or 0),
        ]
    elif market_key in {"btts", "both_score", "both_teams_to_score"}:
        candidates = [("yes", prediction.home_prob or 0), ("no", prediction.away_prob or 0)]
    elif market_key in {"ou_2_5", "over_under", "over_under_2_5", "overunder", "totals"}:
        candidates = [("over", prediction.home_prob or 0), ("under", prediction.away_prob or 0)]
    else:
        candidates = [("home", prediction.home_prob or 0), ("away", prediction.away_prob or 0)]
    return max(candidates, key=lambda item: item[1])[0]


def _prediction_snapshot_fields(
    prediction: ModelPrediction,
    *,
    selection: str,
    selected_odds: float,
) -> dict:
    """Build server-owned audit evidence for a selected prediction outcome."""

    quality_report = prediction.quality_report if isinstance(prediction.quality_report, dict) else {}
    field_names = _market_probability_and_odds_fields(prediction.market, selection)
    probability_field = field_names[0] if field_names is not None else None
    probability = getattr(prediction, probability_field, None) if probability_field is not None else None
    try:
        probability = float(probability)
    except (TypeError, ValueError):
        probability = None
    if probability is not None and (not isfinite(probability) or probability <= 0 or probability > 1):
        probability = None

    market_payload = quality_report.get("market", {}) if isinstance(quality_report, dict) else {}
    market_probabilities = market_payload.get("probabilities", {}) if isinstance(market_payload, dict) else {}
    market_probability = market_probabilities.get(selection) if isinstance(market_probabilities, dict) else None
    market_probability_basis = "consensus_de_vig"
    try:
        market_probability = float(market_probability)
    except (TypeError, ValueError):
        market_probability = 1.0 / selected_odds
        market_probability_basis = "inverse_selected_odds"
    if not isfinite(market_probability) or market_probability <= 0 or market_probability > 1:
        market_probability = 1.0 / selected_odds
        market_probability_basis = "inverse_selected_odds"

    expected_value = prediction.expected_value
    try:
        expected_value = float(expected_value)
    except (TypeError, ValueError):
        expected_value = probability * selected_odds - 1.0 if probability is not None else None
    if expected_value is not None and not isfinite(expected_value):
        expected_value = probability * selected_odds - 1.0 if probability is not None else None

    edge_payload = quality_report.get("edge", {}) if isinstance(quality_report, dict) else {}
    edge_pct = edge_payload.get("pick_edge_pct") if isinstance(edge_payload, dict) else None
    if edge_pct is None and isinstance(edge_payload, dict):
        edge_pct = edge_payload.get(selection)
    try:
        edge_pct = float(edge_pct)
    except (TypeError, ValueError):
        edge_pct = expected_value * 100.0 if expected_value is not None else None
    if edge_pct is not None and not isfinite(edge_pct):
        edge_pct = expected_value * 100.0 if expected_value is not None else None

    reliability = quality_report.get("reliability", {}) if isinstance(quality_report, dict) else {}
    reliability_label = reliability.get("label") if isinstance(reliability, dict) else None
    reliability_score = reliability.get("score") if isinstance(reliability, dict) else None
    try:
        reliability_score = float(reliability_score) if reliability_score is not None else None
    except (TypeError, ValueError):
        reliability_score = None
    if reliability_score is not None and not isfinite(reliability_score):
        reliability_score = None

    return {
        "prediction_run_id_snapshot": getattr(prediction, "run_id", None),
        "model_probability_snapshot": probability,
        "market_probability_snapshot": market_probability,
        "market_probability_basis_snapshot": market_probability_basis,
        "expected_value_snapshot": expected_value,
        "edge_pct_snapshot": edge_pct,
        "reliability_label_snapshot": str(reliability_label) if reliability_label is not None else None,
        "reliability_score_snapshot": reliability_score,
    }


def _build_ticket_candidate(
    prediction: ModelPrediction,
    *,
    min_odds: float,
    max_odds: float,
) -> dict | None:
    candidate, _reason = _build_ticket_candidate_with_reason(
        prediction,
        min_odds=min_odds,
        max_odds=max_odds,
    )
    return candidate


def _build_ticket_candidate_with_reason(
    prediction: ModelPrediction,
    *,
    min_odds: float,
    max_odds: float,
) -> tuple[dict | None, str | None]:
    quality_report = prediction.quality_report if isinstance(prediction.quality_report, dict) else {}
    model_payload = quality_report.get("model", {}) if isinstance(quality_report, dict) else {}
    selection = str(model_payload.get("pick") or _fallback_selection_for_prediction(prediction)).lower()
    field_names = _market_probability_and_odds_fields(prediction.market, selection)
    if field_names is None:
        return None, "market_or_selection_unsupported"
    probability_field, odds_field = field_names

    probability = getattr(prediction, probability_field, None)
    odds = getattr(prediction, odds_field, None)
    bookmaker = None

    market_payload = quality_report.get("market", {}) if isinstance(quality_report, dict) else {}
    odds_payload = market_payload.get("odds", {}) if isinstance(market_payload, dict) else {}
    selected_odds_payload = odds_payload.get(selection) if isinstance(odds_payload, dict) else None
    if isinstance(selected_odds_payload, dict):
        odds = selected_odds_payload.get("odds", odds)
        bookmaker = selected_odds_payload.get("bookmaker")

    if probability is None:
        return None, "probability_missing"
    if odds is None:
        return None, "odds_missing"
    try:
        odds = float(odds)
        probability = float(probability)
    except (TypeError, ValueError):
        return None, "odds_or_probability_invalid"
    if not isfinite(odds) or not isfinite(probability):
        return None, "odds_or_probability_invalid"
    if probability <= 0 or probability > 1:
        return None, "probability_outside_interval"
    if odds <= 1:
        return None, "odds_unusable"
    if odds < min_odds or odds > max_odds:
        return None, "odds_outside_interval"

    snapshots = _prediction_snapshot_fields(prediction, selection=selection, selected_odds=odds)
    expected_value = snapshots["expected_value_snapshot"]
    if expected_value is None:
        expected_value = probability * odds - 1.0
        snapshots["expected_value_snapshot"] = expected_value
    if snapshots["edge_pct_snapshot"] is None:
        snapshots["edge_pct_snapshot"] = expected_value * 100.0

    return (
        {
            "model_prediction_id": prediction.id,
            "prediction_run_id": getattr(prediction, "run_id", None),
            "match_id": prediction.match_id,
            "market": prediction.market,
            "selection": selection,
            "odds": odds,
            "probability": probability,
            "bookmaker": bookmaker,
            "score": expected_value,
            **snapshots,
        },
        None,
    )


def _prediction_ticket_exclusion_reason(
    prediction: ModelPrediction,
    *,
    normalized_markets: set[str],
    min_odds: float,
    max_odds: float,
    now: datetime,
) -> tuple[dict | None, str | None]:
    if (prediction.market or "").lower() not in normalized_markets:
        return None, "market_not_requested"

    match = getattr(prediction, "match", None)
    if match is None:
        return None, "match_missing"
    canonical_fixture, snapshot_error = _p4_canonical_fixture(prediction)
    if snapshot_error is not None:
        return None, snapshot_error
    kickoff = canonical_fixture["kickoff"] if canonical_fixture is not None else getattr(match, "match_date", None)
    if kickoff is None:
        return None, "kickoff_missing"
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    else:
        kickoff = kickoff.astimezone(timezone.utc)
    if kickoff <= now:
        return None, "match_started_or_finished"
    if str(getattr(match, "status", "")).strip().lower() not in NOT_STARTED_MATCH_STATUSES:
        return None, "match_status_not_eligible"

    quality_report = prediction.quality_report if isinstance(prediction.quality_report, dict) else {}
    reliability = quality_report.get("reliability") if isinstance(quality_report, dict) else None
    if not isinstance(reliability, dict) or reliability.get("is_ticket_eligible") is not True:
        return None, "quality_ineligible"

    candidate, reason = _build_ticket_candidate_with_reason(
        prediction,
        min_odds=min_odds,
        max_odds=max_odds,
    )
    if candidate is not None:
        candidate["kickoff"] = kickoff
        if canonical_fixture is not None:
            candidate["team_ids"] = (canonical_fixture["home_team"], canonical_fixture["away_team"])
            candidate["league_ids"] = (canonical_fixture["competition_key"],)
    return candidate, reason


def _candidate_league_kickoffs(candidates: list[dict]) -> dict[int | str, tuple[datetime, ...]]:
    values: dict[int | str, set[datetime]] = defaultdict(set)
    for candidate in candidates:
        kickoff = candidate.get("kickoff")
        if not isinstance(kickoff, datetime):
            continue
        normalized_kickoff = _utc(kickoff)
        for league_id in candidate.get("league_ids", ()):
            values[league_id].add(normalized_kickoff)
    return {league_id: tuple(sorted(kickoffs)) for league_id, kickoffs in values.items()}


def _match_league_kickoffs(matches: list[Match]) -> dict[int | str, tuple[datetime, ...]]:
    values: dict[int | str, set[datetime]] = defaultdict(set)
    for match in matches:
        league_id = getattr(match, "competition", None)
        kickoff = getattr(match, "match_date", None)
        if league_id and kickoff is not None:
            values[league_id].add(_utc(kickoff))
    return {league_id: tuple(sorted(kickoffs)) for league_id, kickoffs in values.items()}


def _fixture_league_kickoffs(
    fixtures: list[dict | None], matches: list[Match]
) -> dict[int | str, tuple[datetime, ...]]:
    values: dict[int | str, set[datetime]] = defaultdict(set)
    for fixture, match in zip(fixtures, matches, strict=True):
        league = fixture["competition_key"] if fixture is not None else getattr(match, "competition", None)
        kickoff = fixture["kickoff"] if fixture is not None else getattr(match, "match_date", None)
        if league and kickoff is not None:
            values[league].add(_utc(kickoff))
    return {league_id: tuple(sorted(kickoffs)) for league_id, kickoffs in values.items()}


def _legs_for_difficulty(difficulty: str) -> int:
    normalized = (difficulty or "").strip().lower()
    if normalized not in DIFFICULTY_LEGS:
        raise ValueError("difficulty must be one of: " + ", ".join(sorted(DIFFICULTY_LEGS)))
    return DIFFICULTY_LEGS[normalized]


def _evaluate_ticket_candidates(
    predictions: list[ModelPrediction],
    *,
    normalized_markets: set[str],
    min_odds: float,
    max_odds: float,
    now: datetime,
    odds_entries_by_match: dict[int, list[OddsEntry]] | None = None,
) -> tuple[list[dict], dict]:
    """Evaluate ticket candidates without mutating the database.

    Generation and preflight must use identical eligibility rules. Keeping the
    per-prediction evaluation in one pure helper prevents the UI's preview from
    drifting away from the actual ticket-generation gate.
    """

    candidates: list[dict] = []
    excluded_by_reason: dict[str, int] = defaultdict(int)
    eligible_by_run: dict[str, int] = defaultdict(int)
    excluded_by_run: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for prediction in predictions:
        candidate, exclusion_reason = _prediction_ticket_exclusion_reason(
            prediction,
            normalized_markets=normalized_markets,
            min_odds=min_odds,
            max_odds=max_odds,
            now=now,
        )
        if candidate is None:
            reason = exclusion_reason or "unknown"
            excluded_by_reason[reason] += 1
            excluded_by_run[str(prediction.run_id)][reason] += 1
            continue
        if odds_entries_by_match is not None:
            quote_set = select_quote_set(
                odds_entries_by_match.get(int(prediction.match_id), []),
                market=prediction.market,
                as_of=now,
                max_age=PREMATCH_MAX_AGE,
            )
            if not quote_set.is_ticket_eligible:
                reason = quote_set.reason_codes[0] if quote_set.reason_codes else "quote_ineligible"
                excluded_by_reason[reason] += 1
                excluded_by_run[str(prediction.run_id)][reason] += 1
                continue
            quote = quote_set.quote_for(str(candidate["selection"]))
            market_probability = quote_set.consensus_probabilities.get(str(candidate["selection"]))
            if quote is None or market_probability is None:
                reason = "quote_selection_missing"
                excluded_by_reason[reason] += 1
                excluded_by_run[str(prediction.run_id)][reason] += 1
                continue
            if quote.price < min_odds or quote.price > max_odds:
                reason = "odds_outside_interval"
                excluded_by_reason[reason] += 1
                excluded_by_run[str(prediction.run_id)][reason] += 1
                continue
            expected_value = float(candidate["probability"]) * quote.price - 1.0
            if expected_value <= 0:
                reason = "expected_value_not_positive"
                excluded_by_reason[reason] += 1
                excluded_by_run[str(prediction.run_id)][reason] += 1
                continue
            candidate.update(
                {
                    "odds": quote.price,
                    "bookmaker": quote.bookmaker,
                    "score": expected_value,
                    "market_probability_snapshot": market_probability,
                    "market_probability_basis_snapshot": "consensus_de_vig",
                    "expected_value_snapshot": expected_value,
                    "edge_pct_snapshot": (float(candidate["probability"]) - market_probability) * 100.0,
                    "quote_entry_id": quote.entry_id,
                    "quote_snapshot_id": quote.snapshot_id if isinstance(quote.snapshot_id, int) else None,
                    "quote_observed_at": quote.observed_at,
                }
            )
        match = getattr(prediction, "match", None)
        if "team_ids" not in candidate:
            candidate["team_ids"] = tuple(
                value for value in (getattr(match, "home_team", None), getattr(match, "away_team", None)) if value
            )
            candidate["league_ids"] = tuple(value for value in (getattr(match, "competition", None),) if value)
        candidates.append(candidate)
        eligible_by_run[str(prediction.run_id)] += 1

    candidates.sort(key=lambda item: (-item["score"], item["model_prediction_id"]))
    report = {
        "scanned_predictions": len(predictions),
        "scanned_predictions_by_run": dict(
            sorted(
                ((str(run_id), count) for run_id, count in _count_predictions_by_run(predictions).items()),
                key=lambda item: int(item[0]),
            )
        ),
        "eligible_candidates": len(candidates),
        "eligible_candidates_by_run": dict(sorted(eligible_by_run.items(), key=lambda item: int(item[0]))),
        "eligible_prediction_ids": sorted(candidate["model_prediction_id"] for candidate in candidates),
        "excluded_predictions": sum(excluded_by_reason.values()),
        "excluded_by_reason": dict(sorted(excluded_by_reason.items())),
        "excluded_by_run": {
            run: dict(sorted(reasons.items()))
            for run, reasons in sorted(excluded_by_run.items(), key=lambda item: int(item[0]))
        },
        "eligible_unique_matches": len({candidate["match_id"] for candidate in candidates}),
    }
    return candidates, report


async def _load_odds_entries_by_match(
    db: AsyncSession,
    match_ids: list[int],
) -> dict[int, list[OddsEntry]]:
    if not match_ids:
        return {}
    result = await db.execute(
        select(OddsEntry)
        .options(selectinload(OddsEntry.odds_snapshot))
        .where(OddsEntry.match_id.in_(match_ids))
        .order_by(OddsEntry.match_id.asc(), OddsEntry.timestamp.desc().nulls_last(), OddsEntry.id.desc())
    )
    grouped: dict[int, list[OddsEntry]] = defaultdict(list)
    for entry in result.scalars().all():
        grouped[int(entry.match_id)].append(entry)
    return dict(grouped)


async def _load_portfolio_exposure(
    db: AsyncSession,
    *,
    bankroll_id: int,
    now: datetime,
) -> PortfolioExposure:
    active_result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.legs).selectinload(TicketLeg.match),
            selectinload(Ticket.legs).selectinload(TicketLeg.model_prediction).selectinload(ModelPrediction.run),
        )
        .where(Ticket.bankroll_id == bankroll_id, Ticket.status.in_(("open", "watchlist")))
    )
    active_tickets = list(active_result.scalars().unique().all())
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    ledger_result = await db.execute(
        select(LedgerEntry).where(
            LedgerEntry.bankroll_id == bankroll_id,
            LedgerEntry.entry_type == "stake",
            LedgerEntry.created_at >= week_ago,
        )
    )
    ledgers = list(ledger_result.scalars().all())

    by_match: dict[int | str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    by_team: dict[int | str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    league_exposures: list[LeagueExposure] = []
    pipeline_run_integrity: dict[int, bool] = {}
    open_total = Decimal("0.00")
    for ticket in active_tickets:
        stake = quantize_money(ticket.stake)
        open_total += stake
        for leg in getattr(ticket, "legs", []) or []:
            if leg.match_id is not None:
                by_match[leg.match_id] += stake
            match = getattr(leg, "match", None)
            if match is None:
                continue
            # A leg with a run snapshot once had an attributable prediction.
            # Do not silently reclassify it as legacy after that prediction has
            # been removed: doing so would make exposure fall back to mutable
            # Match fields and could bypass governed P4 league limits.
            if (
                getattr(leg, "prediction_run_id_snapshot", None) is not None
                and getattr(leg, "model_prediction", None) is None
            ):
                raise ValueError("Active ticket leg has lost immutable prediction lineage")
            prediction = getattr(leg, "model_prediction", None)
            prediction_run = getattr(prediction, "run", None)
            if (
                prediction_run is not None
                and prediction_run.pipeline_contract_version == "penaltyblog-model-pipeline/v1"
            ):
                model_version_id = prediction_run.model_version_id
                if getattr(leg, "prediction_run_id_snapshot", None) != prediction_run.id or model_version_id is None:
                    raise ValueError("Governed active ticket has incomplete prediction-run lineage")
                run_id = int(prediction_run.id)
                if run_id not in pipeline_run_integrity:
                    pipeline_run_integrity[run_id] = await pipeline_prediction_output_is_complete(
                        db, prediction_run, int(model_version_id)
                    )
                if not pipeline_run_integrity[run_id]:
                    raise ValueError("Governed active ticket has incomplete or tampered prediction output")
            canonical_fixture, snapshot_error = _p4_canonical_fixture(prediction)
            if snapshot_error is not None:
                raise ValueError("Governed active ticket has invalid canonical fixture evidence")
            teams = (
                (canonical_fixture["home_team"], canonical_fixture["away_team"])
                if canonical_fixture is not None
                else (getattr(match, "home_team", None), getattr(match, "away_team", None))
            )
            for team in teams:
                if team:
                    by_team[str(team)] += stake
            league = (
                canonical_fixture["competition_key"]
                if canonical_fixture is not None
                else getattr(match, "competition", None)
            )
            kickoff = (
                canonical_fixture["kickoff"] if canonical_fixture is not None else getattr(match, "match_date", None)
            )
            if league and kickoff is not None:
                league_exposures.append(
                    LeagueExposure(
                        exposure_id=ticket.id,
                        league_id=str(league),
                        kickoff=_utc(kickoff),
                        stake=stake,
                    )
                )

    def ledger_amount(entry: LedgerEntry) -> Decimal:
        return abs(quantize_money(entry.amount))

    return PortfolioExposure(
        open_total=open_total,
        staked_last_24h=sum(
            (ledger_amount(entry) for entry in ledgers if _utc(entry.created_at) >= day_ago), Decimal("0.00")
        ),
        staked_last_7d=sum((ledger_amount(entry) for entry in ledgers), Decimal("0.00")),
        ticket_count_last_24h=sum(1 for entry in ledgers if _utc(entry.created_at) >= day_ago),
        ticket_count_last_7d=len(ledgers),
        by_match=by_match,
        by_team=by_team,
        league_exposures=tuple(league_exposures),
    )


def _project_exposure(
    exposure: PortfolioExposure,
    *,
    stake: Decimal,
    match_ids: set[int | str],
    team_ids: set[int | str],
    league_kickoffs: dict[int | str, tuple[datetime, ...]],
    exposure_id: int | str,
) -> PortfolioExposure:
    by_match = dict(exposure.by_match)
    by_team = dict(exposure.by_team)
    for key in match_ids:
        by_match[key] = by_match.get(key, Decimal("0.00")) + stake
    for key in team_ids:
        by_team[key] = by_team.get(key, Decimal("0.00")) + stake
    league_exposures = list(exposure.league_exposures)
    for league_id, kickoffs in league_kickoffs.items():
        league_exposures.extend(
            LeagueExposure(
                exposure_id=exposure_id,
                league_id=league_id,
                kickoff=kickoff,
                stake=stake,
            )
            for kickoff in kickoffs
        )
    return PortfolioExposure(
        open_total=exposure.open_total + stake,
        staked_last_24h=exposure.staked_last_24h + stake,
        staked_last_7d=exposure.staked_last_7d + stake,
        ticket_count_last_24h=exposure.ticket_count_last_24h + 1,
        ticket_count_last_7d=exposure.ticket_count_last_7d + 1,
        by_match=by_match,
        by_team=by_team,
        league_exposures=tuple(league_exposures),
    )


async def _load_policy_context(
    db: AsyncSession,
    *,
    bankroll_id: int,
    user_id: int,
    now: datetime,
    lock_bankroll: bool,
) -> tuple[Bankroll, object | None, object | None, RiskContext]:
    bankroll = await db.get(Bankroll, bankroll_id, with_for_update=lock_bankroll)
    if bankroll is None:
        raise ValueError(f"Bankroll {bankroll_id} not found")
    if bankroll.user_id != user_id:
        raise PermissionError(f"Bankroll {bankroll_id} does not belong to the current user")
    policy_row = await load_active_policy(db, bankroll_id, now=now, promote_pending=False)
    state = await load_risk_state(db, bankroll_id)
    policy = (
        orm_policy_to_domain(policy_row, paused_until=getattr(state, "paused_until", None))
        if policy_row is not None
        else None
    )
    exposure = await _load_portfolio_exposure(db, bankroll_id=bankroll_id, now=now)
    bankroll_amount = Decimal(str(bankroll.balance))
    return (
        bankroll,
        policy_row,
        policy,
        RiskContext(
            bankroll_amount=bankroll_amount,
            available_balance=bankroll_amount,
            exposure=exposure,
            now=now,
        ),
    )


def _count_predictions_by_run(predictions: list[ModelPrediction]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for prediction in predictions:
        counts[int(prediction.run_id)] += 1
    return counts


async def preflight_ticket_generation(
    db: AsyncSession,
    *,
    user_id: int,
    bankroll_id: int | None = None,
    run_id: int | None,
    run_ids: list[int] | None,
    prediction_ids: list[int] | None,
    market_types: list[str],
    min_odds: float,
    max_odds: float,
    ticket_format: str = "single",
    accumulator_risk_acknowledged: bool = False,
    automated: bool = False,
) -> dict:
    """Return all risk-tier availability without creating a batch or ticket."""

    if run_id is not None and run_ids is not None:
        raise ValueError("Provide either run_id or run_ids, not both")
    if run_id is None and not run_ids:
        raise ValueError("Provide run_id or run_ids for explicit prediction lineage")
    if prediction_ids is not None and not prediction_ids:
        raise ValueError("prediction_ids must contain at least one prediction ID")
    if not isfinite(float(min_odds)) or not isfinite(float(max_odds)):
        raise ValueError("min_odds and max_odds must be finite numbers")
    if min_odds <= 1 or max_odds <= 1:
        raise ValueError("min_odds and max_odds must be greater than 1")
    if min_odds > max_odds:
        raise ValueError("min_odds must be lower than or equal to max_odds")

    normalized_markets = {str(market).strip().lower() for market in market_types}
    if not normalized_markets:
        raise ValueError("market_types must contain at least one market")
    unsupported_markets = sorted(normalized_markets - SUPPORTED_TICKET_MARKETS)
    if unsupported_markets:
        raise ValueError("Unsupported ticket markets: " + ", ".join(unsupported_markets))

    requested_run_ids = list(dict.fromkeys(run_ids or [])) if run_ids is not None else None
    if requested_run_ids is not None:
        run_result = await db.execute(
            select(PredictionRun).where(
                PredictionRun.user_id == user_id,
                PredictionRun.id.in_(requested_run_ids),
                PredictionRun.status == "completed",
            )
        )
        runs_by_id = {run.id: run for run in run_result.scalars().all()}
        missing_run_ids = [run_id_value for run_id_value in requested_run_ids if run_id_value not in runs_by_id]
        if missing_run_ids:
            raise ValueError(
                "Prediction runs not found or not eligible for ticket generation: "
                + ", ".join(str(value) for value in missing_run_ids)
            )
        selected_runs = [runs_by_id[selected_id] for selected_id in requested_run_ids]
    else:
        run_stmt = select(PredictionRun).where(
            PredictionRun.user_id == user_id,
            PredictionRun.id == run_id,
            PredictionRun.status == "completed",
        )
        run_result = await db.execute(run_stmt.limit(1))
        selected_run = run_result.scalar_one_or_none()
        if selected_run is None:
            raise ValueError(f"Prediction run {run_id} not found or not eligible for ticket generation")
        selected_runs = [selected_run]

    selected_run_ids = [run.id for run in selected_runs]
    source_dataset_ids = {run.source_dataset_id for run in selected_runs}
    if len(selected_runs) > 1 and (len(source_dataset_ids) != 1 or None in source_dataset_ids):
        raise ValueError("Prediction runs must belong to the same source dataset")
    source_dataset_id = selected_runs[0].source_dataset_id
    governance_assessment = await assess_prediction_runs_governance(
        db,
        user_id=user_id,
        runs=selected_runs,
        automated=automated,
    )
    requested_prediction_ids = list(dict.fromkeys(prediction_ids or [])) if prediction_ids is not None else None
    prediction_stmt = (
        select(ModelPrediction)
        .options(selectinload(ModelPrediction.match))
        .order_by(
            ModelPrediction.expected_value.desc().nulls_last(),
            ModelPrediction.created_at.desc(),
            ModelPrediction.id.asc(),
        )
    )
    prediction_stmt = prediction_stmt.where(
        ModelPrediction.run_id == selected_run_ids[0]
        if len(selected_run_ids) == 1
        else ModelPrediction.run_id.in_(selected_run_ids)
    )
    if requested_prediction_ids is not None:
        prediction_stmt = prediction_stmt.where(ModelPrediction.id.in_(requested_prediction_ids))
    prediction_result = await db.execute(prediction_stmt)
    predictions = list(prediction_result.scalars().all())
    if requested_prediction_ids is not None:
        found_prediction_ids = {prediction.id for prediction in predictions}
        missing_prediction_ids = [
            prediction_id for prediction_id in requested_prediction_ids if prediction_id not in found_prediction_ids
        ]
        if missing_prediction_ids:
            raise ValueError(
                "Requested predictions are missing or do not belong to the selected prediction runs: "
                + ", ".join(str(value) for value in missing_prediction_ids)
            )

    preflight_time = _utc()
    odds_entries_by_match = None
    if bankroll_id is not None:
        odds_entries_by_match = await _load_odds_entries_by_match(
            db,
            list(dict.fromkeys(int(prediction.match_id) for prediction in predictions)),
        )
    candidates, report = _evaluate_ticket_candidates(
        predictions,
        normalized_markets=normalized_markets,
        min_odds=min_odds,
        max_odds=max_odds,
        now=preflight_time,
        odds_entries_by_match=odds_entries_by_match,
    )
    risk_specs = (
        ("safe", "safe", ["safe", "low"], 1),
        ("low", "safe", ["safe", "low"], 1),
        ("balanced", "balanced", ["balanced", "medium"], 2),
        ("medium", "balanced", ["balanced", "medium"], 2),
        ("aggressive", "aggressive", ["aggressive", "high"], 3),
        ("high", "aggressive", ["aggressive", "high"], 3),
    )
    risks = []
    for difficulty, tier, aliases, required_legs in risk_specs:
        eligible_unique_matches = int(report["eligible_unique_matches"])
        blockers = dict(report["excluded_by_reason"])
        if eligible_unique_matches < required_legs:
            blockers["insufficient_unique_matches"] = required_legs - eligible_unique_matches
        if not report["eligible_candidates"]:
            blockers["no_eligible_candidates"] = 1
        risks.append(
            {
                "difficulty": difficulty,
                "tier": tier,
                "aliases": aliases,
                "required_legs": required_legs,
                "eligible_candidates": report["eligible_candidates"],
                "eligible_unique_matches": eligible_unique_matches,
                "can_generate": bool(report["eligible_candidates"] and eligible_unique_matches >= required_legs),
                "excluded_by_reason": blockers,
            }
        )

    response = {
        "source_prediction_run_id": selected_run_ids[0] if selected_run_ids else None,
        "source_prediction_run_ids": selected_run_ids,
        "source_dataset_id": source_dataset_id,
        "scanned_predictions": report["scanned_predictions"],
        "eligible_candidates": report["eligible_candidates"],
        "eligible_unique_matches": report["eligible_unique_matches"],
        "eligible_prediction_ids": report["eligible_prediction_ids"],
        "excluded_predictions": report["excluded_predictions"],
        "excluded_by_reason": report["excluded_by_reason"],
        "governance_assessment": governance_assessment,
        "risks": risks,
    }
    if not governance_assessment["allowed"]:
        blocker = _governance_blocker_payload(governance_assessment)
        for risk in risks:
            risk["can_generate"] = False
            risk["excluded_by_reason"][blocker["code"]] = 1
        response["risk_assessment"] = {
            "policy_version": None,
            "allowed": False,
            "blockers": [blocker],
            "warnings": [],
        }
        return response
    if bankroll_id is not None:
        normalized_format = ticket_format.strip().lower()
        if normalized_format not in TICKET_FORMAT_LEGS:
            raise ValueError("ticket_format must be one of: single, double, treble")
        bankroll, policy_row, policy, risk_context = await _load_policy_context(
            db,
            bankroll_id=bankroll_id,
            user_id=user_id,
            now=preflight_time,
            lock_bankroll=False,
        )
        del bankroll, policy_row
        if policy is None:
            response["risk_assessment"] = {
                "policy_version": None,
                "allowed": False,
                "blockers": [{"code": "risk_policy_required", "scope": "policy"}],
                "warnings": [],
            }
            return response
        required_legs = TICKET_FORMAT_LEGS[normalized_format]
        selected: list[dict] = []
        used_teams: set[int | str] = set()
        for candidate in candidates:
            teams = set(candidate.get("team_ids") or ())
            if used_teams & teams:
                continue
            selected.append(candidate)
            used_teams.update(teams)
            if len(selected) == required_legs:
                break
        if len(selected) != required_legs:
            response["risk_assessment"] = {
                "policy_version": policy.version,
                "allowed": False,
                "blockers": [{"code": "insufficient_unique_candidates", "scope": "ticket"}],
                "warnings": [],
            }
            return response
        combined_odds = 1.0
        combined_probability = 1.0
        for candidate in selected:
            combined_odds *= float(candidate["odds"])
            combined_probability *= float(candidate["probability"])
        calculation = calculate_stake(
            policy=policy.staking,
            bankroll_amount=risk_context.bankroll_amount,
            ticket_format=normalized_format,
            ticket_limit_percent=policy.max_ticket_percent,
            model_probability=combined_probability if normalized_format == "single" else None,
            decimal_odds=combined_odds if normalized_format == "single" else None,
        )
        response["staking_snapshot"] = _staking_payload(calculation)
        if not calculation.eligible:
            response["risk_assessment"] = {
                "policy_version": policy.version,
                "allowed": False,
                "blockers": [{"code": calculation.reason_code, "scope": "staking"}],
                "warnings": [],
            }
            return response
        assessment = assess_portfolio_risk(
            policy=policy,
            context=risk_context,
            candidate=RiskCandidate(
                stake=calculation.stake,
                ticket_format=normalized_format,
                match_ids=frozenset(int(candidate["match_id"]) for candidate in selected),
                team_ids=frozenset(team for candidate in selected for team in candidate.get("team_ids", ())),
                league_ids=frozenset(league for candidate in selected for league in candidate.get("league_ids", ())),
                league_kickoffs=_candidate_league_kickoffs(selected),
                accumulator_risk_acknowledged=accumulator_risk_acknowledged,
                is_automated=automated,
            ),
        )
        response["risk_assessment"] = _risk_assessment_payload(assessment)
    return response


def _recalculate_ticket_totals(ticket: Ticket) -> float:
    combined_odds = 1.0
    for leg in getattr(ticket, "legs", []) or []:
        combined_odds *= float(getattr(leg, "odds", 1.0) or 1.0)
    ticket.total_odds = round(combined_odds, 6)
    ticket.potential_return = round(float(ticket.stake or 0.0) * ticket.total_odds, 2)
    return ticket.total_odds


async def create_ticket(
    db: AsyncSession,
    user_id: int,
    ticket_type: str,
    stake: float,
    bankroll_id: int | None = None,
    legs_data: list[dict] | None = None,
    batch_id: int | None = None,
    status: str = "open",
    debit_bankroll: bool = True,
    validate_references: bool = False,
) -> Ticket:
    if legs_data is None:
        legs_data = []

    try:
        stake = float(stake)
    except (TypeError, ValueError) as exc:
        raise ValueError("stake must be a finite positive number") from exc
    if not isfinite(stake) or stake <= 0:
        raise ValueError("stake must be a finite positive number")
    money_stake = quantize_money(stake)
    if not legs_data:
        raise ValueError("Ticket must contain at least one leg")

    normalized_legs: list[dict] = []
    for index, leg_data in enumerate(legs_data, start=1):
        if not isinstance(leg_data, dict):
            raise ValueError(f"Ticket leg {index} must be an object")
        try:
            odds = float(leg_data.get("odds"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Ticket leg {index} odds must be a finite number greater than 1") from exc
        if not isfinite(odds) or odds <= 1:
            raise ValueError(f"Ticket leg {index} odds must be a finite number greater than 1")

        match_id = leg_data.get("match_id")
        if not isinstance(match_id, int) or isinstance(match_id, bool) or match_id <= 0:
            raise ValueError(f"Ticket leg {index} must reference a valid match")
        market = str(leg_data.get("market") or "").strip()
        selection = str(leg_data.get("selection") or "").strip()
        if not market:
            raise ValueError(f"Ticket leg {index} market is required")
        if not selection:
            raise ValueError(f"Ticket leg {index} selection is required")

        prediction_id = leg_data.get("model_prediction_id")
        if prediction_id is not None and (
            not isinstance(prediction_id, int) or isinstance(prediction_id, bool) or prediction_id <= 0
        ):
            raise ValueError(f"Ticket leg {index} model prediction reference is invalid")

        normalized_legs.append(
            {
                **leg_data,
                "match_id": match_id,
                "model_prediction_id": prediction_id,
                "market": market,
                "selection": selection,
                "odds": odds,
            }
        )
    legs_data = normalized_legs

    if validate_references:
        # Manual/API creation never accepts caller-owned audit evidence.
        for leg in legs_data:
            for field_name in TICKET_LEG_SNAPSHOT_FIELDS:
                leg.pop(field_name, None)

        match_ids = list(dict.fromkeys(int(leg["match_id"]) for leg in legs_data))
        match_result = await db.execute(select(Match.id).where(Match.id.in_(match_ids)))
        existing_match_ids = set(match_result.scalars().all())
        missing_match_ids = [match_id for match_id in match_ids if match_id not in existing_match_ids]
        if missing_match_ids:
            raise ValueError("Matches not found: " + ", ".join(str(match_id) for match_id in missing_match_ids))

        prediction_to_match = {
            int(leg["model_prediction_id"]): int(leg["match_id"])
            for leg in legs_data
            if leg.get("model_prediction_id") is not None
        }
        if prediction_to_match:
            prediction_result = await db.execute(
                select(
                    ModelPrediction.id,
                    ModelPrediction.run_id,
                    ModelPrediction.match_id,
                    ModelPrediction.market,
                    ModelPrediction.home_prob,
                    ModelPrediction.draw_prob,
                    ModelPrediction.away_prob,
                    ModelPrediction.expected_value,
                    ModelPrediction.quality_report,
                    PredictionRun.user_id,
                )
                .join(PredictionRun, PredictionRun.id == ModelPrediction.run_id)
                .where(ModelPrediction.id.in_(prediction_to_match))
            )
            predictions = {row.id: row for row in prediction_result.all()}
            missing_prediction_ids = [
                prediction_id for prediction_id in prediction_to_match if prediction_id not in predictions
            ]
            if missing_prediction_ids:
                raise ValueError(
                    "Model predictions not found: "
                    + ", ".join(str(prediction_id) for prediction_id in missing_prediction_ids)
                )
            foreign_prediction_ids = [
                prediction_id for prediction_id, prediction in predictions.items() if prediction.user_id != user_id
            ]
            if foreign_prediction_ids:
                raise PermissionError("Model predictions do not belong to the current user")
            inconsistent_prediction_ids = [
                prediction_id
                for prediction_id, prediction in predictions.items()
                if prediction.match_id != prediction_to_match[prediction_id]
            ]
            if inconsistent_prediction_ids:
                raise ValueError("Model prediction and match lineage are inconsistent")

            # Discard any client-supplied snapshot-like dictionary keys and
            # rebuild evidence exclusively from the owned prediction row.
            for leg in legs_data:
                prediction_id = leg.get("model_prediction_id")
                if prediction_id is None:
                    continue
                snapshot_fields = _prediction_snapshot_fields(
                    predictions[prediction_id],
                    selection=leg["selection"].lower(),
                    selected_odds=leg["odds"],
                )
                leg.update(snapshot_fields)

    bankroll = None
    if bankroll_id:
        bankroll = await db.get(Bankroll, bankroll_id, with_for_update=debit_bankroll)
        if bankroll is None:
            raise ValueError(f"Bankroll {bankroll_id} not found")
        if bankroll.user_id != user_id:
            raise PermissionError(f"Bankroll {bankroll_id} does not belong to the current user")
        if debit_bankroll and quantize_money(bankroll.balance) < money_stake:
            raise ValueError("Insufficient bankroll balance")

    combined_odds = 1.0
    for leg in legs_data:
        combined_odds *= leg.get("odds", 1.0)

    potential_return = quantize_money(money_stake * Decimal(str(combined_odds)))

    ticket = Ticket(
        user_id=user_id,
        bankroll_id=bankroll_id,
        batch_id=batch_id,
        ticket_type=ticket_type,
        stake=money_stake,
        total_odds=combined_odds,
        potential_return=potential_return,
        status=status,
    )
    db.add(ticket)
    await db.flush()

    created_legs: list[tuple[TicketLeg, dict]] = []
    for leg_data in legs_data:
        leg = TicketLeg(
            ticket_id=ticket.id,
            model_prediction_id=leg_data.get("model_prediction_id"),
            match_id=leg_data.get("match_id"),
            selection=leg_data.get("selection", ""),
            market=leg_data.get("market", ""),
            odds=leg_data.get("odds", 1.0),
            bookmaker=leg_data.get("bookmaker"),
            prediction_run_id_snapshot=leg_data.get("prediction_run_id_snapshot"),
            model_probability_snapshot=leg_data.get("model_probability_snapshot"),
            market_probability_snapshot=leg_data.get("market_probability_snapshot"),
            market_probability_basis_snapshot=leg_data.get("market_probability_basis_snapshot"),
            expected_value_snapshot=leg_data.get("expected_value_snapshot"),
            edge_pct_snapshot=leg_data.get("edge_pct_snapshot"),
            reliability_label_snapshot=leg_data.get("reliability_label_snapshot"),
            reliability_score_snapshot=leg_data.get("reliability_score_snapshot"),
            status="pending",
        )
        db.add(leg)
        created_legs.append((leg, leg_data))

    await db.flush()
    for leg, leg_data in created_legs:
        quote_price = leg_data.get("odds")
        quote_observed_at = leg_data.get("quote_observed_at")
        if leg_data.get("quote_contract_version") != 1 and quote_observed_at is None:
            continue
        probability = leg_data.get("model_probability_snapshot")
        market_probability = leg_data.get("market_probability_snapshot")
        expected_value = leg_data.get("expected_value_snapshot")
        db.add(
            TicketLegQuoteSnapshot(
                ticket_leg_id=leg.id,
                stage="generation",
                revision=1,
                odds_entry_id=leg_data.get("quote_entry_id"),
                odds_snapshot_id=leg_data.get("quote_snapshot_id"),
                market=leg.market,
                selection=leg.selection,
                bookmaker=leg.bookmaker,
                price=quote_price,
                observed_at=quote_observed_at,
                model_probability=probability,
                market_probability=market_probability,
                market_probability_method=leg_data.get("market_probability_basis_snapshot"),
                fair_odds=(1.0 / probability) if probability else None,
                probability_edge_pp=(
                    (probability - market_probability) * 100.0
                    if probability is not None and market_probability is not None
                    else None
                ),
                expected_value=expected_value,
                expected_value_pct=expected_value * 100.0 if expected_value is not None else None,
            )
        )

    if debit_bankroll and bankroll_id and bankroll is not None:
        bankroll.balance = quantize_money(bankroll.balance) - money_stake
        ledger = LedgerEntry(
            bankroll_id=bankroll_id,
            ticket_id=ticket.id,
            entry_type="stake",
            amount=-money_stake,
            balance_after=bankroll.balance,
        )
        db.add(ledger)

    await db.flush()
    return ticket


async def create_manual_ticket(
    db: AsyncSession,
    *,
    user_id: int,
    ticket_type: str,
    stake: float,
    bankroll_id: int | None,
    legs_data: list[dict],
    accumulator_risk_acknowledged: bool = False,
) -> Ticket:
    """Validate and atomically open a manually entered paper ticket.

    The legacy ``POST /tickets`` surface used to call :func:`create_ticket`
    directly, so a caller-controlled stake could be debited without an active
    policy or portfolio assessment.  Keep the low-level constructor available
    for draft/import workflows, but route every manual activation through this
    fail-closed gate while holding the bankroll row lock.
    """

    if bankroll_id is None:
        report = {
            "risk_assessment": {
                "policy_version": None,
                "allowed": False,
                "blockers": [{"code": "risk_policy_required", "scope": "policy"}],
                "warnings": [],
            }
        }
        raise TicketRiskPolicyRequiredError(
            "A bankroll with an explicit risk policy is required for manual tickets",
            report,
        )

    leg_count = len(legs_data)
    ticket_format = {1: "single", 2: "double", 3: "treble"}.get(leg_count)
    if ticket_format is None:
        raise ValueError("Manual tickets must contain between one and three legs")

    normalized_requested_type = str(ticket_type or "").strip().lower()
    if normalized_requested_type in TICKET_FORMAT_LEGS and normalized_requested_type != ticket_format:
        raise ValueError("ticket_type must match the number of ticket legs")

    try:
        money_stake = quantize_money(stake)
    except (TypeError, ValueError) as exc:
        raise ValueError("stake must be a finite positive number") from exc
    if not isfinite(float(stake)) or money_stake <= 0:
        raise ValueError("stake must be a finite positive number")

    match_ids: list[int] = []
    for index, leg in enumerate(legs_data, start=1):
        match_id = leg.get("match_id") if isinstance(leg, dict) else None
        if not isinstance(match_id, int) or isinstance(match_id, bool) or match_id <= 0:
            raise ValueError(f"Ticket leg {index} must reference a valid match")
        match_ids.append(match_id)
    match_ids = list(dict.fromkeys(match_ids))

    now = _utc()
    _bankroll, policy_row, policy, context = await _load_policy_context(
        db,
        bankroll_id=bankroll_id,
        user_id=user_id,
        now=now,
        lock_bankroll=True,
    )
    match_result = await db.execute(select(Match).where(Match.id.in_(match_ids)))
    matches = list(match_result.scalars().all())
    matches_by_id = {int(match.id): match for match in matches}
    missing_match_ids = [match_id for match_id in match_ids if match_id not in matches_by_id]
    if missing_match_ids:
        raise ValueError("Matches not found: " + ", ".join(str(match_id) for match_id in missing_match_ids))

    governance_assessment = None
    prediction_ids = list(
        dict.fromkeys(
            int(leg["model_prediction_id"])
            for leg in legs_data
            if isinstance(leg, dict) and leg.get("model_prediction_id") is not None
        )
    )
    if prediction_ids:
        run_result = await db.execute(
            select(PredictionRun)
            .join(ModelPrediction, ModelPrediction.run_id == PredictionRun.id)
            .where(
                ModelPrediction.id.in_(prediction_ids),
                PredictionRun.user_id == user_id,
            )
        )
        runs = list(run_result.scalars().unique().all())
        governance_assessment = await assess_prediction_runs_governance(
            db,
            user_id=user_id,
            runs=runs,
            automated=False,
        )
        if not governance_assessment["allowed"]:
            blocker = _governance_blocker_payload(governance_assessment)
            raise TicketManualRiskConflictError(
                "Manual ticket is blocked by model governance",
                {
                    "governance_assessment": governance_assessment,
                    "risk_assessment": {
                        "policy_version": str(getattr(policy_row, "version", "")) or None,
                        "allowed": False,
                        "blockers": [blocker],
                        "warnings": [],
                    },
                },
            )

    assessment = assess_portfolio_risk(
        policy=policy,
        context=context,
        candidate=RiskCandidate(
            stake=money_stake,
            ticket_format=ticket_format,
            match_ids=frozenset(match_ids),
            team_ids=frozenset(
                team
                for match in matches
                for team in (getattr(match, "home_team", None), getattr(match, "away_team", None))
                if team
            ),
            league_ids=frozenset(
                competition for match in matches if (competition := getattr(match, "competition", None))
            ),
            league_kickoffs=_match_league_kickoffs(matches),
            accumulator_risk_acknowledged=accumulator_risk_acknowledged,
            is_automated=False,
        ),
    )
    risk_payload = _risk_assessment_payload(assessment)
    if governance_assessment is not None:
        risk_payload["governance_assessment"] = governance_assessment
    report = {"risk_assessment": risk_payload}
    if not assessment.allowed:
        if "risk_policy_required" in assessment.blocker_codes:
            raise TicketRiskPolicyRequiredError("An explicit risk policy is required", report)
        raise TicketManualRiskConflictError("Manual ticket is blocked by the risk policy", report)

    try:
        calculation = calculate_stake(
            policy=policy.staking,
            bankroll_amount=context.bankroll_amount,
            ticket_format=ticket_format,
            ticket_limit_percent=policy.max_ticket_percent,
        )
    except StakingError as exc:
        risk_payload["allowed"] = False
        risk_payload["blockers"].append({"code": exc.code, "message": str(exc), "scope": "staking"})
        raise TicketManualRiskConflictError(
            "Manual ticket stake cannot be verified by the active staking policy",
            report,
        ) from exc
    if not calculation.eligible:
        risk_payload["allowed"] = False
        risk_payload["blockers"].append(
            {
                "code": calculation.reason_code or "staking_ineligible",
                "message": "The active staking policy did not produce an eligible stake",
                "scope": "staking",
            }
        )
        raise TicketManualRiskConflictError(
            "Manual ticket stake is ineligible under the active staking policy",
            report,
        )
    if calculation.stake != money_stake:
        risk_payload["allowed"] = False
        risk_payload["blockers"].append(
            {
                "code": "manual_stake_policy_mismatch",
                "message": "The submitted stake does not match the server-calculated policy stake",
                "scope": "staking",
                "proposed": str(money_stake),
                "limit": str(calculation.stake),
            }
        )
        raise TicketManualRiskConflictError(
            "Manual ticket stake does not match the active staking policy",
            report,
        )

    ticket = await create_ticket(
        db=db,
        user_id=user_id,
        ticket_type=ticket_format,
        stake=float(money_stake),
        bankroll_id=bankroll_id,
        legs_data=legs_data,
        status="open",
        debit_bankroll=True,
        validate_references=True,
    )
    ticket.risk_policy_id = getattr(policy_row, "id", None)
    ticket.risk_policy_version = getattr(policy_row, "version", None)
    ticket.risk_assessment = risk_payload
    ticket.staking_snapshot = _staking_payload(calculation)
    await db.flush()
    return ticket


async def generate_tickets(
    db: AsyncSession,
    *,
    user_id: int,
    bankroll_id: int | None,
    ticket_count: int = 1,
    difficulty: str | None = None,
    ticket_format: str | None = None,
    accumulator_risk_acknowledged: bool = False,
    automated: bool = False,
    market_types: list[str],
    min_odds: float,
    max_odds: float,
    stake: float | None = None,
    run_id: int | None = None,
    run_ids: list[int] | None = None,
    prediction_ids: list[int] | None = None,
    scheduled_job_run_id: int | None = None,
) -> tuple[TicketBatch, list[Ticket]]:
    if ticket_count < 1:
        raise ValueError("ticket_count must be at least 1")
    if ticket_count > 50:
        raise ValueError("ticket_count must not exceed 50")
    legacy_generation = bankroll_id is None
    if legacy_generation:
        if stake is None or stake <= 0:
            raise ValueError("stake must be greater than 0")
        if not isfinite(float(stake)):
            raise ValueError("stake must be a finite number")
    if not isfinite(float(min_odds)) or not isfinite(float(max_odds)):
        raise ValueError("min_odds and max_odds must be finite numbers")
    if min_odds <= 1 or max_odds <= 1:
        raise ValueError("min_odds and max_odds must be greater than 1")
    if min_odds > max_odds:
        raise ValueError("min_odds must be lower than or equal to max_odds")
    if run_id is not None and run_ids is not None:
        raise ValueError("Provide either run_id or run_ids, not both")
    if run_ids is not None and not run_ids:
        raise ValueError("run_ids must contain at least one prediction run ID")
    if prediction_ids is not None and not prediction_ids:
        raise ValueError("prediction_ids must contain at least one prediction ID")

    if scheduled_job_run_id is not None:
        existing_result = await db.execute(
            select(TicketBatch)
            .options(selectinload(TicketBatch.tickets))
            .where(TicketBatch.scheduled_job_run_id == scheduled_job_run_id)
        )
        existing_batch = existing_result.scalar_one_or_none()
        if existing_batch is not None:
            return existing_batch, list(existing_batch.tickets)

    normalized_format = (ticket_format or _format_from_difficulty(difficulty)).strip().lower()
    if normalized_format not in TICKET_FORMAT_LEGS:
        raise ValueError("ticket_format must be one of: single, double, treble")
    if difficulty is not None and _format_from_difficulty(difficulty) != normalized_format:
        raise ValueError("difficulty and ticket_format describe different ticket formats")
    legs_per_ticket = TICKET_FORMAT_LEGS[normalized_format]
    difficulty = difficulty or {"single": "safe", "double": "balanced", "treble": "aggressive"}[normalized_format]
    normalized_markets = {str(market).strip().lower() for market in market_types}
    if not normalized_markets:
        raise ValueError("market_types must contain at least one market")
    unsupported_markets = sorted(normalized_markets - SUPPORTED_TICKET_MARKETS)
    if unsupported_markets:
        raise ValueError("Unsupported ticket markets: " + ", ".join(unsupported_markets))

    selected_runs: list[PredictionRun]
    requested_run_ids = list(dict.fromkeys(run_ids or [])) if run_ids is not None else None
    if requested_run_ids is not None:
        run_stmt = select(PredictionRun).where(
            PredictionRun.user_id == user_id,
            PredictionRun.id.in_(requested_run_ids),
            PredictionRun.status == "completed",
        )
        run_result = await db.execute(run_stmt)
        runs_by_id = {run.id: run for run in run_result.scalars().all()}
        missing_run_ids = [requested_id for requested_id in requested_run_ids if requested_id not in runs_by_id]
        if missing_run_ids:
            raise ValueError(
                "Prediction runs not found or not eligible for ticket generation: "
                + ", ".join(str(value) for value in missing_run_ids)
            )
        selected_runs = [runs_by_id[selected_id] for selected_id in requested_run_ids]
    elif run_id is not None:
        run_stmt = select(PredictionRun).where(PredictionRun.user_id == user_id)
        run_stmt = run_stmt.where(
            PredictionRun.id == run_id,
            PredictionRun.status == "completed",
        )
        run_result = await db.execute(run_stmt.limit(1))
        selected_run = run_result.scalar_one_or_none()
        if selected_run is None:
            raise ValueError(f"Prediction run {run_id} not found or not eligible for ticket generation")
        selected_runs = [selected_run]
    else:
        run_stmt = select(PredictionRun).where(PredictionRun.user_id == user_id)
        run_stmt = run_stmt.where(PredictionRun.status == "completed")
        run_stmt = run_stmt.order_by(
            PredictionRun.completed_at.desc().nulls_last(),
            PredictionRun.started_at.desc().nulls_last(),
            PredictionRun.created_at.desc(),
            PredictionRun.id.desc(),
        )
        run_result = await db.execute(run_stmt.limit(1))
        selected_run = run_result.scalar_one_or_none()
        if selected_run is None:
            raise ValueError("No completed prediction run available for ticket generation")
        selected_runs = [selected_run]

    selected_run_ids = [run.id for run in selected_runs]
    selected_run_id = selected_run_ids[0]
    source_dataset_ids = {run.source_dataset_id for run in selected_runs}
    if len(selected_runs) > 1 and (len(source_dataset_ids) != 1 or None in source_dataset_ids):
        raise ValueError("Prediction runs must belong to the same source dataset")
    source_dataset_id = selected_runs[0].source_dataset_id
    governance_assessment = await assess_prediction_runs_governance(
        db,
        user_id=user_id,
        runs=selected_runs,
        automated=automated,
    )

    if not governance_assessment["allowed"]:
        blocker = _governance_blocker_payload(governance_assessment)
        raise TicketGenerationError(
            "Ticket generation is blocked by model governance",
            {
                "report_version": 2,
                "prediction_run_id": selected_run_id,
                "prediction_run_ids": selected_run_ids,
                "source_dataset_id": source_dataset_id,
                "governance_assessment": governance_assessment,
                "scanned_predictions": 0,
                "eligible_candidates": 0,
                "excluded_predictions": 0,
                "excluded_by_reason": {blocker["code"]: 1},
                "risk_assessment": {
                    "policy_version": None,
                    "allowed": False,
                    "blockers": [blocker],
                    "warnings": [],
                },
            },
        )

    requested_prediction_ids = list(dict.fromkeys(prediction_ids or [])) if prediction_ids is not None else None
    stmt = (
        select(ModelPrediction)
        .options(selectinload(ModelPrediction.match))
        .order_by(
            ModelPrediction.expected_value.desc().nulls_last(),
            ModelPrediction.created_at.desc(),
            ModelPrediction.id.asc(),
        )
    )
    if len(selected_run_ids) == 1:
        stmt = stmt.where(ModelPrediction.run_id == selected_run_id)
    else:
        stmt = stmt.where(ModelPrediction.run_id.in_(selected_run_ids))
    if requested_prediction_ids is not None:
        stmt = stmt.where(ModelPrediction.id.in_(requested_prediction_ids))
    result = await db.execute(stmt)
    predictions = list(result.scalars().all())

    report = {
        "report_version": 2,
        "generation_status": "evaluated",
        "prediction_run_id": selected_run_id,
        "prediction_run_ids": selected_run_ids,
        "prediction_run_status": selected_runs[0].status,
        "prediction_run_statuses": {str(run.id): run.status for run in selected_runs},
        "source_dataset_id": source_dataset_id,
        "input_hash": selected_runs[0].input_hash,
        "input_hashes": {str(run.id): run.input_hash for run in selected_runs},
        "governance_assessment": governance_assessment,
        "request": {
            "bankroll_id": bankroll_id,
            "ticket_count": ticket_count,
            "difficulty": difficulty,
            "ticket_format": normalized_format,
            "accumulator_risk_acknowledged": accumulator_risk_acknowledged,
            "automated": automated,
            "market_types": sorted(normalized_markets),
            "min_odds": float(min_odds),
            "max_odds": float(max_odds),
            "requested_prediction_ids": requested_prediction_ids,
        },
        "scanned_predictions": len(predictions),
        "scanned_predictions_by_run": {},
        "eligible_candidates": 0,
        "eligible_candidates_by_run": {},
        "eligible_prediction_ids": [],
        "excluded_predictions": 0,
        "excluded_by_reason": {},
        "excluded_by_run": {},
    }
    scanned_by_run: dict[str, int] = defaultdict(int)
    for prediction in predictions:
        scanned_by_run[str(prediction.run_id)] += 1
    report["scanned_predictions_by_run"] = dict(sorted(scanned_by_run.items(), key=lambda item: int(item[0])))
    if requested_prediction_ids is not None:
        found_prediction_ids = {prediction.id for prediction in predictions}
        missing_prediction_ids = [
            prediction_id for prediction_id in requested_prediction_ids if prediction_id not in found_prediction_ids
        ]
        report.update(
            {
                "requested_prediction_ids": requested_prediction_ids,
                "requested_predictions": len(requested_prediction_ids),
                "missing_prediction_ids": missing_prediction_ids,
                "missing_predictions": len(missing_prediction_ids),
            }
        )
        if missing_prediction_ids:
            report["excluded_predictions"] = len(missing_prediction_ids)
            report["excluded_by_reason"] = {"requested_prediction_missing_or_wrong_run": len(missing_prediction_ids)}
            raise TicketGenerationError(
                "Requested predictions are missing or do not belong to the selected prediction runs",
                report,
            )
    if not predictions:
        run_label = ", ".join(str(value) for value in selected_run_ids)
        if len(selected_run_ids) == 1:
            message = f"Prediction run {selected_run_ids[0]} has no predictions"
        else:
            message = f"Prediction runs {run_label} have no predictions"
        raise TicketGenerationError(message, report)

    generation_time = _utc()
    odds_entries_by_match = None
    if not legacy_generation:
        odds_entries_by_match = await _load_odds_entries_by_match(
            db,
            list(dict.fromkeys(int(prediction.match_id) for prediction in predictions)),
        )
    candidates, candidate_report = _evaluate_ticket_candidates(
        predictions,
        normalized_markets=normalized_markets,
        min_odds=min_odds,
        max_odds=max_odds,
        now=generation_time,
        odds_entries_by_match=odds_entries_by_match,
    )
    report.update(candidate_report)
    if not candidates:
        raise TicketGenerationError("No safe prediction candidates are eligible for ticket generation", report)

    eligible_unique_matches = len({candidate["match_id"] for candidate in candidates})
    report["required_legs_per_ticket"] = legs_per_ticket
    report["eligible_unique_matches"] = eligible_unique_matches
    required_candidate_count = ticket_count * legs_per_ticket
    if eligible_unique_matches < required_candidate_count:
        raise TicketGenerationError(
            f"Difficulty '{difficulty}' requires {required_candidate_count} unique matches for this batch, "
            f"but only {eligible_unique_matches} are eligible",
            report,
        )

    bankroll = None
    policy_row = None
    policy = None
    risk_context = None
    if not legacy_generation:
        assert bankroll_id is not None
        bankroll, policy_row, policy, risk_context = await _load_policy_context(
            db,
            bankroll_id=bankroll_id,
            user_id=user_id,
            now=generation_time,
            lock_bankroll=False,
        )
        if policy is None:
            report["risk_assessment"] = {
                "policy_version": None,
                "allowed": False,
                "blockers": [{"code": "risk_policy_required", "scope": "policy"}],
                "warnings": [],
            }
            raise TicketRiskPolicyRequiredError("An explicit risk policy is required", report)

    planned: list[tuple[list[dict], Decimal, dict, dict]] = []
    used_prediction_ids: set[int] = set()
    used_match_ids: set[int] = set()
    projected_exposure = risk_context.exposure if risk_context is not None else None
    for ticket_index in range(ticket_count):
        legs: list[dict] = []
        ticket_teams: set[int | str] = set()
        for candidate in candidates:
            prediction_id = int(candidate["model_prediction_id"])
            match_id = int(candidate["match_id"])
            teams = set(candidate.get("team_ids") or ())
            if prediction_id in used_prediction_ids or match_id in used_match_ids:
                continue
            if ticket_teams & teams:
                continue
            legs.append(candidate)
            ticket_teams.update(teams)
            if len(legs) == legs_per_ticket:
                break
        if len(legs) != legs_per_ticket:
            raise TicketGenerationError(
                "Eligible candidates could not satisfy unique match/team requirements without reuse",
                report,
            )

        if legacy_generation:
            ticket_stake = quantize_money(stake or 0)
            staking_snapshot = {"mode": "legacy_client_stake", "stake": str(ticket_stake)}
            risk_payload = {"policy_version": None, "allowed": True, "blockers": [], "warnings": []}
        else:
            assert policy is not None and risk_context is not None and projected_exposure is not None
            combined_odds = 1.0
            combined_probability = 1.0
            for leg in legs:
                combined_odds *= float(leg["odds"])
                combined_probability *= float(leg["probability"])
            try:
                stake_calculation = calculate_stake(
                    policy=policy.staking,
                    bankroll_amount=risk_context.bankroll_amount,
                    ticket_format=normalized_format,
                    ticket_limit_percent=policy.max_ticket_percent,
                    model_probability=combined_probability if normalized_format == "single" else None,
                    decimal_odds=combined_odds if normalized_format == "single" else None,
                )
            except StakingError as exc:
                report["staking_error"] = {"code": exc.code, "message": str(exc)}
                raise TicketGenerationError(str(exc), report) from exc
            if not stake_calculation.eligible:
                report["staking_error"] = {
                    "code": stake_calculation.reason_code,
                    "message": "The configured staking policy produced no eligible stake",
                }
                raise TicketGenerationError("The configured staking policy produced no eligible stake", report)
            ticket_stake = stake_calculation.stake
            match_ids = {int(leg["match_id"]) for leg in legs}
            team_ids = {team for leg in legs for team in leg.get("team_ids", ())}
            league_ids = {league for leg in legs for league in leg.get("league_ids", ())}
            league_kickoffs = _candidate_league_kickoffs(legs)
            assessment = assess_portfolio_risk(
                policy=policy,
                context=RiskContext(
                    bankroll_amount=risk_context.bankroll_amount,
                    available_balance=risk_context.available_balance,
                    exposure=projected_exposure,
                    now=generation_time,
                ),
                candidate=RiskCandidate(
                    stake=ticket_stake,
                    ticket_format=normalized_format,
                    match_ids=frozenset(match_ids),
                    team_ids=frozenset(team_ids),
                    league_ids=frozenset(league_ids),
                    league_kickoffs=league_kickoffs,
                    accumulator_risk_acknowledged=accumulator_risk_acknowledged,
                    is_automated=automated,
                ),
            )
            risk_payload = _risk_assessment_payload(assessment)
            if not assessment.allowed:
                report["risk_assessment"] = risk_payload
                raise TicketGenerationError("Ticket generation is blocked by the risk policy", report)
            staking_snapshot = _staking_payload(stake_calculation)
            projected_exposure = _project_exposure(
                projected_exposure,
                stake=ticket_stake,
                match_ids=match_ids,
                team_ids=team_ids,
                league_kickoffs=league_kickoffs,
                exposure_id=f"planned:{ticket_index}",
            )

        for leg in legs:
            leg["quote_contract_version"] = 1 if not legacy_generation else 0
            used_prediction_ids.add(int(leg["model_prediction_id"]))
            used_match_ids.add(int(leg["match_id"]))
        planned.append((legs, ticket_stake, staking_snapshot, risk_payload))

    batch_risk_payload = {
        "allowed": True,
        "policy_version": str(policy_row.version) if policy_row is not None else None,
        "tickets": [item[3] for item in planned],
    }
    batch_staking_payload = {"tickets": [item[2] for item in planned]}
    batch = TicketBatch(
        bankroll_id=bankroll_id,
        source_prediction_run_id=selected_run_id,
        scheduled_job_run_id=scheduled_job_run_id,
        name=f"Generated {normalized_format} tickets",
        strategy=normalized_format,
        tickets_count=0,
        total_stake=Decimal("0.00"),
        revision=1,
        risk_policy_id=getattr(policy_row, "id", None),
        risk_policy_version=getattr(policy_row, "version", None),
        risk_assessment=batch_risk_payload,
        staking_snapshot=batch_staking_payload,
        model_evaluation_id=(
            governance_assessment["model_evaluation_ids"][0]
            if len(governance_assessment["model_evaluation_ids"]) == 1
            else None
        ),
        # Keep the initial persisted value separate from the mutable working report.
        # Otherwise in-place updates can leave SQLAlchemy's JSON value history clean.
        generation_report=dict(report),
    )
    db.add(batch)
    await db.flush()

    tickets: list[Ticket] = []
    generated_ticket_lineage: list[dict] = []
    for legs, ticket_stake, staking_snapshot, risk_payload in planned:
        ticket = await create_ticket(
            db=db,
            user_id=user_id,
            ticket_type=normalized_format,
            stake=float(ticket_stake),
            bankroll_id=bankroll_id,
            legs_data=legs,
            batch_id=batch.id,
            status="generated",
            debit_bankroll=False,
        )
        ticket.risk_policy_id = getattr(policy_row, "id", None)
        ticket.risk_policy_version = getattr(policy_row, "version", None)
        ticket.risk_assessment = risk_payload
        ticket.staking_snapshot = staking_snapshot
        tickets.append(ticket)
        generated_ticket_lineage.append(
            {
                "ticket_id": ticket.id,
                "prediction_ids": [int(leg["model_prediction_id"]) for leg in legs],
                "prediction_run_ids": list(
                    dict.fromkeys(int(leg["prediction_run_id"]) for leg in legs if leg["prediction_run_id"] is not None)
                ),
                "match_ids": [int(leg["match_id"]) for leg in legs],
            }
        )

    batch.tickets_count = len(tickets)
    batch.total_stake = sum((item[1] for item in planned), Decimal("0.00"))
    generated_prediction_ids = sorted(
        {
            prediction_id
            for ticket_lineage in generated_ticket_lineage
            for prediction_id in ticket_lineage["prediction_ids"]
        }
    )
    report.update(
        {
            "generation_status": "generated",
            "generated_ticket_count": len(tickets),
            "generated_leg_count": sum(len(item["prediction_ids"]) for item in generated_ticket_lineage),
            "generated_prediction_ids": generated_prediction_ids,
            "generated_prediction_run_ids": list(
                dict.fromkeys(
                    run_id_value for item in generated_ticket_lineage for run_id_value in item["prediction_run_ids"]
                )
            ),
            "generated_ticket_lineage": generated_ticket_lineage,
            "quote_contract_version": 1 if not legacy_generation else 0,
            "risk_policy_version": getattr(policy_row, "version", None),
            "ticket_format": normalized_format,
        }
    )
    batch.generation_report = dict(report)
    await db.flush()
    return batch, tickets


async def activate_ticket_batch(
    db: AsyncSession,
    *,
    user_id: int,
    batch_id: int,
    now: datetime | None = None,
    expected_revision: int | None = None,
    review_acknowledged: bool = True,
    accepted_warning_codes: list[str] | None = None,
) -> tuple[TicketBatch, list[Ticket], float]:
    """Atomically fund a generated batch and transition every draft to open.

    Row locks plus the generated-only transition make the operation repeat-safe:
    a concurrent or repeated request can never create a second stake debit.
    """

    batch_result = await db.execute(select(TicketBatch).where(TicketBatch.id == batch_id).with_for_update())
    batch = batch_result.scalar_one_or_none()
    if batch is None:
        raise LookupError("Ticket batch not found")
    batch_revision = int(getattr(batch, "revision", 1) or 1)
    if expected_revision is not None and expected_revision != batch_revision:
        raise TicketActivationConflictError("Ticket batch revision changed; refresh and review the batch again")
    if not review_acknowledged:
        raise TicketActivationConflictError("Ticket batch review must be acknowledged before activation")

    tickets_result = await db.execute(
        select(Ticket).where(Ticket.batch_id == batch_id).order_by(Ticket.id.asc()).with_for_update()
    )
    tickets = list(tickets_result.scalars().all())
    if not tickets or any(ticket.user_id != user_id for ticket in tickets):
        raise LookupError("Ticket batch not found")

    statuses = {ticket.status for ticket in tickets}
    if statuses != {"generated"}:
        raise TicketActivationConflictError(
            "Ticket batch can only be activated once while every ticket is in generated status"
        )
    if batch.bankroll_id is None:
        raise TicketActivationConflictError("Ticket batch has no bankroll selected")
    if any(ticket.bankroll_id != batch.bankroll_id for ticket in tickets):
        raise TicketActivationConflictError("Ticket batch bankroll lineage is inconsistent")
    if any(float(ticket.stake or 0.0) <= 0 for ticket in tickets):
        raise TicketActivationConflictError("Every generated ticket must have a positive stake")
    if int(batch.tickets_count or 0) != len(tickets):
        raise TicketActivationConflictError("Ticket batch ticket count is inconsistent")

    ticket_ids = [ticket.id for ticket in tickets]
    legs_result = await db.execute(
        select(TicketLeg)
        .where(TicketLeg.ticket_id.in_(ticket_ids))
        .order_by(TicketLeg.ticket_id.asc(), TicketLeg.id.asc())
        .with_for_update()
    )
    legs = list(legs_result.scalars().all())
    ticket_ids_with_legs = {leg.ticket_id for leg in legs}
    if any(ticket_id not in ticket_ids_with_legs for ticket_id in ticket_ids):
        raise TicketActivationConflictError("Every generated ticket must have at least one leg")
    if any(leg.match_id is None for leg in legs):
        raise TicketActivationConflictError("Every generated ticket leg must reference a match")
    if any(leg.model_prediction_id is None for leg in legs):
        raise TicketActivationConflictError("Every generated ticket leg must reference a model prediction")

    report = batch.generation_report if isinstance(batch.generation_report, dict) else {}
    raw_run_ids = report.get("prediction_run_ids")
    source_run_ids = (
        [int(value) for value in raw_run_ids if isinstance(value, int) and value > 0]
        if isinstance(raw_run_ids, list)
        else []
    )
    if not source_run_ids and batch.source_prediction_run_id is not None:
        source_run_ids = [int(batch.source_prediction_run_id)]
    source_run_ids = list(dict.fromkeys(source_run_ids))
    if not source_run_ids:
        raise TicketActivationConflictError("Ticket batch has no source prediction lineage")
    activation_time = _utc(now)
    governance_assessment = await _revalidate_batch_governance(
        db,
        batch=batch,
        user_id=user_id,
        automated=False,
        now=activation_time,
    )
    if governance_assessment is not None and not governance_assessment["allowed"]:
        raise TicketActivationConflictError("Model governance changed; refresh cannot authorize this batch")

    prediction_ids = list(
        dict.fromkeys(int(leg.model_prediction_id) for leg in legs if leg.model_prediction_id is not None)
    )
    predictions_result = await db.execute(
        select(
            ModelPrediction.id,
            ModelPrediction.run_id,
            ModelPrediction.match_id,
            ModelPrediction.quality_report,
            PredictionRun.user_id,
            PredictionRun.source_dataset_id,
        )
        .join(PredictionRun, PredictionRun.id == ModelPrediction.run_id)
        .where(ModelPrediction.id.in_(prediction_ids))
        .order_by(ModelPrediction.id.asc())
        .with_for_update()
    )
    predictions_by_id = {row.id: row for row in predictions_result.all()}
    fixtures_by_prediction_id: dict[int, dict | None] = {}
    expected_dataset_id = report.get("source_dataset_id")
    for leg in legs:
        prediction = predictions_by_id.get(leg.model_prediction_id)
        if prediction is None:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} references a missing model prediction")
        if prediction.user_id != user_id:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} prediction does not belong to the current user")
        if prediction.run_id not in source_run_ids:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} prediction is outside the batch source runs")
        if prediction.match_id != leg.match_id:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} prediction and match lineage are inconsistent")
        if expected_dataset_id is not None and prediction.source_dataset_id != expected_dataset_id:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} prediction dataset lineage is inconsistent")
        canonical_fixture, snapshot_error = _p4_canonical_fixture(prediction)
        if snapshot_error is not None:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} has invalid governed fixture evidence")
        fixtures_by_prediction_id[int(prediction.id)] = canonical_fixture

    match_ids = list(dict.fromkeys(int(leg.match_id) for leg in legs if leg.match_id is not None))
    matches_result = await db.execute(
        select(Match).where(Match.id.in_(match_ids)).order_by(Match.id.asc()).with_for_update()
    )
    matches_by_id = {match.id: match for match in matches_result.scalars().all()}
    for leg in legs:
        match = matches_by_id.get(leg.match_id)
        if match is None:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} references a missing match")
        canonical_fixture = fixtures_by_prediction_id[int(leg.model_prediction_id)]
        kickoff = canonical_fixture["kickoff"] if canonical_fixture is not None else match.match_date
        if kickoff is None:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} has no match kickoff")
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        else:
            kickoff = kickoff.astimezone(timezone.utc)
        if kickoff <= activation_time:
            raise TicketActivationConflictError(f"Ticket leg {leg.id} match has already started")
        match_status = str(match.status or "").strip().lower()
        if match_status not in NOT_STARTED_MATCH_STATUSES:
            raise TicketActivationConflictError(
                f"Ticket leg {leg.id} match status '{match.status}' is not eligible for activation"
            )

    uses_controlled_contract = bool(
        getattr(batch, "risk_policy_id", None) or int((report.get("quote_contract_version") or 0)) == 1
    )
    quote_updates: list[tuple[TicketLeg, object, float, float]] = []
    if uses_controlled_contract:
        odds_by_match = await _load_odds_entries_by_match(db, match_ids)
        for leg in legs:
            quote_set = select_quote_set(
                odds_by_match.get(int(leg.match_id), []),
                market=leg.market,
                as_of=activation_time,
                max_age=PREMATCH_MAX_AGE,
            )
            if not quote_set.is_ticket_eligible:
                reasons = ",".join(quote_set.reason_codes) or "quote_ineligible"
                raise TicketActivationConflictError(f"Quote revalidation required for leg {leg.id}: {reasons}")
            quote = quote_set.quote_for(leg.selection)
            market_probability = quote_set.consensus_probabilities.get(str(leg.selection).lower())
            if quote is None or market_probability is None:
                raise TicketActivationConflictError(f"Quote revalidation required for leg {leg.id}")
            if quote.price < float(leg.odds):
                raise TicketActivationConflictError(f"Quote worsened for leg {leg.id}; refresh and review the batch")
            model_probability = getattr(leg, "model_probability_snapshot", None)
            if model_probability is None or float(model_probability) * quote.price - 1.0 <= 0:
                raise TicketActivationConflictError(f"Expected value is no longer positive for leg {leg.id}")
            quote_updates.append((leg, quote, float(market_probability), float(model_probability)))

        bankroll, active_policy_row, active_policy, risk_context = await _load_policy_context(
            db,
            bankroll_id=batch.bankroll_id,
            user_id=user_id,
            now=activation_time,
            lock_bankroll=True,
        )
        if active_policy_row is None or active_policy is None:
            raise TicketActivationConflictError("Risk policy is no longer configured; refresh the batch")
        if active_policy_row.id != getattr(batch, "risk_policy_id", None) or active_policy_row.version != getattr(
            batch, "risk_policy_version", None
        ):
            raise TicketActivationConflictError("Risk policy changed; refresh and review the batch")
        accepted = set(accepted_warning_codes or [])
        projected_exposure = risk_context.exposure
        risk_payloads: list[dict] = []
        legs_by_ticket: dict[int, list[TicketLeg]] = defaultdict(list)
        for leg in legs:
            legs_by_ticket[leg.ticket_id].append(leg)
        for ticket in tickets:
            ticket_legs = legs_by_ticket[ticket.id]
            match_scope = {int(leg.match_id) for leg in ticket_legs if leg.match_id is not None}
            team_scope: set[int | str] = set()
            league_scope: set[int | str] = set()
            scoped_matches: list[Match] = []
            scoped_fixtures: list[dict | None] = []
            for leg in ticket_legs:
                match = matches_by_id[int(leg.match_id)]
                canonical_fixture = fixtures_by_prediction_id[int(leg.model_prediction_id)]
                if canonical_fixture is not None:
                    team_scope.update((canonical_fixture["home_team"], canonical_fixture["away_team"]))
                    league_scope.add(canonical_fixture["competition_key"])
                    scoped_matches.append(match)
                    scoped_fixtures.append(canonical_fixture)
                else:
                    scoped_matches.append(match)
                    scoped_fixtures.append(None)
                    team_scope.update(value for value in (match.home_team, match.away_team) if value)
                if canonical_fixture is None and match.competition:
                    league_scope.add(match.competition)
            assessment = assess_portfolio_risk(
                policy=active_policy,
                context=RiskContext(
                    bankroll_amount=risk_context.bankroll_amount,
                    available_balance=risk_context.available_balance,
                    exposure=projected_exposure,
                    now=activation_time,
                ),
                candidate=RiskCandidate(
                    stake=ticket.stake,
                    ticket_format=ticket.ticket_type,
                    match_ids=frozenset(match_scope),
                    team_ids=frozenset(team_scope),
                    league_ids=frozenset(league_scope),
                    league_kickoffs=_fixture_league_kickoffs(scoped_fixtures, scoped_matches),
                    accumulator_risk_acknowledged=bool(report.get("request", {}).get("accumulator_risk_acknowledged")),
                    is_automated=False,
                ),
            )
            if not assessment.allowed:
                raise TicketActivationConflictError("Current portfolio exposure blocks activation; refresh the batch")
            warning_codes = {warning.code for warning in assessment.warnings}
            if not warning_codes.issubset(accepted):
                raise TicketActivationConflictError("Risk warnings changed; review and accept the current warnings")
            risk_payloads.append(_risk_assessment_payload(assessment))
            projected_exposure = _project_exposure(
                projected_exposure,
                stake=quantize_money(ticket.stake),
                match_ids=match_scope,
                team_ids=team_scope,
                league_kickoffs=_fixture_league_kickoffs(scoped_fixtures, scoped_matches),
                exposure_id=ticket.id,
            )
    else:
        bankroll_result = await db.execute(select(Bankroll).where(Bankroll.id == batch.bankroll_id).with_for_update())
        bankroll = bankroll_result.scalar_one_or_none()
        if bankroll is None:
            raise ValueError(f"Bankroll {batch.bankroll_id} not found")
        if bankroll.user_id != user_id:
            raise PermissionError(f"Bankroll {batch.bankroll_id} does not belong to the current user")
        risk_payloads = []

    total_stake = sum((quantize_money(ticket.stake) for ticket in tickets), Decimal("0.00"))
    if quantize_money(batch.total_stake) != total_stake:
        raise TicketActivationConflictError("Ticket batch total stake is inconsistent")
    if quantize_money(bankroll.balance) < total_stake:
        raise ValueError("Insufficient bankroll balance")

    for leg, quote, market_probability, model_probability in quote_updates:
        expected_value = model_probability * quote.price - 1.0
        leg.odds = quote.price
        leg.bookmaker = quote.bookmaker
        leg.market_probability_snapshot = market_probability
        leg.expected_value_snapshot = expected_value
        leg.edge_pct_snapshot = (model_probability - market_probability) * 100.0
        db.add(
            TicketLegQuoteSnapshot(
                ticket_leg_id=leg.id,
                stage="activation",
                revision=batch_revision,
                odds_entry_id=quote.entry_id,
                odds_snapshot_id=quote.snapshot_id if isinstance(quote.snapshot_id, int) else None,
                market=leg.market,
                selection=leg.selection,
                bookmaker=quote.bookmaker,
                price=quote.price,
                observed_at=quote.observed_at,
                model_probability=model_probability,
                market_probability=market_probability,
                market_probability_method="consensus_de_vig",
                fair_odds=1.0 / model_probability,
                probability_edge_pp=(model_probability - market_probability) * 100.0,
                expected_value=expected_value,
                expected_value_pct=expected_value * 100.0,
            )
        )
    if quote_updates:
        legs_by_ticket_for_totals: dict[int, list[TicketLeg]] = defaultdict(list)
        for leg in legs:
            legs_by_ticket_for_totals[leg.ticket_id].append(leg)
        for ticket in tickets:
            combined = 1.0
            for leg in legs_by_ticket_for_totals[ticket.id]:
                combined *= float(leg.odds)
            ticket.total_odds = round(combined, 6)
            ticket.potential_return = quantize_money(Decimal(str(ticket.stake)) * Decimal(str(combined)))

    for index, ticket in enumerate(tickets):
        stake = quantize_money(ticket.stake)
        bankroll.balance = quantize_money(bankroll.balance) - stake
        ticket.status = "open"
        if index < len(risk_payloads):
            ticket.risk_assessment = risk_payloads[index]
        db.add(
            LedgerEntry(
                bankroll_id=bankroll.id,
                ticket_id=ticket.id,
                entry_type="stake",
                amount=-stake,
                balance_after=bankroll.balance,
            )
        )

    if uses_controlled_contract:
        batch.activation_report = {
            "revision": batch_revision,
            "activated_at": activation_time.isoformat(),
            "risk_assessments": risk_payloads,
            "quote_revalidated": True,
            "governance_assessment": governance_assessment,
        }

    await db.flush()
    return batch, tickets, total_stake


async def refresh_ticket_batch(
    db: AsyncSession,
    *,
    user_id: int,
    batch_id: int,
    expected_revision: int,
    now: datetime | None = None,
) -> tuple[TicketBatch, list[Ticket]]:
    """Reprice and re-risk a generated draft, then require a fresh review."""

    batch_result = await db.execute(select(TicketBatch).where(TicketBatch.id == batch_id).with_for_update())
    batch = batch_result.scalar_one_or_none()
    if batch is None:
        raise LookupError("Ticket batch not found")
    if int(batch.revision or 1) != expected_revision:
        raise TicketRefreshConflictError("Ticket batch revision changed")

    tickets_result = await db.execute(
        select(Ticket).where(Ticket.batch_id == batch_id).order_by(Ticket.id.asc()).with_for_update()
    )
    tickets = list(tickets_result.scalars().all())
    if not tickets or any(ticket.user_id != user_id for ticket in tickets):
        raise LookupError("Ticket batch not found")
    if any(ticket.status != "generated" for ticket in tickets):
        raise TicketRefreshConflictError("Only generated draft batches can be refreshed")
    if batch.bankroll_id is None:
        raise TicketRefreshConflictError("Ticket batch has no bankroll selected")

    ticket_ids = [ticket.id for ticket in tickets]
    legs_result = await db.execute(
        select(TicketLeg)
        .where(TicketLeg.ticket_id.in_(ticket_ids))
        .order_by(TicketLeg.ticket_id.asc(), TicketLeg.id.asc())
        .with_for_update()
    )
    legs = list(legs_result.scalars().all())
    if not legs or any(leg.match_id is None for leg in legs):
        raise TicketRefreshConflictError("Every generated ticket must have complete match lineage")

    prediction_ids = [int(leg.model_prediction_id) for leg in legs if leg.model_prediction_id is not None]
    predictions_result = await db.execute(
        select(ModelPrediction.id, ModelPrediction.match_id, ModelPrediction.quality_report).where(
            ModelPrediction.id.in_(prediction_ids)
        )
    )
    predictions_by_id = {row.id: row for row in predictions_result.all()}
    fixtures_by_prediction_id: dict[int, dict | None] = {}
    for leg in legs:
        prediction = predictions_by_id.get(leg.model_prediction_id)
        if prediction is None or prediction.match_id != leg.match_id:
            raise TicketRefreshConflictError(f"Ticket leg {leg.id} prediction lineage is inconsistent")
        canonical_fixture, snapshot_error = _p4_canonical_fixture(prediction)
        if snapshot_error is not None:
            raise TicketRefreshConflictError(f"Ticket leg {leg.id} has invalid governed fixture evidence")
        fixtures_by_prediction_id[int(prediction.id)] = canonical_fixture

    match_ids = list(dict.fromkeys(int(leg.match_id) for leg in legs))
    matches_result = await db.execute(select(Match).where(Match.id.in_(match_ids)).with_for_update())
    matches_by_id = {match.id: match for match in matches_result.scalars().all()}
    refresh_time = _utc(now)
    governance_assessment = await _revalidate_batch_governance(
        db,
        batch=batch,
        user_id=user_id,
        automated=False,
        now=refresh_time,
    )
    if governance_assessment is not None and not governance_assessment["allowed"]:
        raise TicketRefreshConflictError("Model governance no longer authorizes this batch")
    for leg in legs:
        match = matches_by_id.get(leg.match_id)
        canonical_fixture = fixtures_by_prediction_id[int(leg.model_prediction_id)]
        kickoff = canonical_fixture["kickoff"] if canonical_fixture is not None else getattr(match, "match_date", None)
        if match is None or kickoff is None or _utc(kickoff) <= refresh_time:
            raise TicketRefreshConflictError(f"Ticket leg {leg.id} match is no longer eligible")
        if str(match.status or "").strip().lower() not in NOT_STARTED_MATCH_STATUSES:
            raise TicketRefreshConflictError(f"Ticket leg {leg.id} match is no longer eligible")

    odds_by_match = await _load_odds_entries_by_match(db, match_ids)
    quote_plans: dict[int, tuple[object, float, float]] = {}
    for leg in legs:
        quote_set = select_quote_set(
            odds_by_match.get(int(leg.match_id), []),
            market=leg.market,
            as_of=refresh_time,
            max_age=PREMATCH_MAX_AGE,
        )
        quote = quote_set.quote_for(leg.selection)
        market_probability = quote_set.consensus_probabilities.get(str(leg.selection).lower())
        model_probability = getattr(leg, "model_probability_snapshot", None)
        if not quote_set.is_ticket_eligible or quote is None or market_probability is None:
            raise TicketRefreshConflictError(f"Fresh coherent quote unavailable for leg {leg.id}")
        if model_probability is None or float(model_probability) * quote.price - 1.0 <= 0:
            raise TicketRefreshConflictError(f"Expected value is no longer positive for leg {leg.id}")
        quote_plans[leg.id] = (quote, float(market_probability), float(model_probability))

    bankroll, policy_row, policy, risk_context = await _load_policy_context(
        db,
        bankroll_id=batch.bankroll_id,
        user_id=user_id,
        now=refresh_time,
        lock_bankroll=True,
    )
    del bankroll
    if policy_row is None or policy is None:
        raise TicketRefreshConflictError("An explicit risk policy is required")

    request_report = (batch.generation_report or {}).get("request", {})
    accumulator_ack = bool(request_report.get("accumulator_risk_acknowledged"))
    legs_by_ticket: dict[int, list[TicketLeg]] = defaultdict(list)
    for leg in legs:
        legs_by_ticket[leg.ticket_id].append(leg)
    projected_exposure = risk_context.exposure
    ticket_plans: list[tuple[Ticket, Decimal, dict, dict]] = []
    for ticket in tickets:
        ticket_legs = legs_by_ticket[ticket.id]
        combined_odds = 1.0
        combined_probability = 1.0
        match_scope: set[int | str] = set()
        team_scope: set[int | str] = set()
        league_scope: set[int | str] = set()
        scoped_matches: list[Match] = []
        scoped_fixtures: list[dict | None] = []
        for leg in ticket_legs:
            quote, _market_probability, model_probability = quote_plans[leg.id]
            combined_odds *= quote.price
            combined_probability *= model_probability
            match_scope.add(int(leg.match_id))
            match = matches_by_id[int(leg.match_id)]
            canonical_fixture = fixtures_by_prediction_id[int(leg.model_prediction_id)]
            if canonical_fixture is not None:
                team_scope.update((canonical_fixture["home_team"], canonical_fixture["away_team"]))
                league_scope.add(canonical_fixture["competition_key"])
                scoped_matches.append(match)
                scoped_fixtures.append(canonical_fixture)
            else:
                scoped_matches.append(match)
                scoped_fixtures.append(None)
                team_scope.update(value for value in (match.home_team, match.away_team) if value)
            if canonical_fixture is None and match.competition:
                league_scope.add(match.competition)
        calculation = calculate_stake(
            policy=policy.staking,
            bankroll_amount=risk_context.bankroll_amount,
            ticket_format=ticket.ticket_type,
            ticket_limit_percent=policy.max_ticket_percent,
            model_probability=combined_probability if ticket.ticket_type == "single" else None,
            decimal_odds=combined_odds if ticket.ticket_type == "single" else None,
        )
        if not calculation.eligible:
            raise TicketRefreshConflictError("The configured staking policy produced no eligible stake")
        assessment = assess_portfolio_risk(
            policy=policy,
            context=RiskContext(
                bankroll_amount=risk_context.bankroll_amount,
                available_balance=risk_context.available_balance,
                exposure=projected_exposure,
                now=refresh_time,
            ),
            candidate=RiskCandidate(
                stake=calculation.stake,
                ticket_format=ticket.ticket_type,
                match_ids=frozenset(match_scope),
                team_ids=frozenset(team_scope),
                league_ids=frozenset(league_scope),
                league_kickoffs=_fixture_league_kickoffs(scoped_fixtures, scoped_matches),
                accumulator_risk_acknowledged=accumulator_ack,
                is_automated=False,
            ),
        )
        if not assessment.allowed:
            raise TicketRefreshConflictError("Current portfolio exposure blocks this batch")
        ticket_plans.append(
            (ticket, calculation.stake, _staking_payload(calculation), _risk_assessment_payload(assessment))
        )
        projected_exposure = _project_exposure(
            projected_exposure,
            stake=calculation.stake,
            match_ids=match_scope,
            team_ids=team_scope,
            league_kickoffs=_fixture_league_kickoffs(scoped_fixtures, scoped_matches),
            exposure_id=ticket.id,
        )

    refreshed_revision = expected_revision + 1
    for leg in legs:
        quote, market_probability, model_probability = quote_plans[leg.id]
        expected_value = model_probability * quote.price - 1.0
        leg.odds = quote.price
        leg.bookmaker = quote.bookmaker
        leg.market_probability_snapshot = market_probability
        leg.expected_value_snapshot = expected_value
        leg.edge_pct_snapshot = (model_probability - market_probability) * 100.0
        db.add(
            TicketLegQuoteSnapshot(
                ticket_leg_id=leg.id,
                stage="refresh",
                revision=refreshed_revision,
                odds_entry_id=quote.entry_id,
                odds_snapshot_id=quote.snapshot_id if isinstance(quote.snapshot_id, int) else None,
                market=leg.market,
                selection=leg.selection,
                bookmaker=quote.bookmaker,
                price=quote.price,
                observed_at=quote.observed_at,
                model_probability=model_probability,
                market_probability=market_probability,
                market_probability_method="consensus_de_vig",
                fair_odds=1.0 / model_probability,
                probability_edge_pp=(model_probability - market_probability) * 100.0,
                expected_value=expected_value,
                expected_value_pct=expected_value * 100.0,
            )
        )
    for ticket, new_stake, staking_payload, risk_payload in ticket_plans:
        ticket.stake = new_stake
        ticket.risk_policy_id = policy_row.id
        ticket.risk_policy_version = policy_row.version
        ticket.staking_snapshot = staking_payload
        ticket.risk_assessment = risk_payload
        combined_odds = 1.0
        for leg in legs_by_ticket[ticket.id]:
            combined_odds *= float(leg.odds)
        ticket.total_odds = round(combined_odds, 6)
        ticket.potential_return = quantize_money(new_stake * Decimal(str(combined_odds)))

    batch.revision = refreshed_revision
    batch.risk_policy_id = policy_row.id
    batch.risk_policy_version = policy_row.version
    batch.staking_snapshot = {"tickets": [plan[2] for plan in ticket_plans]}
    batch.risk_assessment = {
        "allowed": True,
        "policy_version": str(policy_row.version),
        "tickets": [plan[3] for plan in ticket_plans],
    }
    batch.total_stake = sum((plan[1] for plan in ticket_plans), Decimal("0.00"))
    report = dict(batch.generation_report or {})
    refresh_event = {
        "refreshed_at": refresh_time.isoformat(),
        "revision": batch.revision,
        "risk_policy_version": policy_row.version,
        "governance_assessment": governance_assessment,
    }
    report["refresh"] = refresh_event
    refresh_history = list(report.get("refresh_history") or [])
    refresh_history.append(refresh_event)
    report["refresh_history"] = refresh_history
    if governance_assessment is not None:
        report["governance_assessment"] = governance_assessment
    batch.generation_report = report
    batch.activation_report = None
    await db.flush()
    return batch, tickets


async def discard_generated_ticket_batch(
    db: AsyncSession,
    *,
    user_id: int,
    batch_id: int,
) -> tuple[int, int]:
    """Delete an owned, untouched generated draft batch.

    Batch and ticket row locks serialize this operation with activation. Existing
    financial, placement, settlement, or trading artifacts always block deletion
    even if the ticket status was externally corrupted back to ``generated``.
    """

    batch_result = await db.execute(select(TicketBatch).where(TicketBatch.id == batch_id).with_for_update())
    batch = batch_result.scalar_one_or_none()
    if batch is None:
        raise LookupError("Ticket batch not found")

    tickets_result = await db.execute(
        select(Ticket).where(Ticket.batch_id == batch_id).order_by(Ticket.id.asc()).with_for_update()
    )
    tickets = list(tickets_result.scalars().all())
    if not tickets or any(ticket.user_id != user_id for ticket in tickets):
        # Do not reveal whether another user's batch exists.
        raise LookupError("Ticket batch not found")
    if any(ticket.status != "generated" for ticket in tickets):
        raise TicketBatchDiscardConflictError("Only untouched generated draft batches can be discarded")

    ticket_ids = [ticket.id for ticket in tickets]
    artifact_queries = (
        ("ledger entries", select(LedgerEntry.id).where(LedgerEntry.ticket_id.in_(ticket_ids)).limit(1)),
        ("bookmaker placements", select(BetPlacement.id).where(BetPlacement.ticket_id.in_(ticket_ids)).limit(1)),
        ("settlements", select(Settlement.id).where(Settlement.ticket_id.in_(ticket_ids)).limit(1)),
        ("trading executions", select(ExecutionIntent.id).where(ExecutionIntent.ticket_id.in_(ticket_ids)).limit(1)),
    )
    for artifact_name, stmt in artifact_queries:
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise TicketBatchDiscardConflictError(f"Ticket batch cannot be discarded because it has {artifact_name}")

    await db.execute(delete(TicketLeg).where(TicketLeg.ticket_id.in_(ticket_ids)))
    await db.execute(delete(Ticket).where(Ticket.id.in_(ticket_ids)))
    await db.execute(delete(TicketBatch).where(TicketBatch.id == batch_id))
    await db.flush()
    return batch_id, len(tickets)


async def swap_ticket_legs(
    db: AsyncSession,
    *,
    user_id: int,
    batch_id: int | None = None,
    source_ticket_id: int,
    source_leg_id: int,
    target_ticket_id: int,
    target_leg_id: int,
) -> tuple[Ticket, Ticket]:
    if source_leg_id == target_leg_id:
        raise ValueError("Choose two different legs to swap")

    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.legs).selectinload(TicketLeg.match), selectinload(Ticket.placements))
        .where(Ticket.user_id == user_id, Ticket.id.in_([source_ticket_id, target_ticket_id]))
        .with_for_update()
    )
    if batch_id is not None:
        stmt = stmt.where(Ticket.batch_id == batch_id)
    result = await db.execute(stmt)
    tickets = {ticket.id: ticket for ticket in result.scalars().unique().all()}
    source_ticket = tickets.get(source_ticket_id)
    target_ticket = tickets.get(target_ticket_id)
    if source_ticket is None or target_ticket is None:
        if batch_id is not None:
            raise ValueError("Both tickets must belong to the selected batch")
        raise ValueError("Ticket not found")
    if batch_id is not None and (source_ticket.batch_id != batch_id or target_ticket.batch_id != batch_id):
        raise ValueError("Both tickets must belong to the selected batch")
    if source_ticket.status != "generated" or target_ticket.status != "generated":
        raise ValueError("Only generated draft tickets can be reviewed or swapped")

    source_leg = next((leg for leg in source_ticket.legs if leg.id == source_leg_id), None)
    target_leg = next((leg for leg in target_ticket.legs if leg.id == target_leg_id), None)
    if source_leg is None or target_leg is None:
        raise ValueError("Ticket leg not found")

    replacements_by_ticket: dict[int, dict[int, int | None]] = defaultdict(dict)
    replacements_by_ticket[source_ticket.id][source_leg.id] = target_leg.match_id
    replacements_by_ticket[target_ticket.id][target_leg.id] = source_leg.match_id
    for ticket in {source_ticket.id: source_ticket, target_ticket.id: target_ticket}.values():
        projected_match_ids = [replacements_by_ticket[ticket.id].get(leg.id, leg.match_id) for leg in ticket.legs]
        if any(match_id is None for match_id in projected_match_ids):
            raise ValueError(f"Ticket {ticket.id} would contain a leg without a match after the swap")
        if len(set(projected_match_ids)) != len(projected_match_ids):
            raise ValueError(f"Ticket {ticket.id} would contain duplicate matches after the swap")

    # Snapshot evidence travels with the selected leg. Swapping only the live
    # prediction reference/odds would silently detach the audit basis from the
    # selection it describes.
    fields = (
        "model_prediction_id",
        "match_id",
        "selection",
        "market",
        "odds",
        "bookmaker",
        *TICKET_LEG_SNAPSHOT_FIELDS,
    )
    source_values = {field: getattr(source_leg, field) for field in fields}
    target_values = {field: getattr(target_leg, field) for field in fields}
    for field in fields:
        setattr(source_leg, field, target_values[field])
        setattr(target_leg, field, source_values[field])

    _recalculate_ticket_totals(source_ticket)
    _recalculate_ticket_totals(target_ticket)
    await db.flush()
    return source_ticket, target_ticket


async def settle_ticket(
    db: AsyncSession,
    ticket_id: int,
    outcome: str,
    return_amount: float = 0.0,
    *,
    user_id: int | None = None,
) -> Settlement:
    normalized_outcome = str(outcome or "").strip().lower()
    if normalized_outcome not in SETTLEMENT_OUTCOMES:
        raise ValueError("outcome must be one of: lost, void, won")
    try:
        normalized_return = float(return_amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("return_amount must be a finite non-negative number") from exc
    if not isfinite(normalized_return) or normalized_return < 0:
        raise ValueError("return_amount must be a finite non-negative number")
    if normalized_outcome == "lost" and normalized_return != 0:
        raise ValueError("return_amount must be 0 when outcome is lost")

    stmt = select(Ticket).options(selectinload(Ticket.legs)).where(Ticket.id == ticket_id).with_for_update()
    if user_id is not None:
        stmt = stmt.where(Ticket.user_id == user_id)
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")
    if ticket.status != "open":
        raise TicketSettlementConflictError("Only active open tickets can be settled")

    bankroll = None
    if ticket.bankroll_id and normalized_return > 0:
        bankroll_result = await db.execute(select(Bankroll).where(Bankroll.id == ticket.bankroll_id).with_for_update())
        bankroll = bankroll_result.scalar_one_or_none()
        if bankroll is None:
            raise ValueError(f"Bankroll {ticket.bankroll_id} not found")
        if user_id is not None and bankroll.user_id != user_id:
            raise PermissionError(f"Bankroll {ticket.bankroll_id} does not belong to the current user")

    normalized_return_money = quantize_money(normalized_return)
    pnl = quantize_money(normalized_return_money - quantize_money(ticket.stake))

    ticket.status = normalized_outcome
    await db.flush()

    settlement = Settlement(
        ticket_id=ticket_id,
        outcome=normalized_outcome,
        return_amount=normalized_return_money,
        pnl=pnl,
    )
    db.add(settlement)

    for leg in ticket.legs:
        leg.status = normalized_outcome

    if bankroll is not None:
        bankroll.balance = quantize_money(bankroll.balance) + normalized_return_money
        ledger = LedgerEntry(
            bankroll_id=ticket.bankroll_id,
            ticket_id=ticket.id,
            entry_type="win" if normalized_outcome == "won" else "void",
            amount=normalized_return_money,
            balance_after=bankroll.balance,
        )
        db.add(ledger)

    await db.flush()
    await db.refresh(settlement)
    return settlement


async def place_bet(
    db: AsyncSession,
    ticket_id: int,
    bookmaker: str,
    bookmaker_account_id: int | None = None,
) -> BetPlacement:
    placement = BetPlacement(
        ticket_id=ticket_id,
        bookmaker_account_id=bookmaker_account_id,
        bookmaker=bookmaker,
        status="placed",
    )
    db.add(placement)
    await db.flush()
    return placement
