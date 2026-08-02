import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from enum import StrEnum
from typing import cast

import pytest

from app.providers import (
    ProviderCapability,
    ProviderEnvelopeQuarantine,
    ProviderRecordEnvelope,
    ProviderRecordEnvelopeV2,
    read_provider_record_envelope,
)
from app.providers import contracts as provider_contracts

OBSERVED_AT = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)


def _canonical_digest(raw: dict) -> str:
    def serialize(value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, StrEnum):
            return value.value
        return f"<non-json:{type(value).__module__}.{type(value).__qualname__}>"

    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False, default=serialize).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _v2_envelope() -> ProviderRecordEnvelopeV2:
    return ProviderRecordEnvelopeV2.from_payload(
        adapter_key="penaltyblog",
        source_key="local-model",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-42",
        observed_at=OBSERVED_AT,
        payload={"away_goals": 0.8, "home_goals": 1.2},
        adapter_version="1.9.0",
        transport_version="python-3.13",
        job_id="job-42",
        run_id="run-42",
        correlation_id="correlation-42",
        freshness={"as_of": "2026-08-01T12:30:00Z", "ttl_seconds": 3600},
        provenance={"model": "dixon-coles", "dataset_id": "dataset-42"},
        schema_version="7.3",
        envelope_version="2.0",
    )


def test_v1_reader_round_trips_with_its_existing_canonical_digest():
    v1 = ProviderRecordEnvelope.from_payload(
        provider_key="penaltyblog",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-42",
        observed_at=OBSERVED_AT,
        payload={"away_goals": 0.8, "home_goals": 1.2},
    )

    decoded = read_provider_record_envelope(asdict(v1))

    assert isinstance(decoded, ProviderRecordEnvelope)
    assert decoded.payload == v1.payload
    assert decoded.payload_json == v1.payload_json
    assert decoded.payload_digest == v1.payload_digest


def test_v2_reader_round_trips_provider_identity_lineage_freshness_and_provenance():
    v2 = _v2_envelope()

    decoded = read_provider_record_envelope(asdict(v2))

    assert isinstance(decoded, ProviderRecordEnvelopeV2)
    assert decoded.adapter_key == "penaltyblog"
    assert decoded.source_key == "local-model"
    assert decoded.adapter_version == "1.9.0"
    assert decoded.transport_version == "python-3.13"
    assert (decoded.job_id, decoded.run_id, decoded.correlation_id) == ("job-42", "run-42", "correlation-42")
    assert decoded.freshness == {"as_of": "2026-08-01T12:30:00Z", "ttl_seconds": 3600}
    assert decoded.provenance == {"dataset_id": "dataset-42", "model": "dixon-coles"}
    assert decoded.payload_digest == v2.payload_digest
    assert decoded.schema_version == "7.3"
    assert decoded.envelope_version == "2.0"


def test_unknown_envelope_major_is_quarantined_before_v2_normalization(monkeypatch):
    raw = {
        "envelope_version": "99.0",
        "schema_version": "7.3",
        "payload_json": "secret-payload",
        "headers": {"Authorization": "Bearer top-secret"},
        "cookies": {"session": "cookie-secret"},
        "credentials": "credential-secret",
        "request_url": "https://private.example/token-value",
        "error": "provider-private-error",
        "untrusted": "value",
    }

    def normalizer_must_not_run(**_kwargs):
        raise AssertionError("unknown envelope major must not be normalized")

    monkeypatch.setattr(provider_contracts, "ProviderRecordEnvelopeV2", normalizer_must_not_run)
    decoded = read_provider_record_envelope(raw)

    assert isinstance(decoded, ProviderEnvelopeQuarantine)
    assert decoded.reason == "unsupported_envelope_major"
    assert decoded.raw_digest == _canonical_digest(raw)
    assert decoded.raw_envelope == "[raw envelope redacted]"
    for secret in (
        "secret-payload",
        "top-secret",
        "cookie-secret",
        "credential-secret",
        "private.example",
        "token-value",
        "provider-private-error",
    ):
        assert secret not in repr(decoded)


def test_invalid_v2_payload_is_quarantined_and_is_not_normalized():
    raw = asdict(_v2_envelope())
    raw["payload_json"] = "not-json"
    raw["payload_digest"] = hashlib.sha256(b"not-json").hexdigest()
    decoded = read_provider_record_envelope(raw)
    decoded_again = read_provider_record_envelope(raw)

    assert isinstance(decoded, ProviderEnvelopeQuarantine)
    assert decoded.reason == "invalid_envelope"
    assert decoded.raw_digest == _canonical_digest(raw)
    assert isinstance(decoded_again, ProviderEnvelopeQuarantine)
    assert decoded_again.raw_digest == decoded.raw_digest
    assert decoded.raw_envelope == "[raw envelope redacted]"
    assert "not-json" not in repr(decoded)


