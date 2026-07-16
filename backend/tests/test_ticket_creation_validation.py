from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm.attributes import set_committed_value

from app.services import ticket_engine
from app.services.portfolio_risk import PortfolioExposure, RiskContext, RiskPolicy
from app.services.staking import StakingPolicy
from app.services.ticket_engine import (
    _build_ticket_candidate,
    _recalculate_ticket_totals,
    activate_ticket_batch,
    create_manual_ticket,
    create_ticket,
    generate_tickets,
    settle_ticket,
    swap_ticket_legs,
)


def _manual_risk_policy(*, paused_until=None, accumulators_enabled=True):
    return RiskPolicy(
        version="1",
        staking=StakingPolicy(mode="flat_percent", flat_stake_percent="1", kelly_fraction=None),
        max_ticket_percent="5",
        max_open_exposure_percent="20",
        max_daily_stake_percent="100",
        max_weekly_stake_percent="100",
        max_daily_ticket_count=100,
        max_weekly_ticket_count=500,
        max_match_exposure_percent="20",
        max_team_exposure_percent="20",
        max_league_window_exposure_percent="20",
        league_window_hours=6,
        accumulators_enabled=accumulators_enabled,
        automation_enabled=True,
        paused_until=paused_until,
    )


def _manual_risk_context(*, open_total="0"):
    now = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
    return RiskContext(
        bankroll_amount="100",
        available_balance="100",
        exposure=PortfolioExposure(
            open_total=open_total,
            staked_last_24h="0",
            staked_last_7d="0",
            ticket_count_last_24h=0,
            ticket_count_last_7d=0,
            by_match={},
            by_team={},
            league_exposures=(),
        ),
        now=now,
    )


class _ManualRiskSession:
    def __init__(self, matches):
        self.matches = matches
        self.flush_count = 0

    async def execute(self, _stmt):
        return _FakeExecuteResult(rows=self.matches)

    async def flush(self):
        self.flush_count += 1


class _FakeSession:
    def __init__(self, bankroll=None):
        self.bankroll = bankroll
        self.added = []
        self._ticket_id = 0
        self.get_calls = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "Ticket" and getattr(obj, "id", None) is None:
                self._ticket_id += 1
                obj.id = self._ticket_id

    async def get(self, model, pk, **kwargs):
        self.get_calls.append((model, pk, kwargs))
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
            def all(self):
                return rows

        return _Scalars()

    def all(self):
        return self._rows


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


class _ReferenceValidationSession(_FakeSession):
    def __init__(self, *, match_ids, predictions=None, bankroll=None):
        super().__init__(bankroll=bankroll)
        self.match_ids = match_ids
        self.predictions = predictions or []
        self.execute_calls = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _FakeExecuteResult(rows=self.match_ids)
        return _FakeExecuteResult(rows=self.predictions)


@pytest.mark.asyncio
async def test_manual_ticket_requires_bankroll_and_explicit_policy_before_any_creation(monkeypatch):
    create_calls = []

    async def fake_create_ticket(**kwargs):
        create_calls.append(kwargs)

    monkeypatch.setattr(ticket_engine, "create_ticket", fake_create_ticket)

    with pytest.raises(ticket_engine.TicketRiskPolicyRequiredError) as exc_info:
        await create_manual_ticket(
            db=_ManualRiskSession([]),
            user_id=8,
            ticket_type="single",
            stake=1,
            bankroll_id=None,
            legs_data=[{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}],
        )

    assert exc_info.value.report["risk_assessment"]["blockers"] == [
        {"code": "risk_policy_required", "scope": "policy"}
    ]
    assert create_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stake", "policy", "context", "expected_code"),
    [
        (
            1,
            _manual_risk_policy(paused_until=datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)),
            _manual_risk_context(),
            "responsible_gambling_pause_active",
        ),
        (6, _manual_risk_policy(), _manual_risk_context(), "ticket_stake_hard_cap_exceeded"),
        (2, _manual_risk_policy(), _manual_risk_context(open_total="19"), "open_exposure_hard_cap_exceeded"),
        (2, _manual_risk_policy(), _manual_risk_context(), "manual_stake_policy_mismatch"),
    ],
)
async def test_manual_ticket_blocks_pause_hard_cap_and_existing_portfolio_exposure(
    monkeypatch,
    stake,
    policy,
    context,
    expected_code,
):
    create_calls = []
    policy_row = SimpleNamespace(id=31, version=1)

    async def fake_load_policy_context(*_args, **_kwargs):
        return SimpleNamespace(id=5), policy_row, policy, context

    async def fake_create_ticket(**kwargs):
        create_calls.append(kwargs)

    monkeypatch.setattr(ticket_engine, "_load_policy_context", fake_load_policy_context)
    monkeypatch.setattr(ticket_engine, "create_ticket", fake_create_ticket)
    db = _ManualRiskSession(
        [
            SimpleNamespace(
                id=10,
                home_team="Alpha",
                away_team="Beta",
                competition="Test League",
                match_date=datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc),
            )
        ]
    )

    with pytest.raises(ticket_engine.TicketManualRiskConflictError) as exc_info:
        await create_manual_ticket(
            db=db,
            user_id=8,
            ticket_type="single",
            stake=stake,
            bankroll_id=5,
            legs_data=[{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}],
        )

    blocker_codes = {
        blocker["code"] for blocker in exc_info.value.report["risk_assessment"]["blockers"]
    }
    assert expected_code in blocker_codes
    assert create_calls == []


