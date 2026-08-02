import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.models.job import ScheduledJob, ScheduledJobRun, TaskOutbox
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.provider_observation import ProviderObservation
from app.models.user import User
from app.providers.soccerdata import SoccerdataIngestionSpec
from app.schemas.job import (
    LICENSED_ODDS_SCHEDULED_TASK_TYPES,
    MODEL_PIPELINE_SCHEDULED_TASK_TYPES,
    SCHEDULED_JOB_TASK_TYPES,
    LicensedOddsJobSpecV1,
    parse_licensed_odds_scheduled_config,
    parse_model_pipeline_scheduled_config,
    validate_scheduled_job_cron,
)
from app.schemas.strategy import StrategyRunFilters, StrategyRunRequest
from app.services.licensed_odds import LicensedOddsAcquisitionStatus, LicensedOddsService
from app.services.model_artifacts import model_fingerprint
from app.services.odds_ingestion import OddsObservationMaterializationError, materialize_odds_observation
from app.services.odds_rollout import canary_bucket, included_in_canary
from app.services.python_bridge import BridgeError
from app.services.result_settlement import evaluate_model_prediction, settle_due_tickets
from app.services.scraper import create_scrape_job, execute_scrape_job
from app.services.soccerdata_ingestion import (
    SoccerdataBatch,
    SoccerdataIngestionError,
    SoccerdataIngestionResult,
    authorize_soccerdata_ingestion,
    fetch_soccerdata_batch,
    persist_soccerdata_batch,
    replay_soccerdata_batch,
)
from app.services.task_runs import (
    RETRYABLE_FAILURE_KINDS,
    TERMINAL_FAILURE_KINDS,
    LaneBackpressureError,
    StaleTaskRunFenceError,
    TaskOutboxContractError,
    TransientTaskRunError,
    WorkerLaneAdmissionClosedError,
    acquire_lane_advisory_lock,
    assert_task_run_fence,
    claim_queued_task_run,
    classify_execution_failure,
    create_task_outbox,
    create_task_run,
    find_active_scrape_task_run,
    finish_task_run,
    heartbeat_task_run_by_id,
    mark_outbox_publish_failed,
    mark_outbox_published,
    next_task_retry_at,
    requeue_task_run_failure,
)
from app.services.ticket_engine import TicketGenerationError, TicketRiskPolicyRequiredError, generate_tickets
from app.tasks.worker_lanes import (
    LEGACY_WORKER_CONTRACT_VERSION,
    WORKER_LANE_CONTRACT_VERSION,
    WorkerLane,
    WorkerLaneDisabledError,
    is_worker_lane_enabled,
    lane_for_operation,
    queue_name_for_lane,
    worker_lane_spec,
)

SCHEDULED_JOB_OWNER_CONFIG_KEY = "_created_by_user_id"
SCHEDULED_JOB_QUARANTINE_CONFIG_KEY = "_scheduler_quarantine"

_scheduler_lock = asyncio.Lock()
_scheduler_task: asyncio.Task | None = None
_inprocess_tasks: set[asyncio.Task] = set()
_inprocess_scrape_semaphore: tuple[int, asyncio.Semaphore] | None = None

settings = get_settings()
logger = logging.getLogger(__name__)


def _task_run_lease_seconds(run: ScheduledJobRun) -> int:
    configured_lease = settings.task_run_lease_seconds
    task_type = (run.task_type or "").lower()
    if task_type in LICENSED_ODDS_SCHEDULED_TASK_TYPES:
        return max(configured_lease, worker_lane_spec(lane_for_operation(task_type)).timeout_seconds + 60)
    if task_type == "world_cup_pipeline" or any(token in task_type for token in ("scrape", "odds")):
        # A healthy OddsHarvester subprocess may legitimately use its entire
        # timeout. The margin prevents a duplicate claim between timeout and
        # exception/final-state persistence, including SQLite dev mode where a
        # long write transaction may temporarily block the heartbeat session.
        return max(configured_lease, settings.oddsharvester_timeout_seconds + 60)
    if task_type in {"soccerdata_http_ingest", "soccerdata_browser_ingest"} | MODEL_PIPELINE_SCHEDULED_TASK_TYPES:
        return max(configured_lease, worker_lane_spec(lane_for_operation(task_type)).timeout_seconds + 60)
    return configured_lease


def _run_execution_token(run: ScheduledJobRun) -> str | None:
    """Legacy control envelopes retain compatibility without v1 fencing."""
    if getattr(run, "queue_contract_version", LEGACY_WORKER_CONTRACT_VERSION) != WORKER_LANE_CONTRACT_VERSION:
        return None
    return getattr(run, "execution_token", None)


