"""guard concurrent identical prediction runs

Revision ID: 015
Revises: 014
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTIVE_DEDUPE_PREDICATE = sa.text("dedupe_enabled AND input_hash IS NOT NULL AND status IN ('running', 'completed')")


def upgrade() -> None:
    with op.batch_alter_table("prediction_runs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "dedupe_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.create_index(
        "uq_prediction_runs_active_dedupe",
        "prediction_runs",
        ["user_id", "input_hash"],
        unique=True,
        postgresql_where=ACTIVE_DEDUPE_PREDICATE,
        sqlite_where=sa.text("dedupe_enabled = 1 AND input_hash IS NOT NULL AND status IN ('running', 'completed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_prediction_runs_active_dedupe", table_name="prediction_runs")
    with op.batch_alter_table("prediction_runs") as batch_op:
        batch_op.drop_column("dedupe_enabled")
