from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.providers.odds import OddsEventObservationV1, OddsQuoteV1, validate_odds_event_payload


def _quote(**overrides):
    values = {
        "source_quote_id": "quote-1",
        "provider_bookmaker_key": "book-7",
        "provider_bookmaker_name": "Book Seven",
        "provider_market_key": "market-1",
        "market_key": "1x2",
        "period_key": "full_time",
        "line": None,
        "selection_key": "home",
        "selection_name": "Home",
        "price": "2.10",
        "provider_updated_at": datetime(2026, 8, 3, 11, 59, tzinfo=UTC),
        "status": "active",
    }
    values.update(overrides)
    return OddsQuoteV1(**values)


def _event(*quotes, **overrides):
    values = {
        "source_event_id": "fixture-42",
        "sport_key": "football",
        "competition_key": "england-premier-league",
        "commence_time": datetime(2026, 8, 3, 12, tzinfo=UTC),
        "home_team": "Team A",
        "away_team": "Team B",
        "observed_at": datetime(2026, 8, 3, 11, 59, tzinfo=UTC),
        "scope": "prematch",
        "quality": "complete",
        "quotes": tuple(quotes or (_quote(),)),
        "expected_bookmaker_count": 1,
        "expected_market_count": 1,
    }
    values.update(overrides)
    return OddsEventObservationV1(**values)


def test_contract_allows_one_bookmaker_to_quote_multiple_selections():
    event = _event(
        _quote(),
        _quote(source_quote_id="quote-2", selection_key="draw", selection_name="Draw", price="3.20"),
        _quote(source_quote_id="quote-3", selection_key="away", selection_name="Away", price="4.00"),
    )
    assert len(event.quotes) == 3


def test_quote_identity_includes_bookmaker_market_period_line_and_selection():
    quote = _quote(line="2.5", market_key="totals", selection_key="over")
    assert quote.identity == ("book-7", "totals", "full_time", "2.5", "over")
    assert len(quote.identity_digest) == 64


def test_contract_rejects_duplicate_quote_identity_even_when_source_ids_differ():
    with pytest.raises(ValueError, match="duplicate quote identities"):
        _event(_quote(), _quote(source_quote_id="other", price="2.20"))


def test_contract_canonical_payload_and_digest_ignore_input_quote_order():
    first = _quote()
    second = _quote(source_quote_id="q2", provider_bookmaker_key="book-8", provider_bookmaker_name="Book 8")
    left, right = _event(first, second), _event(second, first)
    assert left.payload == right.payload
    assert left.payload_digest == right.payload_digest
    assert left.payload["quotes"][0]["price"] == "2.1"


def test_contract_rejects_naive_time_nonfinite_or_bounded_price():
    with pytest.raises(ValueError, match="timezone-aware"):
        _quote(provider_updated_at=datetime(2026, 8, 3, 12))
    with pytest.raises(ValueError, match="greater than"):
        _quote(price="NaN")
    with pytest.raises(ValueError, match="supported bound"):
        _quote(price="1000001")


def test_partial_observation_may_be_empty_but_complete_may_not():
    assert _event(quality="partial", quotes=()).quotes == ()
    with pytest.raises(ValueError, match="at least one quote"):
        _event(quotes=())


def test_parser_requires_exact_fields_and_round_trips():
    event = _event()
    restored = validate_odds_event_payload(event.payload)
    assert restored == event
    extra = deepcopy(event.payload)
    extra["api_key"] = "must-never-be-accepted"
    with pytest.raises(ValueError, match="exact v1 fields"):
        validate_odds_event_payload(extra)


def test_parser_rejects_extra_quote_fields_and_bool_counts():
    payload = deepcopy(_event().payload)
    payload["quotes"][0]["headers"] = {"Authorization": "secret"}
    with pytest.raises(ValueError, match="exact v1 fields"):
        validate_odds_event_payload(payload)
    with pytest.raises(ValueError, match="bounded nonnegative"):
        _event(expected_market_count=True)


def test_teams_must_differ_and_versions_are_strict():
    with pytest.raises(ValueError, match="must differ"):
        _event(away_team=" team a ")
    with pytest.raises(ValueError, match="Unsupported"):
        _event(contract_version="odds-observation/v2")


def test_decimal_line_and_price_are_exact_not_float_storage():
    quote = _quote(line=Decimal("-1.50"), price=Decimal("1.9500"))
    assert quote.line == Decimal("-1.5")
    assert quote.price == Decimal("1.95")
