"""PostgreSQL regressions for scheduled soccerdata worker transaction ownership."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.job import ScheduledJob, ScheduledJobRun
from app.providers.soccerdata import SoccerdataJobMode
from app.services import scheduled_jobs
from app.services.soccerdata_ingestion import SoccerdataIngestionResult

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL"),
]


async def _cleanup(sessions: async_sessionmaker, name: str) -> None:
    async with sessions() as session, session.begin():
        await session.execute(delete(ScheduledJob).where(ScheduledJob.name == name))


async def test_scheduled_soccerdata_replay_misses_keep_worker_session_clean_for_each_bridge_fetch(monkeypatch) -> None:
    """Replay reads use dedicated sessions, preserving worker ORM identities across pages."""
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    name = f"g009-scheduler-{uuid4()}"
    spec = scheduled_jobs.SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition=f"g009-{uuid4()}",
        season="2025-2026",
        mode=SoccerdataJobMode.INCREMENTAL,
        limit=2,
        chunk_size=1,
    )
    worker_session = None

    class TrackingSessionFactory:
        def __call__(self):
            nonlocal worker_session
            session = sessions()
            if worker_session is None:
                worker_session = session
            return session

    try:
        async with sessions() as session, session.begin():
            job = ScheduledJob(
                name=name,
                task_type="soccerdata_http_ingest",
                cron_expression="0 * * * *",
                config=spec.to_config(),
            )
            session.add(job)
            await session.flush()
            run = ScheduledJobRun(
                scheduled_job_id=job.id,
                task_type=job.task_type,
                status="queued",
                queue_lane="provider-http",
                queue_contract_version="worker-lanes/v1",
                artifacts={
                    "job_spec": spec.to_config(),
                    "job_spec_digest": spec.spec_digest,
                    "request_fingerprint": spec.request_fingerprint,
                },
            )
            session.add(run)
            await session.flush()
            run_id = run.id

        replay_sessions = []
        fetched_pages = []

        async def replay_miss(replay_db, page_spec):
            assert replay_db is not worker_session
            replay_sessions.append(replay_db)
            # A real SELECT starts a transaction in the dedicated replay session.
            assert await replay_db.scalar(select(text("1"))) == 1
            assert replay_db.in_transaction()
            assert page_spec.page in {0, 1}
            return None

        async def fetch(page_spec):
            assert worker_session is not None
            assert not worker_session.in_transaction(), "bridge fetch must not inherit worker DB transaction"
            fetched_pages.append(page_spec.page)
            return object()

        async def persist(_db, page_spec, _batch, **kwargs):
            await kwargs["fence"]()
            cursor = {"page": 1, "start_cursor": 1, "generation_key": "a" * 64} if page_spec.page == 0 else None
            return SoccerdataIngestionResult(
                checkpoint_id=100 + page_spec.page,
                state="completed",
                dataset_id=200 + page_spec.page,
                record_count=1,
                observation_count=1,
                cursor=cursor,
            )

        @asynccontextmanager
        async def no_heartbeat(*_args, **_kwargs):
            yield

        monkeypatch.setattr(scheduled_jobs, "async_session_factory", TrackingSessionFactory())
        monkeypatch.setattr(scheduled_jobs, "authorize_soccerdata_ingestion", lambda _spec: None)
        monkeypatch.setattr(scheduled_jobs, "replay_soccerdata_batch", replay_miss)
        monkeypatch.setattr(scheduled_jobs, "fetch_soccerdata_batch", fetch)
        monkeypatch.setattr(scheduled_jobs, "persist_soccerdata_batch", persist)
        monkeypatch.setattr(scheduled_jobs, "_task_run_heartbeat", no_heartbeat)

        result = await scheduled_jobs.execute_scheduled_job_run(run_id)

        assert fetched_pages == [0, 1]
        assert len(replay_sessions) == 2
        assert result.status == "completed"
        assert result.artifacts["page_count"] == 2
        assert result.artifacts["dataset_ids"] == [200, 201]

        async with sessions() as session:
            persisted_run = await session.get(ScheduledJobRun, run_id)
            assert persisted_run is not None
            assert persisted_run.status == "completed"
            assert persisted_run.artifacts is not None
            assert persisted_run.artifacts["page_count"] == 2
    finally:
        await _cleanup(sessions, name)
        await engine.dispose()
