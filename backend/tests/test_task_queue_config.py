import pytest
from pydantic import ValidationError

from app.config import Settings


def test_inline_backend_is_a_deprecated_inprocess_alias():
    with pytest.warns(DeprecationWarning, match="inline is deprecated"):
        settings = Settings(_env_file=None, task_queue_backend="inline")

    assert settings.task_queue_backend == "inprocess"


def test_invalid_task_backend_is_rejected_during_settings_validation():
    with pytest.raises(ValidationError, match="task_queue_backend"):
        Settings(_env_file=None, task_queue_backend="celery")


def test_worker_lane_defaults_are_distinct_and_bounded():
    settings = Settings(_env_file=None)

    assert settings.taskiq_enabled_lanes == ("control", "provider-http", "provider-browser", "model-cpu")
    assert settings.taskiq_admitted_lanes == ("control", "provider-http", "provider-browser", "model-cpu")
    assert settings.taskiq_queue_name == "bet"
    assert settings.taskiq_provider_http_queue_name == "bet-provider-http"
    assert settings.taskiq_provider_browser_queue_name == "bet-provider-browser"
    assert settings.taskiq_model_cpu_queue_name == "bet-model-cpu"
    assert settings.taskiq_provider_browser_max_async_tasks == 1
    assert settings.taskiq_provider_browser_prefetch == 1
    assert settings.taskiq_model_cpu_max_async_tasks == 1


def test_worker_lane_configuration_rejects_shared_queues_and_excess_prefetch():
    with pytest.raises(ValidationError, match="queue names must be distinct"):
        Settings(_env_file=None, taskiq_provider_http_queue_name="bet")

    with pytest.raises(ValidationError, match="prefetch must not exceed"):
        Settings(_env_file=None, taskiq_provider_browser_prefetch=2)


def test_enabled_worker_lanes_accept_an_ordered_control_subset():
    settings = Settings(
        _env_file=None,
        taskiq_enabled_lanes="control,provider-browser",
        taskiq_admitted_lanes="control,provider-browser",
    )

    assert settings.taskiq_enabled_lanes == ("control", "provider-browser")


def test_environment_lane_lists_are_read_as_csv_not_json(monkeypatch):
    monkeypatch.setenv("BET_TASKIQ_ENABLED_LANES", "control,provider-http,provider-browser,model-cpu")
    monkeypatch.setenv("BET_TASKIQ_ADMITTED_LANES", "control,provider-http")

    settings = Settings(_env_file=None)

    assert settings.taskiq_enabled_lanes == ("control", "provider-http", "provider-browser", "model-cpu")
    assert settings.taskiq_admitted_lanes == ("control", "provider-http")


def test_admitted_lanes_are_an_ordered_subset_of_enabled_consumer_lanes():
    settings = Settings(
        _env_file=None,
        taskiq_enabled_lanes="control,provider-http,provider-browser",
        taskiq_admitted_lanes="control,provider-browser",
    )

    assert settings.taskiq_admitted_lanes == ("control", "provider-browser")


@pytest.mark.parametrize(
    ("enabled_lanes", "admitted_lanes"),
    (
        ("control", "control,provider-http"),
        ("control,provider-http", "provider-http"),
        ("control,provider-http", "provider-http,control"),
        ("control,provider-http", "control,control"),
    ),
)
def test_admitted_lanes_reject_disabled_or_noncanonical_values(enabled_lanes, admitted_lanes):
    with pytest.raises(ValidationError, match="admitted"):
        Settings(_env_file=None, taskiq_enabled_lanes=enabled_lanes, taskiq_admitted_lanes=admitted_lanes)


@pytest.mark.parametrize(
    "enabled_lanes",
    ("", "provider-http", "provider-http,control", "control,control", "control,unknown"),
)
def test_enabled_worker_lanes_require_control_and_canonical_order(enabled_lanes):
    with pytest.raises(ValidationError, match="enabled"):
        Settings(_env_file=None, taskiq_enabled_lanes=enabled_lanes)


def test_model_artifact_root_defaults_to_backend_owned_path_and_honors_explicit_setting(tmp_path):
    settings = Settings(_env_file=None)
    assert settings.resolved_model_artifact_root.endswith(".model-artifacts")

    configured = Settings(_env_file=None, model_artifact_root=str(tmp_path / "artifacts"))
    assert configured.resolved_model_artifact_root == str(tmp_path / "artifacts")


def test_canonical_model_pipeline_operations_are_isolated_to_model_cpu_lane():
    from app.tasks.worker_lanes import WorkerLane, contract_for_operation

    for operation in ("train_model", "backtest_model", "predict_model"):
        assert contract_for_operation(operation).lane is WorkerLane.MODEL_CPU
