"""Matchbook Betting Exchange API client.

Docs: https://developers.matchbook.com/
API base: https://api.matchbook.com

Free tier: up to 1M GET requests/month
Commission: 2% on net profit per market (no commission on losing bets)
Auth: session token via username/password
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

BASE = "https://api.matchbook.com"


class MatchbookClient:
    """Async Matchbook REST API wrapper."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        cfg = get_settings()
        self.username = username or getattr(cfg, "matchbook_username", None) or ""
        self.password = password or getattr(cfg, "matchbook_password", None) or ""
        self.session_token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE,
                timeout=httpx.Timeout(15.0),
                event_hooks={"request": [self._attach_auth]},
            )
        return self._client

    async def _attach_auth(self, request: httpx.Request) -> None:
        if self.session_token:
            request.headers["session-token"] = self.session_token
        request.headers["User-Agent"] = "BettingBot/1.0"
        request.headers["Accept"] = "application/json"

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Auth ──────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def login(self) -> str:
        """Authenticate with username/password. Returns session token."""
        client = await self._ensure_client()
        payload = {"username": self.username, "password": self.password}
        resp = await client.post(
            "/api/session",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        self.session_token = data.get("session-token", "")
        if not self.session_token:
            raise RuntimeError(f"Matchbook login failed: {data}")
        return self.session_token

    async def logout(self) -> None:
        """End the session."""
        if not self.session_token:
            return
        client = await self._ensure_client()
        try:
            await client.delete("/api/session")
        except Exception:
            pass
        self.session_token = None

    # ── Navigation ────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def list_events(
        self,
        sport_ids: list[int] | None = None,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        """List events. sport_ids: 4=football, state: open|closed|upcoming."""
        params: dict[str, Any] = {
            "state": state,
            "offset": 0,
            "per-page": 100,
            "include-prices": "true",
        }
        if sport_ids:
            params["sport-ids"] = ",".join(str(s) for s in sport_ids)
        client = await self._ensure_client()
        resp = await client.get("/api/events", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("events", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_event_markets(self, event_id: int) -> list[dict[str, Any]]:
        """Get markets for an event."""
        client = await self._ensure_client()
        resp = await client.get(f"/api/events/{event_id}/markets")
        resp.raise_for_status()
        data = resp.json()
        return data.get("markets", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_market(self, market_id: int) -> dict[str, Any]:
        """Get market details with current odds (runners + prices)."""
        client = await self._ensure_client()
        resp = await client.get(
            f"/api/markets/{market_id}",
            params={"include-prices": "true", "include-runners": "true"},
        )
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def list_market_odds(self, market_id: int) -> dict[str, Any]:
        """Shorthand for get_market with odds data."""
        return await self.get_market(market_id)

    # ── Orders ────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def place_bet(
        self,
        market_id: int,
        runner_id: int,
        side: str,  # "back" | "lay"
        odds: float,
        stake: float,
    ) -> dict[str, Any]:
        """Place a single bet on Matchbook.

        stake = liability (for back, it's the stake; for lay, it's the liability).
        odds = decimal odds (e.g. 2.50).
        """
        client = await self._ensure_client()
        price_cents = int(odds * 100)
        stake_cents = int(stake * 100)

        payload = {
            "market-id": market_id,
            "runner-id": runner_id,
            "side": side.upper(),
            "price": price_cents,
            "stake": stake_cents,
            "odds-type": "DECIMAL",
        }
        resp = await client.post(
            "/api/bets/place",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def list_bets(
        self,
        state: str = "open",
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        """List your bets. state: open|settled|cancelled."""
        client = await self._ensure_client()
        resp = await client.get(
            "/api/bets",
            params={"state": state, "per-page": per_page},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("bets", [])

    # ── Account ────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_account(self) -> dict[str, Any]:
        """Get account balance and exposure."""
        client = await self._ensure_client()
        resp = await client.get("/api/account")
        resp.raise_for_status()
        return resp.json()

    # ── Helpers ────────────────────────────────────────

    @staticmethod
    def extract_odds_snapshot(
        market: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Normalize Matchbook market runners into our LiveOdds row shape.

        Returns list of dicts with: runner, available_to_back, available_to_lay.
        """
        rows: list[dict[str, Any]] = []
        for runner in market.get("runners", []):
            prices = runner.get("prices", [])
            available_to_back = []
            available_to_lay = []
            for p in prices:
                price = p.get("decimal-odds", 0) or (p.get("price", 0) / 100)
                volume = p.get("volume", 0)
                side = p.get("side", "").upper()
                if side == "BACK":
                    available_to_back.append({"price": price, "size": volume})
                elif side == "LAY":
                    available_to_lay.append({"price": price, "size": volume})

            # Sort back descending (best price first), lay ascending
            available_to_back.sort(key=lambda x: x["price"], reverse=True)
            available_to_lay.sort(key=lambda x: x["price"])

            rows.append({
                "runner": str(runner.get("id", "")),
                "runner_name": runner.get("name", ""),
                "available_to_back": available_to_back[:3],
                "available_to_lay": available_to_lay[:3],
                "in_play": market.get("state", "") == "live",
            })
        return rows