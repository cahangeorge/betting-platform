from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException, Response
from starlette.requests import Request

from app.api.deps import get_current_user
from app.api.v1 import auth as auth_api
from app.api.v1 import dashboard as dashboard_api
from app.api.v1 import data as data_api
from app.api.v1 import job_runs as job_runs_api
from app.api.v1 import jobs as jobs_api
from app.api.v1 import matches as matches_api
from app.api.v1 import predictions as predictions_api
from app.api.v1 import tickets as tickets_api
from app.api.v1.catalog import CATALOG
from app.schemas.auth import LoginRequest, SignupRequest
from app.schemas.data import ScrapeJobCreateRequest, WorldCupPipelineRequest
from app.schemas.match import MatchResponse
from app.schemas.ticket import SettlementResponse, TicketCreateRequest, TicketGenerateRequest
from app.services.auth import hash_password, verify_password


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeListResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeAuthDb:
    def __init__(self, existing_user=None):
        self.user = existing_user

    async def execute(self, *_args, **_kwargs):
        return _FakeScalarResult(self.user)

    def add(self, user):
        user.id = getattr(user, "id", None) or 1
        self.user = user

    async def flush(self):
        return None

    async def commit(self):
        return None


def _set_cookie_header_values(response: Response) -> list[str]:
    return [
        value.decode("latin-1") for key, value in response.raw_headers if key.decode("latin-1").lower() == "set-cookie"
    ]


@pytest.mark.asyncio
async def test_dataset_list_filters_by_originating_scrape_job_before_pagination():
    own = SimpleNamespace(id=1, data={"job_id": 11})
    foreign = SimpleNamespace(id=2, data={"job_id": 22})
    orphan = SimpleNamespace(id=3, data={})
    own_job = SimpleNamespace(id=11, params={"_created_by_user_id": 7})
    foreign_job = SimpleNamespace(id=22, params={"_created_by_user_id": 8})

    class _Db:
        def __init__(self):
            self.results = [_FakeListResult([foreign, orphan, own]), _FakeListResult([own_job, foreign_job])]

        async def execute(self, _stmt):
            return self.results.pop(0)

    visible = await data_api.list_datasets(
        page=1,
        per_page=20,
        db=_Db(),
        user=SimpleNamespace(id=7, is_admin=False),
    )

    assert [dataset.id for dataset in visible] == [1]


@pytest.mark.asyncio
async def test_dataset_get_rejects_foreign_owner_but_allows_admin():
    dataset = SimpleNamespace(id=2, data={"job_id": 22})
    foreign_job = SimpleNamespace(id=22, params={"_created_by_user_id": 8})

    class _Db:
        async def get(self, model, object_id):
            if model.__name__ == "ScrapedDataset":
                return dataset if object_id == dataset.id else None
            if model.__name__ == "ScrapeJob":
                return foreign_job if object_id == foreign_job.id else None
            raise AssertionError(model)

    with pytest.raises(HTTPException) as exc_info:
        await data_api.get_dataset(
            dataset_id=2,
            db=_Db(),
            user=SimpleNamespace(id=7, is_admin=False),
        )
    assert exc_info.value.status_code == 403

    assert (
        await data_api.get_dataset(
            dataset_id=2,
            db=_Db(),
            user=SimpleNamespace(id=1, is_admin=True),
        )
        is dataset
    )


@pytest.mark.asyncio
async def test_signup_returns_tokens_and_sets_auth_cookies():
    response = Response()
    body = SignupRequest(email="  NewUser@Example.com  ", password="password123", name="New User")

    request = Request({"type": "http", "client": ("198.51.100.1", 1234)})
    token = await auth_api.signup(body=body, request=request, response=response, db=_FakeAuthDb())

    assert token.access_token
    set_cookie_values = _set_cookie_header_values(response)
    assert any("access_token=" in value for value in set_cookie_values)
    assert any("refresh_token=" in value for value in set_cookie_values)


@pytest.mark.asyncio
async def test_login_normalizes_email_and_sets_auth_cookies():
    fake_user = SimpleNamespace(
        id=42,
        email="test@example.com",
        password_hash=hash_password("password123"),
    )
    response = Response()
    body = LoginRequest(email="  TEST@EXAMPLE.COM  ", password="password123")

    request = Request({"type": "http", "client": ("198.51.100.2", 1234)})
    token = await auth_api.login(body=body, request=request, response=response, db=_FakeAuthDb(existing_user=fake_user))

    assert token.access_token
    set_cookie_values = _set_cookie_header_values(response)
    assert any("access_token=" in value for value in set_cookie_values)
    assert any("refresh_token=" in value for value in set_cookie_values)


