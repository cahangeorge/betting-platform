from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute, serialize_response

from app.api.v1 import live as live_api
from app.main import app
from app.services import scraper


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _MatchesResult:
    def __init__(self, matches):
        self._matches = matches

    def scalars(self):
        return self

    def all(self):
        return list(self._matches)


class _DBSequence:
    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("unexpected extra db.execute call")
        return self._results.pop(0)


async def _serialize_live_overview_response(overview):
    route = next(
        route for route in app.routes if isinstance(route, APIRoute) and route.path == "/api/v1/live/overview"
    )
    return await serialize_response(
        field=route.response_field,
        response_content=overview,
        include=None,
        exclude=None,
        by_alias=True,
        exclude_unset=False,
        exclude_defaults=False,
        exclude_none=False,
        is_coroutine=True,
    )


def _make_match(
    now: datetime,
    *,
    status: str = "live",
    odds_timestamp: datetime | None = None,
    market: str = "1x2",
):
    odds_timestamp = odds_timestamp or now
    return SimpleNamespace(
        id=101,
        external_id="live-101",
        home_team="USA",
        away_team="Canada",
        home_score=1,
        away_score=0,
        status=status,
        competition="World Cup",
        season="2026",
        match_date=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=20),
        updated_at=now - timedelta(seconds=5),
        odds=[
            SimpleNamespace(
                id=1,
                match_id=101,
                bookmaker="Book",
                market=market,
                home_odds=2.4,
                draw_odds=3.4,
                away_odds=3.8,
                timestamp=odds_timestamp,
                created_at=odds_timestamp,
            )
        ],
        stats=[],
        sources=[],
    )


def _make_prediction(now: datetime, *, created_at: datetime | None = None, home_prob: float = 0.5):
    created_at = created_at or now
    return SimpleNamespace(
        market="1x2",
        home_prob=home_prob,
        draw_prob=0.28,
        away_prob=0.22,
        created_at=created_at,
    )


def test_live_value_candidate_is_only_betslip_eligible_when_trust_signals_are_green():
    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    match = _make_match(now, odds_timestamp=now - timedelta(seconds=10))
    prediction = _make_prediction(now, created_at=now - timedelta(seconds=8), home_prob=0.52)

    [candidate] = live_api._build_live_value_candidates(
        match=match,
        predictions=[prediction],
        now=now,
        min_edge=0,
        bridge_ready=True,
    )

    assert candidate.source_ok is True
    assert candidate.model_drift_flag is False
    assert candidate.is_betslip_eligible is True
    assert candidate.block_reasons == []
    assert candidate.data_age_seconds == 10
    assert candidate.confidence_band == "high"


def test_live_match_trust_requires_live_1x2_market_not_any_recent_odds():
    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    match = _make_match(now, odds_timestamp=now - timedelta(seconds=5), market="btts")

    live_match, _last_update = live_api._build_match_payload(
        match,
        now,
        bridge_ready=True,
        prediction_candidates=[_make_prediction(now, home_prob=0.52)],
        min_edge=0,
    )

    assert live_match.source_ok is False
    assert live_match.has_live_1x2_odds is False
    assert live_match.odds_freshness_seconds is None
    assert live_match.live_value_candidates == []


def test_live_matchwinner_alias_counts_as_live_1x2_for_api_and_broadcasts():
    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    match = _make_match(now, odds_timestamp=now - timedelta(seconds=5), market="matchwinner")

    live_match, _last_update = live_api._build_match_payload(match, now, bridge_ready=True)

    assert live_match.source_ok is True
    assert live_match.has_live_1x2_odds is True
    assert live_match.odds_freshness_seconds == 5
    assert scraper._is_live_relevant_market("matchwinner") is True


