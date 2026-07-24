from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm.attributes import NO_VALUE, set_committed_value

from app.models.match import OddsEntry
from app.models.odds_lineage import OddsSnapshot
from app.services.clv import (
    CLOSING_CONSENSUS_UNAVAILABLE,
    CLOSING_MARKET_UNAVAILABLE,
    CLOSING_SAME_BOOK_UNAVAILABLE,
    REFERENCE_MARKET_PROBABILITY_UNAVAILABLE,
    calculate_clv,
    consensus_clv_pp,
    market_best_clv_pct,
    same_book_clv_pct,
)
from app.services.odds_quotes import (
    QUOTE_CONSENSUS_UNAVAILABLE,
    QUOTE_FUTURE_ONLY,
    QUOTE_OBSERVED_AT_MISSING,
    QUOTE_SNAPSHOT_INCOHERENT,
    QUOTE_STALE,
    load_odds_entries,
    select_closing_quote_set,
    select_quote_set,
)

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_snapshot_backed_odds_are_eager_loaded_and_unloaded_rows_remain_greenlet_safe():
    snapshot_observed_at = NOW - timedelta(minutes=1)
    legacy_entry_timestamp = NOW - timedelta(minutes=2)
    entry = OddsEntry(
        id=903,
        match_id=901,
        odds_snapshot_id=902,
        bookmaker="SnapshotBook",
        market="1x2",
        home_odds=2.1,
        draw_odds=3.2,
        away_odds=3.8,
        timestamp=legacy_entry_timestamp,
    )
    assert sa_inspect(entry).attrs.odds_snapshot.loaded_value is NO_VALUE

    # Synchronous selection must not attempt a lazy relationship load. It can
    # safely fall back to the entry timestamp while retaining FK lineage.
    safe_quote_set = select_quote_set([entry], market="1x2", as_of=NOW)
    assert safe_quote_set.snapshot_id == 902
    assert safe_quote_set.observed_at == legacy_entry_timestamp

    snapshot = OddsSnapshot(
        id=902,
        match_id=901,
        source="test",
        source_key="snapshot-902",
        observed_at=snapshot_observed_at,
        quality="complete",
    )
    set_committed_value(entry, "odds_snapshot", snapshot)

    class _Scalars:
        def all(self):
            return [entry]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Db:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            return _Result()

    db = _Db()
    eager_entries = await load_odds_entries(db, match_ids=[901])
    assert any("OddsEntry.odds_snapshot" in str(option.path) for option in db.statement._with_options)
    eager_quote_set = select_quote_set(eager_entries, market="1x2", as_of=NOW)
    assert eager_quote_set.snapshot_id == 902
    assert eager_quote_set.observed_at == snapshot_observed_at
    assert eager_quote_set.best_quotes["home"].price == 2.1


def _entry(
    *,
    entry_id: int,
    bookmaker: str,
    observed_at: datetime | None,
    home: float | None,
    draw: float | None,
    away: float | None,
    market: str = "1x2:FullTime",
    snapshot_id: int | None = None,
):
    snapshot = (
        SimpleNamespace(id=snapshot_id, observed_at=observed_at, ingested_at=NOW) if snapshot_id is not None else None
    )
    return SimpleNamespace(
        id=entry_id,
        bookmaker=bookmaker,
        market=market,
        home_odds=home,
        draw_odds=draw,
        away_odds=away,
        timestamp=observed_at,
        created_at=NOW,
        snapshot_id=snapshot_id,
        snapshot=snapshot,
    )


def test_select_quote_set_never_uses_future_or_historic_best_prices():
    old = NOW - timedelta(minutes=10)
    current = NOW - timedelta(minutes=2)
    future = NOW + timedelta(seconds=1)
    entries = [
        _entry(entry_id=1, bookmaker="A", observed_at=old, home=9.0, draw=9.0, away=9.0),
        _entry(entry_id=2, bookmaker="A", observed_at=current, home=2.0, draw=3.2, away=4.0),
        _entry(entry_id=3, bookmaker="B", observed_at=current, home=2.1, draw=3.1, away=3.9),
        _entry(entry_id=4, bookmaker="A", observed_at=future, home=10.0, draw=10.0, away=10.0),
    ]

    result = select_quote_set(entries, market="1x2", as_of=NOW)

    assert result.observed_at == current
    assert result.is_ticket_eligible is True
    assert result.best_quotes["home"].price == 2.1
    assert result.best_quotes["draw"].price == 3.2
    assert result.best_quotes["away"].price == 4.0


def test_snapshot_fk_is_used_as_coherent_group_and_line_shopping_is_internal():
    observed = NOW - timedelta(minutes=1)
    entries = [
        _entry(entry_id=1, bookmaker="A", observed_at=observed, home=2.0, draw=3.2, away=4.0, snapshot_id=10),
        _entry(entry_id=2, bookmaker="B", observed_at=observed, home=2.1, draw=3.1, away=3.9, snapshot_id=10),
        _entry(entry_id=3, bookmaker="C", observed_at=observed, home=8.0, draw=8.0, away=8.0, snapshot_id=9),
    ]

    result = select_quote_set(entries, market="1x2", as_of=NOW)

    assert result.snapshot_id == 10
    assert result.best_quotes["home"].price == 2.1
    assert result.best_quotes["home"].snapshot_id == 10


