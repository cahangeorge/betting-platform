from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.portfolio_risk import (
    LeagueExposure,
    PortfolioExposure,
    RiskCandidate,
    RiskContext,
    RiskPolicy,
    RiskPolicyError,
    assess_portfolio_risk,
)
from app.services.staking import StakingPolicy

NOW = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)


def _policy(**overrides):
    values = {
        "version": "policy-v1",
        "staking": StakingPolicy(mode="flat_percent", flat_stake_percent="1", kelly_fraction=None),
        "max_ticket_percent": "5",
        "max_open_exposure_percent": "20",
        "max_daily_stake_percent": "10",
        "max_weekly_stake_percent": "30",
        "max_daily_ticket_count": 10,
        "max_weekly_ticket_count": 50,
        "max_match_exposure_percent": "10",
        "max_team_exposure_percent": "10",
        "max_league_window_exposure_percent": "15",
        "league_window_hours": 6,
        "accumulators_enabled": False,
        "automation_enabled": False,
        "paused_until": None,
    }
    values.update(overrides)
    return RiskPolicy(**values)


def _exposure(**overrides):
    values = {
        "open_total": "0",
        "staked_last_24h": "0",
        "staked_last_7d": "0",
        "ticket_count_last_24h": 0,
        "ticket_count_last_7d": 0,
        "by_match": {},
        "by_team": {},
        "league_exposures": (),
    }
    values.update(overrides)
    return PortfolioExposure(**values)


def _context(**overrides):
    values = {
        "bankroll_amount": "1000",
        "available_balance": "1000",
        "exposure": _exposure(),
        "now": NOW,
    }
    values.update(overrides)
    return RiskContext(**values)


def _candidate(**overrides):
    values = {
        "stake": "10",
        "ticket_format": "single",
        "match_ids": frozenset({101}),
        "team_ids": frozenset({1, 2}),
        "league_ids": frozenset({44}),
        "league_kickoffs": {44: (NOW + timedelta(hours=12),)},
        "accumulator_risk_acknowledged": False,
        "is_automated": False,
    }
    values.update(overrides)
    return RiskCandidate(**values)


def test_policy_is_required_and_no_default_policy_is_invented():
    assessment = assess_portfolio_risk(policy=None, context=_context(), candidate=_candidate())

    assert assessment.allowed is False
    assert assessment.policy_version is None
    assert assessment.blocker_codes == ("risk_policy_required",)


def test_explicit_policy_allows_a_ticket_within_every_limit():
    assessment = assess_portfolio_risk(policy=_policy(), context=_context(), candidate=_candidate())

    assert assessment.allowed is True
    assert assessment.policy_version == "policy-v1"
    assert assessment.blockers == ()
    assert assessment.warnings == ()


def test_policy_configuration_cannot_relax_platform_hard_caps():
    with pytest.raises(RiskPolicyError) as ticket_error:
        _policy(max_ticket_percent="5.01")
    assert ticket_error.value.code == "invalid_risk_policy"

    with pytest.raises(RiskPolicyError) as exposure_error:
        _policy(max_open_exposure_percent="20.01")
    assert exposure_error.value.code == "invalid_risk_policy"


def test_ticket_stake_over_five_percent_is_blocked_by_the_hard_cap():
    assessment = assess_portfolio_risk(
        policy=_policy(),
        context=_context(),
        candidate=_candidate(stake="50.01"),
    )

    assert "ticket_stake_hard_cap_exceeded" in assessment.blocker_codes
    finding = next(item for item in assessment.blockers if item.code == "ticket_stake_hard_cap_exceeded")
    assert finding.limit == Decimal("50.00")
    assert finding.projected == Decimal("50.01")


def test_projected_open_exposure_over_twenty_percent_is_blocked():
    context = _context(exposure=_exposure(open_total="190.01"))
    assessment = assess_portfolio_risk(policy=_policy(), context=context, candidate=_candidate(stake="10"))

    assert "open_exposure_hard_cap_exceeded" in assessment.blocker_codes
    finding = next(item for item in assessment.blockers if item.code == "open_exposure_hard_cap_exceeded")
    assert finding.current == Decimal("190.01")
    assert finding.projected == Decimal("200.01")
    assert finding.limit == Decimal("200.00")


def test_a_stricter_configured_ticket_limit_is_enforced_separately():
    assessment = assess_portfolio_risk(
        policy=_policy(max_ticket_percent="2"),
        context=_context(),
        candidate=_candidate(stake="25"),
    )

    assert assessment.blocker_codes == ("ticket_stake_policy_limit_exceeded",)


def test_rolling_count_and_concentration_limits_are_all_fail_closed():
    context = _context(
        exposure=_exposure(
            staked_last_24h="95",
            staked_last_7d="295",
            ticket_count_last_24h=10,
            ticket_count_last_7d=50,
            by_match={101: "95"},
            by_team={1: "95", 2: "0"},
            league_exposures=(
                LeagueExposure(
                    exposure_id=77,
                    league_id=44,
                    kickoff=NOW + timedelta(hours=10),
                    stake="145",
                ),
            ),
        )
    )

    assessment = assess_portfolio_risk(policy=_policy(), context=context, candidate=_candidate(stake="10"))

    assert set(assessment.blocker_codes) == {
        "daily_stake_limit_exceeded",
        "weekly_stake_limit_exceeded",
        "daily_ticket_count_exceeded",
        "weekly_ticket_count_exceeded",
        "match_exposure_limit_exceeded",
        "team_exposure_limit_exceeded",
        "league_window_exposure_limit_exceeded",
    }


