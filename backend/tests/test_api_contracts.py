from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.deps import get_current_user
from app.api.v1 import dashboard as dashboard_api
from app.api.v1 import data as data_api
from app.api.v1 import matches as matches_api
from app.api.v1 import predictions as predictions_api
from app.api.v1 import tickets as tickets_api
from app.api.v1.catalog import CATALOG
from app.database import get_db
from app.main import app
from app.schemas.data import ScrapeJobCreateRequest, WorldCupPipelineRequest
from app.schemas.match import MatchResponse
from app.schemas.ticket import SettlementResponse, TicketCreateRequest
from app.services.auth import hash_password, verify_password


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


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


def _auth_test_client(fake_db: _FakeAuthDb) -> TestClient:
    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    return client


def test_signup_returns_tokens_and_sets_auth_cookies():
    client = _auth_test_client(_FakeAuthDb())

    try:
        response = client.post(
            "/api/v1/auth/signup",
            json={"email": "  NewUser@Example.com  ", "password": "password123", "name": "New User"},
        )
    finally:
        app.dependency_overrides.clear()
        client.close()

    assert response.status_code == 201
    assert response.json()["access_token"]
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "refresh_token=" in set_cookie


def test_login_normalizes_email_and_sets_auth_cookies():
    fake_user = SimpleNamespace(
        id=42,
        email="test@example.com",
        password_hash=hash_password("password123"),
    )
    client = _auth_test_client(_FakeAuthDb(existing_user=fake_user))

    try:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "  TEST@EXAMPLE.COM  ", "password": "password123"},
        )
    finally:
        app.dependency_overrides.clear()
        client.close()

    assert response.status_code == 200
    assert response.json()["access_token"]
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "refresh_token=" in set_cookie


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
    async def fake_create_ticket(**kwargs):
        raise ValueError("Insufficient bankroll balance")

    monkeypatch.setattr(tickets_api, "create_ticket", fake_create_ticket)

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


@pytest.mark.asyncio
async def test_ticket_creation_maps_domain_permission_errors(monkeypatch):
    async def fake_create_ticket(**kwargs):
        raise PermissionError("Bankroll 5 does not belong to the current user")

    monkeypatch.setattr(tickets_api, "create_ticket", fake_create_ticket)

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
async def test_scrape_execute_maps_lookup_errors_to_404(monkeypatch):
    async def fake_execute_scrape_job(db, job_id):
        raise LookupError(f"ScrapeJob {job_id} not found")

    monkeypatch.setattr(data_api, "execute_scrape_job", fake_execute_scrape_job)

    with pytest.raises(HTTPException) as exc_info:
        await data_api.run_scrape_job(
            job_id=999,
            db=object(),
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
        assert params == {"sport": "football"}
        return fake_job

    monkeypatch.setattr(data_api, "create_scrape_job", fake_create_scrape_job)

    result = await data_api.start_scrape_job(
        body=ScrapeJobCreateRequest(job_type="oddsportal", league="Premier League", params={"sport": "football"}),
        db=object(),
        user=SimpleNamespace(id=12),
    )

    assert result is fake_job


@pytest.mark.asyncio
async def test_scrape_background_execute_queues_task():
    fake_job = SimpleNamespace(id=45, job_type="scrape_odds", status="pending")

    class _DB:
        async def get(self, model, job_id):
            assert job_id == fake_job.id
            return fake_job

    queued = []

    class _BackgroundTasks:
        def add_task(self, func, *args):
            queued.append((func, args))

    result = await data_api.run_scrape_job_background(
        job_id=fake_job.id,
        background_tasks=_BackgroundTasks(),
        db=_DB(),
        user=SimpleNamespace(id=12),
    )

    assert result is fake_job
    assert queued == [(data_api._execute_scrape_job_background, (fake_job.id,))]


@pytest.mark.asyncio
async def test_scrape_background_execute_returns_404_when_missing():
    class _DB:
        async def get(self, model, job_id):
            return None

    class _BackgroundTasks:
        def add_task(self, *_args):
            raise AssertionError("background task should not be queued")

    with pytest.raises(HTTPException) as exc_info:
        await data_api.run_scrape_job_background(
            job_id=999,
            background_tasks=_BackgroundTasks(),
            db=_DB(),
            user=SimpleNamespace(id=12),
        )

    assert exc_info.value.status_code == 404


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
    async def fake_settle_ticket(db, ticket_id, outcome, return_amount):
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
            return _ScalarOneResult(SimpleNamespace(id=18, user_id=12))

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
