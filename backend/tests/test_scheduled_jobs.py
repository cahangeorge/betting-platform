from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import jobs as jobs_api
from app.models.job import ScheduledJob, ScheduledJobRun
from app.schemas.job import ScheduledJobCreateRequest
from app.services import scheduled_jobs
from app.services.result_settlement import SettlementRunSummary
from app.services.scheduled_jobs import (
    SCHEDULED_JOB_OWNER_CONFIG_KEY,
    SCHEDULED_JOB_QUARANTINE_CONFIG_KEY,
    dispatch_scheduled_job,
    enqueue_due_scheduled_jobs,
    next_run_from_cron,
    scheduled_job_due,
    stamp_created_by,
)


def test_next_run_from_ui_cron_patterns():
    base = datetime(2026, 6, 24, 10, 30, tzinfo=timezone.utc)

    assert next_run_from_cron("0 */6 * * *", after=base) == base + timedelta(hours=6)
    assert next_run_from_cron("0 0 */2 * *", after=base) == base + timedelta(days=2)
    with pytest.raises(ValueError, match="cron_expression"):
        next_run_from_cron("invalid", after=base)


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


def test_scrape_job_artifacts_exposes_created_dataset_for_downstream_lineage():
    artifacts = scheduled_jobs._scrape_job_artifacts(
        SimpleNamespace(
            id=88,
            output=(
                '{"skipped": true, "reused_job_id": 77, "dataset_id": 188, '
                '"scrape_report": {"health": "degraded"}}'
            ),
        )
    )

    assert artifacts == {
        "scrape_job_ids": [88],
        "dataset_ids": [188],
        "scrape_report": {"health": "degraded"},
    }
    assert scheduled_jobs._scrape_task_run_status("completed", artifacts) == "partial"


def test_create_request_rejects_spoofed_owner_and_invalid_task_input_before_persistence():
    with pytest.raises(ValidationError, match="ownership"):
        ScheduledJobCreateRequest(
            name="spoof",
            task_type="generate_tickets",
            cron_expression="0 */6 * * *",
            config={"_created_by_user_id": 999, "bankroll_id": 1},
        )
    with pytest.raises(ValidationError, match="Unsupported scheduled task type"):
        ScheduledJobCreateRequest(name="bad", task_type="shell", cron_expression="0 */6 * * *", config={})
    with pytest.raises(ValidationError, match="cron_expression"):
        ScheduledJobCreateRequest(name="bad", task_type="scrape_odds", cron_expression="* * * * *", config={})


def test_stamp_created_by_overwrites_a_cross_user_legacy_owner():
    config = stamp_created_by({SCHEDULED_JOB_OWNER_CONFIG_KEY: 999, "user_id": 999}, 12)

    assert config[SCHEDULED_JOB_OWNER_CONFIG_KEY] == 12
    assert "user_id" not in config


@pytest.mark.asyncio
async def test_non_admin_run_due_requires_an_owned_job_selector():
    with pytest.raises(HTTPException) as exc_info:
        await jobs_api.run_due_jobs(
            limit=10,
            job_id=None,
            db=SimpleNamespace(),
            user=SimpleNamespace(id=7, is_admin=False),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_run_due_scopes_non_admin_to_selected_owned_job(monkeypatch):
    job = SimpleNamespace(id=41, config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 7})

    class _Db:
        async def get(self, _model, job_id):
            return job if job_id == job.id else None

    async def fake_run_due(_db, *, limit, job_ids=None):
        assert limit == 10
        assert job_ids == [job.id]
        return []

    monkeypatch.setattr(jobs_api, "run_due_scheduled_jobs", fake_run_due)

    result = await jobs_api.run_due_jobs(
        limit=10,
        job_id=job.id,
        db=_Db(),
        user=SimpleNamespace(id=7, is_admin=False),
    )

    assert result == []


