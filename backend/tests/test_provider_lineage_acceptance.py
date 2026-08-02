"""ORM acceptance contracts for provider identity and observation lineage.

The service-level replay/concurrency gates are intentionally left to the
executor's public APIs (`provider_observations` and `provider_identity`): these
contracts ensure those services cannot silently weaken their durable schema.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.models import Base


def _table(name: str):
    assert name in Base.metadata.tables, f"missing provider lineage table: {name}"
    return Base.metadata.tables[name]


def _unique_columns(table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _check_sql(table) -> str:
    return "\n".join(
        str(constraint.sqltext) for constraint in table.constraints if isinstance(constraint, CheckConstraint)
    )


def _foreign_keys(table) -> dict[str, str | None]:
    return {foreign_key.parent.name: foreign_key.ondelete for foreign_key in table.foreign_keys}


def _composite_foreign_keys(table) -> set[tuple[tuple[str, ...], tuple[str, ...], str | None]]:
    return {
        (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.target_fullname for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def test_valid_observations_have_exact_replay_identity_and_slot_serialization() -> None:
    slots = _table("provider_observation_slots")
    observations = _table("provider_observations")

    assert ("observation_slot_key",) in _unique_columns(slots)
    assert ("adapter_key", "source_key", "observation_key") in _unique_columns(observations)
    assert {
        "observation_key",
        "observation_slot_key",
        "payload_digest",
        "envelope_digest",
        "normalization_state",
        "conflict_state",
    } <= set(observations.c.keys())
    assert "normalization_state IN ('normalized')" in _check_sql(observations)
    assert _foreign_keys(observations)["slot_id"] == "RESTRICT"


def test_exact_fact_replay_can_add_receipts_without_duplicating_the_fact() -> None:
    receipts = _table("provider_observation_receipts")

    assert ("receipt_key",) in _unique_columns(receipts)
    assert {"observation_id", "provider_job_id", "provider_run_id", "correlation_id"} <= set(receipts.c.keys())
    assert _foreign_keys(receipts)["observation_id"] == "RESTRICT"
    assert _foreign_keys(receipts)["scrape_job_id"] == "SET NULL"
    assert _foreign_keys(receipts)["scheduled_job_run_id"] == "SET NULL"


def test_different_payloads_in_one_slot_keep_an_ordered_restricted_conflict_pair() -> None:
    conflicts = _table("provider_observation_conflicts")

    assert ("left_observation_id", "right_observation_id") in _unique_columns(conflicts)
    assert {"observation_slot_key", "left_observation_id", "right_observation_id"} <= set(conflicts.c.keys())
    assert _foreign_keys(conflicts)["left_observation_id"] == "RESTRICT"
    assert _foreign_keys(conflicts)["right_observation_id"] == "RESTRICT"
    assert "left_observation_id < right_observation_id" in _check_sql(conflicts)


def test_quarantine_is_digest_and_redacted_metadata_only() -> None:
    quarantine = _table("provider_observation_quarantine")

    assert {"raw_digest", "reason_code", "reader_version", "diagnostic_metadata", "metadata_purged_at"} <= set(
        quarantine.c.keys()
    )
    assert "raw_payload" not in quarantine.c.keys()
    assert "raw_envelope" not in quarantine.c.keys()
    assert "payload_json" not in quarantine.c.keys()
    assert "envelope_json" not in quarantine.c.keys()


def test_retention_tombstones_cannot_erase_digests_or_lineage_keys() -> None:
    observations = _table("provider_observations")
    receipts = _table("provider_observation_receipts")
    quarantine = _table("provider_observation_quarantine")

    assert observations.c.payload_json.nullable is True
    assert observations.c.envelope_json.nullable is True
    assert observations.c.body_purged_at.nullable is True
    assert observations.c.payload_digest.nullable is False
    assert observations.c.envelope_digest.nullable is False
    assert receipts.c.received_envelope_json.nullable is True
    assert receipts.c.body_purged_at.nullable is True
    assert receipts.c.received_envelope_digest.nullable is False
    assert quarantine.c.diagnostic_metadata.nullable is True
    assert quarantine.c.raw_digest.nullable is False


def test_mapping_history_requires_predecessor_guard_and_candidate_target_consistency() -> None:
    for name, target_column in (
        ("provider_team_mappings", "team_id"),
        ("provider_competition_mappings", "competition_id"),
        ("provider_match_mappings", "match_id"),
    ):
        mappings = _table(name)
        assert {"predecessor_mapping_id", "selected_candidate_id", "decision_digest", "valid_from", "valid_to"} <= set(
            mappings.c.keys()
        )
        assert mappings.c[target_column].nullable is True
        checks = _check_sql(mappings)
        assert "pending_review" in checks
        assert "accepted" in checks
        assert "rejected" in checks
        assert "selected_candidate_id IS NULL OR predecessor_mapping_id IS NOT NULL" in checks
        assert _foreign_keys(mappings)["predecessor_mapping_id"] == "RESTRICT"
        candidate_table = name.replace("_mappings", "_mapping_candidates")
        assert (
            ("selected_candidate_id", "predecessor_mapping_id", target_column),
            (
                f"{candidate_table}.id",
                f"{candidate_table}.mapping_id",
                f"{candidate_table}.{target_column}",
            ),
            "RESTRICT",
        ) in _composite_foreign_keys(mappings)


def test_mapping_candidates_are_typed_ranked_and_restricted() -> None:
    for name, target_column in (
        ("provider_team_mapping_candidates", "team_id"),
        ("provider_competition_mapping_candidates", "competition_id"),
        ("provider_match_mapping_candidates", "match_id"),
    ):
        candidates = _table(name)
        assert ("mapping_id", "rank") in _unique_columns(candidates)
        assert ("mapping_id", target_column) in _unique_columns(candidates)
        assert "rank > 0" in _check_sql(candidates)
        assert _foreign_keys(candidates)["mapping_id"] == "RESTRICT"
        assert _foreign_keys(candidates)[target_column] == "RESTRICT"


def test_match_keeps_legacy_text_and_gets_nullable_restricted_canonical_identity_keys() -> None:
    matches = _table("matches")

    assert {"home_team", "away_team", "competition", "home_team_id", "away_team_id", "competition_id"} <= set(
        matches.c.keys()
    )
    assert matches.c.home_team_id.nullable is True
    assert matches.c.away_team_id.nullable is True
    assert matches.c.competition_id.nullable is True
    foreign_keys = _foreign_keys(matches)
    assert foreign_keys["home_team_id"] == "RESTRICT"
    assert foreign_keys["away_team_id"] == "RESTRICT"
    assert foreign_keys["competition_id"] == "RESTRICT"
