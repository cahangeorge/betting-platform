from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.adapters.betfair_readonly import BetfairReadOnlyAdapter
from app.adapters.flumine_paper import FluminePaperAdapter
from app.config import Settings
from app.models.trading import ExecutionIntent, ExecutionOrder, TradingAccount
from app.services import trading_execution
from app.services.trading_execution import create_execution_intent, execute_paper_intent


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        if self.value is None:
            return []
        return self.value if isinstance(self.value, list) else [self.value]


class _FakeDb:
    def __init__(self, *, account, ticket, odds, existing=None):
        self.account = account
        self.responses = [existing, None, ticket, [odds]]
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

    def begin_nested(self):
        class _Nested:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *_args):
                return False

        return _Nested()


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
    leg = SimpleNamespace(market="1x2", selection="home", odds=2.25, match=match)
    ticket = SimpleNamespace(id=9, user_id=user_id, ticket_type="single", status="open", stake=10.0, legs=[leg])
    odds = SimpleNamespace(
        id=15,
        odds_snapshot_id=16,
        snapshot=SimpleNamespace(
            id=16,
            observed_at=datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc),
        ),
        market="1x2",
        bookmaker="PaperBook",
        home_odds=2.25,
        draw_odds=3.1,
        away_odds=3.4,
        timestamp=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
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
    assert intent.odds_snapshot_id == odds.odds_snapshot_id

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
async def test_concurrent_ticket_execution_conflict_is_reported_without_second_intent():
    user_id, account, ticket, odds = _paper_domain()
    winner = ExecutionIntent(
        id=34,
        user_id=user_id,
        trading_account_id=account.id,
        ticket_id=ticket.id,
        odds_entry_id=odds.id,
        idempotency_key="winner-key",
        market="1x2",
        selection="home",
        stake=10,
        limit_price=2.25,
    )

    class _RacingDb(_FakeDb):
        def __init__(self):
            super().__init__(account=account, ticket=ticket, odds=odds)
            self.conflict_raised = False

        async def execute(self, statement):
            if self.conflict_raised:
                if "idempotency_key_1" in statement.compile().params:
                    return _ScalarResult(None)
                return _ScalarResult(winner)
            return await super().execute(statement)

        async def flush(self):
            pending_intent = next(
                (value for value in self.added if isinstance(value, ExecutionIntent) and value.id is None),
                None,
            )
            if pending_intent is not None:
                self.conflict_raised = True
                raise IntegrityError("INSERT INTO execution_intents", {}, RuntimeError("unique conflict"))
            await super().flush()

    db = _RacingDb()
    with pytest.raises(ValueError, match="already exists for this ticket"):
        await create_execution_intent(
            db,
            user_id=user_id,
            trading_account_id=account.id,
            ticket_id=ticket.id,
            idempotency_key="loser-key",
            side="BACK",
            order_type="LIMIT",
            settings=Settings(trading_enabled=True, trading_paper_enabled=True),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["account", "balance"])
async def test_terminal_execution_failures_complete_delivery(failure):
    user_id, account, ticket, odds = _paper_domain()
    intent = ExecutionIntent(
        id=33,
        user_id=user_id,
        trading_account_id=account.id,
        ticket_id=ticket.id,
        odds_entry_id=odds.id,
        idempotency_key=f"terminal-{failure}",
        mode="paper",
        market="1x2",
        selection="home",
        side="BACK",
        order_type="LIMIT",
        stake=110 if failure == "balance" else 10,
        limit_price=2.25,
        status="queued",
        delivery_status="publishing",
    )
    db = _FakeDb(account=account, ticket=ticket, odds=odds)
    db.responses = [intent]
    if failure == "account":
        account.enabled = False

    result = await execute_paper_intent(db, intent.id)

    assert result.status == "failed"
    assert result.delivery_status == "completed"
    assert result.last_delivery_error is None
    assert result.completed_at is not None


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


@pytest.mark.asyncio
async def test_versioned_execution_is_revalidated_before_account_debit(monkeypatch):
    user_id, account, ticket, odds = _paper_domain()
    run = SimpleNamespace(id=101, model_version_id=9)
    intent = ExecutionIntent(
        id=33,
        user_id=user_id,
        trading_account_id=account.id,
        ticket_id=ticket.id,
        odds_entry_id=odds.id,
        idempotency_key="governance-revalidation",
        mode="paper",
        market="1x2",
        selection="home",
        side="BACK",
        order_type="LIMIT",
        stake=10,
        limit_price=2.25,
        status="queued",
        model_evaluation_id=21,
    )
    db = _FakeDb(account=account, ticket=ticket, odds=odds)
    db.responses = [intent, [run]]

    async def blocked_governance(*_args, **_kwargs):
        return {
            "allowed": False,
            "mode": "manual",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runs": [{"run_id": 101, "allowed": False, "reason": "critical_monitoring_drift"}],
            "model_evaluation_ids": [21],
        }

    monkeypatch.setattr(trading_execution, "assess_prediction_runs_governance", blocked_governance)

    result = await execute_paper_intent(db, intent.id)

    assert result.status == "failed"
    assert result.error == "Paper execution is blocked by current model governance"
    assert account.balance == 100
    assert not any(isinstance(value, ExecutionOrder) for value in db.added)


@pytest.mark.asyncio
async def test_versioned_execution_intent_records_current_governance_evaluation(monkeypatch):
    user_id, account, ticket, odds = _paper_domain()
    ticket.legs[0].model_prediction_id = 42
    run = SimpleNamespace(id=101, model_version_id=9)
    db = _FakeDb(account=account, ticket=ticket, odds=odds)
    db.responses = [None, None, ticket, [run], [odds]]

    async def allowed_governance(*_args, **_kwargs):
        return {
            "allowed": True,
            "mode": "manual",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runs": [{"run_id": 101, "allowed": True, "reason": "staged_manual_paper_only"}],
            "model_evaluation_ids": [21],
        }

    monkeypatch.setattr(trading_execution, "assess_prediction_runs_governance", allowed_governance)

    intent, created = await create_execution_intent(
        db,
        user_id=user_id,
        trading_account_id=account.id,
        ticket_id=ticket.id,
        idempotency_key="versioned-ticket",
        side="BACK",
        order_type="LIMIT",
        settings=Settings(trading_enabled=True, trading_paper_enabled=True),
    )

    assert created is True
    assert intent.model_evaluation_id == 21


def test_local_flumine_limit_order_contract_is_used_without_execution_client():
    instruction = FluminePaperAdapter(Settings()).build_back_limit(price=2.25, size=10)

    assert instruction.framework == "flumine"
    assert instruction.order_type == "Limit"
    assert instruction.side == "BACK"
    assert instruction.price == 2.25
    assert instruction.size == 10
    assert not hasattr(FluminePaperAdapter, "place_order")