@pytest.mark.asyncio
async def test_non_admin_cannot_run_due_for_another_users_job(monkeypatch):
    job = SimpleNamespace(id=42, config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 8})

    class _Db:
        async def get(self, _model, _job_id):
            return job

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("foreign job must not be enqueued")

    monkeypatch.setattr(jobs_api, "run_due_scheduled_jobs", fail_if_called)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_api.run_due_jobs(
            limit=10,
            job_id=job.id,
            db=_Db(),
            user=SimpleNamespace(id=7, is_admin=False),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_invalid_legacy_cron_is_quarantined_without_blocking_other_due_jobs(monkeypatch):
    now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    invalid_job = SimpleNamespace(
        id=41,
        enabled=True,
        cron_expression="* * * * *",
        config={"area": "legacy"},
        next_run=now - timedelta(minutes=1),
        task_type="scrape_odds",
        last_run=None,
    )
    valid_job = SimpleNamespace(
        id=42,
        enabled=True,
        cron_expression="0 */6 * * *",
        config={"area": "current"},
        next_run=now - timedelta(minutes=1),
        task_type="scrape_odds",
        last_run=None,
    )
    run = SimpleNamespace(id=77, scheduled_job_id=valid_job.id, due_at=valid_job.next_run)

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [invalid_job, valid_job]

    class _Db:
        commits = 0
        flushes = 0

        async def execute(self, _statement):
            return _Result()

        async def flush(self):
            self.flushes += 1

        async def commit(self):
            self.commits += 1

    async def create_run(*_args, **_kwargs):
        return run

    async def create_outbox(*_args, **_kwargs):
        return SimpleNamespace()

    async def publish(*_args, **_kwargs):
        return None

    monkeypatch.setattr(scheduled_jobs, "create_task_run", create_run)
    monkeypatch.setattr(scheduled_jobs, "create_task_outbox", create_outbox)
    monkeypatch.setattr(scheduled_jobs, "_publish_outbox_entry", publish)

    db = _Db()
    runs = await enqueue_due_scheduled_jobs(db, now=now, limit=10, transport="inprocess")

    assert runs == [run]
    assert invalid_job.enabled is False
    assert invalid_job.next_run is None
    assert invalid_job.config[SCHEDULED_JOB_QUARANTINE_CONFIG_KEY]["code"] == "invalid_cron_expression"
    assert "cron_expression" in invalid_job.config[SCHEDULED_JOB_QUARANTINE_CONFIG_KEY]["detail"]
    assert valid_job.next_run == now + timedelta(hours=6)
    assert db.commits == 1


@pytest.mark.asyncio
async def test_downstream_value_error_does_not_quarantine_a_valid_scheduled_job(monkeypatch):
    now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id=43,
        enabled=True,
        cron_expression="0 */6 * * *",
        config={"area": "current"},
        next_run=now - timedelta(minutes=1),
        task_type="scrape_odds",
        last_run=None,
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [job]

    class _Db:
        async def execute(self, _statement):
            return _Result()

        async def flush(self):
            return None

        async def commit(self):
            raise AssertionError("valid downstream failures must not be committed as quarantines")

    async def fail_create_run(*_args, **_kwargs):
        raise ValueError("task payload is invalid")

    monkeypatch.setattr(scheduled_jobs, "create_task_run", fail_create_run)

    with pytest.raises(ValueError, match="task payload is invalid"):
        await enqueue_due_scheduled_jobs(_Db(), now=now, limit=10, transport="inprocess")

    assert job.enabled is True
    assert job.config == {"area": "current"}
    assert job.next_run == now - timedelta(minutes=1)


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
async def test_dispatch_owned_scrape_job_stamps_owner_into_created_scrape_params(monkeypatch):
    async def fake_create_scrape_job(db, job_type, league, params):
        assert params == {"command": "noop", SCHEDULED_JOB_OWNER_CONFIG_KEY: 12}
        return SimpleNamespace(id=46)

    async def fake_execute_scrape_job(db, job_id):
        return SimpleNamespace(id=job_id, status="completed")

    monkeypatch.setattr(scheduled_jobs, "create_scrape_job", fake_create_scrape_job)
    monkeypatch.setattr(scheduled_jobs, "execute_scrape_job", fake_execute_scrape_job)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(
            id=8,
            task_type="scrape_odds",
            config={
                SCHEDULED_JOB_OWNER_CONFIG_KEY: 12,
                "league": "world-cup",
                "params": {"command": "noop"},
            },
        ),
    )

    assert result.status == "completed"


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
        assert job.config[SCHEDULED_JOB_OWNER_CONFIG_KEY] == 42
        calls.append(("scrape", job.id, job.task_type))
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="scrape_job:19",
            artifacts={"dataset_ids": [119]},
        )

    async def fake_predict(db, job, *, config_override=None):
        calls.append(("predict", job.id))
        assert config_override == {
            "strategy_ids": [5],
            SCHEDULED_JOB_OWNER_CONFIG_KEY: 42,
            "user_id": 42,
            "dataset_id": 119,
        }
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
    assert result.artifacts == {"dataset_ids": [119], "prediction_run_ids": [77]}


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset_ids", [None, 119, [119, 120]])
async def test_dispatch_scrape_then_predict_job_stops_without_one_fresh_scrape_dataset(monkeypatch, dataset_ids):
    calls = []

    async def fake_scrape(db, job):
        assert job.config[SCHEDULED_JOB_OWNER_CONFIG_KEY] == 42
        calls.append(("scrape", job.id))
        artifacts = {} if dataset_ids is None else {"dataset_ids": dataset_ids}
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="scrape_job:119",
            artifacts=artifacts,
        )

    async def fail_prediction(*_args, **_kwargs):
        raise AssertionError("prediction must not run without exactly one fresh scrape dataset")

    monkeypatch.setattr(scheduled_jobs, "_run_scrape_job", fake_scrape)
    monkeypatch.setattr(scheduled_jobs, "_run_prediction_job", fail_prediction)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(
            id=119,
            task_type="scrape_then_predict",
            config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "prediction": {"strategy_ids": [5], "dataset_id": 999}},
        ),
    )

    assert result.status == "partial"
    assert result.detail == "scrape_job:119; predictions:missing_or_ambiguous_scrape_dataset_id"
    assert result.artifacts == ({} if dataset_ids is None else {"dataset_ids": dataset_ids})
    assert calls == [("scrape", 119)]


