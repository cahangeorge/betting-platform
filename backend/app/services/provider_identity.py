"""Fail-closed commands for provider-scoped identity decisions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Mapping

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.provider_identity import (
    Competition,
    CompetitionProviderMapping,
    CompetitionProviderMappingCandidate,
    MatchProviderMapping,
    MatchProviderMappingCandidate,
    Team,
    TeamProviderMapping,
    TeamProviderMappingCandidate,
)

MappingType = Literal["team", "competition", "match"]
_MAPPING = {
    "team": (TeamProviderMapping, TeamProviderMappingCandidate, Team, "team_id"),
    "competition": (CompetitionProviderMapping, CompetitionProviderMappingCandidate, Competition, "competition_id"),
    "match": (MatchProviderMapping, MatchProviderMappingCandidate, Match, "match_id"),
}
_SENSITIVE_EVIDENCE_KEYS = frozenset(
    {"authorization", "api_key", "apikey", "cookie", "credential", "headers", "password", "secret", "token"}
)
_IDENTITY_KEY = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


class StaleIdentityDecisionError(ValueError):
    pass


class InvalidIdentityTransitionError(ValueError):
    pass


@dataclass(frozen=True)
class IdentityDecision:
    entity_type: MappingType
    adapter_key: str
    source_key: str
    source_id: str
    command_kind: Literal["propose", "decide", "reopen", "remap"]
    state: Literal["pending_review", "accepted", "rejected"]
    canonical_target_id: int | None
    expected_predecessor_mapping_id: int | None
    selected_candidate_id: int | None = None
    evidence_observation_id: int | None = None
    resolver_kind: str = "manual"
    resolver_id: str | None = None
    rule_version: str | None = None
    reason: str | None = None
    confidence: Decimal | None = None

    def digest(self) -> str:
        """SHA-256 of canonical JSON decision fields; generated times excluded."""
        value = {
            "adapter_key": self.adapter_key,
            "canonical_target_id": self.canonical_target_id,
            "confidence": (
                format(self.confidence.normalize(), "f") if self.confidence is not None and self.confidence else "0"
            )
            if self.confidence is not None
            else None,
            "entity_type": self.entity_type,
            "evidence_observation_id": self.evidence_observation_id,
            "predecessor_mapping_id": self.expected_predecessor_mapping_id,
            "reason": " ".join(self.reason.split()) if self.reason else None,
            "resolver_id": self.resolver_id,
            "resolver_kind": self.resolver_kind,
            "rule_version": self.rule_version,
            "selected_candidate_id": self.selected_candidate_id,
            "source_id": self.source_id,
            "source_key": self.source_key,
            "state": self.state,
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()


@dataclass(frozen=True)
class IdentityCandidateProposal:
    entity_type: MappingType
    mapping_id: int
    canonical_target_id: int
    rank: int
    confidence: Decimal
    evidence: Mapping[str, Any]

    def evidence_json(self) -> str:
        def validate(value: object) -> None:
            if isinstance(value, Mapping):
                for key, item in value.items():
                    normalized = str(key).casefold()
                    if not isinstance(key, str) or any(token in normalized for token in _SENSITIVE_EVIDENCE_KEYS):
                        raise InvalidIdentityTransitionError("candidate evidence contains sensitive metadata")
                    validate(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    validate(item)

        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank <= 0:
            raise InvalidIdentityTransitionError("candidate rank must be positive")
        if not isinstance(self.confidence, Decimal) or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise InvalidIdentityTransitionError("candidate confidence must be a Decimal in [0, 1]")
        validate(self.evidence)
        try:
            return json.dumps(self.evidence, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise InvalidIdentityTransitionError("candidate evidence must be canonical JSON") from exc


# A caller must supply this exact version to make an automatic decision.  The
# version is deliberately not inferred from deployed code: changing the rule
# requires an explicit new version at the call site and remains auditable in
# the successor mapping.
EXACT_SINGLETON_RULE_VERSION = "exact-singleton/v1"


@dataclass(frozen=True)
class IdentityReviewCandidate:
    """A redacted candidate shown in the deterministic review queue."""

    id: int
    canonical_target_id: int
    rank: int
    confidence: Decimal
    evidence: str | None


@dataclass(frozen=True)
class IdentityReviewItem:
    """One open provider identity mapping plus its ordered candidates."""

    entity_type: MappingType
    mapping_id: int
    adapter_key: str
    source_key: str
    source_id: str
    candidates: tuple[IdentityReviewCandidate, ...]


def _review_item_sort_key(item: IdentityReviewItem) -> tuple[str, str, str, str, int]:
    """Stable cross-entity ordering for an operator-facing review queue."""
    return (item.adapter_key, item.source_key, item.source_id, item.entity_type, item.mapping_id)


def _is_exact_singleton_candidate(item: IdentityReviewItem) -> IdentityReviewCandidate | None:
    """Return the only candidate eligible for the v1 deterministic rule.

    ``exact-singleton/v1`` intentionally accepts only a sole rank-one,
    full-confidence candidate.  Any competing candidate, even one with lower
    rank or confidence, stays pending for human review rather than letting a
    tie-breaker become an undocumented resolver rule.
    """
    if len(item.candidates) != 1:
        return None
    candidate = item.candidates[0]
    if candidate.rank != 1 or candidate.confidence != Decimal("1"):
        return None
    return candidate


def _lock_value(d: IdentityDecision) -> int:
    raw = hashlib.sha256(f"{d.entity_type}\0{d.adapter_key}\0{d.source_key}\0{d.source_id}".encode()).digest()
    return int.from_bytes(raw[:8], "big", signed=True)


def validate_decision_shape(d: IdentityDecision, current_state: str | None) -> None:
    if d.entity_type not in _MAPPING:
        raise InvalidIdentityTransitionError("unknown identity entity type")
    if not _IDENTITY_KEY.fullmatch(d.adapter_key) or not _IDENTITY_KEY.fullmatch(d.source_key):
        raise InvalidIdentityTransitionError("adapter and source identity must be lowercase slugs")
    if not d.source_id.strip() or len(d.source_id) > 255:
        raise InvalidIdentityTransitionError("source identity must be nonempty and at most 255 characters")
    if current_state not in {None, "pending_review", "accepted", "rejected"}:
        raise InvalidIdentityTransitionError("unknown predecessor state")
    expected_kind = {None: "propose", "pending_review": "decide", "rejected": "reopen", "accepted": "remap"}[
        current_state
    ]
    if d.command_kind != expected_kind:
        raise InvalidIdentityTransitionError("command kind does not match predecessor state")
    if d.state not in {"pending_review", "accepted", "rejected"}:
        raise InvalidIdentityTransitionError("unknown identity state")
    if d.confidence is not None and (
        not isinstance(d.confidence, Decimal) or not Decimal("0") <= d.confidence <= Decimal("1")
    ):
        raise InvalidIdentityTransitionError("confidence must be a Decimal in [0, 1]")
    if (d.state == "accepted") != (d.canonical_target_id is not None):
        raise InvalidIdentityTransitionError("accepted decisions and canonical targets must match")
    if current_state is None and d.state != "pending_review":
        raise InvalidIdentityTransitionError("first decision must be pending review")
    allowed = {"pending_review": {"accepted", "rejected"}, "rejected": {"pending_review"}, "accepted": {"accepted"}}
    if current_state is not None and d.state not in allowed[current_state]:
        raise InvalidIdentityTransitionError("invalid identity state transition")


async def _current(session: AsyncSession, model: type, d: IdentityDecision):
    statement = (
        select(model)
        .where(
            model.adapter_key == d.adapter_key,
            model.source_key == d.source_key,
            model.source_id == d.source_id,
            model.valid_to.is_(None),
        )
        .with_for_update()
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def apply_identity_decision(session: AsyncSession, d: IdentityDecision):
    """Append an explicit decision under a transaction-scoped PostgreSQL lock.

    A concurrent unique winner is accepted only when it has the identical
    digest; otherwise the caller receives a stale-decision error.
    """
    if d.entity_type not in _MAPPING:
        raise InvalidIdentityTransitionError("unknown identity entity type")
    model, candidate_model, target_model, target_field = _MAPPING[d.entity_type]
    await session.execute(select(func.pg_advisory_xact_lock(_lock_value(d))))
    current = await _current(session, model, d)
    current_id = current.id if current else None
    if current_id != d.expected_predecessor_mapping_id:
        # Idempotent replay is only the already-current identical winner; a
        # stale accept is never reinterpreted as a remap.
        if current is not None and current.decision_digest == d.digest():
            return current
        raise StaleIdentityDecisionError("expected predecessor no longer current")
    validate_decision_shape(d, current.state if current else None)
    if d.canonical_target_id is not None and await session.get(target_model, d.canonical_target_id) is None:
        raise InvalidIdentityTransitionError("canonical target does not exist")
    if d.evidence_observation_id is not None:
        from app.models.provider_observation import ProviderObservation

        if await session.get(ProviderObservation, d.evidence_observation_id) is None:
            raise InvalidIdentityTransitionError("evidence observation does not exist")
    if d.selected_candidate_id is not None:
        if current is None or current.state != "pending_review":
            raise InvalidIdentityTransitionError("selected candidate requires pending predecessor")
        candidate = await session.get(candidate_model, d.selected_candidate_id)
        if (
            candidate is None
            or candidate.mapping_id != current.id
            or d.canonical_target_id != getattr(candidate, target_field)
        ):
            raise InvalidIdentityTransitionError("selected candidate does not belong to pending predecessor and target")
    if d.resolver_kind == "deterministic":
        if d.resolver_id != "exact-singleton" or d.rule_version != EXACT_SINGLETON_RULE_VERSION:
            raise InvalidIdentityTransitionError("unknown deterministic identity resolver rule")
        locked_item = IdentityReviewItem(
            entity_type=d.entity_type,
            mapping_id=current.id if current is not None else -1,
            adapter_key=d.adapter_key,
            source_key=d.source_key,
            source_id=d.source_id,
            candidates=await _ordered_candidates(
                session,
                candidate_model,
                target_field,
                current.id if current is not None else -1,
            ),
        )
        exact_candidate = _is_exact_singleton_candidate(locked_item)
        if (
            exact_candidate is None
            or exact_candidate.id != d.selected_candidate_id
            or exact_candidate.canonical_target_id != d.canonical_target_id
        ):
            raise InvalidIdentityTransitionError("exact singleton candidate changed before decision")
    transition_at = datetime.now(timezone.utc)
    if current is not None and current.valid_from >= transition_at:
        transition_at = current.valid_from + timedelta(microseconds=1)
    values = {
        "adapter_key": d.adapter_key,
        "source_key": d.source_key,
        "source_id": d.source_id,
        "state": d.state,
        "confidence": d.confidence,
        "resolver_kind": d.resolver_kind,
        "resolver_id": d.resolver_id,
        "rule_version": d.rule_version,
        "reason": d.reason,
        "decision_digest": d.digest(),
        "evidence_observation_id": d.evidence_observation_id,
        "predecessor_mapping_id": current_id,
        "selected_candidate_id": d.selected_candidate_id,
        "valid_from": transition_at,
        target_field: d.canonical_target_id,
    }
    created = model(**values)
    try:
        async with session.begin_nested():
            if current is not None:
                current.valid_to = transition_at
                current.closed_at = transition_at
                current.closed_by_decision_digest = d.digest()
            session.add(created)
            await session.flush()
    except IntegrityError:
        winner = await _current(session, model, d)
        if winner is None or winner.id == current_id:
            raise
        if winner.decision_digest == d.digest():
            return winner
        raise StaleIdentityDecisionError("concurrent decision won with different digest") from None
    return created


async def add_identity_candidate(session: AsyncSession, proposal: IdentityCandidateProposal):
    """Append a typed, redacted candidate to one open pending review mapping."""
    model, candidate_model, target_model, target_field = _MAPPING[proposal.entity_type]
    evidence_json = proposal.evidence_json()
    mapping = await session.get(model, proposal.mapping_id, with_for_update=True)
    if mapping is None or mapping.state != "pending_review" or mapping.valid_to is not None:
        raise InvalidIdentityTransitionError("candidate requires an open pending review mapping")
    if await session.get(target_model, proposal.canonical_target_id) is None:
        raise InvalidIdentityTransitionError("candidate canonical target does not exist")
    existing = await session.scalar(
        select(candidate_model).where(
            candidate_model.mapping_id == proposal.mapping_id,
            (getattr(candidate_model, target_field) == proposal.canonical_target_id)
            | (candidate_model.rank == proposal.rank),
        )
    )
    if existing is not None:
        if (
            getattr(existing, target_field) == proposal.canonical_target_id
            and existing.rank == proposal.rank
            and existing.confidence == proposal.confidence
            and existing.evidence == evidence_json
        ):
            return existing
        raise InvalidIdentityTransitionError("candidate rank or target is already used")
    values = {
        "mapping_id": proposal.mapping_id,
        target_field: proposal.canonical_target_id,
        "rank": proposal.rank,
        "confidence": proposal.confidence,
        "evidence": evidence_json,
    }
    created = candidate_model(**values)
    try:
        async with session.begin_nested():
            session.add(created)
            await session.flush()
    except IntegrityError:
        winner = await session.scalar(
            select(candidate_model).where(
                candidate_model.mapping_id == proposal.mapping_id,
                (getattr(candidate_model, target_field) == proposal.canonical_target_id)
                | (candidate_model.rank == proposal.rank),
            )
        )
        if (
            winner is not None
            and getattr(winner, target_field) == proposal.canonical_target_id
            and winner.rank == proposal.rank
            and winner.confidence == proposal.confidence
            and winner.evidence == evidence_json
        ):
            return winner
        if winner is None:
            raise
        raise InvalidIdentityTransitionError("concurrent candidate uses a different rank or target") from None
    return created


async def _ordered_candidates(
    session: AsyncSession,
    candidate_model: type,
    target_field: str,
    mapping_id: int,
) -> tuple[IdentityReviewCandidate, ...]:
    candidates = (
        (
            await session.execute(
                select(candidate_model)
                .where(candidate_model.mapping_id == mapping_id)
                .order_by(candidate_model.rank.asc(), candidate_model.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return tuple(
        IdentityReviewCandidate(
            id=candidate.id,
            canonical_target_id=getattr(candidate, target_field),
            rank=candidate.rank,
            confidence=candidate.confidence,
            evidence=candidate.evidence,
        )
        for candidate in sorted(candidates, key=lambda candidate: (candidate.rank, candidate.id))
    )


async def list_open_identity_reviews(
    session: AsyncSession,
    *,
    entity_type: MappingType | None = None,
    limit: int | None = None,
) -> list[IdentityReviewItem]:
    """Return current pending mappings in a stable, cross-entity order.

    This is the review-queue read API.  It deliberately reads only current
    rows, so historical/rejected mappings cannot re-enter review accidentally.
    Candidates are ordered by their persisted rank and ID for reproducible UI
    and resolver input.
    """
    if entity_type is not None and entity_type not in _MAPPING:
        raise InvalidIdentityTransitionError("unknown identity entity type")
    if limit is not None and (isinstance(limit, bool) or limit <= 0):
        raise InvalidIdentityTransitionError("review queue limit must be positive")

    kinds: tuple[MappingType, ...] = (entity_type,) if entity_type is not None else ("team", "competition", "match")
    items: list[IdentityReviewItem] = []
    for kind in kinds:
        model, candidate_model, _, target_field = _MAPPING[kind]
        mappings = (
            (
                await session.execute(
                    select(model)
                    .where(model.state == "pending_review", model.valid_to.is_(None))
                    .order_by(model.adapter_key.asc(), model.source_key.asc(), model.source_id.asc(), model.id.asc())
                )
            )
            .scalars()
            .all()
        )
        for mapping in mappings:
            items.append(
                IdentityReviewItem(
                    entity_type=kind,
                    mapping_id=mapping.id,
                    adapter_key=mapping.adapter_key,
                    source_key=mapping.source_key,
                    source_id=mapping.source_id,
                    candidates=await _ordered_candidates(session, candidate_model, target_field, mapping.id),
                )
            )
    items.sort(key=_review_item_sort_key)
    return items if limit is None else items[:limit]


async def auto_accept_exact_singletons(
    session: AsyncSession,
    *,
    rule_version: str,
    entity_type: MappingType | None = None,
    limit: int | None = None,
) -> list[IdentityReviewItem]:
    """Accept only v1 exact singleton candidates; leave every ambiguity pending.

    The returned items are the queue entries successfully resolved.  A stale
    entry is skipped because a concurrent human or resolver decision is the
    authoritative successor; it is never retried as a remap.
    """
    if rule_version != EXACT_SINGLETON_RULE_VERSION:
        raise InvalidIdentityTransitionError("automatic resolver requires its explicit exact-singleton/v1 rule version")

    accepted: list[IdentityReviewItem] = []
    for item in await list_open_identity_reviews(session, entity_type=entity_type, limit=limit):
        candidate = _is_exact_singleton_candidate(item)
        if candidate is None:
            continue
        try:
            await apply_identity_decision(
                session,
                IdentityDecision(
                    entity_type=item.entity_type,
                    adapter_key=item.adapter_key,
                    source_key=item.source_key,
                    source_id=item.source_id,
                    command_kind="decide",
                    state="accepted",
                    canonical_target_id=candidate.canonical_target_id,
                    expected_predecessor_mapping_id=item.mapping_id,
                    selected_candidate_id=candidate.id,
                    resolver_kind="deterministic",
                    resolver_id="exact-singleton",
                    rule_version=rule_version,
                    reason="exact singleton candidate",
                    confidence=candidate.confidence,
                ),
            )
        except StaleIdentityDecisionError:
            continue
        accepted.append(item)
    return accepted
