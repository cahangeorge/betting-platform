from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.job import ScheduledJob, ScheduledJobRun, TaskOutbox
from app.tasks.runtime import cgroup_resource_snapshot
from app.tasks.worker_lanes import (
    LEGACY_WORKER_CONTRACT_VERSION,
    WORKER_LANE_CONTRACT_VERSION,
    WorkerLane,
    backlog_cap_for_lane,
    contract_for_operation,
    is_worker_lane_admitted,
    normalize_worker_lane,
)

ACTIVE_TASK_RUN_STATUSES = {"queued", "running"}
TERMINAL_TASK_RUN_STATUSES = {
    "completed",
    "partial",
    "skipped",
    "failed",
    "enqueue_failed",
    "timed_out",
    "cancelled",
}

settings = get_settings()

RETRYABLE_FAILURE_KINDS = frozenset(
    {"timeout", "transport", "provider_429", "provider_5xx", "process_lost", "resource_limit"}
)
TERMINAL_FAILURE_KINDS = frozenset(
    {
        "anti_bot",
        "forbidden",
        "policy_denied",
        "validation",
        "schema",
        "contract_mismatch",
        "identity_conflict",
        "stale_fence",
        "lease_expired",
        "cancelled",
        "internal",
    }
)


class TaskRunExecutionError(RuntimeError):
    """Explicit bounded failure signal crossing an execution boundary."""

    def __init__(self, failure_kind: str, message: str):
        if failure_kind not in RETRYABLE_FAILURE_KINDS | TERMINAL_FAILURE_KINDS:
            raise ValueError(f"{failure_kind!r} is not a recognized failure kind")
        super().__init__(message)
        self.failure_kind = failure_kind


class TransientTaskRunError(TaskRunExecutionError):
    """Explicit adapter/runtime signal eligible for durable execution retry."""

    def __init__(self, failure_kind: str, message: str):
        if failure_kind not in RETRYABLE_FAILURE_KINDS:
            raise ValueError(f"{failure_kind!r} is not a retryable failure kind")
        super().__init__(failure_kind, message)


def classify_execution_failure(exc: BaseException) -> str:
    """Classify only timeout and explicit typed transient failures as retryable."""
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, TaskRunExecutionError):
        return exc.failure_kind
    return "internal"


RETRY_BACKOFF_BASE_SECONDS = {
    WorkerLane.CONTROL: 5,
    WorkerLane.PROVIDER_HTTP: 15,
    WorkerLane.PROVIDER_BROWSER: 30,
    WorkerLane.MODEL_CPU: 30,
}
RETRY_BACKOFF_MAX_SECONDS = 300


def next_task_retry_at(run: ScheduledJobRun, failure_kind: str, *, now: datetime | None = None) -> datetime:
    """Deterministic bounded exponential backoff; no random retry storm."""
    lane = normalize_worker_lane(getattr(run, "queue_lane", WorkerLane.CONTROL.value))
    base = RETRY_BACKOFF_BASE_SECONDS[lane]
    exponent = max(0, min(int(run.attempt) - 1, 6))
    window = min(RETRY_BACKOFF_MAX_SECONDS, base * (2**exponent))
    digest = sha256(f"{lane.value}:{run.id}:{run.attempt}:{failure_kind}".encode()).digest()
    jitter = int.from_bytes(digest[:2], "big") % (max(1, window // 5) + 1)
    return (now or utcnow()) + timedelta(seconds=min(RETRY_BACKOFF_MAX_SECONDS, window + jitter))


def retry_disposition_for_failure_kind(failure_kind: str | None) -> str:
    """Return the bounded execution-retry disposition for a machine failure kind."""
    normalized = str(failure_kind or "validation").strip().lower()
    return "retryable" if normalized in RETRYABLE_FAILURE_KINDS else "terminal"


LANE_ADVISORY_LOCK_NAMESPACE = 8_462_033
LANE_ADVISORY_LOCK_IDS = {
    WorkerLane.CONTROL: 1,
    WorkerLane.PROVIDER_HTTP: 2,
    WorkerLane.PROVIDER_BROWSER: 3,
    WorkerLane.MODEL_CPU: 4,
}


class LaneBackpressureError(RuntimeError):
    def __init__(self, lane: WorkerLane, cap: int):
        super().__init__(f"Worker lane {lane.value!r} is saturated at active cap {cap}")
        self.lane, self.cap = lane, cap


class WorkerLaneAdmissionClosedError(RuntimeError):
    def __init__(self, lane: WorkerLane):
        super().__init__(f"Worker lane {lane.value!r} is not admitted for new work")
        self.lane = lane


async def acquire_lane_advisory_lock(db: AsyncSession, lane: WorkerLane | str) -> None:
    lane = normalize_worker_lane(lane)
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :lane_id)"),
            {"namespace": LANE_ADVISORY_LOCK_NAMESPACE, "lane_id": LANE_ADVISORY_LOCK_IDS[lane]},
        )


