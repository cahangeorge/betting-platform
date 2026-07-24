"""Canonical, leakage-safe selection of bookmaker quote snapshots.

The service deliberately operates on duck-typed objects.  It supports the
current ``OddsEntry`` shape (where ``timestamp`` belongs to each entry) and a
future snapshot-backed shape (``snapshot_id`` / ``snapshot.observed_at``)
without coupling quote semantics to a particular migration.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import isfinite
from statistics import median
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import NO_VALUE

from app.models.match import OddsEntry
from app.services.prediction_quality import market_matches, market_outcomes, outcome_odds_field

PREMATCH_MAX_AGE = timedelta(minutes=15)
LIVE_MAX_AGE = timedelta(seconds=30)
CLOSING_MAX_LOOKBACK = timedelta(hours=6)

QUOTE_MISSING = "quote_missing"
QUOTE_FUTURE_ONLY = "quote_future_only"
QUOTE_OBSERVED_AT_MISSING = "quote_observed_at_missing"
QUOTE_STALE = "quote_stale"
QUOTE_CONSENSUS_UNAVAILABLE = "quote_consensus_unavailable"
QUOTE_SNAPSHOT_INCOHERENT = "quote_snapshot_incoherent"


@dataclass(frozen=True, slots=True)
class OutcomeQuote:
    """One selected price, with enough lineage to persist it later."""

    outcome: str
    price: float
    bookmaker: str
    observed_at: datetime
    entry_id: int | None = None
    snapshot_id: int | str | None = None
    snapshot_key: tuple[str, Any] | None = None
    ingested_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BookmakerLine:
    """A complete line from one bookmaker in one coherent snapshot."""

    bookmaker: str
    prices: dict[str, float]
    implied_probabilities: dict[str, float]
    overround: float


@dataclass(frozen=True, slots=True)
class QuoteSet:
    market: str
    as_of: datetime
    observed_at: datetime | None
    snapshot_id: int | str | None
    snapshot_key: tuple[str, Any] | None
    best_quotes: dict[str, OutcomeQuote] = field(default_factory=dict)
    consensus_probabilities: dict[str, float] = field(default_factory=dict)
    bookmaker_lines: tuple[BookmakerLine, ...] = ()
    is_ticket_eligible: bool = False
    reason_codes: tuple[str, ...] = ()

    def quote_for(self, outcome: str) -> OutcomeQuote | None:
        return self.best_quotes.get(outcome.strip().lower())


@dataclass(frozen=True, slots=True)
class _Candidate:
    entry: Any
    observed_at: datetime
    ingested_at: datetime | None
    snapshot_id: int | str | None
    snapshot_key: tuple[str, Any]
    bookmaker: str


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _datetime_attr(*objects: Any, names: tuple[str, ...]) -> datetime | None:
    for obj in objects:
        if obj is None:
            continue
        for name in names:
            value = getattr(obj, name, None)
            if isinstance(value, datetime):
                return _utc(value)
    return None


def _snapshot_for(entry: Any) -> Any | None:
    # Canonical quote selection is intentionally synchronous. Accessing an
    # unloaded SQLAlchemy relationship here would attempt async IO outside the
    # greenlet bridge and raise MissingGreenlet. Known database call sites eager
    # load the relationship, while this guard keeps detached/legacy rows safe.
    try:
        state = sa_inspect(entry)
    except NoInspectionAvailable:
        return getattr(entry, "snapshot", None) or getattr(entry, "odds_snapshot", None)
    for attribute_name in ("snapshot", "odds_snapshot"):
        if attribute_name not in state.attrs:
            continue
        loaded_value = state.attrs[attribute_name].loaded_value
        if loaded_value is not NO_VALUE and loaded_value is not None:
            return loaded_value
    return None


def _snapshot_identity(entry: Any, observed_at: datetime) -> tuple[int | str | None, tuple[str, Any]]:
    snapshot = _snapshot_for(entry)
    snapshot_id = getattr(entry, "snapshot_id", None)
    if snapshot_id is None:
        snapshot_id = getattr(entry, "odds_snapshot_id", None)
    if snapshot_id is None and snapshot is not None:
        snapshot_id = getattr(snapshot, "id", None)
    if snapshot_id is not None:
        return snapshot_id, ("snapshot_id", snapshot_id)

    source_key = getattr(snapshot, "source_key", None) if snapshot is not None else None
    if source_key:
        return None, ("source_key", str(source_key))

    # The current schema has no snapshot FK. Odds imported from one scrape
    # share their observation timestamp, which is the only safe cohort key.
    return None, ("observed_at", observed_at)


async def load_odds_entries(
    db: AsyncSession,
    *,
    match_ids: Iterable[int],
) -> list[OddsEntry]:
    """Load odds with snapshot lineage ready for synchronous selection."""

    normalized_ids = list(dict.fromkeys(int(match_id) for match_id in match_ids))
    if not normalized_ids:
        return []
    result = await db.execute(
        select(OddsEntry)
        .options(selectinload(OddsEntry.odds_snapshot))
        .where(OddsEntry.match_id.in_(normalized_ids))
        .order_by(OddsEntry.match_id.asc(), OddsEntry.timestamp.desc().nulls_last(), OddsEntry.id.desc())
    )
    return list(result.scalars().all())


def _candidate(entry: Any) -> _Candidate | None:
    snapshot = _snapshot_for(entry)
    observed_at = _datetime_attr(snapshot, entry, names=("observed_at", "timestamp"))
    if observed_at is None:
        return None
    ingested_at = _datetime_attr(snapshot, entry, names=("ingested_at", "created_at"))
    snapshot_id, snapshot_key = _snapshot_identity(entry, observed_at)
    return _Candidate(
        entry=entry,
        observed_at=observed_at,
        ingested_at=ingested_at,
        snapshot_id=snapshot_id,
        snapshot_key=snapshot_key,
        bookmaker=str(getattr(entry, "bookmaker", "") or "").strip(),
    )


def _price(entry: Any, outcome: str) -> float | None:
    field_name = outcome_odds_field(outcome)
    value = getattr(entry, field_name, None) if field_name else None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) and parsed > 1.0 else None


def _bookmaker_lines(
    candidates: list[_Candidate], outcomes: list[str]
) -> tuple[tuple[BookmakerLine, ...], dict[str, dict[str, _Candidate]]]:
    by_book: dict[str, dict[str, _Candidate]] = defaultdict(dict)
    prices_by_book: dict[str, dict[str, float]] = defaultdict(dict)
    for candidate in candidates:
        if not candidate.bookmaker:
            continue
        for outcome in outcomes:
            price = _price(candidate.entry, outcome)
            if price is None:
                continue
            current = prices_by_book[candidate.bookmaker].get(outcome)
            if current is None or price > current:
                prices_by_book[candidate.bookmaker][outcome] = price
                by_book[candidate.bookmaker][outcome] = candidate

    lines: list[BookmakerLine] = []
    for bookmaker, prices in sorted(prices_by_book.items()):
        if set(prices) != set(outcomes):
            continue
        raw = {outcome: 1.0 / prices[outcome] for outcome in outcomes}
        overround = sum(raw.values())
        if overround <= 0:
            continue
        lines.append(
            BookmakerLine(
                bookmaker=bookmaker,
                prices=dict(prices),
                implied_probabilities={outcome: raw[outcome] / overround for outcome in outcomes},
                overround=overround,
            )
        )
    return tuple(lines), by_book


def _snapshot_sort_key(key: tuple[str, Any]) -> tuple[str, int, float | str]:
    value = key[1]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return key[0], 1, float(value)
    return key[0], 0, str(value)


def _analysis_quotes(candidates: list[_Candidate], outcomes: list[str]) -> dict[str, OutcomeQuote]:
    """Expose partial prices without making them ticket eligible."""

    result: dict[str, OutcomeQuote] = {}
    for candidate in candidates:
        if not candidate.bookmaker:
            continue
        for outcome in outcomes:
            price = _price(candidate.entry, outcome)
            current = result.get(outcome)
            if price is None or (current is not None and price <= current.price):
                continue
            result[outcome] = OutcomeQuote(
                outcome=outcome,
                price=price,
                bookmaker=candidate.bookmaker,
                observed_at=candidate.observed_at,
                entry_id=getattr(candidate.entry, "id", None),
                snapshot_id=candidate.snapshot_id,
                snapshot_key=candidate.snapshot_key,
                ingested_at=candidate.ingested_at,
            )
    return result


def _consensus(lines: tuple[BookmakerLine, ...], outcomes: list[str]) -> dict[str, float]:
    if not lines:
        return {}
    medians = {outcome: median(line.implied_probabilities[outcome] for line in lines) for outcome in outcomes}
    total = sum(medians.values())
    if total <= 0:
        return {}
    return {outcome: value / total for outcome, value in medians.items()}


def select_quote_set(
    entries: Iterable[Any],
    *,
    market: str,
    as_of: datetime,
    max_age: timedelta = PREMATCH_MAX_AGE,
) -> QuoteSet:
    """Select the latest temporally eligible snapshot and its best prices.

    Future and timestamp-less records are never used.  Line shopping happens
    only between complete bookmaker lines inside the chosen snapshot; it never
    mixes historic snapshots.  An incomplete latest snapshot remains visible
    for analysis but is explicitly ineligible for ticket generation.
    """

    as_of_utc = _utc(as_of)
    matching = [entry for entry in entries if market_matches(market, getattr(entry, "market", None))]
    if not matching:
        return QuoteSet(
            market=market,
            as_of=as_of_utc,
            observed_at=None,
            snapshot_id=None,
            snapshot_key=None,
            reason_codes=(QUOTE_MISSING,),
        )

    parsed = [candidate for entry in matching if (candidate := _candidate(entry)) is not None]
    if not parsed:
        return QuoteSet(
            market=market,
            as_of=as_of_utc,
            observed_at=None,
            snapshot_id=None,
            snapshot_key=None,
            reason_codes=(QUOTE_OBSERVED_AT_MISSING,),
        )

    eligible = [candidate for candidate in parsed if candidate.observed_at <= as_of_utc]
    if not eligible:
        return QuoteSet(
            market=market,
            as_of=as_of_utc,
            observed_at=None,
            snapshot_id=None,
            snapshot_key=None,
            reason_codes=(QUOTE_FUTURE_ONLY,),
        )

    latest_observed_at = max(candidate.observed_at for candidate in eligible)
    latest_candidates = [candidate for candidate in eligible if candidate.observed_at == latest_observed_at]
    latest_key = max(
        (candidate.snapshot_key for candidate in latest_candidates),
        key=_snapshot_sort_key,
    )
    selected = [candidate for candidate in latest_candidates if candidate.snapshot_key == latest_key]
    representative = selected[0]

    age = as_of_utc - latest_observed_at
    outcomes = market_outcomes(market)
    lines, candidate_by_book = _bookmaker_lines(selected, outcomes)
    consensus = _consensus(lines, outcomes)

    best_quotes: dict[str, OutcomeQuote] = {}
    for outcome in outcomes:
        available = [line for line in lines if outcome in line.prices]
        if not available:
            continue
        best_line = max(available, key=lambda line: line.prices[outcome])
        candidate = candidate_by_book[best_line.bookmaker][outcome]
        best_quotes[outcome] = OutcomeQuote(
            outcome=outcome,
            price=best_line.prices[outcome],
            bookmaker=best_line.bookmaker,
            observed_at=latest_observed_at,
            entry_id=getattr(candidate.entry, "id", None),
            snapshot_id=candidate.snapshot_id,
            snapshot_key=candidate.snapshot_key,
            ingested_at=candidate.ingested_at,
        )
    if not lines:
        best_quotes = _analysis_quotes(selected, outcomes)

    reasons: list[str] = []
    if age > max_age:
        reasons.append(QUOTE_STALE)
    if not outcomes or not lines or not consensus:
        reasons.append(QUOTE_CONSENSUS_UNAVAILABLE)
    if set(best_quotes) != set(outcomes):
        reasons.append(QUOTE_SNAPSHOT_INCOHERENT)

    return QuoteSet(
        market=market,
        as_of=as_of_utc,
        observed_at=latest_observed_at,
        snapshot_id=representative.snapshot_id,
        snapshot_key=representative.snapshot_key,
        best_quotes=best_quotes,
        consensus_probabilities=consensus,
        bookmaker_lines=lines,
        is_ticket_eligible=not reasons,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def select_closing_quote_set(
    entries: Iterable[Any],
    *,
    market: str,
    kickoff_at: datetime,
    max_lookback: timedelta = CLOSING_MAX_LOOKBACK,
) -> QuoteSet:
    """Return the last coherent view no later than kickoff."""

    return select_quote_set(entries, market=market, as_of=kickoff_at, max_age=max_lookback)


def max_quote_age(*, live: bool) -> timedelta:
    return LIVE_MAX_AGE if live else PREMATCH_MAX_AGE
