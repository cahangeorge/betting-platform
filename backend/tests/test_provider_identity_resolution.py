from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.provider_identity import (
    EXACT_SINGLETON_RULE_VERSION,
    IdentityCandidateProposal,
    IdentityDecision,
    InvalidIdentityTransitionError,
    StaleIdentityDecisionError,
    auto_accept_exact_singletons,
    list_open_identity_reviews,
    validate_decision_shape,
)


class _ScalarResult:
    def __init__(self, values: list[Any]):
        self._values = values

    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> list[Any]:
        return self._values


class _ReviewQueueSession:
    """Minimal query-result double keyed by the model selected by the service."""

    def __init__(self, rows: dict[type, list[Any]]):
        self.rows = rows

    async def execute(self, statement: Any) -> _ScalarResult:
        entity = statement.column_descriptions[0]["entity"]
        return _ScalarResult(self.rows.get(entity, []))

    async def get(self, entity: type, ident: int, **_: Any) -> Any | None:
        return next((row for row in self.rows.get(entity, []) if row.id == ident), None)


def decision(**changes: Any) -> IdentityDecision:
    data: dict[str, Any] = dict(
        entity_type="team",
        adapter_key="soccerdata",
        source_key="fbref",
        source_id="x",
        command_kind="propose",
        state="pending_review",
        canonical_target_id=None,
        expected_predecessor_mapping_id=None,
        confidence=Decimal("0.5000"),
    )
    data.update(changes)
    return IdentityDecision(**data)


def test_digest_is_deterministic_and_normalizes_reason():
    assert decision(reason=" a   reason ").digest() == decision(reason="a reason").digest()
    assert decision(confidence=Decimal("0.5")).digest() == decision(confidence=Decimal("0.5000")).digest()
    assert decision(command_kind="propose").digest() == decision(command_kind="reopen").digest()
    assert decision().digest() != decision(source_id="y").digest()


def test_decision_is_immutable_and_explicit_predecessor_required():
    first = decision()
    assert first.expected_predecessor_mapping_id is None
    with pytest.raises(AttributeError):
        first.source_id = "mutate"  # type: ignore[misc]


def test_state_contract_is_expressed_by_command_data():
    accepted = decision(
        command_kind="decide", state="accepted", canonical_target_id=7, expected_predecessor_mapping_id=2
    )
    assert accepted.state == "accepted"
    assert accepted.canonical_target_id == 7
    assert StaleIdentityDecisionError("stale")
    assert InvalidIdentityTransitionError("invalid")


def test_transition_matrix_and_confidence_are_fail_closed():
    validate_decision_shape(decision(), None)
    validate_decision_shape(
        decision(command_kind="decide", state="accepted", canonical_target_id=3, expected_predecessor_mapping_id=1),
        "pending_review",
    )
    with pytest.raises(InvalidIdentityTransitionError):
        validate_decision_shape(decision(command_kind="decide", state="accepted", canonical_target_id=3), None)
    with pytest.raises(InvalidIdentityTransitionError):
        validate_decision_shape(decision(confidence=Decimal("1.0001")), None)


def test_remap_is_explicit_successor_only():
    # A new accepted decision can only follow an accepted row with the exact
    # predecessor supplied by the caller; stale checking happens before this.
    validate_decision_shape(
        decision(command_kind="remap", state="accepted", canonical_target_id=4, expected_predecessor_mapping_id=9),
        "accepted",
    )
    with pytest.raises(InvalidIdentityTransitionError):
        validate_decision_shape(
            decision(command_kind="remap", state="pending_review", expected_predecessor_mapping_id=9), "accepted"
        )


def test_command_kind_prevents_stale_accept_becoming_remap():
    with pytest.raises(InvalidIdentityTransitionError):
        validate_decision_shape(
            decision(command_kind="decide", state="accepted", canonical_target_id=4, expected_predecessor_mapping_id=9),
            "accepted",
        )


def test_candidate_proposal_is_ranked_canonical_and_secret_safe():
    proposal = IdentityCandidateProposal(
        entity_type="team",
        mapping_id=1,
        canonical_target_id=2,
        rank=1,
        confidence=Decimal("0.7500"),
        evidence={"rule": "normalized-name", "signals": ["country", "league"]},
    )
    assert proposal.evidence_json() == '{"rule":"normalized-name","signals":["country","league"]}'

    with pytest.raises(InvalidIdentityTransitionError, match="sensitive"):
        IdentityCandidateProposal(
            entity_type="team",
            mapping_id=1,
            canonical_target_id=2,
            rank=1,
            confidence=Decimal("0.7500"),
            evidence={"api_token": "never-store"},
        ).evidence_json()


