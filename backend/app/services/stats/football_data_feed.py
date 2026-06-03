"""Football-data.org API client — free-tier live stats & fixtures.

Docs: https://www.football-data.org/documentation/quickstart
Free tier: 10 req/min, current season data for major leagues.
"""
from __future__ import annotations

from typing import Any

import aiohttp


LEAGUES = {
    "PL": 2021,  # Premier League
    "BL1": 2002,  # Bundesliga
    "SA": 2019,  # Serie A
    "LL": 2014,  # La Liga
    "FL1": 2015,  # Ligue 1
    "DED": 2003,  # Eredivisie
}


class FootballDataFeed:
    """Async client for football-data.org API."""

    BASE = "https://api.football-data.org/v4"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or ""
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"X-Auth-Token": self.api_key}
            self._session = aiohttp.ClientSession(
                base_url=self.BASE,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        session = await self._get_session()
        async with session.get(path, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ── Competitions & matches ──────────────────────────

    async def get_competition_matches(
        self, league_code: str, season: int | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch matches for a competition.

        status: SCHEDULED | LIVE | IN_PLAY | PAUSED | FINISHED | POSTPONED | CANCELLED
        """
        code_id = LEAGUES.get(league_code)
        if not code_id:
            return []
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if season:
            params["season"] = season
        data = await self._get(f"/competitions/{code_id}/matches", params)
        return data.get("matches", [])

    async def get_live_matches(self, league_code: str | None = None) -> list[dict[str, Any]]:
        """Fetch currently live matches."""
        if league_code:
            return await self.get_competition_matches(league_code, status="LIVE")
        # Get all live matches across all competitions
        data = await self._get("/matches", {"status": "LIVE"})
        return data.get("matches", [])

    async def get_match(self, match_id: int) -> dict[str, Any]:
        """Fetch full match details including live stats."""
        return await self._get(f"/matches/{match_id}")

    # ── Stats extraction ────────────────────────────────

    @staticmethod
    def extract_stat_snapshot(match: dict[str, Any]) -> dict[str, Any]:
        """Extract a MatchStat-compatible dict from football-data.org match data.

        Returns dict with keys: match_id, source, elapsed, xg_home, xg_away,
        possession_home, possession_away, shots_on_target_home, shots_on_target_away,
        cards_home, cards_away, etc.
        """
        score = match.get("score", {})
        home_team = match.get("homeTeam", {})
        away_team = match.get("awayTeam", {})

        # Extract from fullTime or halfTime
        ft = score.get("fullTime", {}) or {}
        ht = score.get("halfTime", {}) or {}

        # Build stat dict (football-data.org doesn't provide xG in free tier)
        snapshot: dict[str, Any] = {
            "match_id": str(match.get("id", "")),
            "source": "football-data",
            "elapsed": 90,  # final
            "xg_home": None,
            "xg_away": None,
            "possession_home": None,
            "possession_away": None,
            "shots_on_target_home": None,
            "shots_on_target_away": None,
            "shots_home": None,
            "shots_away": None,
            "corners_home": None,
            "corners_away": None,
            "dangerous_attacks_home": None,
            "dangerous_attacks_away": None,
            "cards_home": None,
            "cards_away": None,
        }

        # Update with live score info
        if score.get("duration") == "REGULAR":
            snapshot["elapsed"] = 90
        elif score.get("duration") == "EXTRA_TIME":
            snapshot["elapsed"] = 120

        # If match is live, extract from live status
        if match.get("status") in ("IN_PLAY", "PAUSED"):
            # football-data.org free tier doesn't provide real-time stats
            # but we can extract what's available from the score object
            pass

        return snapshot

    @staticmethod
    def match_to_csv_row(match: dict[str, Any], league: str) -> dict[str, Any]:
        """Convert a football-data.org match to our CSV training format."""
        score = match.get("score", {})
        ft = score.get("fullTime", {}) or {}
        ht = score.get("halfTime", {}) or {}
        home_team = match.get("homeTeam", {}).get("shortName", match.get("homeTeam", {}).get("name", ""))
        away_team = match.get("awayTeam", {}).get("shortName", match.get("awayTeam", {}).get("name", ""))
        return {
            "Date": (match.get("utcDate", "") or "")[:10],
            "HomeTeam": home_team,
            "AwayTeam": away_team,
            "FTHG": ft.get("home", 0),
            "FTAG": ft.get("away", 0),
            "League": league,
        }

    async def fetch_historical_for_csv(
        self, league_code: str, season: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch finished matches as CSV rows for training."""
        matches = await self.get_competition_matches(league_code, season=season, status="FINISHED")
        return [self.match_to_csv_row(m, league_code) for m in matches]