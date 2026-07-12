import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import python_bridge, scraper
from app.services.python_bridge import BridgeError, OddsHarvesterJsonResult


def _report(*, status="success", successful=1, failed=0, partial=0, failures=None, warnings=None):
    return {
        "schema_version": "1.0",
        "command": "upcoming",
        "status": status,
        "engines": {"requested": "auto", "used": ["playwright"] if successful else []},
        "source": {
            "sport": "football",
            "date": "20260713",
            "leagues": ["romania"],
            "markets": ["1x2"],
            "season": None,
            "match_links": ["https://example.test/match/secret"],
            "base_url": "https://www.oddsportal.com",
        },
        "locale": "ro-RO",
        "timezone": "Europe/Bucharest",
        "stats": {
            "total_urls": successful + failed + partial,
            "successful": successful,
            "failed": failed,
            "partial": partial,
            "success_rate_pct": 100.0 if successful and not failed else 50.0,
        },
        "failures": failures or [],
        "warnings": warnings or [],
        "timing": {
            "started_at": "2026-07-12T10:00:00+00:00",
            "finished_at": "2026-07-12T10:00:02+00:00",
            "duration_seconds": 2.0,
        },
    }


@pytest.mark.asyncio
async def test_bridge_reads_new_report_and_keeps_primary_list(monkeypatch, tmp_path):
    monkeypatch.setattr(python_bridge, "TEMP_DIR", tmp_path)

    async def fake_run(args, *, timeout=None):
        output = Path(args[args.index("--output") + 1])
        report = Path(args[args.index("--report-output") + 1])
        output.write_text(json.dumps([{"home_team": "A"}]))
        report.write_text(json.dumps(_report()))
        return "ok"

    monkeypatch.setattr(python_bridge, "run_oddsharvester", fake_run)

    result = await python_bridge.run_oddsharvester_json(["upcoming"], include_report=True)

    assert isinstance(result, OddsHarvesterJsonResult)
    assert result.records == [{"home_team": "A"}]
    assert result.report["schema_version"] == "1.0"
    assert result.cli_error is None


@pytest.mark.asyncio
async def test_bridge_retries_list_only_cli_without_report_option(monkeypatch, tmp_path):
    monkeypatch.setattr(python_bridge, "TEMP_DIR", tmp_path)
    calls = []

    async def fake_run(args, *, timeout=None):
        calls.append(args)
        if "--report-output" in args:
            raise BridgeError("No such option: --report-output")
        Path(args[args.index("--output") + 1]).write_text("[]")
        return "ok"

    monkeypatch.setattr(python_bridge, "run_oddsharvester", fake_run)

    result = await python_bridge.run_oddsharvester_json(["upcoming"], include_report=True)

    assert isinstance(result, OddsHarvesterJsonResult)
    assert result.records == []
    assert result.report is None
    assert len(calls) == 2


def test_geo_params_are_validated_forwarded_and_sensitive_args_redacted():
    job = SimpleNamespace(
        league="romania",
        params={
            "command": "upcoming",
            "sport": "football",
            "base_url": "https://www.centroquote.it/",
            "locale": "it-IT",
            "timezone": "Europe/Rome",
        },
    )

    args = scraper._build_oddsharvester_args(job)

    assert args[args.index("--base-url") + 1] == "https://www.centroquote.it"
    assert args[args.index("--locale") + 1] == "it-IT"
    assert args[args.index("--timezone") + 1] == "Europe/Rome"
    assert scraper._redact_sensitive_args(["upcoming", "--proxy-pass", "secret", "--sport", "football"]) == [
        "upcoming",
        "--proxy-pass",
        "[REDACTED]",
        "--sport",
        "football",
    ]

    job.params["base_url"] = "https://user:secret@example.test/path"
    with pytest.raises(ValueError, match="host-only"):
        scraper._build_oddsharvester_args(job)


