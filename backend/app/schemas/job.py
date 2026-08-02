import re
from datetime import datetime
from typing import Any, Literal

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
        "soccerdata_http_ingest",
        "soccerdata_browser_ingest",
        "train_model",
        "backtest_model",
        "predict_model",
        "fetch_latest_odds",
    }
)
MODEL_PIPELINE_SCHEDULED_TASK_TYPES = frozenset({"train_model", "backtest_model", "predict_model"})
LICENSED_ODDS_SCHEDULED_TASK_TYPES = frozenset({"fetch_latest_odds"})
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


def parse_model_pipeline_scheduled_config(task_type: str, config: dict[str, Any]) -> Any:
    """Parse one immutable, versioned model-pipeline command.

    Scheduled jobs intentionally store only the public command contract.  The
    service turns it into a canonical JSON snapshot when enqueueing, so later
    edits to the schedule cannot alter an already-delivered model run.
    """
    from app.schemas.model_pipeline import (
        BacktestModelCommandV1,
        PredictModelCommandV1,
        TrainModelCommandV1,
    )

    command_types = {
        "train_model": TrainModelCommandV1,
        "backtest_model": BacktestModelCommandV1,
        "predict_model": PredictModelCommandV1,
    }
    try:
        command_type = command_types[task_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported model pipeline task type: {task_type}") from exc
    try:
        return command_type.model_validate(config)
    except ValueError as exc:
        raise ValueError(f"Invalid {task_type} model pipeline command: {exc}") from exc


class LicensedOddsJobSpecV1(BaseModel):
    """Immutable, secret-free command for the approved provider HTTP lane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["licensed-odds-job/v1"] = "licensed-odds-job/v1"
    scope: Literal["prematch", "inplay"]
    canary_stage_percent: Literal[10, 25, 50, 100]

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def parse_licensed_odds_scheduled_config(config: dict[str, Any]) -> LicensedOddsJobSpecV1:
    try:
        return LicensedOddsJobSpecV1.model_validate(config)
    except ValueError as exc:
        raise ValueError(f"Invalid fetch_latest_odds licensed odds command: {exc}") from exc


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
        if self.task_type in {"soccerdata_http_ingest", "soccerdata_browser_ingest"}:
            from app.providers.soccerdata import SoccerdataIngestionSpec

            if config.get("page", 0) != 0 or config.get("start_cursor") not in {None, 0} or "generation_key" in config:
                raise ValueError("Scheduled soccerdata jobs must start from page zero")
            try:
                spec = SoccerdataIngestionSpec.from_config(config)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
            if spec.task_type != self.task_type:
                raise ValueError("Soccerdata operation does not match the scheduled worker lane")
        if self.task_type in MODEL_PIPELINE_SCHEDULED_TASK_TYPES:
            parse_model_pipeline_scheduled_config(self.task_type, config)
        if self.task_type in LICENSED_ODDS_SCHEDULED_TASK_TYPES:
            parse_licensed_odds_scheduled_config(config)
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
