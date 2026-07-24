from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import Index, Numeric, UniqueConstraint
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
    assert "ix_model_monitoring_snapshots_user_version_scope" in {index.name for index in monitoring.indexes}


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


def _predicate(index: Index) -> str | None:
    predicate = index.dialect_options["postgresql"].get("where")
    if predicate is None:
        predicate = index.dialect_options["sqlite"].get("where")
    return " ".join(str(predicate).split()) if predicate is not None else None


def _index_inventory() -> dict[str, tuple[tuple[str, tuple[str, ...], bool, str | None], ...]]:
    inventory: dict[str, list[tuple[str, tuple[str, ...], bool, str | None]]] = {}
    for table in Base.metadata.tables.values():
        inventory[table.name] = sorted(
            (
                index.name,
                tuple(column.name for column in index.columns),
                index.unique,
                _predicate(index),
            )
            for index in table.indexes
        )
    return {table: tuple(indexes) for table, indexes in inventory.items()}


def _unique_inventory() -> dict[str, set[tuple[str | None, tuple[str, ...]]]]:
    return {
        table.name: {
            (constraint.name, tuple(constraint.columns.keys()))
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        for table in Base.metadata.tables.values()
    }


def _assert_inventory_contains(
    actual: dict[str, Iterable[tuple[str, tuple[str, ...], bool, str | None]]],
    expected: dict[str, tuple[tuple[str, tuple[str, ...], bool, str | None], ...]],
) -> None:
    for table, specs in expected.items():
        assert set(specs) <= set(actual[table]), table


def test_historical_migration_indexes_are_declared_in_orm_metadata() -> None:
    active_scrape = "scrape_job_id IS NOT NULL AND status IN ('queued', 'running')"
    expected = {
        # 001_initial
        "sessions": (
            ("ix_sessions_user_id", ("user_id",), False, None),
            ("ix_sessions_expires_at", ("expires_at",), False, None),
        ),
        "matches": (
            ("ix_matches_status", ("status",), False, None),
            ("ix_matches_match_date", ("match_date",), False, None),
            ("ix_matches_competition", ("competition",), False, None),
        ),
        "odds_entries": (
            ("ix_odds_entries_match_id", ("match_id",), False, None),
            ("ix_odds_entries_odds_snapshot_id", ("odds_snapshot_id",), False, None),
        ),
        "match_stats": (("ix_match_stats_match_id", ("match_id",), False, None),),
        "match_sources": (("ix_match_sources_match_id", ("match_id",), False, None),),
        "scrape_jobs": (
            ("ix_scrape_jobs_status", ("status",), False, None),
            ("ix_scrape_jobs_status_created", ("status", "created_at"), False, None),
        ),
        "scraped_datasets": (("ix_scraped_datasets_source", ("source",), False, None),),
        "prediction_runs": (
            ("ix_prediction_runs_user_id", ("user_id",), False, None),
            ("ix_prediction_runs_user_status_created", ("user_id", "status", "created_at"), False, None),
            ("ix_prediction_runs_model_version_id", ("model_version_id",), False, None),
            ("ix_prediction_runs_training_fingerprint", ("training_data_fingerprint",), False, None),
        ),
        "bankrolls": (("ix_bankrolls_user_id", ("user_id",), False, None),),
        "scheduled_jobs": (
            ("ix_scheduled_jobs_enabled", ("enabled",), False, None),
            ("ix_scheduled_jobs_enabled_next_run", ("enabled", "next_run"), False, None),
        ),
        "bookmaker_accounts": (("ix_bookmaker_accounts_bankroll_id", ("bankroll_id",), False, None),),
        "tickets": (
            ("ix_tickets_user_id", ("user_id",), False, None),
            ("ix_tickets_bankroll_id", ("bankroll_id",), False, None),
            ("ix_tickets_batch_id", ("batch_id",), False, None),
            ("ix_tickets_user_status_created", ("user_id", "status", "created_at"), False, None),
        ),
        "ticket_legs": (
            ("ix_ticket_legs_ticket_id", ("ticket_id",), False, None),
            ("ix_ticket_legs_ticket_status", ("ticket_id", "status"), False, None),
            ("ix_ticket_legs_model_prediction_id", ("model_prediction_id",), False, None),
        ),
        "bet_placements": (("ix_bet_placements_ticket_id", ("ticket_id",), False, None),),
        "ledger_entries": (("ix_ledger_entries_bankroll_id", ("bankroll_id",), False, None),),
        "model_predictions": (
            ("ix_model_predictions_run_id", ("run_id",), False, None),
            ("ix_model_predictions_match_id", ("match_id",), False, None),
            ("ix_model_predictions_run_market", ("run_id", "market"), False, None),
            ("ix_model_predictions_match_market", ("match_id", "market"), False, None),
            ("ix_model_predictions_model_version_id", ("model_version_id",), False, None),
            ("ix_model_predictions_odds_snapshot_id", ("odds_snapshot_id",), False, None),
        ),
        "execution_intents": (
            ("ix_execution_intents_odds_snapshot_id", ("odds_snapshot_id",), False, None),
            ("ix_execution_intents_model_evaluation_id", ("model_evaluation_id",), False, None),
        ),
        "ensemble_predictions": (
            ("ix_ensemble_predictions_run_id", ("run_id",), False, None),
            ("ix_ensemble_predictions_match_id", ("match_id",), False, None),
        ),
        "predictions": (("ix_predictions_session_id", ("session_id",), False, None),),
        # 006_add_scheduled_job_runs
        "scheduled_job_runs": (
            ("ix_scheduled_job_runs_scheduled_job_id", ("scheduled_job_id",), False, None),
            ("ix_scheduled_job_runs_scrape_job_id", ("scrape_job_id",), False, None),
            ("ix_scheduled_job_runs_status", ("status",), False, None),
            ("uq_scheduled_job_runs_active_scrape_task", ("task_type", "scrape_job_id"), True, active_scrape),
            ("ix_scheduled_job_runs_job_created", ("scheduled_job_id", "created_at"), False, None),
            ("uq_scheduled_job_runs_idempotency_key", ("idempotency_key",), True, None),
            ("ix_scheduled_job_runs_model_evaluation_id", ("model_evaluation_id",), False, None),
        ),
        "scrape_job_logs": (
            ("ix_scrape_job_logs_job_id", ("job_id",), False, None),
            ("ix_scrape_job_logs_job_created", ("job_id", "created_at"), False, None),
        ),
        # 008_add_football_league_catalog
        "football_league_catalog": (
            ("ix_football_league_catalog_scrape_slug", ("scrape_slug",), False, None),
            ("ix_football_league_catalog_country_slug", ("country_slug",), False, None),
            ("ix_football_league_catalog_status", ("status",), False, None),
        ),
        # 009_add_async_task_delivery
        "task_outbox": (
            ("ix_task_outbox_run_id", ("run_id",), False, None),
            ("ix_task_outbox_status", ("status",), False, None),
            ("ix_task_outbox_pending", ("status", "available_at"), False, None),
        ),
        # 017_add_odds_quote_lineage
        "odds_snapshots": (
            ("ix_odds_snapshots_match_observed", ("match_id", "observed_at"), False, None),
            ("ix_odds_snapshots_dataset_id", ("dataset_id",), False, None),
            ("ix_odds_snapshots_scrape_job_id", ("scrape_job_id",), False, None),
        ),
        "ticket_leg_quote_snapshots": (
            ("ix_ticket_leg_quote_snapshots_ticket_leg_id", ("ticket_leg_id",), False, None),
            ("ix_ticket_leg_quote_snapshots_odds_snapshot_id", ("odds_snapshot_id",), False, None),
            ("ix_ticket_leg_quote_snapshots_recorded_at", ("recorded_at",), False, None),
        ),
        # 019_add_model_governance and 020_add_monitoring_snapshot_ownership
        "model_versions": (
            ("ix_model_versions_model_key_status", ("model_key", "status"), False, None),
            ("ix_model_versions_training_fingerprint", ("training_data_fingerprint",), False, None),
        ),
        "model_evaluations": (
            ("ix_model_evaluations_version_scope", ("model_version_id", "scope_key", "created_at"), False, None),
            ("ix_model_evaluations_status", ("status",), False, None),
        ),
        "model_evaluation_folds": (("ix_model_evaluation_folds_evaluation_id", ("evaluation_id",), False, None),),
        "model_evaluation_predictions": (
            ("ix_model_evaluation_predictions_fold_id", ("fold_id",), False, None),
            ("ix_model_evaluation_predictions_match_market", ("match_id", "market"), False, None),
        ),
        "prediction_outcomes": (
            ("ix_prediction_outcomes_model_version_id", ("model_version_id",), False, None),
            ("ix_prediction_outcomes_resolved_at", ("resolved_at",), False, None),
        ),
        "model_certifications": (
            ("ix_model_certifications_version_scope_status", ("model_version_id", "scope_key", "status"), False, None),
            ("ix_model_certifications_valid_until", ("valid_until",), False, None),
        ),
        "model_monitoring_snapshots": (
            (
                "ix_model_monitoring_snapshots_version_scope",
                ("model_version_id", "scope_key", "window_ended_at"),
                False,
                None,
            ),
            ("ix_model_monitoring_snapshots_severity", ("severity",), False, None),
            (
                "ix_model_monitoring_snapshots_user_version_scope",
                ("user_id", "model_version_id", "scope_key", "window_ended_at"),
                False,
                None,
            ),
        ),
    }

    _assert_inventory_contains(_index_inventory(), expected)


def test_historical_migration_unique_constraints_are_declared_in_orm_metadata() -> None:
    expected = {
        "users": {(None, ("email",))},
        "sessions": {(None, ("session_id",))},
        "football_league_catalog": {(None, ("scrape_slug",))},
        "task_outbox": {("uq_task_outbox_run_id", ("run_id",))},
        "odds_snapshots": {("uq_odds_snapshots_source_key", ("source", "source_key"))},
        "ticket_leg_quote_snapshots": {
            ("uq_ticket_leg_quote_snapshots_leg_stage_revision", ("ticket_leg_id", "stage", "revision"))
        },
        "model_versions": {
            (
                "uq_model_versions_identity",
                ("model_key", "version", "strategy_config_hash", "training_data_fingerprint"),
            )
        },
        "model_evaluation_folds": {("uq_model_evaluation_folds_number", ("evaluation_id", "fold_number"))},
        "model_evaluation_predictions": {
            ("uq_model_evaluation_predictions_target", ("fold_id", "match_id", "market", "selection"))
        },
        "prediction_outcomes": {("uq_prediction_outcomes_model_prediction_id", ("model_prediction_id",))},
        "model_monitoring_snapshots": {
            (
                "uq_model_monitoring_snapshots_tenant_window",
                ("user_id", "model_version_id", "scope_key", "window_ended_at"),
            )
        },
    }
    actual = _unique_inventory()
    for table, constraints in expected.items():
        assert constraints <= actual[table], table