def test_report_health_covers_partial_and_zero_antibot_failure():
    degraded = scraper._scrape_report_summary(
        _report(status="partial", successful=1, failed=1, partial=1, failures=[{"error_type": "parsing"}]),
        [{"home_team": "A"}],
    )
    failed = scraper._scrape_report_summary(
        _report(
            status="failed",
            successful=0,
            failed=1,
            failures=[{"error_type": "rate_limited", "error_message": "Cloudflare challenge blocked request"}],
        ),
        [],
        cli_error="exit 1",
    )

    assert degraded["health"] == "degraded"
    assert failed["health"] == "failed"
    assert failed["anti_bot_detected"] is True
    assert failed["cli_error"] is True
    assert "match_links" not in degraded["source"]
    assert degraded["source"]["match_link_count"] == 1


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _ReportSession:
    def __init__(self, job, run):
        self.job = job
        self.run = run
        self.added = []

    async def get(self, _model, primary_key):
        return self.job if primary_key == self.job.id else None

    async def execute(self, _statement):
        return _ScalarRows([self.run])

    def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = len(self.added) + 1
        self.added.append(value)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_execute_job_persists_degraded_report_in_run_artifacts_and_log(monkeypatch):
    job = SimpleNamespace(
        id=41,
        job_type="scrape_odds",
        status="pending",
        league="romania",
        params={"command": "upcoming", "sport": "football"},
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
    )
    run = SimpleNamespace(artifacts={"scrape_job_ids": [41]})
    db = _ReportSession(job, run)
    report = _report(
        status="partial",
        successful=1,
        failed=1,
        partial=0,
        failures=[{"error_type": "navigation", "error_message": "one URL timed out"}],
    )

    async def fake_bridge(args, label, *, timeout=None, include_report=False):
        assert include_report is True
        return OddsHarvesterJsonResult([{"home_team": "A", "away_team": "B"}], report)

    async def fake_ingest(_db, _job, _records):
        return {"dataset_id": 7, "matches_count": 1, "matches_upserted": 1, "odds_written": 0}

    monkeypatch.setattr(scraper, "run_oddsharvester_json", fake_bridge)
    monkeypatch.setattr(scraper, "_ingest_scraped_payload", fake_ingest)

    result = await scraper.execute_scrape_job(db, 41)

    assert result.status == "completed"
    assert run.artifacts["scrape_report"]["health"] == "degraded"
    report_logs = [item for item in db.added if getattr(item, "action", None) == "scrape_report"]
    assert report_logs[0].level == "warning"
    assert report_logs[0].metadata_json["failure_count"] == 1
    assert json.loads(result.output)["scrape_report"]["health"] == "degraded"


@pytest.mark.asyncio
async def test_execute_job_fails_on_zero_result_antibot_report(monkeypatch):
    job = SimpleNamespace(
        id=42,
        job_type="scrape_odds",
        status="pending",
        league="romania",
        params={"command": "upcoming", "sport": "football"},
        started_at=None,
        completed_at=None,
        output=None,
        error=None,
    )
    run = SimpleNamespace(artifacts={"scrape_job_ids": [42]})
    db = _ReportSession(job, run)
    report = _report(
        status="failed",
        successful=0,
        failed=1,
        failures=[{"error_type": "rate_limited", "error_message": "Captcha challenge"}],
    )

    async def fake_bridge(args, label, *, timeout=None, include_report=False):
        return OddsHarvesterJsonResult([], report, cli_error="exit 1")

    async def fail_ingest(*_args):
        raise AssertionError("failed scrape report must not be ingested")

    monkeypatch.setattr(scraper, "run_oddsharvester_json", fake_bridge)
    monkeypatch.setattr(scraper, "_ingest_scraped_payload", fail_ingest)

    result = await scraper.execute_scrape_job(db, 42)

    assert result.status == "failed"
    assert "classified the run as failed" in result.error
    assert run.artifacts["scrape_report"]["health"] == "failed"
