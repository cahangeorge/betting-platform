from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    completed: bool = False
    created_at: datetime


class TodoCreateRequest(BaseModel):
    title: str
