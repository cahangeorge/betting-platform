from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.adapters.betfair_readonly import BetfairReadOnlyAdapter
from app.adapters.flumine_paper import FluminePaperAdapter
from app.config import Settings
from app.models.trading import ExecutionIntent, ExecutionOrder, TradingAccount
from app.services.trading_execution import create_execution_intent, execute_paper_intent


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, *, account, ticket, odds, existing=None):
        self.account = account
        self.responses = [existing, ticket, odds]
        self.added = []
        self.next_id = 1

    async def execute(self, _statement):
        return _ScalarResult(self.responses.pop(0))

    async def get(self, model, object_id, **_kwargs):
        if model is TradingAccount and object_id == self.account.id:
            return self.account
        return None

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = self.next_id
                self.next_id += 1


def _paper_domain():
    user_id = 7
    account = TradingAccount(
        id=4,
        user_id=user_id,
        name="Paper",
        provider="paper-local",
        mode="paper",
        currency="EUR",
        balance=100,
        enabled=True,
    )
    match = SimpleNamespace(
        id=11,
        status="scheduled",
        match_date=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    leg = SimpleNamespace(market="1x2", selection="home", match=match)
    ticket = SimpleNamespace(id=9, user_id=user_id, ticket_type="single", status="open", stake=10.0, legs=[leg])
    odds = SimpleNamespace(id=15, home_odds=2.25, draw_odds=3.1, away_odds=3.4)
    return user_id, account, ticket, odds


@pytest.mark.asyncio
async def test_paper_execution_uses_persisted_odds_and_has_no_external_order():
    user_id, account, ticket, odds = _paper_domain()
    db = _FakeDb(account=account, ticket=ticket, odds=odds)
    intent, created = await create_execution_intent(
        db,
        user_id=user_id,
        trading_account_id=account.id,
        ticket_id=ticket.id,
        idempotency_key="ticket-9-attempt-1",
        side="BACK",
        order_type="LIMIT",
        settings=Settings(trading_enabled=True, trading_paper_enabled=True),
    )

    assert created is True
    assert intent.limit_price == 2.25
    assert intent.odds_entry_id == odds.id

    db.responses = [intent]
    await execute_paper_intent(db, intent.id)

    orders = [value for value in db.added if isinstance(value, ExecutionOrder)]
    assert intent.status == "filled"
    assert orders[0].provider == "flumine-paper-local"
    assert orders[0].external_order_id is None
    assert orders[0].average_price == 2.25
    assert account.balance == 90.0


@pytest.mark.asyncio
async def test_idempotency_returns_existing_intent_without_new_work():
    user_id, account, ticket, odds = _paper_domain()
    existing = ExecutionIntent(
        id=33,
        user_id=user_id,
        trading_account_id=account.id,
        ticket_id=ticket.id,
        odds_entry_id=odds.id,
        idempotency_key="stable-key",
        market="1x2",
        selection="home",
        stake=10,
        limit_price=2.25,
    )
    db = _FakeDb(account=account, ticket=ticket, odds=odds, existing=existing)

    returned, created = await create_execution_intent(
        db,
        user_id=user_id,
        trading_account_id=account.id,
        ticket_id=ticket.id,
        idempotency_key="stable-key",
        side="BACK",
        order_type="LIMIT",
        settings=Settings(),
    )

    assert created is False
    assert returned is existing
    assert db.added == []


@pytest.mark.asyncio
async def test_live_account_and_lay_order_are_rejected_even_if_live_flag_is_true():
    user_id, account, ticket, odds = _paper_domain()
    account.mode = "live"
    db = _FakeDb(account=account, ticket=ticket, odds=odds)
    with pytest.raises(PermissionError, match="paper-local"):
        await create_execution_intent(
            db,
            user_id=user_id,
            trading_account_id=account.id,
            ticket_id=ticket.id,
            idempotency_key="live-impossible",
            side="BACK",
            order_type="LIMIT",
            settings=Settings(trading_live_enabled=True),
        )

    account.mode = "paper"
    db = _FakeDb(account=account, ticket=ticket, odds=odds)
    with pytest.raises(ValueError, match="BACK LIMIT"):
        await create_execution_intent(
            db,
            user_id=user_id,
            trading_account_id=account.id,
            ticket_id=ticket.id,
            idempotency_key="lay-impossible",
            side="LAY",
            order_type="LIMIT",
            settings=Settings(),
        )


@pytest.mark.asyncio
async def test_betfair_boundary_is_read_only_and_not_configured():
    adapter = BetfairReadOnlyAdapter(Settings(trading_betfair_read_only_enabled=False))
    health = await adapter.health()

    assert health.status == "not_configured"
    assert not hasattr(adapter, "place_order")


def test_local_flumine_limit_order_contract_is_used_without_execution_client():
    instruction = FluminePaperAdapter(Settings()).build_back_limit(price=2.25, size=10)

    assert instruction.framework == "flumine"
    assert instruction.order_type == "Limit"
    assert instruction.side == "BACK"
    assert instruction.price == 2.25
    assert instruction.size == 10
    assert not hasattr(FluminePaperAdapter, "place_order")
