from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.providers.odds import OddsEventObservationV1, OddsQuoteV1
from app.services.odds_ingestion import (
    OddsObservationMaterializationError,
    _is_fully_mapped,
    _legacy_1x2_groups,
)


def _quote(selection, *, bookmaker="book-1", market="1x2", line=None, status="active"):
    return OddsQuoteV1(
        source_quote_id=f"{bookmaker}-{selection}",
        provider_bookmaker_key=bookmaker,
        provider_bookmaker_name="Book",
        provider_market_key="market-1",
        market_key=market,
        period_key="full_time",
        line=line,
        selection_key=selection,
        selection_name=selection.title(),
        price=Decimal("2.0"),
        provider_updated_at=datetime(2026, 8, 1, tzinfo=UTC),
        status=status,
    )


def _event(*quotes, quality="complete", expected_bookmaker_count=1, expected_market_count=1):
    return OddsEventObservationV1(
        source_event_id="fixture-1",
        sport_key="football",
        competition_key="league-1",
        commence_time=datetime(2026, 8, 2, tzinfo=UTC),
        home_team="Home",
        away_team="Away",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        scope="prematch",
        quality=quality,
        quotes=quotes,
        expected_bookmaker_count=expected_bookmaker_count,
        expected_market_count=expected_market_count,
    )


def test_complete_mapping_requires_honest_expected_scope_and_exact_mappings():
    event = _event(_quote("home"), _quote("draw"), _quote("away"))
    assert _is_fully_mapped(event, bookmaker_mapping={"book-1": "canonical"}, supported_markets=frozenset({"1x2"}))
    assert not _is_fully_mapped(event, bookmaker_mapping={}, supported_markets=frozenset({"1x2"}))
    assert not _is_fully_mapped(event, bookmaker_mapping={"book-1": "canonical"}, supported_markets=frozenset())
    mismatched = _event(*event.quotes, expected_market_count=2)
    assert not _is_fully_mapped(
        mismatched, bookmaker_mapping={"book-1": "canonical"}, supported_markets=frozenset({"1x2"})
    )


def test_legacy_projection_requires_complete_active_exact_1x2_set():
    event = _event(_quote("home"), _quote("draw"), _quote("away"))
    groups = _legacy_1x2_groups(event, bookmaker_mapping={"book-1": "canonical"}, snapshot_complete=True)
    assert len(groups) == 1 and groups[0][0] == "canonical"
    assert not _legacy_1x2_groups(event, bookmaker_mapping={"book-1": "canonical"}, snapshot_complete=False)
    stopped = _event(_quote("home"), _quote("draw"), _quote("away", status="stopped"))
    assert not _legacy_1x2_groups(stopped, bookmaker_mapping={"book-1": "canonical"}, snapshot_complete=True)


@pytest.mark.asyncio
async def test_materialization_rejects_invalid_mapping_version_before_database_work():
    from app.services.odds_ingestion import materialize_odds_observation

    with pytest.raises(OddsObservationMaterializationError, match="mapping_version"):
        # Validation is synchronous up to the first database access.
        await materialize_odds_observation(
            SimpleNamespace(), SimpleNamespace(), bookmaker_mapping={}, mapping_version=""
        )