@pytest.mark.asyncio
async def test_manual_ticket_assesses_accumulator_and_persists_policy_evidence(monkeypatch):
    policy = _manual_risk_policy()
    context = _manual_risk_context()
    policy_row = SimpleNamespace(id=31, version=1)
    created_ticket = SimpleNamespace(id=44)
    create_calls = []

    async def fake_load_policy_context(*_args, **kwargs):
        assert kwargs["lock_bankroll"] is True
        return SimpleNamespace(id=5), policy_row, policy, context

    async def fake_create_ticket(**kwargs):
        create_calls.append(kwargs)
        return created_ticket

    monkeypatch.setattr(ticket_engine, "_load_policy_context", fake_load_policy_context)
    monkeypatch.setattr(ticket_engine, "create_ticket", fake_create_ticket)
    db = _ManualRiskSession(
        [
            SimpleNamespace(
                id=10,
                home_team="Alpha",
                away_team="Beta",
                competition="Test League",
                match_date=datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=11,
                home_team="Gamma",
                away_team="Delta",
                competition="Test League",
                match_date=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    legs = [
        {"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0},
        {"match_id": 11, "market": "1x2", "selection": "away", "odds": 2.1},
    ]

    with pytest.raises(ticket_engine.TicketManualRiskConflictError) as exc_info:
        await create_manual_ticket(
            db=db,
            user_id=8,
            ticket_type="double",
            stake=1,
            bankroll_id=5,
            legs_data=legs,
            accumulator_risk_acknowledged=False,
        )
    assert "accumulator_acknowledgement_required" in {
        blocker["code"] for blocker in exc_info.value.report["risk_assessment"]["blockers"]
    }
    assert create_calls == []

    ticket = await create_manual_ticket(
        db=db,
        user_id=8,
        ticket_type="double",
        stake=1,
        bankroll_id=5,
        legs_data=legs,
        accumulator_risk_acknowledged=True,
    )

    assert ticket is created_ticket
    assert create_calls == [
        {
            "db": db,
            "user_id": 8,
            "ticket_type": "double",
            "stake": 1.0,
            "bankroll_id": 5,
            "legs_data": legs,
            "status": "open",
            "debit_bankroll": True,
            "validate_references": True,
        }
    ]
    assert ticket.risk_policy_id == 31
    assert ticket.risk_policy_version == 1
    assert ticket.risk_assessment["allowed"] is True
    assert ticket.staking_snapshot == {
        "mode": "flat_percent",
        "eligible": True,
        "stake": "1.00",
        "stake_percent": "1",
        "full_kelly_fraction": None,
        "applied_kelly_fraction": None,
        "reason_code": None,
    }


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stake", "legs_data", "expected_error"),
    [
        (0, [{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}], "stake"),
        (float("inf"), [{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}], "stake"),
        (10, [], "at least one leg"),
        (10, [{"match_id": 10, "market": "1x2", "selection": "home", "odds": 1.0}], "odds"),
        (10, [{"match_id": 0, "market": "1x2", "selection": "home", "odds": 2.0}], "valid match"),
        (10, [{"match_id": 10, "market": "", "selection": "home", "odds": 2.0}], "market"),
    ],
)
async def test_create_ticket_rejects_invalid_financial_or_leg_input_before_database_access(
    stake,
    legs_data,
    expected_error,
):
    db = _FakeSession()

    with pytest.raises(ValueError, match=expected_error):
        await create_ticket(
            db=db,
            user_id=8,
            ticket_type="single",
            stake=stake,
            bankroll_id=5,
            legs_data=legs_data,
        )

    assert db.get_calls == []


@pytest.mark.asyncio
async def test_create_ticket_locks_bankroll_before_debit():
    bankroll = type("Bankroll", (), {"id": 5, "user_id": 8, "balance": 100.0})()
    db = _FakeSession(bankroll=bankroll)

    await create_ticket(
        db=db,
        user_id=8,
        ticket_type="single",
        stake=10.0,
        bankroll_id=5,
        legs_data=[{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}],
    )

    assert db.get_calls[0][2] == {"with_for_update": True}
    assert bankroll.balance == 90.0


@pytest.mark.asyncio
async def test_create_ticket_reference_validation_rejects_missing_match_before_debit():
    bankroll = type("Bankroll", (), {"id": 5, "user_id": 8, "balance": 100.0})()
    db = _ReferenceValidationSession(match_ids=[], bankroll=bankroll)

    with pytest.raises(ValueError, match="Matches not found: 10"):
        await create_ticket(
            db=db,
            user_id=8,
            ticket_type="single",
            stake=10.0,
            bankroll_id=5,
            legs_data=[{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}],
            validate_references=True,
        )

    assert db.get_calls == []
    assert bankroll.balance == 100.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("predictions", "expected_error", "error_type"),
    [
        ([], "Model predictions not found: 301", ValueError),
        ([SimpleNamespace(id=301, match_id=10, user_id=99)], "do not belong", PermissionError),
        ([SimpleNamespace(id=301, match_id=11, user_id=8)], "lineage are inconsistent", ValueError),
    ],
)
async def test_create_ticket_reference_validation_rejects_invalid_prediction_lineage(
    predictions,
    expected_error,
    error_type,
):
    bankroll = type("Bankroll", (), {"id": 5, "user_id": 8, "balance": 100.0})()
    db = _ReferenceValidationSession(match_ids=[10], predictions=predictions, bankroll=bankroll)

    with pytest.raises(error_type, match=expected_error):
        await create_ticket(
            db=db,
            user_id=8,
            ticket_type="single",
            stake=10.0,
            bankroll_id=5,
            legs_data=[
                {
                    "model_prediction_id": 301,
                    "match_id": 10,
                    "market": "1x2",
                    "selection": "home",
                    "odds": 2.0,
                }
            ],
            validate_references=True,
        )

    assert db.get_calls == []
    assert bankroll.balance == 100.0


@pytest.mark.asyncio
async def test_create_ticket_reference_validation_accepts_owned_matching_prediction():
    bankroll = type("Bankroll", (), {"id": 5, "user_id": 8, "balance": 100.0})()
    db = _ReferenceValidationSession(
        match_ids=[10],
        predictions=[
            SimpleNamespace(
                id=301,
                run_id=77,
                match_id=10,
                market="1x2",
                home_prob=0.62,
                draw_prob=0.23,
                away_prob=0.15,
                expected_value=0.08,
                quality_report={
                    "market": {"probabilities": {"home": 0.57}},
                    "edge": {"pick_edge_pct": 8.0},
                    "reliability": {"label": "reliable", "score": 91},
                },
                user_id=8,
            )
        ],
        bankroll=bankroll,
    )

    ticket = await create_ticket(
        db=db,
        user_id=8,
        ticket_type="single",
        stake=10.0,
        bankroll_id=5,
        legs_data=[
            {
                "model_prediction_id": 301,
                "match_id": 10,
                "market": "1x2",
                "selection": "home",
                "odds": 2.0,
                # Service callers cannot override server-owned audit evidence.
                "model_probability_snapshot": 0.99,
                "reliability_label_snapshot": "client-forged",
            }
        ],
        validate_references=True,
    )

    assert ticket.status == "open"
    assert bankroll.balance == 90.0
    leg = next(obj for obj in db.added if obj.__class__.__name__ == "TicketLeg")
    assert leg.prediction_run_id_snapshot == 77
    assert leg.model_probability_snapshot == pytest.approx(0.62)
    assert leg.market_probability_snapshot == pytest.approx(0.57)
    assert leg.market_probability_basis_snapshot == "consensus_de_vig"
    assert leg.expected_value_snapshot == pytest.approx(0.08)
    assert leg.edge_pct_snapshot == pytest.approx(8.0)
    assert leg.reliability_label_snapshot == "reliable"
    assert leg.reliability_score_snapshot == pytest.approx(91)


@pytest.mark.asyncio
async def test_manual_leg_without_prediction_discards_caller_snapshot_values():
    db = _ReferenceValidationSession(match_ids=[10])

    await create_ticket(
        db=db,
        user_id=8,
        ticket_type="single",
        stake=10.0,
        legs_data=[
            {
                "match_id": 10,
                "market": "1x2",
                "selection": "home",
                "odds": 2.0,
                "model_probability_snapshot": 0.99,
                "reliability_label_snapshot": "client-forged",
            }
        ],
        validate_references=True,
    )

    leg = next(obj for obj in db.added if obj.__class__.__name__ == "TicketLeg")
    assert leg.model_probability_snapshot is None
    assert leg.reliability_label_snapshot is None


@pytest.mark.asyncio
async def test_generated_ticket_is_draft_without_bankroll_debit_or_ledger():
    bankroll = type("Bankroll", (), {"id": 5, "user_id": 8, "balance": 5.0})()
    db = _FakeSession(bankroll=bankroll)

    ticket = await create_ticket(
        db=db,
        user_id=8,
        ticket_type="single",
        stake=10.0,
        bankroll_id=5,
        legs_data=[{"match_id": 10, "market": "1x2", "selection": "home", "odds": 2.0}],
        status="generated",
        debit_bankroll=False,
    )

    assert ticket.status == "generated"
    assert bankroll.balance == 5.0
    assert db.get_calls[0][2] == {"with_for_update": False}
    assert not any(obj.__class__.__name__ == "LedgerEntry" for obj in db.added)
    leg = next(obj for obj in db.added if obj.__class__.__name__ == "TicketLeg")
    assert leg.model_probability_snapshot is None
    assert leg.prediction_run_id_snapshot is None


@pytest.mark.asyncio
async def test_create_ticket_persists_generation_time_prediction_snapshots():
    db = _FakeSession()
    snapshots = {
        "prediction_run_id_snapshot": 77,
        "model_probability_snapshot": 0.62,
        "market_probability_snapshot": 0.57,
        "market_probability_basis_snapshot": "consensus_de_vig",
        "expected_value_snapshot": 0.08,
        "edge_pct_snapshot": 8.0,
        "reliability_label_snapshot": "reliable",
        "reliability_score_snapshot": 91.0,
    }

    await create_ticket(
        db=db,
        user_id=8,
        ticket_type="single",
        stake=10.0,
        legs_data=[
            {
                "model_prediction_id": 42,
                "match_id": 10,
                "market": "1x2",
                "selection": "home",
                "odds": 1.95,
                **snapshots,
            }
        ],
        status="generated",
        debit_bankroll=False,
    )

    leg = next(obj for obj in db.added if obj.__class__.__name__ == "TicketLeg")
    assert {name: getattr(leg, name) for name in snapshots} == snapshots


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
                "market": {
                    "probabilities": {"home": 0.57},
                    "odds": {"home": {"odds": 1.95, "bookmaker": "Pinnacle"}},
                },
                "edge": {"pick_edge_pct": 8.5},
                "reliability": {"label": "reliable", "score": 91},
            },
        },
    )()

    candidate = _build_ticket_candidate(prediction, min_odds=1.5, max_odds=2.5)

    assert candidate == {
        "model_prediction_id": 42,
        "prediction_run_id": None,
        "match_id": 10,
        "market": "1x2",
        "selection": "home",
        "odds": 1.95,
        "probability": 0.62,
        "bookmaker": "Pinnacle",
        "score": pytest.approx(0.08),
        "prediction_run_id_snapshot": None,
        "model_probability_snapshot": pytest.approx(0.62),
        "market_probability_snapshot": pytest.approx(0.57),
        "market_probability_basis_snapshot": "consensus_de_vig",
        "expected_value_snapshot": pytest.approx(0.08),
        "edge_pct_snapshot": pytest.approx(8.5),
        "reliability_label_snapshot": "reliable",
        "reliability_score_snapshot": pytest.approx(91),
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


def _swap_leg(leg_id: int, match_id: int | None, odds: float):
    return SimpleNamespace(
        id=leg_id,
        model_prediction_id=1000 + leg_id,
        match_id=match_id,
        selection="home",
        market="1x2",
        odds=odds,
        bookmaker="Pinnacle",
        prediction_run_id_snapshot=2000 + leg_id,
        model_probability_snapshot=leg_id / 100,
        market_probability_snapshot=leg_id / 110,
        market_probability_basis_snapshot="consensus_de_vig",
        expected_value_snapshot=leg_id / 1000,
        edge_pct_snapshot=leg_id / 10,
        reliability_label_snapshot="reliable",
        reliability_score_snapshot=80 + leg_id / 100,
    )


class _SwapScalars:
    def __init__(self, tickets):
        self.tickets = tickets

    def unique(self):
        return self

    def all(self):
        return self.tickets


class _SwapResult:
    def __init__(self, tickets):
        self.tickets = tickets

    def scalars(self):
        return _SwapScalars(self.tickets)


class _SwapSession:
    def __init__(self, tickets):
        self.tickets = tickets
        self.flushed = False
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        return _SwapResult(self.tickets)

    async def flush(self):
        self.flushed = True


@pytest.mark.asyncio
async def test_swap_moves_prediction_snapshots_with_the_selected_leg():
    source_leg = _swap_leg(11, 1, 1.8)
    target_leg = _swap_leg(21, 3, 2.4)
    source = SimpleNamespace(
        id=1,
        status="generated",
        stake=10.0,
        total_odds=3.78,
        potential_return=37.8,
        legs=[source_leg, _swap_leg(12, 2, 2.1)],
    )
    target = SimpleNamespace(
        id=2,
        status="generated",
        stake=10.0,
        total_odds=4.08,
        potential_return=40.8,
        legs=[target_leg, _swap_leg(22, 4, 1.7)],
    )
    source_snapshot = (source_leg.prediction_run_id_snapshot, source_leg.model_probability_snapshot)
    target_snapshot = (target_leg.prediction_run_id_snapshot, target_leg.model_probability_snapshot)
    db = _SwapSession([source, target])

    await swap_ticket_legs(
        db=db,
        user_id=8,
        source_ticket_id=1,
        source_leg_id=11,
        target_ticket_id=2,
        target_leg_id=21,
    )

    assert (source_leg.prediction_run_id_snapshot, source_leg.model_probability_snapshot) == target_snapshot
    assert (target_leg.prediction_run_id_snapshot, target_leg.model_probability_snapshot) == source_snapshot
    assert db.flushed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate_on", ["source", "target"])
async def test_swap_rejects_projected_duplicate_match_without_mutating_either_ticket(duplicate_on):
    if duplicate_on == "source":
        source_legs = [_swap_leg(11, 1, 1.8), _swap_leg(12, 3, 2.1)]
        target_legs = [_swap_leg(21, 3, 2.4), _swap_leg(22, 4, 1.7)]
    else:
        source_legs = [_swap_leg(11, 4, 1.8), _swap_leg(12, 2, 2.1)]
        target_legs = [_swap_leg(21, 1, 2.4), _swap_leg(22, 4, 1.7)]
    source = SimpleNamespace(
        id=1,
        status="generated",
        stake=10.0,
        total_odds=3.78,
        potential_return=37.8,
        legs=source_legs,
    )
    target = SimpleNamespace(
        id=2,
        status="generated",
        stake=10.0,
        total_odds=4.08,
        potential_return=40.8,
        legs=target_legs,
    )
    before = {
        leg.id: (leg.model_prediction_id, leg.match_id, leg.selection, leg.market, leg.odds, leg.bookmaker)
        for leg in source.legs + target.legs
    }
    totals_before = (source.total_odds, source.potential_return, target.total_odds, target.potential_return)
    db = _SwapSession([source, target])

    with pytest.raises(ValueError, match="would contain duplicate matches"):
        await swap_ticket_legs(
            db=db,
            user_id=8,
            source_ticket_id=source.id,
            source_leg_id=11,
            target_ticket_id=target.id,
            target_leg_id=21,
        )

    after = {
        leg.id: (leg.model_prediction_id, leg.match_id, leg.selection, leg.market, leg.odds, leg.bookmaker)
        for leg in source.legs + target.legs
    }
    assert after == before
    assert (source.total_odds, source.potential_return, target.total_odds, target.potential_return) == totals_before
    assert db.flushed is False


@pytest.mark.asyncio
async def test_swap_scopes_tickets_to_selected_batch_before_mutation():
    db = _SwapSession([])

    with pytest.raises(ValueError, match="selected batch"):
        await swap_ticket_legs(
            db=db,
            user_id=8,
            batch_id=77,
            source_ticket_id=1,
            source_leg_id=11,
            target_ticket_id=2,
            target_leg_id=21,
        )

    assert "tickets.batch_id = 77" in db.statements[0]
    assert db.flushed is False


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
            "quality_report": {
                "model": {"pick": "home"},
                "reliability": {"is_ticket_eligible": True},
            },
            "created_at": None,
            "match": SimpleNamespace(
                id=match_id,
                status="scheduled",
                match_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
            ),
        },
    )()


