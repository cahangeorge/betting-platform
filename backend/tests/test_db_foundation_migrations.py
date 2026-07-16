from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Numeric, create_engine, insert, select
from sqlalchemy.exc import IntegrityError

from app.models import Base
from app.models.odds_lineage import TicketLegQuoteSnapshot
from app.models.risk import BankrollRiskPolicy, BankrollRiskState


def test_foundation_revisions_form_one_linear_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["021"]
    assert script.get_revision("021").down_revision == "020"
    assert script.get_revision("020").down_revision == "019"
    assert script.get_revision("019").down_revision == "018"
    assert script.get_revision("018").down_revision == "017"
    assert script.get_revision("017").down_revision == "016"


def test_foundation_models_create_on_clean_sqlite_schema() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    expected = {
        "odds_snapshots",
        "ticket_leg_quote_snapshots",
        "bankroll_risk_policies",
        "bankroll_risk_states",
        "model_versions",
        "model_evaluations",
        "model_evaluation_folds",
        "model_evaluation_predictions",
        "prediction_outcomes",
        "model_certifications",
        "model_monitoring_snapshots",
    }
    assert expected <= set(Base.metadata.tables)


def test_risk_policy_is_explicit_and_hard_caps_are_database_enforced() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    policy = BankrollRiskPolicy.__table__

    with engine.begin() as connection:
        assert connection.scalar(select(policy.c.id).limit(1)) is None
        connection.execute(
            insert(policy).values(
                bankroll_id=101,
                version=1,
                staking_mode="flat_percent",
                flat_stake_pct=Decimal("0.010000"),
                kelly_fraction=None,
                max_ticket_pct=Decimal("0.050000"),
                max_open_exposure_pct=Decimal("0.200000"),
                league_window_hours=6,
                accumulators_enabled=False,
                automation_enabled=False,
                effective_from=datetime(2026, 7, 16, tzinfo=UTC),
            )
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                insert(policy).values(
                    bankroll_id=102,
                    version=1,
                    staking_mode="flat_percent",
                    flat_stake_pct=Decimal("0.060000"),
                    kelly_fraction=None,
                    max_ticket_pct=Decimal("0.060000"),
                    max_open_exposure_pct=Decimal("0.200000"),
                    league_window_hours=6,
                    accumulators_enabled=False,
                    automation_enabled=False,
                    effective_from=datetime(2026, 7, 16, tzinfo=UTC),
                )
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                insert(policy).values(
                    bankroll_id=103,
                    version=1,
                    staking_mode="fractional_kelly",
                    flat_stake_pct=None,
                    kelly_fraction=Decimal("0.500000"),
                    max_ticket_pct=Decimal("0.050000"),
                    max_open_exposure_pct=Decimal("0.210000"),
                    league_window_hours=6,
                    accumulators_enabled=False,
                    automation_enabled=False,
                    effective_from=datetime(2026, 7, 16, tzinfo=UTC),
                )
            )


def test_risk_state_supports_pending_policy_without_replacing_active_policy() -> None:
    columns = BankrollRiskState.__table__.c
    assert columns.pending_policy.nullable is True
    assert columns.pending_effective_at.nullable is True


def test_quote_snapshot_uses_decimal_prices_and_revisioned_append_only_stages() -> None:
    table = TicketLegQuoteSnapshot.__table__
    assert isinstance(table.c.price.type, Numeric)
    assert (table.c.price.type.precision, table.c.price.type.scale) == (12, 4)
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("ticket_leg_id", "stage", "revision") in unique_columns
    assert ("ticket_leg_id", "stage") not in unique_columns
    assert table.c.revision.nullable is False
    assert table.c.revision.default.arg == 1
    assert {
        "ix_ticket_leg_quote_snapshots_ticket_leg_id",
        "ix_ticket_leg_quote_snapshots_odds_snapshot_id",
    } <= {index.name for index in table.indexes}
    assert "ix_ticket_leg_quote_snapshots_leg_stage_revision" not in {
        index.name for index in table.indexes
    }
