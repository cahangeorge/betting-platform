from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1 import predictions as predictions_api


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DB:
    def __init__(self, value):
        self.value = value
        self.execute_count = 0

    async def execute(self, _stmt):
        self.execute_count += 1
        return _ScalarResult(self.value)


def _freeze_time(monkeypatch: pytest.MonkeyPatch, frozen_now: datetime) -> None:
    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return frozen_now
            return frozen_now.astimezone(tz)

    monkeypatch.setattr(predictions_api, "datetime", _FrozenDateTime)


def _completed_run(
    *,
    match_date: datetime,
    prediction_created_at: datetime,
    odds_timestamp: datetime | None,
    reliability_label: str = "trusted",
    is_ticket_eligible: bool = True,
):
    match = SimpleNamespace(
        id=42,
        competition="World Cup",
        home_team="USA",
        away_team="Canada",
        match_date=match_date,
        status="scheduled",
        odds=[
            SimpleNamespace(
                market="1x2",
                home_odds=2.2,
                draw_odds=3.4,
                away_odds=4.5,
                bookmaker="Book",
                timestamp=odds_timestamp,
                created_at=odds_timestamp,
            )
        ],
    )
    return SimpleNamespace(
        model_type="PoissonGoalsModel",
        model_predictions=[
            SimpleNamespace(
                id=7,
                match=match,
                market="1x2",
                home_prob=0.6,
                draw_prob=0.25,
                away_prob=0.15,
                created_at=prediction_created_at,
                quality_report={
                    "reliability": {
                        "is_ticket_eligible": is_ticket_eligible,
                        "label": reliability_label,
                        "block_reasons": [] if is_ticket_eligible else ["edge_below_ticket_threshold"],
                    }
                },
            )
        ],
    )


@pytest.mark.asyncio
async def test_value_bets_endpoint_returns_stable_empty_feed_when_no_completed_run():
    db = _DB(None)

    feed = await predictions_api.list_value_bets(
        min_edge=0,
        max_results=10,
        include_unreliable=False,
        db=db,
        user=SimpleNamespace(id=9),
    )

    assert db.execute_count == 1
    assert feed.items == []
    assert feed.source == "prediction"
    assert feed.is_demo is False
    assert feed.generated_at


@pytest.mark.asyncio
async def test_value_bets_endpoint_surfaces_fresh_trust_metadata_for_safe_betslip(monkeypatch: pytest.MonkeyPatch):
    now = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    _freeze_time(monkeypatch, now)
    db = _DB(
        _completed_run(
            match_date=datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc),
            prediction_created_at=datetime(2026, 7, 3, 9, 58, tzinfo=timezone.utc),
            odds_timestamp=datetime(2026, 7, 3, 9, 59, tzinfo=timezone.utc),
        )
    )

    feed = await predictions_api.list_value_bets(
        min_edge=0,
        max_results=10,
        include_unreliable=False,
        db=db,
        user=SimpleNamespace(id=9),
    )

    assert db.execute_count == 1
    assert feed.source == "prediction"
    assert feed.is_demo is False
    assert feed.generated_at
    assert len(feed.items) == 1
    [item] = feed.items
    assert item.match_id == 42
    assert item.home_team == "USA"
    assert item.away_team == "Canada"
    assert item.market == "1x2"
    assert item.selection == "home"
    assert item.source == "odds:Book"
    assert item.reliability == "trusted"
    assert item.prediction_age_seconds == 120
    assert item.selection_age_seconds == 120
    assert item.odds_freshness_seconds == 60
    assert item.data_age_seconds == 120
    assert item.source_ok is True
    assert item.model_drift_flag is False
    assert item.is_betslip_eligible is True
    assert item.block_reasons == []


@pytest.mark.asyncio
async def test_value_bets_endpoint_marks_stale_or_untrusted_items_as_betslip_ineligible(
    monkeypatch: pytest.MonkeyPatch,
):
    now = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    _freeze_time(monkeypatch, now)
    db = _DB(
        _completed_run(
            match_date=datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc),
            prediction_created_at=datetime(2026, 7, 3, 7, 0, tzinfo=timezone.utc),
            odds_timestamp=datetime(2026, 7, 3, 9, 58, tzinfo=timezone.utc),
            reliability_label="unreliable",
            is_ticket_eligible=False,
        )
    )

    feed = await predictions_api.list_value_bets(
        min_edge=0,
        max_results=10,
        include_unreliable=True,
        db=db,
        user=SimpleNamespace(id=9),
    )

    assert len(feed.items) == 1
    [item] = feed.items
    assert item.reliability == "unreliable"
    assert item.source_ok is True
    assert item.prediction_age_seconds == 10800
    assert item.odds_freshness_seconds == 120
    assert item.data_age_seconds == 10800
    assert item.model_drift_flag is True
    assert item.is_betslip_eligible is False
    assert set(item.block_reasons) >= {"prediction_untrusted", "data_stale", "model_drift"}