def test_consensus_devigs_each_complete_book_before_median_and_normalization():
    observed = NOW - timedelta(minutes=1)
    entries = [
        _entry(entry_id=1, bookmaker="A", observed_at=observed, home=2.0, draw=3.0, away=4.0),
        _entry(entry_id=2, bookmaker="B", observed_at=observed, home=2.2, draw=3.2, away=3.6),
    ]

    result = select_quote_set(entries, market="1x2", as_of=NOW)

    assert len(result.bookmaker_lines) == 2
    assert sum(result.consensus_probabilities.values()) == pytest.approx(1.0)
    line_a = next(line for line in result.bookmaker_lines if line.bookmaker == "A")
    assert line_a.implied_probabilities["home"] == pytest.approx((1 / 2) / (1 / 2 + 1 / 3 + 1 / 4))


def test_incomplete_latest_snapshot_is_visible_but_never_ticket_eligible():
    observed = NOW - timedelta(minutes=1)
    entries = [_entry(entry_id=1, bookmaker="A", observed_at=observed, home=2.0, draw=None, away=4.0)]

    result = select_quote_set(entries, market="1x2", as_of=NOW)

    assert result.is_ticket_eligible is False
    assert result.best_quotes["home"].price == 2.0
    assert result.best_quotes["away"].price == 4.0
    assert QUOTE_CONSENSUS_UNAVAILABLE in result.reason_codes
    assert QUOTE_SNAPSHOT_INCOHERENT in result.reason_codes


def test_stale_future_only_and_missing_observation_are_explicit():
    stale = select_quote_set(
        [_entry(entry_id=1, bookmaker="A", observed_at=NOW - timedelta(minutes=16), home=2, draw=3, away=4)],
        market="1x2",
        as_of=NOW,
    )
    future = select_quote_set(
        [_entry(entry_id=2, bookmaker="A", observed_at=NOW + timedelta(seconds=1), home=2, draw=3, away=4)],
        market="1x2",
        as_of=NOW,
    )
    missing = select_quote_set(
        [_entry(entry_id=3, bookmaker="A", observed_at=None, home=2, draw=3, away=4)],
        market="1x2",
        as_of=NOW,
    )

    assert QUOTE_STALE in stale.reason_codes
    assert future.reason_codes == (QUOTE_FUTURE_ONLY,)
    assert missing.reason_codes == (QUOTE_OBSERVED_AT_MISSING,)


def test_current_two_way_market_mapping_is_supported():
    observed = NOW - timedelta(minutes=1)
    entries = [
        _entry(
            entry_id=1,
            bookmaker="A",
            observed_at=observed,
            home=1.9,
            draw=None,
            away=1.8,
            market="btts:FullTime",
        )
    ]

    result = select_quote_set(entries, market="btts", as_of=NOW)

    assert result.best_quotes["yes"].price == 1.9
    assert result.best_quotes["no"].price == 1.8
    assert result.is_ticket_eligible is True


def test_closing_quote_is_before_kickoff_and_within_six_hours():
    entries = [
        _entry(entry_id=1, bookmaker="A", observed_at=NOW - timedelta(hours=5), home=2, draw=3, away=4),
        _entry(entry_id=2, bookmaker="A", observed_at=NOW + timedelta(seconds=1), home=8, draw=8, away=8),
    ]

    result = select_closing_quote_set(entries, market="1x2", kickoff_at=NOW)

    assert result.observed_at == NOW - timedelta(hours=5)
    assert result.is_ticket_eligible is True


def test_clv_formulas_follow_reference_over_close_contract():
    assert same_book_clv_pct(2.2, 2.0) == pytest.approx(10.0)
    assert market_best_clv_pct(2.2, 2.1) == pytest.approx(4.76190476)
    assert consensus_clv_pp(0.45, 0.5) == pytest.approx(5.0)

    result = calculate_clv(
        reference_price=2.2,
        same_book_closing_price=2.0,
        market_best_closing_price=2.1,
        reference_market_probability=0.45,
        closing_consensus_probability=0.5,
    )
    assert all(result.coverage.values())
    assert result.unavailable_reasons == {}


def test_clv_missing_inputs_are_not_coerced_to_zero():
    result = calculate_clv(reference_price=2.0)

    assert result.same_book_clv_pct is None
    assert result.market_best_clv_pct is None
    assert result.consensus_clv_pp is None
    assert result.unavailable_reasons["same_book"] == (CLOSING_SAME_BOOK_UNAVAILABLE,)
    assert result.unavailable_reasons["market_best"] == (CLOSING_MARKET_UNAVAILABLE,)
    assert result.unavailable_reasons["consensus"] == (
        REFERENCE_MARKET_PROBABILITY_UNAVAILABLE,
        CLOSING_CONSENSUS_UNAVAILABLE,
    )


def test_non_finite_prices_are_rejected():
    result = calculate_clv(reference_price=float("inf"), same_book_closing_price=2.0)

    assert result.same_book_clv_pct is None
    assert "reference_price_invalid" in result.unavailable_reasons["same_book"]
