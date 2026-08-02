from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_admin, get_current_user
from app.api.v1 import provider as provider_api
from app.database import get_db
from app.main import app
from app.services.worker_observability import WorkerLaneSnapshot
from app.tasks.worker_lanes import WorkerLane


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _SnapshotDb:
    def __init__(self, states):
        self._states = states

    async def scalars(self, _statement):
        return _Rows(self._states)


class _Registry:
    def list_sources(self):
        return (SimpleNamespace(adapter_key="safe-adapter", source_key="safe-source"),)

    def get_source(self, _adapter_key, _source_key):
        raise provider_api.UnknownProviderError("unknown test source")


def _state(**overrides):
    values = {
        "adapter_key": "safe-adapter",
        "source_key": "safe-source",
        "circuit_state": "open",
        "quota_limit": 10,
        "quota_reserved": 2,
        "quota_consumed": 8,
        "provider_remaining": 0,
        "consecutive_failures": 3,
        "last_reconciled_at": datetime(2026, 8, 1, 12, tzinfo=UTC),
        # Explicitly hostile values which must never reach the wire response.
        "last_error_at": "https://provider.invalid/?api_token=provider-secret-sentinel",
        "execution_token": "execution-secret-sentinel",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_provider_phase_classification_uses_persisted_operation_semantics() -> None:
    backfill = {
        "operation": "understat_schedule_backfill",
        "competition": "england-premier-league",
        "season": "2025",
        "mode": "backfill",
        "cache_mode": "warm",
    }
    incremental = {
        "operation": "espn_schedule_incremental",
        "competition": "england-premier-league",
        "season": "2025",
        "mode": "incremental",
        "cache_mode": "warm",
    }

    assert provider_api._phase_for_run("soccerdata_http_ingest", backfill) == "backfill"
    assert provider_api._phase_for_run("soccerdata_http_ingest", incremental) is None
    assert provider_api._phase_for_run("fetch_latest_odds", {}) is None
    assert provider_api._phase_for_run("train_model", {}) == "features"
    assert provider_api._phase_for_run("predict_model", {}) == "model"


def test_upstream_zero_remaining_emits_quota_exhausted_alert() -> None:
    state = _state(quota_limit=None, quota_reserved=0, quota_consumed=0, provider_remaining=0)

    alerts = provider_api._source_alerts(
        state.adapter_key,
        state.source_key,
        source=state,
        summary=provider_api._ObservationSummary(),
    )

    assert "quota_exhausted" in {alert.code for alert in alerts}


@pytest.mark.asyncio
async def test_provider_runtime_requires_authentication() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/provider/runtime")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_provider_runtime_requires_admin_operator() -> None:
    async def override_db():
        yield _SnapshotDb([])

    async def override_user():
        return SimpleNamespace(id=6, is_admin=False)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/v1/provider/runtime")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin access required"}


@pytest.mark.asyncio
async def test_provider_runtime_returns_bounded_redacted_operator_shape(monkeypatch) -> None:
    db = _SnapshotDb([_state()])

    async def fake_snapshot(_db, lane, *, now):
        return WorkerLaneSnapshot(
            lane=lane,
            queued=1 if lane is WorkerLane.PROVIDER_HTTP else 0,
            running=0,
            oldest_queue_age_ms=3,
            sampled_terminal_runs=4,
            retries=2 if lane is WorkerLane.PROVIDER_HTTP else 0,
            fallbacks=0,
            freshness_failures=0,
            peak_rss_bytes=None,
            peak_pid_count=None,
        )

    async def override_db():
        yield db

    async def override_user():
        return SimpleNamespace(id=7, is_admin=True)

    async def fake_observations(_db, *, observed_at):
        return {
            ("safe-adapter", "safe-source"): provider_api._ObservationSummary(
                observation_count=5,
                complete_snapshot_count=3,
                partial_snapshot_count=1,
                unmapped_observation_count=1,
                conflicted_observations=2,
                latest_observed_at=datetime(2026, 8, 1, 11, 59, tzinfo=UTC),
                freshness_state="unknown",
            )
        }

    async def fake_cache(_db):
        return {("safe-adapter", "safe-source"): provider_api._CacheSummary(cache_state="mixed")}

    async def fake_phases(_db, *, observation_summaries):
        return [
            provider_api.ProviderPipelinePhaseResponse(
                phase="backfill", status="queued", queued=2, running=0, failed=0, partial=0, attention_count=0
            ),
            provider_api.ProviderPipelinePhaseResponse(
                phase="normalize", status="attention", queued=0, running=0, failed=0, partial=0, attention_count=2
            ),
            provider_api.ProviderPipelinePhaseResponse(
                phase="features", status="running", queued=0, running=1, failed=0, partial=0, attention_count=0
            ),
            provider_api.ProviderPipelinePhaseResponse(
                phase="model", status="attention", queued=0, running=0, failed=1, partial=2, attention_count=3
            ),
        ]

    monkeypatch.setattr(provider_api, "collect_worker_lane_snapshot", fake_snapshot)
    monkeypatch.setattr(provider_api, "DEFAULT_PROVIDER_REGISTRY", _Registry())
    monkeypatch.setattr(provider_api, "_observation_summaries", fake_observations)
    monkeypatch.setattr(provider_api, "_cache_summaries", fake_cache)
    monkeypatch.setattr(provider_api, "_pipeline_phases", fake_phases)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_admin] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/v1/provider/runtime")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"observed_at", "sources", "lanes", "phases", "alerts"}
    assert body["sources"] == [
        {
            "adapter_key": "safe-adapter",
            "source_key": "safe-source",
            "circuit_state": "open",
            "quota_limit": 10,
            "quota_reserved": 2,
            "quota_consumed": 8,
            "provider_remaining": 0,
            "consecutive_failures": 3,
            "last_reconciled_at": "2026-08-01T12:00:00Z",
            "observation_count": 5,
            "complete_snapshot_count": 3,
            "partial_snapshot_count": 1,
            "unmapped_observation_count": 1,
            "coverage_percent": 60.0,
            "latest_observed_at": "2026-08-01T11:59:00Z",
            "freshness_state": "unknown",
            "cache_state": "mixed",
        }
    ]
    assert [lane["lane"] for lane in body["lanes"]] == [item.value for item in WorkerLane]
    assert body["phases"] == [
        {
            "phase": "backfill",
            "status": "queued",
            "queued": 2,
            "running": 0,
            "failed": 0,
            "partial": 0,
            "attention_count": 0,
        },
        {
            "phase": "normalize",
            "status": "attention",
            "queued": 0,
            "running": 0,
            "failed": 0,
            "partial": 0,
            "attention_count": 2,
        },
        {
            "phase": "features",
            "status": "running",
            "queued": 0,
            "running": 1,
            "failed": 0,
            "partial": 0,
            "attention_count": 0,
        },
        {
            "phase": "model",
            "status": "attention",
            "queued": 0,
            "running": 0,
            "failed": 1,
            "partial": 2,
            "attention_count": 3,
        },
    ]
    assert {alert["code"] for alert in body["alerts"]} >= {
        "circuit_open",
        "quota_exhausted",
        "consecutive_failures",
        "observation_conflicted",
        "coverage_partial",
        "retry_rate_high",
    }
    serialized = response.text
    assert "provider-secret-sentinel" not in serialized
    assert "execution-secret-sentinel" not in serialized
    assert "last_error_at" not in serialized
    assert "execution_token" not in serialized


