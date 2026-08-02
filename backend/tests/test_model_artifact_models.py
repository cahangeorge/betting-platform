import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, insert
from sqlalchemy.exc import IntegrityError

from app.models import (
    Base,
    ModelArtifact,
    ModelEvaluation,
    ModelEvaluationFold,
    ModelEvaluationPrediction,
    ModelFeatureSet,
    ModelVersion,
    PredictionRun,
)


def test_feature_set_and_artifact_models_expose_versioned_digest_only_lineage():
    feature_set = ModelFeatureSet.__table__
    artifact = ModelArtifact.__table__

    assert {"feature_key", "version", "schema_version", "spec_json", "spec_fingerprint"} <= set(feature_set.c.keys())
    assert {"artifact_key", "artifact_digest", "manifest_json", "runtime_dependency_fingerprint"} <= set(
        artifact.c.keys()
    )
    assert "pickle" not in artifact.c.keys()
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in artifact.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert {("artifact_key",)} <= unique_columns
    assert ("artifact_digest",) not in unique_columns
    checks = [str(constraint.sqltext) for constraint in artifact.constraints if isinstance(constraint, CheckConstraint)]
    assert any("length(artifact_key) = 64" in check for check in checks)
    assert any("length(artifact_digest) = 64" in check for check in checks)


def test_model_versions_keep_legacy_feature_and_runtime_lineage_nullable():
    columns = ModelVersion.__table__.c

    assert columns.feature_set_id.nullable is True
    assert columns.runtime_dependency_fingerprint.nullable is True


def test_pipeline_lineage_extensions_are_nullable_for_legacy_rows():
    run_columns = PredictionRun.__table__.c
    evaluation_columns = ModelEvaluation.__table__.c

    assert run_columns.pipeline_contract_version.nullable is True
    assert run_columns.model_artifact_id.nullable is True
    assert run_columns.source_generation_id.nullable is True
    assert run_columns.forecast_at.nullable is True
    assert run_columns.output_fingerprint.nullable is True
    assert evaluation_columns.pipeline_contract_version.nullable is True
    assert evaluation_columns.evaluation_fingerprint.nullable is True
    assert ModelEvaluationFold.__table__.c.feature_artifact_id.nullable is True
    assert ModelEvaluationPrediction.__table__.c.forecast_at.nullable is True

    checks = [
        str(constraint.sqltext)
        for constraint in PredictionRun.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert any("model_artifact_id IS NOT NULL" in check for check in checks)


def test_completed_artifact_requires_exact_row_and_output_completeness():
    artifact = ModelArtifact.__table__
    checks = [str(constraint.sqltext) for constraint in artifact.constraints if isinstance(constraint, CheckConstraint)]

    assert any("expected_row_count = written_row_count" in check for check in checks)
    assert any("expected_output_count = written_output_count" in check for check in checks)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(artifact).values(
                    artifact_key="a" * 64,
                    artifact_digest="b" * 64,
                    model_version_id=1,
                    source_generation_id=1,
                    feature_set_id=1,
                    artifact_kind="feature_matrix",
                    state="completed",
                    manifest_json={},
                    runtime_dependency_fingerprint="c" * 64,
                    expected_row_count=2,
                    written_row_count=1,
                    expected_output_count=2,
                    written_output_count=2,
                )
            )
