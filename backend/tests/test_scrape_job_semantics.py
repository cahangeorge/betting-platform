import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import make_transient_to_detached

from app.models.match import Match
from app.services import scraper
from app.services.python_bridge import BridgeError


class _FakeSession:
    def __init__(self, job=None, duplicate_jobs=None):
        self.job = job
        self.duplicate_jobs = duplicate_jobs or []
        self.added = []
        self.flush_calls = 0
        self.get_calls = 0
        self.commit_calls = 0

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def get(self, model, pk):
        self.get_calls += 1
        if self.job is not None and pk == getattr(self.job, "id", None):
            return self.job
        return None

    async def commit(self):
        self.commit_calls += 1

    async def flush(self):
        self.flush_calls += 1

    async def execute(self, stmt):
        return _FakeExecuteResult(self.duplicate_jobs)


class _FakeExecuteResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return _FakeScalarResult(self.rows)


class _FakeScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


def test_build_match_update_payload_does_not_refresh_unloaded_updated_at():
    match_date = datetime(2026, 7, 13, 18, 30)
    match = Match(
        id=44,
        external_id="argentina-44",
        sport="football",
        competition="Primera Nacional",
        home_team="Home",
        away_team="Away",
        home_score=1,
        away_score=0,
        status="finished",
        match_date=match_date,
    )
    make_transient_to_detached(match)
    assert "updated_at" in inspect(match).unloaded

    payload = scraper._build_match_update_payload(match)

    assert payload == {
        "id": 44,
        "external_id": "argentina-44",
        "sport": "football",
        "competition": "Primera Nacional",
        "home_team": "Home",
        "away_team": "Away",
        "home_score": 1,
        "away_score": 0,
        "status": "finished",
        "match_date": "2026-07-13T18:30:00",
        "updated_at": None,
    }


@pytest.mark.asyncio
async def test_execute_scrape_job_completes_and_persists_ingestion_summary(monkeypatch):
    job = SimpleNamespace(
        id=5,
        job_type="oddsportal",
        status="pending",
        league="Premier League",
        params={"sport": "football"},
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
    )
    db = _FakeSession(job=job)

    async def fake_bridge(args, label, *, timeout=None):
        assert "--sport" in args
        assert label == "scrape_job_5"
        assert timeout is None
        return [{"home_team": "A", "away_team": "B"}]

    async def fake_ingest(session, bound_job, payload):
        assert session is db
        assert bound_job is job
        assert payload == [{"home_team": "A", "away_team": "B"}]
        return {"dataset_id": 21, "matches_count": 1, "matches_upserted": 1, "odds_written": 2}

    monkeypatch.setattr(scraper, "run_oddsharvester_json", fake_bridge)
    monkeypatch.setattr(scraper, "_ingest_scraped_payload", fake_ingest)

    result = await scraper.execute_scrape_job(db, 5)

    assert result is job
    assert job.status == "completed"
    assert json.loads(job.output) == {
        "dataset_id": 21,
        "matches_count": 1,
        "matches_upserted": 1,
        "odds_written": 2,
    }
    assert isinstance(job.started_at, datetime)
    assert isinstance(job.completed_at, datetime)
    assert job.error is None
    assert db.flush_calls >= 2
    assert db.commit_calls == 1
    assert db.get_calls >= 2
    log_actions = [obj.action for obj in db.added if obj.__class__.__name__ == "ScrapeJobLog"]
    assert log_actions == ["job_started", "engine_selected", "bridge_invocation", "job_completed"]


@pytest.mark.asyncio
async def test_execute_scrape_job_raises_lookup_for_missing_job():
    db = _FakeSession(job=None)

    with pytest.raises(LookupError, match="ScrapeJob 99 not found"):
        await scraper.execute_scrape_job(db, 99)


@pytest.mark.asyncio
async def test_execute_scrape_job_marks_failed_on_bridge_error(monkeypatch):
    job = SimpleNamespace(
        id=8,
        job_type="oddsportal",
        status="pending",
        league=None,
        params={"sport": "football"},
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
    )
    db = _FakeSession(job=job)

    async def fake_bridge(args, label, *, timeout=None):
        assert timeout is None
        raise BridgeError("OddsHarvester bridge failed")

    monkeypatch.setattr(scraper, "run_oddsharvester_json", fake_bridge)

    result = await scraper.execute_scrape_job(db, 8)

    assert result is job
    assert job.status == "failed"
    assert job.error == "OddsHarvester bridge failed"
    assert job.output is None
    assert job.started_at is not None
    assert job.completed_at is not None
    log_actions = [obj.action for obj in db.added if obj.__class__.__name__ == "ScrapeJobLog"]
    assert log_actions == ["job_started", "engine_selected", "bridge_invocation", "job_failed"]


