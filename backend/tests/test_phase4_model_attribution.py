from types import SimpleNamespace

import pytest

from app.api.v1.analytics import get_pnl_by_model
from app.models.ticket import TicketLeg
from app.services.ensemble import compute_brier_weights
from app.services.ticket_engine import create_ticket


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeAsyncSession:
    def __init__(self, rows):
        self.rows = rows
        self.last_stmt = None

    async def execute(self, stmt):
        self.last_stmt = stmt
        return _FakeResult(self.rows)


class _FakeTicketSession:
    def __init__(self, bankroll=None):
        self.bankroll = bankroll
        self.added = []
        self._ticket_id = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None and obj.__class__.__name__ == "Ticket":
                self._ticket_id += 1
                obj.id = self._ticket_id

    async def get(self, model, pk):
        if self.bankroll is not None and pk == getattr(self.bankroll, "id", None):
            return self.bankroll
        return None


@pytest.mark.asyncio
async def test_compute_brier_weights_uses_prediction_row_model_type():
    perfect_rows = [
        (
            SimpleNamespace(
                match_id=index,
                model_type="PoissonGoalsModel",
                home_prob=1.0,
                draw_prob=0.0,
                away_prob=0.0,
            ),
            2,
            0,
        )
        for index in range(1, 13)
    ]
    weak_rows = [
        (
            SimpleNamespace(
                match_id=index,
                model_type="DixonColesGoalModel",
                home_prob=0.34,
                draw_prob=0.33,
                away_prob=0.33,
            ),
            2,
            0,
        )
        for index in range(101, 113)
    ]
    db = _FakeAsyncSession(perfect_rows + weak_rows)

    weights = await compute_brier_weights(
        db,
        ["PoissonGoalsModel", "DixonColesGoalModel"],
        "Premier League",
    )

    assert pytest.approx(sum(weights.values()), rel=1e-6) == 1.0
    assert weights["PoissonGoalsModel"] > weights["DixonColesGoalModel"]


@pytest.mark.asyncio
async def test_pnl_by_model_query_uses_ticket_leg_prediction_links():
    db = _FakeAsyncSession(
        [
            SimpleNamespace(
                model_type="PoissonGoalsModel",
                total_pnl=12.5,
                bets_count=2,
                wins=1,
            )
        ]
    )

    rows = await get_pnl_by_model(db=db, user=SimpleNamespace(id=7))

    compiled = str(db.last_stmt)
    assert "model_predictions.id = ticket_legs.model_prediction_id" in compiled
    assert "model_predictions.match_id = ticket_legs.match_id" not in compiled
    assert rows[0].model_type == "PoissonGoalsModel"


@pytest.mark.asyncio
async def test_create_ticket_keeps_model_prediction_link_on_leg():
    bankroll = SimpleNamespace(id=4, user_id=9, balance=100.0)
    db = _FakeTicketSession(bankroll=bankroll)

    await create_ticket(
        db=db,
        user_id=9,
        ticket_type="single",
        stake=10.0,
        bankroll_id=4,
        legs_data=[
            {
                "match_id": 11,
                "market": "1x2",
                "selection": "home",
                "odds": 1.95,
                "model_prediction_id": 42,
            }
        ],
    )

    leg = next(obj for obj in db.added if isinstance(obj, TicketLeg))
    assert leg.model_prediction_id == 42
