"""Offline P5 contract benchmark; never performs provider/browser egress.

The report proves normalization parity and canary/statistical harness behavior
over equivalent fixtures.  It is deliberately not live promotion evidence.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from decimal import Decimal

from app.providers.odds import OddsEventObservationV1, validate_odds_event_payload
from app.providers.oddsharvester_odds import convert_oddsharvester_record
from app.providers.sportmonks_odds import SportmonksOddsAdapter
from app.services.odds_rollout import (
    CANARY_STAGES,
    ComparableQuote,
    ComparableQuoteKey,
    included_in_canary,
    latency_p95_report,
    noninferiority_sample_size,
    request_fingerprint,
    smoke_stage_ready,
    structural_parity,
)

OBSERVED_AT = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _sportmonks_rows() -> list[dict]:
    fixture = {
        "id": 42,
        "starting_at": "2026-08-02T12:00:00Z",
        "league": {"id": 8},
        "participants": [
            {"name": "Home FC", "meta": {"location": "home"}},
            {"name": "Away FC", "meta": {"location": "away"}},
        ],
    }
    bookmaker = {"id": 10, "name": "Book"}
    market = {"id": 1, "name": "1X2"}
    return [
        {
            "id": index,
            "fixture_id": 42,
            "fixture": fixture,
            "bookmaker": bookmaker,
            "market": market,
            "label": label,
            "value": price,
            "latest_bookmaker_update": "2026-08-01T12:00:00Z",
        }
        for index, label, price in ((101, "1", "2.10"), (102, "X", "3.20"), (103, "2", "4.30"))
    ]


def _oddsharvester_record() -> dict:
    return {
        "scraped_date": "2026-08-01 12:00:00 UTC",
        "match_date": "2026-08-02 12:00:00 UTC",
        "match_link": "https://www.oddsportal.com/football/test/league/home-away-AbC123xy/",
        "home_team": "Home FC",
        "away_team": "Away FC",
        "league_name": "Test League",
        "1x2_market": [{"bookmaker_name": "Book", "period": "FullTime", "1": "2.10", "X": "3.20", "2": "4.30"}],
    }


def _sportmonks_observation() -> OddsEventObservationV1:
    envelope = SportmonksOddsAdapter._envelopes(
        _sportmonks_rows(),
        scope="prematch",
        observed_at=OBSERVED_AT,
        job_id="offline-job",
        run_id="offline-run",
        correlation_id="offline-correlation",
    )[0]
    return validate_odds_event_payload(json.loads(envelope.payload_json))


def _comparable(observation: OddsEventObservationV1) -> tuple[ComparableQuote, ...]:
    selection_aliases = {"home": "home", "draw": "draw", "away": "away"}
    return tuple(
        ComparableQuote(
            key=ComparableQuoteKey(
                canonical_match_id=1,
                bookmaker_key=quote.provider_bookmaker_name.casefold(),
                market_key=quote.market_key,
                period_key=quote.period_key,
                line=quote.line,
                selection_key=selection_aliases[quote.selection_key],
            ),
            price=Decimal(quote.price),
        )
        for quote in observation.quotes
    )


def run_benchmark(*, iterations: int = 500) -> dict:
    if iterations < 100:
        raise ValueError("iterations must be at least 100")
    sportmonks_latencies: list[float] = []
    oddsharvester_latencies: list[float] = []
    candidate = baseline = None
    for _ in range(iterations):
        started = time.perf_counter()
        candidate = _sportmonks_observation()
        sportmonks_latencies.append(time.perf_counter() - started)
        started = time.perf_counter()
        baseline = convert_oddsharvester_record(_oddsharvester_record())
        oddsharvester_latencies.append(time.perf_counter() - started)
    assert candidate is not None and baseline is not None
    parity = structural_parity(_comparable(baseline), _comparable(candidate))
    fingerprints = [request_fingerprint({"offline_job": index}) for index in range(400)]
    canary = {
        str(stage): {
            "eligible_jobs": sum(included_in_canary(value, stage) for value in fingerprints),
            "smoke_ready": smoke_stage_ready(
                original_job_ids=[value for value in fingerprints if included_in_canary(value, stage)]
            ),
        }
        for stage in CANARY_STAGES
    }
    candidate_latency = latency_p95_report(sportmonks_latencies, seed=42)
    baseline_latency = latency_p95_report(oddsharvester_latencies, seed=42)
    return {
        "contract": "odds-provider-offline-benchmark/v1",
        "network_requests": 0,
        "browser_requests": 0,
        "live_provider_evidence": False,
        "promotion_proof": False,
        "promotion_blockers": ["provider_approval", "credentials", "live_canary", "end_to_end_workload"],
        "iterations": iterations,
        "parity": {
            "matched": parity.matched_count,
            "union": parity.union_count,
            "point_estimate": parity.point_estimate,
            "wilson_lower_95": parity.wilson_lower_95,
            "formal_gate_passed": parity.formal_gate_passed,
            "max_absolute_price_difference": str(max(parity.absolute_price_differences, default=Decimal(0))),
        },
        "normalization_latency_only": {
            "sportmonks_p95_seconds": candidate_latency.p95_seconds,
            "oddsharvester_p95_seconds": baseline_latency.p95_seconds,
            "formal_sample_count": candidate_latency.original_job_count,
        },
        "canary_contract": canary,
        "formal_success_required_per_arm_at_99_percent_baseline": noninferiority_sample_size(assumed_success_rate=0.99),
    }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), sort_keys=True, separators=(",", ":")))
