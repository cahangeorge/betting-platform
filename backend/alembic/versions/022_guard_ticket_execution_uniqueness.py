"""guard one paper execution intent per user ticket

Revision ID: 022
Revises: 021
Create Date: 2026-07-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Never discard or merge financial audit history automatically. If legacy
    # duplicates exist, stop with an actionable error so an operator can
    # reconcile them before enforcing the invariant.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM execution_intents
                GROUP BY user_id, ticket_id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot add uq_execution_intents_user_ticket: duplicate execution intents require reconciliation';
            END IF;
        END
        $$
        """
    )
    op.create_unique_constraint(
        "uq_execution_intents_user_ticket",
        "execution_intents",
        ["user_id", "ticket_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_execution_intents_user_ticket",
        "execution_intents",
        type_="unique",
    )
