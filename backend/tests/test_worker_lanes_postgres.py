"""Opt-in PostgreSQL regression gates for G003 durable worker lanes.

Run with BET_TEST_POSTGRES_URL pointing at an isolated database migrated to head.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.job import ScheduledJobRun, TaskOutbox
from app.services import task_runs
from app.services.task_runs import (
    LaneBackpressureError,
    claim_queued_task_run,
    create_task_run,
    enforce_lane_backpressure,
    requeue_task_run_failure,
)
from app.tasks.worker_lanes import WORKER_LANE_CONTRACT_VERSION

POSTGRES_URL = os.getenv("BET_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_URL, reason="requires isolated PostgreSQL BET_TEST_POSTGRES_URL"),
]


def _run(key: str, *, lane: str = "provider-browser", status: str = "running", attempt: int = 1) -> ScheduledJobRun:
    now = datetime.now(UTC)
    return ScheduledJobRun(
        task_type="scrape_job",
        status=status,
        transport="taskiq",
        idempotency_key=key,
        queue_lane=lane,
        queue_contract_version=WORKER_LANE_CONTRACT_VERSION,
        attempt=attempt,
        max_attempts=2,
        queued_at=now - timedelta(seconds=10),
        started_at=now - timedelta(seconds=5) if status == "running" else None,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(minutes=1) if status == "running" else None,
        execution_token="token-a" if status == "running" else None,
    )


async def _cleanup(sessions, prefix: str) -> None:
    async with sessions() as db, db.begin():
        ids = list(
            (
                await db.scalars(select(ScheduledJobRun.id).where(ScheduledJobRun.idempotency_key.like(f"{prefix}%")))
            ).all()
        )
        if ids:
            await db.execute(delete(TaskOutbox).where(TaskOutbox.run_id.in_(ids)))
            await db.execute(delete(ScheduledJobRun).where(ScheduledJobRun.id.in_(ids)))


async def test_retry_exhaustion_and_stale_fence_preserve_one_durable_outbox() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    prefix = f"g003-retry-{uuid4()}"
    try:
        async with sessions() as db, db.begin():
            run = _run(prefix)
            db.add(run)
            await db.flush()
            db.add(
                TaskOutbox(
                    run_id=run.id,
                    task_name="scrape_job",
                    transport="taskiq",
                    queue_lane=run.queue_lane,
                    queue_contract_version=run.queue_contract_version,
                    status="published",
                    attempts=3,
                    delivery_generation=1,
                    max_attempts=5,
                    available_at=datetime.now(UTC),
                )
            )
            run_id = run.id

        async with sessions() as db, db.begin():
            run = await db.get(ScheduledJobRun, run_id, with_for_update=True)
            assert run is not None
            # A stale worker cannot alter either run or outbox.
            assert not await requeue_task_run_failure(
                db, run, execution_token="stale-token", failure_kind="timeout", error="late"
            )

        async with sessions() as db, db.begin():
            run = await db.get(ScheduledJobRun, run_id, with_for_update=True)
            assert run is not None
            assert await requeue_task_run_failure(
                db, run, execution_token="token-a", failure_kind="timeout", error="lost worker"
            )

        async with sessions() as db:
            run = await db.get(ScheduledJobRun, run_id)
            outbox = await db.scalar(select(TaskOutbox).where(TaskOutbox.run_id == run_id))
            assert run is not None and outbox is not None
            assert run.status == "queued" and run.attempt == 1
            assert run.next_attempt_at is not None and outbox.available_at == run.next_attempt_at
            assert (outbox.delivery_generation, outbox.attempts, outbox.status) == (2, 0, "pending")

        async with sessions() as db, db.begin():
            run = await db.get(ScheduledJobRun, run_id, with_for_update=True)
            assert run is not None
            run.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            claimed = await claim_queued_task_run(db, run_id)
            assert claimed is not None and claimed.attempt == 2
            token = claimed.execution_token
            assert token
            assert await requeue_task_run_failure(
                db, claimed, execution_token=token, failure_kind="timeout", error="again"
            )

        async with sessions() as db:
            run = await db.get(ScheduledJobRun, run_id)
            outbox = await db.scalar(select(TaskOutbox).where(TaskOutbox.run_id == run_id))
            assert run is not None and outbox is not None
            assert (run.status, run.attempt, run.retry_disposition) == ("failed", 2, "terminal")
            assert (outbox.delivery_generation, outbox.attempts) == (2, 0)
    finally:
        await _cleanup(sessions, prefix)
        await engine.dispose()


async def test_postgres_lane_cap_isolated_between_browser_and_control(monkeypatch) -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    prefix = f"g003-cap-{uuid4()}"
    async with sessions() as db:
        existing_browser_active = int(
            await db.scalar(
                select(func.count())
                .select_from(ScheduledJobRun)
                .where(
                    ScheduledJobRun.queue_lane == "provider-browser",
                    ScheduledJobRun.status.in_(("queued", "running")),
                )
            )
            or 0
        )
    monkeypatch.setattr(
        task_runs,
        "backlog_cap_for_lane",
        lambda _settings, lane: existing_browser_active + 1 if lane.value == "provider-browser" else 1000,
    )
    try:

        async def admit(suffix: str) -> tuple[str, int | None]:
            try:
                async with sessions() as db, db.begin():
                    run = await create_task_run(
                        db,
                        task_type="scrape_job",
                        idempotency_key=f"{prefix}-{suffix}",
                    )
                    return "admitted", run.id
            except LaneBackpressureError:
                return "saturated", None

        results = await asyncio.gather(admit("left"), admit("right"))
        assert sorted(status for status, _ in results) == ["admitted", "saturated"]

        async with sessions() as db, db.begin():
            with pytest.raises(LaneBackpressureError) as exc_info:
                await enforce_lane_backpressure(db, "provider-browser")
            assert exc_info.value.cap == existing_browser_active + 1
            # Saturating a browser lane does not hold the control lane hostage.
            await enforce_lane_backpressure(db, "control")
    finally:
        await _cleanup(sessions, prefix)
        await engine.dispose()


async def test_retry_waits_for_blocking_outbox_lock_before_generation_update() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    prefix = f"g003-outbox-lock-{uuid4()}"
    try:
        async with sessions() as db, db.begin():
            run = _run(prefix)
            db.add(run)
            await db.flush()
            db.add(
                TaskOutbox(
                    run_id=run.id,
                    task_name="scrape_job",
                    transport="taskiq",
                    queue_lane=run.queue_lane,
                    queue_contract_version=run.queue_contract_version,
                    status="published",
                    attempts=1,
                    delivery_generation=1,
                    max_attempts=5,
                    available_at=datetime.now(UTC),
                )
            )
            run_id = run.id

        async with sessions() as lock_db:
            transaction = await lock_db.begin()
            await lock_db.execute(select(TaskOutbox).where(TaskOutbox.run_id == run_id).with_for_update())

            async def retry() -> bool:
                async with sessions() as db, db.begin():
                    run = await db.get(ScheduledJobRun, run_id)
                    assert run is not None
                    return await requeue_task_run_failure(
                        db, run, execution_token="token-a", failure_kind="timeout", error="retry"
                    )

            task = asyncio.create_task(retry())
            await asyncio.sleep(0.15)
            assert not task.done()
            # Publisher order is outbox -> run. If retry held run -> outbox,
            # this update would deadlock instead of completing immediately.
            await asyncio.wait_for(
                lock_db.execute(
                    update(ScheduledJobRun).where(ScheduledJobRun.id == run_id).values(detail="publisher-commit")
                ),
                timeout=2,
            )
            await transaction.commit()
            assert await asyncio.wait_for(task, timeout=5)

        async with sessions() as db:
            outbox = await db.scalar(select(TaskOutbox).where(TaskOutbox.run_id == run_id))
            assert outbox is not None and (outbox.delivery_generation, outbox.attempts) == (2, 0)
    finally:
        await _cleanup(sessions, prefix)
        await engine.dispose()