def _run(run_id: int, *, status: str = "completed", source_dataset_id: int = 29):
    return SimpleNamespace(
        id=run_id,
        status=status,
        source_dataset_id=source_dataset_id,
        input_hash=f"input-{run_id}",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("automated", "expected_code"), [(False, "manual"), (True, "scheduled")])
async def test_generate_tickets_enforces_versioned_run_governance_before_candidate_creation(
    monkeypatch,
    automated,
    expected_code,
):
    db = _FakeGenerateSession([_FakeExecuteResult(scalar=_run(22))])

    async def blocked_governance(*_args, **kwargs):
        assert kwargs["automated"] is automated
        return {
            "allowed": False,
            "mode": expected_code,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runs": [
                {
                    "run_id": 22,
                    "model_version_id": 9,
                    "allowed": False,
                    "reason": "staged_manual_paper_only" if automated else "certification_missing_or_expired",
                }
            ],
            "model_evaluation_ids": [],
        }

    monkeypatch.setattr(ticket_engine, "assess_prediction_runs_governance", blocked_governance)

    with pytest.raises(ticket_engine.TicketGenerationError) as exc_info:
        await generate_tickets(
            db=db,
            user_id=7,
            bankroll_id=None,
            ticket_count=1,
            difficulty="safe",
            automated=automated,
            market_types=["1x2"],
            min_odds=1.5,
            max_odds=2.5,
            stake=10.0,
        )

    blockers = exc_info.value.report["risk_assessment"]["blockers"]
    assert blockers[0]["code"] == f"model_governance_{expected_code}_blocked"
    assert not db.added