@pytest.mark.asyncio
async def test_dispatch_prediction_job_reports_no_matches_truthfully(monkeypatch):
    class FakeDb:
        async def get(self, model, user_id):
            assert user_id == 12
            return SimpleNamespace(id=12)

    async def fake_run_strategy(*, strategy_id, body, db, user):
        assert strategy_id == 5
        assert body.dataset_id == 119
        return SimpleNamespace(status="no_matches", run_id=0)

    monkeypatch.setattr("app.api.v1.strategies.run_strategy", fake_run_strategy)

    result = await dispatch_scheduled_job(
        FakeDb(),
        SimpleNamespace(
            id=15,
            task_type="run_predictions",
            config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 12, "strategy_ids": [5], "dataset_id": 119},
        ),
    )

    assert result.status == "skipped"
    assert result.detail == "summary[no_matches:1]; 5:no_matches:0"


@pytest.mark.asyncio
async def test_dispatch_scrape_predict_tickets_job_stops_before_tickets_when_predictions_are_partial(monkeypatch):
    calls = []

    async def fake_scrape(db, job):
        calls.append(("scrape", job.id))
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="scrape_job:90",
            artifacts={"dataset_ids": [190]},
        )

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
        return SimpleNamespace(
            job_id=job.id, task_type=job.task_type, status="completed", detail="ticket_batch:12; tickets:2"
        )

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
    assert (
        result.detail == "scrape_job:90; predictions:summary[completed:1, no_matches:1]; 4:completed:91, 5:no_matches:0"
    )
    assert calls == [
        ("scrape", 16),
        (
            "predict",
            16,
            {"strategy_ids": [4, 5], SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42, "dataset_id": 190},
        ),
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
        result.detail == "predictions=3 checked, 1 won, 1 lost, 1 pending, 0 void, 0 unsupported; "
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
        ticket_format,
        accumulator_risk_acknowledged,
        automated,
        market_types,
        min_odds,
        max_odds,
        run_id,
        run_ids,
        prediction_ids,
    ):
        assert user_id == 21
        assert bankroll_id == 9
        assert ticket_count == 3
        assert difficulty == "balanced"
        assert ticket_format is None
        assert accumulator_risk_acknowledged is False
        assert automated is True
        assert market_types == ["1x2", "btts"]
        assert min_odds == 1.2
        assert max_odds == 4.5
        assert run_id is None
        assert run_ids is None
        assert prediction_ids == [701, 702]
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
                "prediction_ids": [701, 702],
            },
        ),
    )

    assert result.status == "completed"
    assert result.detail == "ticket_batch:55; tickets:3"
    assert result.artifacts == {"ticket_batch_ids": [55], "ticket_ids": [1, 2, 3]}


@pytest.mark.asyncio
async def test_dispatch_ticket_generation_uses_the_scheduled_run_as_the_idempotency_key(monkeypatch):
    class FakeDb:
        async def get(self, _model, user_id):
            return SimpleNamespace(id=user_id)

    async def fake_generate_tickets(**kwargs):
        assert kwargs["scheduled_job_run_id"] == 812
        return SimpleNamespace(id=55), [SimpleNamespace(id=1)]

    monkeypatch.setattr(scheduled_jobs, "generate_tickets", fake_generate_tickets)
    result = await dispatch_scheduled_job(
        FakeDb(),
        SimpleNamespace(
            id=13,
            task_type="generate_tickets",
            config={SCHEDULED_JOB_OWNER_CONFIG_KEY: 21, "bankroll_id": 9, "market_types": ["1x2"]},
        ),
        scheduled_job_run_id=812,
    )

    assert result.status == "completed"


