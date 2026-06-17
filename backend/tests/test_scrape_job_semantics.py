import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import scraper
from app.services.python_bridge import BridgeError


class _FakeSession:
    def __init__(self, job=None):
        self.job = job
        self.flush_calls = 0

    async def get(self, model, pk):
        if self.job is not None and pk == getattr(self.job, "id", None):
            return self.job
        return None

    async def flush(self):
        self.flush_calls += 1


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

    async def fake_bridge(args, label):
        assert "--sport" in args
        assert label == "scrape_job_5"
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

    async def fake_bridge(args, label):
        raise BridgeError("OddsHarvester bridge failed")

    monkeypatch.setattr(scraper, "run_oddsharvester_json", fake_bridge)

    result = await scraper.execute_scrape_job(db, 8)

    assert result is job
    assert job.status == "failed"
    assert job.error == "OddsHarvester bridge failed"
    assert job.output is None
    assert job.started_at is not None
    assert job.completed_at is not None


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
        },
    )

    args = scraper._build_oddsharvester_args(job)

    assert args[:3] == ["historic", "--sport", "football"]
    assert ["--league", "world-cup"] == args[3:5]
    assert "--season" in args
    assert args[args.index("--season") + 1] == "2022"
    assert "--max-pages" in args
    assert "--odds-history" in args
    assert "--headless" in args
    assert "--market" in args
    markets = args[args.index("--market") + 1].split(",")
    assert "1x2" in markets
    assert "btts" in markets
    assert "over_under_2_5" in markets
    assert "double_chance" in markets
    assert "asian_handicap_0" in markets
