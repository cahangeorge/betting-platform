"""Offline, provider-agnostic parity, canary and rollback contracts for P5."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import NormalDist
from typing import Iterable, Mapping, Sequence

from app.providers.contracts import ProviderExecutionContext, ProviderSourceDescriptor
from app.providers.registry import DEFAULT_PROVIDER_REGISTRY, ProviderRegistry

CANARY_STAGES = (10, 25, 50, 100)
MIN_SMOKE_JOBS_PER_STAGE = 20
MIN_P95_JOBS_PER_STRATUM = 100
ALLOWED_FALLBACK_REASONS = frozenset({"quota_exhausted", "timeout", "upstream_5xx", "transient_circuit_open"})
FORBIDDEN_FALLBACK_REASONS = frozenset({"authorization", "credential", "policy", "schema", "rights"})
_ONE_SIDED_95_Z = NormalDist().inv_cdf(0.95)


def _fingerprint(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("request fingerprint must be a SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("request fingerprint must be a SHA-256 hex digest") from exc
    return value.lower()


def canary_bucket(request_fingerprint: str) -> int:
    """Stable 0..99 bucket; increasing stages are necessarily monotonic."""
    return int(_fingerprint(request_fingerprint)[:16], 16) % 100


def included_in_canary(request_fingerprint: str, stage_percent: int) -> bool:
    if stage_percent not in CANARY_STAGES:
        raise ValueError("canary stage must be one of 10, 25, 50 or 100")
    return canary_bucket(request_fingerprint) < stage_percent


@dataclass(frozen=True, order=True)
class ComparableQuoteKey:
    canonical_match_id: int
    bookmaker_key: str
    market_key: str
    period_key: str
    line: Decimal | None
    selection_key: str

    def __post_init__(self) -> None:
        if self.canonical_match_id <= 0:
            raise ValueError("canonical_match_id must be positive")
        for value in (self.bookmaker_key, self.market_key, self.period_key, self.selection_key):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("comparable quote keys must be nonempty")
        if self.line is not None:
            line = Decimal(str(self.line))
            if not line.is_finite():
                raise ValueError("comparable quote line must be finite")
            object.__setattr__(self, "line", line)


@dataclass(frozen=True)
class ComparableQuote:
    key: ComparableQuoteKey
    price: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.price, bool):
            raise ValueError("price must be an exact decimal")
        price = Decimal(str(self.price))
        if not price.is_finite() or price <= 1:
            raise ValueError("price must be finite and greater than 1")
        object.__setattr__(self, "price", price)


@dataclass(frozen=True)
class StructuralParityReport:
    baseline_count: int
    candidate_count: int
    matched_count: int
    union_count: int
    point_estimate: float
    wilson_lower_95: float
    missing_from_candidate: tuple[ComparableQuoteKey, ...]
    missing_from_baseline: tuple[ComparableQuoteKey, ...]
    absolute_price_differences: tuple[Decimal, ...]

    @property
    def formal_gate_passed(self) -> bool:
        return self.union_count > 0 and self.wilson_lower_95 >= 0.99


def one_sided_wilson_lower(successes: int, total: int, *, confidence: float = 0.95) -> float:
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("Wilson inputs are invalid")
    z = NormalDist().inv_cdf(confidence)
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - spread) / denominator)


def structural_parity(
    baseline: Iterable[ComparableQuote], candidate: Iterable[ComparableQuote]
) -> StructuralParityReport:
    def keyed(values: Iterable[ComparableQuote]) -> dict[ComparableQuoteKey, ComparableQuote]:
        result: dict[ComparableQuoteKey, ComparableQuote] = {}
        for value in values:
            if value.key in result:
                raise ValueError("parity input contains duplicate quote identity")
            result[value.key] = value
        return result

    left, right = keyed(baseline), keyed(candidate)
    left_keys, right_keys = set(left), set(right)
    matched = left_keys & right_keys
    union = left_keys | right_keys
    total = len(union)
    matches = len(matched)
    price_differences = tuple(sorted((abs(left[key].price - right[key].price) for key in matched)))

    def sort_key(key: ComparableQuoteKey) -> tuple[object, ...]:
        return (
            key.canonical_match_id,
            key.bookmaker_key,
            key.market_key,
            key.period_key,
            "" if key.line is None else format(key.line, "f"),
            key.selection_key,
        )

    return StructuralParityReport(
        baseline_count=len(left),
        candidate_count=len(right),
        matched_count=matches,
        union_count=total,
        point_estimate=(matches / total if total else 0.0),
        wilson_lower_95=(one_sided_wilson_lower(matches, total) if total else 0.0),
        missing_from_candidate=tuple(sorted(left_keys - right_keys, key=sort_key)),
        missing_from_baseline=tuple(sorted(right_keys - left_keys, key=sort_key)),
        absolute_price_differences=price_differences,
    )


@dataclass(frozen=True)
class NonInferiorityReport:
    baseline_successes: int
    candidate_successes: int
    baseline_total: int
    candidate_total: int
    difference: float
    lower_bound_95: float
    margin: float
    required_per_arm: int

    @property
    def formally_powered(self) -> bool:
        return min(self.baseline_total, self.candidate_total) >= self.required_per_arm

    @property
    def passed(self) -> bool:
        return self.formally_powered and self.lower_bound_95 >= -self.margin


def noninferiority_sample_size(
    *, assumed_success_rate: float, margin: float = 0.01, power: float = 0.80, confidence: float = 0.95
) -> int:
    if not 0 < assumed_success_rate < 1 or not 0 < margin < 1 or not 0.5 < power < 1:
        raise ValueError("noninferiority design inputs are invalid")
    z_alpha, z_power = NormalDist().inv_cdf(confidence), NormalDist().inv_cdf(power)
    variance = 2 * assumed_success_rate * (1 - assumed_success_rate)
    return math.ceil(((z_alpha + z_power) ** 2 * variance) / (margin**2))


def success_noninferiority(
    *,
    baseline_successes: int,
    baseline_total: int,
    candidate_successes: int,
    candidate_total: int,
    assumed_success_rate: float,
    margin: float = 0.01,
) -> NonInferiorityReport:
    if min(baseline_total, candidate_total) <= 0:
        raise ValueError("noninferiority totals must be positive")
    if not 0 <= baseline_successes <= baseline_total or not 0 <= candidate_successes <= candidate_total:
        raise ValueError("noninferiority successes are invalid")
    p0, p1 = baseline_successes / baseline_total, candidate_successes / candidate_total
    difference = p1 - p0
    standard_error = math.sqrt(p0 * (1 - p0) / baseline_total + p1 * (1 - p1) / candidate_total)
    return NonInferiorityReport(
        baseline_successes=baseline_successes,
        candidate_successes=candidate_successes,
        baseline_total=baseline_total,
        candidate_total=candidate_total,
        difference=difference,
        lower_bound_95=difference - _ONE_SIDED_95_Z * standard_error,
        margin=margin,
        required_per_arm=noninferiority_sample_size(assumed_success_rate=assumed_success_rate, margin=margin),
    )


def nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    if not values or not 0 < percentile <= 1 or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("percentile inputs are invalid")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


@dataclass(frozen=True)
class LatencyReport:
    original_job_count: int
    p95_seconds: float
    bootstrap_lower_95: float | None
    bootstrap_upper_95: float | None

    @property
    def formal(self) -> bool:
        return self.original_job_count >= MIN_P95_JOBS_PER_STRATUM


def latency_p95_report(values: Sequence[float], *, seed: int = 0, bootstrap_samples: int = 2_000) -> LatencyReport:
    p95 = nearest_rank_percentile(values, 0.95)
    if len(values) < MIN_P95_JOBS_PER_STRATUM:
        return LatencyReport(len(values), p95, None, None)
    if bootstrap_samples < 200:
        raise ValueError("bootstrap_samples must be at least 200")
    rng = random.Random(seed)
    estimates = [
        nearest_rank_percentile([values[rng.randrange(len(values))] for _ in values], 0.95)
        for _ in range(bootstrap_samples)
    ]
    return LatencyReport(
        len(values),
        p95,
        nearest_rank_percentile(estimates, 0.025),
        nearest_rank_percentile(estimates, 0.975),
    )


@dataclass(frozen=True)
class OddsFallbackRequest:
    correlation_id: str
    primary_adapter_key: str
    primary_source_key: str
    fallback_adapter_key: str
    fallback_source_key: str
    reason_code: str
    competition_keys: tuple[str, ...]
    market_keys: tuple[str, ...]
    max_events: int
    max_pages: int
    window_start: str
    window_end: str
    worker_lane: str = "provider-browser"

    def __post_init__(self) -> None:
        if self.reason_code not in ALLOWED_FALLBACK_REASONS or self.reason_code in FORBIDDEN_FALLBACK_REASONS:
            raise ValueError("fallback reason is not approved")
        if not self.correlation_id.strip() or not self.competition_keys or not self.market_keys:
            raise ValueError("fallback request requires bounded correlation and scope")
        if not 1 <= self.max_events <= 100 or not 1 <= self.max_pages <= 20:
            raise ValueError("fallback bounds exceed the approved scope")
        if (
            len(self.competition_keys) > 20
            or len(self.market_keys) > 20
            or len(set(self.competition_keys)) != len(self.competition_keys)
            or len(set(self.market_keys)) != len(self.market_keys)
            or any(
                not isinstance(value, str) or not value.strip() or len(value) > 128 for value in self.competition_keys
            )
            or any(not isinstance(value, str) or not value.strip() or len(value) > 128 for value in self.market_keys)
        ):
            raise ValueError("fallback competition and market scope must be bounded and unique")
        if self.fallback_adapter_key != "oddsharvester" or self.fallback_source_key != "oddsportal":
            raise ValueError("fallback must target the registered OddsHarvester source")
        try:
            start = datetime.fromisoformat(self.window_start.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.window_end.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValueError("fallback window must use timezone-aware ISO timestamps") from exc
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or start.utcoffset() is None
            or end.utcoffset() is None
            or not start < end <= start + timedelta(days=7)
        ):
            raise ValueError("fallback window must be ordered and at most seven days")
        object.__setattr__(self, "window_start", start.astimezone(UTC).isoformat().replace("+00:00", "Z"))
        object.__setattr__(self, "window_end", end.astimezone(UTC).isoformat().replace("+00:00", "Z"))

    @property
    def transport_payload(self) -> Mapping[str, object]:
        """Durable job content only; no credentials and never a synchronous call."""
        return {
            "correlation_id": self.correlation_id,
            "reason_code": self.reason_code,
            "competition_keys": list(self.competition_keys),
            "market_keys": list(self.market_keys),
            "max_events": self.max_events,
            "max_pages": self.max_pages,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "worker_lane": self.worker_lane,
        }


def authorize_odds_fallback(
    request: OddsFallbackRequest,
    *,
    context: ProviderExecutionContext = ProviderExecutionContext.PRODUCTION,
    registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
) -> ProviderSourceDescriptor:
    """Apply the normal provider-rights boundary before browser job creation."""

    return registry.require_operation(
        request.fallback_adapter_key,
        request.fallback_source_key,
        "fetch_odds_snapshot",
        context=context,
    )


@dataclass(frozen=True)
class OddsRollbackDecision:
    candidate_admission_percent: int = 0
    drain_admitted_http_runs: bool = True
    retain_observations: bool = True
    restore_previous_provider: bool = True
    delete_history: bool = False


def smoke_stage_ready(*, original_job_ids: Sequence[str]) -> bool:
    return len(set(original_job_ids)) >= MIN_SMOKE_JOBS_PER_STAGE


def request_fingerprint(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
