from types import SimpleNamespace

import pytest

from app.services.result_settlement import (
    evaluate_model_prediction,
    evaluate_ticket_leg,
    resolve_finished_ticket,
    settle_due_tickets,
)


def _match(home_score, away_score, status="finished"):
    return SimpleNamespace(home_score=home_score, away_score=away_score, status=status)


def _leg(selection, market="1x2", odds=2.0, match=None, status="pending"):
    return SimpleNamespace(selection=selection, market=market, odds=odds, match=match, status=status)


def test_evaluate_ticket_leg_for_1x2_outcomes():
    assert evaluate_ticket_leg(_leg("home", match=_match(2, 1))) == "won"
    assert evaluate_ticket_leg(_leg("draw", match=_match(2, 2))) == "won"
    assert evaluate_ticket_leg(_leg("away", match=_match(2, 1))) == "lost"


def test_evaluate_ticket_leg_for_btts_and_over_under():
    assert evaluate_ticket_leg(_leg("yes", market="btts", match=_match(2, 1))) == "won"
    assert evaluate_ticket_leg(_leg("no", market="both_score", match=_match(0, 1))) == "won"
    assert evaluate_ticket_leg(_leg("over", market="over_under_2_5", match=_match(2, 1))) == "won"
    assert evaluate_ticket_leg(_leg("under", market="ou_2_5", match=_match(2, 1))) == "lost"


def test_finished_ticket_loses_when_any_leg_loses():
    ticket = SimpleNamespace(
        stake=10.0,
        total_odds=6.0,
        potential_return=60.0,
        legs=[
            _leg("home", odds=2.0, match=_match(1, 0)),
            _leg("away", odds=3.0, match=_match(1, 0)),
        ],
    )

    outcome = resolve_finished_ticket(ticket)

    assert outcome.status == "lost"
    assert outcome.return_amount == 0.0
    assert [leg.status for leg in ticket.legs] == ["won", "lost"]


def test_ticket_stays_open_until_all_supported_legs_are_finished():
    ticket = SimpleNamespace(
        stake=10.0,
        total_odds=6.0,
        potential_return=60.0,
        legs=[
            _leg("home", odds=2.0, match=_match(1, 0)),
            _leg("away", odds=3.0, match=_match(None, None, status="scheduled")),
        ],
    )

    outcome = resolve_finished_ticket(ticket)

    assert outcome.status == "open"
    assert outcome.return_amount is None
    assert [leg.status for leg in ticket.legs] == ["won", "pending"]


def test_winning_ticket_return_ignores_void_legs():
    ticket = SimpleNamespace(
        stake=10.0,
        total_odds=6.0,
        potential_return=60.0,
        legs=[
            _leg("home", odds=2.0, match=_match(1, 0)),
            _leg("draw", market="unsupported_market", odds=3.0, match=_match(1, 1)),
        ],
    )

    outcome = resolve_finished_ticket(ticket, unsupported_policy="void")

    assert outcome.status == "won"
    assert outcome.return_amount == 20.0
    assert [leg.status for leg in ticket.legs] == ["won", "void"]


def test_evaluate_model_prediction_scores_highest_probability_pick():
    prediction = SimpleNamespace(
        id=7,
        market="1x2",
        home_prob=0.55,
        draw_prob=0.25,
        away_prob=0.20,
        match=_match(2, 0),
    )

    evaluation = evaluate_model_prediction(prediction)

    assert evaluation.status == "won"
    assert evaluation.predicted_selection == "home"
    assert evaluation.actual_selection == "home"


def test_evaluate_model_prediction_handles_pending_and_over_under():
    pending = SimpleNamespace(
        id=8,
        market="1x2",
        home_prob=0.55,
        draw_prob=0.25,
        away_prob=0.20,
        match=_match(None, None, status="scheduled"),
    )
    over = SimpleNamespace(
        id=9,
        market="over_under_2_5",
        home_prob=0.40,
        draw_prob=None,
        away_prob=0.60,
        match=_match(3, 1),
    )

    assert evaluate_model_prediction(pending).status == "pending"
    evaluation = evaluate_model_prediction(over)
    assert evaluation.status == "lost"
    assert evaluation.predicted_selection == "under"
    assert evaluation.actual_selection == "over"


@pytest.mark.asyncio
async def test_generated_draft_is_never_checked_mutated_or_credited_by_automatic_settlement():
    bankroll = SimpleNamespace(id=5, balance=100.0)
    leg = _leg("home", odds=2.0, match=_match(2, 0), status="pending")
    generated = SimpleNamespace(
        id=77,
        user_id=8,
        bankroll_id=5,
        status="generated",
        stake=10.0,
        legs=[leg],
    )

    class _Scalars:
        def unique(self):
            return self

        def all(self):
            # Return the draft even though a real database honors the WHERE;
            # the service-level guard must still prevent lifecycle mutation.
            return [generated]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Db:
        def __init__(self):
            self.added = []
            self.statements = []
            self.flushed = False

        async def execute(self, stmt):
            self.statements.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
            return _Result()

        async def get(self, _model, _object_id):
            raise AssertionError("Generated drafts must never reach bankroll settlement")

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            self.flushed = True

    db = _Db()
    summary = await settle_due_tickets(db, user_id=8)

    assert "tickets.status IN ('open')" in db.statements[0]
    assert summary.checked_tickets == 0
    assert summary.settled_tickets == 0
    assert generated.status == "generated"
    assert leg.status == "pending"
    assert bankroll.balance == 100.0
    assert db.added == []
