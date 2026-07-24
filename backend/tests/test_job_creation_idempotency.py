from contextlib import AbstractAsyncContextManager

import pytest

from app.models.job import JobCreationIdempotency, ScheduledJob
from app.models.scrape import ScrapeJob
from app.services.job_creation_idempotency import create_idempotent_job, request_fingerprint


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Nested(AbstractAsyncContextManager):
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _JobCreationDb:
    """Small durable-store double for replay semantics without a live DB."""

    def __init__(self):
        self.records = {}
        self.jobs = {}
        self.pending_record = None

    async def execute(self, statement):
        params = statement.compile().params
        key = (params["user_id_1"], params["operation_1"], params["idempotency_key_1"])
        return _Result(self.records.get(key))

    def begin_nested(self):
        return _Nested()

    def add(self, value):
        if isinstance(value, JobCreationIdempotency):
            self.pending_record = value
        elif isinstance(value, (ScheduledJob, ScrapeJob)):
            self.jobs[(type(value), value.id)] = value

    async def flush(self):
        if self.pending_record is not None:
            record = self.pending_record
            self.records[(record.user_id, record.operation, record.idempotency_key)] = record
            self.pending_record = None

    async def get(self, model, object_id):
        return self.jobs.get((model, object_id))


@pytest.mark.asyncio
async def test_lost_response_retry_replays_original_scrape_job_and_is_user_scoped():
    db = _JobCreationDb()
    payload = {"job_type": "scrape_odds", "league": "romania", "params": {"season": "2025-26"}}
    fingerprint = request_fingerprint(payload)
    create_calls = 0

    async def create_scrape() -> ScrapeJob:
        nonlocal create_calls
        create_calls += 1
        job = ScrapeJob(id=create_calls, job_type="scrape_odds", league="romania", params={"season": "2025-26"})
        db.add(job)
        return job

    first, created = await create_idempotent_job(
        db,
        user_id=1,
        operation="scrape_job_create",
        idempotency_key="prepare-romania-2025-26",
        fingerprint=fingerprint,
        job_model=ScrapeJob,
        create=create_scrape,
    )
    replay, replay_created = await create_idempotent_job(
        db,
        user_id=1,
        operation="scrape_job_create",
        idempotency_key="prepare-romania-2025-26",
        fingerprint=fingerprint,
        job_model=ScrapeJob,
        create=create_scrape,
    )

    assert created
    assert not replay_created
    assert replay is first
    assert create_calls == 1

    # A matching key from another authenticated user does not replay user 1's
    # job; authorization isolation is part of the uniqueness boundary.
    other_user_job, other_user_created = await create_idempotent_job(
        db,
        user_id=2,
        operation="scrape_job_create",
        idempotency_key="prepare-romania-2025-26",
        fingerprint=fingerprint,
        job_model=ScrapeJob,
        create=create_scrape,
    )
    assert other_user_created
    assert other_user_job.id != first.id

    with pytest.raises(ValueError, match="different job creation request"):
        await create_idempotent_job(
            db,
            user_id=1,
            operation="scrape_job_create",
            idempotency_key="prepare-romania-2025-26",
            fingerprint=request_fingerprint({**payload, "league": "england"}),
            job_model=ScrapeJob,
            create=create_scrape,
        )


@pytest.mark.asyncio
async def test_scheduled_job_creation_retry_replays_the_original_job():
    db = _JobCreationDb()
    payload = {"name": "Romania autoscrape", "task_type": "scrape_odds", "cron_expression": "0 */6 * * *", "config": {}}
    create_calls = 0

    async def create_scheduled() -> ScheduledJob:
        nonlocal create_calls
        create_calls += 1
        job = ScheduledJob(
            id=create_calls,
            name="Romania autoscrape",
            task_type="scrape_odds",
            cron_expression="0 */6 * * *",
            config={"_created_by_user_id": 1},
        )
        db.add(job)
        return job

    first, created = await create_idempotent_job(
        db,
        user_id=1,
        operation="scheduled_job_create",
        idempotency_key="autoscrape-romania",
        fingerprint=request_fingerprint(payload),
        job_model=ScheduledJob,
        create=create_scheduled,
    )
    replay, replay_created = await create_idempotent_job(
        db,
        user_id=1,
        operation="scheduled_job_create",
        idempotency_key="autoscrape-romania",
        fingerprint=request_fingerprint(payload),
        job_model=ScheduledJob,
        create=create_scheduled,
    )

    assert created
    assert not replay_created
    assert replay is first
    assert create_calls == 1