@pytest.mark.asyncio
async def test_dispatch_scrape_predict_tickets_job_runs_full_chain(monkeypatch):
    calls = []

    async def fake_scrape(db, job):
        assert job.config[SCHEDULED_JOB_OWNER_CONFIG_KEY] == 42
        calls.append(("scrape", job.id))
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="scrape_job:88",
            artifacts={"scrape_job_ids": [88], "dataset_ids": [188]},
        )

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
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="ticket_batch:12; tickets:2",
            artifacts={"ticket_batch_ids": [12], "ticket_ids": [1201, 1202]},
        )

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
    assert (
        result.detail == "scrape_job:88; predictions:summary[completed:1]; 4:completed:91; ticket_batch:12; tickets:2"
    )
    assert result.artifacts == {
        "scrape_job_ids": [88],
        "dataset_ids": [188],
        "prediction_run_ids": [91],
        "ticket_batch_ids": [12],
        "ticket_ids": [1201, 1202],
    }
    assert calls == [
        ("scrape", 14),
        (
            "predict",
            14,
            {"strategy_ids": [4], SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42, "dataset_id": 188},
        ),
        (
            "tickets",
            14,
            {"ticket_count": 2, "difficulty": "safe", SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42, "run_id": 91},
        ),
    ]


@pytest.mark.asyncio
async def test_dispatch_scrape_predict_tickets_job_stops_when_prediction_run_is_ambiguous(monkeypatch):
    calls = []

    async def fake_scrape(db, job):
        calls.append(("scrape", job.id))
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="scrape_job:88",
            artifacts={"dataset_ids": [188]},
        )

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
        return SimpleNamespace(
            job_id=job.id, task_type=job.task_type, status="completed", detail="ticket_batch:12; tickets:2"
        )

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
        result.detail == "scrape_job:88; predictions:summary[completed:2]; 4:completed:91, 5:completed:92; "
        "tickets:missing_or_ambiguous_prediction_run_id"
    )
    assert result.artifacts == {"dataset_ids": [188], "prediction_run_ids": [91, 92]}
    assert calls == [
        ("scrape", 71),
        (
            "predict",
            71,
            {"strategy_ids": [4, 5], SCHEDULED_JOB_OWNER_CONFIG_KEY: 42, "user_id": 42, "dataset_id": 188},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset_ids", [None, 201, [201, 202]])
async def test_dispatch_scrape_predict_tickets_job_stops_without_one_fresh_scrape_dataset(monkeypatch, dataset_ids):
    calls = []

    async def fake_scrape(db, job):
        calls.append(("scrape", job.id))
        artifacts = {} if dataset_ids is None else {"dataset_ids": dataset_ids}
        return SimpleNamespace(
            job_id=job.id,
            task_type=job.task_type,
            status="completed",
            detail="scrape_job:200",
            artifacts=artifacts,
        )

    async def fail_prediction(*_args, **_kwargs):
        raise AssertionError("prediction must not run without exactly one fresh scrape dataset")

    async def fail_tickets(*_args, **_kwargs):
        raise AssertionError("ticket generation must not run without exactly one fresh scrape dataset")

    monkeypatch.setattr(scheduled_jobs, "_run_scrape_job", fake_scrape)
    monkeypatch.setattr(scheduled_jobs, "_run_prediction_job", fail_prediction)
    monkeypatch.setattr(scheduled_jobs, "_run_ticket_generation_job", fail_tickets)

    result = await dispatch_scheduled_job(
        object(),
        SimpleNamespace(
            id=200,
            task_type="scrape_predict_tickets",
            config={
                SCHEDULED_JOB_OWNER_CONFIG_KEY: 42,
                "prediction": {"strategy_ids": [4], "dataset_id": 999},
                "tickets": {"ticket_count": 2, "difficulty": "safe"},
            },
        ),
    )

    assert result.status == "partial"
    assert result.detail == "scrape_job:200; predictions:missing_or_ambiguous_scrape_dataset_id"
    assert result.artifacts == ({} if dataset_ids is None else {"dataset_ids": dataset_ids})
    assert calls == [("scrape", 200)]
