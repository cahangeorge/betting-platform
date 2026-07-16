"""Pure, Decimal-safe stake calculations for paper ticket generation.

The module deliberately has no database or ORM dependencies.  Persistence and
portfolio exposure checks belong to :mod:`app.services.portfolio_risk`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from enum import StrEnum
from math import isfinite
from typing import TypeAlias

DecimalInput: TypeAlias = Decimal | int | float | str

MONEY_QUANTUM = Decimal("0.01")
HARD_MAX_TICKET_PERCENT = Decimal("5")
MAX_KELLY_FRACTION = Decimal("0.5")
ONE_HUNDRED = Decimal("100")


class StakingMode(StrEnum):
    FLAT_PERCENT = "flat_percent"
    FRACTIONAL_KELLY = "fractional_kelly"


class StakingError(ValueError):
    """A stable, machine-readable staking validation error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def to_decimal(value: DecimalInput, *, field: str) -> Decimal:
    """Convert user/database numeric input without introducing float noise."""

    if isinstance(value, bool):
        raise StakingError("invalid_numeric_value", f"{field} must be a finite number")
    if isinstance(value, float) and not isfinite(value):
        raise StakingError("invalid_numeric_value", f"{field} must be a finite number")
    try:
        converted = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise StakingError("invalid_numeric_value", f"{field} must be a finite number") from exc
    if not converted.is_finite():
        raise StakingError("invalid_numeric_value", f"{field} must be a finite number")
    return converted


def quantize_money(value: DecimalInput) -> Decimal:
    """Round down to currency precision so a calculated stake never exceeds a cap."""

    return to_decimal(value, field="money").quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)


def _positive_percent(value: DecimalInput, *, field: str, maximum: Decimal) -> Decimal:
    percent = to_decimal(value, field=field)
    if percent <= 0 or percent > maximum:
        raise StakingError(
            "invalid_staking_policy",
            f"{field} must be greater than 0 and no greater than {maximum}",
        )
    return percent


@dataclass(frozen=True, slots=True)
class StakingPolicy:
    """Explicit staking configuration; there are intentionally no defaults."""

    mode: StakingMode | str
    flat_stake_percent: DecimalInput | None
    kelly_fraction: DecimalInput | None

    def __post_init__(self) -> None:
        try:
            mode = self.mode if isinstance(self.mode, StakingMode) else StakingMode(self.mode)
        except ValueError as exc:
            raise StakingError("invalid_staking_policy", f"Unsupported staking mode: {self.mode}") from exc
        object.__setattr__(self, "mode", mode)

        if mode is StakingMode.FLAT_PERCENT:
            if self.flat_stake_percent is None or self.kelly_fraction is not None:
                raise StakingError(
                    "invalid_staking_policy",
                    "flat_percent requires flat_stake_percent and forbids kelly_fraction",
                )
            object.__setattr__(
                self,
                "flat_stake_percent",
                _positive_percent(
                    self.flat_stake_percent,
                    field="flat_stake_percent",
                    maximum=HARD_MAX_TICKET_PERCENT,
                ),
            )
            return

        if self.kelly_fraction is None or self.flat_stake_percent is not None:
            raise StakingError(
                "invalid_staking_policy",
                "fractional_kelly requires kelly_fraction and forbids flat_stake_percent",
            )
        object.__setattr__(
            self,
            "kelly_fraction",
            _positive_percent(
                self.kelly_fraction,
                field="kelly_fraction",
                maximum=MAX_KELLY_FRACTION,
            ),
        )


@dataclass(frozen=True, slots=True)
class StakeCalculation:
    eligible: bool
    mode: StakingMode
    stake: Decimal
    stake_percent: Decimal
    full_kelly_fraction: Decimal | None
    applied_kelly_fraction: Decimal | None
    reason_code: str | None


def full_kelly_fraction(*, model_probability: DecimalInput, decimal_odds: DecimalInput) -> Decimal:
    """Return the full Kelly bankroll fraction, floored at zero."""

    probability = to_decimal(model_probability, field="model_probability")
    odds = to_decimal(decimal_odds, field="decimal_odds")
    if probability <= 0 or probability >= 1:
        raise StakingError("invalid_probability", "model_probability must be strictly between 0 and 1")
    if odds <= 1:
        raise StakingError("invalid_odds", "decimal_odds must be greater than 1")

    net_odds = odds - 1
    fraction = ((odds * probability) - 1) / net_odds
    return max(Decimal("0"), fraction)


def calculate_stake(
    *,
    policy: StakingPolicy,
    bankroll_amount: DecimalInput,
    ticket_format: str,
    ticket_limit_percent: DecimalInput,
    model_probability: DecimalInput | None = None,
    decimal_odds: DecimalInput | None = None,
) -> StakeCalculation:
    """Calculate a paper stake without silently clipping it to a risk limit.

    ``ticket_limit_percent`` is the explicit per-ticket limit from the risk
    policy.  It can be lower than the platform hard cap, never higher.  A
    calculation above that limit is rejected rather than resized.
    """

    bankroll = to_decimal(bankroll_amount, field="bankroll_amount")
    if bankroll <= 0:
        raise StakingError("invalid_bankroll", "bankroll_amount must be greater than 0")
    limit_percent = _positive_percent(
        ticket_limit_percent,
        field="ticket_limit_percent",
        maximum=HARD_MAX_TICKET_PERCENT,
    )
    normalized_format = ticket_format.strip().lower()
    if normalized_format not in {"single", "double", "treble"}:
        raise StakingError("invalid_ticket_format", f"Unsupported ticket format: {ticket_format}")

    kelly = None
    applied_kelly = None
    if policy.mode is StakingMode.FLAT_PERCENT:
        stake_percent = policy.flat_stake_percent
        assert stake_percent is not None  # Guaranteed by StakingPolicy validation.
    else:
        if normalized_format != "single":
            raise StakingError("kelly_single_only", "fractional_kelly is allowed only for single tickets")
        if model_probability is None or decimal_odds is None:
            raise StakingError(
                "kelly_inputs_required",
                "fractional_kelly requires model_probability and decimal_odds",
            )
        kelly = full_kelly_fraction(model_probability=model_probability, decimal_odds=decimal_odds)
        if kelly == 0:
            return StakeCalculation(
                eligible=False,
                mode=policy.mode,
                stake=Decimal("0.00"),
                stake_percent=Decimal("0"),
                full_kelly_fraction=kelly,
                applied_kelly_fraction=Decimal("0"),
                reason_code="no_positive_edge",
            )
        assert policy.kelly_fraction is not None  # Guaranteed by StakingPolicy validation.
        applied_kelly = kelly * policy.kelly_fraction
        stake_percent = applied_kelly * ONE_HUNDRED

    if stake_percent > limit_percent:
        raise StakingError(
            "ticket_stake_policy_limit_exceeded",
            "Calculated stake exceeds the configured per-ticket limit; it was not resized",
        )

    stake = quantize_money(bankroll * stake_percent / ONE_HUNDRED)
    if stake <= 0:
        return StakeCalculation(
            eligible=False,
            mode=policy.mode,
            stake=Decimal("0.00"),
            stake_percent=stake_percent,
            full_kelly_fraction=kelly,
            applied_kelly_fraction=applied_kelly,
            reason_code="stake_below_currency_unit",
        )

    return StakeCalculation(
        eligible=True,
        mode=policy.mode,
        stake=stake,
        stake_percent=stake_percent,
        full_kelly_fraction=kelly,
        applied_kelly_fraction=applied_kelly,
        reason_code=None,
    )
