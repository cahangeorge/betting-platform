from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    config: dict | None = None


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