@pytest.mark.asyncio
async def test_batch_revalidation_reloads_versioned_run_governance(monkeypatch):
    run = SimpleNamespace(id=22, user_id=7, model_version_id=9)
    db = _FakeGenerateSession([_FakeExecuteResult(rows=[run])])
    now = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
    batch = SimpleNamespace(
        generation_report={
            "governance_assessment": {
                "runs": [{"run_id": 22, "model_version_id": 9, "allowed": True}]
            }
        }
    )

    async def current_governance(*_args, **kwargs):
        assert kwargs["runs"] == [run]
        assert kwargs["now"] == now
        return {
            "allowed": False,
            "mode": "manual",
            "checked_at": now.isoformat(),
            "runs": [{"run_id": 22, "allowed": False, "reason": "critical_monitoring_drift"}],
            "model_evaluation_ids": [31],
        }

    monkeypatch.setattr(ticket_engine, "assess_prediction_runs_governance", current_governance)

    result = await ticket_engine._revalidate_batch_governance(
        db,
        batch=batch,
        user_id=7,
        automated=False,
        now=now,
    )

    assert result["allowed"] is False
    assert result["runs"][0]["reason"] == "critical_monitoring_drift"
    assert "prediction_runs.user_id = 7" in db.statements[0]


@pytest.mark.asyncio
async def test_generate_tickets_uses_latest_eligible_prediction_run_by_default(monkeypatch):
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=_run(22)),
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
    assert batch.source_prediction_run_id == 22
    assert batch.generation_report["prediction_run_id"] == 22
    assert batch.generation_report["eligible_candidates"] == 1
    assert [ticket.id for ticket in tickets] == [1]
    assert ticket_calls[0]["legs_data"][0]["model_prediction_id"] == 202
    assert ticket_calls[0]["legs_data"][0]["prediction_run_id_snapshot"] == 22
    assert ticket_calls[0]["legs_data"][0]["model_probability_snapshot"] == pytest.approx(0.62)
    assert ticket_calls[0]["legs_data"][0]["market_probability_basis_snapshot"] == "inverse_selected_odds"
    assert ticket_calls[0]["legs_data"][0]["expected_value_snapshot"] == pytest.approx(0.1)
    assert ticket_calls[0]["status"] == "generated"
    assert ticket_calls[0]["debit_bankroll"] is False
    assert "FROM prediction_runs" in db.statements[0]
    assert "ORDER BY prediction_runs.completed_at DESC NULLS LAST" in db.statements[0]
    assert "model_predictions.run_id = 22" in db.statements[1]


