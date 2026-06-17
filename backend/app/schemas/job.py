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