async def enforce_lane_backpressure(db: AsyncSession, lane: WorkerLane | str) -> None:
    lane = normalize_worker_lane(lane)
    await acquire_lane_advisory_lock(db, lane)
    if db.get_bind().dialect.name != "postgresql":
        return
    cap = backlog_cap_for_lane(settings, lane)
    result = await db.execute(
        select(func.count())
        .select_from(ScheduledJobRun)
        .where(ScheduledJobRun.queue_lane == lane.value, ScheduledJobRun.status.in_(ACTIVE_TASK_RUN_STATUSES))
    )
    if int(result.scalar_one()) >= cap:
        raise LaneBackpressureError(lane, cap)


class TaskOutboxContractError(RuntimeError):
    """A v1 Taskiq retry cannot be made durable without its matching outbox."""


class StaleTaskRunFenceError(RuntimeError):
    """A worker lost the durable claim before committing backend state."""


def _execution_token() -> str:
    return uuid4().hex


async def assert_task_run_fence(db: AsyncSession, run_id: int, execution_token: str) -> None:
    """Lock and verify a v1 claimant immediately before a business commit."""
    result = await db.execute(
        select(ScheduledJobRun.id)
        .where(
            ScheduledJobRun.id == run_id,
            ScheduledJobRun.status == "running",
            ScheduledJobRun.execution_token == execution_token,
            ScheduledJobRun.queue_contract_version == WORKER_LANE_CONTRACT_VERSION,
        )
        .with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise StaleTaskRunFenceError(f"Task run {run_id} lost its execution fence")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    if started_at is None or finished_at is None:
        return None
    started = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    finished = finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)
    return max(0, int((finished - started).total_seconds() * 1000))


