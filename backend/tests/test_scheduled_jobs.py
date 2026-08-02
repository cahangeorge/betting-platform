from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import jobs as jobs_api
from app.models.job import ScheduledJob, ScheduledJobRun
from app.schemas.job import ScheduledJobCreateRequest
from app.services import scheduled_jobs
from app.services.python_bridge import BridgeError
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
from app.services.soccerdata_ingestion import SoccerdataIngestionResult


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
                '{"skipped": true, "reused_job_id": 77, "dataset_id": 188, "scrape_report": {"health": "degraded"}}'
            ),
        )
    )

    assert artifacts == {
        "scrape_job_ids": [88],
        "dataset_ids": [188],
        "scrape_report": {"health": "degraded"},
    }
    assert scheduled_jobs._scrape_task_run_status("completed", artifacts) == "partial"


def test_worker_metrics_extracts_only_bounded_fallback_and_freshness_outcomes():
    assert scheduled_jobs._worker_metrics_from_artifacts(
        {"scrape_report": {"fallback_count": 2, "freshness_status": "STALE", "token": "ignored"}}
    ) == {"fallback_count": 2, "freshness_status": "stale"}
    assert scheduled_jobs._worker_metrics_from_artifacts(
        {"scrape_report": {"fallback_count": -1, "freshness_status": "invented"}}
    ) == {"fallback_count": 0, "freshness_status": "unknown"}


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


def test_soccerdata_scheduled_job_validates_versioned_spec_and_lane():
    request = ScheduledJobCreateRequest(
        name="ESPN incremental",
        task_type="soccerdata_http_ingest",
        cron_expression="0 */6 * * *",
        config={
            "spec_version": "soccerdata-ingestion/v1",
            "operation": "espn_schedule_incremental",
            "competition": "ENG-Premier League",
            "season": "2025-2026",
            "mode": "incremental",
            "cache_mode": "warm",
        },
    )
    assert request.task_type == "soccerdata_http_ingest"

    with pytest.raises(ValidationError, match="scheduled worker lane"):
        ScheduledJobCreateRequest(
            name="FBref on wrong lane",
            task_type="soccerdata_http_ingest",
            cron_expression="0 */6 * * *",
            config={
                "operation": "fbref_schedule_backfill",
                "competition": "ENG-Premier League",
                "season": "2024-2025",
                "mode": "backfill",
            },
        )
    with pytest.raises(ValidationError, match="page zero"):
        ScheduledJobCreateRequest(
            name="Invalid resume injection",
            task_type="soccerdata_http_ingest",
            cron_expression="0 */6 * * *",
            config={
                "operation": "espn_schedule_incremental",
                "competition": "ENG-Premier League",
                "season": "2025-2026",
                "mode": "incremental",
                "page": 1,
                "start_cursor": 200,
            },
        )


def test_soccerdata_run_artifacts_snapshot_immutable_public_job_spec():
    job = SimpleNamespace(
        task_type="soccerdata_http_ingest",
        config={
            SCHEDULED_JOB_OWNER_CONFIG_KEY: 42,
            "operation": "espn_schedule_incremental",
            "competition": "ENG-Premier League",
            "season": "2025-2026",
            "mode": "incremental",
            "cache_mode": "warm",
        },
    )

    artifacts = scheduled_jobs._scheduled_job_run_artifacts(job)

    assert artifacts is not None
    assert artifacts["job_spec"] == {
        "spec_version": "soccerdata-ingestion/v1",
        "operation": "espn_schedule_incremental",
        "competition": "ENG-Premier League",
        "season": "2025-2026",
        "mode": "incremental",
        "cache_mode": "warm",
        "limit": 2_000,
        "chunk_size": 200,
        "page": 0,
        "start_cursor": 0,
    }
    assert len(artifacts["job_spec_digest"]) == len(artifacts["request_fingerprint"]) == 64
    assert SCHEDULED_JOB_OWNER_CONFIG_KEY not in artifacts["job_spec"]


