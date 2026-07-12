from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import ScheduledJob, ScheduledJobRun
from app.models.scrape import ScrapeJob
from app.models.user import User

OWNER_CONFIG_KEYS = ("_created_by_user_id", "user_id")


def stamp_owner(config: dict | None, user_id: int) -> dict:
    stamped = dict(config or {})
    stamped.setdefault("_created_by_user_id", user_id)
    return stamped


def owner_id_from_mapping(value: Mapping[str, Any] | None) -> int | None:
    if not value:
        return None
    for key in OWNER_CONFIG_KEYS:
        raw = value.get(key)
        if raw in (None, ""):
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def user_is_admin(user: User) -> bool:
    return bool(getattr(user, "is_admin", False))


def owner_matches_user(owner_id: int | None, user: User) -> bool:
    return owner_id is not None and owner_id == int(user.id)


def can_read_scheduled_job(job: ScheduledJob, user: User) -> bool:
    if user_is_admin(user):
        return True
    config = job.config if isinstance(job.config, dict) else {}
    return owner_matches_user(owner_id_from_mapping(config), user)


def can_read_scrape_job(job: ScrapeJob, user: User) -> bool:
    if user_is_admin(user):
        return True
    params = job.params if isinstance(job.params, dict) else {}
    return owner_matches_user(owner_id_from_mapping(params), user)


async def can_read_run(db: AsyncSession, run: ScheduledJobRun, user: User) -> bool:
    if user_is_admin(user):
        return True

    run_artifacts = getattr(run, "artifacts", None)
    artifacts = run_artifacts if isinstance(run_artifacts, dict) else {}
    if owner_matches_user(owner_id_from_mapping(artifacts), user):
        return True

    scheduled_job_id = getattr(run, "scheduled_job_id", None)
    if scheduled_job_id is not None:
        job = await db.get(ScheduledJob, scheduled_job_id)
        return job is not None and can_read_scheduled_job(job, user)

    scrape_job_id = getattr(run, "scrape_job_id", None)
    if scrape_job_id is not None:
        job = await db.get(ScrapeJob, scrape_job_id)
        return job is not None and can_read_scrape_job(job, user)

    return False


async def require_can_read_run(db: AsyncSession, run: ScheduledJobRun, user: User) -> None:
    if not await can_read_run(db, run, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Run is not owned by the current user")


def require_can_read_scheduled_job(job: ScheduledJob, user: User) -> None:
    if not can_read_scheduled_job(job, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scheduled job is not owned by the current user",
        )
