from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import tickets as tickets_api
from app.schemas.ticket import TicketPreflightRequest
from app.services import ticket_engine
from app.services.ticket_engine import preflight_ticket_generation


class _Result:
    def __init__(self, *, scalar=None, values=()):
        self._scalar = scalar
        self._values = list(values)

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._values


class _ReadOnlyDb:
    def __init__(self, run, predictions):
        self._results = [_Result(scalar=run), _Result(values=predictions)]
        self.writes = 0

    async def execute(self, _statement):
        return self._results.pop(0)

    def add(self, *_args, **_kwargs):
        self.writes += 1


def _run():
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=101,
        user_id=7,
        source_dataset_id=55,
        status="completed",
        completed_at=now,
        started_at=now,
        created_at=now,
        input_hash="hash",
    )


def _prediction(index: int):
    now = datetime.now(timezone.utc)
    match = SimpleNamespace(
        id=1000 + index,
        match_date=now + timedelta(days=3),
        status="scheduled",
        home_team=f"Home {index}",
        away_team=f"Away {index}",
    )
    return SimpleNamespace(
        id=2000 + index,
        run_id=101,
        match_id=match.id,
        market="1x2",
        model_type="PoissonGoalsModel",
        home_prob=0.6,
        draw_prob=0.2,
        away_prob=0.2,
        home_odds=2.0,
        draw_odds=3.0,
        away_odds=4.0,
        expected_value=0.2,
        created_at=now,
        match=match,
        quality_report={
            "model": {"pick": "home"},
            "market": {"odds": {"home": {"odds": 2.0, "bookmaker": "TestBook"}}},
            "reliability": {"is_ticket_eligible": True},
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("match_count", [1, 2, 3])
async def test_preflight_reports_all_risk_tiers_without_writes(match_count):
    db = _ReadOnlyDb(_run(), [_prediction(index) for index in range(match_count)])

    response = await preflight_ticket_generation(
        db,
        user_id=7,
        run_id=101,
        run_ids=None,
        prediction_ids=None,
        market_types=["1x2"],
        min_odds=1.01,
        max_odds=100,
    )

    risks = {risk["difficulty"]: risk for risk in response["risks"]}
    assert set(risks) == {"safe", "low", "balanced", "medium", "aggressive", "high"}
    assert risks["safe"]["can_generate"] is True
    assert risks["balanced"]["can_generate"] is (match_count >= 2)
    assert risks["aggressive"]["can_generate"] is (match_count >= 3)
    assert response["eligible_unique_matches"] == match_count
    assert response["source_prediction_run_ids"] == [101]
    assert db.writes == 0


@pytest.mark.asyncio
async def test_preflight_rejects_foreign_run_before_prediction_query():
    db = _ReadOnlyDb(None, [])

    with pytest.raises(ValueError, match="not found or not eligible"):
        await preflight_ticket_generation(
            db,
            user_id=7,
            run_id=999,
            run_ids=None,
            prediction_ids=None,
            market_types=["1x2"],
            min_odds=1.01,
            max_odds=100,
        )
    assert db.writes == 0
    assert db._results  # Prediction rows were not queried after ownership failure.


@pytest.mark.asyncio
async def test_preflight_fails_closed_when_versioned_run_is_not_governed_for_manual_use(monkeypatch):
    async def blocked_governance(*_args, **_kwargs):
        return {
            "allowed": False,
            "mode": "manual",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runs": [
                {
                    "run_id": 101,
                    "model_version_id": 9,
                    "allowed": False,
                    "reason": "certification_missing_or_expired",
                }
            ],
            "model_evaluation_ids": [],
        }

    monkeypatch.setattr(ticket_engine, "assess_prediction_runs_governance", blocked_governance)
    db = _ReadOnlyDb(_run(), [_prediction(1)])

    response = await preflight_ticket_generation(
        db,
        user_id=7,
        run_id=101,
        run_ids=None,
        prediction_ids=None,
        market_types=["1x2"],
        min_odds=1.01,
        max_odds=100,
    )

    assert response["governance_assessment"]["allowed"] is False
    assert response["risk_assessment"]["allowed"] is False
    assert response["risk_assessment"]["blockers"][0]["code"] == "model_governance_manual_blocked"
    assert all(risk["can_generate"] is False for risk in response["risks"])


def test_preflight_request_requires_explicit_run_and_valid_odds():
    with pytest.raises(ValidationError):
        TicketPreflightRequest()
    with pytest.raises(ValidationError):
        TicketPreflightRequest(run_id=1, min_odds=3, max_odds=2)
    with pytest.raises(ValidationError):
        TicketPreflightRequest(run_id=1, run_ids=[2])


@pytest.mark.asyncio
async def test_preflight_endpoint_maps_validation_error_without_mutation(monkeypatch):
    async def fake_preflight(**_kwargs):
        raise ValueError("Prediction run 99 not found or not eligible for ticket generation")

    monkeypatch.setattr(tickets_api, "preflight_ticket_generation", fake_preflight)
    body = TicketPreflightRequest(run_id=99)

    with pytest.raises(HTTPException) as error:
        await tickets_api.preflight_ticket_batch(body=body, db=object(), user=SimpleNamespace(id=7))

    assert error.value.status_code == 400