def test_licensed_odds_job_accepts_only_secret_free_immutable_command():
    request = ScheduledJobCreateRequest(
        name="licensed odds (disabled pending approval)",
        task_type="fetch_latest_odds",
        cron_expression="0 */6 * * *",
        config={
            "contract_version": "licensed-odds-job/v1",
            "scope": "prematch",
            "canary_stage_percent": 10,
        },
    )
    assert request.task_type == "fetch_latest_odds"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ScheduledJobCreateRequest(
            name="must not carry a credential",
            task_type="fetch_latest_odds",
            cron_expression="0 */6 * * *",
            config={
                "contract_version": "licensed-odds-job/v1",
                "scope": "prematch",
                "canary_stage_percent": 10,
                "token": "not-allowed",
            },
        )


def test_licensed_odds_run_artifacts_are_canonical_and_tamper_evident():
    job = SimpleNamespace(
        task_type="fetch_latest_odds",
        config={
            SCHEDULED_JOB_OWNER_CONFIG_KEY: 42,
            "contract_version": "licensed-odds-job/v1",
            "scope": "inplay",
            "canary_stage_percent": 25,
        },
    )
    artifacts = scheduled_jobs._scheduled_job_run_artifacts(job)
    assert artifacts == {
        "job_spec": {
            "contract_version": "licensed-odds-job/v1",
            "scope": "inplay",
            "canary_stage_percent": 25,
        },
        "job_spec_digest": artifacts["job_spec_digest"],
        "licensed_odds_contract_version": "licensed-odds-job/v1",
    }
    run = SimpleNamespace(
        task_type="fetch_latest_odds",
        artifacts={**artifacts, "job_spec": {**artifacts["job_spec"], "scope": "prematch"}},
    )
    with pytest.raises(ValueError, match="digest mismatch"):
        scheduled_jobs._licensed_odds_spec_from_run(run)


@pytest.mark.asyncio
async def test_licensed_odds_exact_dispatch_never_falls_through_to_legacy_scraper(monkeypatch):
    async def legacy_scraper(*_args, **_kwargs):
        raise AssertionError("legacy scraper must not be selected")

    monkeypatch.setattr(scheduled_jobs, "_run_scrape_job", legacy_scraper)
    result = await dispatch_scheduled_job(
        SimpleNamespace(), SimpleNamespace(id=3, task_type="fetch_latest_odds", config={})
    )
    assert result.status == "skipped"
    assert result.detail == "licensed_odds_requires_immutable_run_spec"


@pytest.mark.asyncio
async def test_licensed_odds_denial_is_secret_free_and_performs_no_persistence_or_fallback(monkeypatch):
    from app.services.licensed_odds import (
        LicensedOddsAcquisition,
        LicensedOddsAcquisitionStatus,
        LicensedOddsTelemetry,
    )

    calls = []

    class NoLiveService:
        def __init__(self, *_args, **_kwargs):
            calls.append("constructed")

        async def acquire_sportmonks_latest(self, *_args, **_kwargs):
            calls.append("admission")
            return LicensedOddsAcquisition(
                records=(),
                telemetry=LicensedOddsTelemetry(
                    adapter_key="sportmonks-v3-odds",
                    source_key="sportmonks-football-v3-standard-odds",
                    scope="prematch",
                    status=LicensedOddsAcquisitionStatus.DENIED,
                    reason_code="authorization_denied",
                    charged=False,
                    failure=False,
                    record_count=0,
                ),
            )

    class Db:
        commits = 0

        async def commit(self):
            self.commits += 1

    monkeypatch.setattr(scheduled_jobs, "LicensedOddsService", NoLiveService)
    result = await scheduled_jobs._run_licensed_odds_job(
        Db(),
        SimpleNamespace(id=11, scheduled_job_id=7, task_type="fetch_latest_odds"),
        spec=scheduled_jobs.LicensedOddsJobSpecV1(scope="prematch", canary_stage_percent=100),
        execution_token="fence",
    )
    assert calls == ["constructed", "admission"]
    assert result.status == "skipped"
    assert result.artifacts["licensed_odds"]["reason_code"] == "authorization_denied"


