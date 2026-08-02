import hashlib
import io
import os
from datetime import datetime, timedelta, timezone

from app.bridges.soccerdata_bridge import (
    _acquire_source_rate_limit,
    _attach_cache_telemetry,
    _instrument_reader_cache,
    _serialize_utc_datetime,
    _slice_page,
)


class _FixtureReader:
    def __init__(self, *, no_cache=False, no_store=False, network_allowed=True):
        self.no_cache = no_cache
        self.no_store = no_store
        self.network_allowed = network_allowed
        self.network_calls = 0

    def get(self, _url, filepath=None, max_age=None, no_cache=False, var=None):
        del var
        path = filepath
        valid = False
        if path is not None and path.exists():
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            valid = max_age is None or datetime.now(timezone.utc) - modified <= max_age
        if valid and path is not None and not (no_cache or self.no_cache):
            return path.open("rb")
        if not self.network_allowed:
            raise AssertionError("warm cache must not access upstream")
        self.network_calls += 1
        payload = b'{"fixture":true}'
        if not self.no_store and path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        return io.BytesIO(payload)


class _DirectApiReader(_FixtureReader):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cookies_initialized = False
        self.cookie_calls = 0
        self.api_calls = 0

    def _ensure_cookies(self):
        self.cookie_calls += 1
        self._cookies_initialized = True

    def _request_api(self, _url, filepath=None, no_cache=False):
        cached = filepath is not None and filepath.exists() and not no_cache and not self.no_cache
        if cached and filepath is not None:
            return filepath.open("rb")
        self.api_calls += 1
        payload = b'{"direct_api":true}'
        if not self.no_store and filepath is not None:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(payload)
        return io.BytesIO(payload)


def _result(telemetry):
    return _attach_cache_telemetry({"rows": [{"id": 1}], "summary": {"count": 1}}, telemetry)


def test_soccerdata_naive_fixture_dates_are_normalized_to_explicit_utc():
    assert _serialize_utc_datetime("2024-08-16T19:00:00") == "2024-08-16T19:00:00Z"
    assert _serialize_utc_datetime("2024-08-16T21:00:00+02:00") == "2024-08-16T19:00:00Z"


def test_cold_then_warm_cache_proves_zero_upstream_and_equal_artifact_digest(tmp_path):
    artifact = tmp_path / "ESPN" / "schedule.json"
    cold_reader = _FixtureReader()
    cold_telemetry = _instrument_reader_cache(cold_reader, {}, ttl_seconds=300)
    cold_reader.get("https://fixture.invalid", filepath=artifact)
    cold = _result(cold_telemetry)

    warm_reader = _FixtureReader(network_allowed=False)
    warm_telemetry = _instrument_reader_cache(warm_reader, {}, ttl_seconds=300)
    warm_reader.get("https://fixture.invalid", filepath=artifact)
    warm = _result(warm_telemetry)

    assert cold_reader.network_calls == 1
    assert cold["summary"]["cache"]["mode"] == "cold"
    assert warm_reader.network_calls == 0
    assert warm["summary"]["cache"]["mode"] == "warm"
    assert warm["summary"]["cache"]["upstream_requests"] == 0
    assert cold["summary"]["cache"]["artifact_digest"] == warm["summary"]["cache"]["artifact_digest"]
    assert warm["summary"]["coverage_complete"] is True


def test_stale_cache_performs_exactly_one_refresh(tmp_path):
    artifact = tmp_path / "MatchHistory" / "season.csv"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"stale")
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(artifact, (stale_time, stale_time))

    reader = _FixtureReader()
    telemetry = _instrument_reader_cache(reader, {}, ttl_seconds=60)
    reader.get("https://fixture.invalid", filepath=artifact)
    result = _result(telemetry)

    assert reader.network_calls == 1
    assert result["summary"]["cache"]["upstream_requests"] == 1
    assert artifact.read_bytes() == b'{"fixture":true}'


def test_no_store_bypasses_existing_cache_and_writes_nothing(tmp_path):
    artifact = tmp_path / "Understat" / "schedule.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"stale-cache-that-must-not-be-fingerprinted")
    stale_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    reader = _FixtureReader(no_cache=True, no_store=True)
    telemetry = _instrument_reader_cache(reader, {"no_store": True}, ttl_seconds=300)
    reader.get("https://fixture.invalid", filepath=artifact)
    result = _result(telemetry)

    assert reader.network_calls == 1
    assert artifact.read_bytes() == b"stale-cache-that-must-not-be-fingerprinted"
    assert result["summary"]["cache"]["mode"] == "no-store"
    assert len(result["summary"]["cache"]["artifact_digest"]) == 64
    assert result["summary"]["cache"]["artifact_digest"] != stale_digest
    assert result["summary"]["cache"]["as_of"].endswith("Z")


