from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1 import strategies as strategies_api
from app.models.prediction import PredictionRun


def _run(*, status: str, dedupe_enabled: bool, user_id: int = 7, input_hash: str = "same-input"):
    return PredictionRun(
        user_id=user_id,
        name="Strategy: Poisson | input:same-input",
        model_type="poisson",
        status=status,
        matches_count=1,
        input_hash=input_hash,
        dedupe_enabled=dedupe_enabled,
    )


def test_active_dedupe_index_blocks_duplicates_but_releases_partial_and_failed_runs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis-dedupe.db'}")
    try:
        PredictionRun.__table__.create(engine)

        with Session(engine, expire_on_commit=False) as db:
            first = _run(status="running", dedupe_enabled=True)
            db.add(first)
            db.commit()

        with Session(engine) as db:
            db.add(_run(status="running", dedupe_enabled=True))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        with Session(engine) as db:
            first = db.get(PredictionRun, first.id)
            first.status = "partial"
            db.commit()

        with Session(engine, expire_on_commit=False) as db:
            retry = _run(status="running", dedupe_enabled=True)
            db.add(retry)
            db.commit()

            active = db.scalar(
                select(PredictionRun).where(
                    PredictionRun.user_id == 7,
                    PredictionRun.input_hash == "same-input",
                    PredictionRun.status.in_(strategies_api.ACTIVE_DEDUPE_RUN_STATUSES),
                )
            )
            assert active.id == retry.id

            retry.status = "failed"
            db.commit()

        with Session(engine) as db:
            final_retry = _run(status="completed", dedupe_enabled=True)
            db.add(final_retry)
            db.commit()

        with Session(engine) as db:
            db.add(_run(status="running", dedupe_enabled=True))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    finally:
        engine.dispose()


def test_runs_without_avoid_reprediction_do_not_claim_the_dedupe_guard(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis-no-dedupe.db'}")
    try:
        PredictionRun.__table__.create(engine)

        with Session(engine) as db:
            db.add_all(
                [
                    _run(status="running", dedupe_enabled=False),
                    _run(status="running", dedupe_enabled=False),
                ]
            )
            db.commit()
    finally:
        engine.dispose()


class _NestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


class _ConflictSession:
    def __init__(self, winner):
        self.winner = winner
        self.added = []

    def begin_nested(self):
        return _NestedTransaction()

    def add(self, run):
        self.added.append(run)

    async def flush(self):
        raise IntegrityError("INSERT INTO prediction_runs", {}, RuntimeError("unique conflict"))

    async def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.winner)


@pytest.mark.asyncio
async def test_dedupe_claim_returns_concurrent_winner_after_unique_conflict():
    winner = _run(status="running", dedupe_enabled=True)
    winner.id = 91
    loser = _run(status="running", dedupe_enabled=True)
    db = _ConflictSession(winner)

    claimed_by = await strategies_api._claim_deduplicated_strategy_run(db, run=loser)

    assert db.added == [loser]
    assert claimed_by is winner
