"""Read-only, policy-gated Sportmonks Football v3 odds adapter.

This module deliberately contains no activation switch.  The registry is the
single approval boundary, while a token is only ever placed into a request at
the final HTTP boundary.  Callers receive normalized Provider Envelope v2
records, never raw upstream bodies or request URLs.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

import httpx

from app.config import Settings
from app.providers.contracts import ProviderCapability, ProviderExecutionContext, ProviderRecordEnvelopeV2
from app.providers.odds import OddsEventObservationV1, OddsQuoteV1
from app.providers.registry import DEFAULT_PROVIDER_REGISTRY, ProviderRegistry

SPORTMONKS_ADAPTER_KEY = "sportmonks-v3-odds"
SPORTMONKS_SOURCE_KEY = "sportmonks-football-v3-standard-odds"
SPORTMONKS_ADAPTER_VERSION = "sportmonks-odds/v1"
SPORTMONKS_TRANSPORT_VERSION = "httpx-json/v1"
SPORTMONKS_API_ORIGIN = "https://api.sportmonks.com"
SPORTMONKS_PREMATCH_PATH = "/v3/football/odds/pre-match/latest"
SPORTMONKS_INPLAY_PATH = "/v3/football/odds/inplay/latest"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_ITEMS = 5_000


class SportmonksOddsAdapterError(RuntimeError):
    """Safe public error; never include a request URL, query, or credential."""

    def __init__(self, message: str, *, reason_code: str = "schema_error") -> None:
        super().__init__(message)
        self.reason_code = reason_code


class _SportmonksQueryAuthTransport(httpx.AsyncBaseTransport):
    """Attach query authentication beneath httpx's client logging boundary.

    ``httpx.AsyncClient`` logs the request it owns after a response is returned.
    The client-owned request deliberately contains only public query parameters;
    this transport creates the authenticated upstream request immediately before
    dispatch.  That preserves query-token authentication without allowing the
    ordinary ``httpx`` INFO line to serialize the token.
    """

    def __init__(self, upstream: httpx.AsyncBaseTransport, *, api_token: str) -> None:
        self._upstream = upstream
        self._api_token = api_token

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        authenticated_url = request.url.copy_merge_params({"api_token": self._api_token})
        authenticated_request = httpx.Request(
            request.method,
            authenticated_url,
            headers=request.headers,
            content=request.content,
            extensions=request.extensions,
        )
        return await self._upstream.handle_async_request(authenticated_request)

    async def aclose(self) -> None:
        await self._upstream.aclose()


def _utc(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise SportmonksOddsAdapterError(f"Sportmonks {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SportmonksOddsAdapterError(f"Sportmonks {label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SportmonksOddsAdapterError(f"Sportmonks {label} is invalid")
    return parsed.astimezone(UTC)


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise SportmonksOddsAdapterError(f"Sportmonks {label} is invalid")
    return str(value).strip()


def _price(value: object) -> Decimal:
    if isinstance(value, bool):
        raise SportmonksOddsAdapterError("Sportmonks price is invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SportmonksOddsAdapterError("Sportmonks price is invalid") from exc
    if not parsed.is_finite() or parsed <= 1:
        raise SportmonksOddsAdapterError("Sportmonks price is invalid")
    return parsed


def _line(value: object) -> Decimal:
    if isinstance(value, bool):
        raise SportmonksOddsAdapterError("Sportmonks line is invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SportmonksOddsAdapterError("Sportmonks line is invalid") from exc
    if not parsed.is_finite():
        raise SportmonksOddsAdapterError("Sportmonks line is invalid")
    return parsed


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SportmonksOddsAdapterError(f"Sportmonks {label} is invalid")
    return value


def _participant(fixture: Mapping[str, Any], location: str) -> str:
    participants = fixture.get("participants")
    if not isinstance(participants, Sequence) or isinstance(participants, (str, bytes)):
        raise SportmonksOddsAdapterError("Sportmonks fixture participants are invalid")
    for participant in participants:
        item = _mapping(participant, label="fixture participant")
        meta = item.get("meta")
        if isinstance(meta, Mapping) and str(meta.get("location", "")).casefold() == location:
            return _text(item.get("name"), label=f"{location} participant")
    raise SportmonksOddsAdapterError("Sportmonks fixture participants are invalid")


def _scope_path(scope: str) -> str:
    normalized = str(scope).strip().casefold()
    if normalized == "prematch":
        return SPORTMONKS_PREMATCH_PATH
    if normalized == "inplay":
        return SPORTMONKS_INPLAY_PATH
    raise SportmonksOddsAdapterError("Sportmonks scope is invalid")


def _market_key(market: Mapping[str, Any]) -> str:
    provider_id = _text(market.get("id"), label="market id")
    name = _text(market.get("name", provider_id), label="market name").casefold()
    aliases = {
        "1x2": "1x2",
        "3 way result": "1x2",
        "fulltime result": "1x2",
        "match result": "1x2",
        "match winner": "1x2",
        "both teams to score": "btts",
        "goals over/under": "totals",
        "over/under": "totals",
        "total goals": "totals",
    }
    return aliases.get(name, f"unmapped:{provider_id}")


def _selection_key(label: str) -> str:
    normalized = label.casefold()
    aliases = {
        "1": "home",
        "home": "home",
        "x": "draw",
        "draw": "draw",
        "2": "away",
        "away": "away",
        "yes": "yes",
        "no": "no",
        "over": "over",
        "under": "under",
    }
    return aliases.get(normalized, f"unmapped:{hashlib.sha256(normalized.encode()).hexdigest()[:16]}")


class SportmonksOddsAdapter:
    """Maps bounded Sportmonks v3 include responses to strict odds observations."""

    def __init__(
        self,
        settings: Settings,
        *,
        registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._transport = transport

    async def fetch_latest_odds(
        self,
        *,
        scope: str,
        job_id: str,
        run_id: str,
        correlation_id: str,
        context: ProviderExecutionContext = ProviderExecutionContext.PRODUCTION,
        observed_at: datetime | None = None,
    ) -> tuple[ProviderRecordEnvelopeV2, ...]:
        """Fetch one bounded page after policy and credential checks.

        Query authentication is attached only beneath the HTTP client logging
        boundary. Redirects are disabled so it cannot leak to another origin.
        """
        self._registry.require_operation(
            SPORTMONKS_ADAPTER_KEY, SPORTMONKS_SOURCE_KEY, "fetch_latest_odds", context=context
        )
        token = self._settings.sportmonks_api_token
        token_value = token.get_secret_value().strip() if token is not None else ""
        if not token_value:
            raise SportmonksOddsAdapterError("Sportmonks credentials are unavailable", reason_code="credential_error")
        path = _scope_path(scope)
        requested_at = (observed_at or datetime.now(UTC)).astimezone(UTC)
        upstream_transport = self._transport or httpx.AsyncHTTPTransport()
        transport = _SportmonksQueryAuthTransport(upstream_transport, api_token=token_value)
        try:
            async with httpx.AsyncClient(
                base_url=SPORTMONKS_API_ORIGIN,
                transport=transport,
                follow_redirects=False,
                timeout=self._settings.sportmonks_timeout_seconds,
            ) as client:
                async with client.stream(
                    "GET",
                    path,
                    params={
                        "include": "fixture;fixture.participants;fixture.league;bookmaker;market",
                    },
                ) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            declared_size = int(content_length)
                        except ValueError:
                            raise SportmonksOddsAdapterError("Sportmonks response content length is invalid") from None
                        if declared_size < 0 or declared_size > MAX_RESPONSE_BYTES:
                            raise SportmonksOddsAdapterError("Sportmonks response exceeds the byte limit")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise SportmonksOddsAdapterError("Sportmonks response exceeds the byte limit")
                        chunks.extend(chunk)
                    raw = bytes(chunks)
        except httpx.TimeoutException:
            raise SportmonksOddsAdapterError("Sportmonks odds request failed", reason_code="timeout") from None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                reason_code = "quota_exhausted"
            elif exc.response.status_code >= 500:
                reason_code = "upstream_5xx"
            else:
                reason_code = "upstream_http_error"
            raise SportmonksOddsAdapterError("Sportmonks odds request failed", reason_code=reason_code) from None
        except (httpx.HTTPError, httpx.InvalidURL):
            # httpx exceptions retain the full request URL, including query
            # authentication. Do not chain that object into logs/tracebacks.
            raise SportmonksOddsAdapterError("Sportmonks odds request failed", reason_code="transport_error") from None
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SportmonksOddsAdapterError("Sportmonks response is not valid JSON") from exc
        rows = _mapping(body, label="response").get("data")
        if not isinstance(rows, list) or len(rows) > MAX_RESPONSE_ITEMS:
            raise SportmonksOddsAdapterError("Sportmonks response items are invalid")
        return self._envelopes(
            rows,
            scope=scope,
            observed_at=requested_at,
            job_id=job_id,
            run_id=run_id,
            correlation_id=correlation_id,
        )

    @staticmethod
    def _envelopes(
        rows: list[object], *, scope: str, observed_at: datetime, job_id: str, run_id: str, correlation_id: str
    ) -> tuple[ProviderRecordEnvelopeV2, ...]:
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        fixtures: dict[str, Mapping[str, Any]] = {}
        for raw_row in rows:
            row = _mapping(raw_row, label="odds row")
            fixture = _mapping(row.get("fixture"), label="fixture")
            fixture_id = _text(row.get("fixture_id", fixture.get("id")), label="fixture id")
            if fixture_id in fixtures and fixtures[fixture_id] != fixture:
                raise SportmonksOddsAdapterError("Sportmonks fixture identity is ambiguous")
            fixtures[fixture_id] = fixture
            grouped[fixture_id].append(row)
        envelopes: list[ProviderRecordEnvelopeV2] = []
        for fixture_id in sorted(grouped):
            fixture = fixtures[fixture_id]
            league = _mapping(fixture.get("league"), label="fixture league")
            quotes = tuple(
                SportmonksOddsAdapter._quote(row, fixture_id=fixture_id, observed_at=observed_at)
                for row in grouped[fixture_id]
            )
            mapped_market_count = len(
                {quote.market_key for quote in quotes if not quote.market_key.startswith("unmapped:")}
            )
            bookmaker_count = len({quote.provider_bookmaker_key for quote in quotes})
            event = OddsEventObservationV1(
                source_event_id=fixture_id,
                sport_key="football",
                competition_key=_text(league.get("id"), label="league id"),
                commence_time=_utc(fixture.get("starting_at"), label="fixture starting_at"),
                home_team=_participant(fixture, "home"),
                away_team=_participant(fixture, "away"),
                observed_at=observed_at,
                scope=str(scope).strip().casefold(),
                quality=(
                    "partial" if any(quote.market_key.startswith("unmapped:") for quote in quotes) else "complete"
                ),
                quotes=quotes,
                expected_bookmaker_count=bookmaker_count,
                expected_market_count=mapped_market_count,
            )
            envelopes.append(
                ProviderRecordEnvelopeV2.from_payload(
                    adapter_key=SPORTMONKS_ADAPTER_KEY,
                    source_key=SPORTMONKS_SOURCE_KEY,
                    capability=ProviderCapability.ODDS,
                    source_id=fixture_id,
                    observed_at=observed_at,
                    payload=event.payload,
                    adapter_version=SPORTMONKS_ADAPTER_VERSION,
                    transport_version=SPORTMONKS_TRANSPORT_VERSION,
                    job_id=_text(job_id, label="job id"),
                    run_id=_text(run_id, label="run id"),
                    correlation_id=_text(correlation_id, label="correlation id"),
                    freshness={"as_of": observed_at.isoformat().replace("+00:00", "Z"), "ttl_seconds": 300},
                    provenance={"source_revision": SPORTMONKS_ADAPTER_VERSION},
                )
            )
        return tuple(envelopes)

    @staticmethod
    def _quote(row: Mapping[str, Any], *, fixture_id: str, observed_at: datetime) -> OddsQuoteV1:
        bookmaker = _mapping(row.get("bookmaker"), label="bookmaker")
        market = _mapping(row.get("market"), label="market")
        selection_name = _text(row.get("label"), label="selection label")
        selection_key = _selection_key(selection_name)
        update_value = row.get("latest_bookmaker_update") or row.get("updated_at")
        updated_at = _utc(update_value, label="odds updated_at") if update_value else observed_at
        line = row.get("total") if row.get("total") is not None else row.get("handicap")
        stopped = row.get("stopped") is True
        suspended = row.get("suspended") is True
        return OddsQuoteV1(
            source_quote_id=_text(row.get("id"), label="odds id"),
            provider_bookmaker_key=_text(bookmaker.get("id"), label="bookmaker id"),
            provider_bookmaker_name=_text(bookmaker.get("name"), label="bookmaker name"),
            provider_market_key=_text(market.get("id"), label="market id"),
            market_key=_market_key(market),
            period_key="full_time",
            line=None if line is None else _line(line),
            selection_key=selection_key,
            selection_name=selection_name,
            price=_price(row.get("value")),
            provider_updated_at=updated_at,
            status="stopped" if stopped else ("suspended" if suspended else "active"),
        )
