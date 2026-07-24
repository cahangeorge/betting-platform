import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import world_cup_pipeline


def test_recent_world_cup_seasons_uses_last_ten_years():
    seasons = world_cup_pipeline.recent_world_cup_seasons(
        10,
        today=datetime(2026, 6, 17, tzinfo=timezone.utc),
    )

    assert seasons == [2022, 2018]


def test_recent_world_cup_seasons_supports_older_tournaments_newest_first():
    seasons = world_cup_pipeline.recent_world_cup_seasons(
        28,
        today=datetime(2026, 6, 17, tzinfo=timezone.utc),
    )

    assert seasons == [2022, 2018, 2014, 2010, 2006, 2002, 1998]


def test_recent_world_cup_seasons_allows_zero_history_to_skip_historic_scrapes():
    seasons = world_cup_pipeline.recent_world_cup_seasons(
        0,
        today=datetime(2026, 6, 17, tzinfo=timezone.utc),
    )

    assert seasons == []


def test_selected_world_cup_seasons_can_limit_long_backfills():
    seasons = world_cup_pipeline.selected_world_cup_seasons(
        28,
        max_historic_seasons=2,
        today=datetime(2026, 6, 17, tzinfo=timezone.utc),
    )

    assert seasons == [2022, 2018]


def test_expensive_upcoming_world_cup_scrapes_get_longer_timeout():
    assert world_cup_pipeline._world_cup_upcoming_timeout(all_markets=True, odds_history=False) == 1800
    assert world_cup_pipeline._world_cup_upcoming_timeout(all_markets=False, odds_history=True) == 1800
    assert world_cup_pipeline._world_cup_upcoming_timeout(all_markets=False, odds_history=False) is None
    assert (
        world_cup_pipeline._world_cup_upcoming_timeout(
            all_markets=True,
            odds_history=True,
            timeout_seconds=900,
        )
        == 900
    )


def test_world_cup_historic_pages_uses_safe_minimum():
    assert world_cup_pipeline._world_cup_historic_max_pages(None) == 3
    assert world_cup_pipeline._world_cup_historic_max_pages(1) == 3
    assert world_cup_pipeline._world_cup_historic_max_pages(5) == 5


def test_market_matching_accepts_prediction_aliases():
    assert world_cup_pipeline._market_matches("ou_2_5", "over_under_2_5:full_time")
    assert world_cup_pipeline._market_matches("1x2", "1x2:full_time")
    assert world_cup_pipeline._market_matches("btts", "btts:full_time")


def test_parse_pipeline_datetime_accepts_browser_iso_offsets():
    parsed = world_cup_pipeline._parse_pipeline_datetime("2026-06-20T21:00:00.000+03:00")

    assert parsed.isoformat() == "2026-06-20T18:00:00+00:00"


def test_pipeline_errors_include_partial_prediction_runs():
    errors = world_cup_pipeline._pipeline_errors(
        [SimpleNamespace(id=1, status="completed", error=None)],
        [
            SimpleNamespace(id=7, status="partial", error='{"failed": 1}'),
            SimpleNamespace(id=8, status="completed", error=None),
        ],
    )

    assert errors == [{"type": "prediction", "id": 7, "error": '{"failed": 1}'}]


def test_best_odds_for_selection_uses_matching_market_and_best_price():
    odds_entries = [
        SimpleNamespace(
            market="over_under_2_5:full_time", home_odds=1.91, draw_odds=None, away_odds=1.86, bookmaker="A"
        ),
        SimpleNamespace(
            market="over_under_2_5:full_time", home_odds=1.95, draw_odds=None, away_odds=1.82, bookmaker="B"
        ),
        SimpleNamespace(market="1x2:full_time", home_odds=2.0, draw_odds=3.2, away_odds=4.0, bookmaker="C"),
    ]

    odds, bookmaker = world_cup_pipeline._best_odds_for_selection("ou_2_5", "over", odds_entries)

    assert odds == 1.95
    assert bookmaker == "B"


