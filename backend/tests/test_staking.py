from decimal import Decimal

import pytest

from app.services.staking import (
    StakeCalculation,
    StakingError,
    StakingMode,
    StakingPolicy,
    calculate_stake,
    full_kelly_fraction,
)


def test_staking_policy_requires_an_explicit_mode_configuration():
    with pytest.raises(TypeError):
        StakingPolicy()  # type: ignore[call-arg]

    with pytest.raises(StakingError) as error:
        StakingPolicy(mode="flat_percent", flat_stake_percent=None, kelly_fraction=None)
    assert error.value.code == "invalid_staking_policy"


@pytest.mark.parametrize("percent", ["5.01", "100"])
def test_flat_policy_cannot_exceed_the_five_percent_platform_cap(percent):
    with pytest.raises(StakingError) as error:
        StakingPolicy(mode="flat_percent", flat_stake_percent=percent, kelly_fraction=None)
    assert error.value.code == "invalid_staking_policy"


def test_fractional_kelly_policy_is_capped_at_half_kelly():
    with pytest.raises(StakingError) as error:
        StakingPolicy(mode="fractional_kelly", flat_stake_percent=None, kelly_fraction="0.5001")
    assert error.value.code == "invalid_staking_policy"


def test_flat_percent_stake_is_decimal_safe_and_rounded_down_to_currency_precision():
    result = calculate_stake(
        policy=StakingPolicy(mode="flat_percent", flat_stake_percent="1.25", kelly_fraction=None),
        bankroll_amount=1000.99,
        ticket_format="single",
        ticket_limit_percent="5",
    )

    assert result == StakeCalculation(
        eligible=True,
        mode=StakingMode.FLAT_PERCENT,
        stake=Decimal("12.51"),
        stake_percent=Decimal("1.25"),
        full_kelly_fraction=None,
        applied_kelly_fraction=None,
        reason_code=None,
    )


def test_fractional_kelly_calculation_uses_model_edge_for_a_single():
    result = calculate_stake(
        policy=StakingPolicy(mode="fractional_kelly", flat_stake_percent=None, kelly_fraction="0.5"),
        bankroll_amount="1000",
        ticket_format="single",
        ticket_limit_percent="5",
        model_probability="0.55",
        decimal_odds="2.0",
    )

    assert full_kelly_fraction(model_probability="0.55", decimal_odds="2") == Decimal("0.10")
    assert result.eligible is True
    assert result.stake == Decimal("50.00")
    assert result.stake_percent == Decimal("5.000")
    assert result.full_kelly_fraction == Decimal("0.10")
    assert result.applied_kelly_fraction == Decimal("0.050")


def test_fractional_kelly_returns_no_bet_when_edge_is_not_positive():
    result = calculate_stake(
        policy=StakingPolicy(mode="fractional_kelly", flat_stake_percent=None, kelly_fraction="0.25"),
        bankroll_amount="1000",
        ticket_format="single",
        ticket_limit_percent="5",
        model_probability="0.40",
        decimal_odds="2.0",
    )

    assert result.eligible is False
    assert result.stake == Decimal("0.00")
    assert result.reason_code == "no_positive_edge"


def test_kelly_is_rejected_for_accumulators():
    with pytest.raises(StakingError) as error:
        calculate_stake(
            policy=StakingPolicy(mode="fractional_kelly", flat_stake_percent=None, kelly_fraction="0.25"),
            bankroll_amount="1000",
            ticket_format="double",
            ticket_limit_percent="5",
            model_probability="0.55",
            decimal_odds="2.0",
        )
    assert error.value.code == "kelly_single_only"


def test_calculated_stake_above_policy_limit_is_rejected_not_silently_clipped():
    with pytest.raises(StakingError) as error:
        calculate_stake(
            policy=StakingPolicy(mode="flat_percent", flat_stake_percent="3", kelly_fraction=None),
            bankroll_amount="1000",
            ticket_format="single",
            ticket_limit_percent="2",
        )
    assert error.value.code == "ticket_stake_policy_limit_exceeded"


@pytest.mark.parametrize("value", [float("inf"), float("nan"), "not-a-number"])
def test_non_finite_numeric_inputs_are_rejected(value):
    with pytest.raises(StakingError) as error:
        calculate_stake(
            policy=StakingPolicy(mode="flat_percent", flat_stake_percent="1", kelly_fraction=None),
            bankroll_amount=value,
            ticket_format="single",
            ticket_limit_percent="5",
        )
    assert error.value.code == "invalid_numeric_value"
