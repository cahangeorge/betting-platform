"""Materialize accepted immutable odds observations into canonical snapshots."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import OddsEntry
from app.models.odds_lineage import OddsQuote, OddsSnapshot
from app.models.provider_identity import MatchProviderMapping
from app.models.provider_observation import ProviderObservation
from app.providers.odds import (
    ODDS_OBSERVATION_CONTRACT_VERSION,
    OddsEventObservationV1,
    OddsQuoteV1,
    validate_odds_event_payload,
)

ODDS_MAPPING_VERSION = "canonical-odds-mapping/v1"
SUPPORTED_CANONICAL_MARKETS = frozenset({"1x2", "btts", "totals"})


class OddsObservationMaterializationError(ValueError):
    """The immutable observation cannot safely become canonical odds."""


@dataclass(frozen=True)
class OddsMaterializationResult:
    snapshot: OddsSnapshot
    quotes_written: int
    legacy_entries_written: int
    created: bool


def _safe_mapping(values: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for provider_key, canonical_key in values.items():
        if (
            not isinstance(provider_key, str)
            or not provider_key.strip()
            or not isinstance(canonical_key, str)
            or not canonical_key.strip()
            or len(provider_key) > 128
            or len(canonical_key) > 128
        ):
            raise OddsObservationMaterializationError("bookmaker mapping is invalid")
        result[provider_key.casefold()] = canonical_key.casefold()
    return result


def _is_fully_mapped(
    event: OddsEventObservationV1,
    *,
    bookmaker_mapping: Mapping[str, str],
    supported_markets: frozenset[str],
) -> bool:
    if event.quality != "complete" or not event.quotes:
        return False
    bookmakers = {quote.provider_bookmaker_key for quote in event.quotes}
    markets = {quote.market_key for quote in event.quotes}
    if event.expected_bookmaker_count is not None and event.expected_bookmaker_count != len(bookmakers):
        return False
    if event.expected_market_count is not None and event.expected_market_count != len(markets):
        return False
    return all(
        quote.provider_bookmaker_key in bookmaker_mapping
        and quote.market_key in supported_markets
        and not quote.selection_key.startswith("unmapped:")
        for quote in event.quotes
    )


def _legacy_1x2_groups(
    event: OddsEventObservationV1, *, bookmaker_mapping: Mapping[str, str], snapshot_complete: bool
) -> tuple[tuple[str, dict[str, OddsQuoteV1]], ...]:
    if not snapshot_complete:
        return ()
    grouped: dict[str, dict[str, OddsQuoteV1]] = defaultdict(dict)
    for quote in event.quotes:
        bookmaker = bookmaker_mapping.get(quote.provider_bookmaker_key)
        if (
            bookmaker is None
            or quote.market_key != "1x2"
            or quote.period_key != "full_time"
            or quote.line is not None
            or quote.status != "active"
            or quote.selection_key not in {"home", "draw", "away"}
        ):
            continue
        if quote.selection_key in grouped[bookmaker]:
            return ()
        grouped[bookmaker][quote.selection_key] = quote
    return tuple(
        (bookmaker, selections)
        for bookmaker, selections in sorted(grouped.items())
        if set(selections) == {"home", "draw", "away"}
    )


def _validate_observation(observation: ProviderObservation) -> OddsEventObservationV1:
    if (
        observation.capability != "odds"
        or observation.schema_version != "1.0"
        or observation.payload_json is None
        or observation.conflict_state != "clear"
    ):
        raise OddsObservationMaterializationError("provider observation is not eligible for odds materialization")
    try:
        event = validate_odds_event_payload(json.loads(observation.payload_json))
    except (ValueError, TypeError) as exc:
        raise OddsObservationMaterializationError("provider odds payload is invalid") from exc
    if (
        event.payload_digest != observation.payload_digest
        or event.source_event_id != observation.source_id
        or event.observed_at != observation.observed_at
    ):
        raise OddsObservationMaterializationError("provider odds observation lineage does not match its payload")
    return event


async def materialize_odds_observation(
    session: AsyncSession,
    observation: ProviderObservation,
    *,
    bookmaker_mapping: Mapping[str, str],
    mapping_version: str = ODDS_MAPPING_VERSION,
    supported_markets: frozenset[str] = SUPPORTED_CANONICAL_MARKETS,
) -> OddsMaterializationResult:
    """Persist one all-or-nothing canonical snapshot and optional 1X2 projection.

    The caller owns the outer transaction.  Policy and acquisition happen before
    this function; only an already accepted, clear immutable observation enters.
    """
    if not isinstance(mapping_version, str) or not mapping_version.strip() or len(mapping_version) > 128:
        raise OddsObservationMaterializationError("mapping_version is invalid")
    normalized_bookmakers = _safe_mapping(bookmaker_mapping)
    # Serialise all materialisation attempts for the immutable observation.  In
    # particular, this lock must precede the idempotency lookup: otherwise two
    # callers can both see no snapshot and race the unique observation link.
    locked_observation = await session.scalar(
        select(ProviderObservation).where(ProviderObservation.id == observation.id).with_for_update()
    )
    if locked_observation is None:
        raise OddsObservationMaterializationError("provider observation does not exist")
    event = _validate_observation(locked_observation)
    existing = await session.scalar(
        select(OddsSnapshot).where(OddsSnapshot.provider_observation_id == locked_observation.id)
    )
    if existing is not None:
        quote_count = len(
            (await session.scalars(select(OddsQuote.id).where(OddsQuote.odds_snapshot_id == existing.id))).all()
        )
        legacy_count = len(
            (await session.scalars(select(OddsEntry.id).where(OddsEntry.odds_snapshot_id == existing.id))).all()
        )
        return OddsMaterializationResult(existing, quote_count, legacy_count, False)

    mapping = await session.scalar(
        select(MatchProviderMapping).where(
            MatchProviderMapping.adapter_key == locked_observation.adapter_key,
            MatchProviderMapping.source_key == locked_observation.source_key,
            MatchProviderMapping.source_id == event.source_event_id,
            MatchProviderMapping.state == "accepted",
            MatchProviderMapping.valid_to.is_(None),
            MatchProviderMapping.match_id.is_not(None),
        )
    )
    if mapping is None or mapping.match_id is None:
        raise OddsObservationMaterializationError("accepted current provider match mapping is required")

    complete = _is_fully_mapped(
        event,
        bookmaker_mapping=normalized_bookmakers,
        supported_markets=supported_markets,
    )
    snapshot = OddsSnapshot(
        match_id=mapping.match_id,
        source=locked_observation.adapter_key,
        source_key=f"{locked_observation.source_key}:{locked_observation.observation_key}",
        provider_observation_id=locked_observation.id,
        contract_version=ODDS_OBSERVATION_CONTRACT_VERSION,
        payload_digest=locked_observation.payload_digest,
        mapping_version=mapping_version.strip(),
        observed_at=locked_observation.observed_at,
        quality="complete" if complete else "partial",
        metadata_json={
            "scope": event.scope,
            "source_event_id": event.source_event_id,
            "competition_key": event.competition_key,
            "quote_count": len(event.quotes),
        },
    )
    session.add(snapshot)
    await session.flush()
    for quote in event.quotes:
        session.add(
            OddsQuote(
                odds_snapshot_id=snapshot.id,
                source_quote_id=quote.source_quote_id,
                provider_bookmaker_key=quote.provider_bookmaker_key,
                bookmaker_key=normalized_bookmakers.get(quote.provider_bookmaker_key),
                provider_market_key=quote.provider_market_key,
                market_key=quote.market_key,
                period_key=quote.period_key,
                line=quote.line,
                selection_key=quote.selection_key,
                identity_digest=quote.identity_digest,
                price=quote.price,
                provider_updated_at=quote.provider_updated_at,
                status=quote.status,
                metadata_json={
                    "provider_bookmaker_name": quote.provider_bookmaker_name,
                    "selection_name": quote.selection_name,
                },
            )
        )
    legacy_groups = _legacy_1x2_groups(event, bookmaker_mapping=normalized_bookmakers, snapshot_complete=complete)
    for bookmaker, selections in legacy_groups:
        session.add(
            OddsEntry(
                match_id=mapping.match_id,
                odds_snapshot_id=snapshot.id,
                bookmaker=bookmaker,
                market="1x2",
                home_odds=float(selections["home"].price),
                draw_odds=float(selections["draw"].price),
                away_odds=float(selections["away"].price),
                timestamp=locked_observation.observed_at,
            )
        )
    await session.flush()
    snapshot.metadata_json = {
        **(snapshot.metadata_json or {}),
        "legacy_1x2_projection_count": len(legacy_groups),
    }
    return OddsMaterializationResult(snapshot, len(event.quotes), len(legacy_groups), True)