def test_pause_and_automation_flags_are_enforced():
    assessment = assess_portfolio_risk(
        policy=_policy(paused_until=NOW + timedelta(days=1)),
        context=_context(),
        candidate=_candidate(is_automated=True),
    )

    assert set(assessment.blocker_codes) == {"responsible_gambling_pause_active", "automation_disabled"}


def test_accumulator_requires_enablement_acknowledgement_and_flat_staking():
    kelly = StakingPolicy(mode="fractional_kelly", flat_stake_percent=None, kelly_fraction="0.25")
    assessment = assess_portfolio_risk(
        policy=_policy(staking=kelly),
        context=_context(),
        candidate=_candidate(ticket_format="double"),
    )

    assert set(assessment.blocker_codes) == {
        "accumulators_disabled",
        "accumulator_acknowledgement_required",
        "accumulator_flat_staking_required",
    }


def test_enabled_acknowledged_flat_accumulator_can_pass():
    assessment = assess_portfolio_risk(
        policy=_policy(accumulators_enabled=True),
        context=_context(),
        candidate=_candidate(ticket_format="double", accumulator_risk_acknowledged=True),
    )

    assert assessment.allowed is True


def test_missing_entity_scope_blocks_because_concentration_cannot_be_evaluated():
    assessment = assess_portfolio_risk(
        policy=_policy(),
        context=_context(),
        candidate=_candidate(
            match_ids=frozenset(),
            team_ids=frozenset(),
            league_ids=frozenset(),
            league_kickoffs={},
        ),
    )

    assert set(assessment.blocker_codes) == {
        "risk_context_match_scope_required",
        "risk_context_team_scope_required",
        "risk_context_league_scope_required",
    }


def test_risk_context_requires_timezone_aware_clock_and_nonnegative_exposure():
    with pytest.raises(RiskPolicyError) as time_error:
        _context(now=datetime(2026, 7, 16, 10, 0))
    assert time_error.value.code == "invalid_risk_policy"

    with pytest.raises(RiskPolicyError) as exposure_error:
        _exposure(open_total="-0.01")
    assert exposure_error.value.code == "invalid_risk_context"


def test_league_exposure_outside_the_rolling_kickoff_window_is_not_counted():
    exposure = _exposure(
        league_exposures=(
            LeagueExposure(
                exposure_id=70,
                league_id=44,
                kickoff=NOW + timedelta(hours=1),
                stake="145",
            ),
        )
    )
    assessment = assess_portfolio_risk(
        policy=_policy(league_window_hours=6),
        context=_context(exposure=exposure),
        candidate=_candidate(league_kickoffs={44: (NOW + timedelta(hours=12),)}),
    )

    assert assessment.allowed is True
    assert "league_window_exposure_limit_exceeded" not in assessment.blocker_codes


def test_league_exposure_inside_the_rolling_kickoff_window_is_counted():
    exposure = _exposure(
        league_exposures=(
            LeagueExposure(
                exposure_id=70,
                league_id=44,
                kickoff=NOW + timedelta(hours=8),
                stake="145",
            ),
        )
    )
    assessment = assess_portfolio_risk(
        policy=_policy(league_window_hours=6),
        context=_context(exposure=exposure),
        candidate=_candidate(league_kickoffs={44: (NOW + timedelta(hours=12),)}),
    )

    finding = next(item for item in assessment.blockers if item.code == "league_window_exposure_limit_exceeded")
    assert finding.current == Decimal("145.00")
    assert finding.projected == Decimal("155.00")
    assert finding.limit == Decimal("150.00")


def test_league_window_is_half_open_at_the_exact_hour_boundary():
    exposure = _exposure(
        league_exposures=(
            LeagueExposure(
                exposure_id=70,
                league_id=44,
                kickoff=NOW + timedelta(hours=6),
                stake="145",
            ),
        )
    )
    assessment = assess_portfolio_risk(
        policy=_policy(league_window_hours=6),
        context=_context(exposure=exposure),
        candidate=_candidate(league_kickoffs={44: (NOW + timedelta(hours=12),)}),
    )

    assert assessment.allowed is True


def test_multiple_legs_from_one_existing_ticket_are_deduplicated_in_a_window():
    exposure = _exposure(
        league_exposures=(
            LeagueExposure(
                exposure_id=70,
                league_id=44,
                kickoff=NOW + timedelta(hours=8),
                stake="75",
            ),
            LeagueExposure(
                exposure_id=70,
                league_id=44,
                kickoff=NOW + timedelta(hours=9),
                stake="75",
            ),
        )
    )
    assessment = assess_portfolio_risk(
        policy=_policy(max_league_window_exposure_percent="10", league_window_hours=6),
        context=_context(exposure=exposure),
        candidate=_candidate(league_kickoffs={44: (NOW + timedelta(hours=12),)}),
    )

    assert assessment.allowed is True


def test_candidate_league_without_kickoff_fails_closed():
    assessment = assess_portfolio_risk(
        policy=_policy(),
        context=_context(),
        candidate=_candidate(league_kickoffs={}),
    )

    assert "risk_context_league_kickoff_required" in assessment.blocker_codes
