"""Authenticated, redacted provider-runtime observability surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.database import get_db
from app.models.job import ScheduledJob, ScheduledJobRun
from app.models.odds_lineage import OddsSnapshot
from app.models.provider_ingestion import ProviderIngestionCheckpoint
from app.models.provider_observation import ProviderObservation, ProviderObservationDatasetLink
from app.models.provider_runtime import ProviderSourceRuntimeState
from app.models.user import User
from app.providers.registry import DEFAULT_PROVIDER_REGISTRY, UnknownProviderError
from app.providers.soccerdata import SoccerdataIngestionSpec, SoccerdataJobMode
from app.schemas.provider import (
    ProviderLaneSnapshotResponse,
    ProviderPipelinePhaseResponse,
    ProviderRuntimeAlertResponse,
    ProviderRuntimeSnapshotResponse,
    ProviderRuntimeSourceResponse,
)
from app.services.worker_observability import collect_worker_lane_snapshot, evaluate_worker_lane_alerts
from app.tasks.worker_lanes import WorkerLane

router = APIRouter()

_MAX_SOURCES = 100
_MAX_RECENT_OBSERVATIONS = 10_000
_MAX_RECENT_CHECKPOINTS = 100
_MAX_RECENT_PHASE_RUNS = 200

# These are execution categories, not provider-specific labels.  They are
# intentionally derived from the persisted scheduled-run contract so the
# operator API never needs to expose task arguments, payloads, or errors.
_SOCCERDATA_TASK_TYPES = frozenset({"soccerdata_http_ingest", "soccerdata_browser_ingest"})
_FEATURE_TASK_TYPES = frozenset({"train_model"})
_MODEL_TASK_TYPES = frozenset({"backtest_model", "predict_model", "run_predictions"})
_FAILED_RUN_STATUSES = frozenset({"failed", "timed_out", "enqueue_failed", "dead_letter"})


@dataclass(frozen=True)
class _ObservationSummary:
    observation_count: int = 0
    complete_snapshot_count: int = 0
    partial_snapshot_count: int = 0
    unmapped_observation_count: int = 0
    conflicted_observations: int = 0
    latest_observed_at: datetime | None = None
    freshness_state: str = "no_data"


@dataclass(frozen=True)
class _CacheSummary:
    cache_state: str = "unknown"


def _source_scope_key(adapter_key: str, source_key: str) -> str:
    return f"{adapter_key}:{source_key}"


def _source_alerts(
    adapter_key: str,
    source_key: str,
    *,
    source: ProviderSourceRuntimeState | None,
    summary: _ObservationSummary,
) -> list[ProviderRuntimeAlertResponse]:
    scope_key = _source_scope_key(adapter_key, source_key)
    alerts: list[ProviderRuntimeAlertResponse] = []
    if source is not None and source.circuit_state == "open":
        alerts.append(
            ProviderRuntimeAlertResponse(scope="source", scope_key=scope_key, code="circuit_open", severity="critical")
        )
    elif source is not None and source.circuit_state == "half_open":
        alerts.append(
            ProviderRuntimeAlertResponse(
                scope="source", scope_key=scope_key, code="circuit_half_open", severity="warning"
            )
        )
    if source is not None and (
        source.provider_remaining == 0
        or source.quota_limit is not None
        and source.quota_consumed + source.quota_reserved >= source.quota_limit
    ):
        alerts.append(
            ProviderRuntimeAlertResponse(
                scope="source", scope_key=scope_key, code="quota_exhausted", severity="critical"
            )
        )
    if source is not None and source.consecutive_failures:
        alerts.append(
            ProviderRuntimeAlertResponse(
                scope="source", scope_key=scope_key, code="consecutive_failures", severity="warning"
            )
        )
    # Observation bodies are intentionally never read here.  Conflict state is
    # a persisted, provider-agnostic quality signal that remains safe to expose.
    if summary.conflicted_observations:
        alerts.append(
            ProviderRuntimeAlertResponse(
                scope="source", scope_key=scope_key, code="observation_conflicted", severity="warning"
            )
        )
    if summary.freshness_state == "stale":
        alerts.append(
            ProviderRuntimeAlertResponse(
                scope="source", scope_key=scope_key, code="freshness_stale", severity="critical"
            )
        )
    if summary.partial_snapshot_count or summary.unmapped_observation_count:
        alerts.append(
            ProviderRuntimeAlertResponse(
                scope="source", scope_key=scope_key, code="coverage_partial", severity="warning"
            )
        )
    return alerts


async def _observation_summaries(
    db: AsyncSession, *, observed_at: datetime
) -> dict[tuple[str, str], _ObservationSummary]:
    """Read capability-aware aggregates over a fixed recent observation sample."""
    recent_observations = (
        select(ProviderObservation.id)
        .order_by(ProviderObservation.ingested_at.desc(), ProviderObservation.id.desc())
        .limit(_MAX_RECENT_OBSERVATIONS)
        .subquery()
    )
    observation_id = ProviderObservation.id
    odds_complete = and_(
        ProviderObservation.capability == "odds",
        OddsSnapshot.quality == "complete",
    )
    odds_partial = and_(
        ProviderObservation.capability == "odds",
        OddsSnapshot.quality == "partial",
    )
    dataset_complete = and_(
        ProviderObservation.capability != "odds",
        ProviderObservationDatasetLink.id.is_not(None),
    )
    lineage_missing = or_(
        and_(ProviderObservation.capability == "odds", OddsSnapshot.id.is_(None)),
        and_(ProviderObservation.capability != "odds", ProviderObservationDatasetLink.id.is_(None)),
    )
    result = await db.execute(
        select(
            ProviderObservation.adapter_key,
            ProviderObservation.source_key,
            func.count(func.distinct(observation_id)).label("observation_count"),
            func.count(func.distinct(observation_id))
            .filter(or_(odds_complete, dataset_complete))
            .label("complete_count"),
            func.count(func.distinct(observation_id)).filter(odds_partial).label("partial_count"),
            func.count(func.distinct(observation_id)).filter(lineage_missing).label("unmapped_count"),
            func.count(func.distinct(observation_id))
            .filter(ProviderObservation.conflict_state == "conflicted")
            .label("conflicted_count"),
            func.max(ProviderObservation.observed_at).label("latest_observed_at"),
        )
        .join(recent_observations, recent_observations.c.id == ProviderObservation.id)
        .outerjoin(OddsSnapshot, OddsSnapshot.provider_observation_id == ProviderObservation.id)
        .outerjoin(
            ProviderObservationDatasetLink,
            ProviderObservationDatasetLink.observation_id == ProviderObservation.id,
        )
        .group_by(ProviderObservation.adapter_key, ProviderObservation.source_key)
        .order_by(ProviderObservation.adapter_key.asc(), ProviderObservation.source_key.asc())
        .limit(_MAX_SOURCES)
    )
    summaries: dict[tuple[str, str], _ObservationSummary] = {}
    for row in result.all():
        observation_count = int(row.observation_count)
        complete_count = int(row.complete_count)
        partial_count = int(row.partial_count)
        latest = row.latest_observed_at
        try:
            descriptor = DEFAULT_PROVIDER_REGISTRY.get_source(str(row.adapter_key), str(row.source_key))
            max_age_seconds = descriptor.freshness_policy.max_age_seconds
        except UnknownProviderError:
            max_age_seconds = None
        if latest is None:
            freshness_state = "no_data"
        elif max_age_seconds is None:
            freshness_state = "unknown"
        else:
            aware_latest = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
            freshness_state = "fresh" if observed_at <= aware_latest + timedelta(seconds=max_age_seconds) else "stale"
        summaries[(str(row.adapter_key), str(row.source_key))] = _ObservationSummary(
            observation_count=observation_count,
            complete_snapshot_count=complete_count,
            partial_snapshot_count=partial_count,
            unmapped_observation_count=int(row.unmapped_count),
            conflicted_observations=int(row.conflicted_count),
            latest_observed_at=latest,
            freshness_state=freshness_state,
        )
    return summaries


async def _cache_summaries(db: AsyncSession) -> dict[tuple[str, str], _CacheSummary]:
    """Derive bounded source cache evidence from persisted ingestion checkpoints."""
    result = await db.execute(
        select(ProviderIngestionCheckpoint.cache_mode, ScheduledJob.config)
        .join(ScheduledJobRun, ScheduledJobRun.id == ProviderIngestionCheckpoint.scheduled_job_run_id)
        .join(ScheduledJob, ScheduledJob.id == ScheduledJobRun.scheduled_job_id)
        .where(ProviderIngestionCheckpoint.cache_mode.is_not(None))
        .order_by(ProviderIngestionCheckpoint.updated_at.desc(), ProviderIngestionCheckpoint.id.desc())
        .limit(_MAX_RECENT_CHECKPOINTS)
    )
    modes_by_source: dict[tuple[str, str], set[str]] = {}
    for row in result.all():
        try:
            spec = SoccerdataIngestionSpec.from_config(row.config or {})
        except (TypeError, ValueError):
            continue
        identity = ("soccerdata", spec.operation_contract.source_key)
        modes_by_source.setdefault(identity, set()).add(str(row.cache_mode))

    summaries: dict[tuple[str, str], _CacheSummary] = {}
    for identity, modes in modes_by_source.items():
        # A revalidation both reuses the local representation and contacts the
        # upstream source.  It is therefore neither a pure hit nor a pure
        # miss for operational purposes.
        has_hit = bool(modes & {"warm", "revalidated"})
        has_miss = bool(modes & {"cold", "no-store", "revalidated"})
        if has_hit and has_miss:
            state = "mixed"
        elif has_hit:
            state = "hit"
        else:
            state = "miss"
        summaries[identity] = _CacheSummary(cache_state=state)
    return summaries


def _phase_status(*, queued: int, running: int, attention_count: int = 0) -> str:
    if running:
        return "running"
    if queued:
        return "queued"
    if attention_count:
        return "attention"
    return "idle"


def _phase_for_run(task_type: str, config: dict | None) -> str | None:
    if task_type in _SOCCERDATA_TASK_TYPES:
        try:
            spec = SoccerdataIngestionSpec.from_config(config or {})
        except (TypeError, ValueError):
            return None
        return "backfill" if spec.mode is SoccerdataJobMode.BACKFILL else None
    if task_type in _FEATURE_TASK_TYPES:
        return "features"
    if task_type in _MODEL_TASK_TYPES:
        return "model"
    return None


async def _pipeline_phases(
    db: AsyncSession,
    *,
    observation_summaries: dict[tuple[str, str], _ObservationSummary],
) -> list[ProviderPipelinePhaseResponse]:
    """Return progress from a fixed recent run sample and persisted job specs."""
    eligible_task_types = _SOCCERDATA_TASK_TYPES | _FEATURE_TASK_TYPES | _MODEL_TASK_TYPES
    base_statement = select(ScheduledJobRun.task_type, ScheduledJobRun.status, ScheduledJob.config).outerjoin(
        ScheduledJob, ScheduledJob.id == ScheduledJobRun.scheduled_job_id
    )
    # Filter in SQL *before* applying each bound.  Active provider/model work
    # must remain visible even when unrelated terminal jobs dominate history.
    active_result = await db.execute(
        base_statement.where(
            ScheduledJobRun.task_type.in_(eligible_task_types),
            ScheduledJobRun.status.in_(("queued", "running")),
        )
        .order_by(ScheduledJobRun.created_at.desc(), ScheduledJobRun.id.desc())
        .limit(_MAX_RECENT_PHASE_RUNS)
    )
    terminal_result = await db.execute(
        base_statement.where(
            ScheduledJobRun.task_type.in_(eligible_task_types),
            ScheduledJobRun.status.not_in(("queued", "running")),
        )
        .order_by(ScheduledJobRun.created_at.desc(), ScheduledJobRun.id.desc())
        .limit(_MAX_RECENT_PHASE_RUNS)
    )
    counts: dict[str, dict[str, int]] = {
        phase: {"queued": 0, "running": 0, "failed": 0, "partial": 0} for phase in ("backfill", "features", "model")
    }
    for row in [*active_result.all(), *terminal_result.all()]:
        phase = _phase_for_run(str(row.task_type), row.config)
        if phase is None:
            continue
        status = str(row.status)
        if status in {"queued", "running", "partial"}:
            counts[phase][status] += 1
        elif status in _FAILED_RUN_STATUSES:
            counts[phase]["failed"] += 1

    normalize_attention = sum(
        summary.partial_snapshot_count + summary.unmapped_observation_count
        for summary in observation_summaries.values()
    )
    phases: list[ProviderPipelinePhaseResponse] = []
    for phase in ("backfill", "normalize", "features", "model"):
        queued = counts.get(phase, {}).get("queued", 0)
        running = counts.get(phase, {}).get("running", 0)
        failed = counts.get(phase, {}).get("failed", 0)
        partial = counts.get(phase, {}).get("partial", 0)
        attention_count = normalize_attention if phase == "normalize" else failed + partial
        phases.append(
            ProviderPipelinePhaseResponse(
                phase=phase,
                status=_phase_status(queued=queued, running=running, attention_count=attention_count),
                queued=queued,
                running=running,
                failed=failed,
                partial=partial,
                attention_count=attention_count,
            )
        )
    return phases


@router.get("/runtime", response_model=ProviderRuntimeSnapshotResponse)
async def provider_runtime_snapshot(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_admin),
) -> ProviderRuntimeSnapshotResponse:
    """Return safe aggregate state for all generic provider worker lanes.

    This endpoint intentionally reads neither provider envelopes, request data,
    raw errors, nor quota reservation identities.  Source runtime state stores
    the reconciled reservation totals needed by operators.
    """
    observed_at = datetime.now(UTC)
    states_result = await db.scalars(
        select(ProviderSourceRuntimeState)
        .order_by(ProviderSourceRuntimeState.adapter_key.asc(), ProviderSourceRuntimeState.source_key.asc())
        .limit(_MAX_SOURCES)
    )
    states = list(states_result.all())
    observation_summaries = await _observation_summaries(db, observed_at=observed_at)
    cache_summaries = await _cache_summaries(db)
    phases = await _pipeline_phases(db, observation_summaries=observation_summaries)

    states_by_identity = {(state.adapter_key, state.source_key): state for state in states}
    source_identities = {
        *((descriptor.adapter_key, descriptor.source_key) for descriptor in DEFAULT_PROVIDER_REGISTRY.list_sources()),
        *states_by_identity,
        *observation_summaries,
    }

    sources: list[ProviderRuntimeSourceResponse] = []
    for adapter_key, source_key in sorted(source_identities)[:_MAX_SOURCES]:
        state = states_by_identity.get((adapter_key, source_key))
        summary = observation_summaries.get((adapter_key, source_key), _ObservationSummary())
        cache_summary = cache_summaries.get((adapter_key, source_key))
        if cache_summary is not None:
            cache_state = cache_summary.cache_state
        elif adapter_key == "soccerdata":
            cache_state = "unknown"
        else:
            cache_state = "not_applicable"
        coverage_percent = (
            100.0 * summary.complete_snapshot_count / summary.observation_count if summary.observation_count else 0.0
        )
        sources.append(
            ProviderRuntimeSourceResponse(
                adapter_key=adapter_key,
                source_key=source_key,
                circuit_state=state.circuit_state if state is not None else "unknown",
                quota_limit=state.quota_limit if state is not None else None,
                quota_reserved=state.quota_reserved if state is not None else 0,
                quota_consumed=state.quota_consumed if state is not None else 0,
                provider_remaining=state.provider_remaining if state is not None else None,
                consecutive_failures=state.consecutive_failures if state is not None else 0,
                last_reconciled_at=state.last_reconciled_at if state is not None else None,
                observation_count=summary.observation_count,
                complete_snapshot_count=summary.complete_snapshot_count,
                partial_snapshot_count=summary.partial_snapshot_count,
                unmapped_observation_count=summary.unmapped_observation_count,
                coverage_percent=coverage_percent,
                latest_observed_at=summary.latest_observed_at,
                freshness_state=summary.freshness_state,
                cache_state=cache_state,
            )
        )
    alerts = [
        alert
        for adapter_key, source_key in sorted(source_identities)[:_MAX_SOURCES]
        for alert in _source_alerts(
            adapter_key,
            source_key,
            source=states_by_identity.get((adapter_key, source_key)),
            summary=observation_summaries.get((adapter_key, source_key), _ObservationSummary()),
        )
    ]

    lane_snapshots = [await collect_worker_lane_snapshot(db, lane, now=observed_at) for lane in WorkerLane]
    lanes = [
        ProviderLaneSnapshotResponse(
            lane=snapshot.lane.value,
            queued=snapshot.queued,
            running=snapshot.running,
            oldest_queue_age_ms=snapshot.oldest_queue_age_ms,
            sampled_terminal_runs=snapshot.sampled_terminal_runs,
            retries=snapshot.retries,
            fallbacks=snapshot.fallbacks,
            freshness_failures=snapshot.freshness_failures,
            peak_rss_bytes=snapshot.peak_rss_bytes,
            peak_pid_count=snapshot.peak_pid_count,
        )
        for snapshot in lane_snapshots
    ]
    for snapshot in lane_snapshots:
        severity_by_code = {"rss_high": "critical", "pid_high": "critical"}
        alerts.extend(
            ProviderRuntimeAlertResponse(
                scope="lane",
                scope_key=snapshot.lane.value,
                code=code,
                severity=severity_by_code.get(code, "warning"),
            )
            for code in evaluate_worker_lane_alerts(snapshot)
        )

    return ProviderRuntimeSnapshotResponse(
        observed_at=observed_at,
        sources=sources,
        lanes=lanes,
        phases=phases,
        alerts=alerts,
    )
