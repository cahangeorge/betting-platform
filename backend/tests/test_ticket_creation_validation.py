import pytest

from app.services.ticket_engine import (
    _build_ticket_candidate,
    _recalculate_ticket_totals,
    create_ticket,
)


class _FakeSession:
    def __init__(self, bankroll=None):
        self.bankroll = bankroll
        self.added = []
        self._ticket_id = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "Ticket" and getattr(obj, "id", None) is None:
                self._ticket_id += 1
                obj.id = self._ticket_id

    async def get(self, model, pk):
        if self.bankroll is not None and pk == getattr(self.bankroll, "id", None):
            return self.bankroll
        return None


@pytest.mark.asyncio
async def test_create_ticket_rejects_missing_bankroll():
    db = _FakeSession(bankroll=None)

    with pytest.raises(ValueError, match="Bankroll 99 not found"):
        await create_ticket(
            db=db,
            user_id=8,
            ticket_type="single",
            stake=10.0,
            bankroll_id=99,
            legs_data=[{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}],
        )


@pytest.mark.asyncio
async def test_create_ticket_rejects_foreign_bankroll():
    bankroll = type("Bankroll", (), {"id": 5, "user_id": 3, "balance": 120.0})()
    db = _FakeSession(bankroll=bankroll)

    with pytest.raises(PermissionError, match="does not belong to the current user"):
        await create_ticket(
            db=db,
            user_id=8,
            ticket_type="single",
            stake=10.0,
            bankroll_id=5,
            legs_data=[{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}],
        )


@pytest.mark.asyncio
async def test_create_ticket_rejects_stake_above_bankroll_balance():
    bankroll = type("Bankroll", (), {"id": 5, "user_id": 8, "balance": 9.5})()
    db = _FakeSession(bankroll=bankroll)

    with pytest.raises(ValueError, match="Insufficient bankroll balance"):
        await create_ticket(
            db=db,
            user_id=8,
            ticket_type="single",
            stake=10.0,
            bankroll_id=5,
            legs_data=[{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}],
        )


def test_build_ticket_candidate_uses_quality_pick_odds_and_probability():
    prediction = type(
        "Prediction",
        (),
        {
            "id": 42,
            "match_id": 10,
            "market": "1x2",
            "home_prob": 0.62,
            "draw_prob": 0.23,
            "away_prob": 0.15,
            "home_odds": 1.91,
            "draw_odds": 3.4,
            "away_odds": 4.8,
            "expected_value": 0.08,
            "quality_report": {
                "model": {"pick": "home"},
                "market": {"odds": {"home": {"odds": 1.95, "bookmaker": "Pinnacle"}}},
                "reliability": {"label": "reliable"},
            },
        },
    )()

    candidate = _build_ticket_candidate(prediction, min_odds=1.5, max_odds=2.5)

    assert candidate == {
        "model_prediction_id": 42,
        "match_id": 10,
        "market": "1x2",
        "selection": "home",
        "odds": 1.95,
        "probability": 0.62,
        "bookmaker": "Pinnacle",
        "score": pytest.approx(0.08),
    }


def test_build_ticket_candidate_returns_none_when_odds_outside_requested_interval():
    prediction = type(
        "Prediction",
        (),
        {
            "id": 43,
            "match_id": 11,
            "market": "btts",
            "home_prob": 0.55,
            "draw_prob": None,
            "away_prob": 0.45,
            "home_odds": 1.3,
            "draw_odds": None,
            "away_odds": 2.2,
            "expected_value": 0.02,
            "quality_report": {"model": {"pick": "yes"}},
        },
    )()

    assert _build_ticket_candidate(prediction, min_odds=1.5, max_odds=3.0) is None


def test_recalculate_ticket_totals_after_leg_swap():
    ticket = type(
        "Ticket",
        (),
        {
            "stake": 10.0,
            "legs": [
                type("Leg", (), {"odds": 2.0})(),
                type("Leg", (), {"odds": 1.5})(),
            ],
            "total_odds": 0,
            "potential_return": 0,
        },
    )()

    total_odds = _recalculate_ticket_totals(ticket)

    assert total_odds == 3.0
    assert ticket.total_odds == 3.0
    assert ticket.potential_return == 30.0
