"""Bounded, lane-aware worker telemetry and alert evaluation."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import ScheduledJobRun
from app.services.task_runs import ACTIVE_TASK_RUN_STATUSES
from app.tasks.worker_lanes import WorkerLane, normalize_worker_lane


@dataclass(frozen=True)
class WorkerLaneSnapshot:
    lane: WorkerLane
    queued: int
    running: int
    oldest_queue_age_ms: int
    sampled_terminal_runs: int
    retries: int
    fallbacks: int
    freshness_failures: int
    peak_rss_bytes: int | None
    peak_pid_count: int | None


@dataclass(frozen=True)
class WorkerLaneThresholds:
    queue_age_ms: int
    rss_bytes: int
    pid_count: int
    retry_rate: float = 0.25
    fallback_rate: float = 0.25


LANE_THRESHOLDS = {
    WorkerLane.CONTROL: WorkerLaneThresholds(120_000, 4 * 1024**3, 512),
    WorkerLane.PROVIDER_HTTP: WorkerLaneThresholds(600_000, 1 * 1024**3, 128),
    WorkerLane.PROVIDER_BROWSER: WorkerLaneThresholds(3_660_000, 4 * 1024**3, 512),
    WorkerLane.MODEL_CPU: WorkerLaneThresholds(3_600_000, 4 * 1024**3, 256),
}


def _positive_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _queue_age_ms(queued_at: datetime | None, now: datetime) -> int:
    if queued_at is None:
        return 0
    queued = queued_at if queued_at.tzinfo else queued_at.replace(tzinfo=timezone.utc)
    return max(0, int((now - queued).total_seconds() * 1000))


async def collect_worker_lane_snapshot(
    db: AsyncSession,
    lane: WorkerLane | str,
    *,
    now: datetime | None = None,
    terminal_sample_limit: int = 250,
) -> WorkerLaneSnapshot:
    """Collect a bounded PostgreSQL snapshot; Redis depth is not business truth."""
    resolved_lane = normalize_worker_lane(lane)
    observed_at = now or datetime.now(timezone.utc)
    active_result = await db.scalars(
        select(ScheduledJobRun)
        .where(
            ScheduledJobRun.queue_lane == resolved_lane.value,
            ScheduledJobRun.status.in_(ACTIVE_TASK_RUN_STATUSES),
        )
        .order_by(ScheduledJobRun.queued_at.asc().nulls_last(), ScheduledJobRun.id.asc())
    )
    active = list(active_result.all())
    terminal_result = await db.scalars(
        select(ScheduledJobRun)
        .where(
            ScheduledJobRun.queue_lane == resolved_lane.value,
            ScheduledJobRun.status.not_in(ACTIVE_TASK_RUN_STATUSES),
        )
        .order_by(ScheduledJobRun.created_at.desc(), ScheduledJobRun.id.desc())
        .limit(terminal_sample_limit)
    )
    terminal = list(terminal_result.all())
    sampled = active + terminal
    fallbacks = 0
    freshness_failures = 0
    for run in sampled:
        metrics = run.metrics if isinstance(run.metrics, dict) else {}
        fallbacks += _positive_int(metrics.get("fallback_count"))
        freshness_status = str(metrics.get("freshness_status") or "").lower()
        if metrics.get("freshness_failed") is True or freshness_status in {"expired", "failed", "stale"}:
            freshness_failures += 1

    rss_values = [run.peak_rss_bytes for run in sampled if run.peak_rss_bytes is not None]
    pid_values = [run.peak_pid_count for run in sampled if run.peak_pid_count is not None]
    return WorkerLaneSnapshot(
        lane=resolved_lane,
        queued=sum(run.status == "queued" for run in active),
        running=sum(run.status == "running" for run in active),
        oldest_queue_age_ms=max((_queue_age_ms(run.queued_at, observed_at) for run in active), default=0),
        sampled_terminal_runs=len(terminal),
        retries=sum(max(0, run.attempt - 1) for run in terminal),
        fallbacks=fallbacks,
        freshness_failures=freshness_failures,
        peak_rss_bytes=max(rss_values, default=None),
        peak_pid_count=max(pid_values, default=None),
    )


def evaluate_worker_lane_alerts(snapshot: WorkerLaneSnapshot) -> tuple[str, ...]:
    """Return stable alert codes; an empty tuple is the recovered state."""
    thresholds = LANE_THRESHOLDS[snapshot.lane]
    alerts: list[str] = []
    if snapshot.oldest_queue_age_ms > thresholds.queue_age_ms:
        alerts.append("queue_age_high")
    if snapshot.peak_rss_bytes is not None and snapshot.peak_rss_bytes > thresholds.rss_bytes:
        alerts.append("rss_high")
    if snapshot.peak_pid_count is not None and snapshot.peak_pid_count > thresholds.pid_count:
        alerts.append("pid_high")
    sample_size = snapshot.sampled_terminal_runs
    if sample_size >= 4 and snapshot.retries / sample_size > thresholds.retry_rate:
        alerts.append("retry_rate_high")
    if sample_size >= 4 and snapshot.fallbacks / sample_size > thresholds.fallback_rate:
        alerts.append("fallback_rate_high")
    if snapshot.freshness_failures:
        alerts.append("freshness_failure")
    return tuple(alerts)