@pytest.mark.asyncio
async def test_generate_tickets_can_scope_to_explicit_prediction_run(monkeypatch):
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=_run(11, status="partial")),
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
    assert "prediction_runs.status IN ('completed', 'partial')" in db.statements[0]
    assert "ORDER BY prediction_runs.completed_at" not in db.statements[0]
    assert "model_predictions.run_id = 11" in db.statements[1]


@pytest.mark.asyncio
async def test_generate_tickets_accepts_multiple_runs_from_one_dataset(monkeypatch):
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(rows=[_run(22), _run(11, status="partial")]),
            _FakeExecuteResult(
                rows=[
                    _prediction(prediction_id=202, run_id=22, match_id=12, expected_value=0.2),
                    _prediction(prediction_id=101, run_id=11, match_id=10, expected_value=0.1),
                ]
            ),
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
        difficulty="balanced",
        market_types=["1x2"],
        min_odds=1.5,
        max_odds=2.5,
        stake=10.0,
        run_ids=[11, 22],
        prediction_ids=[101, 202],
    )

    assert [ticket.id for ticket in tickets] == [1]
    assert batch.source_prediction_run_id == 11
    assert batch.source_prediction_run_ids == [11, 22]
    assert batch.generation_report["prediction_run_ids"] == [11, 22]
    assert batch.generation_report["source_dataset_id"] == 29
    assert batch.generation_report["generation_status"] == "generated"
    assert batch.generation_report["scanned_predictions_by_run"] == {"11": 1, "22": 1}
    assert batch.generation_report["eligible_candidates_by_run"] == {"11": 1, "22": 1}
    assert batch.generation_report["generated_prediction_ids"] == [101, 202]
    assert batch.generation_report["generated_prediction_run_ids"] == [22, 11]
    assert batch.generation_report["generated_ticket_lineage"] == [
        {
            "ticket_id": 1,
            "prediction_ids": [202, 101],
            "prediction_run_ids": [22, 11],
            "match_ids": [12, 10],
        }
    ]
    assert {leg["model_prediction_id"] for leg in ticket_calls[0]["legs_data"]} == {101, 202}
    assert "prediction_runs.id IN (11, 22)" in db.statements[0]
    assert "model_predictions.run_id IN (11, 22)" in db.statements[1]


@pytest.mark.asyncio
async def test_generate_tickets_marks_final_generation_report_dirty_for_persistence(monkeypatch):
    class _TrackingSession(_FakeGenerateSession):
        def __init__(self, responses):
            super().__init__(responses)
            self.report_snapshot_recorded = False

        async def flush(self):
            await super().flush()
            if self.report_snapshot_recorded:
                return
            batch = next(
                (obj for obj in self.added if obj.__class__.__name__ == "TicketBatch" and obj.id is not None),
                None,
            )
            if batch is not None:
                set_committed_value(batch, "generation_report", batch.generation_report)
                self.report_snapshot_recorded = True

    db = _TrackingSession(
        [
            _FakeExecuteResult(scalar=_run(11)),
            _FakeExecuteResult(rows=[_prediction(prediction_id=101, run_id=11, match_id=10)]),
        ]
    )

    async def fake_create_ticket(**_kwargs):
        return SimpleNamespace(id=1)

    monkeypatch.setattr(ticket_engine, "create_ticket", fake_create_ticket)
    batch, _tickets = await generate_tickets(
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

    assert db.report_snapshot_recorded is True
    assert batch.generation_report["generation_status"] == "generated"
    assert inspect(batch).attrs.generation_report.history.has_changes() is True


@pytest.mark.asyncio
async def test_generate_tickets_rejects_multiple_runs_from_different_datasets():
    db = _FakeGenerateSession(
        [_FakeExecuteResult(rows=[_run(11, source_dataset_id=29), _run(22, source_dataset_id=30)])]
    )

    with pytest.raises(ValueError, match="same source dataset"):
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
            run_ids=[11, 22],
        )


