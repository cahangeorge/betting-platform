"""Pure OddsHarvester record to common odds-contract conversion.

This adapter does not start a browser and does not persist data.  It is the
normalization boundary used by the explicitly bounded browser fallback lane.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlsplit

from app.providers.contracts import ProviderCapability, ProviderRecordEnvelopeV2
from app.providers.odds import MAX_ODDS_QUOTES_PER_EVENT, OddsEventObservationV1, OddsQuoteV1

MAX_ODDSHARVESTER_RECORD_BYTES = 4 * 1024 * 1024
MAX_ODDSHARVESTER_MARKETS = 128
MAX_ODDSHARVESTER_BOOKMAKER_ROWS = 2_000
ODDSHARVESTER_ADAPTER_KEY = "oddsharvester"
ODDSHARVESTER_SOURCE_KEY = "oddsportal"
ODDSHARVESTER_ADAPTER_VERSION = "oddsharvester-odds/v1"
ODDSHARVESTER_TRANSPORT_VERSION = "browser-json/v1"

_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "authorization", "cookie", "password", "secret", "token")
_SAFE_KEY = re.compile(r"[^a-z0-9._:-]+")
_EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{3,255}$")
_TOTALS = re.compile(r"^over_under_(?P<line>-?\d+(?:_\d+)?)$")
_MARKET_SELECTIONS: dict[str, tuple[str, tuple[tuple[str, str, str], ...]]] = {
    "1x2": ("1x2", (("1", "home", "Home"), ("X", "draw", "Draw"), ("2", "away", "Away"))),
    "double_chance": (
        "double_chance",
        (("1X", "home_draw", "Home or draw"), ("12", "home_away", "Home or away"), ("X2", "draw_away", "Draw or away")),
    ),
    "dnb": ("draw_no_bet", (("1", "home", "Home"), ("2", "away", "Away"))),
    "home_away": ("match_winner", (("1", "home", "Home"), ("2", "away", "Away"))),
    "match_winner": ("match_winner", (("1", "home", "Home"), ("2", "away", "Away"))),
    "btts": ("btts", (("Yes", "yes", "Yes"), ("No", "no", "No"))),
}


def _bounded_json_size(record: Mapping[str, Any]) -> None:
    try:
        encoded = json.dumps(record, allow_nan=False, separators=(",", ":")).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("OddsHarvester record must be finite JSON") from exc
    if len(encoded) > MAX_ODDSHARVESTER_RECORD_BYTES:
        raise ValueError("OddsHarvester record exceeds the supported size")


def _reject_sensitive_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).casefold().replace("-", "_")
            if any(part in key for part in _SENSITIVE_KEY_PARTS):
                raise ValueError("OddsHarvester record contains a sensitive field")
            _reject_sensitive_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive_keys(child)


def _required_text(value: Any, *, field: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not (result := " ".join(value.split())) or len(result) > maximum:
        raise ValueError(f"{field} must be a nonempty bounded string")
    return result


def _canonical_key(value: str, *, prefix: str) -> str:
    normalized = _SAFE_KEY.sub("_", value.casefold()).strip("_.:-")
    if not normalized:
        normalized = hashlib.sha256(value.encode()).hexdigest()[:16]
    result = f"{prefix}:{normalized}"
    if len(result) > 128:
        result = f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()}"
    return result


def _timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a timestamp string")
    normalized = value.strip()
    if normalized.endswith(" UTC"):
        normalized = normalized[:-4] + "+00:00"
    elif normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-like timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _source_event_id(record: Mapping[str, Any]) -> str:
    link = _required_text(record.get("match_link"), field="match_link", maximum=2_048)
    parsed = urlsplit(link)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not (parsed.hostname == "oddsportal.com" or parsed.hostname.endswith(".oddsportal.com"))
    ):
        raise ValueError("match_link must be an HTTPS OddsPortal URL")
    explicit = record.get("match_id")
    explicit_id = explicit.strip() if isinstance(explicit, str) and _EVENT_ID.fullmatch(explicit.strip()) else None
    is_h2h = any(segment.casefold() == "h2h" for segment in parsed.path.split("/") if segment)
    if parsed.fragment:
        event_id = parsed.fragment.split(":", 1)[0].split(";", 1)[0]
        if not _EVENT_ID.fullmatch(event_id):
            raise ValueError("match_link does not contain a safe event identifier")
        if explicit_id is not None and explicit_id != event_id:
            raise ValueError("match_id must match the H2H URL event identifier")
        return event_id
    if is_h2h:
        raise ValueError("H2H match_link must contain a safe event identifier fragment")
    if explicit_id is not None:
        return explicit_id
    slug = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if not _EVENT_ID.fullmatch(slug):
        raise ValueError("match_link does not contain a safe event identifier")
    return slug


def _decimal_price(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("odd must be a finite decimal greater than one")
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("odd must be a finite decimal greater than one") from exc
    if not price.is_finite() or price <= 1 or price > 1_000_000:
        raise ValueError("odd must be a finite decimal greater than one")
    return price


def _period(value: Any) -> str:
    raw = "FullTime" if value in (None, "") else _required_text(value, field="period", maximum=64)
    aliases = {
        "fulltime": "full_time",
        "fullincludingot": "full_including_ot",
        "firsthalf": "first_half",
        "secondhalf": "second_half",
    }
    compact = re.sub(r"[^a-z0-9]", "", raw.casefold())
    return aliases.get(compact, _canonical_key(raw, prefix="period"))


def _market_definition(
    market_key: str, row: Mapping[str, Any]
) -> tuple[str, Decimal | None, tuple[tuple[str, str, str], ...]] | None:
    base = market_key.removesuffix("_market")
    if definition := _MARKET_SELECTIONS.get(base):
        canonical, selections = definition
        return canonical, None, selections
    if match := _TOTALS.fullmatch(base):
        line = Decimal(match.group("line").replace("_", "."))
        return "totals", line, (("Over", "over", "Over"), ("Under", "under", "Under"))
    if base.startswith("european_handicap"):
        raw_line = row.get("handicap") or row.get("line")
        if raw_line is None:
            return None
        return "european_handicap", Decimal(str(raw_line)), _MARKET_SELECTIONS["1x2"][1]
    if base.startswith("asian_handicap"):
        raw_line = row.get("handicap") or row.get("line")
        if raw_line is None:
            return None
        return "asian_handicap", Decimal(str(raw_line)), (("1", "home", "Home"), ("2", "away", "Away"))
    return None


def convert_oddsharvester_record(
    record: Mapping[str, Any],
    *,
    sport_key: str = "football",
    scope: str = "prematch",
) -> OddsEventObservationV1:
    """Convert one bounded OddsHarvester match record without side effects."""

    if not isinstance(record, Mapping):
        raise ValueError("OddsHarvester record must be an object")
    _bounded_json_size(record)
    _reject_sensitive_keys(record)

    source_event_id = _source_event_id(record)
    observed_at = _timestamp(record.get("scraped_date"), field="scraped_date")
    commence_time = _timestamp(record.get("match_date"), field="match_date")
    home_team = _required_text(record.get("home_team"), field="home_team")
    away_team = _required_text(record.get("away_team"), field="away_team")
    competition = _required_text(record.get("league_name"), field="league_name")

    market_items = [(key, value) for key, value in record.items() if isinstance(key, str) and key.endswith("_market")]
    if len(market_items) > MAX_ODDSHARVESTER_MARKETS:
        raise ValueError("OddsHarvester record contains too many markets")

    quotes: list[OddsQuoteV1] = []
    incomplete = False
    bookmaker_keys: set[str] = set()
    supported_markets: set[str] = set()
    row_count = 0
    for raw_market_key, rows in market_items:
        if not isinstance(rows, list):
            incomplete = True
            continue
        for row in rows:
            row_count += 1
            if row_count > MAX_ODDSHARVESTER_BOOKMAKER_ROWS:
                raise ValueError("OddsHarvester record contains too many bookmaker rows")
            if not isinstance(row, Mapping):
                incomplete = True
                continue
            definition = _market_definition(raw_market_key, row)
            if definition is None:
                incomplete = True
                continue
            canonical_market, line, selections = definition
            bookmaker_name = _required_text(row.get("bookmaker_name"), field="bookmaker_name")
            bookmaker_key = _canonical_key(bookmaker_name, prefix="bookmaker")
            period_key = _period(row.get("period"))
            provider_market_key = _canonical_key(raw_market_key.removesuffix("_market"), prefix="market")
            bookmaker_keys.add(bookmaker_key)
            supported_markets.add(canonical_market)
            for raw_selection, selection_key, selection_name in selections:
                raw_price = row.get(raw_selection)
                if raw_price is None:
                    aliases = {
                        "Yes": ("odds_yes", "btts_yes"),
                        "No": ("odds_no", "btts_no"),
                        "Over": ("odds_over",),
                        "Under": ("odds_under",),
                    }
                    raw_price = next(
                        (row.get(alias) for alias in aliases.get(raw_selection, ()) if row.get(alias) is not None), None
                    )
                if raw_price is None:
                    incomplete = True
                    continue
                price = _decimal_price(raw_price)
                identity = "|".join(
                    (source_event_id, bookmaker_key, provider_market_key, period_key, str(line), selection_key)
                )
                quotes.append(
                    OddsQuoteV1(
                        source_quote_id=hashlib.sha256(identity.encode()).hexdigest(),
                        provider_bookmaker_key=bookmaker_key,
                        provider_bookmaker_name=bookmaker_name,
                        provider_market_key=provider_market_key,
                        market_key=canonical_market,
                        period_key=period_key,
                        line=line,
                        selection_key=selection_key,
                        selection_name=selection_name,
                        price=price,
                        provider_updated_at=observed_at,
                    )
                )
                if len(quotes) > MAX_ODDS_QUOTES_PER_EVENT:
                    raise ValueError("OddsHarvester record contains too many quotes")

    if not quotes:
        incomplete = True
    return OddsEventObservationV1(
        source_event_id=source_event_id,
        sport_key=sport_key,
        competition_key=_canonical_key(competition, prefix="competition"),
        commence_time=commence_time,
        home_team=home_team,
        away_team=away_team,
        observed_at=observed_at,
        scope=scope,
        quality="partial" if incomplete else "complete",
        quotes=tuple(quotes),
        expected_bookmaker_count=len(bookmaker_keys),
        expected_market_count=len(supported_markets),
    )


def oddsharvester_record_envelope(
    record: Mapping[str, Any],
    *,
    job_id: str,
    run_id: str,
    correlation_id: str,
    sport_key: str = "football",
    scope: str = "prematch",
) -> ProviderRecordEnvelopeV2:
    """Wrap a converted fallback record in the canonical provider envelope."""

    observation = convert_oddsharvester_record(record, sport_key=sport_key, scope=scope)
    return ProviderRecordEnvelopeV2.from_payload(
        adapter_key=ODDSHARVESTER_ADAPTER_KEY,
        source_key=ODDSHARVESTER_SOURCE_KEY,
        capability=ProviderCapability.ODDS,
        source_id=observation.source_event_id,
        observed_at=observation.observed_at,
        payload=observation.payload,
        adapter_version=ODDSHARVESTER_ADAPTER_VERSION,
        transport_version=ODDSHARVESTER_TRANSPORT_VERSION,
        job_id=_required_text(job_id, field="job_id"),
        run_id=_required_text(run_id, field="run_id"),
        correlation_id=_required_text(correlation_id, field="correlation_id"),
        freshness={"as_of": observation.payload["observed_at"], "ttl_seconds": 300},
        provenance={"source_revision": ODDSHARVESTER_ADAPTER_VERSION},
    )
