from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_model_artifact_migration_extends_the_current_ingestion_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("036")

    assert script.get_heads() == ["043"]
    assert script.get_revision("041").down_revision == "040"
    assert script.get_revision("040").down_revision == "039"
    assert script.get_revision("039").down_revision == "038"
    assert script.get_revision("038").down_revision == "037"
    assert script.get_revision("037").down_revision == "036"
    assert revision is not None
    assert revision.down_revision == "035"


def test_model_artifact_migration_is_expand_only() -> None:
    source = script_source("036_harden_model_artifact_trust_boundary.py")

    assert "def downgrade()" in source
    assert "expand-only" in source
    assert "pickle" not in source.lower()
    assert "model_artifact_id" in source
    assert "fk_prediction_runs_model_artifact" in source
    assert "trg_model_artifacts_immutable" in source
    assert "enforce_model_artifact_immutability" in source
    assert "OLD.state <> 'staged'" in source
    assert "terminal model artifacts are immutable and cannot be deleted" in source


def script_source(name: str) -> str:
    return Path("alembic/versions", name).read_text()