@pytest.mark.asyncio
async def test_licensed_odds_canary_exclusion_performs_no_admission_or_egress(monkeypatch):
    class NoLiveService:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("excluded canary work must not construct the acquisition service")

    monkeypatch.setattr(scheduled_jobs, "LicensedOddsService", NoLiveService)
    monkeypatch.setattr(scheduled_jobs, "included_in_canary", lambda *_args: False)
    result = await scheduled_jobs._run_licensed_odds_job(
        SimpleNamespace(),
        SimpleNamespace(id=12, scheduled_job_id=8, task_type="fetch_latest_odds"),
        spec=scheduled_jobs.LicensedOddsJobSpecV1(scope="inplay", canary_stage_percent=10),
        execution_token="fence",
    )

    assert result.status == "skipped"
    assert result.detail == "licensed_odds_canary_excluded"
    assert result.artifacts["licensed_odds"]["canary_included"] is False
    assert result.artifacts["licensed_odds"]["charged"] is False


@pytest.mark.asyncio
async def test_licensed_odds_materializes_only_durable_staged_observation_ids(monkeypatch):
    from app.services.licensed_odds import (
        LicensedOddsAcquisition,
        LicensedOddsAcquisitionStatus,
        LicensedOddsTelemetry,
    )

    observation = SimpleNamespace(id=91)
    calls: list[object] = []

    class StagedService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def acquire_sportmonks_latest(self, *_args, **kwargs):
            calls.append(kwargs["scheduled_job_run_id"])
            return LicensedOddsAcquisition(
                records=(),
                telemetry=LicensedOddsTelemetry(
                    adapter_key="sportmonks-v3-odds",
                    source_key="sportmonks-football-v3-standard-odds",
                    scope="prematch",
                    status=LicensedOddsAcquisitionStatus.ACQUIRED,
                    reason_code="staged_observations_replayed",
                    charged=True,
                    failure=False,
                    record_count=1,
                ),
                observation_ids=(91,),
                replayed=True,
            )

    class Db:
        async def commit(self):
            calls.append("commit")

        async def get(self, model, observation_id):
            calls.append((model, observation_id))
            return observation

    async def materialize(_db, value, **_kwargs):
        calls.append(value)

    async def fence(*_args, **_kwargs):
        calls.append("fence")

    monkeypatch.setattr(scheduled_jobs, "LicensedOddsService", StagedService)
    monkeypatch.setattr(scheduled_jobs, "materialize_odds_observation", materialize)
    monkeypatch.setattr(scheduled_jobs, "assert_task_run_fence", fence)
    result = await scheduled_jobs._run_licensed_odds_job(
        Db(),
        SimpleNamespace(id=19, scheduled_job_id=7, task_type="fetch_latest_odds"),
        spec=scheduled_jobs.LicensedOddsJobSpecV1(scope="prematch", canary_stage_percent=100),
        execution_token="fence-token",
    )

    assert result.status == "completed"
    assert result.artifacts["provider_observation_ids"] == [91]
    assert "replayed:true" in result.detail
    assert 19 in calls
    assert observation in calls


def test_terminal_soccerdata_artifacts_expose_model_source_generation():
    result = scheduled_jobs.SoccerdataIngestionResult(
        checkpoint_id=9,
        state="completed",
        dataset_id=81,
        record_count=3,
        observation_count=3,
        generation_id=41,
    )

    artifacts = scheduled_jobs._soccerdata_result_artifacts(result)

    assert artifacts["provider_dataset_generation_ids"] == [41]
    assert artifacts["source_generation_id"] == 41


