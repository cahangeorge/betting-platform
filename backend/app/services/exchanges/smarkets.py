"""Smarkets REST API client."""
from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

BASE = "https://api.smarkets.com/v3"


class SmarketsClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or getattr(get_settings(), "smarkets_api_key", "") or ""
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=BASE, timeout=httpx.Timeout(15.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        client = await self._ensure_client()
        resp = await client.get(path, headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    async def list_popular_events(self, sport: str = "football", state: str = "upcoming") -> list[dict[str, Any]]:
        data = await self._get("/events/", {"sport_types": sport, "states": state, "sort": "total_volume", "order": "desc"})
        return data.get("events", [])

    async def list_event_markets(self, event_id: str) -> list[dict[str, Any]]:
        data = await self._get(f"/events/{event_id}/markets/")
        return data.get("markets", [])

    async def get_market(self, market_id: str) -> dict[str, Any]:
        return await self._get(f"/markets/{market_id}/")

    async def list_market_quotes(self, market_id: str) -> dict[str, Any]:
        return await self._get(f"/markets/{market_id}/quotes/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def submit_order(self, contract_id: str, side: str, quantity: int, price: int) -> dict[str, Any]:
        client = await self._ensure_client()
        payload = {"contract_id": contract_id, "side": side, "quantity": quantity, "price": price}
        resp = await client.post("/orders/", headers=self._headers(), content=json.dumps(payload))
        resp.raise_for_status()
        return resp.json()

    async def get_account(self) -> dict[str, Any]:
        return await self._get("/account/")