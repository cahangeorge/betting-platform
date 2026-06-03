"""Understat.com live stats feed — fetches match-level xG, possession, shots.

Docs: Understat exposes JSON data embedded in their pages. We scrape:
  - /match/{match_id} for live stats by minute
  - /league/{league}/{season} for match listings

This service acts as the bridge between Understat's data and our MatchStat model.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import aiohttp


LEAGUE_MAP = {
    "EPL": "epl",
    "La_liga": "la_liga",
    "Bundesliga": "bundesliga",
    "Serie_A": "serie_a",
    "Ligue_1": "ligue_1",
    "RFPL": "rfpl",
}

LEAGUE_REVERSE = {v: k for k, v in LEAGUE_MAP.items()}


class UnderstatFeed:
    """Async client for Understat match and league data."""

    BASE = "https://understat.com"

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=self.BASE,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BettingBot/1.0)"},
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_json(self, path: str) -> dict[str, Any]:
        """Fetch a page and extract JSON from embedded <script> tags."""
        session = await self._get_session()
        async with session.get(path) as resp:
            html = await resp.text()

        # Understat embeds JSON in: var teamsData = JSON.parse('...') etc.
        # Find the relevant data section
        for var_name in ["teamsData", "playersData", "matchesData"]:
            pattern = rf"var\s+{var_name}\s*=\s*(?:JSON\.parse\()?'(.+?)'\)?;"
            match = re.search(pattern, html, re.DOTALL)
            if match:
                import json
                raw = match.group(1)
                raw = raw.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
                # Unescape common escapes
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    continue
        return {}

    async def _fetch_stat_data(self, path: str) -> dict[str, Any]:
        """Fetch statData from match page."""
        session = await self._get_session()
        async with session.get(path) as resp:
            html = await resp.text()

        pattern = r"var\s+statData\s*=\s*(?:JSON\.parse\()?'(.+?)'\)?;"
        match = re.search(pattern, html, re.DOTALL)
        if match:
            import json
            raw = match.group(1)
            raw = raw.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
            # Replace escaped forward slashes
            raw = raw.replace("\\/", "/")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"error": "json_parse_failed"}
        return {"error": "not_found"}

    # ── League / season data ────────────────────────────

    async def get_league_matches(
        self, league: str, season: str = "2024",
    ) -> list[dict[str, Any]]:
        """Fetch all matches for a league+season.

        Returns list of dicts with: id, home_team, away_team, home_goals,
        away_goals, xG_home, xG_away, date, etc.
        """
        league_slug = LEAGUE_MAP.get(league, league.lower())
        data = await self._fetch_json(f"/league/{league_slug}/{season}")
        matches = []
        for match_id_str, match_info in data.items():
            if isinstance(match_info, dict):
                h = match_info.get("h", {})
                a = match_info.get("a", {})
                matches.append({
                    "id": match_id_str,
                    "date": match_info.get("date", ""),
                    "home_team": h.get("title", ""),
                    "away_team": a.get("title", ""),
                    "home_goals": h.get("goals", 0),
                    "away_goals": a.get("goals", 0),
                    "xg_home": float(h.get("xG", 0)),
                    "xg_away": float(a.get("xG", 0)),
                    "home_pts": h.get("pts", 0),
                    "away_pts": a.get("pts", 0),
                    "league": league,
                    "season": season,
                })
        return matches

    # ── Live match stats ────────────────────────────────

    async def get_match_stats(self, match_id: str | int) -> dict[str, Any]:
        """Fetch per-minute stat data for a match.

        Returns dict with keys:
          'shots': list of shot events with coordinates, xG, result, minute
          'xg_home', 'xg_away' cumulative
          'shots_home', 'shots_away' counts
          'shots_on_target_home', 'shots_on_target_away'
        """
        data = await self._fetch_stat_data(f"/match/{match_id}")

        if "error" in data:
            return {"shots": [], "xg_home": 0, "xg_away": 0}

        shots: list[dict] = data.get("s", [])
        xg_h = sum(float(s.get("xG", 0)) for s in shots if s.get("h_a") == "h")
        xg_a = sum(float(s.get("xG", 0)) for s in shots if s.get("h_a") == "a")
        shots_h = len([s for s in shots if s.get("h_a") == "h"])
        shots_a = len([s for s in shots if s.get("h_a") == "a"])
        sot_h = len([s for s in shots if s.get("h_a") == "h" and s.get("result") == "Goal"])
        sot_a = len([s for s in shots if s.get("h_a") == "a" and s.get("result") == "Goal"])
        # Also include blocked / saved / missed on target
        for s in shots:
            if s.get("h_a") == "h" and s.get("result") in ("SavedShot", "ShotOnPost"):
                sot_h += 1
            if s.get("h_a") == "a" and s.get("result") in ("SavedShot", "ShotOnPost"):
                sot_a += 1

        # Build a per-minute timeline
        timeline: list[dict[str, Any]] = []
        sorted_shots = sorted(shots, key=lambda x: int(x.get("minute", 0)))
        running_xg_h = 0.0
        running_xg_a = 0.0
        running_sot_h = 0
        running_sot_a = 0
        last_minute = 0
        for s in sorted_shots:
            minute = int(s.get("minute", 0))
            if minute != last_minute and timeline:
                # Carry forward previous values for minutes with no events
                pass
            last_minute = minute
            if s.get("h_a") == "h":
                running_xg_h += float(s.get("xG", 0))
                if s.get("result") in ("Goal", "SavedShot", "ShotOnPost"):
                    running_sot_h += 1
            else:
                running_xg_a += float(s.get("xG", 0))
                if s.get("result") in ("Goal", "SavedShot", "ShotOnPost"):
                    running_sot_a += 1
            timeline.append({
                "minute": minute,
                "xg_home": round(running_xg_h, 3),
                "xg_away": round(running_xg_a, 3),
                "shots_on_target_home": running_sot_h,
                "shots_on_target_away": running_sot_a,
                "shot_result": s.get("result"),
                "shot_team": s.get("h_a"),
                "xG": float(s.get("xG", 0)),
            })

        return {
            "shots": timeline,
            "xg_home": round(xg_h, 2),
            "xg_away": round(xg_a, 2),
            "shots_home": shots_h,
            "shots_away": shots_a,
            "shots_on_target_home": sot_h,
            "shots_on_target_away": sot_a,
        }

    async def build_match_stat_dict(
        self,
        match_id: str,
        elapsed: int,
        understat_match_id: str | int,
    ) -> dict[str, Any] | None:
        """Build a MatchStat-compatible dict from Understat data at a given elapsed minute.

        Returns None if data unavailable.
        """
        data = await self.get_match_stats(understat_match_id)
        if not data.get("shots"):
            return None

        # Find the closest stat snapshot at or before elapsed
        shots = data.get("shots", [])
        closest = None
        for s in shots:
            if int(s.get("minute", 0)) <= elapsed:
                closest = s

        if closest is None:
            return None

        return {
            "match_id": match_id,
            "source": "understat",
            "elapsed": elapsed,
            "xg_home": closest["xg_home"],
            "xg_away": closest["xg_away"],
            "shots_on_target_home": closest["shots_on_target_home"],
            "shots_on_target_away": closest["shots_on_target_away"],
            "shots_home": data.get("shots_home"),
            "shots_away": data.get("shots_away"),
            "possession_home": None,  # Understat doesn't provide possession
            "possession_away": None,
            "dangerous_attacks_home": None,
            "dangerous_attacks_away": None,
            "cards_home": None,
            "cards_away": None,
        }

    async def fetch_historical_for_csv(
        self, league: str, season: str = "2024",
    ) -> list[dict[str, Any]]:
        """Fetch matches formatted for our CSV training data."""
        matches = await self.get_league_matches(league, season)
        rows = []
        for m in matches:
            rows.append({
                "Date": m["date"][:10] if m.get("date") else "",
                "HomeTeam": m["home_team"],
                "AwayTeam": m["away_team"],
                "FTHG": m.get("home_goals", 0),
                "FTAG": m.get("away_goals", 0),
                "League": league,
                "h_xg": m.get("xg_home", 0),
                "a_xg": m.get("xg_away", 0),
            })
        return rows