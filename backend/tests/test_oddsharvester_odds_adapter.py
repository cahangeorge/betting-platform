from __future__ import annotations

from copy import deepcopy

import pytest

from app.providers.oddsharvester_odds import (
    ODDSHARVESTER_ADAPTER_KEY,
    ODDSHARVESTER_SOURCE_KEY,
    convert_oddsharvester_record,
    oddsharvester_record_envelope,
)


def _record() -> dict:
    return {
        "scraped_date": "2026-02-02 09:31:16 UTC",
        "match_date": "2026-02-03 20:00:00 UTC",
        "match_link": "https://www.oddsportal.com/football/england/premier-league/arsenal-chelsea-AbC123xy/",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "league_name": "Premier League 2025/2026",
        "1x2_market": [{"1": "1.90", "X": "3.50", "2": "4.20", "bookmaker_name": "Book Maker", "period": "FullTime"}],
        "over_under_2_5_market": [
            {"odds_over": "1.91", "odds_under": "1.95", "bookmaker_name": "Book Maker", "period": "FullTime"}
        ],
    }


def test_converts_real_oddsharvester_shape_to_row_per_selection_contract():
    observation = convert_oddsharvester_record(_record())

    assert observation.source_event_id == "arsenal-chelsea-AbC123xy"
    assert observation.quality == "complete"
    assert observation.expected_bookmaker_count == 1
    assert observation.expected_market_count == 2
    assert len(observation.quotes) == 5
    assert {quote.market_key for quote in observation.quotes} == {"1x2", "totals"}
    totals = [quote for quote in observation.quotes if quote.market_key == "totals"]
    assert {str(quote.line) for quote in totals} == {"2.5"}
    assert {quote.selection_key for quote in totals} == {"over", "under"}


def test_conversion_is_deterministic_and_does_not_retain_source_payload():
    first = convert_oddsharvester_record(_record())
    second = convert_oddsharvester_record(deepcopy(_record()))

    assert first.payload_digest == second.payload_digest
    assert [quote.source_quote_id for quote in first.quotes] == [quote.source_quote_id for quote in second.quotes]
    assert "match_link" not in first.payload


def test_h2h_fragment_is_the_event_identity_and_prevents_same_team_collisions():
    first_record = _record()
    first_record["match_link"] = "https://www.oddsportal.com/football/h2h/gremio-E1EFmhVh/sao-paulo-QgP0oAUH/#ClHgE1DU"
    second_record = deepcopy(first_record)
    second_record["match_link"] = (
        "https://www.oddsportal.com/football/h2h/gremio-E1EFmhVh/sao-paulo-QgP0oAUH/#Other123:1X2;2"
    )

    first = convert_oddsharvester_record(first_record)
    second = convert_oddsharvester_record(second_record)

    assert first.source_event_id == "ClHgE1DU"
    assert second.source_event_id == "Other123"
    assert {quote.source_quote_id for quote in first.quotes}.isdisjoint(
        quote.source_quote_id for quote in second.quotes
    )


def test_rejects_fragmentless_or_mismatched_h2h_event_identity():
    record = _record()
    record["match_link"] = "https://www.oddsportal.com/football/h2h/gremio-E1EFmhVh/sao-paulo-QgP0oAUH/"

    with pytest.raises(ValueError, match="H2H match_link"):
        convert_oddsharvester_record(record)

    record["match_link"] += "#ClHgE1DU"
    record["match_id"] = "Other123"
    with pytest.raises(ValueError, match="match_id must match"):
        convert_oddsharvester_record(record)


def test_wraps_fallback_record_in_exact_registered_provider_envelope():
    envelope = oddsharvester_record_envelope(_record(), job_id="job-1", run_id="run-1", correlation_id="corr-1")

    assert (envelope.adapter_key, envelope.source_key) == (
        ODDSHARVESTER_ADAPTER_KEY,
        ODDSHARVESTER_SOURCE_KEY,
    )
    assert envelope.schema_version == "1.0"
    assert envelope.source_id == "arsenal-chelsea-AbC123xy"
    assert "match_link" not in envelope.payload_json


def test_unknown_or_incomplete_markets_are_explicitly_partial():
    record = _record()
    record["correct_score_market"] = [{"1:0": "5.0", "bookmaker_name": "Book Maker"}]
    record["1x2_market"][0].pop("X")

    observation = convert_oddsharvester_record(record)

    assert observation.quality == "partial"
    assert len(observation.quotes) == 4


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1", "0.9", True])
def test_rejects_invalid_prices(value):
    record = _record()
    record["1x2_market"][0]["1"] = value

    with pytest.raises(ValueError, match="finite decimal greater than one"):
        convert_oddsharvester_record(record)


def test_rejects_non_oddsportal_event_urls():
    record = _record()
    record["match_link"] = "https://example.com/football/event-123/"

    with pytest.raises(ValueError, match="OddsPortal URL"):
        convert_oddsharvester_record(record)


def test_rejects_sensitive_fields_even_when_nested():
    record = _record()
    record["metadata"] = {"api_token": "must-not-cross-the-boundary"}

    with pytest.raises(ValueError, match="sensitive field"):
        convert_oddsharvester_record(record)


def test_rejects_duplicate_quote_identity_from_duplicate_bookmaker_rows():
    record = _record()
    record["1x2_market"].append(deepcopy(record["1x2_market"][0]))

    with pytest.raises(ValueError, match="duplicate quote identities"):
        convert_oddsharvester_record(record)
