from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.job import ScheduledJob, ScheduledJobRun
from app.services import scheduled_jobs
from app.services.result_settlement import SettlementRunSummary
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
async def test_dispatch_scrape_job_propagates_failed_execution(monkeypatch):
    async def fake_create_scrape_job(db, job_type, league, params):
        return SimpleNamespace(id=45)

    async def fake_execute_scrape_job(db, job_id):
        return SimpleNamespace(id=job_id, status="failed", error="bridge timeout")

    monkeypatch.setattr(scheduled_jobs, "create_scrape_job", fake_create_scrape_job)
    monkeypatch.setattr(scheduled_jobs, "execute_scrape_job", fake_execute_scrape_job)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(id=70, task_type="scrape_odds", config={"league": "world-cup", "params": {"command": "noop"}}),
    )

    assert result.status == "failed"
    assert result.detail == "scrape_job:45; status:failed; error:bridge timeout"


@pytest.mark.asyncio
async def test_scheduled_scrape_persists_degraded_report_and_finishes_partial(monkeypatch):
    job = SimpleNamespace(
        id=7,
        task_type="scrape_odds",
        config={"league": "romania", "params": {"command": "upcoming"}},
    )
    run = SimpleNamespace(
        id=73,
        scheduled_job_id=job.id,
        task_type="scrape_odds",
        status="queued",
        started_at=None,
        finished_at=None,
        heartbeat_at=None,
        lease_expires_at=None,
        next_attempt_at=None,
        attempt=1,
        max_attempts=3,
        error=None,
        detail=None,
        duration_ms=None,
        artifacts=None,
    )

    class ServiceDb:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        async def get(self, model, row_id):
            if model is ScheduledJobRun and row_id == run.id:
                return run
            if model is ScheduledJob and row_id == job.id:
                return job
            return None

        async def flush(self):
            return None

        async def commit(self):
            return None

    db = ServiceDb()

    class SessionManager:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

    async def fake_create_scrape_job(_db, _job_type, _league, _params):
        return SimpleNamespace(id=81)

    async def fake_execute_scrape_job(_db, job_id):
        return SimpleNamespace(
            id=job_id,
            status="completed",
            output='{"scrape_report":{"health":"degraded","failure_count":1}}',
            error=None,
        )

    async def fake_claim(_db, run_id, *, lease_seconds=None):
        assert run_id == run.id
        assert lease_seconds is not None
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        return run

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", SessionManager)
    monkeypatch.setattr(scheduled_jobs, "claim_queued_task_run", fake_claim)
    monkeypatch.setattr(scheduled_jobs, "create_scrape_job", fake_create_scrape_job)
    monkeypatch.setattr(scheduled_jobs, "execute_scrape_job", fake_execute_scrape_job)

    result = await scheduled_jobs.execute_scheduled_job_run(run.id)

    assert result.status == "partial"
    assert result.artifacts == {
        "scrape_job_ids": [81],
        "scrape_report": {"health": "degraded", "failure_count": 1},
    }
    assert run.finished_at is not None


@pytest.mark.asyncio
async def test_dispatch_prediction_job_skips_without_owner():
    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(id=8, task_type="run_predictions", config={"strategy_ids": [1]}),
    )

    assert result.status == "skipped"
    assert result.detail == "missing_user_id"


@pytest.mark.asyncio
async def test_dispatch_scrape_then_predict_job_runs_in_order(monkeypatch):
    calls = []

    async def fake_scrape(db, job):
        calls.append(("scrape", job.id, job.task_type))
        return SimpleNamespace(job_id=job.id, task_type=job.task_type, status="completed", detail="scrape_job:19")

    async def fake_predict(db, job, *, config_override=None):
        calls.append(("predict", job.id))
        assert config_override == {"strategy_ids": [5], SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42}
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="summary[completed:1]; 5:completed:77",
            artifacts={"prediction_run_ids": [77]},
        )

    monkeypatch.setattr(scheduled_jobs, "_run_scrape_job", fake_scrape)
    monkeypatch.setattr(scheduled_jobs, "_run_prediction_job", fake_predict)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(
            id=9,
            task_type="scrape_then_predict",
            config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "strategy_ids": [5]},
        ),
    )

    assert result.status == "completed"
    assert result.detail == "scrape_job:19; predictions:summary[completed:1]; 5:completed:77"
    assert calls == [("scrape", 9, "scrape_odds"), ("predict", 9)]