@pytest.mark.asyncio
async def test_generate_tickets_excludes_started_and_explicitly_ineligible_predictions(monkeypatch):
    started = _prediction(prediction_id=101, run_id=11, match_id=10)
    started.match.match_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    ineligible = _prediction(prediction_id=102, run_id=11, match_id=11)
    ineligible.quality_report["reliability"] = {"is_ticket_eligible": False}
    eligible = _prediction(prediction_id=103, run_id=11, match_id=12)
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=_run(11, status="partial")),
            _FakeExecuteResult(rows=[started, ineligible, eligible]),
        ]
    )

    async def fake_create_ticket(**_kwargs):
        return SimpleNamespace(id=1)

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
        run_id=11,
    )

    assert len(tickets) == 1
    assert batch.generation_report["scanned_predictions"] == 3
    assert batch.generation_report["eligible_candidates"] == 1
    assert batch.generation_report["excluded_predictions"] == 2
    assert batch.generation_report["excluded_by_reason"] == {
        "match_started_or_finished": 1,
        "quality_ineligible": 1,
    }


@pytest.mark.asyncio
async def test_generate_tickets_requires_explicit_positive_reliability(monkeypatch):
    missing_reliability = _prediction(prediction_id=101, run_id=11, match_id=10)
    missing_reliability.quality_report.pop("reliability")
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=_run(11)),
            _FakeExecuteResult(rows=[missing_reliability]),
        ]
    )

    with pytest.raises(ticket_engine.TicketGenerationError, match="No safe prediction candidates") as exc_info:
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

    assert exc_info.value.report["excluded_by_reason"] == {"quality_ineligible": 1}


@pytest.mark.asyncio
async def test_generate_tickets_rejects_requested_prediction_outside_selected_run():
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=_run(11)),
            _FakeExecuteResult(rows=[_prediction(prediction_id=101, run_id=11, match_id=10)]),
        ]
    )

    with pytest.raises(ticket_engine.TicketGenerationError, match="missing or do not belong") as exc_info:
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
            prediction_ids=[101, 999],
        )

    assert exc_info.value.report["requested_predictions"] == 2
    assert exc_info.value.report["missing_predictions"] == 1
    assert exc_info.value.report["missing_prediction_ids"] == [999]
    assert "model_predictions.id IN (101, 999)" in db.statements[1]


@pytest.mark.asyncio
async def test_generate_tickets_rejects_difficulty_when_unique_matches_are_insufficient():
    same_match_predictions = [
        _prediction(prediction_id=101, run_id=11, match_id=10),
        _prediction(prediction_id=102, run_id=11, match_id=10),
    ]
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=_run(11)),
            _FakeExecuteResult(rows=same_match_predictions),
        ]
    )

    with pytest.raises(ticket_engine.TicketGenerationError, match="requires 2 unique matches") as exc_info:
        await generate_tickets(
            db=db,
            user_id=7,
            bankroll_id=None,
            ticket_count=1,
            difficulty="balanced",
            market_types=["1x2"],
            min_odds=1.5,
            max_odds=2.5,
            stake=10.0,
            run_id=11,
        )

    assert exc_info.value.report["required_legs_per_ticket"] == 2
    assert exc_info.value.report["eligible_unique_matches"] == 1


@pytest.mark.asyncio
async def test_generate_tickets_rejects_run_with_no_predictions_truthfully():
    db = _FakeGenerateSession(
        [
            _FakeExecuteResult(scalar=_run(11, status="partial")),
            _FakeExecuteResult(rows=[]),
        ]
    )

    with pytest.raises(ticket_engine.TicketGenerationError, match="has no predictions") as exc_info:
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

    assert exc_info.value.report["scanned_predictions"] == 0
    assert exc_info.value.report["prediction_run_status"] == "partial"


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


@pytest.mark.asyncio
async def test_generate_tickets_service_rejects_more_than_fifty_tickets_before_database_access():
    with pytest.raises(ValueError, match="must not exceed 50"):
        await generate_tickets(
            db=object(),
            user_id=7,
            bankroll_id=None,
            ticket_count=51,
            difficulty="safe",
            market_types=["1x2"],
            min_odds=1.5,
            max_odds=2.5,
            stake=10.0,
        )


class _ActivateSession:
    def __init__(self, batch, tickets, bankroll=None, *, legs=None, matches=None, predictions=None):
        batch.tickets_count = getattr(batch, "tickets_count", len(tickets))
        batch.total_stake = getattr(batch, "total_stake", sum(ticket.stake for ticket in tickets))
        batch.source_prediction_run_id = getattr(batch, "source_prediction_run_id", 31)
        batch.generation_report = getattr(
            batch,
            "generation_report",
            {"prediction_run_ids": [31], "source_dataset_id": 33},
        )
        if legs is None:
            legs = [
                SimpleNamespace(
                    id=100 + index,
                    ticket_id=ticket.id,
                    match_id=200 + index,
                    model_prediction_id=300 + index,
                )
                for index, ticket in enumerate(tickets, start=1)
            ]
        else:
            for index, leg in enumerate(legs, start=1):
                if not hasattr(leg, "model_prediction_id"):
                    leg.model_prediction_id = 300 + index
        if predictions is None:
            predictions = [
                SimpleNamespace(
                    id=leg.model_prediction_id,
                    run_id=31,
                    match_id=leg.match_id,
                    user_id=8,
                    source_dataset_id=33,
                )
                for leg in legs
            ]
        if matches is None:
            matches = [
                SimpleNamespace(
                    id=leg.match_id,
                    match_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
                    status="scheduled",
                )
                for leg in legs
            ]
        self.responses = [
            _FakeExecuteResult(scalar=batch),
            _FakeExecuteResult(rows=tickets),
            _FakeExecuteResult(rows=legs),
            _FakeExecuteResult(rows=predictions),
            _FakeExecuteResult(rows=matches),
        ]
        if bankroll is not None:
            self.responses.append(_FakeExecuteResult(scalar=bankroll))
        self.added = []

    async def execute(self, _stmt):
        return self.responses.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


