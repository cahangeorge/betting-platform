from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import data as data_api
from app.models.match import Match
from app.schemas.data import MatchResultCorrectionRequest


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _CorrectionDb:
    def __init__(self, match, settled_ticket_id=None):
        self.match = match
        self.settled_ticket_id = settled_ticket_id
        self.added = []
        self.flushes = 0

    async def get(self, model, match_id):
        assert model is Match
        return self.match if self.match and match_id == self.match.id else None

    async def execute(self, _stmt):
        return _ScalarResult(self.settled_ticket_id)

    def add(self, value):
        value.id = len(self.added) + 1
        value.created_at = datetime.now(timezone.utc)
        self.added.append(value)

    async def flush(self):
        self.flushes += 1


def _match():
    return SimpleNamespace(id=44, home_score=2, away_score=1, status="finished")


def test_result_correction_requires_non_blank_source_and_reason():
    with pytest.raises(ValidationError):
        MatchResultCorrectionRequest(home_score=1, away_score=0, source="  ", reason="source correction")
    with pytest.raises(ValidationError):
        MatchResultCorrectionRequest(home_score=1, away_score=0, source="provider", reason=" ")


@pytest.mark.asyncio
async def test_result_correction_rejects_non_admin_before_accessing_match():
    body = MatchResultCorrectionRequest(home_score=3, away_score=1, source="provider", reason="official correction")

    with pytest.raises(HTTPException) as exc_info:
        await data_api.correct_match_result(
            match_id=44,
            body=body,
            db=object(),
            user=SimpleNamespace(id=12, is_admin=False),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin access required for match result corrections"


@pytest.mark.asyncio
async def test_result_correction_rejects_matches_linked_to_settled_tickets():
    match = _match()
    db = _CorrectionDb(match, settled_ticket_id=901)
    body = MatchResultCorrectionRequest(home_score=3, away_score=1, source="provider", reason="official correction")

    with pytest.raises(HTTPException) as exc_info:
        await data_api.correct_match_result(
            match_id=44,
            body=body,
            db=db,
            user=SimpleNamespace(id=7, is_admin=True),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Cannot correct match result: linked ticket 901 is already settled"
    assert (match.home_score, match.away_score, match.status) == (2, 1, "finished")
    assert db.added == []
    assert db.flushes == 0


@pytest.mark.asyncio
async def test_admin_result_correction_records_audit_without_settlement_side_effects():
    match = _match()
    db = _CorrectionDb(match)
    body = MatchResultCorrectionRequest(
        home_score=3,
        away_score=1,
        source="official provider",
        reason="Provider corrected the final score after review",
    )

    correction = await data_api.correct_match_result(
        match_id=44,
        body=body,
        db=db,
        user=SimpleNamespace(id=7, is_admin=True),
    )

    assert (match.home_score, match.away_score, match.status) == (3, 1, "finished")
    assert correction.match_id == 44
    assert correction.corrected_by_user_id == 7
    assert correction.source == "official provider"
    assert correction.reason == "Provider corrected the final score after review"
    assert (
        correction.previous_home_score,
        correction.previous_away_score,
        correction.previous_status,
    ) == (2, 1, "finished")
    assert (
        correction.corrected_home_score,
        correction.corrected_away_score,
        correction.corrected_status,
    ) == (3, 1, "finished")
    assert db.flushes == 1
