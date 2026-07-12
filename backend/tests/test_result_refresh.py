from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from app.api.v1 import data as data_api
from app.schemas.data import ResultRefreshRequest
from app.services import scraper


class _SourceResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _SourceSession:
    def __init__(self, rows):
        self.rows = rows
        self.added = []

    async def execute(self, _stmt):
        return _SourceResult(self.rows)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_result_refresh_job_requires_source_urls_and_stamps_owner():
    match = SimpleNamespace(id=8, sport="football")
    db = _SourceSession([(match, "https://www.oddsportal.com/football/x/#fixture-8")])

    job = await scraper.create_result_refresh_job(db, [8, 8], user_id=12)

    assert job.job_type == "refresh_results"
    assert job.params["_created_by_user_id"] == 12
    assert job.params["match_ids"] == [8]
    assert job.params["match_links"] == ["https://www.oddsportal.com/football/x/#fixture-8"]


@pytest.mark.asyncio
async def test_result_refresh_job_rejects_matches_without_source_url():
    db = _SourceSession([])

    with pytest.raises(ValueError, match="match IDs: 8"):
        await scraper.create_result_refresh_job(db, [8], user_id=12)


def test_result_refresh_builds_explicit_source_link_arguments():
    job = SimpleNamespace(
        league=None,
        params={
            "command": "upcoming",
            "sport": "football",
            "match_links": ["https://example.test/a", "https://example.test/b"],
        },
    )

    args = scraper._build_oddsharvester_args(job)

    assert args.count("--match-link") == 2
    assert args[args.index("--match-link") + 1] == "https://example.test/a"


def test_scoreless_live_refresh_cannot_regress_a_final_score():
    stored = SimpleNamespace(home_score=2, away_score=1, status="finished")

    status, home_score, away_score = scraper._resolve_match_result(
        stored,
        {"home_score": None, "away_score": None},
        datetime.now(timezone.utc),
    )

    assert (status, home_score, away_score) == ("finished", 2, 1)


def test_conflicting_completed_refresh_cannot_overwrite_a_final_score(caplog):
    stored = SimpleNamespace(id=31, home_score=2, away_score=1, status="finished")

    status, home_score, away_score = scraper._resolve_match_result(
        stored, {"home_score": "0", "away_score": "3"}, None
    )

    assert (status, home_score, away_score) == ("finished", 2, 1)
    assert "Ignored conflicting final score refresh for match_id=31" in caplog.text


def test_matching_score_refresh_with_future_date_cannot_regress_a_final_status():
    stored = SimpleNamespace(id=32, home_score=2, away_score=1, status="final")

    status, home_score, away_score = scraper._resolve_match_result(
        stored,
        {"home_score": "2", "away_score": "1"},
        datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1),
    )

    assert (status, home_score, away_score) == ("final", 2, 1)


def test_result_refresh_request_rejects_nonpositive_match_ids():
    with pytest.raises(ValidationError):
        ResultRefreshRequest(match_ids=[0])


@pytest.mark.asyncio
async def test_result_refresh_endpoint_queues_but_does_not_execute_inline(monkeypatch):
    job = SimpleNamespace(
        id=35,
        job_type="refresh_results",
        status="pending",
        league=None,
        params={"_created_by_user_id": 12, "match_ids": [8]},
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
        created_at=datetime.now(timezone.utc),
    )
    queued_run = SimpleNamespace(
        id=501,
        task_type="scrape_job",
        status="queued",
        scheduled_job_id=None,
        scrape_job_id=35,
        artifacts={"_created_by_user_id": 12},
    )

    async def fake_create(db, match_ids, *, user_id):
        assert match_ids == [8]
        assert user_id == 12
        return job

    async def fake_enqueue(db, *, scrape_job_id, triggered_by, user_id):
        assert (scrape_job_id, triggered_by, user_id) == (35, "api", 12)
        return queued_run

    monkeypatch.setattr(data_api, "create_result_refresh_job", fake_create)
    monkeypatch.setattr(data_api, "enqueue_scrape_job_execution", fake_enqueue)
    monkeypatch.setattr(data_api, "taskiq_queue_enabled", lambda: True)

    response = await data_api.refresh_match_results(
        ResultRefreshRequest(match_ids=[8]),
        BackgroundTasks(),
        db=object(),
        user=SimpleNamespace(id=12),
    )

    assert response.id == 35
    assert response.status == "pending"
    assert response.queued_run_id == 501
    assert response.queued_run.status == "queued"


@pytest.mark.asyncio
async def test_non_owner_cannot_get_execute_or_read_scrape_logs(monkeypatch):
    job = SimpleNamespace(id=8, params={"_created_by_user_id": 99})

    class _DB:
        async def get(self, _model, _job_id):
            return job

    async def should_not_execute(*_args, **_kwargs):
        raise AssertionError("non-owner must be rejected before execution")

    monkeypatch.setattr(data_api, "execute_scrape_job", should_not_execute)
    user = SimpleNamespace(id=12, is_admin=False)

    for call in (
        lambda: data_api.get_scrape_job(job.id, db=_DB(), user=user),
        lambda: data_api.run_scrape_job(job.id, db=_DB(), user=user),
        lambda: data_api.get_scrape_job_logs(job.id, db=_DB(), user=user),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await call()
        assert exc_info.value.status_code == 403
