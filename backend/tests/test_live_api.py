from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.api.v1 import live as live_api
from app.database import get_db
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


class _CapturingDB:
    def __init__(self, result):
        self.result = result
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return self.result


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


@pytest.mark.asyncio
async def test_live_prediction_map_selects_latest_completed_run_per_match():
    predictions = [SimpleNamespace(match_id=101), SimpleNamespace(match_id=102)]
    db = _CapturingDB(_MatchesResult(predictions))

    mapped = await live_api._load_live_prediction_map(
        db,
        match_ids=[101, 102],
        user=SimpleNamespace(id=7),
    )

    sql = str(db.statement)
    assert "row_number() OVER" in sql
    assert "PARTITION BY" in sql
    assert "prediction_runs.user_id" in sql
    assert "prediction_runs.status" in sql
    assert mapped == {101: [predictions[0]], 102: [predictions[1]]}


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

    async def override_db():
        yield db

    async def override_user():
        return SimpleNamespace(id=7)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/api/v1/live/overview",
                params={
                    "status": "live",
                    "max_matches": 10,
                    "min_live_value_edge": 0,
                    "include_live_value": "true",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200, response.text
    payload = response.json()
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