async def _maintain_task_run_heartbeat(
    run_id: int,
    stopped: asyncio.Event,
    *,
    lease_seconds: int | None = None,
    execution_token: str | None = None,
) -> None:
    """Renew a running task lease until execution finishes.

    The heartbeat owns its own short-lived session so a long scraper or model
    transaction cannot prevent lease renewal. A worker that genuinely dies
    stops heartbeating and remains recoverable after the lease expires.
    """
    effective_lease_seconds = lease_seconds or settings.task_run_lease_seconds
    interval_seconds = max(1, min(30, effective_lease_seconds // 3))
    while True:
        try:
            await asyncio.wait_for(stopped.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            pass

        try:
            async with async_session_factory() as heartbeat_db:
                heartbeat_kwargs = {"lease_seconds": effective_lease_seconds}
                if execution_token is not None:
                    heartbeat_kwargs["execution_token"] = execution_token
                renewed = await heartbeat_task_run_by_id(heartbeat_db, run_id, **heartbeat_kwargs)
                await heartbeat_db.commit()
        except Exception:
            logger.warning("Task run %s heartbeat renewal failed", run_id, exc_info=True)
            continue
        if not renewed:
            return


@contextlib.asynccontextmanager
async def _task_run_heartbeat(run_id: int, *, lease_seconds: int | None = None, execution_token: str | None = None):
    stopped = asyncio.Event()
    task = asyncio.create_task(
        _maintain_task_run_heartbeat(run_id, stopped, lease_seconds=lease_seconds, execution_token=execution_token),
        name=f"task-run-heartbeat-{run_id}",
    )
    try:
        yield
    finally:
        stopped.set()
        await task


class TaskEnqueueError(RuntimeError):
    def __init__(self, run: ScheduledJobRun, message: str):
        super().__init__(message)
        self.run = run


@dataclass(frozen=True)
class ScheduledJobRunResult:
    job_id: int
    task_type: str
    status: str
    detail: str | None = None
    artifacts: dict[str, Any] | None = None


def _merge_run_artifacts(*results: ScheduledJobRunResult) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    for result in results:
        for key, value in (result.artifacts or {}).items():
            if isinstance(value, list):
                existing = merged.setdefault(key, [])
                if not isinstance(existing, list):
                    merged[key] = list(value)
                    continue
                for item in value:
                    if item not in existing:
                        existing.append(item)
            else:
                merged[key] = value
    return merged or None


def _scheduled_job_run_artifacts(job: ScheduledJob) -> dict[str, Any] | None:
    if job.task_type in MODEL_PIPELINE_SCHEDULED_TASK_TYPES:
        public_config = {
            key: value
            for key, value in (job.config or {}).items()
            if key not in {SCHEDULED_JOB_OWNER_CONFIG_KEY, "user_id"}
        }
        command = parse_model_pipeline_scheduled_config(job.task_type, public_config)
        job_spec = command.model_dump(mode="json")
        # `mode=json` gives immutable UTC-safe wire values; fingerprinting the
        # exact stored object detects tampering or accidental config mutation.
        return {
            "model_pipeline_command": job_spec,
            "model_pipeline_command_digest": model_fingerprint(job_spec),
            "model_pipeline_contract_version": job_spec["contract_version"],
        }
    if job.task_type in LICENSED_ODDS_SCHEDULED_TASK_TYPES:
        public_config = {
            key: value
            for key, value in (job.config or {}).items()
            if key not in {SCHEDULED_JOB_OWNER_CONFIG_KEY, "user_id"}
        }
        spec = parse_licensed_odds_scheduled_config(public_config)
        job_spec = spec.canonical_payload()
        return {
            "job_spec": job_spec,
            "job_spec_digest": model_fingerprint(job_spec),
            "licensed_odds_contract_version": job_spec["contract_version"],
        }
    if job.task_type not in {"soccerdata_http_ingest", "soccerdata_browser_ingest"}:
        return None
    public_config = {
        key: value
        for key, value in (job.config or {}).items()
        if key not in {SCHEDULED_JOB_OWNER_CONFIG_KEY, "user_id"}
    }
    if (
        public_config.get("page", 0) != 0
        or public_config.get("start_cursor") not in {None, 0}
        or "generation_key" in public_config
    ):
        raise ValueError("Scheduled soccerdata jobs must start from page zero")
    spec = SoccerdataIngestionSpec.from_config(public_config)
    if spec.task_type != job.task_type:
        raise ValueError("Soccerdata operation does not match the scheduled worker lane")
    return {
        "job_spec": spec.to_config(),
        "job_spec_digest": spec.spec_digest,
        "request_fingerprint": spec.request_fingerprint,
    }


def _soccerdata_spec_from_run(run: ScheduledJobRun) -> SoccerdataIngestionSpec:
    """Read and verify the immutable soccerdata request captured at enqueue time."""
    artifacts = run.artifacts or {}
    raw_spec = artifacts.get("job_spec")
    if not isinstance(raw_spec, dict):
        raise ValueError("soccerdata scheduled run is missing its immutable job_spec")
    spec = SoccerdataIngestionSpec.from_config(raw_spec)
    if spec.task_type != run.task_type:
        raise ValueError("soccerdata scheduled run job_spec does not match its worker lane")
    if artifacts.get("job_spec_digest") != spec.spec_digest:
        raise ValueError("soccerdata scheduled run job_spec digest mismatch")
    if artifacts.get("request_fingerprint") != spec.request_fingerprint:
        raise ValueError("soccerdata scheduled run request fingerprint mismatch")
    return spec


def _model_pipeline_command_from_run(run: ScheduledJobRun) -> Any:
    """Read a model command from its immutable enqueue snapshot, fail closed."""
    artifacts = run.artifacts or {}
    raw_command = artifacts.get("model_pipeline_command")
    if not isinstance(raw_command, dict):
        raise ValueError("model pipeline scheduled run is missing its immutable command")
    command = parse_model_pipeline_scheduled_config(run.task_type, raw_command)
    canonical_command = command.model_dump(mode="json")
    if raw_command != canonical_command:
        raise ValueError("model pipeline scheduled run command is not canonical")
    if artifacts.get("model_pipeline_command_digest") != model_fingerprint(canonical_command):
        raise ValueError("model pipeline scheduled run command digest mismatch")
    if artifacts.get("model_pipeline_contract_version") != canonical_command["contract_version"]:
        raise ValueError("model pipeline scheduled run contract version mismatch")
    return command


def _licensed_odds_spec_from_run(run: ScheduledJobRun) -> LicensedOddsJobSpecV1:
    """Load a canonical immutable provider-http command captured at enqueue."""
    artifacts = run.artifacts or {}
    raw_spec = artifacts.get("job_spec")
    if not isinstance(raw_spec, dict):
        raise ValueError("licensed odds scheduled run is missing its immutable job_spec")
    spec = parse_licensed_odds_scheduled_config(raw_spec)
    canonical_spec = spec.canonical_payload()
    if raw_spec != canonical_spec:
        raise ValueError("licensed odds scheduled run job_spec is not canonical")
    if artifacts.get("job_spec_digest") != model_fingerprint(canonical_spec):
        raise ValueError("licensed odds scheduled run job_spec digest mismatch")
    if artifacts.get("licensed_odds_contract_version") != canonical_spec["contract_version"]:
        raise ValueError("licensed odds scheduled run contract version mismatch")
    return spec


def _soccerdata_result_artifacts(result: SoccerdataIngestionResult) -> dict[str, Any]:
    artifacts: dict[str, Any] = {
        "ingestion_checkpoint_id": result.checkpoint_id,
        "ingestion_state": result.state,
        "record_count": result.record_count,
        "observation_count": result.observation_count,
        "replayed": result.replayed,
    }
    if result.dataset_id is not None:
        artifacts["dataset_ids"] = [result.dataset_id]
    if result.generation_id is not None:
        artifacts["provider_dataset_generation_ids"] = [result.generation_id]
        if result.state == "completed" and result.cursor is None:
            # Exact scalar consumed by TrainModelCommandV1.source_generation_id.
            artifacts["source_generation_id"] = result.generation_id
    if result.cursor is not None:
        artifacts["next_cursor"] = result.cursor
    return artifacts


async def _run_licensed_odds_job(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    spec: LicensedOddsJobSpecV1,
    execution_token: str | None,
) -> ScheduledJobRunResult:
    """Acquire then persist a licensed odds batch without a browser fallback.

    The acquisition service owns a short, clean quota transaction.  Accepted
    envelope rows are committed even when canonical match/bookmaker mapping is
    incomplete, so operators can repair identity data without reacquiring.
    """
    canary_fingerprint = model_fingerprint(
        {
            "contract": "licensed-odds-canary/v1",
            "scheduled_job_id": run.scheduled_job_id,
            "scheduled_job_run_id": run.id,
            "scope": spec.scope,
        }
    )
    bucket = canary_bucket(canary_fingerprint)
    if not included_in_canary(canary_fingerprint, spec.canary_stage_percent):
        return ScheduledJobRunResult(
            job_id=run.scheduled_job_id or 0,
            task_type=run.task_type,
            status="skipped",
            detail="licensed_odds_canary_excluded",
            artifacts={
                "licensed_odds": {
                    "contract_version": spec.contract_version,
                    "scope": spec.scope,
                    "canary_stage_percent": spec.canary_stage_percent,
                    "canary_bucket": bucket,
                    "canary_included": False,
                    "status": "skipped",
                    "reason_code": "canary_excluded",
                    "charged": False,
                    "record_count": 0,
                }
            },
        )

    # Close the scheduled-job read transaction before quota admission/egress.
    await db.commit()
    acquisition = await LicensedOddsService(settings).acquire_sportmonks_latest(
        db,
        scope=spec.scope,
        job_id=f"scheduled-job:{run.scheduled_job_id}",
        run_id=str(run.id),
        correlation_id=f"scheduled-job-run:{run.id}",
        execution_token=execution_token,
        scheduled_job_run_id=run.id,
    )
    telemetry = acquisition.telemetry
    artifacts: dict[str, Any] = {
        "licensed_odds": {
            "contract_version": spec.contract_version,
            "scope": spec.scope,
            "canary_stage_percent": spec.canary_stage_percent,
            "canary_bucket": bucket,
            "canary_included": True,
            "status": telemetry.status.value,
            "reason_code": telemetry.reason_code,
            "charged": telemetry.charged,
            "record_count": telemetry.record_count,
        }
    }
    if telemetry.status is LicensedOddsAcquisitionStatus.DENIED:
        return ScheduledJobRunResult(
            job_id=run.scheduled_job_id or 0,
            task_type=run.task_type,
            status="skipped",
            detail=f"licensed_odds_denied:{telemetry.reason_code}",
            artifacts=artifacts,
        )
    if telemetry.status is LicensedOddsAcquisitionStatus.FAILED:
        return ScheduledJobRunResult(
            job_id=run.scheduled_job_id or 0,
            task_type=run.task_type,
            status="failed",
            detail=f"licensed_odds_failed:{telemetry.reason_code}",
            artifacts=artifacts,
        )

    observation_ids: list[int] = []
    materialized = 0
    unmapped = 0
    for observation_id in acquisition.observation_ids:
        observation = await db.get(ProviderObservation, observation_id)
        if observation is None:
            unmapped += 1
            continue
        observation_ids.append(observation_id)
        try:
            await materialize_odds_observation(db, observation, bookmaker_mapping={})
        except OddsObservationMaterializationError:
            unmapped += 1
        else:
            materialized += 1
    if execution_token is not None:
        await assert_task_run_fence(db, run.id, execution_token)
    artifacts["provider_observation_ids"] = observation_ids
    artifacts["materialized_observation_count"] = materialized
    artifacts["unmapped_observation_count"] = unmapped
    status = "partial" if unmapped else "completed"
    return ScheduledJobRunResult(
        job_id=run.scheduled_job_id or 0,
        task_type=run.task_type,
        status=status,
        detail=(
            f"licensed_odds:{status}; records:{len(acquisition.observation_ids)}; "
            f"unmapped:{unmapped}; replayed:{str(acquisition.replayed).lower()}"
        ),
        artifacts=artifacts,
    )


async def _run_soccerdata_job(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    spec: SoccerdataIngestionSpec,
    batch: SoccerdataBatch,
    execution_token: str | None,
) -> ScheduledJobRunResult:
    """Persist a pre-fetched soccerdata batch with the terminal run fence."""

    async def fence() -> None:
        if execution_token is not None:
            await assert_task_run_fence(db, run.id, execution_token)

    result = await persist_soccerdata_batch(
        db,
        spec,
        batch,
        fence=fence if execution_token is not None else None,
        job_id=f"scheduled-job:{run.scheduled_job_id}",
        run_id=str(run.id),
        correlation_id=f"scheduled-job-run:{run.id}",
        scheduled_job_run_id=run.id,
        now=datetime.now(timezone.utc),
    )
    artifacts = _soccerdata_result_artifacts(result)
    replay = "; replayed" if result.replayed else ""
    detail = (
        f"soccerdata:{result.state}{replay}; checkpoint:{result.checkpoint_id}; "
        f"records:{result.record_count}; observations:{result.observation_count}"
    )
    # No rows is a durable non-error checkpoint, but must not be represented
    # as a completed data-producing run.
    return ScheduledJobRunResult(
        job_id=run.scheduled_job_id or 0,
        task_type=run.task_type,
        status="skipped" if result.state == "no_data" else "completed",
        detail=detail,
        artifacts=artifacts,
    )


async def _replay_scheduled_soccerdata_page(spec: SoccerdataIngestionSpec) -> SoccerdataIngestionResult | None:
    """Probe a checkpoint in an isolated short-lived session.

    The worker session retains the claimed run and job ORM identities.  A
    rollback on that session after a replay SELECT can expire those identities
    and later lazy-load during the fenced persistence path.  The replay probe
    is pure read-only work, so isolate and close it before bridge I/O instead.
    """
    async with async_session_factory() as replay_db:
        # Lightweight scheduler doubles used by legacy unit tests do not
        # expose the database read surface.
        if not hasattr(replay_db, "scalar"):
            return None
        replay = await replay_soccerdata_batch(replay_db, spec)
        # End the read transaction explicitly before returning.  This matters
        # for long cursor chains even though session close would also roll back.
        if getattr(replay_db, "in_transaction", lambda: False)():
            await replay_db.rollback()
        return replay


def _summarize_prediction_statuses(statuses: list[str]) -> str:
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return ", ".join(f"{status}:{count}" for status, count in sorted(counts.items()))


def _prediction_job_status(statuses: list[str]) -> str:
    if not statuses:
        return "skipped"

    truthy_success_statuses = {"completed", "deduped"}
    if all(status in truthy_success_statuses for status in statuses):
        return "completed"
    if all(status == "no_matches" for status in statuses):
        return "skipped"
    if any(status == "failed" for status in statuses):
        return "failed"
    return "partial"


def _scrape_task_run_status(job_status: str, artifacts: dict[str, Any] | None) -> str:
    report = (artifacts or {}).get("scrape_report")
    if job_status == "completed" and isinstance(report, dict) and report.get("health") == "degraded":
        return "partial"
    return job_status


def _scrape_job_artifacts(job: Any) -> dict[str, Any]:
    artifacts: dict[str, Any] = {"scrape_job_ids": [job.id]}
    output = getattr(job, "output", None)
    if not isinstance(output, str) or not output:
        return artifacts
    try:
        summary = json.loads(output)
    except (TypeError, ValueError):
        return artifacts
    if not isinstance(summary, dict):
        return artifacts

    dataset_id = summary.get("dataset_id")
    if dataset_id not in (None, ""):
        try:
            parsed_dataset_id = int(dataset_id)
        except (TypeError, ValueError):
            pass
        else:
            if parsed_dataset_id > 0:
                artifacts["dataset_ids"] = [parsed_dataset_id]

    report = summary.get("scrape_report")
    if isinstance(report, dict):
        artifacts["scrape_report"] = report
    failure = summary.get("failure")
    failure_kind = failure.get("kind") if isinstance(failure, dict) else None
    if failure_kind in RETRYABLE_FAILURE_KINDS | TERMINAL_FAILURE_KINDS:
        artifacts["failure_kind"] = failure_kind
    return artifacts


async def _apply_scrape_failure_retry(
    db: AsyncSession,
    run: ScheduledJobRun,
    *,
    artifacts: dict[str, Any] | None,
    execution_token: str | None,
    error: str,
) -> bool:
    safe_artifacts = artifacts or {}
    failure_kind = safe_artifacts.get("failure_kind")
    if not isinstance(failure_kind, str):
        return False
    if execution_token is None:
        return False
    changed = await requeue_task_run_failure(
        db,
        run,
        execution_token=execution_token,
        failure_kind=failure_kind,
        error=error,
    )
    if not changed:
        raise StaleTaskRunFenceError(f"Task run {run.id} lost its execution fence during scrape failure")
    run.artifacts = {**(run.artifacts or {}), **safe_artifacts}
    await db.flush()
    return True


def _worker_metrics_from_artifacts(artifacts: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract only bounded operational outcomes from a scrape report."""
    report = (artifacts or {}).get("scrape_report")
    if not isinstance(report, dict):
        return None
    raw_fallbacks = report.get("fallback_count", 1 if report.get("fallback_used") is True else 0)
    fallback_count = raw_fallbacks if isinstance(raw_fallbacks, int) and raw_fallbacks >= 0 else 0
    raw_freshness = str(report.get("freshness_status") or "unknown").strip().lower()
    freshness_status = raw_freshness if raw_freshness in {"fresh", "stale", "expired", "failed"} else "unknown"
    return {"fallback_count": fallback_count, "freshness_status": freshness_status}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _int_config(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if value in (None, ""):
        return default
    return int(value)


def _optional_int_config(config: dict[str, Any], key: str) -> int | None:
    value = config.get(key)
    if value in (None, ""):
        return None
    return int(value)


def _optional_int_list_config(config: dict[str, Any], key: str) -> list[int] | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list of integer ids")
    return [int(item) for item in value]


def _bool_config(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _dict_config(config: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = config.get(key)
    return dict(value) if isinstance(value, dict) else None


def _stamp_owner_if_missing(config: dict[str, Any], owner_id: int | None) -> dict[str, Any]:
    if owner_id is None:
        return config
    stamped = dict(config)
    stamped.setdefault(SCHEDULED_JOB_OWNER_CONFIG_KEY, owner_id)
    stamped.setdefault("user_id", owner_id)
    return stamped


async def _load_scheduled_job_owner(db: AsyncSession, config: dict[str, Any]) -> User | None:
    user_id = config.get(SCHEDULED_JOB_OWNER_CONFIG_KEY) or config.get("user_id")
    if not user_id:
        return None
    return await db.get(User, int(user_id))


def _parse_step(field: str, *, prefix: str = "*/") -> int | None:
    if not field.startswith(prefix):
        return None
    try:
        value = int(field.removeprefix(prefix))
    except ValueError:
        return None
    return value if value > 0 else None


def next_run_from_cron(cron_expression: str, *, after: datetime | None = None) -> datetime:
    """Return the next run for the simple cron patterns generated by the UI.

    Supported patterns:
    - 0 */N * * *  -> every N hours
    - 0 0 */N * *  -> every N days
    - 0 0 * * 1    -> weekly on Monday
    Invalid patterns are rejected rather than silently becoming an hourly job.
    """
    base = after or utcnow()
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    cron_expression = validate_scheduled_job_cron(cron_expression)
    fields = cron_expression.split()

    minute, hour, day_of_month, _month, day_of_week = fields

    if minute == "0" and (hours := _parse_step(hour)) is not None:
        return base + timedelta(hours=hours)

    if minute == "0" and hour == "0" and (days := _parse_step(day_of_month)) is not None:
        return base + timedelta(days=days)

    if minute == "0" and hour == "0" and day_of_month == "*" and day_of_week in {"1", "mon", "MON"}:
        days_until_monday = (7 - base.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_date = (base + timedelta(days=days_until_monday)).date()
        return datetime.combine(next_date, datetime.min.time(), tzinfo=timezone.utc)

    # validate_scheduled_job_cron keeps this unreachable. Keep an explicit
    # failure here so future grammar changes cannot create an unsafe fallback.
    raise ValueError(f"Unsupported cron expression: {cron_expression}")


def scheduled_job_due(job: ScheduledJob, *, now: datetime | None = None) -> bool:
    if not job.enabled:
        return False
    if job.next_run is None:
        return False
    current = now or utcnow()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    next_run = job.next_run if job.next_run.tzinfo else job.next_run.replace(tzinfo=timezone.utc)
    return next_run <= current


async def quarantine_invalid_scheduled_job(
    db: AsyncSession, job: ScheduledJob, *, error: ValueError, detected_at: datetime
) -> None:
    """Disable an invalid legacy schedule without rolling back healthy jobs."""
    config = dict(job.config or {})
    config[SCHEDULED_JOB_QUARANTINE_CONFIG_KEY] = {
        "code": "invalid_cron_expression",
        "detail": str(error),
        "detected_at": detected_at.isoformat(),
    }
    job.config = config
    job.enabled = False
    job.next_run = None
    await db.flush()
    logger.error("Quarantined scheduled job id=%s with invalid cron: %s", job.id, error)


def stamp_created_by(config: dict | None, user_id: int) -> dict:
    stamped = dict(config or {})
    # Client config is never authoritative for ownership.  Explicitly replace
    # both the legacy public field and the internal marker on every create.
    stamped.pop("user_id", None)
    stamped[SCHEDULED_JOB_OWNER_CONFIG_KEY] = user_id
    return stamped


async def initialize_next_run(db: AsyncSession, job: ScheduledJob, *, now: datetime | None = None) -> ScheduledJob:
    if job.next_run is None:
        job.next_run = next_run_from_cron(job.cron_expression, after=now or utcnow())
        await db.flush()
    return job


async def _run_scrape_job(db: AsyncSession, job: ScheduledJob) -> ScheduledJobRunResult:
    config = job.config or {}
    params = dict(config["params"]) if isinstance(config.get("params"), dict) else dict(config)
    owner_id = config.get(SCHEDULED_JOB_OWNER_CONFIG_KEY) or config.get("user_id")
    if owner_id is not None:
        params[SCHEDULED_JOB_OWNER_CONFIG_KEY] = int(owner_id)
    league = config.get("league") if isinstance(config.get("league"), str) else params.get("league")
    task_type = job.task_type or "scrape_odds"

    created = await create_scrape_job(db, task_type, league, params)
    executed = await execute_scrape_job(db, created.id)
    artifacts = _scrape_job_artifacts(executed)
    status = _scrape_task_run_status(executed.status or "failed", artifacts)
    if executed.status != "completed":
        detail_parts = [f"scrape_job:{created.id}", f"status:{executed.status}"]
        if getattr(executed, "error", None):
            detail_parts.append(f"error:{executed.error}")
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status=status,
            detail="; ".join(detail_parts),
            artifacts=artifacts,
        )
    return ScheduledJobRunResult(
        job_id=job.id,
        task_type=job.task_type,
        status=status,
        detail=f"scrape_job:{created.id}",
        artifacts=artifacts,
    )


async def _run_prediction_job(
    db: AsyncSession,
    job: ScheduledJob,
    *,
    config_override: dict[str, Any] | None = None,
) -> ScheduledJobRunResult:
    # Imported lazily to avoid importing API routes during module import.
    from app.api.v1.strategies import run_strategy

    config = dict(config_override or job.config or {})
    user = await _load_scheduled_job_owner(db, config)
    if user is None:
        return ScheduledJobRunResult(job_id=job.id, task_type=job.task_type, status="skipped", detail="missing_user_id")

    strategy_ids = [int(value) for value in config.get("strategy_ids") or []]
    if not strategy_ids:
        return ScheduledJobRunResult(
            job_id=job.id, task_type=job.task_type, status="skipped", detail="missing_strategy_ids"
        )

    filters_payload = config.get("filters") if isinstance(config.get("filters"), dict) else {}
    request = StrategyRunRequest(
        match_ids=[int(value) for value in config.get("match_ids") or []],
        dataset_id=_optional_int_config(config, "dataset_id"),
        markets=list(config.get("markets") or []),
        filters=StrategyRunFilters(**filters_payload) if filters_payload else None,
        autopredict=True,
        avoid_reprediction=bool(config.get("avoid_reprediction", True)),
    )

    strategy_statuses: list[str] = []
    strategy_details: list[str] = []
    prediction_run_ids: list[int] = []
    for strategy_id in strategy_ids:
        response = await run_strategy(strategy_id=strategy_id, body=request, db=db, user=user)
        strategy_statuses.append(response.status)
        strategy_details.append(f"{strategy_id}:{response.status}:{response.run_id}")
        if response.status in {"completed", "deduped"} and int(response.run_id or 0) > 0:
            prediction_run_ids.append(int(response.run_id))

    overall_status = _prediction_job_status(strategy_statuses)
    detail = f"summary[{_summarize_prediction_statuses(strategy_statuses)}]; " + ", ".join(strategy_details)
    artifacts = {"prediction_run_ids": prediction_run_ids}
    return ScheduledJobRunResult(
        job_id=job.id, task_type=job.task_type, status=overall_status, detail=detail, artifacts=artifacts
    )


def _prediction_run_id_for_ticket_generation(prediction_result: ScheduledJobRunResult) -> int | None:
    raw_run_ids = (prediction_result.artifacts or {}).get("prediction_run_ids") or []
    run_ids = [int(run_id) for run_id in raw_run_ids if int(run_id) > 0]
    unique_run_ids = sorted(set(run_ids))
    if len(unique_run_ids) == 1:
        return unique_run_ids[0]
    return None


def _scrape_dataset_id_for_prediction(scrape_result: ScheduledJobRunResult) -> int | None:
    raw_dataset_ids = (scrape_result.artifacts or {}).get("dataset_ids") or []
    if not isinstance(raw_dataset_ids, (list, tuple, set)):
        return None
    dataset_ids: list[int] = []
    for dataset_id in raw_dataset_ids:
        try:
            parsed_dataset_id = int(dataset_id)
        except (TypeError, ValueError):
            continue
        if parsed_dataset_id > 0:
            dataset_ids.append(parsed_dataset_id)
    unique_dataset_ids = sorted(set(dataset_ids))
    if len(unique_dataset_ids) == 1:
        return unique_dataset_ids[0]
    return None


async def _run_scrape_then_predict_job(db: AsyncSession, job: ScheduledJob) -> ScheduledJobRunResult:
    config = dict(job.config or {})
    owner_id = config.get(SCHEDULED_JOB_OWNER_CONFIG_KEY) or config.get("user_id")

    scrape_config = _dict_config(config, "scrape")
    prediction_config = _dict_config(config, "prediction")

    default_scrape_config = {
        "league": config.get("league"),
        "params": config.get("params") if isinstance(config.get("params"), dict) else dict(config),
    }
    selected_scrape_config = scrape_config or default_scrape_config

    scrape_job = type(
        "EmbeddedScrapeJob",
        (),
        {
            "id": job.id,
            "task_type": "scrape_odds",
            "config": {
                SCHEDULED_JOB_OWNER_CONFIG_KEY: owner_id,
                "league": selected_scrape_config.get("league"),
                "params": selected_scrape_config.get("params")
                if isinstance(selected_scrape_config.get("params"), dict)
                else selected_scrape_config,
            },
        },
    )()

    scrape_result = await _run_scrape_job(db, scrape_job)
    if scrape_result.status != "completed":
        return scrape_result

    scrape_dataset_id = _scrape_dataset_id_for_prediction(scrape_result)
    if scrape_dataset_id is None:
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="partial",
            detail=f"{scrape_result.detail}; predictions:missing_or_ambiguous_scrape_dataset_id",
            artifacts=scrape_result.artifacts,
        )

    merged_prediction_config = _stamp_owner_if_missing(prediction_config or config, owner_id)
    merged_prediction_config["dataset_id"] = scrape_dataset_id
    prediction_result = await _run_prediction_job(db, job, config_override=merged_prediction_config)
    if prediction_result.status != "completed":
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status=prediction_result.status,
            detail=f"{scrape_result.detail}; {prediction_result.detail}",
            artifacts=_merge_run_artifacts(scrape_result, prediction_result),
        )

    return ScheduledJobRunResult(
        job_id=job.id,
        task_type=job.task_type,
        status="completed",
        detail=f"{scrape_result.detail}; predictions:{prediction_result.detail}",
        artifacts=_merge_run_artifacts(scrape_result, prediction_result),
    )


async def _run_ticket_generation_job(
    db: AsyncSession,
    job: ScheduledJob,
    *,
    config_override: dict[str, Any] | None = None,
    scheduled_job_run_id: int | None = None,
) -> ScheduledJobRunResult:
    config = dict(config_override or job.config or {})
    user = await _load_scheduled_job_owner(db, config)
    if user is None:
        return ScheduledJobRunResult(job_id=job.id, task_type=job.task_type, status="skipped", detail="missing_user_id")

    bankroll_id = _optional_int_config(config, "bankroll_id")
    if bankroll_id is None:
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="skipped",
            detail="missing_bankroll_id",
        )

    market_types = list(config.get("market_types") or config.get("markets") or ["1x2"])
    ticket_generation_args: dict[str, Any] = {
        "db": db,
        "user_id": user.id,
        "bankroll_id": bankroll_id,
        "ticket_count": _int_config(config, "ticket_count", 1),
        "difficulty": str(config["difficulty"]) if config.get("difficulty") else None,
        "ticket_format": str(config["ticket_format"]) if config.get("ticket_format") else None,
        "accumulator_risk_acknowledged": bool(config.get("accumulator_risk_acknowledged", False)),
        "automated": True,
        "market_types": market_types,
        "min_odds": float(config.get("min_odds", 1.01) or 1.01),
        "max_odds": float(config.get("max_odds", 100.0) or 100.0),
        "run_id": _optional_int_config(config, "run_id"),
        "run_ids": _optional_int_list_config(config, "run_ids"),
        "prediction_ids": _optional_int_list_config(config, "prediction_ids"),
    }
    if scheduled_job_run_id is not None:
        ticket_generation_args["scheduled_job_run_id"] = scheduled_job_run_id
    try:
        batch, tickets = await generate_tickets(
            **ticket_generation_args,
        )
    except TicketRiskPolicyRequiredError:
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="skipped",
            detail="risk_policy_required",
        )
    except TicketGenerationError as exc:
        blockers = exc.report.get("risk_assessment", {}).get("blockers", [])
        blocker_codes = [item.get("code") for item in blockers if isinstance(item, dict) and item.get("code")]
        detail = ",".join(blocker_codes) if blocker_codes else str(exc)
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="skipped",
            detail=f"tickets_blocked:{detail}",
        )
    return ScheduledJobRunResult(
        job_id=job.id,
        task_type=job.task_type,
        status="completed",
        detail=f"ticket_batch:{batch.id}; tickets:{len(tickets)}",
        artifacts={
            "ticket_batch_ids": [int(batch.id)],
            "ticket_ids": [int(ticket.id) for ticket in tickets],
        },
    )


async def _run_prediction_then_ticket_job(
    db: AsyncSession, job: ScheduledJob, *, scheduled_job_run_id: int | None = None
) -> ScheduledJobRunResult:
    config = dict(job.config or {})
    owner_id = config.get(SCHEDULED_JOB_OWNER_CONFIG_KEY) or config.get("user_id")

    prediction_config = _stamp_owner_if_missing(_dict_config(config, "prediction") or config, owner_id)
    prediction_result = await _run_prediction_job(db, job, config_override=prediction_config)
    if prediction_result.status != "completed":
        return prediction_result

    prediction_run_id = _prediction_run_id_for_ticket_generation(prediction_result)
    if prediction_run_id is None:
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="partial",
            detail=f"predictions:{prediction_result.detail}; tickets:missing_or_ambiguous_prediction_run_id",
            artifacts=prediction_result.artifacts,
        )

    ticket_config = _stamp_owner_if_missing(_dict_config(config, "tickets") or config, owner_id)
    ticket_config["run_id"] = prediction_run_id
    ticket_kwargs: dict[str, Any] = {"config_override": ticket_config}
    if scheduled_job_run_id is not None:
        ticket_kwargs["scheduled_job_run_id"] = scheduled_job_run_id
    ticket_result = await _run_ticket_generation_job(db, job, **ticket_kwargs)
    if ticket_result.status != "completed":
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status=ticket_result.status,
            detail=f"predictions:{prediction_result.detail}; {ticket_result.detail}",
            artifacts=_merge_run_artifacts(prediction_result, ticket_result),
        )

    return ScheduledJobRunResult(
        job_id=job.id,
        task_type=job.task_type,
        status="completed",
        detail=f"predictions:{prediction_result.detail}; {ticket_result.detail}",
        artifacts=_merge_run_artifacts(prediction_result, ticket_result),
    )


async def _run_scrape_predict_tickets_job(
    db: AsyncSession, job: ScheduledJob, *, scheduled_job_run_id: int | None = None
) -> ScheduledJobRunResult:
    config = dict(job.config or {})
    owner_id = config.get(SCHEDULED_JOB_OWNER_CONFIG_KEY) or config.get("user_id")

    scrape_config = _dict_config(config, "scrape")
    prediction_config = _dict_config(config, "prediction")
    ticket_config = _dict_config(config, "tickets")

    default_scrape_config = {
        "league": config.get("league"),
        "params": config.get("params") if isinstance(config.get("params"), dict) else dict(config),
    }
    selected_scrape_config = scrape_config or default_scrape_config
    scrape_job = type(
        "EmbeddedScrapeJob",
        (),
        {
            "id": job.id,
            "task_type": "scrape_odds",
            "config": {
                SCHEDULED_JOB_OWNER_CONFIG_KEY: owner_id,
                "league": selected_scrape_config.get("league"),
                "params": selected_scrape_config.get("params")
                if isinstance(selected_scrape_config.get("params"), dict)
                else selected_scrape_config,
            },
        },
    )()

    scrape_result = await _run_scrape_job(db, scrape_job)
    if scrape_result.status != "completed":
        return scrape_result

    scrape_dataset_id = _scrape_dataset_id_for_prediction(scrape_result)
    if scrape_dataset_id is None:
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="partial",
            detail=f"{scrape_result.detail}; predictions:missing_or_ambiguous_scrape_dataset_id",
            artifacts=scrape_result.artifacts,
        )

    merged_prediction_config = _stamp_owner_if_missing(prediction_config or config, owner_id)
    merged_prediction_config["dataset_id"] = scrape_dataset_id
    prediction_result = await _run_prediction_job(db, job, config_override=merged_prediction_config)
    if prediction_result.status != "completed":
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status=prediction_result.status,
            detail=f"{scrape_result.detail}; predictions:{prediction_result.detail}",
            artifacts=_merge_run_artifacts(scrape_result, prediction_result),
        )

    prediction_run_id = _prediction_run_id_for_ticket_generation(prediction_result)
    if prediction_run_id is None:
        detail = (
            f"{scrape_result.detail}; predictions:{prediction_result.detail}; "
            "tickets:missing_or_ambiguous_prediction_run_id"
        )
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="partial",
            detail=detail,
            artifacts=_merge_run_artifacts(scrape_result, prediction_result),
        )

    merged_ticket_config = _stamp_owner_if_missing(ticket_config or config, owner_id)
    merged_ticket_config["run_id"] = prediction_run_id
    ticket_kwargs: dict[str, Any] = {"config_override": merged_ticket_config}
    if scheduled_job_run_id is not None:
        ticket_kwargs["scheduled_job_run_id"] = scheduled_job_run_id
    ticket_result = await _run_ticket_generation_job(db, job, **ticket_kwargs)
    if ticket_result.status != "completed":
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status=ticket_result.status,
            detail=f"{scrape_result.detail}; predictions:{prediction_result.detail}; {ticket_result.detail}",
            artifacts=_merge_run_artifacts(scrape_result, prediction_result, ticket_result),
        )

    return ScheduledJobRunResult(
        job_id=job.id,
        task_type=job.task_type,
        status="completed",
        detail=f"{scrape_result.detail}; predictions:{prediction_result.detail}; {ticket_result.detail}",
        artifacts=_merge_run_artifacts(scrape_result, prediction_result, ticket_result),
    )


async def _run_world_cup_pipeline_job(db: AsyncSession, job: ScheduledJob) -> ScheduledJobRunResult:
    from app.services.world_cup_pipeline import run_world_cup_pipeline

    config = dict(job.config or {})
    user = await _load_scheduled_job_owner(db, config)
    if user is None:
        return ScheduledJobRunResult(job_id=job.id, task_type=job.task_type, status="skipped", detail="missing_user_id")

    result = await run_world_cup_pipeline(
        db,
        user_id=user.id,
        parent_job_id=None,
        future_days=_int_config(config, "future_days", 7),
        history_years=_int_config(config, "history_years", 10),
        all_markets=_bool_config(config, "all_markets", True),
        odds_history=_bool_config(config, "odds_history", True),
        max_historic_pages=_optional_int_config(config, "max_historic_pages"),
        max_historic_seasons=_optional_int_config(config, "max_historic_seasons"),
        upcoming_timeout_seconds=_optional_int_config(config, "upcoming_timeout_seconds"),
        historic_timeout_seconds=_optional_int_config(config, "historic_timeout_seconds"),
        scraper_engine=str(config.get("scraper_engine") or "playwright"),
        ticket_count=_int_config(config, "ticket_count", 10),
        ticket_stake=float(config.get("ticket_stake", 10.0) or 10.0),
        create_tickets=_bool_config(config, "create_tickets", True),
        allow_experimental_tickets=_bool_config(config, "allow_experimental_tickets", False),
        training_limit=_int_config(config, "training_limit", 240),
        target_date=config.get("target_date"),
        target_date_from=config.get("target_date_from"),
        target_date_to=config.get("target_date_to"),
    )
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    detail = (
        f"scrape_jobs:{summary.get('completed_scrape_jobs', 0)}/{summary.get('scrape_jobs', 0)}, "
        f"prediction_runs:{summary.get('completed_prediction_runs', 0) + summary.get('partial_prediction_runs', 0)}/"
        f"{summary.get('prediction_runs', 0)}, "
        f"tickets:{summary.get('created_tickets', 0)}"
    )
    return ScheduledJobRunResult(job_id=job.id, task_type=job.task_type, status="completed", detail=detail)


async def _run_verification_and_settlement_job(db: AsyncSession, job: ScheduledJob) -> ScheduledJobRunResult:
    config = dict(job.config or {})
    user = await _load_scheduled_job_owner(db, config)
    if user is None:
        return ScheduledJobRunResult(job_id=job.id, task_type=job.task_type, status="skipped", detail="missing_user_id")

    detail_parts: list[str] = []

    if _bool_config(config, "verify_predictions", True):
        run_id = _optional_int_config(config, "run_id")
        stmt = (
            select(ModelPrediction)
            .join(PredictionRun, ModelPrediction.run_id == PredictionRun.id)
            .where(PredictionRun.user_id == user.id)
            .order_by(ModelPrediction.created_at.desc())
            .limit(_int_config(config, "max_results", 250))
        )
        if run_id is not None:
            stmt = stmt.where(ModelPrediction.run_id == run_id)

        result = await db.execute(stmt)
        predictions = result.scalars().all()
        counts = {"won": 0, "lost": 0, "pending": 0, "void": 0, "unsupported": 0}
        for prediction in predictions:
            evaluation = evaluate_model_prediction(prediction)
            counts[evaluation.status] = counts.get(evaluation.status, 0) + 1

        detail_parts.append(
            "predictions="
            f"{len(predictions)} checked, "
            f"{counts['won']} won, "
            f"{counts['lost']} lost, "
            f"{counts['pending']} pending, "
            f"{counts['void']} void, "
            f"{counts['unsupported']} unsupported"
        )

    if _bool_config(config, "settle_tickets", True):
        summary = await settle_due_tickets(
            db,
            user_id=user.id,
            unsupported_policy=str(config.get("unsupported_policy") or "pending"),
            limit=_int_config(config, "ticket_limit", _int_config(config, "limit", 100)),
        )
        detail_parts.append(
            "tickets="
            f"{summary.checked_tickets} checked, "
            f"{summary.settled_tickets} settled, "
            f"{summary.pending_tickets} pending, "
            f"{summary.updated_legs} legs_updated"
        )

    if not detail_parts:
        return ScheduledJobRunResult(job_id=job.id, task_type=job.task_type, status="skipped", detail="nothing_enabled")

    return ScheduledJobRunResult(
        job_id=job.id,
        task_type=job.task_type,
        status="completed",
        detail="; ".join(detail_parts),
    )


async def _run_model_pipeline_job(
    db: AsyncSession,
    job: ScheduledJob,
    *,
    command: Any,
    fence: Any | None = None,
) -> ScheduledJobRunResult:
    """Run only a strict, versioned command on the isolated model-cpu lane."""
    from app.services.model_pipeline import backtest_model, predict_model, train_model

    task_type = (job.task_type or "").lower()
    config = dict(job.config or {})
    owner = await _load_scheduled_job_owner(db, config)
    user_id = owner.id if owner is not None else None

    if task_type == "train_model":
        artifact = await train_model(db, command, **({"fence": fence} if fence is not None else {}))
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail=f"model_artifact:{artifact.id}",
            artifacts={
                "model_artifact_ids": [artifact.id],
                "model_artifact_key": artifact.artifact_key,
                "source_generation_id": artifact.source_generation_id,
            },
        )
    if task_type == "backtest_model":
        evaluation = await backtest_model(
            db, command, user_id=user_id, **({"fence": fence} if fence is not None else {})
        )
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail=f"model_evaluation:{evaluation.id}",
            artifacts={
                "model_evaluation_ids": [evaluation.id],
                "model_artifact_ids": [command.model_artifact_id],
                "source_generation_id": command.source_generation_id,
            },
        )
    if task_type == "predict_model":
        prediction_run = await predict_model(
            db, command, user_id=user_id, **({"fence": fence} if fence is not None else {})
        )
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail=f"prediction_run:{prediction_run.id}",
            artifacts={
                "prediction_run_ids": [prediction_run.id],
                "model_artifact_ids": [command.model_artifact_id],
                "source_generation_id": command.source_generation_id,
            },
        )
    raise ValueError(f"Unsupported model pipeline task type: {job.task_type}")


async def dispatch_scheduled_job(
    db: AsyncSession,
    job: ScheduledJob,
    *,
    scheduled_job_run_id: int | None = None,
    model_pipeline_command: Any | None = None,
    model_pipeline_fence: Any | None = None,
) -> ScheduledJobRunResult:
    task_type = (job.task_type or "").lower()
    if task_type not in SCHEDULED_JOB_TASK_TYPES:
        return ScheduledJobRunResult(
            job_id=job.id, task_type=job.task_type, status="skipped", detail="unsupported_task_type"
        )
    # Exact model task types must dispatch before the legacy substring router.
    # The worker supplies an immutable delivery snapshot; direct service users
    # are still parsed through the same strict contract.
    if task_type in MODEL_PIPELINE_SCHEDULED_TASK_TYPES:
        command = model_pipeline_command or parse_model_pipeline_scheduled_config(task_type, dict(job.config or {}))
        return await _run_model_pipeline_job(db, job, command=command, fence=model_pipeline_fence)
    # Keep the explicit licensed operation ahead of the legacy ``odds``
    # substring branch. Real execution requires the run-bound immutable spec.
    if task_type == "fetch_latest_odds":
        return ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="skipped",
            detail="licensed_odds_requires_immutable_run_spec",
        )
    if "world_cup_pipeline" in task_type:
        return await _run_world_cup_pipeline_job(db, job)
    if (
        "scrape" in task_type
        and any(token in task_type for token in ("predict", "prediction", "strategy"))
        and any(token in task_type for token in ("ticket", "slip", "batch"))
    ):
        return await _run_scrape_predict_tickets_job(db, job, scheduled_job_run_id=scheduled_job_run_id)
    if "scrape" in task_type and any(
        token in task_type for token in ("predict", "prediction", "strategy", "chain", "pipeline")
    ):
        return await _run_scrape_then_predict_job(db, job)
    if any(token in task_type for token in ("predict", "prediction", "strategy")) and any(
        token in task_type for token in ("ticket", "slip", "batch")
    ):
        return await _run_prediction_then_ticket_job(db, job, scheduled_job_run_id=scheduled_job_run_id)
    if any(token in task_type for token in ("settle", "settlement", "verify", "verification")):
        return await _run_verification_and_settlement_job(db, job)
    if any(token in task_type for token in ("ticket", "slip", "batch")):
        return await _run_ticket_generation_job(db, job, scheduled_job_run_id=scheduled_job_run_id)
    if any(token in task_type for token in ("scrape", "odds")):
        return await _run_scrape_job(db, job)
    if any(token in task_type for token in ("predict", "prediction", "strategy")):
        return await _run_prediction_job(db, job)
    return ScheduledJobRunResult(
        job_id=job.id, task_type=job.task_type, status="skipped", detail="unsupported_task_type"
    )


def taskiq_queue_enabled() -> bool:
    return settings.task_queue_backend == "taskiq"


async def _send_taskiq_run(run: ScheduledJobRun, *, task_name: str) -> str | None:
    if run.queue_contract_version not in {WORKER_LANE_CONTRACT_VERSION, LEGACY_WORKER_CONTRACT_VERSION}:
        raise ValueError(f"Unsupported Taskiq queue contract: {run.queue_contract_version}")
    if run.queue_contract_version == LEGACY_WORKER_CONTRACT_VERSION and run.queue_lane != "control":
        raise ValueError("legacy-control/v0 Taskiq messages may only use the control lane")
    if not is_worker_lane_enabled(settings, run.queue_lane):
        raise WorkerLaneDisabledError(f"Worker lane {run.queue_lane!r} is disabled")
    queue_name = queue_name_for_lane(settings, run.queue_lane)
    if task_name == "scheduled_job":
        from app.tasks.jobs import execute_scheduled_job_run_task

        kicker = execute_scheduled_job_run_task.kicker()
    elif task_name == "scrape_job":
        from app.tasks.jobs import execute_scrape_job_task

        kicker = execute_scrape_job_task.kicker()
    elif task_name == "world_cup_pipeline":
        from app.tasks.jobs import execute_world_cup_pipeline_task

        kicker = execute_world_cup_pipeline_task.kicker()
    else:
        raise ValueError(f"Unsupported Taskiq task name: {task_name}")
    # Redis carries no business payload besides the durable run ID. `queue_name`
    # is a transport label used by taskiq-redis dynamic queue routing.
    task = await kicker.with_labels(queue_name=queue_name).kiq(run.id)
    return getattr(task, "task_id", None)


async def _send_inprocess_run(run: ScheduledJobRun, *, task_name: str) -> str:
    task = asyncio.create_task(_execute_inprocess_task(run.id, task_name=task_name), name=f"task-run-{run.id}")
    _inprocess_tasks.add(task)
    task.add_done_callback(_inprocess_tasks.discard)
    return f"inprocess:{run.id}"


async def _execute_inprocess_task(run_id: int, *, task_name: str) -> ScheduledJobRun:
    """Serialize browser-heavy scrape runs when development uses in-process delivery."""
    if task_name != "scrape_job":
        return await execute_task_run(run_id)

    global _inprocess_scrape_semaphore
    limit = settings.inprocess_scrape_max_concurrency
    if _inprocess_scrape_semaphore is None or _inprocess_scrape_semaphore[0] != limit:
        _inprocess_scrape_semaphore = (limit, asyncio.Semaphore(limit))

    async with _inprocess_scrape_semaphore[1]:
        return await execute_task_run(run_id)


async def _send_outbox_run(run: ScheduledJobRun, outbox: TaskOutbox) -> str | None:
    if outbox.transport == "taskiq":
        return await _send_taskiq_run(run, task_name=outbox.task_name)
    if outbox.transport == "inprocess":
        return await _send_inprocess_run(run, task_name=outbox.task_name)
    raise ValueError(f"Unsupported task transport: {outbox.transport}")


async def _publish_outbox_entry(db: AsyncSession, outbox: TaskOutbox) -> ScheduledJobRun:
    run = await db.get(ScheduledJobRun, outbox.run_id)
    if run is None:
        raise LookupError(f"Task outbox {outbox.id} references missing run {outbox.run_id}")
    if outbox.status == "published":
        return run
    outbox.attempts += 1
    try:
        transport_task_id = await _send_outbox_run(run, outbox)
    except Exception as exc:
        await mark_outbox_publish_failed(db, outbox, run, error=str(exc))
        await db.commit()
        raise TaskEnqueueError(run, str(exc)) from exc
    await mark_outbox_published(db, outbox, run, transport_task_id=transport_task_id)
    await db.commit()
    return run


async def _replay_stale_published_outbox_entry(
    db: AsyncSession,
    outbox: TaskOutbox,
) -> ScheduledJobRun | None:
    run = await db.get(ScheduledJobRun, outbox.run_id)
    if run is None:
        raise LookupError(f"Task outbox {outbox.id} references missing run {outbox.run_id}")
    if run.status != "queued" or run.started_at is not None or run.finished_at is not None:
        return run
    predecessor_result = await db.execute(
        select(ScheduledJobRun.id)
        .join(TaskOutbox, TaskOutbox.run_id == ScheduledJobRun.id)
        .where(
            TaskOutbox.id < outbox.id,
            TaskOutbox.transport == "taskiq",
            TaskOutbox.status == "published",
            TaskOutbox.queue_lane == outbox.queue_lane,
            TaskOutbox.queue_contract_version == outbox.queue_contract_version,
            ScheduledJobRun.transport == "taskiq",
            ScheduledJobRun.status.in_(("queued", "running")),
            ScheduledJobRun.finished_at.is_(None),
        )
        .limit(1)
    )
    if predecessor_result.scalar_one_or_none() is not None:
        # A published Taskiq message can legitimately remain unclaimed while
        # the single conservative worker is processing an earlier long-running
        # scrape. Do not replay or exhaust later queue entries as though their
        # delivery had been lost.
        return run
    if outbox.attempts >= outbox.max_attempts:
        outbox.status = "failed"
        outbox.last_error = "task delivery remained unconfirmed after the replay limit"
        await finish_task_run(
            db,
            run,
            status="timed_out",
            detail="task_delivery_unconfirmed",
            error=outbox.last_error,
        )
        await db.commit()
        return None

    outbox.status = "pending"
    outbox.available_at = utcnow()
    outbox.last_error = "task delivery unconfirmed; replaying the queued run"
    previous_task_id = outbox.transport_task_id
    replayed = await _publish_outbox_entry(db, outbox)
    logger.warning(
        "Replayed stale Taskiq outbox id=%s run_id=%s attempt=%s old_task_id=%s new_task_id=%s",
        outbox.id,
        run.id,
        outbox.attempts,
        previous_task_id,
        outbox.transport_task_id,
    )
    return replayed


async def requeue_expired_task_run_leases(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> list[ScheduledJobRun]:
    """Durably recover lost workers before outbox publication/replay.

    This changes execution state, not outbox publication attempts.  A later
    reconcile publishes the same run ID, while claim fencing rejects any old
    worker token.
    """
    current = now or utcnow()
    for lane in WorkerLane:
        await acquire_lane_advisory_lock(db, lane)
    stmt = (
        select(ScheduledJobRun.id)
        .where(
            ScheduledJobRun.status == "running",
            ScheduledJobRun.queue_contract_version == WORKER_LANE_CONTRACT_VERSION,
            ScheduledJobRun.lease_expires_at.is_not(None),
            ScheduledJobRun.lease_expires_at <= current,
        )
        .order_by(ScheduledJobRun.lease_expires_at.asc(), ScheduledJobRun.id.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    recovered: list[ScheduledJobRun] = []
    for candidate in result.scalars().all():
        run_id = candidate.id if hasattr(candidate, "id") else int(candidate)
        # Canonical lock order is outbox -> run, matching publication/replay.
        outbox_result = await db.execute(select(TaskOutbox).where(TaskOutbox.run_id == run_id).with_for_update())
        outbox = outbox_result.scalar_one_or_none()
        if outbox is None:
            raise TaskOutboxContractError(f"Task run {run_id} has no durable outbox for lease recovery")
        run_result = await db.execute(
            select(ScheduledJobRun)
            .where(
                ScheduledJobRun.id == run_id,
                ScheduledJobRun.status == "running",
                ScheduledJobRun.queue_contract_version == WORKER_LANE_CONTRACT_VERSION,
                ScheduledJobRun.lease_expires_at.is_not(None),
                ScheduledJobRun.lease_expires_at <= current,
            )
            .with_for_update()
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            continue
        if outbox.queue_lane != run.queue_lane or outbox.queue_contract_version != run.queue_contract_version:
            raise TaskOutboxContractError(f"Task outbox {outbox.id} lane contract does not match run {run.id}")
        if run.attempt >= run.max_attempts:
            await finish_task_run(
                db,
                run,
                status="timed_out",
                detail="lease_retry_limit_exhausted",
                error="task lease expired and retry limit was exhausted",
                failure_kind="lease_expired",
                retry_disposition="terminal",
                execution_token=_run_execution_token(run),
            )
            recovered.append(run)
            continue
        retry_at = next_task_retry_at(run, "lease_expired", now=current)
        run.status = "queued"
        run.next_attempt_at = retry_at
        run.started_at = None
        run.finished_at = None
        run.duration_ms = None
        run.queue_wait_ms = None
        run.lease_expires_at = None
        run.heartbeat_at = current
        run.execution_token = None
        run.error = "task lease expired; queued for durable recovery"
        run.failure_kind = "lease_expired"
        run.retry_disposition = "retryable"
        outbox.delivery_generation += 1
        outbox.attempts = 0
        outbox.status = "pending"
        outbox.available_at = retry_at
        outbox.last_error = "execution lease expired; awaiting durable republish"
        recovered.append(run)
    await db.flush()
    return recovered


async def reconcile_task_outbox(db: AsyncSession, *, limit: int = 100) -> list[ScheduledJobRun]:
    """Retry pending and stale published tasks while the durable run is still unclaimed."""
    now = utcnow()
    pending_stmt = (
        select(TaskOutbox)
        .where(TaskOutbox.status == "pending", TaskOutbox.available_at <= now)
        .order_by(TaskOutbox.available_at.asc(), TaskOutbox.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    pending_result = await db.execute(pending_stmt)
    outbox_entries = list(pending_result.scalars().all())
    published: list[ScheduledJobRun] = []
    for outbox in outbox_entries:
        try:
            published.append(await _publish_outbox_entry(db, outbox))
        except TaskEnqueueError:
            continue

    remaining = max(0, limit - len(outbox_entries))
    if remaining == 0:
        return published

    stale_cutoff = now - timedelta(seconds=settings.task_publish_replay_grace_seconds)
    stale_stmt = (
        select(TaskOutbox)
        .join(ScheduledJobRun, ScheduledJobRun.id == TaskOutbox.run_id)
        .where(
            TaskOutbox.status == "published",
            TaskOutbox.transport == "taskiq",
            TaskOutbox.published_at.is_not(None),
            TaskOutbox.published_at <= stale_cutoff,
            ScheduledJobRun.transport == "taskiq",
            ScheduledJobRun.status == "queued",
            ScheduledJobRun.started_at.is_(None),
            ScheduledJobRun.finished_at.is_(None),
            ScheduledJobRun.lease_expires_at.is_(None),
            (ScheduledJobRun.next_attempt_at.is_(None) | (ScheduledJobRun.next_attempt_at <= now)),
        )
        .order_by(TaskOutbox.published_at.asc(), TaskOutbox.id.asc())
        .limit(remaining)
        .with_for_update(skip_locked=True)
    )
    stale_result = await db.execute(stale_stmt)
    for outbox in stale_result.scalars().all():
        try:
            replayed = await _replay_stale_published_outbox_entry(db, outbox)
        except TaskEnqueueError:
            continue
        if replayed is not None:
            published.append(replayed)
    return published


async def _enqueue_taskiq_run_after_commit(
    db: AsyncSession, run: ScheduledJobRun, *, task_name: str
) -> ScheduledJobRun:
    """Compatibility wrapper for callers transitioning to the transactional outbox."""
    run.transport = "taskiq"
    outbox = await create_task_outbox(db, run, task_name=task_name, transport="taskiq", max_attempts=1)
    await db.commit()
    return await _publish_outbox_entry(db, outbox)


async def _enqueue_run_after_commit(db: AsyncSession, run: ScheduledJobRun, *, task_name: str) -> ScheduledJobRun:
    """Write run and outbox atomically, then publish only after their transaction commits."""
    outbox = await create_task_outbox(db, run, task_name=task_name, transport=run.transport)
    await db.commit()
    return await _publish_outbox_entry(db, outbox)


async def _publish_committed_taskiq_run(db: AsyncSession, run: ScheduledJobRun, *, task_name: str) -> ScheduledJobRun:
    """Compatibility wrapper used by older callers/tests."""
    outbox = await create_task_outbox(db, run, task_name=task_name, transport="taskiq", max_attempts=1)
    await db.commit()
    try:
        return await _publish_outbox_entry(db, outbox)
    except TaskEnqueueError:
        if run.scheduled_job_id is not None and run.due_at is not None:
            job = await db.get(ScheduledJob, run.scheduled_job_id)
            if job is not None:
                job.next_run = run.due_at
                await db.commit()
        return run


async def _recover_execution_exception(
    db: AsyncSession,
    *,
    run_id: int,
    execution_token: str | None,
    exc: Exception,
) -> ScheduledJobRun:
    """Rollback caller writes, then terminalize or requeue in a clean transaction."""
    await db.rollback()
    run = await db.get(ScheduledJobRun, run_id)
    if run is None:
        raise LookupError(f"Task run {run_id} not found after rollback") from exc
    failure_kind = classify_execution_failure(exc)
    if execution_token is not None:
        changed = await requeue_task_run_failure(
            db,
            run,
            execution_token=execution_token,
            failure_kind=failure_kind,
            error=str(exc),
        )
        if changed:
            await db.commit()
            return run
        await db.rollback()
        return run
    await finish_task_run(
        db,
        run,
        status="failed",
        detail=str(exc),
        error=str(exc),
        failure_kind=failure_kind,
        execution_token=None,
    )
    await db.commit()
    return run


async def execute_scheduled_job_run(run_id: int) -> ScheduledJobRun:
    async with async_session_factory() as db:
        existing_run = await db.get(ScheduledJobRun, run_id)
        lease_seconds = _task_run_lease_seconds(existing_run) if existing_run is not None else None
        run = await claim_queued_task_run(db, run_id, lease_seconds=lease_seconds)
        if run is None:
            if existing_run is None:
                raise LookupError(f"Scheduled job run {run_id} not found")
            return existing_run
        await db.commit()
        if run.scheduled_job_id is None:
            await finish_task_run(
                db,
                run,
                status="failed",
                detail="scheduled_job_missing",
                error=f"Scheduled job run {run_id} is not attached to a scheduled job",
                execution_token=_run_execution_token(run),
            )
            await db.commit()
            return run
        job = await db.get(ScheduledJob, run.scheduled_job_id)
        if job is None:
            await finish_task_run(
                db,
                run,
                status="failed",
                detail="scheduled_job_missing",
                error="Scheduled job not found",
                execution_token=_run_execution_token(run),
            )
            await db.commit()
            return run

        execution_token = _run_execution_token(run)
        try:
            soccerdata_spec: SoccerdataIngestionSpec | None = None
            soccerdata_batch: SoccerdataBatch | None = None
            model_pipeline_command: Any | None = None
            licensed_odds_spec: LicensedOddsJobSpecV1 | None = None
            if run.task_type in {"soccerdata_http_ingest", "soccerdata_browser_ingest"}:
                # The enqueue snapshot is authoritative. Do not allow edits to
                # ScheduledJob.config after delivery to alter this execution.
                soccerdata_spec = _soccerdata_spec_from_run(run)
                authorize_soccerdata_ingestion(soccerdata_spec)
                # `db.get()` above opened a read transaction. Commit it before
                # crossing the external bridge boundary; persistence happens
                # later with the task-run fence in one new transaction.
                await db.commit()
            elif run.task_type in MODEL_PIPELINE_SCHEDULED_TASK_TYPES:
                # The durable delivery snapshot, not mutable ScheduledJob.config,
                # is authoritative for every model-cpu execution.
                model_pipeline_command = _model_pipeline_command_from_run(run)
            elif run.task_type in LICENSED_ODDS_SCHEDULED_TASK_TYPES:
                licensed_odds_spec = _licensed_odds_spec_from_run(run)
                # Acquiring uses the clean worker session only after this
                # initial scheduled-job lookup transaction is closed.
                await db.commit()
            async with _task_run_heartbeat(
                run.id,
                lease_seconds=lease_seconds,
                **({"execution_token": execution_token} if execution_token is not None else {}),
            ):
                if licensed_odds_spec is not None:
                    result = await _run_licensed_odds_job(
                        db,
                        run,
                        spec=licensed_odds_spec,
                        execution_token=execution_token,
                    )
                elif soccerdata_spec is not None:
                    # Heartbeat the lease during the external fetch while the
                    # worker session itself remains outside a DB transaction.
                    page_spec = soccerdata_spec
                    page_results: list[ScheduledJobRunResult] = []
                    while True:
                        # Policy is deliberately repeated for every page before
                        # crossing the external boundary; completed pages replay
                        # from their checkpoint without a bridge fetch.
                        authorize_soccerdata_ingestion(page_spec)
                        replayed_page = await _replay_scheduled_soccerdata_page(page_spec)
                        if replayed_page is not None:
                            page_result = ScheduledJobRunResult(
                                job_id=run.scheduled_job_id or 0,
                                task_type=run.task_type,
                                status="skipped" if replayed_page.state == "no_data" else "completed",
                                detail=f"soccerdata:{replayed_page.state}; replayed",
                                artifacts=_soccerdata_result_artifacts(replayed_page),
                            )
                        else:
                            # The dedicated replay session is already closed;
                            # the worker session still owns stable run/job ORM
                            # identities and remains transaction-free here.
                            try:
                                soccerdata_batch = await fetch_soccerdata_batch(page_spec)
                            except BridgeError as exc:
                                if exc.failure_kind in RETRYABLE_FAILURE_KINDS:
                                    raise TransientTaskRunError(exc.failure_kind, str(exc)) from exc
                                raise
                            page_result = await _run_soccerdata_job(
                                db, run, spec=page_spec, batch=soccerdata_batch, execution_token=execution_token
                            )
                        page_results.append(page_result)
                        await db.commit()  # each staged page and checkpoint is durable before the next fetch
                        page_artifacts = page_result.artifacts or {}
                        cursor = page_artifacts.get("next_cursor")
                        if not cursor:
                            result = page_result
                            break
                        page_spec = replace(
                            page_spec,
                            page=cursor["page"],
                            start_cursor=cursor["start_cursor"],
                            generation_key=cursor["generation_key"],
                        )
                    if len(page_results) > 1:
                        artifact_rows = [item.artifacts or {} for item in page_results]
                        dataset_ids = [
                            artifacts["dataset_ids"][0] for artifacts in artifact_rows if artifacts.get("dataset_ids")
                        ]
                        total_records = sum(int(artifacts.get("record_count") or 0) for artifacts in artifact_rows)
                        total_observations = sum(
                            int(artifacts.get("observation_count") or 0) for artifacts in artifact_rows
                        )
                        ingestion_state = "completed" if total_records else "no_data"
                        generation_ids = list(
                            dict.fromkeys(
                                generation_id
                                for artifacts in artifact_rows
                                for generation_id in artifacts.get("provider_dataset_generation_ids", [])
                            )
                        )
                        aggregate_artifacts = {
                            **(result.artifacts or {}),
                            "dataset_ids": dataset_ids,
                            "checkpoint_ids": [artifacts["ingestion_checkpoint_id"] for artifacts in artifact_rows],
                            "ingestion_state": ingestion_state,
                            "record_count": total_records,
                            "observation_count": total_observations,
                            "page_count": len(page_results),
                            "replayed": all(bool(artifacts.get("replayed")) for artifacts in artifact_rows),
                        }
                        if generation_ids:
                            aggregate_artifacts["provider_dataset_generation_ids"] = generation_ids
                        if total_records and len(generation_ids) == 1:
                            # A terminal empty continuation can still publish
                            # the data-bearing generation built by earlier pages.
                            aggregate_artifacts["source_generation_id"] = generation_ids[0]
                        result = ScheduledJobRunResult(
                            job_id=run.scheduled_job_id or 0,
                            task_type=run.task_type,
                            status="completed" if total_records else "skipped",
                            detail=(
                                f"soccerdata:{ingestion_state}; pages:{len(page_results)}; "
                                f"records:{total_records}; observations:{total_observations}"
                            ),
                            artifacts=aggregate_artifacts,
                        )
                else:

                    async def model_fence() -> None:
                        if execution_token is not None:
                            await assert_task_run_fence(db, run.id, execution_token)

                    result = await dispatch_scheduled_job(
                        db,
                        job,
                        scheduled_job_run_id=run.id,
                        model_pipeline_command=model_pipeline_command,
                        model_pipeline_fence=(
                            model_fence if model_pipeline_command is not None and execution_token is not None else None
                        ),
                    )
            if await _apply_scrape_failure_retry(
                db,
                run,
                artifacts=result.artifacts,
                execution_token=execution_token,
                error=result.detail or "scheduled scrape execution failed",
            ):
                await db.commit()
                return run
            if execution_token is not None:
                await assert_task_run_fence(db, run.id, execution_token)
            await finish_task_run(
                db,
                run,
                status=result.status,
                detail=result.detail,
                artifacts=result.artifacts,
                metrics=_worker_metrics_from_artifacts(result.artifacts),
                execution_token=execution_token,
            )
            await db.commit()
        except SoccerdataIngestionError as exc:
            # The ingestion service rolls partial dataset/observation writes
            # back to its savepoint and leaves a durable failed checkpoint.
            # Preserve that checkpoint before task-run recovery starts a clean
            # outbox -> run lock transaction.
            await db.commit()
            return await _recover_execution_exception(db, run_id=run_id, execution_token=execution_token, exc=exc)
        except Exception as exc:
            return await _recover_execution_exception(db, run_id=run_id, execution_token=execution_token, exc=exc)
        return run


async def execute_scrape_job_run(run_id: int) -> ScheduledJobRun:
    async with async_session_factory() as db:
        existing_run = await db.get(ScheduledJobRun, run_id)
        lease_seconds = _task_run_lease_seconds(existing_run) if existing_run is not None else None
        run = await claim_queued_task_run(db, run_id, lease_seconds=lease_seconds)
        if run is None:
            if existing_run is None:
                raise LookupError(f"Scrape job run {run_id} not found")
            return existing_run
        await db.commit()
        scrape_job_ids = (run.artifacts or {}).get("scrape_job_ids") or []
        if not scrape_job_ids:
            await finish_task_run(
                db,
                run,
                status="failed",
                detail="missing_scrape_job_id",
                error="missing_scrape_job_id",
                execution_token=_run_execution_token(run),
            )
            await db.commit()
            return run

        try:
            async with _task_run_heartbeat(
                run.id,
                lease_seconds=lease_seconds,
                **({"execution_token": token} if (token := _run_execution_token(run)) is not None else {}),
            ):
                try:
                    job = await execute_scrape_job(db, int(scrape_job_ids[0]))
                    # Do not commit business state independently. The fence
                    # and terminal run update below share one transaction.
                except Exception:
                    await db.rollback()
                    raise
            artifacts = _scrape_job_artifacts(job)
            status = _scrape_task_run_status(job.status or "failed", artifacts)
            detail = f"scrape_job:{job.id}; status:{status}"
            if getattr(job, "error", None):
                detail = f"{detail}; error:{job.error}"
            token = _run_execution_token(run)
            if await _apply_scrape_failure_retry(
                db,
                run,
                artifacts=artifacts,
                execution_token=token,
                error=str(getattr(job, "error", None) or detail),
            ):
                await db.commit()
                return run
            if (token := _run_execution_token(run)) is not None:
                await assert_task_run_fence(db, run.id, token)
            await finish_task_run(
                db,
                run,
                status=status,
                detail=detail,
                artifacts=artifacts,
                metrics=_worker_metrics_from_artifacts(artifacts),
                execution_token=_run_execution_token(run),
            )
            await db.commit()
        except Exception as exc:
            return await _recover_execution_exception(
                db, run_id=run_id, execution_token=_run_execution_token(run), exc=exc
            )
        return run


async def execute_world_cup_pipeline_run(run_id: int) -> ScheduledJobRun:
    from app.services.world_cup_pipeline import execute_world_cup_pipeline_job

    async with async_session_factory() as db:
        existing_run = await db.get(ScheduledJobRun, run_id)
        lease_seconds = _task_run_lease_seconds(existing_run) if existing_run is not None else None
        run = await claim_queued_task_run(db, run_id, lease_seconds=lease_seconds)
        if run is None:
            if existing_run is None:
                raise LookupError(f"World Cup pipeline run {run_id} not found")
            return existing_run
        await db.commit()
        artifacts = run.artifacts or {}
        scrape_job_ids = artifacts.get("scrape_job_ids") or []
        user_id = artifacts.get("user_id")
        if not scrape_job_ids or not user_id:
            await finish_task_run(
                db,
                run,
                status="failed",
                detail="missing_pipeline_inputs",
                error="missing_pipeline_inputs",
                execution_token=_run_execution_token(run),
            )
            await db.commit()
            return run

        try:
            async with _task_run_heartbeat(
                run.id,
                lease_seconds=lease_seconds,
                **({"execution_token": token} if (token := _run_execution_token(run)) is not None else {}),
            ):
                await execute_world_cup_pipeline_job(int(scrape_job_ids[0]), int(user_id))
            await finish_task_run(
                db,
                run,
                status="completed",
                detail=f"world_cup_pipeline:{scrape_job_ids[0]}",
                execution_token=_run_execution_token(run),
            )
            await db.commit()
        except Exception as exc:
            return await _recover_execution_exception(
                db, run_id=run_id, execution_token=_run_execution_token(run), exc=exc
            )
        return run


async def execute_task_run(run_id: int) -> ScheduledJobRun:
    """Canonical executor shared by in-process and Taskiq transports."""
    async with async_session_factory() as db:
        run = await db.get(ScheduledJobRun, run_id)
        if run is None:
            raise LookupError(f"Task run {run_id} not found")
        scheduled_job_id = run.scheduled_job_id
        task_type = run.task_type
    if scheduled_job_id is not None:
        return await execute_scheduled_job_run(run_id)
    if task_type == "world_cup_pipeline":
        return await execute_world_cup_pipeline_run(run_id)
    if task_type == "scrape_job":
        return await execute_scrape_job_run(run_id)
    raise ValueError(f"Unsupported task run type: {task_type}")


async def enqueue_scrape_job_execution(
    db: AsyncSession, *, scrape_job_id: int, triggered_by: str = "api", user_id: int | None = None
) -> ScheduledJobRun:
    existing_run = await find_active_scrape_task_run(db, task_type="scrape_job", scrape_job_id=scrape_job_id)
    if existing_run is not None:
        return existing_run

    artifacts: dict[str, Any] = {"scrape_job_ids": [scrape_job_id]}
    if user_id is not None:
        artifacts["user_id"] = user_id

    run = await create_task_run(
        db,
        task_type="scrape_job",
        scrape_job_id=scrape_job_id,
        triggered_by=triggered_by,
        artifacts=artifacts,
        transport=settings.task_queue_backend,
    )
    return await _enqueue_run_after_commit(db, run, task_name="scrape_job")


async def enqueue_world_cup_pipeline_execution(
    db: AsyncSession,
    *,
    scrape_job_id: int,
    user_id: int,
    triggered_by: str = "api",
) -> ScheduledJobRun:
    existing_run = await find_active_scrape_task_run(db, task_type="world_cup_pipeline", scrape_job_id=scrape_job_id)
    if existing_run is not None:
        return existing_run

    run = await create_task_run(
        db,
        task_type="world_cup_pipeline",
        scrape_job_id=scrape_job_id,
        triggered_by=triggered_by,
        artifacts={"scrape_job_ids": [scrape_job_id], "user_id": user_id},
        transport=settings.task_queue_backend,
    )
    return await _enqueue_run_after_commit(db, run, task_name="world_cup_pipeline")


async def enqueue_due_scheduled_jobs(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 10,
    transport: str = "taskiq",
    job_ids: list[int] | None = None,
) -> list[ScheduledJobRun]:
    current = now or utcnow()
    async with _scheduler_lock:
        stmt = select(ScheduledJob).where(ScheduledJob.enabled.is_(True))
        if job_ids is not None:
            if not job_ids:
                return []
            stmt = stmt.where(ScheduledJob.id.in_(job_ids))
        stmt = stmt.order_by(ScheduledJob.next_run.asc().nulls_last()).limit(limit).with_for_update(skip_locked=True)
        result = await db.execute(stmt)
        jobs = list(result.scalars().all())

        runs: list[ScheduledJobRun] = []
        outbox_entries: list[TaskOutbox] = []
        quarantined_jobs = False
        for job in jobs:
            if job.next_run is None:
                try:
                    await initialize_next_run(db, job, now=current)
                except ValueError as exc:
                    await quarantine_invalid_scheduled_job(db, job, error=exc, detected_at=current)
                    quarantined_jobs = True
                continue

            if not scheduled_job_due(job, now=current):
                continue

            try:
                next_run = next_run_from_cron(job.cron_expression, after=current)
            except ValueError as exc:
                await quarantine_invalid_scheduled_job(db, job, error=exc, detected_at=current)
                quarantined_jobs = True
                continue

            try:
                run = await create_task_run(
                    db,
                    task_type=job.task_type,
                    scheduled_job=job,
                    due_at=job.next_run,
                    triggered_by="scheduler",
                    transport=transport,
                    artifacts=_scheduled_job_run_artifacts(job),
                )
            except (LaneBackpressureError, WorkerLaneAdmissionClosedError):
                # Keep this due job untouched; another lane must still advance.
                continue
            outbox_entries.append(await create_task_outbox(db, run, task_name="scheduled_job", transport=transport))
            job.last_run = current
            job.next_run = next_run
            await db.flush()
            runs.append(run)

        if runs or quarantined_jobs:
            await db.commit()
            for run, outbox in zip(runs, outbox_entries, strict=True):
                try:
                    await _publish_outbox_entry(db, outbox)
                except TaskEnqueueError:
                    if run.scheduled_job_id is not None and run.due_at is not None:
                        job = await db.get(ScheduledJob, run.scheduled_job_id)
                        if job is not None:
                            job.next_run = run.due_at
                            await db.commit()

        return runs


async def run_due_scheduled_jobs(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 10,
    job_ids: list[int] | None = None,
) -> list[ScheduledJobRun]:
    current = now or utcnow()
    return await enqueue_due_scheduled_jobs(
        db,
        now=current,
        limit=limit,
        transport=settings.task_queue_backend,
        job_ids=job_ids,
    )


async def scheduler_loop(*, interval_seconds: int = 60) -> None:
    while True:
        async with async_session_factory() as db:
            try:
                await reconcile_task_outbox(db)
                await run_due_scheduled_jobs(db)
                await db.commit()
            except Exception:
                await db.rollback()
        await asyncio.sleep(max(5, interval_seconds))


def start_scheduler(*, interval_seconds: int = 60) -> None:
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(scheduler_loop(interval_seconds=interval_seconds))


async def stop_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is None:
        return
    _scheduler_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _scheduler_task
    _scheduler_task = None
