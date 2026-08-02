import hashlib
import json
import math
import re
from collections.abc import Iterator
from collections.abc import Mapping as AbcMapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

_PROVIDER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_SCHEMA_VERSION_PATTERN = re.compile(r"^[1-9][0-9]*\.[0-9]+$")
_SENSITIVE_ENVELOPE_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "access_key",
        "bearer",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "headers",
        "password",
        "payload",
        "payload_json",
        "secret",
        "token",
    }
)
_PROVENANCE_KEYS = frozenset(
    {"model", "model_version", "dataset_id", "dataset_digest", "source_revision", "transform_version", "license_id"}
)
_FRESHNESS_KEYS = frozenset({"as_of", "ttl_seconds"})


class _FrozenJsonMapping(AbcMapping[str, Any]):
    """A JSON-scalar mapping that remains usable with dataclasses.asdict."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return repr(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AbcMapping):
            return self._values == dict(other)
        return NotImplemented

    def __deepcopy__(self, memo: dict[int, object]) -> dict[str, Any]:
        return self._values.copy()


class ProviderKind(StrEnum):
    DATA = "data"
    ODDS = "odds"
    MODEL = "model"
    EXECUTION = "execution"


class ProviderTransport(StrEnum):
    API = "api"
    SUBPROCESS = "subprocess"
    BROWSER = "browser"
    LIBRARY = "library"


class ProviderCapability(StrEnum):
    FIXTURES = "fixtures"
    RESULTS = "results"
    ODDS = "odds"
    STATISTICS = "statistics"
    LINEUPS = "lineups"
    INJURIES = "injuries"
    FEATURES = "features"
    RATINGS = "ratings"
    PREDICTIONS = "predictions"
    BACKTESTS = "backtests"
    EXECUTION = "execution"


class ProductionPolicy(StrEnum):
    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"
    DISABLED = "disabled"


class ProviderExecutionContext(StrEnum):
    """Declared environment for a provider invocation.

    This is intentionally not a permission switch: an approval-required source
    remains closed unless a future, auditable approval mechanism is added.
    """

    PRODUCTION = "production"
    CANARY = "canary"
    TEST = "test"


@dataclass(frozen=True)
class ProviderQuotaPolicy:
    """Per-source upstream quota. Null limits are explicitly unlimited."""

    requests_per_minute: int | None = None
    requests_per_day: int | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("requests per minute", self.requests_per_minute),
            ("requests per day", self.requests_per_day),
        ):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"Provider quota {label} must be a nonnegative integer or null")

    @classmethod
    def unlimited(cls) -> "ProviderQuotaPolicy":
        return cls()


@dataclass(frozen=True)
class ProviderFreshnessPolicy:
    """Per-source maximum observation age. Null is explicitly not applicable."""

    max_age_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.max_age_seconds is not None and (
            isinstance(self.max_age_seconds, bool)
            or not isinstance(self.max_age_seconds, int)
            or self.max_age_seconds < 0
        ):
            raise ValueError("Provider freshness maximum age must be a nonnegative integer or null")

    @classmethod
    def not_applicable(cls) -> "ProviderFreshnessPolicy":
        return cls()


def _normalise_capabilities(capabilities: object) -> frozenset[ProviderCapability]:
    try:
        return frozenset(ProviderCapability(capability) for capability in capabilities)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("Provider descriptor contains an invalid enum value") from exc


def _coerce_quota_policy(value: object) -> ProviderQuotaPolicy:
    if isinstance(value, ProviderQuotaPolicy):
        return value
    if not isinstance(value, Mapping) or set(value) - {"requests_per_minute", "requests_per_day"}:
        raise ValueError("Provider source quota policy is invalid")
    return ProviderQuotaPolicy(
        requests_per_minute=value.get("requests_per_minute"),
        requests_per_day=value.get("requests_per_day"),
    )


def _coerce_freshness_policy(value: object) -> ProviderFreshnessPolicy:
    if isinstance(value, ProviderFreshnessPolicy):
        return value
    if not isinstance(value, Mapping) or set(value) - {"max_age_seconds"}:
        raise ValueError("Provider source freshness policy is invalid")
    return ProviderFreshnessPolicy(max_age_seconds=value.get("max_age_seconds"))


def _validate_key(value: str, *, label: str) -> None:
    if not _PROVIDER_KEY_PATTERN.fullmatch(value):
        raise ValueError(f"Provider {label} must be a lowercase slug between 2 and 63 characters")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    try:
        value = dict(payload)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Provider payload must contain canonical JSON values") from exc


def _quarantine_json(raw_envelope: Mapping[str, Any] | str) -> str:
    """Produce a stable digest input even if a malformed envelope is not JSON-safe."""
    if isinstance(raw_envelope, str):
        return raw_envelope

    def _normalise(value: object, ancestors: set[int]) -> object:
        is_container = isinstance(value, (Mapping, list, tuple, set, frozenset))
        value_id = id(value)
        if is_container and value_id in ancestors:
            return "<cycle>"
        if is_container:
            ancestors = {*ancestors, value_id}
        if isinstance(value, Mapping):
            if all(isinstance(key, str) for key in value):
                return {key: _normalise(item, ancestors) for key, item in value.items()}

            def _key_record(key: object) -> dict[str, str]:
                if isinstance(key, StrEnum):
                    return {"type": "str_enum", "value": key.value}
                if isinstance(key, (str, int, float, bool)) or key is None:
                    return {"type": type(key).__qualname__, "value": repr(key)}
                return {"type": f"{type(key).__module__}.{type(key).__qualname__}", "value": "<non-json-key>"}

            records = [{"key": _key_record(key), "value": _normalise(item, ancestors)} for key, item in value.items()]
            return {
                "<typed-mapping>": sorted(
                    records,
                    key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False),
                )
            }
        if isinstance(value, (list, tuple)):
            return [_normalise(item, ancestors) for item in value]
        if isinstance(value, (set, frozenset)):
            normalized = [_normalise(item, ancestors) for item in value]
            return sorted(
                normalized,
                key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False),
            )
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, StrEnum):
            return value.value
        if isinstance(value, float) and not math.isfinite(value):
            return f"<non-finite:{value!r}>"
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return f"<non-json:{type(value).__module__}.{type(value).__qualname__}>"

    return json.dumps(
        _normalise(raw_envelope, set()),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _validate_payload_json(payload_json: str, payload_digest: str) -> None:
    try:
        payload = json.loads(payload_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Provider payload must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Provider payload must be a JSON object")
    canonical_payload = _canonical_json(payload)
    if payload_json != canonical_payload:
        raise ValueError("Provider payload JSON must use the canonical representation")
    expected_digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if payload_digest != expected_digest:
        raise ValueError("Provider payload digest does not match the canonical payload")


def _validate_observed_at(observed_at: datetime) -> None:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("Provider observation time must be timezone-aware")


def _parse_reader_observed_at(value: object) -> datetime:
    if isinstance(value, datetime):
        _validate_observed_at(value)
        return value
    if not isinstance(value, str):
        raise ValueError("Provider observation time must be timezone-aware")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Provider observation time must be an ISO timezone-aware timestamp") from exc
    _validate_observed_at(parsed)
    return parsed


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return (
        normalized in _SENSITIVE_ENVELOPE_KEYS
        or "token" in normalized
        or "secret" in normalized
        or "credential" in normalized
    )


def _validate_safe_provenance(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("Provider provenance must be a JSON object")
    for key, item in value.items():
        normalized_key = str(key)
        if normalized_key not in _PROVENANCE_KEYS or _is_sensitive_key(normalized_key):
            raise ValueError("Provider provenance cannot contain credentials or auth state")
        if isinstance(item, (Mapping, list, tuple, set, frozenset)):
            raise ValueError("Provider provenance values must be scalar metadata")
        if not isinstance(item, (str, int, float, bool)) and item is not None:
            raise ValueError("Provider provenance values must be JSON scalars")


@dataclass(frozen=True)
class ProviderDescriptor:
    """Stable adapter descriptor; upstream policy belongs to ProviderSourceDescriptor."""

    key: str
    display_name: str
    kind: ProviderKind
    transport: ProviderTransport
    capabilities: frozenset[ProviderCapability]
    production_policy: ProductionPolicy
    policy_reason: str = ""

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "kind", ProviderKind(self.kind))
            object.__setattr__(self, "transport", ProviderTransport(self.transport))
            object.__setattr__(self, "production_policy", ProductionPolicy(self.production_policy))
            object.__setattr__(self, "capabilities", _normalise_capabilities(self.capabilities))
        except (TypeError, ValueError) as exc:
            raise ValueError("Provider descriptor contains an invalid enum value") from exc
        _validate_key(self.key, label="key")
        if not self.display_name.strip():
            raise ValueError("Provider display name cannot be empty")
        if not self.capabilities:
            raise ValueError("Provider must declare at least one capability")
        if self.production_policy is not ProductionPolicy.ALLOWED and not self.policy_reason.strip():
            raise ValueError("Restricted providers must explain their production policy")

    @property
    def adapter_key(self) -> str:
        """Explicit adapter identity while retaining the v1 `key` API."""
        return self.key

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class ProviderSourceDescriptor:
    """Policy and capability boundary for one real upstream source."""

    adapter_key: str
    source_key: str
    capabilities: frozenset[ProviderCapability]
    production_policy: ProductionPolicy
    policy_reason: str = ""
    quota_policy: ProviderQuotaPolicy = ProviderQuotaPolicy.unlimited()
    freshness_policy: ProviderFreshnessPolicy = ProviderFreshnessPolicy.not_applicable()
    body_retention_days: int | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "capabilities", _normalise_capabilities(self.capabilities))
            object.__setattr__(self, "production_policy", ProductionPolicy(self.production_policy))
        except (TypeError, ValueError) as exc:
            raise ValueError("Provider source descriptor contains an invalid enum value") from exc
        try:
            object.__setattr__(self, "quota_policy", _coerce_quota_policy(self.quota_policy))
            object.__setattr__(self, "freshness_policy", _coerce_freshness_policy(self.freshness_policy))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Provider source quota or freshness policy is invalid: {exc}") from exc
        _validate_key(self.adapter_key, label="adapter key")
        _validate_key(self.source_key, label="source key")
        if not self.capabilities:
            raise ValueError("Provider source must declare at least one capability")
        if self.body_retention_days is not None and (
            isinstance(self.body_retention_days, bool)
            or not isinstance(self.body_retention_days, int)
            or self.body_retention_days < 0
        ):
            raise ValueError("Provider source body retention must be a nonnegative integer or null")
        if self.production_policy is not ProductionPolicy.ALLOWED and not self.policy_reason.strip():
            raise ValueError("Restricted provider sources must explain their production policy")
        if not isinstance(self.quota_policy, ProviderQuotaPolicy) or not isinstance(
            self.freshness_policy, ProviderFreshnessPolicy
        ):
            raise ValueError("Provider source quota and freshness policies are invalid")

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class ProviderRecordEnvelope:
    """Provider Envelope v1. Kept unchanged for existing callers and stored records."""

    provider_key: str
    capability: ProviderCapability
    source_id: str
    observed_at: datetime
    payload_json: str
    payload_digest: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "capability", ProviderCapability(self.capability))
        except ValueError as exc:
            raise ValueError("Provider record contains an invalid capability") from exc
        _validate_key(self.provider_key, label="key")
        if not self.source_id.strip():
            raise ValueError("Provider source ID cannot be empty")
        _validate_observed_at(self.observed_at)
        if not _SCHEMA_VERSION_PATTERN.fullmatch(self.schema_version):
            raise ValueError("Provider schema version must use major.minor format")
        _validate_payload_json(self.payload_json, self.payload_digest)

    @classmethod
    def from_payload(
        cls,
        *,
        provider_key: str,
        capability: ProviderCapability,
        source_id: str,
        observed_at: datetime,
        payload: Mapping[str, Any],
        schema_version: str = "1.0",
    ) -> "ProviderRecordEnvelope":
        payload_json = _canonical_json(payload)
        return cls(
            provider_key=provider_key,
            capability=capability,
            source_id=source_id,
            observed_at=observed_at,
            payload_json=payload_json,
            payload_digest=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            schema_version=schema_version,
        )

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self.payload_json)
        assert isinstance(value, dict)
        return value


@dataclass(frozen=True)
class ProviderRecordEnvelopeV2:
    """Provider Envelope v2 with explicit upstream identity and execution lineage."""

    adapter_key: str
    source_key: str
    capability: ProviderCapability
    source_id: str
    observed_at: datetime
    payload_json: str
    payload_digest: str
    adapter_version: str
    transport_version: str
    job_id: str
    run_id: str
    correlation_id: str
    freshness: Mapping[str, Any]
    provenance: Mapping[str, Any]
    schema_version: str = "1.0"
    envelope_version: str = "2.0"

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "capability", ProviderCapability(self.capability))
        except ValueError as exc:
            raise ValueError("Provider record contains an invalid capability") from exc
        _validate_key(self.adapter_key, label="adapter key")
        _validate_key(self.source_key, label="source key")
        if not self.source_id.strip():
            raise ValueError("Provider source ID cannot be empty")
        for label, value in (
            ("adapter version", self.adapter_version),
            ("transport version", self.transport_version),
            ("job ID", self.job_id),
            ("run ID", self.run_id),
            ("correlation ID", self.correlation_id),
        ):
            if not value.strip():
                raise ValueError(f"Provider {label} cannot be empty")
        _validate_observed_at(self.observed_at)
        if not _SCHEMA_VERSION_PATTERN.fullmatch(self.schema_version):
            raise ValueError("Provider payload schema version must use major.minor format")
        if self.envelope_version.split(".", 1)[0] != "2" or not _SCHEMA_VERSION_PATTERN.fullmatch(
            self.envelope_version
        ):
            raise ValueError("Provider Envelope v2 envelope version must use 2.minor format")
        if not isinstance(self.freshness, Mapping) or not isinstance(self.provenance, Mapping):
            raise ValueError("Provider freshness and provenance must be JSON objects")
        freshness = _canonical_json(self.freshness)
        provenance = _canonical_json(self.provenance)
        freshness_value = json.loads(freshness)
        if set(freshness_value) - _FRESHNESS_KEYS:
            raise ValueError("Provider freshness contains an unsupported field")
        for key, value in freshness_value.items():
            if key == "as_of" and not isinstance(value, str):
                raise ValueError("Provider freshness as_of must be an ISO timestamp string")
            if key == "as_of":
                _parse_reader_observed_at(value)
        ttl_seconds = freshness_value.get("ttl_seconds")
        if ttl_seconds is not None and (
            isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds < 0
        ):
            raise ValueError("Provider freshness ttl_seconds must be a nonnegative integer")
        _validate_safe_provenance(self.provenance)
        object.__setattr__(self, "freshness", _FrozenJsonMapping(freshness_value))
        object.__setattr__(self, "provenance", _FrozenJsonMapping(json.loads(provenance)))
        _validate_payload_json(self.payload_json, self.payload_digest)

    @classmethod
    def from_payload(
        cls,
        *,
        adapter_key: str,
        source_key: str,
        capability: ProviderCapability,
        source_id: str,
        observed_at: datetime,
        payload: Mapping[str, Any],
        adapter_version: str,
        transport_version: str,
        job_id: str,
        run_id: str,
        correlation_id: str,
        freshness: Mapping[str, Any],
        provenance: Mapping[str, Any],
        schema_version: str = "1.0",
        envelope_version: str = "2.0",
    ) -> "ProviderRecordEnvelopeV2":
        payload_json = _canonical_json(payload)
        return cls(
            adapter_key=adapter_key,
            source_key=source_key,
            capability=capability,
            source_id=source_id,
            observed_at=observed_at,
            payload_json=payload_json,
            payload_digest=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            adapter_version=adapter_version,
            transport_version=transport_version,
            job_id=job_id,
            run_id=run_id,
            correlation_id=correlation_id,
            freshness=freshness,
            provenance=provenance,
            schema_version=schema_version,
            envelope_version=envelope_version,
        )

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self.payload_json)
        assert isinstance(value, dict)
        return value


@dataclass(frozen=True)
class ProviderEnvelopeQuarantine:
    """Fail-closed representation of an envelope that must not be normalized."""

    reason: str
    raw_envelope: Mapping[str, Any] | str
    raw_digest: str

    @classmethod
    def from_raw(cls, raw_envelope: Mapping[str, Any] | str, *, reason: str) -> "ProviderEnvelopeQuarantine":
        raw_json = _quarantine_json(raw_envelope)
        return cls(
            reason=reason,
            raw_envelope="[raw envelope redacted]",
            raw_digest=hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
        )

    @property
    def digest(self) -> str:
        """Generic digest alias for quarantine persistence callers."""
        return self.raw_digest


def read_provider_record_envelope(
    raw_envelope: Mapping[str, Any],
) -> ProviderRecordEnvelope | ProviderRecordEnvelopeV2 | ProviderEnvelopeQuarantine:
    """Read supported envelopes; invalid or unknown major versions are quarantined."""

    try:
        envelope_version = raw_envelope.get("envelope_version")
        if envelope_version is not None:
            if not isinstance(envelope_version, str) or not _SCHEMA_VERSION_PATTERN.fullmatch(envelope_version):
                return ProviderEnvelopeQuarantine.from_raw(raw_envelope, reason="invalid_envelope_version")
            if envelope_version.split(".", 1)[0] != "2":
                return ProviderEnvelopeQuarantine.from_raw(raw_envelope, reason="unsupported_envelope_major")
        parsed = dict(raw_envelope)
        if "observed_at" in parsed:
            parsed["observed_at"] = _parse_reader_observed_at(parsed["observed_at"])
        if envelope_version is None:
            return ProviderRecordEnvelope(**parsed)  # type: ignore[arg-type]
        return ProviderRecordEnvelopeV2(**parsed)  # type: ignore[arg-type]
    except (AttributeError, TypeError, ValueError):
        return ProviderEnvelopeQuarantine.from_raw(raw_envelope, reason="invalid_envelope")