def test_build_difficulty_ticket_tiers_creates_seven_top_lists():
    candidates = [
        {
            "match_id": index,
            "match": f"Team {index}A vs Team {index}B",
            "league": "World Cup",
            "kickoff": None,
            "market": "1x2",
            "selection": "home",
            "probability": 0.8 - index * 0.01,
            "odds": 1.4 + index * 0.05,
            "bookmaker": "Book",
            "model_types": ["PoissonGoalsModel"],
            "model_prediction_id": index,
            "expected_return_score": (0.8 - index * 0.01) * (1.4 + index * 0.05),
        }
        for index in range(1, 10)
    ]

    tiers = world_cup_pipeline._build_difficulty_ticket_tiers(candidates, per_tier_count=10)

    assert [tier["level"] for tier in tiers] == [1, 2, 3, 4, 5, 6, 7]
    assert len(tiers[0]["tickets"]) == 9
    assert len(tiers[6]["tickets"]) == 10
    assert tiers[0]["tickets"][0]["ticket_type"] == "single"
    assert tiers[6]["tickets"][0]["ticket_type"] == "accumulator"
    assert tiers[6]["tickets"][0]["leg_count"] == 7
    assert len({leg["match_id"] for leg in tiers[6]["tickets"][0]["legs"]}) == 7


@pytest.mark.asyncio
async def test_publish_pipeline_progress_writes_parent_output_and_commits():
    class _DB:
        def __init__(self, parent):
            self.parent = parent
            self.commits = 0

        async def get(self, model, job_id):
            assert model.__name__ == "ScrapeJob"
            assert job_id == self.parent.id
            return self.parent

        async def commit(self):
            self.commits += 1

    parent = SimpleNamespace(id=99, output=None)
    jobs = [
        SimpleNamespace(id=1, status="completed", error=None),
        SimpleNamespace(id=2, status="failed", error="timeout"),
        SimpleNamespace(id=3, status="running", error=None),
    ]
    runs = [SimpleNamespace(id=7, status="partial", error="1 target failed")]
    db = _DB(parent)

    await world_cup_pipeline._publish_pipeline_progress(
        db,
        99,
        stage="scraped_historic_2022",
        scrape_jobs=jobs,
        prediction_runs=runs,
        skipped_historic_seasons=[2026],
    )

    assert db.commits == 1
    assert '"stage": "scraped_historic_2022"' in parent.output
    assert '"completed_scrape_jobs": 1' in parent.output
    assert '"failed_scrape_jobs": 1' in parent.output
    assert '"running_scrape_jobs": 1' in parent.output
    assert '"skipped_historic_seasons": 1' in parent.output
    assert "timeout" in parent.output
    assert "1 target failed" in parent.output
    assert '"skipped_historic_seasons": [2026]' in parent.output


