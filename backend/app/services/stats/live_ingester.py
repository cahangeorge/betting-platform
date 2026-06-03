"""Live stats ingestion service — polls football-data.org and populates MatchStat."""
from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.match import Match
from app.services.stats.football_data_feed import FootballDataFeed


class LiveStatsIngester:
    """Polls football-data.org for live matches and writes MatchStat snapshots.

    Designed to run as a background task alongside the bot daemon.
    """

    def __init__(self, poll_interval: int = 60) -> None:
        self.poll_interval = poll_interval
        settings = get_settings()
        self.feed = FootballDataFeed(api_key=settings.football_data_api_key or None)
        self._running = False
        self._task: asyncio.Task | None = None
        self.stats: dict[str, Any] = {"cycles": 0, "ingested": 0, "errors": 0}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.feed.close()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._cycle()
            except Exception:
                self.stats["errors"] += 1
            self.stats["cycles"] += 1
            await asyncio.sleep(self.poll_interval)

    async def _cycle(self) -> None:
        """One poll cycle: fetch live matches, write snapshots."""
        async with async_session_factory() as db:
            for league_code in ("PL", "BL1", "SA", "LL", "FL1"):
                matches = await self.feed.get_live_matches(league_code)
                for m in matches:
                    await self._process_match(db, m, league_code)

    async def _process_match(
        self, db: Any, match_data: dict[str, Any], league_code: str,
    ) -> None:
        """Process a single live match from football-data.org."""
        match_id_api = str(match_data.get("id", ""))
        home_name = match_data.get("homeTeam", {}).get("shortName", "") or \
                    match_data.get("homeTeam", {}).get("name", "") or ""
        away_name = match_data.get("awayTeam", {}).get("shortName", "") or \
                    match_data.get("awayTeam", {}).get("name", "") or ""

        if not home_name or not away_name:
            return

        # Find our match record
        result = await db.execute(
            select(Match).where(
                Match.home_team.ilike(f"%{home_name}%"),
                Match.away_team.ilike(f"%{away_name}%"),
                Match.is_deleted.is_(False),
            )
        )
        our_match = result.scalar_one_or_none()
        if not our_match:
            return

        # Build stat snapshot
        snapshot = FootballDataFeed.extract_stat_snapshot(match_data)
        if snapshot is None:
            return

        snapshot["match_id"] = str(our_match.id)
        snapshot["source"] = f"football-data-{league_code}"

        from app.models.match import MatchStat

        stat = MatchStat(
            match_id=snapshot["match_id"],
            source=snapshot["source"],
            elapsed=snapshot.get("elapsed", 90),
            xg_home=snapshot.get("xg_home"),
            xg_away=snapshot.get("xg_away"),
            possession_home=snapshot.get("possession_home"),
            possession_away=snapshot.get("possession_away"),
            shots_home=snapshot.get("shots_home"),
            shots_away=snapshot.get("shots_away"),
            shots_on_target_home=snapshot.get("shots_on_target_home"),
            shots_on_target_away=snapshot.get("shots_on_target_away"),
            corners_home=snapshot.get("corners_home"),
            corners_away=snapshot.get("corners_away"),
            dangerous_attacks_home=snapshot.get("dangerous_attacks_home"),
            dangerous_attacks_away=snapshot.get("dangerous_attacks_away"),
            cards_home=snapshot.get("cards_home"),
            cards_away=snapshot.get("cards_away"),
        )
        db.add(stat)
        await db.commit()
        self.stats["ingested"] += 1

    # ── Historical data expansion ────────────────────────

    async def expand_training_data(self, seasons: list[int] | None = None) -> dict[str, int]:
        """Fetch historical match data across leagues and append to CSV."""
        import csv
        from pathlib import Path

        from app.services.training.trainer import fetch_training_data

        csv_path = Path(__file__).resolve().parents[3] / "data" / "historical_matches.csv"
        target_leagues = ["PL", "BL1", "SA", "LL", "FL1"]
        seasons = seasons or [2023, 2024]
        total = 0

        with open(csv_path, "a", newline="") as f:
            writer = None
            for league in target_leagues:
                for season in seasons:
                    rows = await self.feed.fetch_historical_for_csv(league, season)
                    for row in rows:
                        if writer is None:
                            writer = csv.DictWriter(f, fieldnames=row.keys())
                        writer.writerow(row)
                        total += 1
        return {"leagues": len(target_leagues), "seasons": len(seasons), "appended": total}