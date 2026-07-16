"""Persistence and reporting helpers for closing-line value evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.odds_lineage import TicketLegQuoteSnapshot
from app.services.clv import calculate_clv
from app.services.odds_quotes import load_odds_entries, select_closing_quote_set


def _selection_outcome(selection: str) -> str:
    normalized = selection.strip().lower()
    aliases = {
        "1": "home",
        "h": "home",
        "home_win": "home",
        "x": "draw",
        "d": "draw",
        "2": "away",
        "a": "away",
        "away_win": "away",
        "btts_yes": "yes",
        "true": "yes",
        "btts_no": "no",
        "false": "no",
        "over_2.5": "over",
        "over_2_5": "over",
        "under_2.5": "under",
        "under_2_5": "under",
    }
    return aliases.get(normalized, normalized)


def _snapshot_rank(snapshot: TicketLegQuoteSnapshot) -> tuple[int, float, int]:
    recorded_at = getattr(snapshot, "recorded_at", None)
    return (
        int(getattr(snapshot, "revision", 1) or 1),
        recorded_at.timestamp() if recorded_at is not None else float("-inf"),
        int(snapshot.id or 0),
    )


def _same_quote(
    snapshot: TicketLegQuoteSnapshot | None,
    *,
    price: float,
    bookmaker: str | None,
    odds_snapshot_id: int | None,
    observed_at: datetime | None,
) -> bool:
    if snapshot is None:
        return False
    return (
        Decimal(str(snapshot.price)) == Decimal(str(price))
        and snapshot.bookmaker == bookmaker
        and snapshot.odds_snapshot_id == odds_snapshot_id
        and snapshot.observed_at == observed_at
    )


async def capture_ticket_closing_quotes(db: AsyncSession, ticket: Any) -> int:
    """Persist immutable closing quotes for a ticket immediately before settlement.

    The quote selector never reads observations after kickoff. Missing or
    incoherent data remains missing rather than being synthesized as zero CLV.
    """

    leg_ids = [int(leg.id) for leg in ticket.legs if getattr(leg, "id", None) is not None]
    if not leg_ids:
        return 0

    existing_result = await db.execute(
        select(TicketLegQuoteSnapshot).where(
            TicketLegQuoteSnapshot.ticket_leg_id.in_(leg_ids),
            TicketLegQuoteSnapshot.stage.in_(
                ("generation", "refresh", "activation", "closing_same_book", "closing_market")
            ),
        )
    )
    latest_by_leg_stage: dict[tuple[int, str], TicketLegQuoteSnapshot] = {}
    for snapshot in existing_result.scalars().all():
        key = (int(snapshot.ticket_leg_id), str(snapshot.stage))
        current = latest_by_leg_stage.get(key)
        if current is None or _snapshot_rank(snapshot) > _snapshot_rank(current):
            latest_by_leg_stage[key] = snapshot

    created = 0
    for leg in ticket.legs:
        match = getattr(leg, "match", None)
        kickoff_at: datetime | None = getattr(match, "match_date", None)
        match_id = getattr(leg, "match_id", None)
        if match_id is None or kickoff_at is None:
            continue

        quote_set = select_closing_quote_set(
            await load_odds_entries(db, match_ids=[match_id]),
            market=leg.market,
            kickoff_at=kickoff_at,
        )
        outcome = _selection_outcome(leg.selection)
        market_quote = quote_set.quote_for(outcome)
        market_probability = quote_set.consensus_probabilities.get(outcome)
        if not quote_set.is_ticket_eligible or market_quote is None or market_probability is None:
            continue

        reference = next(
            (
                latest_by_leg_stage[(leg.id, stage)]
                for stage in ("activation", "refresh", "generation")
                if (leg.id, stage) in latest_by_leg_stage
            ),
            None,
        )
        reference_bookmaker = getattr(reference, "bookmaker", None) or leg.bookmaker
        closing_snapshot_id = quote_set.snapshot_id if isinstance(quote_set.snapshot_id, int) else None
        if reference_bookmaker:
            same_book_line = next(
                (line for line in quote_set.bookmaker_lines if line.bookmaker == reference_bookmaker),
                None,
            )
            same_book_price = same_book_line.prices.get(outcome) if same_book_line else None
            if same_book_price is not None:
                previous = latest_by_leg_stage.get((leg.id, "closing_same_book"))
                if not _same_quote(
                    previous,
                    price=same_book_price,
                    bookmaker=reference_bookmaker,
                    odds_snapshot_id=closing_snapshot_id,
                    observed_at=quote_set.observed_at,
                ):
                    db.add(
                        TicketLegQuoteSnapshot(
                            ticket_leg_id=leg.id,
                            stage="closing_same_book",
                            revision=int(getattr(previous, "revision", 0) or 0) + 1,
                            odds_snapshot_id=closing_snapshot_id,
                            market=leg.market,
                            selection=leg.selection,
                            bookmaker=reference_bookmaker,
                            price=same_book_price,
                            observed_at=quote_set.observed_at,
                            market_probability=market_probability,
                            market_probability_method="devig_median_consensus",
                        )
                    )
                    created += 1

        market_snapshot_id = market_quote.snapshot_id if isinstance(market_quote.snapshot_id, int) else None
        previous = latest_by_leg_stage.get((leg.id, "closing_market"))
        if not _same_quote(
            previous,
            price=market_quote.price,
            bookmaker=market_quote.bookmaker,
            odds_snapshot_id=market_snapshot_id,
            observed_at=market_quote.observed_at,
        ):
            db.add(
                TicketLegQuoteSnapshot(
                    ticket_leg_id=leg.id,
                    stage="closing_market",
                    revision=int(getattr(previous, "revision", 0) or 0) + 1,
                    odds_entry_id=market_quote.entry_id,
                    odds_snapshot_id=market_snapshot_id,
                    market=leg.market,
                    selection=leg.selection,
                    bookmaker=market_quote.bookmaker,
                    price=market_quote.price,
                    observed_at=market_quote.observed_at,
                    market_probability=market_probability,
                    market_probability_method="devig_median_consensus",
                )
            )
            created += 1

    return created


def build_clv_report(rows: Iterable[tuple[int, int, TicketLegQuoteSnapshot]]) -> dict[str, Any]:
    """Build a coverage-aware CLV report from owned ticket quote snapshots."""

    grouped: dict[tuple[int, int], dict[str, TicketLegQuoteSnapshot]] = defaultdict(dict)
    for ticket_id, leg_id, snapshot in rows:
        stages = grouped[(int(ticket_id), int(leg_id))]
        current = stages.get(snapshot.stage)
        if current is None or _snapshot_rank(snapshot) > _snapshot_rank(current):
            stages[snapshot.stage] = snapshot

    items: list[dict[str, Any]] = []
    for (ticket_id, leg_id), snapshots in sorted(grouped.items()):
        reference_stage = next(
            (stage for stage in ("activation", "refresh", "generation") if stage in snapshots),
            "generation",
        )
        reference = snapshots.get(reference_stage)
        same_book = snapshots.get("closing_same_book")
        closing_market = snapshots.get("closing_market")
        metrics = calculate_clv(
            reference_price=float(reference.price) if reference is not None else None,
            same_book_closing_price=float(same_book.price) if same_book is not None else None,
            market_best_closing_price=float(closing_market.price) if closing_market is not None else None,
            reference_market_probability=(
                float(reference.market_probability)
                if reference is not None and reference.market_probability is not None
                else None
            ),
            closing_consensus_probability=(
                float(closing_market.market_probability)
                if closing_market is not None and closing_market.market_probability is not None
                else None
            ),
        )
        items.append(
            {
                "ticket_id": ticket_id,
                "ticket_leg_id": leg_id,
                "reference_stage": reference_stage if reference is not None else None,
                "same_book_clv_pct": metrics.same_book_clv_pct,
                "market_best_clv_pct": metrics.market_best_clv_pct,
                "consensus_clv_pp": metrics.consensus_clv_pp,
                "coverage": metrics.coverage,
                "unavailable_reasons": metrics.unavailable_reasons,
            }
        )

    def metric_summary(key: str) -> tuple[float, float | None, float | None]:
        values = [float(item[key]) for item in items if item[key] is not None]
        coverage = (100.0 * len(values) / len(items)) if items else 0.0
        average = sum(values) / len(values) if values else None
        positive = (100.0 * sum(value > 0 for value in values) / len(values)) if values else None
        return coverage, average, positive

    same_coverage, same_average, same_positive = metric_summary("same_book_clv_pct")
    market_coverage, market_average, market_positive = metric_summary("market_best_clv_pct")
    consensus_coverage, consensus_average, consensus_positive = metric_summary("consensus_clv_pp")
    return {
        "summary": {
            "leg_count": len(items),
            "same_book_coverage_pct": same_coverage,
            "market_best_coverage_pct": market_coverage,
            "consensus_coverage_pct": consensus_coverage,
            "average_same_book_clv_pct": same_average,
            "average_market_best_clv_pct": market_average,
            "average_consensus_clv_pp": consensus_average,
            "positive_same_book_pct": same_positive,
            "positive_market_best_pct": market_positive,
            "positive_consensus_pct": consensus_positive,
        },
        "items": items,
    }