async def find_active_scrape_task_run(
    db: AsyncSession,
    *,
    task_type: str,
    scrape_job_id: int,
) -> ScheduledJobRun | None:
    stmt = (
        select(ScheduledJobRun)
        .where(
            ScheduledJobRun.task_type == task_type,
            ScheduledJobRun.scrape_job_id == scrape_job_id,
            ScheduledJobRun.status.in_(ACTIVE_TASK_RUN_STATUSES),
        )
        .order_by(ScheduledJobRun.created_at.desc(), ScheduledJobRun.id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_task_run(
    db: AsyncSession,
    *,
    task_type: str,
    scheduled_job: ScheduledJob | None = None,
    scrape_job_id: int | None = None,
    triggered_by: str = "scheduler",
    due_at: datetime | None = None,
    artifacts: dict[str, Any] | None = None,
    status: str = "queued",
    transport: str | None = None,
    idempotency_key: str | None = None,
    max_attempts: int | None = None,
    queue_lane: WorkerLane | str | None = None,
    queue_contract_version: str | None = None,
) -> ScheduledJobRun:
    now = utcnow()
    contract = contract_for_operation(task_type, allow_unknown_control=True)
    lane = normalize_worker_lane(queue_lane) if queue_lane is not None else contract.lane
    queue_contract_version = queue_contract_version or contract.queue_contract_version
    if queue_contract_version not in {WORKER_LANE_CONTRACT_VERSION, LEGACY_WORKER_CONTRACT_VERSION}:
        raise ValueError(f"Unsupported worker lane contract version: {queue_contract_version}")
    if queue_contract_version == LEGACY_WORKER_CONTRACT_VERSION:
        if lane is not WorkerLane.CONTROL or max_attempts not in {None, 1}:
            raise ValueError("legacy-control/v0 is allowed only on control with max_attempts=1")
    if not is_worker_lane_admitted(settings, lane):
        raise WorkerLaneAdmissionClosedError(lane)
    await enforce_lane_backpressure(db, lane)
    run = ScheduledJobRun(
        scheduled_job_id=scheduled_job.id if scheduled_job else None,
        scrape_job_id=scrape_job_id,
        task_type=task_type,
        status=status,
        queued_at=now if status in {"queued", "running"} else None,
        started_at=now if status == "running" else None,
        triggered_by=triggered_by,
        due_at=due_at,
        artifacts=artifacts or None,
        transport=transport or settings.task_queue_backend,
        idempotency_key=idempotency_key or f"task-run:{uuid4()}",
        max_attempts=(
            1
            if queue_contract_version == LEGACY_WORKER_CONTRACT_VERSION
            else (max_attempts if max_attempts is not None else contract.max_attempts)
        ),
        queue_lane=lane.value,
        queue_contract_version=queue_contract_version,
    )
    db.add(run)
    await db.flush()
    return run


async def mark_task_run_queued(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    transport_task_id: str | None = None,
    taskiq_task_id: str | None = None,
) -> ScheduledJobRun:
    run.status = "queued"
    run.queued_at = run.queued_at or utcnow()
    task_id = transport_task_id or taskiq_task_id
    run.transport_task_id = task_id or run.transport_task_id
    # Deprecated compatibility alias. New code should read transport_task_id.
    run.taskiq_task_id = task_id or run.taskiq_task_id
    await db.flush()
    return run


async def mark_task_run_running(
    db: AsyncSession, run: ScheduledJobRun, *, lease_seconds: int | None = None
) -> ScheduledJobRun:
    now = utcnow()
    run.status = "running"
    run.started_at = run.started_at or now
    run.heartbeat_at = now
    run.lease_expires_at = now + timedelta(seconds=lease_seconds or settings.task_run_lease_seconds)
    run.error = None
    if getattr(run, "queue_contract_version", WORKER_LANE_CONTRACT_VERSION) == WORKER_LANE_CONTRACT_VERSION:
        run.execution_token = _execution_token()
    await db.flush()
    return run


async def claim_queued_task_run(
    db: AsyncSession,
    run_id: int,
    *,
    now: datetime | None = None,
    lease_seconds: int | None = None,
) -> ScheduledJobRun | None:
    """Atomically transition a queued run to running.

    Returns the claimed run, or None when another worker already claimed or
    completed it. This protects Taskiq duplicate delivery/retry paths from
    executing side effects more than once.
    """
    claimed_at = now or utcnow()
    lease_expires_at = claimed_at + timedelta(seconds=lease_seconds or settings.task_run_lease_seconds)
    execution_token = _execution_token()
    stmt = (
        update(ScheduledJobRun)
        .where(
            ScheduledJobRun.id == run_id,
            or_(
                (
                    (ScheduledJobRun.status == "queued")
                    & or_(ScheduledJobRun.next_attempt_at.is_(None), ScheduledJobRun.next_attempt_at <= claimed_at)
                ),
                (
                    (ScheduledJobRun.status == "running")
                    & (ScheduledJobRun.lease_expires_at.is_not(None))
                    & (ScheduledJobRun.lease_expires_at <= claimed_at)
                    & (ScheduledJobRun.attempt < ScheduledJobRun.max_attempts)
                ),
            ),
        )
        .values(
            status="running",
            started_at=claimed_at,
            heartbeat_at=claimed_at,
            lease_expires_at=lease_expires_at,
            next_attempt_at=None,
            attempt=ScheduledJobRun.attempt
            + sa.case(
                (
                    (ScheduledJobRun.status == "running")
                    | ((ScheduledJobRun.status == "queued") & ScheduledJobRun.next_attempt_at.is_not(None)),
                    1,
                ),
                else_=0,
            ),
            finished_at=None,
            duration_ms=None,
            error=None,
            execution_token=sa.case(
                (ScheduledJobRun.queue_contract_version == WORKER_LANE_CONTRACT_VERSION, execution_token),
                else_=None,
            ),
            failure_kind=None,
            retry_disposition=None,
        )
        .returning(ScheduledJobRun.id)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    claimed_id = result.scalar_one_or_none()
    if claimed_id is not None:
        # Force an asynchronous refresh because the same run may already be in
        # the identity map from the caller's lease/timeout lookup.
        claimed_run = await db.get(ScheduledJobRun, claimed_id, populate_existing=True)
        if claimed_run is None:
            return None
        if getattr(claimed_run, "queue_contract_version", WORKER_LANE_CONTRACT_VERSION) == WORKER_LANE_CONTRACT_VERSION:
            claimed_run.execution_token = execution_token
        claimed_run.queue_wait_ms = duration_ms(getattr(claimed_run, "queued_at", None), claimed_at)
        await db.flush()
        return claimed_run

    exhausted_stmt = (
        update(ScheduledJobRun)
        .where(
            ScheduledJobRun.id == run_id,
            ScheduledJobRun.status == "running",
            ScheduledJobRun.lease_expires_at.is_not(None),
            ScheduledJobRun.lease_expires_at <= claimed_at,
            ScheduledJobRun.attempt >= ScheduledJobRun.max_attempts,
        )
        .values(
            status="timed_out",
            finished_at=claimed_at,
            heartbeat_at=claimed_at,
            lease_expires_at=None,
            error="task lease expired and retry limit was exhausted",
            failure_kind="lease_expired",
            retry_disposition="terminal",
            execution_token=None,
        )
        .returning(ScheduledJobRun.id)
        .execution_options(synchronize_session=False)
    )
    exhausted_result = await db.execute(exhausted_stmt)
    exhausted_id = exhausted_result.scalar_one_or_none()
    if exhausted_id is not None:
        exhausted_run = await db.get(ScheduledJobRun, exhausted_id, populate_existing=True)
    else:
        exhausted_run = None
    if exhausted_run is not None:
        exhausted_run.duration_ms = duration_ms(exhausted_run.started_at, claimed_at)
        await db.flush()
    return None


async def finish_task_run(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    status: str,
    detail: str | None = None,
    artifacts: dict[str, Any] | None = None,
    error: str | None = None,
    execution_token: str | None = None,
    failure_kind: str | None = None,
    retry_disposition: str | None = None,
    metrics: dict[str, Any] | None = None,
    peak_rss_bytes: int | None = None,
    peak_pid_count: int | None = None,
    raise_on_stale_fence: bool = True,
) -> ScheduledJobRun:
    """Persist a terminal result, fencing it when a claim token is supplied.

    Fencing does not promise exactly-once external provider effects; callers
    still need stable adapter idempotency keys and reconciliation.
    """
    is_v1 = getattr(run, "queue_contract_version", LEGACY_WORKER_CONTRACT_VERSION) == WORKER_LANE_CONTRACT_VERSION
    if is_v1 and run.status == "running" and not execution_token:
        raise StaleTaskRunFenceError(f"Task run {run.id} requires an execution fence")
    finished_at = utcnow()
    resource_snapshot = cgroup_resource_snapshot()
    peak_rss_bytes = peak_rss_bytes if peak_rss_bytes is not None else resource_snapshot["peak_rss_bytes"]
    peak_pid_count = peak_pid_count if peak_pid_count is not None else resource_snapshot["peak_pid_count"]
    if resource_snapshot["peak_rss_bytes"] is not None or resource_snapshot["peak_pid_count"] is not None:
        metrics = {**(metrics or {}), "resource": resource_snapshot}
    normalized_kind = str(failure_kind).strip().lower() if failure_kind else None
    disposition = retry_disposition or (
        retry_disposition_for_failure_kind(normalized_kind) if normalized_kind else None
    )
    if execution_token is not None:
        values: dict[str, Any] = {
            "status": status,
            "finished_at": finished_at,
            "duration_ms": duration_ms(run.started_at, finished_at),
            "detail": detail,
            "error": error,
            "lease_expires_at": None,
            "heartbeat_at": finished_at,
            "execution_token": None,
            "failure_kind": normalized_kind,
            "retry_disposition": disposition,
        }
        if artifacts:
            values["artifacts"] = {**(run.artifacts or {}), **artifacts}
        if metrics is not None:
            values["metrics"] = {**(run.metrics or {}), **metrics}
        if peak_rss_bytes is not None:
            values["peak_rss_bytes"] = peak_rss_bytes
        if peak_pid_count is not None:
            values["peak_pid_count"] = peak_pid_count
        result = await db.execute(
            update(ScheduledJobRun)
            .where(
                ScheduledJobRun.id == run.id,
                ScheduledJobRun.status == "running",
                ScheduledJobRun.execution_token == execution_token,
            )
            .values(**values)
            .returning(ScheduledJobRun.id)
        )
        if result.scalar_one_or_none() is None:
            if raise_on_stale_fence:
                raise StaleTaskRunFenceError(f"Task run {run.id} lost its execution fence")
            return run
    run.status = status
    run.finished_at = finished_at
    run.duration_ms = duration_ms(run.started_at, finished_at)
    run.detail = detail
    if artifacts:
        run.artifacts = {**(run.artifacts or {}), **artifacts}
    if metrics is not None:
        run.metrics = {**(run.metrics or {}), **metrics}
    run.error = error
    run.lease_expires_at = None
    run.heartbeat_at = finished_at
    run.execution_token = None
    run.failure_kind = normalized_kind
    run.retry_disposition = disposition
    if peak_rss_bytes is not None:
        run.peak_rss_bytes = peak_rss_bytes
    if peak_pid_count is not None:
        run.peak_pid_count = peak_pid_count
    await db.flush()
    return run


async def mark_task_run_enqueue_failed(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    error: str,
) -> ScheduledJobRun:
    return await finish_task_run(db, run, status="enqueue_failed", detail="enqueue_failed", error=error)


async def heartbeat_task_run(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    lease_seconds: int | None = None,
    execution_token: str | None = None,
) -> ScheduledJobRun:
    if run.status != "running":
        return run
    if (
        getattr(run, "queue_contract_version", LEGACY_WORKER_CONTRACT_VERSION) == WORKER_LANE_CONTRACT_VERSION
        and not execution_token
    ):
        return run
    renewed = await heartbeat_task_run_by_id(db, run.id, lease_seconds=lease_seconds, execution_token=execution_token)
    if renewed:
        now = utcnow()
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=lease_seconds or settings.task_run_lease_seconds)
    return run


async def heartbeat_task_run_by_id(
    db: AsyncSession,
    run_id: int,
    *,
    now: datetime | None = None,
    lease_seconds: int | None = None,
    execution_token: str | None = None,
) -> bool:
    """Renew only the live claimant lease; late fenced heartbeats are no-ops."""
    heartbeat_at = now or utcnow()
    lease_expires_at = heartbeat_at + timedelta(seconds=lease_seconds or settings.task_run_lease_seconds)
    predicates = [ScheduledJobRun.id == run_id, ScheduledJobRun.status == "running"]
    if execution_token is not None:
        predicates.append(ScheduledJobRun.execution_token == execution_token)
    else:
        predicates.append(ScheduledJobRun.queue_contract_version == LEGACY_WORKER_CONTRACT_VERSION)
    stmt = (
        update(ScheduledJobRun)
        .where(*predicates)
        .values(heartbeat_at=heartbeat_at, lease_expires_at=lease_expires_at)
        .returning(ScheduledJobRun.id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def record_task_run_metrics(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    execution_token: str,
    metrics: dict[str, Any] | None = None,
    peak_rss_bytes: int | None = None,
    peak_pid_count: int | None = None,
) -> bool:
    """Record bounded lane telemetry only for the current execution claimant."""
    if peak_rss_bytes is not None and peak_rss_bytes < 0:
        raise ValueError("peak_rss_bytes must be non-negative")
    if peak_pid_count is not None and peak_pid_count < 0:
        raise ValueError("peak_pid_count must be non-negative")
    values: dict[str, Any] = {}
    if metrics is not None:
        values["metrics"] = {**(run.metrics or {}), **metrics}
    if peak_rss_bytes is not None:
        values["peak_rss_bytes"] = peak_rss_bytes
    if peak_pid_count is not None:
        values["peak_pid_count"] = peak_pid_count
    if not values:
        return True
    result = await db.execute(
        update(ScheduledJobRun)
        .where(
            ScheduledJobRun.id == run.id,
            ScheduledJobRun.status == "running",
            ScheduledJobRun.execution_token == execution_token,
        )
        .values(**values)
        .returning(ScheduledJobRun.id)
    )
    return result.scalar_one_or_none() is not None


async def requeue_task_run_failure(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    execution_token: str,
    failure_kind: str,
    error: str,
    retry_at: datetime | None = None,
) -> bool:
    """Fence a retryable attempt or terminalize it without resurrecting a run."""
    kind = str(failure_kind).strip().lower()
    disposition = retry_disposition_for_failure_kind(kind)
    now = utcnow()
    is_v1_taskiq = (
        getattr(run, "queue_contract_version", LEGACY_WORKER_CONTRACT_VERSION) == WORKER_LANE_CONTRACT_VERSION
        and getattr(run, "transport", None) == "taskiq"
    )
    outbox = None
    if is_v1_taskiq:
        # Canonical lock order is outbox -> run, matching the publisher.
        outbox_result = await db.execute(select(TaskOutbox).where(TaskOutbox.run_id == run.id).with_for_update())
        outbox = outbox_result.scalar_one_or_none()
        if outbox is None:
            raise TaskOutboxContractError(f"Task run {run.id} has no durable outbox for execution recovery")
        if outbox.queue_lane != run.queue_lane or outbox.queue_contract_version != run.queue_contract_version:
            raise TaskOutboxContractError(f"Task outbox {outbox.id} lane contract does not match run {run.id}")
    where = (
        ScheduledJobRun.id == run.id,
        ScheduledJobRun.status == "running",
        ScheduledJobRun.execution_token == execution_token,
    )
    if disposition == "retryable" and run.attempt < run.max_attempts:
        scheduled_retry_at = retry_at or next_task_retry_at(run, kind, now=now)
        values: dict[str, Any] = {
            "status": "queued",
            "next_attempt_at": scheduled_retry_at,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "queue_wait_ms": None,
            "lease_expires_at": None,
            "heartbeat_at": now,
            "execution_token": None,
            "error": error,
            "failure_kind": kind,
            "retry_disposition": "retryable",
        }
    else:
        values = {
            "status": "failed",
            "finished_at": now,
            "duration_ms": duration_ms(run.started_at, now),
            "lease_expires_at": None,
            "heartbeat_at": now,
            "execution_token": None,
            "error": error,
            "failure_kind": kind,
            "retry_disposition": "terminal",
        }
    result = await db.execute(update(ScheduledJobRun).where(*where).values(**values).returning(ScheduledJobRun.id))
    changed = result.scalar_one_or_none() is not None
    if changed and disposition == "retryable" and run.attempt < run.max_attempts:
        run.status = "queued"
        run.next_attempt_at = scheduled_retry_at
        run.started_at = None
        run.finished_at = None
        run.duration_ms = None
        run.queue_wait_ms = None
        run.lease_expires_at = None
        run.execution_token = None
        run.error = error
        run.failure_kind = kind
        run.retry_disposition = "retryable"
        if outbox is not None and hasattr(outbox, "queue_lane"):
            outbox.delivery_generation += 1
            outbox.attempts = 0
            outbox.status = "pending"
            outbox.available_at = scheduled_retry_at
            outbox.last_error = f"execution {kind}; awaiting durable republish"
    if changed and not (disposition == "retryable" and run.attempt < run.max_attempts):
        run.status = "failed"
        run.finished_at = now
        run.lease_expires_at = None
        run.execution_token = None
        run.error = error
        run.failure_kind = kind
        run.retry_disposition = "terminal"
    return changed


async def create_task_outbox(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    task_name: str,
    transport: str | None = None,
    max_attempts: int | None = None,
    queue_lane: WorkerLane | str | None = None,
    queue_contract_version: str | None = None,
) -> TaskOutbox:
    lane = normalize_worker_lane(queue_lane or run.queue_lane)
    contract_version = queue_contract_version or run.queue_contract_version
    if lane.value != run.queue_lane or contract_version != run.queue_contract_version:
        raise ValueError("Task outbox lane and contract version must match its scheduled job run")
    outbox = TaskOutbox(
        run_id=run.id,
        task_name=task_name,
        transport=transport or run.transport,
        queue_lane=lane.value,
        queue_contract_version=contract_version,
        status="pending",
        attempts=0,
        delivery_generation=1,
        max_attempts=max_attempts or settings.task_publish_max_attempts,
        available_at=utcnow(),
    )
    db.add(outbox)
    await db.flush()
    return outbox


async def mark_outbox_published(
    db: AsyncSession, outbox: TaskOutbox, run: ScheduledJobRun, *, transport_task_id: str | None
) -> None:
    now = utcnow()
    outbox.status = "published"
    outbox.published_at = now
    outbox.last_error = None
    outbox.transport_task_id = transport_task_id
    run.transport_task_id = transport_task_id or run.transport_task_id
    if run.transport == "taskiq":
        run.taskiq_task_id = transport_task_id or run.taskiq_task_id
    if run.detail == "enqueue_retry_pending":
        run.detail = None
        run.error = None
    await db.flush()


async def mark_outbox_publish_failed(db: AsyncSession, outbox: TaskOutbox, run: ScheduledJobRun, *, error: str) -> None:
    outbox.last_error = error
    run.error = error
    run.detail = "enqueue_retry_pending"
    if outbox.attempts >= outbox.max_attempts:
        outbox.status = "failed"
        await finish_task_run(db, run, status="enqueue_failed", detail="enqueue_failed", error=error)
    else:
        outbox.status = "pending"
        outbox.available_at = utcnow() + timedelta(seconds=settings.task_publish_retry_seconds)
    await db.flush()
