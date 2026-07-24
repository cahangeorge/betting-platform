import pytest

from app.services.e2e_cleanup import (
    CONFIRMATION_PHRASE,
    CleanupGuardError,
    CleanupPlan,
    e2e_named_namespace,
    e2e_user_namespace,
    render_plan,
    require_apply_confirmation,
    validate_plan_for_apply,
)

NAMESPACE = "1752481234567-a1b2c3d4"


def test_user_match_requires_exact_generated_email_namespace():
    assert e2e_user_namespace(f"e2e-{NAMESPACE}@example.com", f"E2E {NAMESPACE}") == NAMESPACE

    assert e2e_user_namespace(f"e2e-{NAMESPACE}@example.com", "legacy fixture name") == NAMESPACE
    assert e2e_user_namespace("e2e-admin@example.com", "E2E admin") is None
    assert e2e_user_namespace(f"e2e-{NAMESPACE}@company.com", f"E2E {NAMESPACE}") is None
    assert e2e_user_namespace(f"prefix-e2e-{NAMESPACE}@example.com", f"E2E {NAMESPACE}") is None


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("strategy", f"E2E Strategy {NAMESPACE}"),
        ("strategy", f"E2E Lineage {NAMESPACE}"),
        ("dataset", f"E2E Analysis Dataset {NAMESPACE}"),
        ("dataset", f"E2E Ticket Lifecycle {NAMESPACE}"),
        ("competition", f"E2E {NAMESPACE}"),
        ("competition", f"E2E Ticket Lifecycle {NAMESPACE}"),
        ("scheduled_job", f"E2E orchestration {NAMESPACE}"),
        ("scheduled_job", f"E2E verification {NAMESPACE}"),
        ("prediction_run", f"E2E selected one {NAMESPACE}"),
        ("prediction_run", f"Strategy: E2E Lineage {NAMESPACE} | input:0123456789abcdef01234567"),
        ("scrape_job", f"e2e-analysis-{NAMESPACE}"),
    ],
)
def test_named_fixture_matchers_accept_only_known_exact_shapes(kind, value):
    assert e2e_named_namespace(kind, value) == NAMESPACE


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("strategy", "E2E Production strategy"),
        ("strategy", f"My E2E Strategy {NAMESPACE}"),
        ("dataset", f"E2E Analysis Dataset {NAMESPACE} backup"),
        ("competition", "E2E Argentina"),
        ("scheduled_job", f"E2E arbitrary {NAMESPACE}"),
        ("prediction_run", f"Strategy: Real Strategy {NAMESPACE}"),
        ("scrape_job", f"import-{NAMESPACE}"),
    ],
)
def test_named_fixture_matchers_reject_broad_or_product_like_names(kind, value):
    assert e2e_named_namespace(kind, value) is None


def test_apply_requires_both_flag_and_exact_confirmation():
    require_apply_confirmation(apply=False, confirmation=None)
    require_apply_confirmation(apply=False, confirmation="wrong")
    require_apply_confirmation(apply=True, confirmation=CONFIRMATION_PHRASE)

    with pytest.raises(CleanupGuardError, match="Apply requires"):
        require_apply_confirmation(apply=True, confirmation=None)
    with pytest.raises(CleanupGuardError, match="Apply requires"):
        require_apply_confirmation(apply=True, confirmation="delete everything")


def test_apply_plan_refuses_blockers_invalid_namespaces_and_user_limit():
    with pytest.raises(CleanupGuardError, match="blockers"):
        validate_plan_for_apply(CleanupPlan(blockers=["shared strategy"]))

    with pytest.raises(CleanupGuardError, match="invalid namespaces"):
        validate_plan_for_apply(CleanupPlan(namespaces={"production"}))

    plan = CleanupPlan(namespaces={NAMESPACE}, ids={"users": list(range(1, 502))})
    with pytest.raises(CleanupGuardError, match="safety limit"):
        validate_plan_for_apply(plan)


def test_dry_run_report_is_explicit_and_includes_dependency_counts():
    plan = CleanupPlan(namespaces={NAMESPACE})
    plan.add_ids("users", [3, 2, 3])
    plan.add_ids("tickets", [10, 11])

    report = render_plan(plan, applied=False)

    assert "DRY-RUN" in report
    assert "users: 2" in report
    assert "tickets: 2" in report
    assert "No rows changed" in report
    assert CONFIRMATION_PHRASE in report
