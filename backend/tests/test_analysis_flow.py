from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import strategies as strategies_api
from app.models.prediction import PredictionRun
from app.schemas.strategy import StrategyBatchRunRequest, StrategyRunRequest, StrategyRunResponse
from app.services.analysis_flow import (
    DatasetMatchResolution,
    resolve_dataset_match_ids,
    summarize_analysis_batch_status,
)


class _Result:
    def __init__(self, *, rows=None, scalars=None, scalar_one=None):
        self._rows = None if rows is None else list(rows)
        self._scalars = list(scalars or [])
        self._scalar_one = scalar_one

    def all(self):
        return self._scalars if self._rows is None else self._rows

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar_one


class _ResolverSession:
    def __init__(self, dataset, scrape_job, results):
        self.dataset = dataset
        self.scrape_job = scrape_job
        self.results = list(results)

    async def get(self, model, object_id):
        if model.__name__ == "ScrapedDataset":
            return self.dataset if object_id == self.dataset.id else None
        if model.__name__ == "ScrapeJob":
            return self.scrape_job if object_id == self.scrape_job.id else None
        raise AssertionError(f"Unexpected model lookup: {model}")

    async def execute(self, _stmt):
        return self.results.pop(0)


def _dataset(*records):
    return SimpleNamespace(
        id=29,
        source="OddsHarvester",
        data={"job_id": 181, "matches": list(records)},
    )


def _record(*, home, away, kickoff, league, link):
    return {
        "home_team": home,
        "away_team": away,
        "match_date": kickoff,
        "league_name": league,
        "match_link": link,
    }


@pytest.mark.asyncio
async def test_dataset_resolution_prefers_source_url_and_preserves_dataset_order():
    first_link = "https://www.oddsportal.com/football/argentina/liga/a-b-AAA/#abc123"
    second_link = "https://www.oddsportal.com/football/argentina/liga/c-d-BBB/#def456"
    dataset = _dataset(
        _record(home="A", away="B", kickoff="2026-07-14T12:00:00+00:00", league="Liga", link=first_link),
        _record(home="C", away="D", kickoff="2026-07-14T14:00:00+00:00", league="Liga", link=second_link),
    )
    db = _ResolverSession(
        dataset,
        SimpleNamespace(id=181, status="completed"),
        [
            _Result(rows=[(second_link, 22), (first_link, 11)]),
            _Result(rows=[]),
            _Result(scalars=[]),
        ],
    )

    resolution = await resolve_dataset_match_ids(db, dataset.id)

    assert resolution.match_ids == [11, 22]
    assert resolution.resolved_records == 2
    assert resolution.unresolved_records == 0
    assert resolution.resolution_counts == {"source_url": 2}
    assert resolution.scrape_job_id == 181
    assert resolution.scrape_job_status == "completed"


@pytest.mark.asyncio
async def test_dataset_resolution_uses_unique_reversed_fixture_identity():
    record = _record(
        home="Club Atlético Ñandú",
        away="Deportivo Sur",
        kickoff="2026-07-14T19:30:45+00:00",
        league="Primera Nacional",
        link="https://www.oddsportal.com/football/argentina/primera-nacional/a-b/#missing",
    )
    persisted = SimpleNamespace(
        id=73,
        sport="football",
        home_team="Deportivo Sur",
        away_team="Club Atletico Nandu",
        match_date=datetime(2026, 7, 14, 19, 30, tzinfo=timezone.utc),
        competition="Primera Nacional",
    )
    db = _ResolverSession(
        _dataset(record),
        SimpleNamespace(id=181, status="completed"),
        [_Result(rows=[]), _Result(rows=[]), _Result(scalars=[persisted])],
    )

    resolution = await resolve_dataset_match_ids(db, 29)

    assert resolution.match_ids == [73]
    assert resolution.resolution_counts == {"normalized_fixture_kickoff_league_reversed": 1}
    assert resolution.unresolved_samples == []


@pytest.mark.asyncio
async def test_dataset_resolution_rejects_failed_scrape_job_before_analysis():
    dataset = _dataset(
        _record(
            home="A",
            away="B",
            kickoff="2026-07-14T12:00:00+00:00",
            league="Liga",
            link="https://example.test/a-b/#abc",
        )
    )
    db = _ResolverSession(dataset, SimpleNamespace(id=181, status="failed"), [])

    with pytest.raises(ValueError, match="status 'failed'"):
        await resolve_dataset_match_ids(db, dataset.id)


