from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.tickets import _serialize_ticket_lineage, get_ticket_batch_lineage


def _objects():
    now = datetime.now(timezone.utc)
    match = SimpleNamespace(
        id=10,
        competition="NPL South Australia",
        home_team="Home FC",
        away_team="Away FC",
        match_date=now,
        status="scheduled",
    )
    run = SimpleNamespace(
        id=2,
        user_id=1,
        name="Australia run",
        model_type="PoissonGoalsModel",
        ensemble=False,
        status="completed",
        matches_count=1,
        started_at=now,
        completed_at=now,
        error=None,
        source_dataset_id=7,
        strategy_id=4,
        input_hash="hash",
        input_context={"date_from": "2026-07-17"},
        created_at=now,
    )
    prediction = SimpleNamespace(
        id=20,
        run_id=2,
        model_type="PoissonGoalsModel",
        match_id=10,
        market="1x2",
        home_prob=0.5,
        draw_prob=0.2,
        away_prob=0.3,
        home_odds=2.0,
        draw_odds=3.0,
        away_odds=4.0,
        value_home=0.1,
        value_draw=None,
        value_away=None,
        expected_value=0.1,
        quality_report={"reliability": "medium"},
        created_at=now,
        run=run,
    )
    leg = SimpleNamespace(
        id=30,
        ticket_id=40,
        model_prediction_id=20,
        match_id=10,
        selection="home",
        market="1x2",
        odds=2.0,
        bookmaker="Getsbet",
        prediction_run_id_snapshot=2,
        model_probability_snapshot=0.5,
        market_probability_snapshot=0.48,
        market_probability_basis_snapshot="consensus_de_vig",
        expected_value_snapshot=0.1,
        edge_pct_snapshot=10.0,
        reliability_label_snapshot="moderate",
        reliability_score_snapshot=72.0,
        status="pending",
        created_at=now,
        match=match,
        model_prediction=prediction,
    )
    ticket = SimpleNamespace(
        id=40,
        user_id=1,
        bankroll_id=None,
        batch_id=5,
        ticket_type="single",
        stake=10.0,
        total_odds=2.0,
        potential_return=20.0,
        status="open",
        created_at=now,
        updated_at=now,
        legs=[leg],
        placements=[],
    )
    return now, run, ticket


def test_ticket_lineage_serializer_includes_prediction_and_run():
    _now, run, ticket = _objects()

    response = _serialize_ticket_lineage(ticket)

    assert response.legs[0].prediction.id == 20
    assert response.legs[0].run.id == run.id
    assert response.legs[0].match["home_team"] == "Home FC"
    assert response.legs[0].prediction_run_id_snapshot == 2
    assert response.legs[0].model_probability_snapshot == 0.5
    assert response.legs[0].market_probability_snapshot == 0.48
    assert response.legs[0].expected_value_snapshot == 0.1
    assert response.legs[0].reliability_label_snapshot == "moderate"


class _Result:
    def __init__(self, *, scalar=None, values=()):
        self.scalar = scalar
        self.values = list(values)

    def unique(self):
        return self

    def scalar_one_or_none(self):
        return self.scalar

    def scalars(self):
        return self

    def all(self):
        return self.values


class _Db:
    def __init__(self, results):
        self.results = list(results)

    async def execute(self, _statement):
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_ticket_batch_lineage_is_owner_scoped_and_returns_source_runs():
    now, run, ticket = _objects()
    batch = SimpleNamespace(
        id=5,
        bankroll_id=None,
        source_prediction_run_id=2,
        source_prediction_run_ids=[2],
        name="Australia 17 July",
        strategy="value",
        tickets_count=1,
        total_stake=10.0,
        generation_report={"prediction_run_ids": [2]},
        created_at=now,
        tickets=[ticket],
    )
    strategy = SimpleNamespace(id=4, name="Poisson Standard")
    db = _Db([_Result(scalar=batch), _Result(values=[run]), _Result(values=[strategy])])

    response = await get_ticket_batch_lineage(batch_id=5, db=db, user=SimpleNamespace(id=1))

    assert response.source_prediction_run_ids == [2]
    assert response.source_runs[0].strategy_name == "Poisson Standard"
    assert response.tickets[0].legs[0].prediction.id == 20


@pytest.mark.asyncio
async def test_ticket_batch_lineage_hides_missing_or_foreign_batch():
    db = _Db([_Result(scalar=None)])

    with pytest.raises(HTTPException) as error:
        await get_ticket_batch_lineage(batch_id=999, db=db, user=SimpleNamespace(id=1))

    assert error.value.status_code == 404
