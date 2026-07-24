import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.models.job import ScheduledJob, ScheduledJobRun, TaskOutbox
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.user import User
from app.schemas.job import SCHEDULED_JOB_TASK_TYPES, validate_scheduled_job_cron
from app.schemas.strategy import StrategyRunFilters, StrategyRunRequest
from app.services.result_settlement import evaluate_model_prediction, settle_due_tickets
from app.services.scraper import create_scrape_job, execute_scrape_job
from app.services.task_runs import (
    claim_queued_task_run,
    create_task_outbox,
    create_task_run,
    find_active_scrape_task_run,
    finish_task_run,
    heartbeat_task_run_by_id,
    mark_outbox_publish_failed,
    mark_outbox_published,
)
from app.services.ticket_engine import TicketGenerationError, TicketRiskPolicyRequiredError, generate_tickets

SCHEDULED_JOB_OWNER_CONFIG_KEY = "_created_by_user_id"
SCHEDULED_JOB_QUARANTINE_CONFIG_KEY = "_scheduler_quarantine"

_scheduler_lock = asyncio.Lock()
_scheduler_task: asyncio.Task | None = None
_inprocess_tasks: set[asyncio.Task] = set()

settings = get_settings()
logger = logging.getLogger(__name__)


def _task_run_lease_seconds(run: ScheduledJobRun) -> int:
    configured_lease = settings.task_run_lease_seconds
    task_type = (run.task_type or "").lower()
    if task_type == "world_cup_pipeline" or any(token in task_type for token in ("scrape", "odds")):
        # A healthy OddsHarvester subprocess may legitimately use its entire
        # timeout. The margin prevents a duplicate claim between timeout and
        # exception/final-state persistence, including SQLite dev mode where a
        # long write transaction may temporarily block the heartbeat session.
        return max(configured_lease, settings.oddsharvester_timeout_seconds + 60)
    return configured_lease


async def _maintain_task_run_heartbeat(
    run_id: int,
    stopped: asyncio.Event,
    *,
    lease_seconds: int | None = None,
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
                renewed = await heartbeat_task_run_by_id(
                    heartbeat_db,
                    run_id,
                    lease_seconds=effective_lease_seconds,
                )
                await heartbeat_db.commit()
        except Exception:
            logger.warning("Task run %s heartbeat renewal failed", run_id, exc_info=True)
            continue
        if not renewed:
            return


@contextlib.asynccontextmanager
async def _task_run_heartbeat(run_id: int, *, lease_seconds: int | None = None):
    stopped = asyncio.Event()
    task = asyncio.create_task(
        _maintain_task_run_heartbeat(run_id, stopped, lease_seconds=lease_seconds),
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
    return artifacts


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


async def dispatch_scheduled_job(
    db: AsyncSession, job: ScheduledJob, *, scheduled_job_run_id: int | None = None
) -> ScheduledJobRunResult:
    task_type = (job.task_type or "").lower()
    if task_type not in SCHEDULED_JOB_TASK_TYPES:
        return ScheduledJobRunResult(
            job_id=job.id, task_type=job.task_type, status="skipped", detail="unsupported_task_type"
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
    if task_name == "scheduled_job":
        from app.tasks.jobs import execute_scheduled_job_run_task

        task = await execute_scheduled_job_run_task.kiq(run.id)
    elif task_name == "scrape_job":
        from app.tasks.jobs import execute_scrape_job_task

        task = await execute_scrape_job_task.kiq(run.id)
    elif task_name == "world_cup_pipeline":
        from app.tasks.jobs import execute_world_cup_pipeline_task

        task = await execute_world_cup_pipeline_task.kiq(run.id)
    else:
        raise ValueError(f"Unsupported Taskiq task name: {task_name}")
    return getattr(task, "task_id", None)


async def _send_inprocess_run(run: ScheduledJobRun, *, task_name: str) -> str:
    del task_name  # execution routing is derived durably from the run record
    task = asyncio.create_task(execute_task_run(run.id), name=f"task-run-{run.id}")
    _inprocess_tasks.add(task)
    task.add_done_callback(_inprocess_tasks.discard)
    return f"inprocess:{run.id}"


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
            )
            await db.commit()
            return run
        job = await db.get(ScheduledJob, run.scheduled_job_id)
        if job is None:
            await finish_task_run(
                db, run, status="failed", detail="scheduled_job_missing", error="Scheduled job not found"
            )
            await db.commit()
            return run

        try:
            async with _task_run_heartbeat(run.id, lease_seconds=lease_seconds):
                result = await dispatch_scheduled_job(db, job, scheduled_job_run_id=run.id)
            await finish_task_run(
                db,
                run,
                status=result.status,
                detail=result.detail,
                artifacts=result.artifacts,
            )
            await db.commit()
        except Exception as exc:
            await finish_task_run(db, run, status="failed", detail=str(exc), error=str(exc))
            await db.commit()
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
                db, run, status="failed", detail="missing_scrape_job_id", error="missing_scrape_job_id"
            )
            await db.commit()
            return run

        try:
            async with _task_run_heartbeat(run.id, lease_seconds=lease_seconds):
                job = await execute_scrape_job(db, int(scrape_job_ids[0]))
            artifacts = _scrape_job_artifacts(job)
            status = _scrape_task_run_status(job.status or "failed", artifacts)
            detail = f"scrape_job:{job.id}; status:{status}"
            if getattr(job, "error", None):
                detail = f"{detail}; error:{job.error}"
            await finish_task_run(db, run, status=status, detail=detail, artifacts=artifacts)
            await db.commit()
        except Exception as exc:
            await finish_task_run(db, run, status="failed", detail=str(exc), error=str(exc))
            await db.commit()
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
                db, run, status="failed", detail="missing_pipeline_inputs", error="missing_pipeline_inputs"
            )
            await db.commit()
            return run

        try:
            async with _task_run_heartbeat(run.id, lease_seconds=lease_seconds):
                await execute_world_cup_pipeline_job(int(scrape_job_ids[0]), int(user_id))
            await finish_task_run(db, run, status="completed", detail=f"world_cup_pipeline:{scrape_job_ids[0]}")
            await db.commit()
        except Exception as exc:
            await finish_task_run(db, run, status="failed", detail=str(exc), error=str(exc))
            await db.commit()
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

            run = await create_task_run(
                db,
                task_type=job.task_type,
                scheduled_job=job,
                due_at=job.next_run,
                triggered_by="scheduler",
                transport=transport,
            )
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