@pytest.mark.asyncio
async def test_review_queue_is_deterministic_across_entity_types_and_candidates():
    from app.models.provider_identity import (
        CompetitionProviderMapping,
        CompetitionProviderMappingCandidate,
        MatchProviderMapping,
        MatchProviderMappingCandidate,
        TeamProviderMapping,
        TeamProviderMappingCandidate,
    )

    session = _ReviewQueueSession(
        {
            TeamProviderMapping: [
                SimpleNamespace(id=8, adapter_key="zeta", source_key="a", source_id="one"),
            ],
            CompetitionProviderMapping: [
                SimpleNamespace(id=7, adapter_key="alpha", source_key="b", source_id="two"),
            ],
            MatchProviderMapping: [],
            TeamProviderMappingCandidate: [
                SimpleNamespace(id=12, team_id=5, rank=2, confidence=Decimal("0.5"), evidence="{}"),
                SimpleNamespace(id=11, team_id=4, rank=1, confidence=Decimal("0.9"), evidence="{}"),
            ],
            CompetitionProviderMappingCandidate: [
                SimpleNamespace(id=13, competition_id=6, rank=1, confidence=Decimal("1"), evidence="{}"),
            ],
            MatchProviderMappingCandidate: [],
        }
    )

    items = await list_open_identity_reviews(session)  # type: ignore[arg-type]

    assert [(item.entity_type, item.mapping_id) for item in items] == [("competition", 7), ("team", 8)]
    assert [candidate.id for candidate in items[1].candidates] == [11, 12]


@pytest.mark.asyncio
async def test_exact_singleton_auto_accepts_with_explicit_audit_shape(monkeypatch: pytest.MonkeyPatch):
    from app.models.provider_identity import (
        CompetitionProviderMapping,
        CompetitionProviderMappingCandidate,
        MatchProviderMapping,
        MatchProviderMappingCandidate,
        TeamProviderMapping,
        TeamProviderMappingCandidate,
    )

    session = _ReviewQueueSession(
        {
            TeamProviderMapping: [
                SimpleNamespace(
                    id=8,
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id="club-8",
                    state="pending_review",
                    valid_to=None,
                ),
            ],
            CompetitionProviderMapping: [],
            MatchProviderMapping: [],
            TeamProviderMappingCandidate: [
                SimpleNamespace(id=11, team_id=4, rank=1, confidence=Decimal("1"), evidence='{"rule":"exact"}'),
            ],
            CompetitionProviderMappingCandidate: [],
            MatchProviderMappingCandidate: [],
        }
    )
    decisions: list[IdentityDecision] = []

    async def record_decision(_: Any, command: IdentityDecision) -> object:
        decisions.append(command)
        return object()

    monkeypatch.setattr("app.services.provider_identity.apply_identity_decision", record_decision)

    resolved = await auto_accept_exact_singletons(
        session,  # type: ignore[arg-type]
        rule_version=EXACT_SINGLETON_RULE_VERSION,
    )

    assert [item.mapping_id for item in resolved] == [8]
    assert decisions == [
        IdentityDecision(
            entity_type="team",
            adapter_key="soccerdata",
            source_key="fbref",
            source_id="club-8",
            command_kind="decide",
            state="accepted",
            canonical_target_id=4,
            expected_predecessor_mapping_id=8,
            selected_candidate_id=11,
            resolver_kind="deterministic",
            resolver_id="exact-singleton",
            rule_version=EXACT_SINGLETON_RULE_VERSION,
            reason="exact singleton candidate",
            confidence=Decimal("1"),
        )
    ]


@pytest.mark.asyncio
async def test_ambiguous_candidates_stay_pending_and_rule_version_is_not_inferred(monkeypatch: pytest.MonkeyPatch):
    from app.models.provider_identity import (
        CompetitionProviderMapping,
        CompetitionProviderMappingCandidate,
        MatchProviderMapping,
        MatchProviderMappingCandidate,
        TeamProviderMapping,
        TeamProviderMappingCandidate,
    )

    session = _ReviewQueueSession(
        {
            TeamProviderMapping: [
                SimpleNamespace(
                    id=8,
                    adapter_key="soccerdata",
                    source_key="fbref",
                    source_id="club-8",
                    state="pending_review",
                    valid_to=None,
                ),
            ],
            CompetitionProviderMapping: [],
            MatchProviderMapping: [],
            TeamProviderMappingCandidate: [
                SimpleNamespace(id=11, team_id=4, rank=1, confidence=Decimal("1"), evidence="{}"),
                SimpleNamespace(id=12, team_id=5, rank=2, confidence=Decimal("0.1"), evidence="{}"),
            ],
            CompetitionProviderMappingCandidate: [],
            MatchProviderMappingCandidate: [],
        }
    )
    called = False

    async def record_decision(*_: Any) -> object:
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr("app.services.provider_identity.apply_identity_decision", record_decision)

    assert (
        await auto_accept_exact_singletons(
            session,  # type: ignore[arg-type]
            rule_version=EXACT_SINGLETON_RULE_VERSION,
        )
        == []
    )
    assert not called
    with pytest.raises(InvalidIdentityTransitionError, match="explicit"):
        await auto_accept_exact_singletons(session, rule_version="exact-singleton/v2")  # type: ignore[arg-type]