@pytest.mark.asyncio
async def test_dispatch_prediction_job_reports_no_matches_truthfully(monkeypatch):
    class FakeDb:
        async def get(self, model, user_id):
            assert user_id == 12
            return SimpleNamespace(id=12)

    async def fake_run_strategy(*, strategy_id, body, db, user):
        assert strategy_id == 5
        return SimpleNamespace(status="no_matches", run_id=0)

    monkeypatch.setattr("app.api.v1.strategies.run_strategy", fake_run_strategy)

    result = await dispatch_scheduled_job(
        FakeDb(),
        SimpleNamespace(id=15, task_type="run_predictions", config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 12, "strategy_ids": [5]}),
    )

    assert result.status == "skipped"
    assert result.detail == "summary[no_matches:1]; 5:no_matches:0"


@pytest.mark.asyncio
async def test_dispatch_scrape_predict_tickets_job_stops_before_tickets_when_predictions_are_partial(monkeypatch):
    calls = []

    async def fake_scrape(db, job):
        calls.append(("scrape", job.id))
        return SimpleNamespace(job_id=job.id, task_type=job.task_type, status="completed", detail="scrape_job:90")

    async def fake_predict(db, job, *, config_override=None):
        calls.append(("predict", job.id, config_override))
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="partial",
            detail="summary[completed:1, no_matches:1]; 4:completed:91, 5:no_matches:0",
            artifacts={"prediction_run_ids": [91]},
        )

    async def fake_tickets(db, job, *, config_override=None):
        calls.append(("tickets", job.id, config_override))
        return SimpleNamespace(job_id=job.id, task_type=job.task_type, status="completed", detail="ticket_batch:12; tickets:2")

    monkeypatch.setattr(scheduled_jobs, "_run_scrape_job", fake_scrape)
    monkeypatch.setattr(scheduled_jobs, "_run_prediction_job", fake_predict)
    monkeypatch.setattr(scheduled_jobs, "_run_ticket_generation_job", fake_tickets)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(
            id=16,
            task_type="scrape_predict_tickets",
            config={
                SCHEDULED_JOB_OWNER_CONFIG_KEY: 42,
                "prediction": {"strategy_ids": [4, 5]},
                "tickets": {"ticket_count": 2, "difficulty": "safe"},
            },
        ),
    )

    assert result.status == "partial"
    assert result.detail == "scrape_job:90; predictions:summary[completed:1, no_matches:1]; 4:completed:91, 5:no_matches:0"
    assert calls == [
        ("scrape", 16),
        ("predict", 16, {"strategy_ids": [4, 5], SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42}),
    ]


@pytest.mark.asyncio
async def test_dispatch_verification_and_settlement_job_skips_without_owner():
    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(id=10, task_type="verify_and_settle", config={}),
    )

    assert result.status == "skipped"
    assert result.detail == "missing_user_id"


