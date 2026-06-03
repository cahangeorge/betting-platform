"""Betfair Exchange API client with SSO login.

Docs: https://developer.betfair.com/
Free delayed app key: no cost, 60s delayed data
Live app key: £499 one-time activation
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

DEFAULT_BASE = "https://api.betfair.com/exchange/betting/json-rpc/v1"
AUTH_URL = "https://identitysso.betfair.com/api/session"


class BetfairClient:
    def __init__(self, app_key: str | None = None, session_token: str | None = None) -> None:
        cfg = get_settings()
        self.app_key = app_key or cfg.betfair_app_key or ""
        self.session_token = session_token or cfg.betfair_session_token or ""
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "X-Application": self.app_key,
            "X-Authentication": self.session_token,
            "Content-Type": "application/json",
        }

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Auth ──────────────────────────────────────────

    async def login(self, username: str | None = None, password: str | None = None) -> str:
        """SSO login — required for both delayed (free) and live app keys."""
        cfg = get_settings()
        uname = username or cfg.betfair_username or ""
        pwd = password or cfg.betfair_password or ""
        if not uname or not pwd:
            raise RuntimeError(
                "Betfair credentials not configured — set BETFAIR_USERNAME and BETFAIR_PASSWORD"
            )
        client = await self._ensure_client()
        resp = await client.post(
            AUTH_URL,
            data={"username": uname, "password": pwd},
            headers={"X-Application": self.app_key, "Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "SUCCESS":
            raise RuntimeError(f"Betfair login failed: {data.get('error', 'unknown')}")
        self.session_token = data["token"]
        return self.session_token

    # ── API calls ────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call(self, method: str, params: dict[str, Any], endpoint: str | None = None) -> Any:
        client = await self._ensure_client()
        payload = [{"jsonrpc": "2.0", "method": method, "params": params, "id": 1}]
        resp = await client.post(
            endpoint or DEFAULT_BASE,
            headers=self._headers(),
            content=json.dumps(payload),
        )
        resp.raise_for_status()
        data = resp.json()
        result = data[0] if isinstance(data, list) and len(data) > 0 else data
        if "error" in result:
            raise RuntimeError(f"Betfair API error: {result['error']}")
        return result.get("result", {})

    async def list_event_types(self) -> list[dict[str, Any]]:
        return await self._call("listEventTypes", {"filter": {}})

    async def list_competitions(self) -> list[dict[str, Any]]:
        return await self._call("listCompetitions", {"filter": {}})

    async def list_events(self, competition_ids: list[str]) -> list[dict[str, Any]]:
        return await self._call("listEvents", {"filter": {"competitionIds": competition_ids}})

    async def list_market_catalogue(self, event_ids: list[str]) -> list[dict[str, Any]]:
        return await self._call(
            "listMarketCatalogue",
            {"filter": {"eventIds": event_ids}, "maxResults": "100"},
        )

    async def list_market_book(self, market_ids: list[str]) -> list[dict[str, Any]]:
        return await self._call("listMarketBook", {
            "marketIds": market_ids,
            "priceProjection": {"priceData": ["EX_BEST_OFFERS", "EX_TRADED_VOLUME"]},
        })

    async def place_orders(self, market_id: str, instructions: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._call("placeOrders", {"marketId": market_id, "instructions": instructions})