def test_nonterminal_soccerdata_artifacts_do_not_advertise_trainable_generation():
    result = scheduled_jobs.SoccerdataIngestionResult(
        checkpoint_id=9,
        state="completed",
        dataset_id=81,
        record_count=3,
        observation_count=3,
        generation_id=41,
        cursor={"page": 1, "start_cursor": 200, "generation_key": "a" * 64},
    )

    artifacts = scheduled_jobs._soccerdata_result_artifacts(result)

    assert artifacts["provider_dataset_generation_ids"] == [41]
    assert "source_generation_id" not in artifacts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ingestion_state", "replayed"),
    [("completed", False), ("no_data", True)],
)
async def test_scheduled_soccerdata_run_fetches_snapshot_outside_transaction_and_fences_persistence(
    monkeypatch, ingestion_state, replayed
):
    snapshot = {
        "spec_version": "soccerdata-ingestion/v1",
        "operation": "espn_schedule_incremental",
        "competition": "ENG-Premier League",
        "season": "2025-2026",
        "mode": "incremental",
        "cache_mode": "warm",
        "limit": 2_000,
        "chunk_size": 200,
        "page": 0,
        "start_cursor": 0,
    }
    spec = scheduled_jobs.SoccerdataIngestionSpec.from_config(snapshot)
    run = SimpleNamespace(
        id=701,
        scheduled_job_id=17,
        task_type="soccerdata_http_ingest",
        status="queued",
        queue_contract_version="worker-lanes/v1",
        execution_token="fence-701",
        artifacts={
            "job_spec": snapshot,
            "job_spec_digest": spec.spec_digest,
            "request_fingerprint": spec.request_fingerprint,
        },
    )
    # This intentionally conflicts with the immutable delivery snapshot.
    job = SimpleNamespace(id=17, task_type=run.task_type, config={"operation": "fbref_schedule_backfill"})

    class ServiceDb:
        commits = 0

        async def get(self, model, row_id):
            if model is ScheduledJobRun and row_id == run.id:
                return run
            if model is ScheduledJob and row_id == job.id:
                return job
            return None

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            raise AssertionError("successful ingestion must not roll back")

    db = ServiceDb()

    class SessionManager:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

    calls = []

    async def fake_claim(_db, run_id, *, lease_seconds=None):
        assert run_id == run.id
        assert lease_seconds is not None
        run.status = "running"
        return run

    async def fake_fetch(received_spec):
        calls.append(("fetch", received_spec.to_config()))
        assert db.commits == 2  # claim and job-read transactions are closed first
        return SimpleNamespace()

    async def fake_persist(_db, received_spec, batch, **kwargs):
        assert received_spec.to_config() == snapshot
        assert batch is not None
        assert kwargs["scheduled_job_run_id"] == run.id
        assert kwargs["run_id"] == str(run.id)
        await kwargs["fence"]()
        calls.append(("persist", kwargs["correlation_id"]))
        return SoccerdataIngestionResult(
            checkpoint_id=9,
            state=ingestion_state,
            dataset_id=81 if ingestion_state == "completed" else None,
            record_count=3 if ingestion_state == "completed" else 0,
            observation_count=3 if ingestion_state == "completed" else 0,
            replayed=replayed,
        )

    async def fake_fence(_db, run_id, execution_token):
        assert (run_id, execution_token) == (run.id, "fence-701")
        calls.append(("fence", run_id))

    async def fake_finish(_db, bound_run, **kwargs):
        bound_run.status = kwargs["status"]
        bound_run.detail = kwargs["detail"]
        bound_run.artifacts = {**bound_run.artifacts, **kwargs["artifacts"]}
        calls.append(("finish", kwargs["status"]))
        return bound_run

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", SessionManager)
    monkeypatch.setattr(scheduled_jobs, "claim_queued_task_run", fake_claim)
    monkeypatch.setattr(scheduled_jobs, "authorize_soccerdata_ingestion", lambda _spec: None)
    monkeypatch.setattr(scheduled_jobs, "fetch_soccerdata_batch", fake_fetch)
    monkeypatch.setattr(scheduled_jobs, "persist_soccerdata_batch", fake_persist)
    monkeypatch.setattr(scheduled_jobs, "assert_task_run_fence", fake_fence)
    monkeypatch.setattr(scheduled_jobs, "finish_task_run", fake_finish)

    result = await scheduled_jobs.execute_scheduled_job_run(run.id)

    expected_status = "skipped" if ingestion_state == "no_data" else "completed"
    assert result.status == expected_status
    assert result.artifacts["ingestion_state"] == ingestion_state
    assert result.artifacts["replayed"] is replayed
    assert result.artifacts.get("dataset_ids") == ([81] if ingestion_state == "completed" else None)
    assert calls[0] == ("fetch", snapshot)
    assert calls.count(("fence", run.id)) == 2
    assert calls[-1] == ("finish", expected_status)