@pytest.mark.asyncio
async def test_run_scrape_jobs_publishes_running_subjobs_and_continues_after_historic_timeout(monkeypatch):
    class _DB:
        def __init__(self):
            self.flushes = 0

        async def flush(self):
            self.flushes += 1

    created_jobs = {}
    stages = []

    async def fake_create_scrape_job(_db, job_type, league, params):
        job = SimpleNamespace(
            id=len(created_jobs) + 1,
            job_type=job_type,
            league=league,
            params=params,
            status="pending",
            started_at=None,
            error=None,
        )
        created_jobs[job.id] = job
        return job

    async def fake_execute_scrape_job(_db, job_id):
        job = created_jobs[job_id]
        if job.params["command"] == "historic" and job.params["season"] == "2018":
            job.status = "failed"
            job.error = "OddsHarvester request timed out after 600s"
            return job
        job.status = "completed"
        return job

    async def fake_publish(_db, parent_job_id, *, stage, scrape_jobs=None, skipped_historic_seasons=None, **_kwargs):
        stages.append(
            {
                "parent_job_id": parent_job_id,
                "stage": stage,
                "statuses": [job.status for job in scrape_jobs or []],
                "seasons": [job.params.get("season") for job in scrape_jobs or []],
                "skipped": skipped_historic_seasons or [],
            }
        )

    monkeypatch.setattr(world_cup_pipeline, "create_scrape_job", fake_create_scrape_job)
    monkeypatch.setattr(world_cup_pipeline, "execute_scrape_job", fake_execute_scrape_job)
    monkeypatch.setattr(world_cup_pipeline, "_publish_pipeline_progress", fake_publish)
    monkeypatch.setattr(world_cup_pipeline, "recent_world_cup_seasons", lambda *_args, **_kwargs: [2022, 2018])

    jobs, skipped = await world_cup_pipeline._run_scrape_jobs(
        _DB(),
        future_days=1,
        history_years=10,
        all_markets=False,
        odds_history=False,
        max_historic_pages=1,
        parent_job_id=99,
    )

    assert [job.params["command"] for job in jobs] == ["upcoming", "historic", "historic"]
    assert all(job.params["scraper_engine"] == "playwright" for job in jobs)
    assert [job.params.get("season") for job in jobs if job.params["command"] == "historic"] == ["2022", "2018"]
    assert all((job.params.get("max_pages") or 0) >= 3 for job in jobs if job.params["command"] == "historic")
    assert all(
        job.params.get("timeout_seconds") == world_cup_pipeline.WORLD_CUP_HISTORIC_TIMEOUT_SECONDS
        for job in jobs
        if job.params["command"] == "historic"
    )
    assert skipped == []
    assert any(stage["stage"].startswith("scraping_upcoming_") and "running" in stage["statuses"] for stage in stages)
    assert any(stage["stage"] == "scraping_historic_2018" and "running" in stage["statuses"] for stage in stages)
    assert stages[-1]["stage"] == "historic_timeout_continuing_after_2018"
    assert stages[-1]["skipped"] == []


@pytest.mark.asyncio
async def test_run_scrape_jobs_bounds_historic_seasons_and_uses_timeout_overrides(monkeypatch):
    class _DB:
        async def flush(self):
            return None

    created_jobs = {}

    async def fake_create_scrape_job(_db, job_type, league, params):
        job = SimpleNamespace(
            id=len(created_jobs) + 1,
            job_type=job_type,
            league=league,
            params=params,
            status="pending",
            started_at=None,
            error=None,
        )
        created_jobs[job.id] = job
        return job

    async def fake_execute_scrape_job(_db, job_id):
        job = created_jobs[job_id]
        job.status = "completed"
        return job

    async def fake_publish(*_args, **_kwargs):
        return None

    monkeypatch.setattr(world_cup_pipeline, "create_scrape_job", fake_create_scrape_job)
    monkeypatch.setattr(world_cup_pipeline, "execute_scrape_job", fake_execute_scrape_job)
    monkeypatch.setattr(world_cup_pipeline, "_publish_pipeline_progress", fake_publish)
    monkeypatch.setattr(
        world_cup_pipeline,
        "recent_world_cup_seasons",
        lambda *_args, **_kwargs: [2022, 2018, 2014],
    )

    jobs, skipped = await world_cup_pipeline._run_scrape_jobs(
        _DB(),
        future_days=1,
        history_years=28,
        all_markets=True,
        odds_history=True,
        max_historic_pages=1,
        max_historic_seasons=1,
        upcoming_timeout_seconds=900,
        historic_timeout_seconds=120,
        parent_job_id=99,
        scraper_engine="auto",
    )

    assert [job.params["command"] for job in jobs] == ["upcoming", "historic"]
    assert all(job.params["scraper_engine"] == "auto" for job in jobs)
    assert jobs[0].params["timeout_seconds"] == 900
    assert jobs[1].params["season"] == "2022"
    assert jobs[1].params["max_pages"] == 3
    assert jobs[1].params["timeout_seconds"] == 120
    assert skipped == []


