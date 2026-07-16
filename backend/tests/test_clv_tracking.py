from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.odds_lineage import TicketLegQuoteSnapshot
from app.services import clv_tracking
from app.services.clv_tracking import build_clv_report, capture_ticket_closing_quotes
from app.services.odds_quotes import BookmakerLine, OutcomeQuote, QuoteSet


def _snapshot(stage: str, price: str, probability: str | None = None, *, revision: int = 1):
    return TicketLegQuoteSnapshot(
        ticket_leg_id=10,
        stage=stage,
        revision=revision,
        market="1x2",
        selection="home",
        bookmaker="book-a",
        price=Decimal(price),
        observed_at=datetime(2026, 7, 16, tzinfo=UTC),
        market_probability=Decimal(probability) if probability else None,
    )


def test_clv_report_prefers_activation_and_reports_real_coverage():
    rows = [
        (1, 10, _snapshot("generation", "2.00", "0.48")),
        (1, 10, _snapshot("activation", "2.10", "0.47")),
        (1, 10, _snapshot("closing_same_book", "1.90", "0.52")),
        (1, 10, _snapshot("closing_market", "1.85", "0.53")),
    ]

    report = build_clv_report(rows)

    item = report["items"][0]
    assert item["reference_stage"] == "activation"
    assert item["same_book_clv_pct"] == pytest.approx(10.5263158)
    assert item["market_best_clv_pct"] == pytest.approx(13.5135135)
    assert item["consensus_clv_pp"] == pytest.approx(6.0)
    assert report["summary"]["same_book_coverage_pct"] == 100.0


def test_clv_report_never_turns_missing_closing_data_into_zero():
    report = build_clv_report([(1, 10, _snapshot("generation", "2.00", "0.48"))])

    item = report["items"][0]
    assert item["same_book_clv_pct"] is None
    assert item["market_best_clv_pct"] is None
    assert item["consensus_clv_pp"] is None
    assert report["summary"]["market_best_coverage_pct"] == 0.0
    assert "closing_market_unavailable" in item["unavailable_reasons"]["market_best"]


def test_clv_report_uses_latest_revision_per_stage_regardless_of_row_order():
    rows = [
        (1, 10, _snapshot("closing_market", "1.90", "0.52", revision=1)),
        (1, 10, _snapshot("activation", "2.00", "0.48", revision=1)),
        (1, 10, _snapshot("closing_market", "1.80", "0.54", revision=2)),
        (1, 10, _snapshot("activation", "2.10", "0.47", revision=2)),
    ]

    report = build_clv_report(reversed(rows))

    item = report["items"][0]
    assert item["reference_stage"] == "activation"
    assert item["market_best_clv_pct"] == pytest.approx(16.6666667)
    assert item["consensus_clv_pp"] == pytest.approx(7.0)


def test_clv_report_uses_latest_refresh_when_activation_is_unavailable():
    rows = [
        (1, 10, _snapshot("generation", "2.00", "0.48", revision=1)),
        (1, 10, _snapshot("refresh", "2.05", "0.47", revision=2)),
        (1, 10, _snapshot("refresh", "2.10", "0.46", revision=3)),
        (1, 10, _snapshot("closing_market", "1.90", "0.52", revision=1)),
    ]

    item = build_clv_report(rows)["items"][0]

    assert item["reference_stage"] == "refresh"
    assert item["market_best_clv_pct"] == pytest.approx(10.5263158)
    assert item["consensus_clv_pp"] == pytest.approx(6.0)


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class _Db:
    def __init__(self, existing):
        self.existing = existing
        self.added = []

    async def execute(self, _statement):
        return _Result(self.existing)

    def add(self, value):
        self.added.append(value)


def _closing_quote_set(*, observed_at: datetime, home_price: float, snapshot_id: int) -> QuoteSet:
    line = BookmakerLine(
        bookmaker="book-a",
        prices={"home": home_price, "draw": 3.2, "away": 4.1},
        implied_probabilities={"home": 0.5, "draw": 0.3, "away": 0.2},
        overround=1.05,
    )
    return QuoteSet(
        market="1x2",
        as_of=observed_at,
        observed_at=observed_at,
        snapshot_id=snapshot_id,
        snapshot_key=("snapshot_id", snapshot_id),
        best_quotes={
            "home": OutcomeQuote(
                outcome="home",
                price=home_price,
                bookmaker="book-a",
                observed_at=observed_at,
                entry_id=77,
                snapshot_id=snapshot_id,
            )
        },
        consensus_probabilities={"home": 0.5, "draw": 0.3, "away": 0.2},
        bookmaker_lines=(line,),
        is_ticket_eligible=True,
    )


@pytest.mark.asyncio
async def test_closing_capture_appends_a_new_revision_when_quote_evidence_changes(monkeypatch):
    observed_at = datetime(2026, 7, 16, tzinfo=UTC)
    reference = _snapshot("activation", "2.10", "0.47", revision=2)
    reference.id = 1
    previous_same_book = _snapshot("closing_same_book", "2.00", "0.50", revision=1)
    previous_same_book.id = 2
    previous_same_book.odds_snapshot_id = 8
    previous_market = _snapshot("closing_market", "2.00", "0.50", revision=1)
    previous_market.id = 3
    previous_market.odds_snapshot_id = 8
    db = _Db([reference, previous_same_book, previous_market])

    async def fake_load(*_args, **_kwargs):
        return []

    monkeypatch.setattr(clv_tracking, "load_odds_entries", fake_load)
    monkeypatch.setattr(
        clv_tracking,
        "select_closing_quote_set",
        lambda *_args, **_kwargs: _closing_quote_set(
            observed_at=observed_at,
            home_price=1.90,
            snapshot_id=9,
        ),
    )
    leg = SimpleNamespace(
        id=10,
        match_id=20,
        market="1x2",
        selection="home",
        bookmaker="book-a",
        match=SimpleNamespace(match_date=observed_at),
    )

    created = await capture_ticket_closing_quotes(db, SimpleNamespace(legs=[leg]))

    assert created == 2
    assert {(row.stage, row.revision) for row in db.added} == {
        ("closing_same_book", 2),
        ("closing_market", 2),
    }
    assert all(row.odds_snapshot_id == 9 for row in db.added)


@pytest.mark.asyncio
async def test_closing_capture_is_idempotent_for_the_same_quote_revision(monkeypatch):
    observed_at = datetime(2026, 7, 16, tzinfo=UTC)
    reference = _snapshot("activation", "2.10", "0.47", revision=2)
    existing_same_book = _snapshot("closing_same_book", "1.90", "0.50", revision=2)
    existing_same_book.odds_snapshot_id = 9
    existing_market = _snapshot("closing_market", "1.90", "0.50", revision=2)
    existing_market.odds_snapshot_id = 9
    db = _Db([reference, existing_same_book, existing_market])

    async def fake_load(*_args, **_kwargs):
        return []

    monkeypatch.setattr(clv_tracking, "load_odds_entries", fake_load)
    monkeypatch.setattr(
        clv_tracking,
        "select_closing_quote_set",
        lambda *_args, **_kwargs: _closing_quote_set(
            observed_at=observed_at,
            home_price=1.90,
            snapshot_id=9,
        ),
    )
    leg = SimpleNamespace(
        id=10,
        match_id=20,
        market="1x2",
        selection="home",
        bookmaker="book-a",
        match=SimpleNamespace(match_date=observed_at),
    )

    created = await capture_ticket_closing_quotes(db, SimpleNamespace(legs=[leg]))

    assert created == 0
    assert db.added == []
