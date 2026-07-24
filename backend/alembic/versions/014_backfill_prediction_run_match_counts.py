"""backfill prediction run counts to unique predicted matches

Revision ID: 014
Revises: 013
Create Date: 2026-07-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE prediction_runs
        SET matches_count = (
            SELECT COUNT(DISTINCT model_predictions.match_id)
            FROM model_predictions
            WHERE model_predictions.run_id = prediction_runs.id
        )
        WHERE prediction_runs.status <> 'running'
        """
    )


def downgrade() -> None:
    # The previous values mixed prediction-row and target-match semantics and
    # cannot be reconstructed reliably. The corrected counts remain valid.
    pass