@pytest.mark.asyncio
async def test_scheduled_soccerdata_fetch_timeout_uses_fenced_retry(monkeypatch):
    spec = scheduled_jobs.SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition="ENG-Premier League",
        season="2025-2026",
        mode="incremental",
    )
    run = SimpleNamespace(
        id=702,
        scheduled_job_id=18,
        task_type="soccerdata_http_ingest",
        status="queued",
        queue_contract_version="worker-lanes/v1",
        execution_token="fence-702",
        artifacts={
            "job_spec": spec.to_config(),
            "job_spec_digest": spec.spec_digest,
            "request_fingerprint": spec.request_fingerprint,
        },
    )
    job = SimpleNamespace(id=18, task_type=run.task_type, config={})

    class ServiceDb:
        async def get(self, model, row_id):
            if model is ScheduledJobRun and row_id == run.id:
                return run
            if model is ScheduledJob and row_id == job.id:
                return job
            return None

        async def commit(self):
            return None

        async def rollback(self):
            return None

    db = ServiceDb()

    class SessionManager:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

    async def fake_claim(*_args, **_kwargs):
        run.status = "running"
        return run

    async def timed_out_fetch(_spec):
        raise BridgeError("provider bridge timed out", failure_kind="timeout")

    async def fake_requeue(_db, bound_run, **kwargs):
        assert kwargs["execution_token"] == "fence-702"
        assert kwargs["failure_kind"] == "timeout"
        bound_run.status = "queued"
        bound_run.retry_disposition = "retryable"
        return True

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", SessionManager)
    monkeypatch.setattr(scheduled_jobs, "claim_queued_task_run", fake_claim)
    monkeypatch.setattr(scheduled_jobs, "authorize_soccerdata_ingestion", lambda _spec: None)
    monkeypatch.setattr(scheduled_jobs, "fetch_soccerdata_batch", timed_out_fetch)
    monkeypatch.setattr(scheduled_jobs, "requeue_task_run_failure", fake_requeue)

    result = await scheduled_jobs.execute_scheduled_job_run(run.id)

    assert result.status == "queued"
    assert result.retry_disposition == "retryable"