def test_v1_reader_accepts_a_valid_payload_schema_version_independent_of_envelope_major():
    v1 = ProviderRecordEnvelope.from_payload(
        provider_key="penaltyblog",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-42",
        observed_at=OBSERVED_AT,
        payload={"home_goals": 1.2},
        schema_version="7.3",
    )

    decoded = read_provider_record_envelope(asdict(v1))

    assert isinstance(decoded, ProviderRecordEnvelope)
    assert decoded.schema_version == "7.3"
    assert decoded.payload_digest == v1.payload_digest


def test_unknown_envelope_major_with_nan_is_quarantined_deterministically_without_leaking_payload():
    raw = {
        "envelope_version": "99.0",
        "schema_version": "7.3",
        "payload": {"score": float("nan"), "credential": "credential-secret"},
    }

    first = read_provider_record_envelope(raw)
    second = read_provider_record_envelope(raw)

    assert isinstance(first, ProviderEnvelopeQuarantine)
    assert first.reason == "unsupported_envelope_major"
    assert isinstance(second, ProviderEnvelopeQuarantine)
    assert first.raw_digest == second.raw_digest
    assert first.raw_envelope == "[raw envelope redacted]"
    assert "credential-secret" not in repr(first)


def test_v2_reader_accepts_a_json_like_utc_iso_observation_timestamp():
    raw = asdict(_v2_envelope())
    raw["observed_at"] = "2026-08-01T12:30:00Z"

    decoded = read_provider_record_envelope(raw)

    assert isinstance(decoded, ProviderRecordEnvelopeV2)
    assert decoded.observed_at == OBSERVED_AT


@pytest.mark.parametrize("observed_at", ["2026-08-01T12:30:00", "not-a-timestamp"])
def test_v2_reader_quarantines_naive_or_invalid_json_like_observation_timestamp(observed_at):
    raw = asdict(_v2_envelope())
    raw["observed_at"] = observed_at

    decoded = read_provider_record_envelope(raw)

    assert isinstance(decoded, ProviderEnvelopeQuarantine)
    assert decoded.reason == "invalid_envelope"


def test_v2_rejects_recursively_sensitive_provenance_metadata():
    with pytest.raises(ValueError):
        ProviderRecordEnvelopeV2.from_payload(
            adapter_key="penaltyblog",
            source_key="local-model",
            capability=ProviderCapability.PREDICTIONS,
            source_id="match-42",
            observed_at=OBSERVED_AT,
            payload={"home_goals": 1.2},
            adapter_version="1.9.0",
            transport_version="python-3.13",
            job_id="job-42",
            run_id="run-42",
            correlation_id="correlation-42",
            freshness={"ttl_seconds": 3600},
            provenance={"upstream": {"access_token": "must-not-persist"}},
        )


def test_v2_rejects_a_negative_freshness_ttl():
    with pytest.raises(ValueError, match="ttl_seconds"):
        ProviderRecordEnvelopeV2.from_payload(
            adapter_key="penaltyblog",
            source_key="local-model",
            capability=ProviderCapability.PREDICTIONS,
            source_id="match-42",
            observed_at=OBSERVED_AT,
            payload={"home_goals": 1.2},
            adapter_version="1.9.0",
            transport_version="python-3.13",
            job_id="job-42",
            run_id="run-42",
            correlation_id="correlation-42",
            freshness={"ttl_seconds": -1},
            provenance={"model": "dixon-coles"},
        )


def test_v2_copies_and_freezes_caller_owned_freshness_and_provenance_metadata():
    freshness = {"ttl_seconds": 3600}
    provenance = {"model": "dixon-coles", "model_version": "1.0"}
    envelope = ProviderRecordEnvelopeV2.from_payload(
        adapter_key="penaltyblog",
        source_key="local-model",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-42",
        observed_at=OBSERVED_AT,
        payload={"home_goals": 1.2},
        adapter_version="1.9.0",
        transport_version="python-3.13",
        job_id="job-42",
        run_id="run-42",
        correlation_id="correlation-42",
        freshness=freshness,
        provenance=provenance,
    )

    freshness["ttl_seconds"] = 1
    provenance["model"] = "mutated"

    assert envelope.freshness["ttl_seconds"] == 3600
    assert envelope.provenance["model"] == "dixon-coles"
    with pytest.raises(TypeError):
        cast(dict[str, object], envelope.freshness)["ttl_seconds"] = 1
    with pytest.raises(TypeError):
        cast(dict[str, object], envelope.provenance)["model"] = "mutated"