@pytest.mark.asyncio
async def test_run_scrape_jobs_uses_explicit_target_date(monkeypatch):
    class _DB:
        async def flush(self):
            return None

    created_params = []

    async def fake_create_scrape_job(_db, _job_type, _league, params):
        created_params.append(params)
        return SimpleNamespace(id=len(created_params), status="pending", params=params, error=None, started_at=None)

    async def fake_execute_scrape_job(_db, job_id):
        return SimpleNamespace(id=job_id, status="completed", params=created_params[job_id - 1], error=None)

    async def fake_publish(*_args, **_kwargs):
        return None

    monkeypatch.setattr(world_cup_pipeline, "create_scrape_job", fake_create_scrape_job)
    monkeypatch.setattr(world_cup_pipeline, "execute_scrape_job", fake_execute_scrape_job)
    monkeypatch.setattr(world_cup_pipeline, "_publish_pipeline_progress", fake_publish)
    monkeypatch.setattr(world_cup_pipeline, "recent_world_cup_seasons", lambda *_args, **_kwargs: [])

    jobs, skipped = await world_cup_pipeline._run_scrape_jobs(
        _DB(),
        future_days=7,
        history_years=1,
        all_markets=False,
        odds_history=False,
        max_historic_pages=1,
        target_date="2026-06-21",
        parent_job_id=99,
    )

    assert [job.params["date"] for job in jobs] == ["20260621"]
    assert skipped == []


@pytest.mark.asyncio
async def test_build_top_ticket_candidates_skips_unreliable_predictions():
    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def unique(self):
            return self

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

    class _DB:
        async def execute(self, _stmt):
            return _Result(predictions)

    odds_entries = [
        SimpleNamespace(market="1x2:FullTime", home_odds=2.1, draw_odds=3.4, away_odds=4.0, bookmaker="Book")
    ]
    match = SimpleNamespace(
        id=19,
        home_team="USA",
        away_team="Australia",
        competition="World Cup",
        match_date=None,
        odds=odds_entries,
    )
    predictions = [
        SimpleNamespace(
            id=1,
            match=match,
            market="1x2",
            home_prob=0.62,
            draw_prob=0.23,
            away_prob=0.15,
            model_type="PoissonGoalsModel",
            quality_report={"reliability": {"is_ticket_eligible": False, "label": "unreliable"}},
        )
    ]

    candidates = await world_cup_pipeline._build_top_ticket_candidates(_DB(), run_ids=[123], limit=10)

    assert candidates == []


@pytest.mark.asyncio
async def test_build_top_ticket_candidates_can_include_unreliable_watchlist():
    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def unique(self):
            return self

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

    class _DB:
        async def execute(self, _stmt):
            return _Result(predictions)

    odds_entries = [
        SimpleNamespace(market="1x2:FullTime", home_odds=2.1, draw_odds=3.4, away_odds=4.0, bookmaker="Book")
    ]
    match = SimpleNamespace(
        id=19,
        home_team="USA",
        away_team="Australia",
        competition="World Cup",
        match_date=None,
        odds=odds_entries,
    )
    predictions = [
        SimpleNamespace(
            id=1,
            match=match,
            market="1x2",
            home_prob=0.62,
            draw_prob=0.23,
            away_prob=0.15,
            model_type="PoissonGoalsModel",
            quality_report={
                "reliability": {
                    "is_ticket_eligible": False,
                    "label": "unreliable",
                    "score": 9,
                    "block_reasons": ["market_disagreement"],
                }
            },
        )
    ]

    candidates = await world_cup_pipeline._build_top_ticket_candidates(
        _DB(),
        run_ids=[123],
        limit=10,
        include_unreliable=True,
    )

    assert len(candidates) == 3
    assert candidates[0]["is_ticket_eligible"] is False
    assert candidates[0]["reliability"] == "unreliable"
    assert candidates[0]["quality_reasons"] == ["market_disagreement"]


@pytest.mark.asyncio
async def test_create_tiered_tickets_can_mark_experimental_watchlist(monkeypatch):
    class _DB:
        def __init__(self):
            self.added = []
            self.flushes = 0

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            self.flushes += 1
            for obj in self.added:
                if obj.__class__.__name__ == "TicketBatch" and getattr(obj, "id", None) is None:
                    obj.id = 123

    created_ticket = SimpleNamespace(id=77, batch_id=None, status="open")

    async def fake_create_ticket(**_kwargs):
        return created_ticket

    monkeypatch.setattr(world_cup_pipeline, "create_ticket", fake_create_ticket)

    ticket_ids = await world_cup_pipeline._create_tiered_tickets(
        _DB(),
        user_id=5,
        tiers=[
            {
                "tickets": [
                    {
                        "ticket_type": "single",
                        "legs": [
                            {
                                "model_prediction_id": 1,
                                "match_id": 10,
                                "selection": "home",
                                "market": "1x2",
                                "odds": 2.0,
                                "bookmaker": "Book",
                            }
                        ],
                    }
                ]
            }
        ],
        stake=10,
        batch_name="Experimental",
        strategy="world_cup_watchlist_experimental",
        ticket_status="watchlist",
    )

    assert ticket_ids == [77]
    assert created_ticket.batch_id == 123
    assert created_ticket.status == "watchlist"


