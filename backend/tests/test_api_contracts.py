from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.deps import get_current_user
from app.api.v1 import data as data_api
from app.api.v1 import matches as matches_api
from app.api.v1 import tickets as tickets_api
from app.api.v1.catalog import CATALOG
from app.schemas.match import MatchResponse
from app.schemas.data import ScrapeJobCreateRequest
from app.schemas.ticket import TicketCreateRequest


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
    leagues = {
        league.id: league
        for country in CATALOG
        for league in country.leagues
    }

    assert leagues["premier_league"].scrape_slug == "england-premier-league"
    assert leagues["world_cup"].name == "World Cup"
    assert leagues["world_cup"].scrape_slug == "world-cup"
