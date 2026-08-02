from decimal import Decimal

import pytest

from app.providers.registry import ProviderPolicyError
from app.services.odds_rollout import (
    ComparableQuote,
    ComparableQuoteKey,
    OddsFallbackRequest,
    OddsRollbackDecision,
    authorize_odds_fallback,
    included_in_canary,
    latency_p95_report,
    noninferiority_sample_size,
    request_fingerprint,
    smoke_stage_ready,
    structural_parity,
    success_noninferiority,
)


def _key(selection="home"):
    return ComparableQuoteKey(1, "book", "1x2", "full_time", None, selection)


def test_canary_cohorts_are_deterministic_and_monotonic():
    fingerprints = [request_fingerprint({"job": value}) for value in range(1_000)]
    cohorts = [{value for value in fingerprints if included_in_canary(value, stage)} for stage in (10, 25, 50, 100)]
    assert cohorts[0] <= cohorts[1] <= cohorts[2] <= cohorts[3]
    assert cohorts[3] == set(fingerprints)


def test_structural_parity_uses_union_denominator_and_separates_price_difference():
    left = [ComparableQuote(_key("home"), Decimal("2.0")), ComparableQuote(_key("away"), Decimal("4.0"))]
    right = [ComparableQuote(_key("home"), Decimal("2.2")), ComparableQuote(_key("draw"), Decimal("3.0"))]
    report = structural_parity(left, right)
    assert (report.matched_count, report.union_count, report.point_estimate) == (1, 3, 1 / 3)
    assert report.absolute_price_differences == (Decimal("0.2"),)
    assert report.missing_from_candidate == (_key("away"),)
    assert not report.formal_gate_passed


def test_structural_parity_rejects_intersection_only_duplicate_inputs():
    quote = ComparableQuote(_key(), Decimal("2"))
    with pytest.raises(ValueError, match="duplicate"):
        structural_parity([quote, quote], [quote])


def test_noninferiority_requires_preregistered_power_and_lower_bound():
    required = noninferiority_sample_size(assumed_success_rate=0.98)
    provisional = success_noninferiority(
        baseline_successes=20, baseline_total=20, candidate_successes=20, candidate_total=20, assumed_success_rate=0.98
    )
    assert provisional.required_per_arm == required
    assert not provisional.formally_powered
    assert not provisional.passed
    powered = success_noninferiority(
        baseline_successes=required,
        baseline_total=required,
        candidate_successes=required,
        candidate_total=required,
        assumed_success_rate=0.98,
    )
    assert powered.passed


def test_p95_is_provisional_below_100_original_jobs_and_bootstrapped_after():
    provisional = latency_p95_report([float(value) for value in range(1, 21)])
    assert provisional.p95_seconds == 19.0
    assert not provisional.formal
    assert provisional.bootstrap_lower_95 is None
    formal = latency_p95_report([float(value) for value in range(1, 101)], seed=42, bootstrap_samples=200)
    repeat = latency_p95_report([float(value) for value in range(1, 101)], seed=42, bootstrap_samples=200)
    assert formal.formal and formal == repeat


def test_smoke_counts_unique_original_jobs_not_retries():
    assert not smoke_stage_ready(original_job_ids=["one"] * 20)
    assert smoke_stage_ready(original_job_ids=[str(value) for value in range(20)])


def test_fallback_is_bounded_browser_only_and_rejects_policy_failures():
    request = OddsFallbackRequest(
        correlation_id="corr-1",
        primary_adapter_key="sportmonks-v3-odds",
        primary_source_key="sportmonks-football-v3-standard-odds",
        fallback_adapter_key="oddsharvester",
        fallback_source_key="oddsportal",
        reason_code="quota_exhausted",
        competition_keys=("england-premier-league",),
        market_keys=("1x2",),
        max_events=20,
        max_pages=2,
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-02T00:00:00Z",
    )
    assert request.transport_payload["worker_lane"] == "provider-browser"
    assert "token" not in repr(request.transport_payload).lower()
    with pytest.raises(ValueError, match="not approved"):
        OddsFallbackRequest(**{**request.__dict__, "reason_code": "authorization"})
    with pytest.raises(ValueError, match="bounds"):
        OddsFallbackRequest(**{**request.__dict__, "max_events": 101})
    with pytest.raises(ValueError, match="seven days"):
        OddsFallbackRequest(**{**request.__dict__, "window_end": "2026-09-01T00:00:00Z"})
    with pytest.raises(ValueError, match="unique"):
        OddsFallbackRequest(**{**request.__dict__, "market_keys": ("1x2", "1x2")})
    with pytest.raises(ProviderPolicyError, match="approval"):
        authorize_odds_fallback(request)


def test_rollback_drains_without_deleting_history():
    decision = OddsRollbackDecision()
    assert decision.candidate_admission_percent == 0
    assert decision.drain_admitted_http_runs
    assert decision.retain_observations and not decision.delete_history
