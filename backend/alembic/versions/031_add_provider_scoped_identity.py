"""add provider scoped canonical identity and temporal mappings

Revision ID: 031
Revises: 030
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "031"
down_revision: str | None = "030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(8)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(f"ix_{name}_lookup", name, ["sport", "normalized_name"])


def _mapping(kind: str, target_table: str, target_column: str) -> None:
    table = f"provider_{kind}_mappings"
    candidate = f"provider_{kind}_mapping_candidates"
    op.create_table(
        table,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("adapter_key", sa.String(100), nullable=False),
        sa.Column("source_key", sa.String(100), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("resolver_kind", sa.String(100), nullable=False),
        sa.Column("resolver_id", sa.String(255)),
        sa.Column("rule_version", sa.String(100)),
        sa.Column("reason", sa.Text()),
        sa.Column("decision_digest", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "evidence_observation_id", sa.Integer(), sa.ForeignKey("provider_observations.id", ondelete="RESTRICT")
        ),
        sa.Column("predecessor_mapping_id", sa.Integer()),
        sa.Column("selected_candidate_id", sa.Integer()),
        sa.Column(target_column, sa.Integer(), sa.ForeignKey(f"{target_table}.id", ondelete="RESTRICT")),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by_decision_digest", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("state IN ('pending_review', 'accepted', 'rejected')", name=f"ck_{kind}_mapping_state"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name=f"ck_{kind}_mapping_confidence"
        ),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name=f"ck_{kind}_mapping_interval"),
        sa.CheckConstraint(f"(state = 'accepted') = ({target_column} IS NOT NULL)", name=f"ck_{kind}_mapping_target"),
        sa.CheckConstraint(
            "selected_candidate_id IS NULL OR state = 'accepted'",
            name=f"ck_{kind}_mapping_selected_candidate_state",
        ),
        sa.CheckConstraint(
            "selected_candidate_id IS NULL OR predecessor_mapping_id IS NOT NULL",
            name=f"ck_{kind}_mapping_selected_candidate_predecessor",
        ),
        sa.CheckConstraint(
            "(valid_to IS NULL AND closed_at IS NULL AND closed_by_decision_digest IS NULL) OR "
            "(valid_to IS NOT NULL AND closed_at IS NOT NULL AND closed_by_decision_digest IS NOT NULL)",
            name=f"ck_{kind}_mapping_closure",
        ),
    )
    op.create_index(
        f"uq_{kind}_mapping_current_source",
        table,
        ["adapter_key", "source_key", "source_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_table(
        candidate,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mapping_id", sa.Integer(), sa.ForeignKey(f"{table}.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            target_column, sa.Integer(), sa.ForeignKey(f"{target_table}.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("evidence", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("mapping_id", target_column, name=f"uq_provider_{kind}_candidate_target"),
        sa.UniqueConstraint("mapping_id", "rank", name=f"uq_provider_{kind}_candidate_rank"),
        sa.UniqueConstraint("id", "mapping_id", target_column, name=f"uq_provider_{kind}_candidate_selection"),
        sa.CheckConstraint("rank > 0", name=f"ck_provider_{kind}_candidate_rank"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name=f"ck_provider_{kind}_candidate_confidence"),
    )
    op.create_index(f"ix_{kind}_mapping_candidate_target", candidate, [target_column])
    op.create_index(f"ix_{kind}_mapping_candidate_rank", candidate, ["mapping_id", "rank"])
    op.create_foreign_key(
        f"fk_{kind}_mapping_predecessor", table, table, ["predecessor_mapping_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        f"fk_{kind}_mapping_selected_candidate",
        table,
        candidate,
        ["selected_candidate_id", "predecessor_mapping_id", target_column],
        ["id", "mapping_id", target_column],
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    _entity("teams")
    _entity("competitions")
    _mapping("team", "teams", "team_id")
    _mapping("competition", "competitions", "competition_id")
    _mapping("match", "matches", "match_id")
    with op.batch_alter_table("matches") as batch:
        batch.add_column(sa.Column("home_team_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("away_team_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("competition_id", sa.Integer(), nullable=True))
    for col, table in (("home_team_id", "teams"), ("away_team_id", "teams"), ("competition_id", "competitions")):
        op.execute("SET LOCAL lock_timeout = '2s'")
        op.execute("SET LOCAL statement_timeout = '10s'")
        op.create_foreign_key(
            f"fk_matches_{col}", "matches", table, [col], ["id"], ondelete="RESTRICT", postgresql_not_valid=True
        )


def downgrade() -> None:
    raise RuntimeError("provider identity migration is expand-only; destructive downgrade is not supported")
