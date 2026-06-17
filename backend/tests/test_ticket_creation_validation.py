import pytest

from app.services.ticket_engine import create_ticket


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