@pytest.mark.asyncio
async def test_dataset_resolution_rejects_foreign_scrape_job_for_non_admin():
    dataset = _dataset()
    scrape_job = SimpleNamespace(
        id=181,
        status="completed",
        params={"_created_by_user_id": 8},
    )
    db = _ResolverSession(dataset, scrape_job, [])

    with pytest.raises(PermissionError, match="not owned by the current user"):
        await resolve_dataset_match_ids(
            db,
            dataset.id,
            user=SimpleNamespace(id=7, is_admin=False),
        )

    resolution = await resolve_dataset_match_ids(
        _ResolverSession(dataset, scrape_job, []),
        dataset.id,
        user=SimpleNamespace(id=1, is_admin=True),
    )
    assert resolution.dataset is dataset


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["batch", "single"])
async def test_analysis_endpoints_map_dataset_authorization_failure_to_403(monkeypatch, endpoint):
    async def fake_resolve(_db, _dataset_id, *, user=None):
        assert user.id == 7
        raise PermissionError("Dataset 29 is not owned by the current user")

    monkeypatch.setattr(strategies_api, "resolve_dataset_match_ids", fake_resolve)

    if endpoint == "batch":
        async def fake_load(_db, _strategy_ids):
            return [SimpleNamespace(id=5, name="Poisson", model_type="poisson", parameters={}, is_active=True)]

        monkeypatch.setattr(strategies_api, "load_analysis_strategies", fake_load)
        call = strategies_api.run_strategy_batch(
            body=StrategyBatchRunRequest(strategy_ids=[5], dataset_id=29),
            db=object(),
            user=SimpleNamespace(id=7, is_admin=False),
        )
    else:
        strategy = SimpleNamespace(id=5, name="Poisson", model_type="poisson", parameters={}, is_active=True)

        class _Db:
            async def execute(self, _stmt):
                return _Result(scalar_one=strategy)

        call = strategies_api.run_strategy(
            strategy_id=5,
            body=StrategyRunRequest(dataset_id=29, markets=["1x2"]),
            db=_Db(),
            user=SimpleNamespace(id=7, is_admin=False),
        )

    with pytest.raises(HTTPException) as exc_info:
        await call
    assert exc_info.value.status_code == 403


def test_batch_status_reports_mixed_strategy_outcomes_truthfully():
    assert summarize_analysis_batch_status(["completed", "deduped"]) == "completed"
    assert summarize_analysis_batch_status(["deduped", "deduped"]) == "deduped"
    assert summarize_analysis_batch_status(["completed", "failed"]) == "partial"
    assert summarize_analysis_batch_status(["failed", "failed"]) == "failed"


def test_strategy_dedupe_hash_includes_source_dataset_lineage():
    strategy = SimpleNamespace(id=7, model_type="poisson", parameters={})
    execution_config = strategies_api._build_strategy_execution_config(strategy)

    first_hash = strategies_api._strategy_run_input_hash(
        strategy=strategy,
        execution_config=execution_config,
        markets=["1x2"],
        match_ids=[101],
        filters=None,
        source_dataset_id=29,
    )
    second_hash = strategies_api._strategy_run_input_hash(
        strategy=strategy,
        execution_config=execution_config,
        markets=["1x2"],
        match_ids=[101],
        filters=None,
        source_dataset_id=30,
    )

    assert first_hash != second_hash