def test_live_value_candidate_exposes_bridge_and_freshness_block_reasons():
    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    match = _make_match(now, odds_timestamp=now - timedelta(seconds=45))
    prediction = _make_prediction(now, created_at=now - timedelta(minutes=7), home_prob=0.52)

    [candidate] = live_api._build_live_value_candidates(
        match=match,
        predictions=[prediction],
        now=now,
        min_edge=0,
        bridge_ready=False,
    )

    assert candidate.source_ok is False
    assert candidate.model_drift_flag is True
    assert candidate.is_betslip_eligible is False
    assert set(candidate.block_reasons) == {"bridge_not_ready", "data_stale", "model_drift"}
    assert candidate.data_age_seconds == 420
    assert candidate.confidence_band == "medium"


@pytest.mark.asyncio
async def test_live_overview_reports_cache_demo_state_when_bridge_is_not_ready(monkeypatch):
    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    match = _make_match(now, odds_timestamp=now - timedelta(seconds=12))
    db = _DBSequence(_MatchesResult([match]), _ScalarResult(2))

    monkeypatch.setattr(live_api, "_safe_now", lambda: now)
    monkeypatch.setattr(live_api, "_is_bridge_ready", lambda: (False, ["missing_bridge_binary"]))

    overview = await live_api.live_overview(
        status="live",
        league=None,
        max_matches=10,
        min_live_value_edge=0,
        include_live_value=False,
        db=db,
        user=SimpleNamespace(id=7),
    )

    assert overview.source == "cache"
    assert overview.is_demo is True
    assert overview.jobs_active == 2
    assert overview.is_data_stale is False
    assert overview.data_age_seconds == 5
    assert len(overview.matches) == 1
    assert overview.matches[0].source_ok is False
    assert overview.matches[0].is_live_data is True
    assert overview.matches[0].has_live_1x2_odds is True


@pytest.mark.asyncio
async def test_live_overview_http_serialization_keeps_live_contract_fields(monkeypatch):
    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    match = _make_match(now, odds_timestamp=now - timedelta(seconds=12))
    prediction = _make_prediction(now, created_at=now - timedelta(seconds=8), home_prob=0.52)
    db = _DBSequence(_MatchesResult([match]), _ScalarResult(2))

    monkeypatch.setattr(live_api, "_safe_now", lambda: now)
    monkeypatch.setattr(live_api, "_is_bridge_ready", lambda: (True, []))

    async def _prediction_map(**_kwargs):
        return {101: [prediction]}

    monkeypatch.setattr(live_api, "_load_live_prediction_map", _prediction_map)

    overview = await live_api.live_overview(
        status="live",
        league=None,
        max_matches=10,
        min_live_value_edge=0,
        include_live_value=True,
        db=db,
        user=SimpleNamespace(id=7),
    )

    payload = await _serialize_live_overview_response(overview)

    [live_match] = payload["matches"]
    assert live_match["source_ok"] is True
    assert live_match["odds_freshness_seconds"] == 12
    assert live_match["has_live_1x2_odds"] is True

    [candidate] = live_match["live_value_candidates"]
    assert candidate["source_ok"] is True
    assert candidate["odds_freshness_seconds"] == 12
    assert candidate["is_betslip_eligible"] is True


@pytest.mark.asyncio
async def test_live_heartbeat_surfaces_bridge_issues_and_latest_success(monkeypatch):
    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    last_success = now - timedelta(minutes=3)
    db = _DBSequence(_ScalarResult(1), _ScalarResult(last_success))

    monkeypatch.setattr(live_api, "_safe_now", lambda: now)
    monkeypatch.setattr(live_api, "_is_bridge_ready", lambda: (False, ["missing_bridge_binary"]))

    heartbeat = await live_api.live_heartbeat(db=db, _user=SimpleNamespace(id=7))

    assert heartbeat.schema_version == "live-v1"
    assert heartbeat.jobs_active == 1
    assert heartbeat.bridge_ready is False
    assert heartbeat.bridge_issues == ["missing_bridge_binary"]
    assert heartbeat.source == "cache"
    assert heartbeat.timestamp == now.isoformat()
    assert heartbeat.last_success == last_success.isoformat()