@pytest.mark.asyncio
async def test_scheduled_soccerdata_retry_replays_committed_page_then_resumes_at_next_cursor(monkeypatch):
    spec = scheduled_jobs.SoccerdataIngestionSpec(
        operation="espn_schedule_incremental",
        competition="ENG-Premier League",
        season="2025-2026",
        mode="incremental",
        limit=2,
        chunk_size=1,
    )
    run = SimpleNamespace(
        id=703,
        scheduled_job_id=19,
        task_type="soccerdata_http_ingest",
        status="queued",
        queue_contract_version="worker-lanes/v1",
        execution_token="fence-703",
        artifacts={
            "job_spec": spec.to_config(),
            "job_spec_digest": spec.spec_digest,
            "request_fingerprint": spec.request_fingerprint,
        },
    )
    job = SimpleNamespace(id=19, task_type=run.task_type, config={})

    class ServiceDb:
        async def get(self, model, row_id):
            if model is ScheduledJobRun and row_id == run.id:
                return run
            if model is ScheduledJob and row_id == job.id:
                return job
            return None

        async def scalar(self, *_args, **_kwargs):
            return None

        async def commit(self):
            return None

        async def rollback(self):
            return None

    db = ServiceDb()

    class SessionManager:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

    page_zero_committed = False
    page_one_failures = 0
    fetched_pages = []

    async def fake_claim(*_args, **_kwargs):
        run.status = "running"
        return run

    async def fake_replay(_db, page_spec):
        if page_zero_committed and page_spec.page == 0:
            return SoccerdataIngestionResult(
                10,
                "completed",
                81,
                1,
                1,
                True,
                {"page": 1, "start_cursor": 1, "generation_key": "a" * 64},
                41,
            )
        return None

    async def fake_fetch(page_spec):
        nonlocal page_one_failures
        fetched_pages.append(page_spec.page)
        if page_spec.page == 1 and page_one_failures == 0:
            page_one_failures += 1
            raise BridgeError("page one transport failure", failure_kind="transport")
        return SimpleNamespace()

    async def fake_persist(_db, page_spec, _batch, **_kwargs):
        nonlocal page_zero_committed
        if page_spec.page == 0:
            page_zero_committed = True
            return SoccerdataIngestionResult(
                10,
                "completed",
                81,
                1,
                1,
                False,
                {"page": 1, "start_cursor": 1, "generation_key": "a" * 64},
                41,
            )
        return SoccerdataIngestionResult(11, "no_data", None, 0, 0, generation_id=41)

    async def fake_requeue(_db, bound_run, **kwargs):
        assert kwargs["failure_kind"] == "transport"
        bound_run.status = "queued"
        return True

    async def fake_finish(_db, bound_run, **kwargs):
        bound_run.status = kwargs["status"]
        bound_run.artifacts = {**bound_run.artifacts, **kwargs["artifacts"]}
        return bound_run

    async def fake_fence(*_args, **_kwargs):
        return None

    @asynccontextmanager
    async def fake_heartbeat(*_args, **_kwargs):
        yield

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", SessionManager)
    monkeypatch.setattr(scheduled_jobs, "claim_queued_task_run", fake_claim)
    monkeypatch.setattr(scheduled_jobs, "authorize_soccerdata_ingestion", lambda _spec: None)
    monkeypatch.setattr(scheduled_jobs, "replay_soccerdata_batch", fake_replay)
    monkeypatch.setattr(scheduled_jobs, "fetch_soccerdata_batch", fake_fetch)
    monkeypatch.setattr(scheduled_jobs, "persist_soccerdata_batch", fake_persist)
    monkeypatch.setattr(scheduled_jobs, "requeue_task_run_failure", fake_requeue)
    monkeypatch.setattr(scheduled_jobs, "assert_task_run_fence", fake_fence)
    monkeypatch.setattr(scheduled_jobs, "finish_task_run", fake_finish)
    monkeypatch.setattr(scheduled_jobs, "_task_run_heartbeat", fake_heartbeat)

    first = await scheduled_jobs.execute_scheduled_job_run(run.id)
    assert first.status == "queued"
    second = await scheduled_jobs.execute_scheduled_job_run(run.id)

    assert second.status == "completed"
    assert fetched_pages == [0, 1, 1]
    assert second.artifacts["dataset_ids"] == [81]
    assert second.artifacts["checkpoint_ids"] == [10, 11]
    assert second.artifacts["record_count"] == 1
    assert second.artifacts["provider_dataset_generation_ids"] == [41]
    assert second.artifacts["source_generation_id"] == 41


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

    db = object()
    result = await dispatch_scheduled_job(
        db,
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
        metrics=None,
        peak_rss_bytes=None,
        peak_pid_count=None,
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
async def test_scheduled_scrape_timeout_uses_fenced_retry_instead_of_terminal_finish(monkeypatch):
    job = SimpleNamespace(id=8, task_type="scrape_odds", config={})
    run = SimpleNamespace(
        id=74,
        scheduled_job_id=job.id,
        task_type="scrape_odds",
        status="queued",
        queue_contract_version="worker-lanes/v1",
        execution_token="token-74",
        artifacts=None,
    )

    class ServiceDb:
        async def get(self, model, row_id):
            if model is ScheduledJobRun and row_id == run.id:
                return run
            if model is ScheduledJob and row_id == job.id:
                return job
            return None

        async def commit(self):
            return None

        async def flush(self):
            return None

    db = ServiceDb()

    class SessionManager:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return None

    async def fake_claim(*_args, **_kwargs):
        run.status = "running"
        return run

    async def fake_dispatch(*_args, **_kwargs):
        return scheduled_jobs.ScheduledJobRunResult(
            job_id=job.id,
            task_type=job.task_type,
            status="failed",
            detail="scrape timeout",
            artifacts={"scrape_job_ids": [82], "failure_kind": "timeout"},
        )

    async def fake_requeue(_db, bound_run, **kwargs):
        assert kwargs["execution_token"] == "token-74"
        assert kwargs["failure_kind"] == "timeout"
        bound_run.status = "queued"
        bound_run.execution_token = None
        bound_run.retry_disposition = "retryable"
        return True

    async def fake_fence(*_args, **_kwargs):
        raise AssertionError("retry path must lock outbox before touching the run fence")

    monkeypatch.setattr(scheduled_jobs, "async_session_factory", SessionManager)
    monkeypatch.setattr(scheduled_jobs, "claim_queued_task_run", fake_claim)
    monkeypatch.setattr(scheduled_jobs, "dispatch_scheduled_job", fake_dispatch)
    monkeypatch.setattr(scheduled_jobs, "requeue_task_run_failure", fake_requeue)
    monkeypatch.setattr(scheduled_jobs, "assert_task_run_fence", fake_fence)

    result = await scheduled_jobs.execute_scheduled_job_run(run.id)

    assert result.status == "queued"
    assert result.retry_disposition == "retryable"
    assert result.artifacts["failure_kind"] == "timeout"


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


def _train_model_schedule_config() -> dict:
    return {
        "contract_version": "penaltyblog-model-pipeline/v1",
        "source_generation_id": 91,
        "model_spec": {"model_class": "PoissonGoalsModel"},
        "model_version": "golden-v1",
        "training_cutoff_at": "2026-01-01T00:00:00Z",
    }


def test_model_pipeline_scheduled_job_requires_the_strict_versioned_command():
    request = ScheduledJobCreateRequest(
        name="Train governed model",
        task_type="train_model",
        cron_expression="0 */6 * * *",
        config=_train_model_schedule_config(),
    )
    assert request.task_type == "train_model"

    with pytest.raises(ValidationError, match="Invalid train_model"):
        ScheduledJobCreateRequest(
            name="Unsafe train command",
            task_type="train_model",
            cron_expression="0 */6 * * *",
            config={**_train_model_schedule_config(), "unapproved_flag": True},
        )


def test_model_pipeline_run_snapshot_is_canonical_and_rejects_mutation():
    job = SimpleNamespace(
        id=91,
        task_type="train_model",
        config={**_train_model_schedule_config(), SCHEDULED_JOB_OWNER_CONFIG_KEY: 42},
    )
    artifacts = scheduled_jobs._scheduled_job_run_artifacts(job)

    assert artifacts is not None
    assert artifacts["model_pipeline_contract_version"] == "penaltyblog-model-pipeline/v1"
    assert len(artifacts["model_pipeline_command_digest"]) == 64
    assert SCHEDULED_JOB_OWNER_CONFIG_KEY not in artifacts["model_pipeline_command"]
    run = SimpleNamespace(id=92, task_type="train_model", artifacts=artifacts)
    command = scheduled_jobs._model_pipeline_command_from_run(run)
    assert command.source_generation_id == 91

    run.artifacts = {**artifacts, "model_pipeline_command_digest": "0" * 64}
    with pytest.raises(ValueError, match="digest mismatch"):
        scheduled_jobs._model_pipeline_command_from_run(run)


@pytest.mark.asyncio
async def test_dispatch_model_pipeline_exact_type_precedes_legacy_token_router(monkeypatch):
    import app.services.model_pipeline as model_pipeline

    calls = []

    async def fake_train(db, command):
        calls.append((db, command.source_generation_id))
        return SimpleNamespace(id=9, artifact_key="a" * 64, source_generation_id=command.source_generation_id)

    async def fail_legacy(*_args, **_kwargs):
        raise AssertionError("legacy prediction router must not receive predict_model")

    monkeypatch.setattr(model_pipeline, "train_model", fake_train)
    monkeypatch.setattr(scheduled_jobs, "_run_prediction_job", fail_legacy)
    db = object()
    result = await dispatch_scheduled_job(
        db,
        SimpleNamespace(id=93, task_type="train_model", config=_train_model_schedule_config()),
    )

    assert result.status == "completed"
    assert result.artifacts == {
        "model_artifact_ids": [9],
        "model_artifact_key": "a" * 64,
        "source_generation_id": 91,
    }
    assert calls == [(db, 91)]
