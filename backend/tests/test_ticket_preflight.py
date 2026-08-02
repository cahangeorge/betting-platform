from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import tickets as tickets_api
from app.schemas.ticket import TicketPreflightRequest
from app.services import ticket_engine
from app.services.portfolio_risk import (
    LeagueExposure,
    PortfolioExposure,
    RiskCandidate,
    RiskContext,
    RiskPolicy,
    assess_portfolio_risk,
)
from app.services.staking import StakingPolicy
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
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement.compile(compile_kwargs={"literal_binds": True})))
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


def test_governed_ticket_candidate_uses_pinned_fixture_after_match_mutation():
    now = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
    prediction = _prediction(1)
    prediction.quality_report.update(
        {
            "pipeline_contract_version": "penaltyblog-model-pipeline/v1",
            "canonical_fixture": {
                "match_id": prediction.match_id,
                "home_team": "Pinned Home",
                "away_team": "Pinned Away",
                "kickoff_at": (now + timedelta(hours=2)).isoformat(),
                "competition_key": "Canonical League",
            },
        }
    )
    prediction.match.home_team = "Mutable Home"
    prediction.match.away_team = "Mutable Away"
    prediction.match.match_date = now - timedelta(hours=1)
    prediction.match.competition = "Mutable League"

    candidate, reason = ticket_engine._prediction_ticket_exclusion_reason(
        prediction, normalized_markets={"1x2"}, min_odds=1.01, max_odds=100, now=now
    )

    assert reason is None
    assert candidate is not None
    assert candidate["kickoff"] == now + timedelta(hours=2)
    assert candidate["team_ids"] == ("Pinned Home", "Pinned Away")
    assert candidate["league_ids"] == ("Canonical League",)
    assessment = assess_portfolio_risk(
        policy=RiskPolicy(
            version="p4-canonical-league",
            staking=StakingPolicy(mode="flat_percent", flat_stake_percent="1", kelly_fraction=None),
            max_ticket_percent="5",
            max_open_exposure_percent="20",
            max_daily_stake_percent="10",
            max_weekly_stake_percent="30",
            max_daily_ticket_count=10,
            max_weekly_ticket_count=50,
            max_match_exposure_percent="10",
            max_team_exposure_percent="10",
            max_league_window_exposure_percent="15",
            league_window_hours=6,
            accumulators_enabled=False,
            automation_enabled=False,
            paused_until=None,
        ),
        context=RiskContext(
            bankroll_amount="1000",
            available_balance="1000",
            exposure=PortfolioExposure(
                open_total="0",
                staked_last_24h="0",
                staked_last_7d="0",
                ticket_count_last_24h=0,
                ticket_count_last_7d=0,
                by_match={},
                by_team={},
                league_exposures=(
                    LeagueExposure(
                        exposure_id=1,
                        league_id="Canonical League",
                        kickoff=now + timedelta(hours=3),
                        stake="145",
                    ),
                ),
            ),
            now=now,
        ),
        candidate=RiskCandidate(
            stake="10",
            ticket_format="single",
            match_ids=frozenset({candidate["match_id"]}),
            team_ids=frozenset(candidate["team_ids"]),
            league_ids=frozenset(candidate["league_ids"]),
            league_kickoffs=ticket_engine._candidate_league_kickoffs([candidate]),
            accumulator_risk_acknowledged=False,
            is_automated=False,
        ),
    )
    assert "league_window_exposure_limit_exceeded" in assessment.blocker_codes

    prediction.quality_report["canonical_fixture"]["kickoff_at"] = (now - timedelta(minutes=1)).isoformat()
    candidate, reason = ticket_engine._prediction_ticket_exclusion_reason(
        prediction, normalized_markets={"1x2"}, min_odds=1.01, max_odds=100, now=now
    )
    assert candidate is None
    assert reason == "match_started_or_finished"


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
async def test_preflight_requires_a_completed_prediction_run():
    db = _ReadOnlyDb(None, [])

    with pytest.raises(ValueError, match="not found or not eligible"):
        await preflight_ticket_generation(
            db,
            user_id=7,
            run_id=101,
            run_ids=None,
            prediction_ids=None,
            market_types=["1x2"],
            min_odds=1.01,
            max_odds=100,
        )

    assert "prediction_runs.status = 'completed'" in db.statements[0]


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