@pytest.mark.asyncio
async def test_revalidated_cache_evidence_is_reported_as_mixed() -> None:
    config = {
        "operation": "understat_schedule_backfill",
        "competition": "england-premier-league",
        "season": "2025",
        "mode": "backfill",
        # Job configuration controls bridge behavior; checkpoint evidence is
        # independently persisted as revalidated after the run.
        "cache_mode": "warm",
    }

    class _Db:
        async def execute(self, _statement):
            return _Rows([SimpleNamespace(cache_mode="revalidated", config=config)])

    summaries = await provider_api._cache_summaries(_Db())

    assert summaries[("soccerdata", "understat")].cache_state == "mixed"


@pytest.mark.asyncio
async def test_pipeline_phase_queries_filter_eligible_runs_before_each_bound() -> None:
    backfill_config = {
        "operation": "understat_schedule_backfill",
        "competition": "england-premier-league",
        "season": "2025",
        "mode": "backfill",
        "cache_mode": "warm",
    }

    class _Db:
        def __init__(self):
            self.statements = []
            self.results = [
                _Rows([SimpleNamespace(task_type="soccerdata_http_ingest", status="running", config=backfill_config)]),
                _Rows([SimpleNamespace(task_type="unrelated_terminal_job", status="completed", config={})]),
            ]

        async def execute(self, statement):
            self.statements.append(statement)
            return self.results.pop(0)

    db = _Db()
    phases = await provider_api._pipeline_phases(db, observation_summaries={})

    backfill = next(phase for phase in phases if phase.phase == "backfill")
    assert (backfill.status, backfill.running) == ("running", 1)
    assert len(db.statements) == 2
    for statement in db.statements:
        sql = str(statement)
        assert "scheduled_job_runs.task_type IN" in sql
        assert sql.index("WHERE") < sql.index("LIMIT")
    assert "scheduled_job_runs.status IN" in str(db.statements[0])
    assert "scheduled_job_runs.status NOT IN" in str(db.statements[1])


@pytest.mark.asyncio
async def test_missing_runtime_state_is_unknown_not_healthy(monkeypatch) -> None:
    db = _SnapshotDb([])

    async def fake_snapshot(_db, lane, *, now):
        return WorkerLaneSnapshot(
            lane=lane,
            queued=0,
            running=0,
            oldest_queue_age_ms=0,
            sampled_terminal_runs=0,
            retries=0,
            fallbacks=0,
            freshness_failures=0,
            peak_rss_bytes=None,
            peak_pid_count=None,
        )

    async def fake_observations(_db, *, observed_at):
        return {}

    async def fake_cache(_db):
        return {}

    async def fake_phases(_db, *, observation_summaries):
        return []

    async def override_db():
        yield db

    async def override_user():
        return SimpleNamespace(id=7, is_admin=True)

    monkeypatch.setattr(provider_api, "collect_worker_lane_snapshot", fake_snapshot)
    monkeypatch.setattr(provider_api, "DEFAULT_PROVIDER_REGISTRY", _Registry())
    monkeypatch.setattr(provider_api, "_observation_summaries", fake_observations)
    monkeypatch.setattr(provider_api, "_cache_summaries", fake_cache)
    monkeypatch.setattr(provider_api, "_pipeline_phases", fake_phases)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_admin] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/v1/provider/runtime")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["sources"][0]["circuit_state"] == "unknown"
