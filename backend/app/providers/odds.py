"""Strict provider-agnostic odds observation contract.

The common shape is row-per-selection.  It deliberately does not inherit the
legacy three-column ``OddsEntry`` projection, so totals, handicaps and future
markets retain their actual identity and line.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

ODDS_OBSERVATION_CONTRACT_VERSION = "odds-observation/v1"
ODDS_OBSERVATION_SCHEMA_VERSION = "1.0"
ODDS_EVENTS_CONTRACT_VERSION = ODDS_OBSERVATION_CONTRACT_VERSION  # compatibility export
MAX_ODDS_QUOTES_PER_EVENT = 5_000
MAX_ODDS_KEY_LENGTH = 128
_KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_EVENT_FIELDS = frozenset(
    {
        "contract_version",
        "schema_version",
        "source_event_id",
        "sport_key",
        "competition_key",
        "commence_time",
        "home_team",
        "away_team",
        "observed_at",
        "scope",
        "quality",
        "expected_bookmaker_count",
        "expected_market_count",
        "quotes",
    }
)
_QUOTE_FIELDS = frozenset(
    {
        "source_quote_id",
        "provider_bookmaker_key",
        "provider_bookmaker_name",
        "provider_market_key",
        "market_key",
        "period_key",
        "line",
        "selection_key",
        "selection_name",
        "price",
        "provider_updated_at",
        "status",
    }
)


def _text(value: object, *, label: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not (normalized := " ".join(value.split())) or len(normalized) > maximum:
        raise ValueError(f"{label} must be a nonempty bounded string")
    return normalized


def _key(value: object, *, label: str) -> str:
    normalized = _text(value, label=label, maximum=MAX_ODDS_KEY_LENGTH).casefold().replace(" ", "_")
    if not _KEY.fullmatch(normalized):
        raise ValueError(f"{label} must be a canonical provider key")
    return normalized


def _utc(value: object, *, label: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{label} must be an ISO timezone-aware timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: object, *, label: str, minimum: Decimal | None = None) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a finite decimal") from exc
    if not result.is_finite() or (minimum is not None and result <= minimum):
        raise ValueError(f"{label} must be greater than {minimum}")
    return result.normalize()


def _optional_count(value: object, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > MAX_ODDS_QUOTES_PER_EVENT:
        raise ValueError(f"{label} must be a bounded nonnegative integer")
    return value


def _line_token(value: Decimal | None) -> str:
    return "none" if value is None else format(value, "f")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class OddsQuoteV1:
    source_quote_id: str
    provider_bookmaker_key: str
    provider_bookmaker_name: str
    provider_market_key: str
    market_key: str
    period_key: str
    selection_key: str
    selection_name: str
    price: Decimal
    provider_updated_at: datetime
    line: Decimal | None = None
    status: str = "active"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_quote_id", _text(self.source_quote_id, label="source_quote_id"))
        for name in ("provider_bookmaker_key", "provider_market_key", "market_key", "period_key", "selection_key"):
            object.__setattr__(self, name, _key(getattr(self, name), label=name))
        object.__setattr__(
            self, "provider_bookmaker_name", _text(self.provider_bookmaker_name, label="provider_bookmaker_name")
        )
        object.__setattr__(self, "selection_name", _text(self.selection_name, label="selection_name"))
        object.__setattr__(self, "price", _decimal(self.price, label="price", minimum=Decimal("1")))
        if self.price > Decimal("1000000"):
            raise ValueError("price exceeds the supported bound")
        object.__setattr__(self, "line", None if self.line is None else _decimal(self.line, label="line"))
        object.__setattr__(self, "provider_updated_at", _utc(self.provider_updated_at, label="provider_updated_at"))
        normalized_status = _key(self.status, label="status")
        if normalized_status not in {"active", "suspended", "stopped"}:
            raise ValueError("status must be active, suspended or stopped")
        object.__setattr__(self, "status", normalized_status)

    @property
    def identity(self) -> tuple[str, str, str, str, str]:
        return (
            self.provider_bookmaker_key,
            self.market_key,
            self.period_key,
            _line_token(self.line),
            self.selection_key,
        )

    @property
    def identity_digest(self) -> str:
        return _digest(self.identity)

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "source_quote_id": self.source_quote_id,
            "provider_bookmaker_key": self.provider_bookmaker_key,
            "provider_bookmaker_name": self.provider_bookmaker_name,
            "provider_market_key": self.provider_market_key,
            "market_key": self.market_key,
            "period_key": self.period_key,
            "line": None if self.line is None else format(self.line, "f"),
            "selection_key": self.selection_key,
            "selection_name": self.selection_name,
            "price": format(self.price, "f"),
            "provider_updated_at": _timestamp(self.provider_updated_at),
            "status": self.status,
        }


@dataclass(frozen=True)
class OddsEventObservationV1:
    source_event_id: str
    sport_key: str
    competition_key: str
    commence_time: datetime
    home_team: str
    away_team: str
    observed_at: datetime
    scope: str
    quality: str
    quotes: tuple[OddsQuoteV1, ...] = field(default_factory=tuple)
    expected_bookmaker_count: int | None = None
    expected_market_count: int | None = None
    contract_version: str = ODDS_OBSERVATION_CONTRACT_VERSION
    schema_version: str = ODDS_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != ODDS_OBSERVATION_CONTRACT_VERSION or self.schema_version != "1.0":
            raise ValueError("Unsupported odds observation contract version")
        object.__setattr__(self, "source_event_id", _text(self.source_event_id, label="source_event_id"))
        object.__setattr__(self, "sport_key", _key(self.sport_key, label="sport_key"))
        object.__setattr__(self, "competition_key", _key(self.competition_key, label="competition_key"))
        object.__setattr__(self, "commence_time", _utc(self.commence_time, label="commence_time"))
        object.__setattr__(self, "observed_at", _utc(self.observed_at, label="observed_at"))
        object.__setattr__(self, "home_team", _text(self.home_team, label="home_team"))
        object.__setattr__(self, "away_team", _text(self.away_team, label="away_team"))
        if self.home_team.casefold() == self.away_team.casefold():
            raise ValueError("home_team and away_team must differ")
        normalized_scope = _key(self.scope, label="scope")
        if normalized_scope not in {"prematch", "inplay"}:
            raise ValueError("scope must be prematch or inplay")
        object.__setattr__(self, "scope", normalized_scope)
        normalized_quality = _key(self.quality, label="quality")
        if normalized_quality not in {"complete", "partial"}:
            raise ValueError("quality must be complete or partial")
        object.__setattr__(self, "quality", normalized_quality)
        if len(self.quotes) > MAX_ODDS_QUOTES_PER_EVENT:
            raise ValueError("odds observation has too many quotes")
        identities = [quote.identity for quote in self.quotes]
        if len(identities) != len(set(identities)):
            raise ValueError("odds observation contains duplicate quote identities")
        object.__setattr__(
            self,
            "expected_bookmaker_count",
            _optional_count(self.expected_bookmaker_count, label="expected_bookmaker_count"),
        )
        object.__setattr__(
            self,
            "expected_market_count",
            _optional_count(self.expected_market_count, label="expected_market_count"),
        )
        if self.quality == "complete" and not self.quotes:
            raise ValueError("complete odds observations require at least one quote")

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "schema_version": self.schema_version,
            "source_event_id": self.source_event_id,
            "sport_key": self.sport_key,
            "competition_key": self.competition_key,
            "commence_time": _timestamp(self.commence_time),
            "home_team": self.home_team,
            "away_team": self.away_team,
            "observed_at": _timestamp(self.observed_at),
            "scope": self.scope,
            "quality": self.quality,
            "expected_bookmaker_count": self.expected_bookmaker_count,
            "expected_market_count": self.expected_market_count,
            "quotes": [quote.payload for quote in sorted(self.quotes, key=lambda item: item.identity)],
        }

    @property
    def payload_digest(self) -> str:
        return _digest(self.payload)


# Compatibility names for the first draft; all now represent the strict v1 row contract.
OddsSelectionQuote = OddsQuoteV1
OddsEventSnapshot = OddsEventObservationV1


def _exact_mapping(value: object, *, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value) or set(value) != fields:
        raise ValueError(f"{label} must contain the exact v1 fields")
    return value


def validate_odds_event_payload(payload: Mapping[str, Any]) -> OddsEventObservationV1:
    event = _exact_mapping(payload, fields=_EVENT_FIELDS, label="odds observation")
    raw_quotes = event["quotes"]
    if not isinstance(raw_quotes, list):
        raise ValueError("quotes must be a JSON array")
    quotes: list[OddsQuoteV1] = []
    for raw_quote in raw_quotes:
        quote = _exact_mapping(raw_quote, fields=_QUOTE_FIELDS, label="odds quote")
        quotes.append(OddsQuoteV1(**quote))
    return OddsEventObservationV1(**{**event, "quotes": tuple(quotes)})


def is_finite_json_number(value: object) -> bool:
    """Small reusable guard for adapters before Decimal conversion."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
