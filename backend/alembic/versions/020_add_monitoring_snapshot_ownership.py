"""add explicit tenant ownership to model monitoring snapshots

Revision ID: 020
Revises: 019
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("model_monitoring_snapshots") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_model_monitoring_snapshots_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Certification-linked history has an unambiguous owner. For older
    # unlinked rows, backfill only when the model version belongs to exactly
    # one tenant; ambiguous legacy rows remain NULL and are never returned by
    # the tenant-filtered application queries.
    op.execute(
        sa.text(
            """
            UPDATE model_monitoring_snapshots
            SET user_id = (
                SELECT model_evaluations.user_id
                FROM model_certifications
                JOIN model_evaluations
                  ON model_evaluations.id = model_certifications.model_evaluation_id
                WHERE model_certifications.id = model_monitoring_snapshots.model_certification_id
            )
            WHERE model_certification_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE model_monitoring_snapshots
            SET user_id = (
                SELECT MIN(model_evaluations.user_id)
                FROM model_evaluations
                WHERE model_evaluations.model_version_id = model_monitoring_snapshots.model_version_id
                HAVING COUNT(DISTINCT model_evaluations.user_id) = 1
            )
            WHERE user_id IS NULL
            """
        )
    )

    with op.batch_alter_table("model_monitoring_snapshots") as batch_op:
        batch_op.drop_constraint("uq_model_monitoring_snapshots_window", type_="unique")
        batch_op.create_unique_constraint(
            "uq_model_monitoring_snapshots_tenant_window",
            ["user_id", "model_version_id", "scope_key", "window_ended_at"],
        )
        batch_op.create_index(
            "ix_model_monitoring_snapshots_user_version_scope",
            ["user_id", "model_version_id", "scope_key", "window_ended_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("model_monitoring_snapshots") as batch_op:
        batch_op.drop_index("ix_model_monitoring_snapshots_user_version_scope")
        batch_op.drop_constraint("uq_model_monitoring_snapshots_tenant_window", type_="unique")
        batch_op.create_unique_constraint(
            "uq_model_monitoring_snapshots_window",
            ["model_version_id", "scope_key", "window_ended_at"],
        )
        batch_op.drop_constraint("fk_model_monitoring_snapshots_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
