from decimal import Decimal

from sqlalchemy import Numeric
from sqlalchemy.orm import configure_mappers

from app.models import Base


def _foreign_key_target(table_name: str, column_name: str) -> str:
    column = Base.metadata.tables[table_name].c[column_name]
    return next(iter(column.foreign_keys)).target_fullname


def test_revision_018_money_columns_use_fixed_precision_decimals() -> None:
    expected = {
        "bankrolls": ("balance", "initial_balance"),
        "bookmaker_accounts": ("balance",),
        "ticket_batches": ("total_stake",),
        "tickets": ("stake", "potential_return"),
        "settlements": ("return_amount", "pnl"),
        "ledger_entries": ("amount", "balance_after"),
    }

    for table_name, column_names in expected.items():
        table = Base.metadata.tables[table_name]
        for column_name in column_names:
            column_type = table.c[column_name].type
            assert isinstance(column_type, Numeric), f"{table_name}.{column_name} must use Numeric"
            assert (column_type.precision, column_type.scale) == (14, 2)
            assert column_type.python_type is Decimal


def test_revisions_017_to_019_nullable_lineage_columns_match_foreign_keys() -> None:
    expected = {
        ("odds_entries", "odds_snapshot_id"): "odds_snapshots.id",
        ("model_predictions", "odds_snapshot_id"): "odds_snapshots.id",
        ("execution_intents", "odds_snapshot_id"): "odds_snapshots.id",
        ("tickets", "risk_policy_id"): "bankroll_risk_policies.id",
        ("ticket_batches", "risk_policy_id"): "bankroll_risk_policies.id",
        ("prediction_runs", "model_version_id"): "model_versions.id",
        ("model_predictions", "model_version_id"): "model_versions.id",
        ("ticket_batches", "model_evaluation_id"): "model_evaluations.id",
        ("execution_intents", "model_evaluation_id"): "model_evaluations.id",
        ("scheduled_job_runs", "model_evaluation_id"): "model_evaluations.id",
    }

    for (table_name, column_name), target in expected.items():
        column = Base.metadata.tables[table_name].c[column_name]
        assert column.nullable is True
        assert _foreign_key_target(table_name, column_name) == target


def test_revision_018_ticket_audit_columns_and_indexes_are_exposed_by_orm() -> None:
    ticket_batch = Base.metadata.tables["ticket_batches"]
    ticket = Base.metadata.tables["tickets"]

    assert {
        "revision",
        "risk_policy_version",
        "risk_assessment",
        "staking_snapshot",
        "activation_report",
        "updated_at",
    } <= set(ticket_batch.c.keys())
    assert {"risk_policy_version", "risk_assessment", "staking_snapshot"} <= set(ticket.c.keys())

    index_names = {index.name for index in ticket_batch.indexes} | {index.name for index in ticket.indexes}
    assert {
        "ix_ticket_batches_risk_policy_id",
        "ix_ticket_batches_bankroll_revision",
        "ix_ticket_batches_model_evaluation_id",
        "ix_tickets_risk_policy_id",
        "ix_tickets_open_exposure",
    } <= index_names


def test_revision_020_monitoring_snapshots_have_explicit_tenant_ownership() -> None:
    monitoring = Base.metadata.tables["model_monitoring_snapshots"]

    assert monitoring.c.user_id.nullable is True
    assert _foreign_key_target("model_monitoring_snapshots", "user_id") == "users.id"
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in monitoring.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("user_id", "model_version_id", "scope_key", "window_ended_at") in unique_columns
    assert "ix_model_monitoring_snapshots_user_version_scope" in {
        index.name for index in monitoring.indexes
    }


def test_new_lineage_relationships_can_be_configured_together() -> None:
    configure_mappers()

    expected = {
        "Bankroll": {"risk_policies", "risk_state"},
        "OddsEntry": {"odds_snapshot", "quote_snapshots"},
        "PredictionRun": {"model_version"},
        "ModelPrediction": {"model_version", "odds_snapshot", "outcome"},
        "Ticket": {"risk_policy"},
        "TicketBatch": {"risk_policy", "model_evaluation"},
        "TicketLeg": {"quote_snapshots"},
        "ExecutionIntent": {"odds_snapshot", "model_evaluation"},
        "ScheduledJobRun": {"model_evaluation"},
    }
    for mapper in Base.registry.mappers:
        class_name = mapper.class_.__name__
        if class_name in expected:
            assert expected[class_name] <= set(mapper.relationships.keys())
