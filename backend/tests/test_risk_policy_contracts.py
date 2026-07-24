from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.risk import RiskPauseRequest, RiskPolicyWriteRequest
from app.services.risk_policy import _is_relaxation


def _payload(**overrides):
    payload = {
        "staking_mode": "flat_percent",
        "flat_stake_pct": "0.01",
        "kelly_fraction": None,
        "max_ticket_pct": "0.02",
        "max_open_exposure_pct": "0.10",
        "max_match_pct": "0.02",
        "max_team_pct": "0.04",
        "max_league_window_pct": "0.05",
        "league_window_hours": 6,
        "max_daily_stake_pct": "0.05",
        "max_weekly_stake_pct": "0.15",
        "max_daily_ticket_count": 10,
        "max_weekly_ticket_count": 40,
        "accumulators_enabled": False,
        "automation_enabled": False,
    }
    payload.update(overrides)
    return payload


def test_policy_has_no_defaults_and_enforces_platform_caps():
    with pytest.raises(ValidationError):
        RiskPolicyWriteRequest()
    with pytest.raises(ValidationError):
        RiskPolicyWriteRequest.model_validate(_payload(max_ticket_pct="0.051"))
    with pytest.raises(ValidationError):
        RiskPolicyWriteRequest.model_validate(_payload(max_open_exposure_pct="0.201"))


def test_policy_requires_matching_staking_fields_and_coherent_limits():
    with pytest.raises(ValidationError):
        RiskPolicyWriteRequest.model_validate(_payload(flat_stake_pct=None))
    with pytest.raises(ValidationError):
        RiskPolicyWriteRequest.model_validate(_payload(max_match_pct="0.11"))
    with pytest.raises(ValidationError):
        RiskPolicyWriteRequest.model_validate(
            _payload(staking_mode="fractional_kelly", flat_stake_pct=None, kelly_fraction="0.51")
        )


def test_policy_wire_percentages_are_decimal_fractions():
    policy = RiskPolicyWriteRequest.model_validate(_payload())
    assert policy.flat_stake_pct == Decimal("0.01")
    assert policy.max_ticket_pct == Decimal("0.02")
    assert policy.max_open_exposure_pct == Decimal("0.10")


def test_relaxations_are_detected_for_cooldown():
    current = SimpleNamespace(**RiskPolicyWriteRequest.model_validate(_payload()).model_dump())
    relaxed = RiskPolicyWriteRequest.model_validate(_payload(max_open_exposure_pct="0.11"))
    tightened = RiskPolicyWriteRequest.model_validate(_payload(max_open_exposure_pct="0.09"))
    enabled = RiskPolicyWriteRequest.model_validate(_payload(automation_enabled=True))
    shorter_league_window = RiskPolicyWriteRequest.model_validate(_payload(league_window_hours=4))
    longer_league_window = RiskPolicyWriteRequest.model_validate(_payload(league_window_hours=8))

    assert _is_relaxation(current, relaxed)
    assert not _is_relaxation(current, tightened)
    assert _is_relaxation(current, enabled)
    assert _is_relaxation(current, shorter_league_window)
    assert not _is_relaxation(current, longer_league_window)


def test_pause_timestamp_must_be_timezone_aware():
    now = datetime.now(timezone.utc)
    assert RiskPauseRequest(paused_until=now + timedelta(days=1)).paused_until.tzinfo is not None
    with pytest.raises(ValidationError):
        RiskPauseRequest(paused_until=datetime.now() + timedelta(days=1))
