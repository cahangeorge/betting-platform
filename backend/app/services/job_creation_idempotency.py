"""Database-backed idempotency for user-created scheduled and scrape jobs."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import TypeVar, cast, overload

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import JobCreationIdempotency, ScheduledJob
from app.models.scrape import ScrapeJob

CreatedJob = TypeVar("CreatedJob", ScheduledJob, ScrapeJob)

MAX_IDEMPOTENCY_KEY_LENGTH = 128


def normalize_idempotency_key(value: str | None) -> str | None:
    """Normalize the optional HTTP key and reject non-replay-safe values."""
    if value is None:
        return None
    key = value.strip()
    if not key:
        raise ValueError("Idempotency-Key must not be blank")
    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError(f"Idempotency-Key must be at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters")
    if any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise ValueError("Idempotency-Key must contain visible ASCII characters only")
    return key


def request_fingerprint(payload: dict) -> str:
    """Return a stable digest of the complete client-visible creation request."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@overload
async def create_idempotent_job(
    db: AsyncSession,
    *,
    user_id: int,
    operation: str,
    idempotency_key: str,
    fingerprint: str,
    job_model: type[ScheduledJob],
    create: Callable[[], Awaitable[ScheduledJob]],
) -> tuple[ScheduledJob, bool]: ...


@overload
async def create_idempotent_job(
    db: AsyncSession,
    *,
    user_id: int,
    operation: str,
    idempotency_key: str,
    fingerprint: str,
    job_model: type[ScrapeJob],
    create: Callable[[], Awaitable[ScrapeJob]],
) -> tuple[ScrapeJob, bool]: ...


async def create_idempotent_job(
    db: AsyncSession,
    *,
    user_id: int,
    operation: str,
    idempotency_key: str,
    fingerprint: str,
    job_model: type[CreatedJob],
    create: Callable[[], Awaitable[CreatedJob]],
) -> tuple[CreatedJob, bool]:
    """Create once or replay the original job for an identical authenticated request.

    The uniqueness constraint is the concurrency boundary.  The nested
    transaction rolls back a losing job insert before loading the winner, so a
    simultaneous retry cannot leave an orphan duplicate behind.
    """
    existing = await _find_record(db, user_id=user_id, operation=operation, idempotency_key=idempotency_key)
    if existing is not None:
        return await _replayed_job(db, existing, fingerprint, job_model), False

    try:
        async with db.begin_nested():
            job = await create()
            record = JobCreationIdempotency(
                user_id=user_id,
                operation=operation,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                scheduled_job_id=job.id if job_model is ScheduledJob else None,
                scrape_job_id=job.id if job_model is ScrapeJob else None,
            )
            db.add(record)
            await db.flush()
    except IntegrityError:
        existing = await _find_record(db, user_id=user_id, operation=operation, idempotency_key=idempotency_key)
        if existing is None:
            raise
        return await _replayed_job(db, existing, fingerprint, job_model), False

    return job, True


async def _find_record(
    db: AsyncSession, *, user_id: int, operation: str, idempotency_key: str
) -> JobCreationIdempotency | None:
    result = await db.execute(
        select(JobCreationIdempotency).where(
            JobCreationIdempotency.user_id == user_id,
            JobCreationIdempotency.operation == operation,
            JobCreationIdempotency.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _replayed_job(
    db: AsyncSession, record: JobCreationIdempotency, fingerprint: str, job_model: type[CreatedJob]
) -> CreatedJob:
    if record.request_fingerprint != fingerprint:
        raise ValueError("Idempotency-Key is already used for a different job creation request")
    job_id = record.scheduled_job_id if job_model is ScheduledJob else record.scrape_job_id
    if job_id is None:
        raise RuntimeError("Idempotency record has a different job type")
    job = await db.get(job_model, job_id)
    if job is None:
        raise RuntimeError("Idempotency record references a missing job")
    return cast(CreatedJob, job)
