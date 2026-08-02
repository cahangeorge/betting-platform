from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models import (
    ProviderDatasetGeneration,
    ProviderDatasetGenerationPage,
    ProviderIngestionCheckpoint,
    ScrapedDataset,
)


def test_checkpoint_is_idempotent_partitioned_and_resumable():
    table = ProviderIngestionCheckpoint.__table__
    assert {
        "checkpoint_key",
        "spec_digest",
        "spec_version",
        "partition_key",
        "cursor_json",
        "record_count",
        "observation_count",
        "payload_digest",
        "cache_mode",
        "cache_as_of",
        "fresh_until",
        "run_id_snapshot",
        "scheduled_job_run_id",
        "claim_token",
        "attempt",
    } <= set(table.c.keys())
    unique_columns = {
        tuple(column.name for column in item.columns)
        for item in table.constraints
        if isinstance(item, UniqueConstraint)
    }
    assert ("checkpoint_key",) in unique_columns
    assert ("spec_digest", "partition_key") in unique_columns
    checks = [str(item.sqltext) for item in table.constraints if isinstance(item, CheckConstraint)]
    assert any("no_data" in check and "failed" in check for check in checks)


def test_dataset_metadata_is_legacy_nullable_but_published_rows_are_complete():
    table = ScrapedDataset.__table__
    assert {
        "dataset_key",
        "dataset_group_key",
        "dataset_schema_version",
        "dataset_digest",
        "publication_state",
        "origin_scheduled_job_run_id",
        "origin_run_id_snapshot",
        "source_as_of",
        "fresh_until",
    } <= set(table.c.keys())
    assert all(
        table.c[name].nullable for name in ("dataset_key", "dataset_group_key", "dataset_digest", "publication_state")
    )
    assert any(
        isinstance(item, UniqueConstraint) and tuple(column.name for column in item.columns) == ("dataset_key",)
        for item in table.constraints
    )
    assert any(
        "matches_count > 0" in str(item.sqltext) and "staged" in str(item.sqltext)
        for item in table.constraints
        if isinstance(item, CheckConstraint)
    )


def test_generation_head_and_page_membership_are_separate_from_content_identity():
    generation = ProviderDatasetGeneration.__table__
    page = ProviderDatasetGenerationPage.__table__
    assert {"generation_key", "dataset_group_key", "artifact_digest", "state", "terminal_page"} <= set(
        generation.c.keys()
    )
    assert any(
        isinstance(item, UniqueConstraint) and tuple(column.name for column in item.columns) == ("generation_key",)
        for item in generation.constraints
    )
    assert any(
        isinstance(item, UniqueConstraint)
        and tuple(column.name for column in item.columns) == ("generation_id", "page")
        for item in page.constraints
    )