def test_verify_password_returns_false_for_malformed_hash():
    assert verify_password("password123", "not-a-bcrypt-hash") is False


@pytest.mark.asyncio
async def test_get_current_user_requires_authentication_without_token():
    request = Request({"type": "http", "headers": []})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request=request, db=object(), access_token=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_without_token():
    from app.api.deps import get_current_user_optional

    request = Request({"type": "http", "headers": []})

    user = await get_current_user_optional(request=request, db=object(), access_token=None)

    assert user is None


@pytest.mark.asyncio
async def test_ticket_creation_maps_domain_validation_errors(monkeypatch):
    captured = {}

    async def fake_create_manual_ticket(**kwargs):
        captured.update(kwargs)
        raise ValueError("Insufficient bankroll balance")

    monkeypatch.setattr(tickets_api, "create_manual_ticket", fake_create_manual_ticket)

    with pytest.raises(HTTPException) as exc_info:
        await tickets_api.create_new_ticket(
            body=TicketCreateRequest(
                ticket_type="single",
                stake=10,
                bankroll_id=5,
                legs=[{"match_id": 1, "market": "1x2", "selection": "home", "odds": 2.0}],
            ),
            db=object(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Insufficient bankroll balance"
    assert captured["accumulator_risk_acknowledged"] is False
    assert captured["legs_data"] == [{"match_id": 1, "selection": "home", "market": "1x2", "odds": 2.0}]


@pytest.mark.asyncio
async def test_ticket_creation_maps_domain_permission_errors(monkeypatch):
    async def fake_create_manual_ticket(**kwargs):
        raise PermissionError("Bankroll 5 does not belong to the current user")

    monkeypatch.setattr(tickets_api, "create_manual_ticket", fake_create_manual_ticket)

    with pytest.raises(HTTPException) as exc_info:
        await tickets_api.create_new_ticket(
            body=TicketCreateRequest(
                ticket_type="single",
                stake=10,
                bankroll_id=5,
                legs=[{"match_id": 1, "market": "1x2", "selection": "home", "odds": 2.0}],
            ),
            db=object(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Bankroll 5 does not belong to the current user"


@pytest.mark.asyncio
async def test_manual_ticket_creation_requires_explicit_risk_policy(monkeypatch):
    report = {
        "risk_assessment": {
            "allowed": False,
            "blockers": [{"code": "risk_policy_required", "scope": "policy"}],
        }
    }

    async def fake_create_manual_ticket(**_kwargs):
        raise tickets_api.TicketRiskPolicyRequiredError("An explicit risk policy is required", report)

    monkeypatch.setattr(tickets_api, "create_manual_ticket", fake_create_manual_ticket)

    with pytest.raises(HTTPException) as exc_info:
        await tickets_api.create_new_ticket(
            body=TicketCreateRequest(
                ticket_type="single",
                stake=1,
                bankroll_id=5,
                legs=[{"match_id": 1, "market": "1x2", "selection": "home", "odds": 2.0}],
            ),
            db=object(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 428
    assert exc_info.value.detail == {
        "code": "risk_policy_required",
        "message": "An explicit risk policy is required",
        "report": report,
    }


@pytest.mark.asyncio
async def test_manual_ticket_creation_returns_conflict_for_current_risk_blocker(monkeypatch):
    report = {
        "risk_assessment": {
            "allowed": False,
            "blockers": [{"code": "responsible_gambling_pause_active", "scope": "policy"}],
        }
    }

    async def fake_create_manual_ticket(**_kwargs):
        raise tickets_api.TicketManualRiskConflictError("Manual ticket is blocked", report)

    monkeypatch.setattr(tickets_api, "create_manual_ticket", fake_create_manual_ticket)

    with pytest.raises(HTTPException) as exc_info:
        await tickets_api.create_new_ticket(
            body=TicketCreateRequest(
                ticket_type="single",
                stake=1,
                bankroll_id=5,
                legs=[{"match_id": 1, "market": "1x2", "selection": "home", "odds": 2.0}],
            ),
            db=object(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "risk_policy_blocked",
        "message": "Manual ticket is blocked",
        "report": report,
    }


@pytest.mark.asyncio
async def test_ticket_batch_discard_returns_explicit_cleanup_receipt(monkeypatch):
    async def fake_discard_generated_ticket_batch(**kwargs):
        assert kwargs["user_id"] == 12
        assert kwargs["batch_id"] == 77
        return 77, 5

    monkeypatch.setattr(tickets_api, "discard_generated_ticket_batch", fake_discard_generated_ticket_batch)

    response = await tickets_api.discard_generated_batch(
        batch_id=77,
        db=object(),
        user=SimpleNamespace(id=12),
    )

    assert response.model_dump() == {
        "batch_id": 77,
        "status": "discarded",
        "discarded_tickets": 5,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (LookupError("Ticket batch not found"), 404),
        (tickets_api.TicketBatchDiscardConflictError("Only generated drafts can be discarded"), 409),
    ],
)
async def test_ticket_batch_discard_maps_not_found_and_conflict_errors(monkeypatch, error, expected_status):
    async def fake_discard_generated_ticket_batch(**_kwargs):
        raise error

    monkeypatch.setattr(tickets_api, "discard_generated_ticket_batch", fake_discard_generated_ticket_batch)

    with pytest.raises(HTTPException) as exc_info:
        await tickets_api.discard_generated_batch(
            batch_id=77,
            db=object(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == str(error)


@pytest.mark.asyncio
async def test_ticket_generation_passes_explicit_prediction_run_id(monkeypatch):
    captured = {}

    async def fake_generate_tickets(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=77), []

    monkeypatch.setattr(tickets_api, "generate_tickets", fake_generate_tickets)

    result = await tickets_api.generate_ticket_batch(
        body=TicketGenerateRequest(
            bankroll_id=5,
            run_id=31,
            prediction_ids=[401, 402],
            ticket_count=1,
            difficulty="safe",
            market_types=["1x2"],
            min_odds=1.2,
            max_odds=3.0,
        ),
        db=object(),
        user=SimpleNamespace(id=12),
    )

    assert result.batch_id == 77
    assert captured["user_id"] == 12
    assert captured["run_id"] == 31
    assert captured["prediction_ids"] == [401, 402]
    assert captured["ticket_format"] == "single"
    assert "stake" not in captured


def test_ticket_generation_request_bounds_ticket_count():
    with pytest.raises(ValueError):
        TicketGenerateRequest(ticket_count=0)
    with pytest.raises(ValueError):
        TicketGenerateRequest(ticket_count=51)


def test_ticket_generation_request_rejects_ambiguous_or_invalid_configuration():
    with pytest.raises(ValueError, match="bankroll_id"):
        TicketGenerateRequest()
    with pytest.raises(ValueError, match="explicit prediction lineage"):
        TicketGenerateRequest(bankroll_id=5)
    with pytest.raises(ValueError, match="either run_id or run_ids"):
        TicketGenerateRequest(bankroll_id=5, run_id=31, run_ids=[31])
    with pytest.raises(ValueError):
        TicketGenerateRequest(bankroll_id=5, run_id=31, market_types=[])
    with pytest.raises(ValueError):
        TicketGenerateRequest(bankroll_id=5, run_id=31, market_types=["unsupported"])
    with pytest.raises(ValueError, match="min_odds"):
        TicketGenerateRequest(bankroll_id=5, run_id=31, min_odds=3.0, max_odds=2.0)


@pytest.mark.asyncio
async def test_ticket_batch_activation_returns_transitioned_tickets(monkeypatch):
    batch = SimpleNamespace(id=77)
    tickets = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    async def fake_activate(**kwargs):
        assert kwargs["user_id"] == 12
        assert kwargs["batch_id"] == 77
        return batch, tickets, 25.0

    async def fake_load(_db, ticket_ids, user_id):
        assert user_id == 12
        return [
            tickets_api.TicketResponse(
                id=ticket_id,
                stake=10.0,
                total_odds=2.0,
                potential_return=20.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            for ticket_id in ticket_ids
        ]

    monkeypatch.setattr(tickets_api, "activate_ticket_batch", fake_activate)
    monkeypatch.setattr(tickets_api, "_load_ticket_summaries", fake_load)

    response = await tickets_api.activate_generated_ticket_batch(
        batch_id=77,
        body=tickets_api.TicketBatchActivateRequest(expected_revision=1, review_acknowledged=True),
        db=object(),
        user=SimpleNamespace(id=12),
    )

    assert response.batch_id == 77
    assert response.status == "activated"
    assert response.debited_amount == 25.0
    assert [ticket.id for ticket in response.tickets] == [1, 2]


@pytest.mark.asyncio
async def test_ticket_batch_activation_maps_repeat_to_conflict(monkeypatch):
    async def fake_activate(**_kwargs):
        raise tickets_api.TicketActivationConflictError("Ticket batch can only be activated once")

    monkeypatch.setattr(tickets_api, "activate_ticket_batch", fake_activate)

    with pytest.raises(HTTPException) as exc_info:
        await tickets_api.activate_generated_ticket_batch(
            batch_id=77,
            body=tickets_api.TicketBatchActivateRequest(expected_revision=1, review_acknowledged=True),
            db=object(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Ticket batch can only be activated once"


@pytest.mark.asyncio
async def test_ticket_generation_returns_truthful_candidate_exclusion_report(monkeypatch):
    report = {
        "prediction_run_id": 31,
        "scanned_predictions": 2,
        "eligible_candidates": 0,
        "excluded_predictions": 2,
        "excluded_by_reason": {"match_started_or_finished": 2},
    }

    async def fake_generate_tickets(**_kwargs):
        raise tickets_api.TicketGenerationError("No safe prediction candidates are eligible", report)

    monkeypatch.setattr(tickets_api, "generate_tickets", fake_generate_tickets)

    with pytest.raises(HTTPException) as exc_info:
        await tickets_api.generate_ticket_batch(
            body=TicketGenerateRequest(
                bankroll_id=5,
                run_id=31,
                ticket_count=1,
                difficulty="safe",
                market_types=["1x2"],
                min_odds=1.2,
                max_odds=3.0,
            ),
            db=object(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "No safe prediction candidates are eligible. Excluded 2/2 predictions: match_started_or_finished=2."
    )


@pytest.mark.asyncio
async def test_scrape_execute_maps_lookup_errors_to_404(monkeypatch):
    job = SimpleNamespace(id=999, params={"_created_by_user_id": 12})

    class _DB:
        async def get(self, model, job_id):
            assert job_id == job.id
            return job

    async def fake_execute_scrape_job(db, job_id):
        raise LookupError(f"ScrapeJob {job_id} not found")

    monkeypatch.setattr(data_api, "execute_scrape_job", fake_execute_scrape_job)

    with pytest.raises(HTTPException) as exc_info:
        await data_api.run_scrape_job(
            job_id=999,
            db=_DB(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "ScrapeJob 999 not found"


@pytest.mark.asyncio
async def test_scrape_start_returns_created_job(monkeypatch):
    fake_job = SimpleNamespace(
        id=44,
        job_type="oddsportal",
        status="pending",
        league="Premier League",
        params={"sport": "football"},
        started_at=None,
        completed_at=None,
        error=None,
        created_at=None,
    )

    async def fake_create_scrape_job(db, job_type, league, params):
        assert job_type == "oddsportal"
        assert league == "Premier League"
        assert params == {"sport": "football", "_created_by_user_id": 12}
        return fake_job

    monkeypatch.setattr(data_api, "create_scrape_job", fake_create_scrape_job)

    result = await data_api.start_scrape_job(
        body=ScrapeJobCreateRequest(job_type="oddsportal", league="Premier League", params={"sport": "football"}),
        response=Response(),
        idempotency_key=None,
        db=object(),
        user=SimpleNamespace(id=12),
    )

    assert result is fake_job


@pytest.mark.asyncio
async def test_scrape_background_execute_enqueues_task(monkeypatch):
    fake_job = SimpleNamespace(
        id=45,
        job_type="scrape_odds",
        status="pending",
        league=None,
        params={"_created_by_user_id": 12},
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
        created_at=datetime.now(timezone.utc),
    )

    class _DB:
        async def get(self, model, job_id):
            assert job_id == fake_job.id
            return fake_job

    queued = []

    async def fake_enqueue(db, *, scrape_job_id, triggered_by, user_id):
        queued.append((scrape_job_id, triggered_by, user_id))
        return SimpleNamespace(
            id=701,
            task_type="scrape_job",
            status="queued",
            scheduled_job_id=None,
            scrape_job_id=scrape_job_id,
            artifacts={"user_id": user_id},
        )

    monkeypatch.setattr(data_api, "enqueue_scrape_job_execution", fake_enqueue)
    background_tasks = BackgroundTasks()

    result = await data_api.run_scrape_job_background(
        job_id=fake_job.id,
        background_tasks=background_tasks,
        db=_DB(),
        user=SimpleNamespace(id=12),
    )

    assert result.id == fake_job.id
    assert result.queued_run_id == 701
    assert result.queued_run is not None
    assert queued == [(fake_job.id, "api", 12)]
    assert len(background_tasks.tasks) == 0


@pytest.mark.asyncio
async def test_scrape_background_execute_returns_404_when_missing():
    class _DB:
        async def get(self, model, job_id):
            return None

    with pytest.raises(HTTPException) as exc_info:
        await data_api.run_scrape_job_background(
            job_id=999,
            background_tasks=BackgroundTasks(),
            db=_DB(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_scrape_background_execute_surfaces_taskiq_enqueue_failures(monkeypatch):
    fake_job = SimpleNamespace(
        id=45,
        job_type="scrape_odds",
        status="pending",
        league=None,
        params={"_created_by_user_id": 12},
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
        created_at=datetime.now(timezone.utc),
    )
    failed_run = SimpleNamespace(id=702, status="enqueue_failed")

    class _DB:
        async def get(self, model, job_id):
            return fake_job

    async def fake_enqueue(db, *, scrape_job_id, triggered_by, user_id):
        raise data_api.TaskEnqueueError(failed_run, "redis down")

    monkeypatch.setattr(data_api, "enqueue_scrape_job_execution", fake_enqueue)

    with pytest.raises(HTTPException) as exc_info:
        await data_api.run_scrape_job_background(
            job_id=fake_job.id,
            background_tasks=BackgroundTasks(),
            db=_DB(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {"message": "Task queue publish failed", "run_id": failed_run.id}


@pytest.mark.asyncio
async def test_scrape_job_runs_are_listed_by_scrape_job_id_for_owner():
    fake_job = SimpleNamespace(id=45, params={"_created_by_user_id": 12})
    fake_run = SimpleNamespace(
        id=701,
        task_type="scrape_job",
        status="queued",
        scrape_job_id=fake_job.id,
        artifacts={"user_id": 12},
        scheduled_job_id=None,
    )

    class _RunScalars:
        def all(self):
            return [fake_run]

    class _RunResult:
        def scalars(self):
            return _RunScalars()

    class _DB:
        async def get(self, model, row_id):
            return fake_job if row_id == fake_job.id else None

        async def execute(self, stmt):
            return _RunResult()

    result = await data_api.get_scrape_job_runs(
        job_id=fake_job.id,
        page=1,
        per_page=20,
        db=_DB(),
        user=SimpleNamespace(id=12, is_admin=False),
    )

    assert result.total == 1
    assert len(result.runs) == 1
    assert result.runs[0].id == fake_run.id
    assert result.runs[0].scrape_job_id == fake_job.id
    assert result.runs[0].status == "queued"
    assert result.page == 1
    assert result.per_page == 20


@pytest.mark.asyncio
async def test_scrape_job_runs_owner_can_list_empty_page():
    fake_job = SimpleNamespace(id=45, params={"_created_by_user_id": 12})

    class _RunScalars:
        def all(self):
            return []

    class _RunResult:
        def scalars(self):
            return _RunScalars()

    class _DB:
        async def get(self, model, row_id):
            return fake_job

        async def execute(self, stmt):
            return _RunResult()

    result = await data_api.get_scrape_job_runs(
        job_id=fake_job.id,
        page=1,
        per_page=20,
        db=_DB(),
        user=SimpleNamespace(id=12, is_admin=False),
    )

    assert result.total == 0
    assert result.runs == []


@pytest.mark.asyncio
async def test_scrape_job_runs_reject_non_owner():
    fake_job = SimpleNamespace(id=45, params={"_created_by_user_id": 99})
    fake_run = SimpleNamespace(
        id=701,
        task_type="scrape_job",
        status="queued",
        scrape_job_id=fake_job.id,
        artifacts={"user_id": 99},
        scheduled_job_id=None,
    )

    class _RunScalars:
        def all(self):
            return [fake_run]

    class _RunResult:
        def scalars(self):
            return _RunScalars()

    class _DB:
        async def get(self, model, row_id):
            return fake_job if row_id == fake_job.id else None

        async def execute(self, stmt):
            return _RunResult()

    with pytest.raises(HTTPException) as exc_info:
        await data_api.get_scrape_job_runs(
            job_id=fake_job.id,
            page=1,
            per_page=20,
            db=_DB(),
            user=SimpleNamespace(id=12, is_admin=False),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_scheduled_jobs_filters_to_current_user():
    owned = SimpleNamespace(id=1, config={"_created_by_user_id": 12})
    foreign = SimpleNamespace(id=2, config={"_created_by_user_id": 99})
    legacy_unowned = SimpleNamespace(id=3, config={})

    class _Scalars:
        def all(self):
            return [owned, foreign, legacy_unowned]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _DB:
        async def execute(self, *_args, **_kwargs):
            return _Result()

    result = await jobs_api.list_scheduled_jobs(db=_DB(), user=SimpleNamespace(id=12, is_admin=False))

    assert result == [owned]


@pytest.mark.asyncio
async def test_list_scheduled_jobs_shows_all_for_admin():
    owned = SimpleNamespace(id=1, config={"_created_by_user_id": 12})
    foreign = SimpleNamespace(id=2, config={"_created_by_user_id": 99})
    legacy_unowned = SimpleNamespace(id=3, config={})

    class _Scalars:
        def all(self):
            return [owned, foreign, legacy_unowned]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _DB:
        async def execute(self, *_args, **_kwargs):
            return _Result()

    result = await jobs_api.list_scheduled_jobs(db=_DB(), user=SimpleNamespace(id=12, is_admin=True))

    assert result == [owned, foreign, legacy_unowned]


@pytest.mark.asyncio
async def test_scheduled_job_detail_and_toggle_require_owner():
    job = SimpleNamespace(id=10, config={"_created_by_user_id": 99}, enabled=True)

    class _DB:
        flushes = 0

        async def get(self, _model, row_id):
            return job if row_id == job.id else None

        async def flush(self):
            self.flushes += 1

    db = _DB()

    with pytest.raises(HTTPException) as exc_info:
        await jobs_api.get_scheduled_job(job_id=job.id, db=db, user=SimpleNamespace(id=12, is_admin=False))
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        await jobs_api.toggle_scheduled_job(job_id=job.id, db=db, _user=SimpleNamespace(id=12, is_admin=False))
    assert exc_info.value.status_code == 403
    assert job.enabled is True
    assert db.flushes == 0

    result = await jobs_api.toggle_scheduled_job(job_id=job.id, db=db, _user=SimpleNamespace(id=99, is_admin=False))
    assert result is job
    assert job.enabled is False
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_direct_job_run_requires_owner_or_admin():
    run = SimpleNamespace(id=701, scheduled_job_id=12, task_type="scrape_job", status="queued")
    job = SimpleNamespace(id=12, config={"_created_by_user_id": 99})

    class _DB:
        async def get(self, model, row_id):
            return run if row_id == run.id else job

    with pytest.raises(HTTPException) as exc_info:
        await job_runs_api.get_job_run(
            run_id=run.id,
            db=_DB(),
            user=SimpleNamespace(id=12, is_admin=False),
        )

    assert exc_info.value.status_code == 403

    result = await job_runs_api.get_job_run(
        run_id=run.id,
        db=_DB(),
        user=SimpleNamespace(id=99, is_admin=False),
    )
    assert result is run


@pytest.mark.asyncio
async def test_direct_api_triggered_job_run_allows_artifact_owner():
    run = SimpleNamespace(
        id=702,
        scheduled_job_id=None,
        scrape_job_id=45,
        artifacts={"user_id": 12},
        task_type="scrape_job",
        status="queued",
    )

    class _DB:
        async def get(self, model, row_id):
            return run

    result = await job_runs_api.get_job_run(
        run_id=run.id,
        db=_DB(),
        user=SimpleNamespace(id=12, is_admin=False),
    )

    assert result is run


def test_world_cup_pipeline_request_defaults_to_safe_ticket_generation():
    default_request = WorldCupPipelineRequest()
    explicit_request = WorldCupPipelineRequest(allow_experimental_tickets=True)
    tomorrow_request = WorldCupPipelineRequest(
        target_date="2026-06-21",
        target_date_from="2026-06-20T21:00:00.000Z",
        target_date_to="2026-06-21T20:59:59.999Z",
        max_historic_seasons=2,
        upcoming_timeout_seconds=900,
        historic_timeout_seconds=120,
    )

    assert default_request.allow_experimental_tickets is False
    assert default_request.scraper_engine == "playwright"
    assert explicit_request.allow_experimental_tickets is True
    assert tomorrow_request.target_date == "2026-06-21"
    assert tomorrow_request.target_date_from == "2026-06-20T21:00:00.000Z"
    assert tomorrow_request.max_historic_seasons == 2
    assert tomorrow_request.upcoming_timeout_seconds == 900
    assert tomorrow_request.historic_timeout_seconds == 120


def test_prediction_verification_maps_pick_to_probability_and_odds():
    prediction = SimpleNamespace(
        market="1x2",
        home_prob=0.61,
        draw_prob=0.22,
        away_prob=0.17,
        home_odds=1.91,
        draw_odds=3.4,
        away_odds=4.8,
    )

    assert predictions_api._prediction_value_for_selection(prediction, "home", "prob") == 0.61
    assert predictions_api._prediction_value_for_selection(prediction, "home", "odds") == 1.91
    assert predictions_api._prediction_value_for_selection(prediction, "draw", "prob") == 0.22


def test_prediction_verification_maps_btts_and_totals_to_home_away_fields():
    prediction = SimpleNamespace(
        market="over_under_2_5",
        home_prob=0.57,
        draw_prob=None,
        away_prob=0.43,
        home_odds=1.85,
        draw_odds=None,
        away_odds=2.05,
    )

    assert predictions_api._prediction_value_for_selection(prediction, "over", "prob") == 0.57
    assert predictions_api._prediction_value_for_selection(prediction, "under", "odds") == 2.05


def test_serialize_ticket_summary_includes_reference_returns_and_legs():
    ticket = SimpleNamespace(
        id=18,
        user_id=12,
        bankroll_id=7,
        batch_id=None,
        ticket_type="single",
        stake=10.0,
        total_odds=1.91,
        potential_return=19.1,
        status="won",
        created_at=datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc),
        legs=[
            SimpleNamespace(
                id=101,
                ticket_id=18,
                model_prediction_id=42,
                match_id=55,
                selection="home",
                market="1x2",
                odds=1.91,
                bookmaker="Pinnacle",
                status="won",
                created_at=datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc),
                match=SimpleNamespace(
                    id=55,
                    competition="World Championship 2026",
                    home_team="Spain",
                    away_team="Saudi Arabia",
                    match_date=datetime(2026, 6, 21, 19, 0, tzinfo=timezone.utc),
                    status="scheduled",
                ),
            )
        ],
    )

    summary = tickets_api._serialize_ticket_summary(
        ticket,
        reference="TKT-18",
        actual_return=19.1,
        settled_at=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    assert summary.reference == "TKT-18"
    assert summary.actual_return == 19.1
    assert summary.settled_at.isoformat() == "2026-06-16T12:00:00+00:00"
    assert len(summary.legs) == 1
    assert summary.legs[0].model_prediction_id == 42
    assert summary.legs[0].match == {
        "id": 55,
        "league": "World Championship 2026",
        "home_team": "Spain",
        "away_team": "Saudi Arabia",
        "start_time": datetime(2026, 6, 21, 19, 0, tzinfo=timezone.utc),
        "status": "scheduled",
    }


def test_compute_ticket_stats_summarizes_history():
    tickets = [
        SimpleNamespace(id=1, status="open"),
        SimpleNamespace(id=2, status="won"),
        SimpleNamespace(id=3, status="lost"),
        SimpleNamespace(id=4, status="won"),
    ]
    settlements = {
        2: SimpleNamespace(return_amount=18.5, pnl=8.5, settled_at=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)),
        3: SimpleNamespace(return_amount=0.0, pnl=-10.0, settled_at=datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)),
        4: SimpleNamespace(return_amount=23.0, pnl=13.0, settled_at=datetime(2026, 6, 16, 14, 0, tzinfo=timezone.utc)),
    }

    stats = tickets_api._compute_ticket_stats(tickets, settlements)

    assert stats == {"total": 4, "won": 2, "lost": 1, "profit_loss": 11.5}


@pytest.mark.asyncio
async def test_ticket_stats_uses_one_sql_aggregate_with_latest_settlement_semantics():
    class _AggregateResult:
        def one(self):
            return SimpleNamespace(total=4, won=2, lost=1, profit_loss=11.5)

    class _Db:
        def __init__(self):
            self.statements = []

        async def execute(self, stmt):
            self.statements.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
            return _AggregateResult()

    db = _Db()
    response = await tickets_api.get_ticket_stats(db=db, user=SimpleNamespace(id=7))

    assert response.model_dump() == {"total": 4, "won": 2, "lost": 1, "profit_loss": 11.5}
    assert len(db.statements) == 1
    assert "row_number() OVER (PARTITION BY settlements.ticket_id" in db.statements[0]
    assert "tickets.user_id = 7" in db.statements[0]


def test_dashboard_date_parser_returns_timezone_aware_bounds():
    start = dashboard_api._parse_dashboard_datetime("2026-06-13")
    end = dashboard_api._parse_dashboard_datetime("2026-06-13", end_of_day=True)

    assert start.isoformat() == "2026-06-13T00:00:00+00:00"
    assert end.isoformat() == "2026-06-13T23:59:59.999999+00:00"


def test_dashboard_range_bounds_support_requested_selector_values():
    now = datetime(2026, 6, 23, 16, 30, tzinfo=timezone.utc)

    today_start, today_end = dashboard_api._dashboard_range_bounds("today", now=now)
    week_start, week_end = dashboard_api._dashboard_range_bounds("7d", now=now)
    month_start, month_end = dashboard_api._dashboard_range_bounds("1m", now=now)
    quarter_start, quarter_end = dashboard_api._dashboard_range_bounds("3m", now=now)
    half_start, half_end = dashboard_api._dashboard_range_bounds("6m", now=now)
    year_start, year_end = dashboard_api._dashboard_range_bounds("1y", now=now)

    assert today_start.isoformat() == "2026-06-23T00:00:00+00:00"
    assert (today_end - today_start).days == 1
    assert (week_end - week_start).days == 7
    assert (month_end - month_start).days == 31
    assert (quarter_end - quarter_start).days == 93
    assert (half_end - half_start).days == 186
    assert (year_end - year_start).days == 366


def test_dashboard_ticket_outcome_buckets_count_statuses_by_day():
    start = datetime(2026, 6, 21, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 24, 0, 0, tzinfo=timezone.utc)
    tickets = [
        SimpleNamespace(id=1, status="won", created_at=datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)),
        SimpleNamespace(id=2, status="lost", created_at=datetime(2026, 6, 21, 13, 0, tzinfo=timezone.utc)),
        SimpleNamespace(id=3, status="open", created_at=datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)),
        SimpleNamespace(id=4, status="void", created_at=datetime(2026, 6, 23, 10, 0, tzinfo=timezone.utc)),
    ]

    response = dashboard_api._build_ticket_outcome_buckets(tickets, range_key="7d", start=start, end=end)

    assert response.range == "7d"
    assert len(response.items) == 3
    assert response.items[0].won == 1
    assert response.items[0].lost == 1
    assert response.items[0].ticket_ids == [1, 2]
    assert response.items[1].pending == 1
    assert response.items[1].ticket_ids == [3]
    assert response.items[2].void == 1
    assert response.items[2].ticket_ids == [4]


def test_match_response_maps_competition_date_and_odds():
    fake_match = SimpleNamespace(
        id=91,
        external_id="fixture-91",
        home_team="Alpha FC",
        away_team="Beta United",
        home_score=None,
        away_score=None,
        status="scheduled",
        match_date=datetime(2026, 6, 17, 18, 30, tzinfo=timezone.utc),
        competition="Test League",
        season="2026",
        created_at=datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 17, 9, 5, tzinfo=timezone.utc),
        odds=[
            SimpleNamespace(
                id=301,
                match_id=91,
                bookmaker="Pinnacle",
                market="1x2",
                home_odds=1.95,
                draw_odds=3.2,
                away_odds=4.1,
                timestamp=datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc),
                created_at=datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc),
            )
        ],
    )

    payload = MatchResponse.model_validate(fake_match)

    assert payload.league == "Test League"
    assert payload.start_time == "2026-06-17T18:30:00+00:00"
    assert payload.odds[0].bookmaker == "Pinnacle"
    assert payload.odds[0].home_odds == 1.95


def test_match_filter_datetime_parser_accepts_browser_iso_offsets():
    parsed = matches_api._parse_match_filter_datetime("2026-06-19T00:00:00+00:00")

    assert parsed == datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)


def test_match_filter_datetime_parser_accepts_browser_utc_z_suffix():
    parsed = matches_api._parse_match_filter_datetime("2026-06-19T23:59:59Z")

    assert parsed == datetime(2026, 6, 19, 23, 59, 59, tzinfo=timezone.utc)


def test_catalog_exposes_scrape_slugs_and_world_cup():
    leagues = {league.id: league for country in CATALOG for league in country.leagues}

    assert leagues["premier_league"].scrape_slug == "england-premier-league"
    assert leagues["world_cup"].name == "World Cup"
    assert leagues["world_cup"].scrape_slug == "world-cup"


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_manual_ticket_settlement_endpoint_returns_declared_schema(monkeypatch):
    async def fake_settle_ticket(db, ticket_id, outcome, return_amount, *, user_id=None):
        assert user_id == 12
        return SimpleNamespace(
            id=77,
            bet_placement_id=None,
            ticket_id=ticket_id,
            settled_at=datetime(2026, 7, 4, 9, 30, tzinfo=timezone.utc),
            outcome=outcome,
            return_amount=return_amount,
            pnl=return_amount - 10.0,
        )

    class _FakeDb:
        async def execute(self, stmt):
            return _ScalarOneResult(SimpleNamespace(id=18, user_id=12, status="open"))

    monkeypatch.setattr(tickets_api, "settle_ticket", fake_settle_ticket)

    response = await tickets_api.settle_ticket_endpoint(
        ticket_id=18,
        outcome="won",
        return_amount=19.5,
        db=_FakeDb(),
        user=SimpleNamespace(id=12),
    )

    assert isinstance(response, SettlementResponse)
    assert response.model_dump() == {
        "id": 77,
        "bet_placement_id": None,
        "ticket_id": 18,
        "settled_at": datetime(2026, 7, 4, 9, 30, tzinfo=timezone.utc),
        "outcome": "won",
        "return_amount": 19.5,
        "pnl": 9.5,
    }


@pytest.mark.asyncio
async def test_generated_draft_cannot_be_settled_before_activation():
    class _FakeDb:
        async def execute(self, stmt):
            return _ScalarOneResult(SimpleNamespace(id=18, user_id=12, status="generated"))

    with pytest.raises(HTTPException) as exc_info:
        await tickets_api.settle_ticket_endpoint(
            ticket_id=18,
            outcome="won",
            return_amount=19.5,
            db=_FakeDb(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Only active open tickets can be settled"