def test_quarantine_handles_cyclic_unordered_and_custom_raw_input_deterministically():
    class CustomValue:
        pass

    raw: dict[str, object] = {"envelope_version": "99.0", "unordered": {"z", "a"}, "custom": CustomValue()}
    raw["cycle"] = raw

    first = read_provider_record_envelope(raw)
    second = read_provider_record_envelope(raw)

    assert isinstance(first, ProviderEnvelopeQuarantine)
    assert first.reason == "unsupported_envelope_major"
    assert first.raw_envelope == "[raw envelope redacted]"
    assert isinstance(second, ProviderEnvelopeQuarantine)
    assert first.raw_digest == second.raw_digest


@pytest.mark.parametrize(
    "envelope_version,reason",
    [("99.0", "unsupported_envelope_major"), ("not-a-version", "invalid_envelope_version")],
)
def test_unsupported_or_invalid_envelope_version_quarantines_before_timestamp_parsing(
    monkeypatch, envelope_version, reason
):
    raw = {"envelope_version": envelope_version, "observed_at": "not-a-timestamp", "payload": "secret"}

    def parser_must_not_run(_value):
        raise AssertionError("unsupported envelope version must not parse or normalize payload fields")

    monkeypatch.setattr(provider_contracts, "_parse_reader_observed_at", parser_must_not_run)
    decoded = read_provider_record_envelope(raw)

    assert isinstance(decoded, ProviderEnvelopeQuarantine)
    assert decoded.reason == reason
    assert decoded.raw_envelope == "[raw envelope redacted]"


def test_v2_freshness_as_of_accepts_an_aware_iso_timestamp():
    envelope = ProviderRecordEnvelopeV2.from_payload(
        adapter_key="penaltyblog",
        source_key="local-model",
        capability=ProviderCapability.PREDICTIONS,
        source_id="match-42",
        observed_at=OBSERVED_AT,
        payload={"home_goals": 1.2},
        adapter_version="1.9.0",
        transport_version="python-3.13",
        job_id="job-42",
        run_id="run-42",
        correlation_id="correlation-42",
        freshness={"as_of": "2026-08-01T12:30:00Z", "ttl_seconds": 3600},
        provenance={"model": "dixon-coles"},
    )

    assert envelope.freshness["as_of"] == "2026-08-01T12:30:00Z"


@pytest.mark.parametrize("as_of", ["2026-08-01T12:30:00", "not-a-timestamp"])
def test_v2_freshness_as_of_rejects_naive_or_invalid_timestamp(as_of):
    with pytest.raises(ValueError):
        ProviderRecordEnvelopeV2.from_payload(
            adapter_key="penaltyblog",
            source_key="local-model",
            capability=ProviderCapability.PREDICTIONS,
            source_id="match-42",
            observed_at=OBSERVED_AT,
            payload={"home_goals": 1.2},
            adapter_version="1.9.0",
            transport_version="python-3.13",
            job_id="job-42",
            run_id="run-42",
            correlation_id="correlation-42",
            freshness={"as_of": as_of},
            provenance={"model": "dixon-coles"},
        )


def test_v2_metadata_rejects_dict_setitem_bypass_and_asdict_reader_round_trip_stays_supported():
    envelope = _v2_envelope()

    with pytest.raises(TypeError):
        dict.__setitem__(cast(dict[str, object], envelope.freshness), "ttl_seconds", 1)
    with pytest.raises(TypeError):
        dict.__setitem__(cast(dict[str, object], envelope.provenance), "model", "mutated")

    decoded = read_provider_record_envelope(asdict(envelope))
    assert isinstance(decoded, ProviderRecordEnvelopeV2)
    assert decoded.freshness == envelope.freshness
    assert decoded.provenance == envelope.provenance


def test_quarantine_key_string_collisions_are_deterministic_and_never_raise():
    first_raw = {"envelope_version": "99.0", 1: "number-key", "1": "string-key"}
    second_raw = {"1": "string-key", 1: "number-key", "envelope_version": "99.0"}

    first = read_provider_record_envelope(first_raw)
    second = read_provider_record_envelope(second_raw)

    assert isinstance(first, ProviderEnvelopeQuarantine)
    assert isinstance(second, ProviderEnvelopeQuarantine)
    assert isinstance(second, ProviderEnvelopeQuarantine)
    assert first.raw_digest == second.raw_digest
    assert first.raw_envelope == second.raw_envelope == "[raw envelope redacted]"


def test_quarantine_same_class_custom_keys_are_deterministic_across_reverse_insertion_order():
    class OpaqueKey:
        pass

    first_key = OpaqueKey()
    second_key = OpaqueKey()
    first_raw = {"envelope_version": "99.0", first_key: "first", second_key: "second"}
    second_raw = {second_key: "second", first_key: "first", "envelope_version": "99.0"}

    first = read_provider_record_envelope(first_raw)
    second = read_provider_record_envelope(second_raw)

    assert isinstance(first, ProviderEnvelopeQuarantine)
    assert isinstance(second, ProviderEnvelopeQuarantine)
    assert first.raw_digest == second.raw_digest