class _DiscardSession:
    def __init__(self, batch, tickets, *, artifact_results=None):
        self.responses = [
            _FakeExecuteResult(scalar=batch),
            _FakeExecuteResult(rows=tickets),
            *[
                _FakeExecuteResult(scalar=value)
                for value in (artifact_results if artifact_results is not None else [None, None, None, None])
            ],
            _FakeExecuteResult(),
            _FakeExecuteResult(),
            _FakeExecuteResult(),
        ]
        self.statements = []
        self.row_lock_flags = []
        self.flushed = False

    async def execute(self, stmt):
        self.statements.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        self.row_lock_flags.append(getattr(stmt, "_for_update_arg", None) is not None)
        return self.responses.pop(0)

    async def flush(self):
        self.flushed = True


@pytest.mark.asyncio
async def test_discard_generated_batch_deletes_only_owned_untouched_drafts_under_row_locks():
    batch = SimpleNamespace(id=77)
    tickets = [
        SimpleNamespace(id=1, user_id=8, batch_id=77, status="generated"),
        SimpleNamespace(id=2, user_id=8, batch_id=77, status="generated"),
    ]
    db = _DiscardSession(batch, tickets)

    discarded_batch_id, discarded_tickets = await ticket_engine.discard_generated_ticket_batch(
        db=db,
        user_id=8,
        batch_id=77,
    )

    assert (discarded_batch_id, discarded_tickets) == (77, 2)
    assert db.row_lock_flags[:2] == [True, True]
    assert "DELETE FROM ticket_legs" in db.statements[-3]
    assert "DELETE FROM tickets" in db.statements[-2]
    assert "DELETE FROM ticket_batches" in db.statements[-1]
    assert db.flushed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("batch", "tickets"),
    [
        (None, []),
        (SimpleNamespace(id=77), []),
        (
            SimpleNamespace(id=77),
            [SimpleNamespace(id=1, user_id=99, batch_id=77, status="generated")],
        ),
    ],
)
async def test_discard_generated_batch_hides_missing_or_foreign_batch(batch, tickets):
    db = _DiscardSession(batch, tickets)

    with pytest.raises(LookupError, match="Ticket batch not found"):
        await ticket_engine.discard_generated_ticket_batch(db=db, user_id=8, batch_id=77)

    assert not any(statement.startswith("DELETE") for statement in db.statements)
    assert db.flushed is False


@pytest.mark.asyncio
async def test_discard_generated_batch_rejects_non_draft_without_deleting():
    batch = SimpleNamespace(id=77)
    tickets = [SimpleNamespace(id=1, user_id=8, batch_id=77, status="open")]
    db = _DiscardSession(batch, tickets)

    with pytest.raises(ticket_engine.TicketBatchDiscardConflictError, match="generated draft"):
        await ticket_engine.discard_generated_ticket_batch(db=db, user_id=8, batch_id=77)

    assert not any(statement.startswith("DELETE") for statement in db.statements)
    assert db.flushed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact_index", "expected_artifact"),
    [
        (0, "ledger entries"),
        (1, "bookmaker placements"),
        (2, "settlements"),
        (3, "trading executions"),
    ],
)
async def test_discard_generated_batch_rejects_any_financial_or_execution_artifact(
    artifact_index,
    expected_artifact,
):
    batch = SimpleNamespace(id=77)
    tickets = [SimpleNamespace(id=1, user_id=8, batch_id=77, status="generated")]
    artifact_results = [None, None, None, None]
    artifact_results[artifact_index] = 901
    db = _DiscardSession(batch, tickets, artifact_results=artifact_results)

    with pytest.raises(ticket_engine.TicketBatchDiscardConflictError, match=expected_artifact):
        await ticket_engine.discard_generated_ticket_batch(db=db, user_id=8, batch_id=77)

    assert not any(statement.startswith("DELETE") for statement in db.statements)
    assert db.flushed is False


@pytest.mark.asyncio
async def test_activate_generated_batch_debits_once_and_opens_all_tickets():
    batch = SimpleNamespace(id=77, bankroll_id=5)
    tickets = [
        SimpleNamespace(id=1, user_id=8, batch_id=77, bankroll_id=5, stake=10.0, status="generated"),
        SimpleNamespace(id=2, user_id=8, batch_id=77, bankroll_id=5, stake=15.0, status="generated"),
    ]
    bankroll = SimpleNamespace(id=5, user_id=8, balance=100.0)
    db = _ActivateSession(batch, tickets, bankroll)

    activated_batch, activated_tickets, debited = await activate_ticket_batch(
        db=db,
        user_id=8,
        batch_id=77,
    )

    assert activated_batch is batch
    assert activated_tickets == tickets
    assert debited == 25.0
    assert bankroll.balance == 75.0
    assert [ticket.status for ticket in tickets] == ["open", "open"]
    ledgers = [obj for obj in db.added if obj.__class__.__name__ == "LedgerEntry"]
    assert [ledger.amount for ledger in ledgers] == [-10.0, -15.0]
    assert [ledger.balance_after for ledger in ledgers] == [90.0, 75.0]

    repeated_db = _ActivateSession(batch, tickets)
    with pytest.raises(ticket_engine.TicketActivationConflictError, match="only be activated once"):
        await activate_ticket_batch(db=repeated_db, user_id=8, batch_id=77)


