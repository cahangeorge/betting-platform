"""Acceptance contracts for the provider lineage expand-only Alembic revisions.

These tests deliberately inspect migration source as well as ORM metadata.  SQLite
cannot execute PostgreSQL-specific ``NOT VALID`` and concurrent-index semantics,
so a promotion run still needs the real PostgreSQL evidence required by the ADR.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _revision_source(revision: str) -> str:
    matches = list(VERSIONS.glob(f"{revision}_*.py"))
    assert len(matches) == 1, f"expected one migration for revision {revision}, found {matches}"
    return matches[0].read_text(encoding="utf-8")


def _upgrade_source(revision: str) -> str:
    source = _revision_source(revision)
    return source.split("def upgrade", maxsplit=1)[1].split("def downgrade", maxsplit=1)[0]


def test_provider_lineage_revisions_extend_the_existing_linear_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["043"]
    assert script.get_revision("041").down_revision == "040"
    assert script.get_revision("040").down_revision == "039"
    assert script.get_revision("039").down_revision == "038"
    assert script.get_revision("038").down_revision == "037"
    assert script.get_revision("037").down_revision == "036"
    assert script.get_revision("030").down_revision == "029"
    assert script.get_revision("031").down_revision == "030"
    assert script.get_revision("032").down_revision == "031"


def test_observation_revision_creates_only_new_lineage_tables() -> None:
    source = _revision_source("030")

    for table in (
        "provider_observation_slots",
        "provider_observations",
        "provider_observation_receipts",
        "provider_observation_conflicts",
        "provider_observation_dataset_links",
        "provider_observation_quarantine",
    ):
        assert table in source
    assert 'add_column("matches"' not in source
    assert "drop_table" not in _upgrade_source("030")


def test_observation_revision_keeps_conflicts_ordered_and_replay_receipts_append_only() -> None:
    source = _revision_source("030")

    for required in (
        "observation_slot_key",
        "observation_key",
        "receipt_key",
        "left_observation_id",
        "right_observation_id",
        "left_observation_id < right_observation_id",
        'ondelete="RESTRICT"',
    ):
        assert required in source
    assert "provider_observation_receipts" in source
    assert "UniqueConstraint" in source


def test_observation_revision_encodes_secret_safe_retention_tombstones() -> None:
    source = _revision_source("030")

    for required in (
        "payload_json",
        "envelope_json",
        "body_purged_at",
        "received_envelope_json",
        "metadata_purged_at",
        "raw_digest",
        "diagnostic_metadata",
    ):
        assert required in source
    assert "raw_payload" not in source
    assert "raw_envelope" not in source


def test_identity_revision_adds_nullable_match_foreign_keys_without_a_backfill() -> None:
    source = _revision_source("031")

    for table in ("teams", "competitions"):
        assert table in source
    assert 'table = f"provider_{kind}_mappings"' in source
    for column in ("home_team_id", "away_team_id", "competition_id"):
        assert column in source
    assert "NOT VALID" in source or "postgresql_not_valid=True" in source
    assert "lock_timeout" in source
    assert "statement_timeout" in source
    assert "UPDATE matches" not in source
    assert "INSERT INTO matches" not in source


def test_identity_revision_requires_temporal_predecessor_and_typed_candidate_guards() -> None:
    source = _revision_source("031")

    for required in (
        "pending_review",
        "accepted",
        "rejected",
        "predecessor_mapping_id",
        "selected_candidate_id",
        "decision_digest",
        "valid_from",
        "valid_to",
        "closed_by_decision_digest",
    ):
        assert required in source
    assert 'candidate = f"provider_{kind}_mapping_candidates"' in source
    assert "postgresql_where" in source
    assert 'ondelete="RESTRICT"' in source


def test_index_revision_uses_postgresql_concurrent_index_recovery_and_constraint_validation() -> None:
    source = _revision_source("032")

    for required in (
        "autocommit_block",
        "CREATE INDEX CONCURRENTLY",
        "DROP INDEX CONCURRENTLY",
        "indisvalid",
        "VALIDATE CONSTRAINT",
        "lock_timeout",
        "statement_timeout",
        "ix_matches_home_team_id",
        "ix_matches_away_team_id",
        "ix_matches_competition_id",
    ):
        assert required in source
