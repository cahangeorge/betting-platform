"""Closing-line-value calculations with explicit data-availability reasons."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

REFERENCE_PRICE_UNAVAILABLE = "reference_price_unavailable"
REFERENCE_PRICE_INVALID = "reference_price_invalid"
CLOSING_SAME_BOOK_UNAVAILABLE = "closing_same_book_unavailable"
CLOSING_SAME_BOOK_INVALID = "closing_same_book_invalid"
CLOSING_MARKET_UNAVAILABLE = "closing_market_unavailable"
CLOSING_MARKET_INVALID = "closing_market_invalid"
REFERENCE_MARKET_PROBABILITY_UNAVAILABLE = "reference_market_probability_unavailable"
REFERENCE_MARKET_PROBABILITY_INVALID = "reference_market_probability_invalid"
CLOSING_CONSENSUS_UNAVAILABLE = "closing_consensus_unavailable"
CLOSING_CONSENSUS_INVALID = "closing_consensus_invalid"


@dataclass(frozen=True, slots=True)
class ClvMetrics:
    same_book_clv_pct: float | None
    market_best_clv_pct: float | None
    consensus_clv_pp: float | None
    unavailable_reasons: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def coverage(self) -> dict[str, bool]:
        return {
            "same_book": self.same_book_clv_pct is not None,
            "market_best": self.market_best_clv_pct is not None,
            "consensus": self.consensus_clv_pp is not None,
        }


def _valid_price(value: float | None) -> bool:
    return value is not None and isfinite(float(value)) and float(value) > 1.0


def _valid_probability(value: float | None) -> bool:
    return value is not None and isfinite(float(value)) and 0.0 < float(value) < 1.0


def same_book_clv_pct(reference_price: float, closing_price: float) -> float:
    if not _valid_price(reference_price) or not _valid_price(closing_price):
        raise ValueError("CLV prices must be greater than 1.0")
    return 100.0 * (float(reference_price) / float(closing_price) - 1.0)


def market_best_clv_pct(reference_price: float, closing_price: float) -> float:
    if not _valid_price(reference_price) or not _valid_price(closing_price):
        raise ValueError("CLV prices must be greater than 1.0")
    return 100.0 * (float(reference_price) / float(closing_price) - 1.0)


def consensus_clv_pp(reference_market_probability: float, closing_consensus_probability: float) -> float:
    if not _valid_probability(reference_market_probability) or not _valid_probability(closing_consensus_probability):
        raise ValueError("CLV probabilities must be strictly between 0 and 1")
    return 100.0 * (float(closing_consensus_probability) - float(reference_market_probability))


def calculate_clv(
    *,
    reference_price: float | None,
    same_book_closing_price: float | None = None,
    market_best_closing_price: float | None = None,
    reference_market_probability: float | None = None,
    closing_consensus_probability: float | None = None,
) -> ClvMetrics:
    """Calculate each CLV dimension independently.

    Missing data is not coerced to zero: each unavailable metric carries a
    stable reason code suitable for APIs, dashboards, and coverage reports.
    """

    unavailable: dict[str, tuple[str, ...]] = {}
    reference_ok = _valid_price(reference_price)

    if reference_price is None:
        reference_reason = REFERENCE_PRICE_UNAVAILABLE
    elif not reference_ok:
        reference_reason = REFERENCE_PRICE_INVALID
    else:
        reference_reason = ""

    same_book: float | None = None
    same_reasons: list[str] = []
    if reference_reason:
        same_reasons.append(reference_reason)
    if same_book_closing_price is None:
        same_reasons.append(CLOSING_SAME_BOOK_UNAVAILABLE)
    elif not _valid_price(same_book_closing_price):
        same_reasons.append(CLOSING_SAME_BOOK_INVALID)
    if not same_reasons:
        same_book = same_book_clv_pct(float(reference_price), float(same_book_closing_price))
    else:
        unavailable["same_book"] = tuple(same_reasons)

    market_best: float | None = None
    market_reasons: list[str] = []
    if reference_reason:
        market_reasons.append(reference_reason)
    if market_best_closing_price is None:
        market_reasons.append(CLOSING_MARKET_UNAVAILABLE)
    elif not _valid_price(market_best_closing_price):
        market_reasons.append(CLOSING_MARKET_INVALID)
    if not market_reasons:
        market_best = market_best_clv_pct(float(reference_price), float(market_best_closing_price))
    else:
        unavailable["market_best"] = tuple(market_reasons)

    consensus: float | None = None
    consensus_reasons: list[str] = []
    if reference_market_probability is None:
        consensus_reasons.append(REFERENCE_MARKET_PROBABILITY_UNAVAILABLE)
    elif not _valid_probability(reference_market_probability):
        consensus_reasons.append(REFERENCE_MARKET_PROBABILITY_INVALID)
    if closing_consensus_probability is None:
        consensus_reasons.append(CLOSING_CONSENSUS_UNAVAILABLE)
    elif not _valid_probability(closing_consensus_probability):
        consensus_reasons.append(CLOSING_CONSENSUS_INVALID)
    if not consensus_reasons:
        consensus = consensus_clv_pp(float(reference_market_probability), float(closing_consensus_probability))
    else:
        unavailable["consensus"] = tuple(consensus_reasons)

    return ClvMetrics(
        same_book_clv_pct=same_book,
        market_best_clv_pct=market_best,
        consensus_clv_pp=consensus,
        unavailable_reasons=unavailable,
    )
