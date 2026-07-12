from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import ticket_engine
from app.services.ticket_engine import (
    _build_ticket_candidate,
    _recalculate_ticket_totals,
    create_ticket,
    generate_tickets,
    settle_ticket,
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


class _FakeExecuteResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        rows = self._rows

        class _Scalars:
            def all(self_nonlocal):
                return rows

        return _Scalars()


class _FakeGenerateSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.statements = []
        self.added = []
        self._batch_id = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "TicketBatch" and getattr(obj, "id", None) is None:
                self._batch_id += 1
                obj.id = self._batch_id

    async def execute(self, stmt):
        self.statements.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        return self.responses.pop(0)


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


def _prediction(*, prediction_id: int, run_id: int, match_id: int, expected_value: float = 0.1):
    return type(
        "Prediction",
        (),
        {
            "id": prediction_id,
            "run_id": run_id,
            "match_id": match_id,
            "market": "1x2",
            "home_prob": 0.62,
            "draw_prob": 0.23,
            "away_prob": 0.15,
            "home_odds": 1.95,
            "draw_odds": 3.4,
            "away_odds": 4.8,
            "expected_value": expected_value,
            "quality_report": {"model": {"pick": "home"}},
            "created_at": None,
        },
    )()


@pytest.mark.asyncio
async def test_generate_tickets_uses_latest_eligible_prediction_run_by_default(monkeypatch):
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=22),
            _FakeExecuteResult(rows=[_prediction(prediction_id=202, run_id=22, match_id=11)]),
        ]
    )
    ticket_calls = []

    async def fake_create_ticket(**kwargs):
        ticket_calls.append(kwargs)
        return SimpleNamespace(id=len(ticket_calls))

    monkeypatch.setattr(ticket_engine, "create_ticket", fake_create_ticket)

    batch, tickets = await generate_tickets(
        db=db,
        user_id=7,
        bankroll_id=None,
        ticket_count=1,
        difficulty="safe",
        market_types=["1x2"],
        min_odds=1.5,
        max_odds=2.5,
        stake=10.0,
    )

    assert batch.id == 1
    assert [ticket.id for ticket in tickets] == [1]
    assert ticket_calls[0]["legs_data"][0]["model_prediction_id"] == 202
    assert "FROM prediction_runs" in db.statements[0]
    assert "ORDER BY prediction_runs.completed_at DESC NULLS LAST" in db.statements[0]
    assert "model_predictions.run_id = 22" in db.statements[1]


@pytest.mark.asyncio
async def test_generate_tickets_can_scope_to_explicit_prediction_run(monkeypatch):
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=11),
            _FakeExecuteResult(rows=[_prediction(prediction_id=101, run_id=11, match_id=10)]),
        ]
    )
    ticket_calls = []

    async def fake_create_ticket(**kwargs):
        ticket_calls.append(kwargs)
        return SimpleNamespace(id=len(ticket_calls))

    monkeypatch.setattr(ticket_engine, "create_ticket", fake_create_ticket)

    await generate_tickets(
        db=db,
        user_id=7,
        bankroll_id=None,
        ticket_count=1,
        difficulty="safe",
        market_types=["1x2"],
        min_odds=1.5,
        max_odds=2.5,
        stake=10.0,
        run_id=11,
    )

    assert ticket_calls[0]["legs_data"][0]["model_prediction_id"] == 101
    assert "prediction_runs.id = 11" in db.statements[0]
    assert "prediction_runs.status = 'completed'" in db.statements[0]
    assert "ORDER BY prediction_runs.completed_at" not in db.statements[0]
    assert "model_predictions.run_id = 11" in db.statements[1]


@pytest.mark.asyncio
async def test_generate_tickets_rejects_unknown_or_ineligible_explicit_prediction_run():
    db = _FakeGenerateSession([_FakeExecuteResult(scalar=None)])

    with pytest.raises(ValueError, match="Prediction run 44 not found or not eligible for ticket generation"):
        await generate_tickets(
            db=db,
            user_id=7,
            bankroll_id=None,
            ticket_count=1,
            difficulty="safe",
            market_types=["1x2"],
            min_odds=1.5,
            max_odds=2.5,
            stake=10.0,
            run_id=44,
        )


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _SettlementSession:
    def __init__(self, ticket, bankroll=None):
        self.ticket = ticket
        self.bankroll = bankroll
        self.added = []
        self._settlement_id = 0

    async def execute(self, stmt):
        return _ScalarResult(self.ticket)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "Settlement" and getattr(obj, "id", None) is None:
                self._settlement_id += 1
                obj.id = self._settlement_id
                if getattr(obj, "settled_at", None) is None:
                    obj.settled_at = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)

    async def refresh(self, obj):
        if getattr(obj, "settled_at", None) is None:
            obj.settled_at = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)

    async def get(self, model, pk):
        if self.bankroll is not None and pk == getattr(self.bankroll, "id", None):
            return self.bankroll
        return None


@pytest.mark.asyncio
async def test_settle_ticket_returns_persisted_settlement_contract():
    ticket = SimpleNamespace(
        id=12,
        stake=10.0,
        status="open",
        bankroll_id=None,
        legs=[SimpleNamespace(status="pending"), SimpleNamespace(status="pending")],
    )
    db = _SettlementSession(ticket=ticket)

    settlement = await settle_ticket(db, ticket_id=12, outcome="won", return_amount=19.5)

    assert settlement.id == 1
    assert settlement.ticket_id == 12
    assert settlement.outcome == "won"
    assert settlement.return_amount == 19.5
    assert settlement.pnl == pytest.approx(9.5)
    assert settlement.settled_at == datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    assert ticket.status == "won"
    assert [leg.status for leg in ticket.legs] == ["won", "won"]