@pytest.mark.asyncio
async def test_dispatch_verification_and_settlement_job_runs_both_paths(monkeypatch):
    class FakeScalarResult:
        def all(self):
            return [
                SimpleNamespace(id=1, status="won"),
                SimpleNamespace(id=2, status="pending"),
                SimpleNamespace(id=3, status="lost"),
            ]

    class FakeResult:
        def scalars(self):
            return FakeScalarResult()

    class FakeDb:
        async def get(self, model, user_id):
            assert user_id == 12
            return SimpleNamespace(id=12)

        async def execute(self, stmt):
            return FakeResult()

    def fake_evaluate_model_prediction(prediction):
        return SimpleNamespace(status=prediction.status)

    async def fake_settle_due_tickets(db, *, user_id, now=None, unsupported_policy="pending", limit=100):
        assert user_id == 12
        assert unsupported_policy == "void"
        assert limit == 25
        return SettlementRunSummary(
            checked_tickets=4,
            settled_tickets=3,
            won_tickets=1,
            lost_tickets=1,
            void_tickets=1,
            pending_tickets=1,
            updated_legs=5,
        )

    monkeypatch.setattr(scheduled_jobs, "evaluate_model_prediction", fake_evaluate_model_prediction)
    monkeypatch.setattr(scheduled_jobs, "settle_due_tickets", fake_settle_due_tickets)

    result = await dispatch_scheduled_job(
        FakeDb(),
        SimpleNamespace(
            id=11,
            task_type="verify_and_settle",
            config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 12, "unsupported_policy": "void", "ticket_limit": 25},
        ),
    )

    assert result.status == "completed"
    assert (
        result.detail
        == "predictions=3 checked, 1 won, 1 lost, 1 pending, 0 void, 0 unsupported; "
        "tickets=4 checked, 3 settled, 1 pending, 5 legs_updated"
    )


@pytest.mark.asyncio
async def test_dispatch_world_cup_pipeline_job_uses_pipeline_service(monkeypatch):
    from app.services import world_cup_pipeline

    class FakeDb:
        async def get(self, model, user_id):
            assert user_id == 7
            return SimpleNamespace(id=7)

    async def fake_run_world_cup_pipeline(
        db,
        *,
        user_id,
        parent_job_id,
        future_days,
        history_years,
        all_markets,
        odds_history,
        max_historic_pages,
        max_historic_seasons,
        upcoming_timeout_seconds,
        historic_timeout_seconds,
        scraper_engine,
        ticket_count,
        ticket_stake,
        create_tickets,
        allow_experimental_tickets,
        training_limit,
        target_date,
        target_date_from,
        target_date_to,
    ):
        assert user_id == 7
        assert parent_job_id is None
        assert future_days == 3
        assert ticket_count == 4
        return {
            "summary": {
                "scrape_jobs": 5,
                "completed_scrape_jobs": 4,
                "prediction_runs": 4,
                "completed_prediction_runs": 2,
                "partial_prediction_runs": 1,
                "created_tickets": 6,
            }
        }

    monkeypatch.setattr(world_cup_pipeline, "run_world_cup_pipeline", fake_run_world_cup_pipeline)

    result = await dispatch_scheduled_job(
        FakeDb(),
        SimpleNamespace(
            id=12,
            task_type="world_cup_pipeline",
            config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 7, "future_days": 3, "ticket_count": 4},
        ),
    )

    assert result.status == "completed"
    assert result.detail == "scrape_jobs:4/5, prediction_runs:3/4, tickets:6"


@pytest.mark.asyncio
async def test_dispatch_ticket_generation_job_uses_ticket_engine(monkeypatch):
    class FakeDb:
        async def get(self, model, user_id):
            assert user_id == 21
            return SimpleNamespace(id=21)

    async def fake_generate_tickets(
        db,
        *,
        user_id,
        bankroll_id,
        ticket_count,
        difficulty,
        market_types,
        min_odds,
        max_odds,
        stake,
        run_id,
    ):
        assert user_id == 21
        assert bankroll_id == 9
        assert ticket_count == 3
        assert difficulty == "balanced"
        assert market_types == ["1x2", "btts"]
        assert min_odds == 1.2
        assert max_odds == 4.5
        assert stake == 12.0
        assert run_id is None
        return SimpleNamespace(id=55), [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)]

    monkeypatch.setattr(scheduled_jobs, "generate_tickets", fake_generate_tickets)

    result = await dispatch_scheduled_job(
        FakeDb(),
        SimpleNamespace(
            id=13,
            task_type="generate_tickets",
            config={
                SCHEDULED_JOB_OWNER_CONFIG_KEY: 21,
                "bankroll_id": 9,
                "ticket_count": 3,
                "difficulty": "balanced",
                "market_types": ["1x2", "btts"],
                "min_odds": 1.2,
                "max_odds": 4.5,
                "stake": 12.0,
            },
        ),
    )

    assert result.status == "completed"
    assert result.detail == "ticket_batch:55; tickets:3"