@pytest.mark.asyncio
async def test_run_top_predictions_preserves_target_errors(monkeypatch):
    class _DB:
        def add(self, _row):
            pass

        async def flush(self):
            if not hasattr(run, "id"):
                run.id = 44

    async def fake_execute_single_model_run(**_kwargs):
        return {
            "target_matches": 2,
            "written": 1,
            "failed": 1,
            "target_errors": [{"match_id": 9, "error": "bridge failed"}],
        }

    run = None
    original_prediction_run = world_cup_pipeline.PredictionRun

    def fake_prediction_run(**kwargs):
        nonlocal run
        run = SimpleNamespace(**kwargs)
        return run

    monkeypatch.setattr(world_cup_pipeline, "PredictionRun", fake_prediction_run)
    monkeypatch.setattr(world_cup_pipeline, "execute_single_model_run", fake_execute_single_model_run)

    try:
        runs = await world_cup_pipeline._run_top_predictions(
            _DB(),
            user_id=1,
            target_match_ids=[9, 10],
            training_limit=120,
        )
    finally:
        monkeypatch.setattr(world_cup_pipeline, "PredictionRun", original_prediction_run)

    assert len(runs) == 4
    payload = json.loads(runs[0].error)
    assert payload["target_errors"] == [{"match_id": 9, "error": "bridge failed"}]


@pytest.mark.asyncio
async def test_execute_world_cup_pipeline_job_preserves_zero_history_years(monkeypatch):
    class _SessionManager:
        def __init__(self, db):
            self.db = db

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *_args):
            return None

    class _DB:
        def __init__(self, job):
            self.job = job
            self.commits = 0

        async def get(self, model, job_id):
            assert model.__name__ == "ScrapeJob"
            assert job_id == self.job.id
            return self.job

        async def commit(self):
            self.commits += 1

    captured_kwargs = {}
    job = SimpleNamespace(
        id=51,
        params={
            "future_days": 1,
            "history_years": 0,
            "all_markets": "false",
            "odds_history": "false",
            "create_tickets": "false",
            "allow_experimental_tickets": "false",
            "max_historic_pages": "3",
            "max_historic_seasons": "1",
            "upcoming_timeout_seconds": "900",
            "historic_timeout_seconds": "120",
            "scraper_engine": "auto",
        },
        status="pending",
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
    )
    db = _DB(job)

    async def fake_run_world_cup_pipeline(_db, **kwargs):
        captured_kwargs.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(world_cup_pipeline, "async_session_factory", lambda: _SessionManager(db))
    monkeypatch.setattr(world_cup_pipeline, "run_world_cup_pipeline", fake_run_world_cup_pipeline)

    await world_cup_pipeline.execute_world_cup_pipeline_job(job.id, user_id=7)

    assert captured_kwargs["history_years"] == 0
    assert captured_kwargs["all_markets"] is False
    assert captured_kwargs["odds_history"] is False
    assert captured_kwargs["create_tickets"] is False
    assert captured_kwargs["allow_experimental_tickets"] is False
    assert captured_kwargs["max_historic_pages"] == 3
    assert captured_kwargs["max_historic_seasons"] == 1
    assert captured_kwargs["upcoming_timeout_seconds"] == 900
    assert captured_kwargs["historic_timeout_seconds"] == 120
    assert captured_kwargs["scraper_engine"] == "auto"
    assert job.status == "completed"
    assert json.loads(job.output) == {"status": "completed"}
    assert db.commits == 2