def test_strategy_response_exposes_truthful_runnable_metadata():
    now = datetime.now(timezone.utc)
    inactive = SimpleNamespace(
        id=1,
        name="Inactive",
        description=None,
        model_type="poisson",
        parameters={},
        weights=None,
        is_active=False,
        created_at=now,
        updated_at=now,
    )
    incompatible = SimpleNamespace(
        id=2,
        name="Legacy invalid",
        description=None,
        model_type="removed-model",
        parameters={},
        weights=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    runnable = SimpleNamespace(
        id=3,
        name="Poisson",
        description=None,
        model_type="poisson",
        parameters={},
        weights=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    inactive_response = strategies_api._strategy_response(inactive)
    incompatible_response = strategies_api._strategy_response(incompatible)
    runnable_response = strategies_api._strategy_response(runnable)

    assert inactive_response.runnable is False
    assert inactive_response.incompatibility_reason == "Strategy is inactive"
    assert incompatible_response.runnable is False
    assert "Unsupported strategy model" in incompatible_response.incompatibility_reason
    assert runnable_response.runnable is True
    assert runnable_response.incompatibility_reason is None


def test_static_strategy_run_routes_precede_dynamic_strategy_id_route():
    paths = [route.path for route in strategies_api.router.routes]
    assert paths.index("/run-batch") < paths.index("/{strategy_id}")
    assert paths.index("/runs") < paths.index("/{strategy_id}")
    assert paths.index("/runs/{run_id}") < paths.index("/{strategy_id}")


@pytest.mark.asyncio
async def test_batch_runs_selected_strategies_with_dataset_lineage(monkeypatch):
    selected = [
        SimpleNamespace(id=8, name="Strategy 8", model_type="poisson", parameters={}, is_active=True),
        SimpleNamespace(id=3, name="Strategy 3", model_type="poisson", parameters={}, is_active=True),
    ]
    dataset = SimpleNamespace(id=29)
    resolution = DatasetMatchResolution(
        dataset=dataset,
        scrape_job_id=181,
        scrape_job_status="completed",
        match_ids=[101, 102],
        total_records=2,
        resolved_records=2,
        unresolved_records=0,
        resolution_counts={"source_url": 2},
        unresolved_samples=[],
    )
    captured = []

    async def fake_load(_db, strategy_ids):
        assert strategy_ids == [8, 3]
        return selected

    async def fake_resolve(_db, dataset_id, *, user=None):
        assert user.id == 7
        assert user.is_admin is True
        assert dataset_id == 29
        return resolution

    async def fake_run_strategy(*, strategy_id, body, db, user):
        captured.append((strategy_id, body, db, user))
        return StrategyRunResponse(
            run_id=1000 + strategy_id,
            status="completed",
            matches_count=6,
            strategy_id=strategy_id,
            dataset_id=body.dataset_id,
            input_hash=f"hash-{strategy_id}",
        )

    monkeypatch.setattr(strategies_api, "load_analysis_strategies", fake_load)
    monkeypatch.setattr(strategies_api, "resolve_dataset_match_ids", fake_resolve)
    monkeypatch.setattr(strategies_api, "run_strategy", fake_run_strategy)
    db = object()
    user = SimpleNamespace(id=7, is_admin=True)

    response = await strategies_api.run_strategy_batch(
        body=StrategyBatchRunRequest(
            strategy_ids=[8, 3],
            dataset_id=29,
            markets=["1x2", "btts"],
            avoid_reprediction=True,
        ),
        db=db,
        user=user,
    )

    assert response.status == "completed"
    assert response.dataset_id == 29
    assert response.scrape_job_id == 181
    assert response.match_ids == [101, 102]
    assert [run.strategy_id for run in response.runs] == [8, 3]
    assert [item[0] for item in captured] == [8, 3]
    assert all(item[1].dataset_id == 29 for item in captured)
    assert all(item[1].match_ids == [101, 102] for item in captured)
    assert all(item[3].is_admin is True for item in captured)


@pytest.mark.asyncio
async def test_batch_refuses_partial_dataset_resolution_by_default(monkeypatch):
    resolution = DatasetMatchResolution(
        dataset=SimpleNamespace(id=29),
        scrape_job_id=181,
        scrape_job_status="completed",
        match_ids=[101],
        total_records=2,
        resolved_records=1,
        unresolved_records=1,
        resolution_counts={"source_url": 1},
        unresolved_samples=[{"record_index": 1, "reason": "no_deterministic_match"}],
    )

    async def fake_load(_db, _strategy_ids):
        return [SimpleNamespace(id=8, name="Strategy 8", model_type="poisson", is_active=True)]

    async def fake_resolve(_db, _dataset_id, *, user=None):
        assert user.id == 7
        return resolution

    monkeypatch.setattr(strategies_api, "load_analysis_strategies", fake_load)
    monkeypatch.setattr(strategies_api, "resolve_dataset_match_ids", fake_resolve)

    with pytest.raises(HTTPException) as exc_info:
        await strategies_api.run_strategy_batch(
            body=StrategyBatchRunRequest(strategy_ids=[8], dataset_id=29),
            db=object(),
            user=SimpleNamespace(id=7),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["resolved_records_count"] == 1
    assert exc_info.value.detail["unresolved_records_count"] == 1


@pytest.mark.asyncio
async def test_batch_rejects_explicit_inactive_or_incompatible_strategies(monkeypatch):
    resolution = DatasetMatchResolution(
        dataset=SimpleNamespace(id=29),
        scrape_job_id=181,
        scrape_job_status="completed",
        match_ids=[101],
        total_records=1,
        resolved_records=1,
        unresolved_records=0,
        resolution_counts={"source_url": 1},
        unresolved_samples=[],
    )
    selected = [
        SimpleNamespace(id=1, name="Inactive", model_type="poisson", parameters={}, is_active=False),
        SimpleNamespace(id=2, name="Invalid", model_type="removed-model", parameters={}, is_active=True),
    ]

    async def fake_load(_db, _strategy_ids):
        return selected

    async def fake_resolve(_db, _dataset_id, *, user=None):
        assert user.id == 7
        return resolution

    monkeypatch.setattr(strategies_api, "load_analysis_strategies", fake_load)
    monkeypatch.setattr(strategies_api, "resolve_dataset_match_ids", fake_resolve)

    with pytest.raises(HTTPException) as exc_info:
        await strategies_api.run_strategy_batch(
            body=StrategyBatchRunRequest(strategy_ids=[1, 2], dataset_id=29),
            db=object(),
            user=SimpleNamespace(id=7),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["message"] == "One or more explicitly selected strategies are not runnable"
    assert [issue["strategy_id"] for issue in exc_info.value.detail["strategies"]] == [1, 2]


@pytest.mark.asyncio
async def test_all_strategy_batch_runs_only_active_runnable_strategies(monkeypatch):
    resolution = DatasetMatchResolution(
        dataset=SimpleNamespace(id=29),
        scrape_job_id=181,
        scrape_job_status="completed",
        match_ids=[101],
        total_records=1,
        resolved_records=1,
        unresolved_records=0,
        resolution_counts={"source_url": 1},
        unresolved_samples=[],
    )
    selected = [
        SimpleNamespace(id=1, name="Poisson", model_type="poisson", parameters={}, is_active=True),
        SimpleNamespace(id=2, name="Invalid", model_type="removed-model", parameters={}, is_active=True),
    ]
    captured = []

    async def fake_load(_db, strategy_ids):
        assert strategy_ids == []
        return selected

    async def fake_resolve(_db, _dataset_id, *, user=None):
        assert user.id == 7
        return resolution

    async def fake_run_strategy(*, strategy_id, body, db, user):
        captured.append(strategy_id)
        return StrategyRunResponse(run_id=101, status="completed", strategy_id=strategy_id, dataset_id=body.dataset_id)

    monkeypatch.setattr(strategies_api, "load_analysis_strategies", fake_load)
    monkeypatch.setattr(strategies_api, "resolve_dataset_match_ids", fake_resolve)
    monkeypatch.setattr(strategies_api, "run_strategy", fake_run_strategy)

    response = await strategies_api.run_strategy_batch(
        body=StrategyBatchRunRequest(strategy_ids=[], dataset_id=29),
        db=object(),
        user=SimpleNamespace(id=7),
    )

    assert captured == [1]
    assert response.strategy_count == 1


class _StrategyRunSession:
    def __init__(self, strategy, matches):
        self.results = [
            _Result(scalar_one=strategy),
            _Result(scalar_one=None),
            _Result(scalars=matches),
            _Result(scalar_one=1),
        ]
        self.added = []

    async def execute(self, _stmt):
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    def begin_nested(self):
        class _Transaction:
            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback):
                return False

        return _Transaction()

    async def flush(self):
        for value in self.added:
            if isinstance(value, PredictionRun) and value.id is None:
                value.id = 77


@pytest.mark.asyncio
async def test_single_strategy_run_persists_exact_input_lineage(monkeypatch):
    strategy = SimpleNamespace(
        id=5,
        name="Argentina Poisson",
        model_type="poisson",
        parameters={},
        is_active=True,
    )
    matches = [SimpleNamespace(id=101, competition="Liga Profesional")]
    db = _StrategyRunSession(strategy, matches)

    async def fake_execute_model(**kwargs):
        assert kwargs["target_match_ids"] == [101]
        return {"target_matches": 1, "written": 3, "failed": 0}

    async def fake_broadcast(_run):
        return None

    async def fake_resolve(_db, dataset_id, *, user=None):
        assert user.id == 9
        assert dataset_id == 29
        return DatasetMatchResolution(
            dataset=SimpleNamespace(id=29),
            scrape_job_id=181,
            scrape_job_status="completed",
            match_ids=[101],
            total_records=1,
            resolved_records=1,
            unresolved_records=0,
            resolution_counts={"source_url": 1},
            unresolved_samples=[],
        )

    monkeypatch.setattr(strategies_api, "execute_single_model_run", fake_execute_model)
    monkeypatch.setattr(strategies_api, "_broadcast_live_prediction_update_if_relevant", fake_broadcast)
    monkeypatch.setattr(strategies_api, "resolve_dataset_match_ids", fake_resolve)

    response = await strategies_api.run_strategy(
        strategy_id=5,
        body=StrategyRunRequest(
            match_ids=[101],
            markets=["1x2"],
            dataset_id=29,
            avoid_reprediction=True,
        ),
        db=db,
        user=SimpleNamespace(id=9),
    )

    run = next(value for value in db.added if isinstance(value, PredictionRun))
    assert response.run_id == 77
    assert response.dataset_id == 29
    assert response.strategy_id == 5
    assert response.matches_count == 1
    assert run.matches_count == 1
    assert response.input_hash == run.input_hash
    assert run.source_dataset_id == 29
    assert run.strategy_id == 5
    assert run.dedupe_enabled is True
    assert {key: value for key, value in run.input_context.items() if key != "execution"} == {
        "source_dataset_id": 29,
        "strategy_id": 5,
        "strategy_model_type": "poisson",
        "match_ids": [101],
        "markets": ["1x2"],
        "filters": None,
        "input_hash": run.input_hash,
    }
    assert run.input_context["execution"] == {
        "status": "completed",
        "written": 3,
        "predicted_matches": 1,
        "fallbacks": 0,
        "per_league": [{"league": "Liga Profesional", "status": "ok", "matches": 1, "written": 3}],
    }


@pytest.mark.asyncio
async def test_strategy_run_marks_model_fallbacks_partial_with_context(monkeypatch):
    strategy = SimpleNamespace(
        id=5,
        name="Argentina Poisson",
        model_type="poisson",
        parameters={},
        is_active=True,
    )
    matches = [SimpleNamespace(id=101, competition="Liga Profesional")]
    db = _StrategyRunSession(strategy, matches)

    async def fake_execute_model(**_kwargs):
        return {
            "target_matches": 1,
            "written": 1,
            "failed": 0,
            "fallbacks": 1,
            "target_errors": [
                {
                    "match_id": 101,
                    "error": "Both teams must have been in the training data",
                    "fallback": "market_consensus_or_neutral",
                }
            ],
        }

    async def fake_broadcast(_run):
        return None

    monkeypatch.setattr(strategies_api, "execute_single_model_run", fake_execute_model)
    monkeypatch.setattr(strategies_api, "_broadcast_live_prediction_update_if_relevant", fake_broadcast)

    response = await strategies_api.run_strategy(
        strategy_id=5,
        body=StrategyRunRequest(match_ids=[101], markets=["1x2"], avoid_reprediction=True),
        db=db,
        user=SimpleNamespace(id=9),
    )

    run = next(value for value in db.added if isinstance(value, PredictionRun))
    assert response.status == "partial"
    assert run.status == "partial"
    assert "1 target matches used model fallback predictions" in response.error
    assert response.context["fallbacks"] == 1
    assert response.context["per_league"][0]["target_errors"][0]["match_id"] == 101


@pytest.mark.asyncio
async def test_direct_strategy_run_rejects_false_dataset_match_lineage(monkeypatch):
    strategy = SimpleNamespace(
        id=5,
        name="Argentina Poisson",
        model_type="poisson",
        parameters={},
        is_active=True,
    )

    class _Db:
        async def execute(self, _stmt):
            return _Result(scalar_one=strategy)

    async def fake_resolve(_db, _dataset_id, *, user=None):
        assert user.id == 9
        return DatasetMatchResolution(
            dataset=SimpleNamespace(id=29),
            scrape_job_id=181,
            scrape_job_status="completed",
            match_ids=[101],
            total_records=1,
            resolved_records=1,
            unresolved_records=0,
            resolution_counts={"source_url": 1},
            unresolved_samples=[],
        )

    monkeypatch.setattr(strategies_api, "resolve_dataset_match_ids", fake_resolve)

    with pytest.raises(HTTPException) as exc_info:
        await strategies_api.run_strategy(
            strategy_id=5,
            body=StrategyRunRequest(match_ids=[999], markets=["1x2"], dataset_id=29),
            db=_Db(),
            user=SimpleNamespace(id=9),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["foreign_match_ids"] == [999]


@pytest.mark.asyncio
async def test_explicit_dataset_matches_are_constrained_by_date_filters():
    db = SimpleNamespace()

    async def execute(_stmt):
        return _Result(rows=[(102,), (103,)])

    db.execute = execute
    filtered = await strategies_api._filter_explicit_match_ids_by_date(
        db,
        [101, 102, 103],
        SimpleNamespace(date_from="2026-07-14", date_to="2026-07-15"),
    )

    assert filtered == [102, 103]


@pytest.mark.asyncio
async def test_batch_continues_after_strategy_exception_and_commits_each_completed_run(monkeypatch):
    resolution = DatasetMatchResolution(
        dataset=SimpleNamespace(id=29),
        scrape_job_id=181,
        scrape_job_status="completed",
        match_ids=[101],
        total_records=1,
        resolved_records=1,
        unresolved_records=0,
        resolution_counts={"source_url": 1},
        unresolved_samples=[],
    )

    async def fake_load(_db, _strategy_ids):
        return [
            SimpleNamespace(id=1, name="Strategy 1", model_type="poisson", parameters={}, is_active=True),
            SimpleNamespace(id=2, name="Strategy 2", model_type="poisson", parameters={}, is_active=True),
            SimpleNamespace(id=3, name="Strategy 3", model_type="poisson", parameters={}, is_active=True),
        ]

    async def fake_resolve(_db, _dataset_id, *, user=None):
        assert user.id == 7
        return resolution

    async def fake_run_strategy(*, strategy_id, body, db, user):
        if strategy_id == 2:
            raise RuntimeError("bridge crashed")
        return StrategyRunResponse(
            run_id=100 + strategy_id,
            status="completed",
            matches_count=1,
            strategy_id=strategy_id,
            dataset_id=body.dataset_id,
        )

    async def fake_broadcast(_run):
        return None

    class _Db:
        commits = 0
        rollbacks = 0

        def __init__(self):
            self.added = []

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            for value in self.added:
                if isinstance(value, PredictionRun) and value.id is None:
                    value.id = 202

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    monkeypatch.setattr(strategies_api, "load_analysis_strategies", fake_load)
    monkeypatch.setattr(strategies_api, "resolve_dataset_match_ids", fake_resolve)
    monkeypatch.setattr(strategies_api, "run_strategy", fake_run_strategy)
    monkeypatch.setattr(strategies_api, "_broadcast_live_prediction_update_if_relevant", fake_broadcast)
    db = _Db()

    response = await strategies_api.run_strategy_batch(
        body=StrategyBatchRunRequest(strategy_ids=[1, 2, 3], dataset_id=29),
        db=db,
        user=SimpleNamespace(id=7),
    )

    assert response.status == "partial"
    assert [run.status for run in response.runs] == ["completed", "failed", "completed"]
    assert response.runs[1].error == "Unexpected strategy execution error: bridge crashed"
    assert response.runs[1].run_id == 202
    assert response.runs[1].input_hash
    assert db.commits == 3
    assert db.rollbacks == 1
