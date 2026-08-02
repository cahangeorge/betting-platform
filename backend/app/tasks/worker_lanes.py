from dataclasses import dataclass
from enum import StrEnum

WORKER_LANE_CONTRACT_VERSION = "worker-lanes/v1"
LEGACY_WORKER_CONTRACT_VERSION = "legacy-control/v0"


class WorkerLane(StrEnum):
    CONTROL = "control"
    PROVIDER_HTTP = "provider-http"
    PROVIDER_BROWSER = "provider-browser"
    MODEL_CPU = "model-cpu"


@dataclass(frozen=True)
class WorkerLaneSpec:
    lane: WorkerLane
    queue_name_setting: str
    consumer_group_setting: str
    processes: int
    async_tasks: int
    prefetch: int
    timeout_seconds: int
    max_attempts: int
    backlog_cap_setting: str


@dataclass(frozen=True)
class WorkContract:
    lane: WorkerLane
    queue_contract_version: str
    max_attempts: int


LANE_SPECS = {
    WorkerLane.CONTROL: WorkerLaneSpec(
        WorkerLane.CONTROL,
        "taskiq_queue_name",
        "taskiq_consumer_group",
        1,
        2,
        2,
        300,
        3,
        "taskiq_control_backlog_cap",
    ),
    WorkerLane.PROVIDER_HTTP: WorkerLaneSpec(
        WorkerLane.PROVIDER_HTTP,
        "taskiq_provider_http_queue_name",
        "taskiq_provider_http_consumer_group",
        1,
        4,
        4,
        900,
        4,
        "taskiq_provider_http_backlog_cap",
    ),
    WorkerLane.PROVIDER_BROWSER: WorkerLaneSpec(
        WorkerLane.PROVIDER_BROWSER,
        "taskiq_provider_browser_queue_name",
        "taskiq_provider_browser_consumer_group",
        1,
        1,
        1,
        3660,
        2,
        "taskiq_provider_browser_backlog_cap",
    ),
    WorkerLane.MODEL_CPU: WorkerLaneSpec(
        WorkerLane.MODEL_CPU,
        "taskiq_model_cpu_queue_name",
        "taskiq_model_cpu_consumer_group",
        1,
        1,
        1,
        3600,
        3,
        "taskiq_model_cpu_backlog_cap",
    ),
}
_OPERATION_CONTRACTS = {
    "scheduled_job": WorkContract(WorkerLane.CONTROL, WORKER_LANE_CONTRACT_VERSION, 3),
    "outbox_recovery_probe": WorkContract(WorkerLane.CONTROL, WORKER_LANE_CONTRACT_VERSION, 3),
    "verify_and_settle": WorkContract(WorkerLane.CONTROL, WORKER_LANE_CONTRACT_VERSION, 3),
    "verify_results": WorkContract(WorkerLane.CONTROL, WORKER_LANE_CONTRACT_VERSION, 3),
    "generate_tickets": WorkContract(WorkerLane.CONTROL, WORKER_LANE_CONTRACT_VERSION, 3),
    "scrape_job": WorkContract(WorkerLane.PROVIDER_BROWSER, WORKER_LANE_CONTRACT_VERSION, 2),
    "scrape_odds": WorkContract(WorkerLane.PROVIDER_BROWSER, WORKER_LANE_CONTRACT_VERSION, 2),
    "scrape_then_predict": WorkContract(WorkerLane.PROVIDER_BROWSER, WORKER_LANE_CONTRACT_VERSION, 2),
    "scrape_predict_tickets": WorkContract(WorkerLane.PROVIDER_BROWSER, WORKER_LANE_CONTRACT_VERSION, 2),
    "soccerdata_http_ingest": WorkContract(WorkerLane.PROVIDER_HTTP, WORKER_LANE_CONTRACT_VERSION, 4),
    "soccerdata_browser_ingest": WorkContract(WorkerLane.PROVIDER_BROWSER, WORKER_LANE_CONTRACT_VERSION, 2),
    "fetch_latest_odds": WorkContract(WorkerLane.PROVIDER_HTTP, WORKER_LANE_CONTRACT_VERSION, 4),
    "fetch_odds_snapshot": WorkContract(WorkerLane.PROVIDER_BROWSER, WORKER_LANE_CONTRACT_VERSION, 2),
    "world_cup_pipeline": WorkContract(WorkerLane.CONTROL, LEGACY_WORKER_CONTRACT_VERSION, 1),
    "run_predictions": WorkContract(WorkerLane.MODEL_CPU, WORKER_LANE_CONTRACT_VERSION, 3),
    # Canonical immutable model-artifact pipeline operations. They must run in
    # the isolated CPU lane; callers cannot select a lane directly.
    "train_model": WorkContract(WorkerLane.MODEL_CPU, WORKER_LANE_CONTRACT_VERSION, 3),
    "backtest_model": WorkContract(WorkerLane.MODEL_CPU, WORKER_LANE_CONTRACT_VERSION, 3),
    "predict_model": WorkContract(WorkerLane.MODEL_CPU, WORKER_LANE_CONTRACT_VERSION, 3),
}


class UnknownWorkerOperationError(ValueError):
    pass


class WorkerLaneDisabledError(RuntimeError):
    pass


def normalize_worker_lane(value):
    try:
        return value if isinstance(value, WorkerLane) else WorkerLane(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"Unknown worker lane {value!r}") from exc


def contract_for_operation(operation, *, allow_unknown_control=False):
    contract = _OPERATION_CONTRACTS.get(str(operation or "").strip().lower())
    if contract is not None:
        return contract
    if allow_unknown_control:
        return WorkContract(WorkerLane.CONTROL, WORKER_LANE_CONTRACT_VERSION, 3)
    raise UnknownWorkerOperationError(f"No approved worker-lane contract for operation {operation!r}")


def lane_for_operation(operation, *, allow_unknown_control=False):
    return contract_for_operation(operation, allow_unknown_control=allow_unknown_control).lane


def worker_lane_spec(lane):
    return LANE_SPECS[normalize_worker_lane(lane)]


def default_max_attempts(lane):
    return worker_lane_spec(lane).max_attempts


def backlog_cap_for_lane(settings, lane) -> int:
    return int(getattr(settings, worker_lane_spec(lane).backlog_cap_setting))


def queue_name_for_lane(settings, lane):
    value = str(getattr(settings, worker_lane_spec(lane).queue_name_setting)).strip()
    if not value:
        raise ValueError("Taskiq queue name must not be empty")
    return value


def consumer_group_for_lane(settings, lane):
    value = str(getattr(settings, worker_lane_spec(lane).consumer_group_setting)).strip()
    if not value:
        raise ValueError("Taskiq consumer group must not be empty")
    return value


def enabled_worker_lanes(settings) -> tuple[WorkerLane, ...]:
    """Return the validated ordered rollout subset configured for this process."""
    return tuple(normalize_worker_lane(lane) for lane in settings.taskiq_enabled_lanes)


def is_worker_lane_enabled(settings, lane) -> bool:
    return normalize_worker_lane(lane) in enabled_worker_lanes(settings)


def admitted_worker_lanes(settings) -> tuple[WorkerLane, ...]:
    """Return lanes that may receive new work; enabled workers may still drain."""
    return tuple(normalize_worker_lane(lane) for lane in settings.taskiq_admitted_lanes)


def is_worker_lane_admitted(settings, lane) -> bool:
    return normalize_worker_lane(lane) in admitted_worker_lanes(settings)