@pytest.mark.asyncio
async def test_dispatch_scrape_predict_tickets_job_runs_full_chain(monkeypatch):
    calls = []

    async def fake_scrape(db, job):
        calls.append(("scrape", job.id))
        return SimpleNamespace(job_id=job.id, task_type=job.task_type, status="completed", detail="scrape_job:88")

    async def fake_predict(db, job, *, config_override=None):
        calls.append(("predict", job.id, config_override))
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="summary[completed:1]; 4:completed:91",
            artifacts={"prediction_run_ids": [91]},
        )

    async def fake_tickets(db, job, *, config_override=None):
        calls.append(("tickets", job.id, config_override))
        return SimpleNamespace(job_id=job.id, task_type=job.task_type, status="completed", detail="ticket_batch:12; tickets:2")

    monkeypatch.setattr(scheduled_jobs, "_run_scrape_job", fake_scrape)
    monkeypatch.setattr(scheduled_jobs, "_run_prediction_job", fake_predict)
    monkeypatch.setattr(scheduled_jobs, "_run_ticket_generation_job", fake_tickets)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(
            id=14,
            task_type="scrape_predict_tickets",
            config={
                SCHEDULED_JOB_OWNER_CONFIG_KEY: 42,
                "prediction": {"strategy_ids": [4]},
                "tickets": {"ticket_count": 2, "difficulty": "safe"},
            },
        ),
    )

    assert result.status == "completed"
    assert result.detail == "scrape_job:88; predictions:summary[completed:1]; 4:completed:91; ticket_batch:12; tickets:2"
    assert calls == [
        ("scrape", 14),
        ("predict", 14, {"strategy_ids": [4], SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42}),
        ("tickets", 14, {"ticket_count": 2, "difficulty": "safe", SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42, "run_id": 91}),
    ]


@pytest.mark.asyncio
async def test_dispatch_scrape_predict_tickets_job_stops_when_prediction_run_is_ambiguous(monkeypatch):
    calls = []

    async def fake_scrape(db, job):
        calls.append(("scrape", job.id))
        return SimpleNamespace(job_id=job.id, task_type=job.task_type, status="completed", detail="scrape_job:88")

    async def fake_predict(db, job, *, config_override=None):
        calls.append(("predict", job.id, config_override))
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="summary[completed:2]; 4:completed:91, 5:completed:92",
            artifacts={"prediction_run_ids": [91, 92]},
        )

    async def fake_tickets(db, job, *, config_override=None):
        calls.append(("tickets", job.id, config_override))
        return SimpleNamespace(job_id=job.id, task_type=job.task_type, status="completed", detail="ticket_batch:12; tickets:2")

    monkeypatch.setattr(scheduled_jobs, "_run_scrape_job", fake_scrape)
    monkeypatch.setattr(scheduled_jobs, "_run_prediction_job", fake_predict)
    monkeypatch.setattr(scheduled_jobs, "_run_ticket_generation_job", fake_tickets)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(
            id=71,
            task_type="scrape_predict_tickets",
            config={
                SCHEDULED_JOB_OWNER_CONFIG_KEY: 42,
                "prediction": {"strategy_ids": [4, 5]},
                "tickets": {"ticket_count": 2, "difficulty": "safe"},
            },
        ),
    )

    assert result.status == "partial"
    assert (
        result.detail
        == "scrape_job:88; predictions:summary[completed:2]; 4:completed:91, 5:completed:92; "
        "tickets:missing_or_ambiguous_prediction_run_id"
    )
    assert calls == [
        ("scrape", 71),
        ("predict", 71, {"strategy_ids": [4, 5], SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42}),
    ]
