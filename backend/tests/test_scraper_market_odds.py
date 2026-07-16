from datetime import datetime, timedelta, timezone

import pytest

from app.models.match import Match, OddsEntry
from app.models.odds_lineage import OddsSnapshot
from app.services.scraper import _derive_match_status, _ingest_match_odds, _market_key_to_odds


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _OddsIngestDb:
    def __init__(self):
        self.added = []

    async def execute(self, _statement):
        return _ScalarResult(None)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, OddsSnapshot) and value.id is None:
                value.id = 41


def test_market_key_to_odds_accepts_oddsharvester_btts_keys():
    assert _market_key_to_odds("btts_market", {"odds_yes": "1.92", "odds_no": "1.88"}) == (1.92, None, 1.88)


def test_market_key_to_odds_accepts_scraped_btts_market_keys():
    assert _market_key_to_odds("btts_market", {"btts_yes": "1.47", "btts_no": "2.45"}) == (1.47, None, 2.45)


def test_market_key_to_odds_accepts_oddsharvester_over_under_keys():
    assert _market_key_to_odds("over_under_2_5_market", {"odds_over": "1.91", "odds_under": "1.95"}) == (
        1.91,
        None,
        1.95,
    )


def test_future_match_with_placeholder_scores_stays_scheduled():
    status = _derive_match_status(
        {"home_score": "0", "away_score": "0"},
        datetime.now(timezone.utc) + timedelta(hours=2),
    )

    assert status == "scheduled"


@pytest.mark.asyncio
async def test_ingest_match_odds_persists_snapshot_lineage():
    db = _OddsIngestDb()
    match = Match(id=7, sport="football", home_team="Atlas", away_team="Comets", status="scheduled")

    report = await _ingest_match_odds(
        db,
        match,
        {
            "match_link": "https://example.test/match/atlas-comets",
            "scraped_date": "2026-07-16T12:00:00+00:00",
            "1x2_market": [
                {
                    "bookmaker_name": "E2E",
                    "1": 2.0,
                    "X": 3.5,
                    "2": 4.2,
                }
            ],
        },
    )

    snapshot = next(value for value in db.added if isinstance(value, OddsSnapshot))
    entry = next(value for value in db.added if isinstance(value, OddsEntry))
    assert snapshot.match_id == match.id
    assert snapshot.quality == "complete"
    assert entry.odds_snapshot_id == snapshot.id == 41
    assert report["written"] == 1
