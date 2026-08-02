"""Canonical provider-scoped identity and review mappings.

These models are intentionally imported by ``app.models`` only once the
identity migrations are present; no existing Match text key is replaced.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

if TYPE_CHECKING:
    pass


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (Index("ix_teams_lookup", "sport", "normalized_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Competition(Base):
    __tablename__ = "competitions"
    __table_args__ = (Index("ix_competitions_lookup", "sport", "normalized_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class _ProviderMappingBase:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    resolver_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    resolver_id: Mapped[str | None] = mapped_column(String(255))
    rule_version: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text)
    decision_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    evidence_observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_observations.id", ondelete="RESTRICT")
    )
    predecessor_mapping_id: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_decision_digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TeamProviderMapping(_ProviderMappingBase, Base):
    __tablename__ = "provider_team_mappings"
    __table_args__ = (
        CheckConstraint("state IN ('pending_review', 'accepted', 'rejected')", name="ck_team_mapping_state"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_team_mapping_confidence"
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_team_mapping_interval"),
        CheckConstraint("(state = 'accepted') = (team_id IS NOT NULL)", name="ck_team_mapping_target"),
        CheckConstraint(
            "selected_candidate_id IS NULL OR state = 'accepted'", name="ck_team_mapping_selected_candidate_state"
        ),
        CheckConstraint(
            "selected_candidate_id IS NULL OR predecessor_mapping_id IS NOT NULL",
            name="ck_team_mapping_selected_candidate_predecessor",
        ),
        CheckConstraint(
            "(valid_to IS NULL AND closed_at IS NULL AND closed_by_decision_digest IS NULL) OR "
            "(valid_to IS NOT NULL AND closed_at IS NOT NULL AND closed_by_decision_digest IS NOT NULL)",
            name="ck_team_mapping_closure",
        ),
        ForeignKeyConstraint(
            ["selected_candidate_id", "predecessor_mapping_id", "team_id"],
            [
                "provider_team_mapping_candidates.id",
                "provider_team_mapping_candidates.mapping_id",
                "provider_team_mapping_candidates.team_id",
            ],
            name="fk_team_mapping_selected_candidate",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "uq_team_mapping_current_source",
            "adapter_key",
            "source_key",
            "source_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
    )
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    predecessor_mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_team_mappings.id", ondelete="RESTRICT")
    )
    selected_candidate_id: Mapped[int | None] = mapped_column(Integer)


class CompetitionProviderMapping(_ProviderMappingBase, Base):
    __tablename__ = "provider_competition_mappings"
    __table_args__ = (
        CheckConstraint("state IN ('pending_review', 'accepted', 'rejected')", name="ck_competition_mapping_state"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_competition_mapping_confidence"
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_competition_mapping_interval"),
        CheckConstraint("(state = 'accepted') = (competition_id IS NOT NULL)", name="ck_competition_mapping_target"),
        CheckConstraint(
            "selected_candidate_id IS NULL OR state = 'accepted'",
            name="ck_competition_mapping_selected_candidate_state",
        ),
        CheckConstraint(
            "selected_candidate_id IS NULL OR predecessor_mapping_id IS NOT NULL",
            name="ck_competition_mapping_selected_candidate_predecessor",
        ),
        CheckConstraint(
            "(valid_to IS NULL AND closed_at IS NULL AND closed_by_decision_digest IS NULL) OR "
            "(valid_to IS NOT NULL AND closed_at IS NOT NULL AND closed_by_decision_digest IS NOT NULL)",
            name="ck_competition_mapping_closure",
        ),
        ForeignKeyConstraint(
            ["selected_candidate_id", "predecessor_mapping_id", "competition_id"],
            [
                "provider_competition_mapping_candidates.id",
                "provider_competition_mapping_candidates.mapping_id",
                "provider_competition_mapping_candidates.competition_id",
            ],
            name="fk_competition_mapping_selected_candidate",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "uq_competition_mapping_current_source",
            "adapter_key",
            "source_key",
            "source_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
    )
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"))
    predecessor_mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_competition_mappings.id", ondelete="RESTRICT")
    )
    selected_candidate_id: Mapped[int | None] = mapped_column(Integer)


class MatchProviderMapping(_ProviderMappingBase, Base):
    __tablename__ = "provider_match_mappings"
    __table_args__ = (
        CheckConstraint("state IN ('pending_review', 'accepted', 'rejected')", name="ck_match_mapping_state"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_match_mapping_confidence"
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_match_mapping_interval"),
        CheckConstraint("(state = 'accepted') = (match_id IS NOT NULL)", name="ck_match_mapping_target"),
        CheckConstraint(
            "selected_candidate_id IS NULL OR state = 'accepted'", name="ck_match_mapping_selected_candidate_state"
        ),
        CheckConstraint(
            "selected_candidate_id IS NULL OR predecessor_mapping_id IS NOT NULL",
            name="ck_match_mapping_selected_candidate_predecessor",
        ),
        CheckConstraint(
            "(valid_to IS NULL AND closed_at IS NULL AND closed_by_decision_digest IS NULL) OR "
            "(valid_to IS NOT NULL AND closed_at IS NOT NULL AND closed_by_decision_digest IS NOT NULL)",
            name="ck_match_mapping_closure",
        ),
        ForeignKeyConstraint(
            ["selected_candidate_id", "predecessor_mapping_id", "match_id"],
            [
                "provider_match_mapping_candidates.id",
                "provider_match_mapping_candidates.mapping_id",
                "provider_match_mapping_candidates.match_id",
            ],
            name="fk_match_mapping_selected_candidate",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "uq_match_mapping_current_source",
            "adapter_key",
            "source_key",
            "source_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
    )
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="RESTRICT"))
    predecessor_mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_match_mappings.id", ondelete="RESTRICT")
    )
    selected_candidate_id: Mapped[int | None] = mapped_column(Integer)


class TeamProviderMappingCandidate(Base):
    __tablename__ = "provider_team_mapping_candidates"
    __table_args__ = (
        UniqueConstraint("mapping_id", "team_id", name="uq_provider_team_candidate_target"),
        UniqueConstraint("mapping_id", "rank", name="uq_provider_team_candidate_rank"),
        UniqueConstraint("id", "mapping_id", "team_id", name="uq_provider_team_candidate_selection"),
        CheckConstraint("rank > 0", name="ck_provider_team_candidate_rank"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_provider_team_candidate_confidence"),
        Index("ix_team_mapping_candidate_target", "team_id"),
        Index("ix_team_mapping_candidate_rank", "mapping_id", "rank"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapping_id: Mapped[int] = mapped_column(
        ForeignKey("provider_team_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionProviderMappingCandidate(Base):
    __tablename__ = "provider_competition_mapping_candidates"
    __table_args__ = (
        UniqueConstraint("mapping_id", "competition_id", name="uq_provider_competition_candidate_target"),
        UniqueConstraint("mapping_id", "rank", name="uq_provider_competition_candidate_rank"),
        UniqueConstraint("id", "mapping_id", "competition_id", name="uq_provider_competition_candidate_selection"),
        CheckConstraint("rank > 0", name="ck_provider_competition_candidate_rank"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_provider_competition_candidate_confidence"),
        Index("ix_competition_mapping_candidate_target", "competition_id"),
        Index("ix_competition_mapping_candidate_rank", "mapping_id", "rank"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapping_id: Mapped[int] = mapped_column(
        ForeignKey("provider_competition_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MatchProviderMappingCandidate(Base):
    __tablename__ = "provider_match_mapping_candidates"
    __table_args__ = (
        UniqueConstraint("mapping_id", "match_id", name="uq_provider_match_candidate_target"),
        UniqueConstraint("mapping_id", "rank", name="uq_provider_match_candidate_rank"),
        UniqueConstraint("id", "mapping_id", "match_id", name="uq_provider_match_candidate_selection"),
        CheckConstraint("rank > 0", name="ck_provider_match_candidate_rank"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_provider_match_candidate_confidence"),
        Index("ix_match_mapping_candidate_target", "match_id"),
        Index("ix_match_mapping_candidate_rank", "mapping_id", "rank"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapping_id: Mapped[int] = mapped_column(
        ForeignKey("provider_match_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="RESTRICT"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
