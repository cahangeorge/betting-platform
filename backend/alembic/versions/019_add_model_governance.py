"""add versioned model evaluation, certification, and monitoring evidence

Revision ID: 019
Revises: 018
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("build_revision", sa.String(length=100), nullable=False),
        sa.Column("engine_version", sa.String(length=100), nullable=True),
        sa.Column("feature_schema_hash", sa.String(length=64), nullable=False),
        sa.Column("strategy_config_hash", sa.String(length=64), nullable=False),
        sa.Column("training_data_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("training_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('candidate', 'active', 'retired', 'legacy_unversioned')",
            name="ck_model_versions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_key",
            "version",
            "strategy_config_hash",
            "training_data_fingerprint",
            name="uq_model_versions_identity",
        ),
    )
    op.create_index("ix_model_versions_model_key_status", "model_versions", ["model_key", "status"])
    op.create_index(
        "ix_model_versions_training_fingerprint",
        "model_versions",
        ["training_data_fingerprint"],
    )

    op.create_table(
        "model_evaluations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("evaluation_kind", sa.String(length=32), nullable=False, server_default="walk_forward"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_folds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("leakage_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quote_cutoff_violations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fallback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_reasons", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "evaluation_kind IN ('walk_forward', 'paper')",
            name="ck_model_evaluations_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'passed', 'failed', 'insufficient_evidence')",
            name="ck_model_evaluations_status",
        ),
        sa.CheckConstraint("sample_size >= 0 AND resolved_count >= 0", name="ck_model_evaluations_counts"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_evaluations_version_scope",
        "model_evaluations",
        ["model_version_id", "scope_key", "created_at"],
    )
    op.create_index("ix_model_evaluations_status", "model_evaluations", ["status"])

    op.create_table(
        "model_evaluation_folds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("fold_number", sa.Integer(), nullable=False),
        sa.Column("training_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("training_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("test_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("test_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_count", sa.Integer(), nullable=False),
        sa.Column("test_count", sa.Integer(), nullable=False),
        sa.Column("resolved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("fold_number >= 0", name="ck_model_evaluation_folds_number"),
        sa.CheckConstraint(
            "training_count >= 0 AND test_count >= 0 AND resolved_count >= 0",
            name="ck_model_evaluation_folds_counts",
        ),
        sa.ForeignKeyConstraint(["evaluation_id"], ["model_evaluations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_id", "fold_number", name="uq_model_evaluation_folds_number"),
    )
    op.create_index("ix_model_evaluation_folds_evaluation_id", "model_evaluation_folds", ["evaluation_id"])

    op.create_table(
        "model_evaluation_predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fold_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("odds_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("market", sa.String(length=50), nullable=False),
        sa.Column("selection", sa.String(length=50), nullable=False),
        sa.Column("predicted_probability", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("fair_odds", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("quoted_odds", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("quote_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_selection", sa.String(length=50), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "predicted_probability >= 0 AND predicted_probability <= 1",
            name="ck_model_evaluation_predictions_probability",
        ),
        sa.CheckConstraint("fair_odds > 1", name="ck_model_evaluation_predictions_fair_odds"),
        sa.ForeignKeyConstraint(["fold_id"], ["model_evaluation_folds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["odds_snapshot_id"], ["odds_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fold_id",
            "match_id",
            "market",
            "selection",
            name="uq_model_evaluation_predictions_target",
        ),
    )
    op.create_index("ix_model_evaluation_predictions_fold_id", "model_evaluation_predictions", ["fold_id"])
    op.create_index(
        "ix_model_evaluation_predictions_match_market",
        "model_evaluation_predictions",
        ["match_id", "market"],
    )

    op.create_table(
        "prediction_outcomes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_prediction_id", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("actual_selection", sa.String(length=50), nullable=False),
        sa.Column("brier_score", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("log_loss", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["model_prediction_id"], ["model_predictions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_prediction_id", name="uq_prediction_outcomes_model_prediction_id"),
    )
    op.create_index("ix_prediction_outcomes_model_version_id", "prediction_outcomes", ["model_version_id"])
    op.create_index("ix_prediction_outcomes_resolved_at", "prediction_outcomes", ["resolved_at"])

    op.create_table(
        "model_certifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column("model_evaluation_id", sa.Integer(), nullable=False),
        sa.Column("certification_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspension_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "certification_type IN ('walk_forward', 'paper')",
            name="ck_model_certifications_type",
        ),
        sa.CheckConstraint(
            "status IN ('walk_forward_passed', 'paper_collecting', 'certified', 'suspended', 'expired')",
            name="ck_model_certifications_status",
        ),
        sa.CheckConstraint("valid_until > valid_from", name="ck_model_certifications_validity"),
        sa.ForeignKeyConstraint(["model_evaluation_id"], ["model_evaluations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_certifications_version_scope_status",
        "model_certifications",
        ["model_version_id", "scope_key", "status"],
    )
    op.create_index("ix_model_certifications_valid_until", "model_certifications", ["valid_until"])

    op.create_table(
        "model_monitoring_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column("model_certification_id", sa.Integer(), nullable=True),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("sample_size >= 0", name="ck_model_monitoring_snapshots_sample_size"),
        sa.CheckConstraint(
            "severity IN ('healthy', 'warning', 'critical', 'insufficient_evidence')",
            name="ck_model_monitoring_snapshots_severity",
        ),
        sa.CheckConstraint("window_ended_at > window_started_at", name="ck_model_monitoring_snapshots_window"),
        sa.ForeignKeyConstraint(["model_certification_id"], ["model_certifications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_version_id",
            "scope_key",
            "window_ended_at",
            name="uq_model_monitoring_snapshots_window",
        ),
    )
    op.create_index(
        "ix_model_monitoring_snapshots_version_scope",
        "model_monitoring_snapshots",
        ["model_version_id", "scope_key", "window_ended_at"],
    )
    op.create_index("ix_model_monitoring_snapshots_severity", "model_monitoring_snapshots", ["severity"])

    with op.batch_alter_table("prediction_runs") as batch_op:
        batch_op.add_column(sa.Column("model_version_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("strategy_config_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("training_data_fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("training_cutoff_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("governance_snapshot", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_prediction_runs_model_version_id",
            "model_versions",
            ["model_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_prediction_runs_model_version_id", ["model_version_id"])
        batch_op.create_index("ix_prediction_runs_training_fingerprint", ["training_data_fingerprint"])

    with op.batch_alter_table("model_predictions") as batch_op:
        batch_op.add_column(sa.Column("model_version_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_model_predictions_model_version_id",
            "model_versions",
            ["model_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_model_predictions_model_version_id", ["model_version_id"])

    for table in ("ticket_batches", "execution_intents", "scheduled_job_runs"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("model_evaluation_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table}_model_evaluation_id",
                "model_evaluations",
                ["model_evaluation_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index(f"ix_{table}_model_evaluation_id", ["model_evaluation_id"])


def downgrade() -> None:
    for table in ("scheduled_job_runs", "execution_intents", "ticket_batches"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_index(f"ix_{table}_model_evaluation_id")
            batch_op.drop_constraint(f"fk_{table}_model_evaluation_id", type_="foreignkey")
            batch_op.drop_column("model_evaluation_id")

    with op.batch_alter_table("model_predictions") as batch_op:
        batch_op.drop_index("ix_model_predictions_model_version_id")
        batch_op.drop_constraint("fk_model_predictions_model_version_id", type_="foreignkey")
        batch_op.drop_column("model_version_id")

    with op.batch_alter_table("prediction_runs") as batch_op:
        batch_op.drop_index("ix_prediction_runs_training_fingerprint")
        batch_op.drop_index("ix_prediction_runs_model_version_id")
        batch_op.drop_constraint("fk_prediction_runs_model_version_id", type_="foreignkey")
        batch_op.drop_column("governance_snapshot")
        batch_op.drop_column("training_cutoff_at")
        batch_op.drop_column("training_data_fingerprint")
        batch_op.drop_column("strategy_config_hash")
        batch_op.drop_column("model_version_id")

    op.drop_table("model_monitoring_snapshots")
    op.drop_table("model_certifications")
    op.drop_table("prediction_outcomes")
    op.drop_table("model_evaluation_predictions")
    op.drop_table("model_evaluation_folds")
    op.drop_table("model_evaluations")
    op.drop_table("model_versions")