@pytest.mark.asyncio
async def test_execute_scrape_job_skips_duplicate_when_avoid_rescraping_requested(monkeypatch):
    duplicate = SimpleNamespace(
        id=3,
        job_type="scrape_odds",
        status="completed",
        league="world-cup",
        params={"command": "historic", "season": "2022", "leagues": ["world-cup"], "sport": "football"},
        output='{"dataset_id": 17, "scrape_report": {"health": "degraded", "failure_count": 1}}',
    )
    job = SimpleNamespace(
        id=9,
        job_type="scrape_odds",
        status="pending",
        league="world-cup",
        params={
            "dedup_skip_requested": True,
            "command": "historic",
            "season": "2022",
            "leagues": ["world-cup"],
            "sport": "football",
        },
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
    )
    db = _FakeSession(job=job, duplicate_jobs=[duplicate])

    async def fail_bridge(args, label, *, timeout=None):
        assert timeout is None
        raise AssertionError("scraper bridge should not run for duplicate jobs")

    monkeypatch.setattr(scraper, "run_oddsharvester_json", fail_bridge)

    result = await scraper.execute_scrape_job(db, 9)

    assert result is job
    assert job.status == "completed"
    assert json.loads(job.output) == {
        "skipped": True,
        "reason": "duplicate_completed_job",
        "reused_job_id": 3,
        "dataset_id": 17,
        "scrape_report": {"health": "degraded", "failure_count": 1},
    }
    assert job.completed_at is not None
    log_actions = [obj.action for obj in db.added if obj.__class__.__name__ == "ScrapeJobLog"]
    assert log_actions == ["job_started", "rescrape_skipped"]


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ('{"dataset_id": "17"}', 17),
        ('{"dataset_id": 0}', None),
        ('{"dataset_id": "invalid"}', None),
        ('{"reused_job_id": 3}', None),
        ("not-json", None),
    ],
)
def test_scrape_output_dataset_id_fails_closed(output, expected):
    assert scraper._scrape_output_dataset_id(SimpleNamespace(output=output)) == expected


def test_build_oddsharvester_args_supports_historic_all_markets():
    job = SimpleNamespace(
        league="world-cup",
        params={
            "command": "historic",
            "sport": "football",
            "leagues": ["world-cup"],
            "season": "2022",
            "all_markets": True,
            "odds_history": True,
            "headless": True,
            "bookies_filter": "all",
            "max_pages": 4,
            "concurrency": 2,
            "request_delay": 1.0,
            "preview_submarkets_only": True,
        },
    )

    args = scraper._build_oddsharvester_args(job)

    assert args[:3] == ["historic", "--sport", "football"]
    assert ["--league", "world-cup"] == args[3:5]
    assert "--season" in args
    assert args[args.index("--season") + 1] == "2022"
    assert "--max-pages" in args
    assert "--odds-history" in args
    assert "--preview-only" in args
    assert "--headless" in args
    assert "--market" in args
    markets = args[args.index("--market") + 1].split(",")
    assert "1x2" in markets
    assert "btts" in markets
    assert "over_under_2_5" in markets
    assert "double_chance" in markets
    assert "asian_handicap_0" in markets


def test_build_oddsharvester_args_forwards_scraper_engine():
    job = SimpleNamespace(
        league="world-cup",
        params={
            "command": "upcoming",
            "sport": "football",
            "leagues": ["world-cup"],
            "date": "20260625",
            "scraper_engine": "auto",
        },
    )

    args = scraper._build_oddsharvester_args(job)

    assert "--engine" in args
    assert args[args.index("--engine") + 1] == "auto"


@pytest.mark.asyncio
async def test_execute_scrape_job_passes_per_job_timeout_to_oddsharvester(monkeypatch):
    job = SimpleNamespace(
        id=12,
        job_type="scrape_odds",
        status="pending",
        league="world-cup",
        params={
            "command": "historic",
            "sport": "football",
            "leagues": ["world-cup"],
            "season": "2018",
            "timeout_seconds": 2400,
        },
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
    )
    db = _FakeSession(job=job)

    async def fake_bridge(args, label, *, timeout=None):
        assert label == "scrape_job_12"
        assert timeout == 2400
        assert args[:3] == ["historic", "--sport", "football"]
        return [{"home_team": "A", "away_team": "B"}]

    async def fake_ingest(_session, _job, _payload):
        return {"dataset_id": 99, "matches_count": 1, "matches_upserted": 1, "odds_written": 0}

    monkeypatch.setattr(scraper, "run_oddsharvester_json", fake_bridge)
    monkeypatch.setattr(scraper, "_ingest_scraped_payload", fake_ingest)

    result = await scraper.execute_scrape_job(db, 12)

    assert result.status == "completed"
    bridge_logs = [obj for obj in db.added if getattr(obj, "action", None) == "bridge_invocation"]
    assert bridge_logs[0].metadata_json["timeout_seconds"] == 2400