@pytest.mark.asyncio
async def test_activate_generated_batch_rejects_insufficient_bankroll_without_partial_writes():
    batch = SimpleNamespace(id=77, bankroll_id=5)
    tickets = [
        SimpleNamespace(id=1, user_id=8, batch_id=77, bankroll_id=5, stake=10.0, status="generated"),
        SimpleNamespace(id=2, user_id=8, batch_id=77, bankroll_id=5, stake=15.0, status="generated"),
    ]
    bankroll = SimpleNamespace(id=5, user_id=8, balance=20.0)
    db = _ActivateSession(batch, tickets, bankroll)

    with pytest.raises(ValueError, match="Insufficient bankroll balance"):
        await activate_ticket_batch(db=db, user_id=8, batch_id=77)

    assert bankroll.balance == 20.0
    assert [ticket.status for ticket in tickets] == ["generated", "generated"]
    assert db.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("match_date", "match_status", "expected_error"),
    [
        (datetime(2026, 7, 12, tzinfo=timezone.utc), "scheduled", "has already started"),
        (datetime(2026, 7, 14, tzinfo=timezone.utc), "finished", "is not eligible for activation"),
    ],
)
async def test_activate_generated_batch_revalidates_match_state_before_any_debit(
    match_date,
    match_status,
    expected_error,
):
    batch = SimpleNamespace(id=77, bankroll_id=5)
    ticket = SimpleNamespace(
        id=1,
        user_id=8,
        batch_id=77,
        bankroll_id=5,
        stake=10.0,
        status="generated",
    )
    leg = SimpleNamespace(id=101, ticket_id=1, match_id=201)
    match = SimpleNamespace(id=201, match_date=match_date, status=match_status)
    bankroll = SimpleNamespace(id=5, user_id=8, balance=100.0)
    db = _ActivateSession(batch, [ticket], bankroll, legs=[leg], matches=[match])

    with pytest.raises(ticket_engine.TicketActivationConflictError, match=expected_error):
        await activate_ticket_batch(
            db=db,
            user_id=8,
            batch_id=77,
            now=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )

    assert ticket.status == "generated"
    assert bankroll.balance == 100.0
    assert db.added == []


@pytest.mark.asyncio
async def test_activate_generated_batch_rejects_leg_with_missing_match_without_financial_effects():
    batch = SimpleNamespace(id=77, bankroll_id=5)
    ticket = SimpleNamespace(
        id=1,
        user_id=8,
        batch_id=77,
        bankroll_id=5,
        stake=10.0,
        status="generated",
    )
    leg = SimpleNamespace(id=101, ticket_id=1, match_id=201)
    bankroll = SimpleNamespace(id=5, user_id=8, balance=100.0)
    db = _ActivateSession(batch, [ticket], bankroll, legs=[leg], matches=[])

    with pytest.raises(ticket_engine.TicketActivationConflictError, match="references a missing match"):
        await activate_ticket_batch(db=db, user_id=8, batch_id=77)

    assert ticket.status == "generated"
    assert bankroll.balance == 100.0
    assert db.added == []


@pytest.mark.asyncio
async def test_activate_generated_batch_rejects_prediction_outside_source_runs_before_debit():
    batch = SimpleNamespace(
        id=77,
        bankroll_id=5,
        tickets_count=1,
        total_stake=10.0,
        source_prediction_run_id=31,
        generation_report={"prediction_run_ids": [31], "source_dataset_id": 33},
    )
    ticket = SimpleNamespace(
        id=1,
        user_id=8,
        batch_id=77,
        bankroll_id=5,
        stake=10.0,
        status="generated",
    )
    leg = SimpleNamespace(id=101, ticket_id=1, match_id=201, model_prediction_id=301)
    prediction = SimpleNamespace(
        id=301,
        run_id=99,
        match_id=201,
        user_id=8,
        source_dataset_id=33,
    )
    bankroll = SimpleNamespace(id=5, user_id=8, balance=100.0)
    db = _ActivateSession(
        batch,
        [ticket],
        bankroll,
        legs=[leg],
        predictions=[prediction],
    )

    with pytest.raises(ticket_engine.TicketActivationConflictError, match="outside the batch source runs"):
        await activate_ticket_batch(db=db, user_id=8, batch_id=77)

    assert ticket.status == "generated"
    assert bankroll.balance == 100.0
    assert db.added == []


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
        self._execute_count = 0

    async def execute(self, stmt):
        self._execute_count += 1
        if self._execute_count == 1:
            return _ScalarResult(self.ticket)
        return _ScalarResult(self.bankroll)

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


@pytest.mark.asyncio
async def test_settle_ticket_locks_and_credits_owned_bankroll_once():
    ticket = SimpleNamespace(
        id=12,
        user_id=8,
        stake=10.0,
        status="open",
        bankroll_id=5,
        legs=[SimpleNamespace(status="pending")],
    )
    bankroll = SimpleNamespace(id=5, user_id=8, balance=100.0)
    db = _SettlementSession(ticket=ticket, bankroll=bankroll)

    await settle_ticket(
        db,
        ticket_id=12,
        outcome="void",
        return_amount=10.0,
        user_id=8,
    )

    assert bankroll.balance == 110.0
    ledgers = [obj for obj in db.added if obj.__class__.__name__ == "LedgerEntry"]
    assert len(ledgers) == 1
    assert ledgers[0].entry_type == "void"
    assert ledgers[0].amount == 10.0


@pytest.mark.asyncio
async def test_settle_ticket_rejects_invalid_or_repeated_terminal_transition():
    with pytest.raises(ValueError, match="outcome must be one of"):
        await settle_ticket(object(), ticket_id=12, outcome="cancelled", return_amount=0)
    with pytest.raises(ValueError, match="must be 0"):
        await settle_ticket(object(), ticket_id=12, outcome="lost", return_amount=1)

    ticket = SimpleNamespace(
        id=12,
        stake=10.0,
        status="won",
        bankroll_id=None,
        legs=[],
    )
    db = _SettlementSession(ticket=ticket)
    with pytest.raises(ticket_engine.TicketSettlementConflictError, match="Only active open"):
        await settle_ticket(db, ticket_id=12, outcome="won", return_amount=19.5)
    assert db.added == []
