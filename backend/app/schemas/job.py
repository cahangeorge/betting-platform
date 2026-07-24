import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEDULED_JOB_TASK_TYPES = frozenset(
    {
        "scrape_odds",
        "run_predictions",
        "scrape_then_predict",
        "scrape_predict_tickets",
        "generate_tickets",
        "verify_and_settle",
        "verify_results",
        "world_cup_pipeline",
    }
)
_RESERVED_CONFIG_KEYS = frozenset({"_created_by_user_id", "user_id"})
_HOURLY_CRON = re.compile(r"0 \*/([1-9][0-9]*) \* \* \*")
_DAILY_CRON = re.compile(r"0 0 \*/([1-9][0-9]*) \* \*")


def validate_scheduled_job_cron(value: str) -> str:
    """Accept only the finite cron grammar produced by the scheduling UI."""
    normalized = " ".join(value.split())
    if _HOURLY_CRON.fullmatch(normalized) or _DAILY_CRON.fullmatch(normalized) or normalized == "0 0 * * 1":
        return normalized
    raise ValueError("cron_expression must be an hourly, daily, or Monday weekly schedule")


def _contains_reserved_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in _RESERVED_CONFIG_KEYS or _contains_reserved_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_reserved_key(item) for item in value)
    return False


class ScheduledJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    task_type: str
    cron_expression: str
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    config: dict | None = None
    created_at: datetime


class ScheduledJobCreateRequest(BaseModel):
    name: str
    task_type: str
    cron_expression: str
    config: dict[str, Any] | None = Field(default=None)

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SCHEDULED_JOB_TASK_TYPES:
            raise ValueError(f"Unsupported scheduled task type: {value}")
        return normalized

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, value: str) -> str:
        return validate_scheduled_job_cron(value)

    @model_validator(mode="after")
    def validate_config(self) -> "ScheduledJobCreateRequest":
        config = self.config or {}
        if _contains_reserved_key(config):
            raise ValueError("config must not contain internal ownership fields")

        def positive_int(field: str, *, required: bool = False) -> None:
            value = config.get(field)
            if value is None:
                if required:
                    raise ValueError(f"config.{field} is required")
                return
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"config.{field} must be a positive integer")

        def positive_id_list(field: str, *, required: bool = False) -> None:
            value = config.get(field)
            if value is None:
                if required:
                    raise ValueError(f"config.{field} is required")
                return
            invalid_items = not isinstance(value, list) or any(
                isinstance(item, bool) or not isinstance(item, int) or item <= 0
                for item in (value if isinstance(value, list) else [])
            )
            if not isinstance(value, list) or not value or invalid_items:
                raise ValueError(f"config.{field} must be a non-empty list of positive integers")

        prediction_tasks = {"run_predictions", "scrape_then_predict", "scrape_predict_tickets"}
        ticket_tasks = {"generate_tickets", "scrape_predict_tickets"}
        if self.task_type in prediction_tasks:
            positive_id_list("strategy_ids", required=self.task_type == "run_predictions")
        if self.task_type in ticket_tasks:
            ticket_config = config.get("tickets") if self.task_type == "scrape_predict_tickets" else config
            if ticket_config is not None and not isinstance(ticket_config, dict):
                raise ValueError("config.tickets must be an object")
            ticket_config = ticket_config or {}
            bankroll = ticket_config.get("bankroll_id")
            invalid_bankroll = isinstance(bankroll, bool) or not isinstance(bankroll, int) or bankroll <= 0
            if self.task_type == "generate_tickets" and invalid_bankroll:
                raise ValueError("config.bankroll_id is required and must be a positive integer")
            for field in ("ticket_count", "run_id", "bankroll_id"):
                if field in ticket_config:
                    value = ticket_config[field]
                    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                        raise ValueError(f"config.{field} must be a positive integer")
            for field in ("run_ids", "prediction_ids"):
                if field in ticket_config:
                    values = ticket_config[field]
                    invalid_items = not isinstance(values, list) or any(
                        isinstance(item, bool) or not isinstance(item, int) or item <= 0
                        for item in (values if isinstance(values, list) else [])
                    )
                    if not isinstance(values, list) or not values or invalid_items:
                        raise ValueError(f"config.{field} must be a non-empty list of positive integers")
            if "min_odds" in ticket_config and "max_odds" in ticket_config:
                try:
                    min_odds = float(ticket_config["min_odds"])
                    max_odds = float(ticket_config["max_odds"])
                    if min_odds <= 0 or max_odds < min_odds:
                        raise ValueError
                except (TypeError, ValueError):
                    raise ValueError("config odds bounds must be positive and ordered") from None
        if self.task_type == "scrape_odds" and "params" in config and not isinstance(config["params"], dict):
            raise ValueError("config.params must be an object")
        return self


class ScheduledJobRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    job_id: int | None = None
    scheduled_job_id: int | None = None
    scrape_job_id: int | None = None
    task_type: str
    status: str
    detail: str | None = None
    artifacts: dict | None = None
    taskiq_task_id: str | None = None
    transport: str | None = None
    transport_task_id: str | None = None
    idempotency_key: str | None = None
    attempt: int | None = None
    max_attempts: int | None = None
    next_attempt_at: datetime | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None
    triggered_by: str | None = None
    due_at: datetime | None = None
    created_at: datetime | None = None


class ScheduledJobRunPageResponse(BaseModel):
    runs: list[ScheduledJobRunResponse]
    total: int
    page: int
    per_page: int
