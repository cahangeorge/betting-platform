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
        dataset_id=71,
        scrape_job_id=19,
    )

    snapshot = next(value for value in db.added if isinstance(value, OddsSnapshot))
    entry = next(value for value in db.added if isinstance(value, OddsEntry))
    assert snapshot.match_id == match.id
    assert snapshot.quality == "complete"
    assert snapshot.dataset_id == 71
    assert snapshot.scrape_job_id == 19
    assert entry.odds_snapshot_id == snapshot.id == 41
    assert report["written"] == 1


@pytest.mark.asyncio
async def test_batch_odds_ingestion_reuses_the_persisted_entry_for_same_chunk_duplicates():
    from app.services.scraper import _ingest_record_odds

    class _DB:
        def __init__(self):
            self.added = []

        def add(self, item):
            self.added.append(item)

    db = _DB()
    match = Match(id=7, sport="football", home_team="Atlas", away_team="Comets", status="scheduled")
    observed_at = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    snapshot = OddsSnapshot(
        id=41,
        match_id=match.id,
        source="OddsHarvester",
        source_key=f"job:19:match:{match.id}:observed:{observed_at.isoformat()}",
        dataset_id=71,
        scrape_job_id=19,
        observed_at=observed_at,
        quality="complete",
    )
    existing_odds = {}
    existing_snapshots = {snapshot.source_key: snapshot}
    record = {
        "scraped_date": observed_at.isoformat(),
        "1x2_market": [
            {"bookmaker_name": "E2E", "1": 2.0, "X": 3.5, "2": 4.2},
            {"bookmaker_name": "E2E", "1": 2.1, "X": 3.6, "2": 4.3},
        ],
    }

    report = await _ingest_record_odds(
        db,
        record=record,
        match=match,
        dataset_id=71,
        scrape_job_id=19,
        existing_odds=existing_odds,
        existing_snapshots=existing_snapshots,
    )

    entries = [item for item in db.added if isinstance(item, OddsEntry)]
    assert len(entries) == 1
    assert entries[0].home_odds == 2.1
    assert entries[0].odds_snapshot is snapshot
    assert report["written"] == 1
    assert report["changed"] == 2


@pytest.mark.asyncio
async def test_odds_lineage_reuses_same_job_but_isolates_new_job_replay():
    from app.services.scraper import _ingest_record_odds

    class _DB:
        def __init__(self):
            self.added = []

        def add(self, item):
            self.added.append(item)

    db = _DB()
    match = Match(id=7, sport="football", home_team="Atlas", away_team="Comets", status="scheduled")
    record = {
        "scraped_date": "2026-07-16T12:00:00+00:00",
        "1x2_market": [{"bookmaker_name": "E2E", "1": 2.0, "X": 3.5, "2": 4.2}],
    }
    existing_odds = {}
    existing_snapshots = {}

    first = await _ingest_record_odds(
        db,
        record=record,
        match=match,
        dataset_id=71,
        scrape_job_id=19,
        existing_odds=existing_odds,
        existing_snapshots=existing_snapshots,
    )
    same_job = await _ingest_record_odds(
        db,
        record=record,
        match=match,
        dataset_id=72,
        scrape_job_id=19,
        existing_odds=existing_odds,
        existing_snapshots=existing_snapshots,
    )
    new_job = await _ingest_record_odds(
        db,
        record=record,
        match=match,
        dataset_id=73,
        scrape_job_id=20,
        existing_odds=existing_odds,
        existing_snapshots=existing_snapshots,
    )

    snapshots = [item for item in db.added if isinstance(item, OddsSnapshot)]
    entries = [item for item in db.added if isinstance(item, OddsEntry)]
    assert first["written"] == 1
    assert same_job["written"] == 0
    assert new_job["written"] == 1
    assert len(snapshots) == 2
    assert len(entries) == 2
    assert snapshots[0].source_key.startswith("job:19:")
    assert snapshots[1].source_key.startswith("job:20:")
    assert snapshots[0].dataset_id == 71
    assert snapshots[1].dataset_id == 73