def test_direct_api_cache_instrumentation_counts_cookie_and_payload_requests(tmp_path):
    artifact = tmp_path / "Understat" / "season.json"
    reader = _DirectApiReader(no_cache=True, no_store=True)
    telemetry = _instrument_reader_cache(
        reader,
        {"no_store": True},
        ttl_seconds=300,
    )

    reader._ensure_cookies()
    reader._request_api("https://fixture.invalid", filepath=artifact)
    result = _result(telemetry)

    assert (reader.cookie_calls, reader.api_calls) == (1, 1)
    assert result["summary"]["cache"]["upstream_requests"] == 2
    assert result["summary"]["cache"]["mode"] == "no-store"


def test_direct_api_warm_cache_defers_cookie_initialization_and_uses_zero_upstream(tmp_path):
    artifact = tmp_path / "Understat" / "season.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b'{"cached":true}')
    reader = _DirectApiReader(network_allowed=False)
    telemetry = _instrument_reader_cache(
        reader,
        {},
        ttl_seconds=300,
    )

    reader._ensure_cookies()
    reader._request_api("https://fixture.invalid", filepath=artifact)
    result = _result(telemetry)

    assert (reader.cookie_calls, reader.api_calls) == (0, 0)
    assert result["summary"]["cache"]["upstream_requests"] == 0
    assert result["summary"]["cache"]["cache_hits"] == 1
    assert result["summary"]["cache"]["mode"] == "warm"


def test_direct_api_stale_cache_forces_cookie_and_payload_refresh(tmp_path):
    artifact = tmp_path / "Understat" / "season.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b'{"stale":true}')
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(artifact, (stale_time, stale_time))
    reader = _DirectApiReader()
    telemetry = _instrument_reader_cache(reader, {}, ttl_seconds=60)

    reader._ensure_cookies()
    reader._request_api("https://fixture.invalid", filepath=artifact)
    result = _result(telemetry)

    assert (reader.cookie_calls, reader.api_calls) == (1, 1)
    assert result["summary"]["cache"]["upstream_requests"] == 2
    assert artifact.read_bytes() == b'{"direct_api":true}'


def test_page_slicing_emits_a_bounded_monotonic_cursor():
    rows = [{"id": value} for value in range(5)]

    first, cursor = _slice_page(rows, {"page": 0, "start_cursor": 0, "chunk_size": 2, "limit": 5})
    second, terminal = _slice_page(rows, {"page": 2, "start_cursor": 4, "chunk_size": 2, "limit": 5})

    assert first == [{"id": 0}, {"id": 1}]
    assert cursor == {"page": 1, "start_cursor": 2}
    assert second == [{"id": 4}]
    assert terminal is None


def test_no_store_generation_digest_is_stable_across_pages_before_slicing():
    rows = [{"id": value} for value in range(3)]

    def page_result(page, start_cursor):
        return _attach_cache_telemetry(
            {"rows": list(rows), "summary": {"count": len(rows)}},
            {
                "cache_hits": 0,
                "upstream_requests": 1,
                "cache_paths": set(),
                "no_store": True,
                "page_payload": {"page": page, "start_cursor": start_cursor, "chunk_size": 2, "limit": 3},
            },
        )

    first = page_result(0, 0)
    second = page_result(1, 2)

    assert first["rows"] != second["rows"]
    assert first["summary"]["cache"]["artifact_digest"] == second["summary"]["cache"]["artifact_digest"]


def test_source_rate_limiter_persists_spacing_and_caps_future_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCCERDATA_DIR", str(tmp_path))
    slept = []

    _acquire_source_rate_limit("espn", 30, clock=lambda: 100.0, sleeper=slept.append)
    times = iter((101.0, 102.0))
    _acquire_source_rate_limit("espn", 30, clock=lambda: next(times), sleeper=slept.append)

    assert slept == [1.0]


def test_warm_cache_hit_does_not_consume_source_quota(tmp_path, monkeypatch):
    artifact = tmp_path / "ESPN" / "schedule.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b'{"fixture":true}')
    calls = []
    monkeypatch.setattr(
        "app.bridges.soccerdata_bridge._acquire_source_rate_limit",
        lambda *_args, **_kwargs: calls.append(True),
    )
    reader = _FixtureReader(network_allowed=False)
    _instrument_reader_cache(
        reader,
        {"source_key": "espn", "requests_per_minute": 30},
        ttl_seconds=300,
    )

    reader.get("https://fixture.invalid", filepath=artifact)

    assert calls == []
