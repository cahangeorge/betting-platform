from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import scheduled_jobs
from app.services.scheduled_jobs import (
    SCHEDULED_JOB_OWNER_CONFIG_KEY,
    dispatch_scheduled_job,
    next_run_from_cron,
    scheduled_job_due,
    stamp_created_by,
)


def test_next_run_from_ui_cron_patterns():
    base = datetime(2026, 6, 24, 10, 30, tzinfo=timezone.utc)

    assert next_run_from_cron("0 */6 * * *", after=base) == base + timedelta(hours=6)
    assert next_run_from_cron("0 0 */2 * *", after=base) == base + timedelta(days=2)
    assert next_run_from_cron("invalid", after=base) == base + timedelta(hours=1)


def test_scheduled_job_due_requires_enabled_and_next_run():
    now = datetime(2026, 6, 24, 10, 30, tzinfo=timezone.utc)

    assert scheduled_job_due(SimpleNamespace(enabled=True, next_run=now - timedelta(seconds=1)), now=now)
    assert not scheduled_job_due(SimpleNamespace(enabled=False, next_run=now - timedelta(seconds=1)), now=now)
    assert not scheduled_job_due(SimpleNamespace(enabled=True, next_run=None), now=now)
    assert not scheduled_job_due(SimpleNamespace(enabled=True, next_run=now + timedelta(seconds=1)), now=now)


def test_stamp_created_by_preserves_existing_config():
    config = stamp_created_by({"area": "prediction"}, 12)

    assert config["area"] == "prediction"
    assert config[SCHEDULED_JOB_OWNER_CONFIG_KEY] == 12


@pytest.mark.asyncio
async def test_dispatch_scrape_job_creates_and_executes_scrape(monkeypatch):
    calls = []

    async def fake_create_scrape_job(db, job_type, league, params):
        calls.append(("create", job_type, league, params))
        return SimpleNamespace(id=44)

    async def fake_execute_scrape_job(db, job_id):
        calls.append(("execute", job_id))
        return SimpleNamespace(id=job_id, status="completed")

    monkeypatch.setattr(scheduled_jobs, "create_scrape_job", fake_create_scrape_job)
    monkeypatch.setattr(scheduled_jobs, "execute_scrape_job", fake_execute_scrape_job)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(id=7, task_type="scrape_odds", config={"league": "world-cup", "params": {"command": "noop"}}),
    )

    assert result.status == "completed"
    assert result.detail == "scrape_job:44"
    assert calls == [
        ("create", "scrape_odds", "world-cup", {"command": "noop"}),
        ("execute", 44),
    ]


@pytest.mark.asyncio
async def test_dispatch_prediction_job_skips_without_owner():
    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(id=8, task_type="run_predictions", config={"strategy_ids": [1]}),
    )

    assert result.status == "skipped"
    assert result.detail == "missing_user_id"
