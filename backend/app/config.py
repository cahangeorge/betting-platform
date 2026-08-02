import warnings
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode

DEVELOPMENT_ENVIRONMENTS = {"development", "test"}
SECURE_ENVIRONMENTS = {"staging", "production"}
INSECURE_JWT_SECRETS = {
    "dev-secret-change-in-production",
    "dev-jwt-secret-change-in-production",
    "replace-this-in-non-dev",
}
JWT_SECRET_MIN_LENGTH = 32
TASKIQ_LANE_ORDER = ("control", "provider-http", "provider-browser", "model-cpu")


def _validate_ordered_taskiq_lanes(value: object, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        lanes = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    elif isinstance(value, (tuple, list)):
        lanes = tuple(str(part).strip().lower() for part in value if str(part).strip())
    else:
        raise ValueError(f"taskiq {field_name} lanes must be a comma-separated ordered lane list")

    if not lanes or "control" not in lanes:
        raise ValueError(f"taskiq {field_name} lanes must include control")
    if len(set(lanes)) != len(lanes):
        raise ValueError(f"taskiq {field_name} lanes must not contain duplicates")
    if any(lane not in TASKIQ_LANE_ORDER for lane in lanes):
        raise ValueError(f"taskiq {field_name} lanes contain an unknown lane")
    ordered_subset = tuple(lane for lane in TASKIQ_LANE_ORDER if lane in lanes)
    if lanes != ordered_subset:
        raise ValueError(f"taskiq {field_name} lanes must use canonical order")
    return lanes


class Settings(BaseSettings):
    app_name: str = "bet-backend"
    debug: bool = False
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/bet"
    auto_create_schema: bool = False
    seed_dev_admin: bool = False
    dev_admin_email: str = "admin@betfront.com"
    dev_admin_password: str = "admin123"
    dev_admin_name: str = "Admin"

    jwt_secret: str = "dev-jwt-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: str = (
        "http://localhost:5173,http://localhost:5174,http://localhost:5175,"
        "http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175,"
        "http://localhost:3000,http://localhost:3002,http://localhost:8080"
    )

    cookie_secure: bool = False

    # Per-process throttling is deliberately enabled by default. Deployments that
    # run multiple API instances should keep the edge/proxy limiter enabled too.
    auth_rate_limit_enabled: bool = True
    auth_rate_limit_window_seconds: int = Field(default=300, ge=1, le=86_400)
    auth_login_max_attempts: int = Field(default=10, ge=1, le=1_000)
    auth_signup_max_attempts: int = Field(default=5, ge=1, le=1_000)
    auth_source_max_attempts: int = Field(default=1_000, ge=1, le=100_000)
    auth_rate_limit_max_sources: int = Field(default=10_000, ge=1, le=1_000_000)
    auth_rate_limit_max_identities: int = Field(default=100_000, ge=1, le=1_000_000)

    # WebSocket capacity is per API process. Horizontal scaling needs a shared
    # pub/sub and admission layer before increasing these values materially.
    websocket_max_connections: int = Field(default=100, ge=1, le=100_000)
    websocket_max_connections_per_user: int = Field(default=3, ge=1, le=1_000)
    websocket_receive_timeout_seconds: int = Field(default=300, ge=1, le=86_400)
    websocket_send_timeout_seconds: int = Field(default=5, ge=1, le=300)
    websocket_max_message_bytes: int = Field(default=8_192, ge=1, le=1_048_576)

    bridge_timeout_seconds: int = 180
    oddsharvester_timeout_seconds: int = 600
    # Deterministic canary percentage for the hybrid scraper pipeline.
    scrape_pipeline_v2_percent: int = Field(default=0, ge=0, le=100)

    scheduled_jobs_enabled: bool = False
    scheduled_jobs_interval_seconds: int = 60
    task_queue_backend: str = "inprocess"
    # The development fallback must not launch every browser-heavy scrape at
    # once when Prepare creates several bounded jobs. Taskiq workers provide
    # their own concurrency control in deployments.
    inprocess_scrape_max_concurrency: int = Field(default=1, ge=1, le=4)
    task_run_lease_seconds: int = 300
    task_publish_retry_seconds: int = 15
    task_publish_max_attempts: int = 5
    task_publish_replay_grace_seconds: int = 900
    redis_url: str = "redis://localhost:6379/0"
    taskiq_broker_url: str = ""
    taskiq_result_backend_url: str = ""
    # `bet` remains the legacy-compatible control queue. Dedicated provider and
    # model queues are deliberately explicit; callers do not select them.
    taskiq_queue_name: str = "bet"
    taskiq_consumer_group: str = "bet-workers"
    # Set per worker process; API/scheduler processes retain the control default.
    taskiq_worker_lane: str = "control"
    # Staged rollout control. The order is semantic and must follow the
    # backend-owned lane sequence; control is permanently required for legacy
    # Taskiq work and scheduler/outbox recovery.
    taskiq_enabled_lanes: Annotated[tuple[str, ...], NoDecode] = (
        "control",
        "provider-http",
        "provider-browser",
        "model-cpu",
    )
    # Consumer/drain availability is independent from new-work admission. This
    # lets an operator stop publishing provider work while retained workers
    # drain their durable backlog during a staged rollback.
    taskiq_admitted_lanes: Annotated[tuple[str, ...], NoDecode] = (
        "control",
        "provider-http",
        "provider-browser",
        "model-cpu",
    )
    taskiq_provider_http_queue_name: str = "bet-provider-http"
    taskiq_provider_http_consumer_group: str = "bet-provider-http-workers"
    taskiq_provider_browser_queue_name: str = "bet-provider-browser"
    taskiq_provider_browser_consumer_group: str = "bet-provider-browser-workers"
    taskiq_model_cpu_queue_name: str = "bet-model-cpu"
    taskiq_model_cpu_consumer_group: str = "bet-model-cpu-workers"
    taskiq_control_worker_processes: int = Field(default=1, ge=1, le=16)
    taskiq_control_max_async_tasks: int = Field(default=2, ge=1, le=64)
    taskiq_control_prefetch: int = Field(default=2, ge=1, le=64)
    taskiq_control_timeout_seconds: int = Field(default=300, ge=1, le=86_400)
    taskiq_control_backlog_cap: int = Field(default=1000, ge=1, le=100_000)
    taskiq_provider_http_worker_processes: int = Field(default=1, ge=1, le=16)
    taskiq_provider_http_max_async_tasks: int = Field(default=4, ge=1, le=64)
    taskiq_provider_http_prefetch: int = Field(default=4, ge=1, le=64)
    taskiq_provider_http_timeout_seconds: int = Field(default=900, ge=1, le=86_400)
    taskiq_provider_http_backlog_cap: int = Field(default=200, ge=1, le=100_000)
    taskiq_provider_browser_worker_processes: int = Field(default=1, ge=1, le=16)
    taskiq_provider_browser_max_async_tasks: int = Field(default=1, ge=1, le=64)
    taskiq_provider_browser_prefetch: int = Field(default=1, ge=1, le=64)
    taskiq_provider_browser_timeout_seconds: int = Field(default=3660, ge=1, le=86_400)
    taskiq_provider_browser_backlog_cap: int = Field(default=50, ge=1, le=100_000)
    taskiq_model_cpu_worker_processes: int = Field(default=1, ge=1, le=16)
    taskiq_model_cpu_max_async_tasks: int = Field(default=1, ge=1, le=64)
    taskiq_model_cpu_prefetch: int = Field(default=1, ge=1, le=64)
    taskiq_model_cpu_timeout_seconds: int = Field(default=3600, ge=1, le=86_400)
    taskiq_model_cpu_backlog_cap: int = Field(default=50, ge=1, le=100_000)
    taskiq_poll_interval_seconds: int = 60
    taskiq_result_ttl_seconds: int = 86400
    taskiq_runtime_heartbeat_seconds: int = 10
    taskiq_runtime_stale_seconds: int = 30

    @field_validator("taskiq_worker_lane", mode="before")
    @classmethod
    def validate_taskiq_worker_lane(cls, value: object) -> str:
        lane = str(value or "control").strip().lower()
        if lane not in {"control", "provider-http", "provider-browser", "model-cpu"}:
            raise ValueError("taskiq_worker_lane must be control, provider-http, provider-browser, or model-cpu")
        return lane

    @field_validator("taskiq_enabled_lanes", mode="before")
    @classmethod
    def validate_taskiq_enabled_lanes(cls, value: object) -> tuple[str, ...]:
        return _validate_ordered_taskiq_lanes(value, field_name="enabled")

    @field_validator("taskiq_admitted_lanes", mode="before")
    @classmethod
    def validate_taskiq_admitted_lanes(cls, value: object) -> tuple[str, ...]:
        return _validate_ordered_taskiq_lanes(value, field_name="admitted")

    @field_validator("task_queue_backend", mode="before")
    @classmethod
    def validate_task_queue_backend(cls, value: object) -> str:
        backend = str(value or "inprocess").strip().lower()
        if backend == "inline":
            warnings.warn(
                "BET_TASK_QUEUE_BACKEND=inline is deprecated; use inprocess",
                DeprecationWarning,
                stacklevel=2,
            )
            return "inprocess"
        if backend not in {"inprocess", "taskiq"}:
            raise ValueError("task_queue_backend must be 'inprocess' (or legacy 'inline') or 'taskiq'")
        return backend

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, value: object) -> str:
        environment = str(value or "development").strip().lower()
        supported = DEVELOPMENT_ENVIRONMENTS | SECURE_ENVIRONMENTS
        if environment not in supported:
            raise ValueError("environment must be development, test, staging, or production")
        return environment

    @property
    def is_secure_environment(self) -> bool:
        return self.environment in SECURE_ENVIRONMENTS

    @staticmethod
    def _is_placeholder_jwt_secret(secret: str) -> bool:
        normalized = secret.strip().lower()
        return normalized in INSECURE_JWT_SECRETS or any(
            marker in normalized for marker in ("placeholder", "replace", "change-me", "example")
        )

    @model_validator(mode="after")
    def validate_runtime_security(self) -> "Settings":
        if self.is_secure_environment:
            secret = self.jwt_secret.strip()
            if len(secret) < JWT_SECRET_MIN_LENGTH or self._is_placeholder_jwt_secret(secret):
                raise ValueError(
                    "BET_JWT_SECRET must be a non-placeholder value of at least "
                    f"{JWT_SECRET_MIN_LENGTH} characters when BET_ENVIRONMENT is staging or production"
                )
            if not self.cookie_secure:
                raise ValueError("BET_COOKIE_SECURE must be true when BET_ENVIRONMENT is staging or production")
            if self.trading_live_enabled:
                raise ValueError("BET_TRADING_LIVE_ENABLED must be false when BET_ENVIRONMENT is staging or production")
            if not self.auth_rate_limit_enabled:
                raise ValueError(
                    "BET_AUTH_RATE_LIMIT_ENABLED must be true when BET_ENVIRONMENT is staging or production"
                )
            if "*" in self.cors_origin_list:
                raise ValueError("BET_CORS_ORIGINS must not contain '*' when BET_ENVIRONMENT is staging or production")

        lane_queues = {
            "control": self.taskiq_queue_name.strip(),
            "provider-http": self.taskiq_provider_http_queue_name.strip(),
            "provider-browser": self.taskiq_provider_browser_queue_name.strip(),
            "model-cpu": self.taskiq_model_cpu_queue_name.strip(),
        }
        lane_groups = {
            "control": self.taskiq_consumer_group.strip(),
            "provider-http": self.taskiq_provider_http_consumer_group.strip(),
            "provider-browser": self.taskiq_provider_browser_consumer_group.strip(),
            "model-cpu": self.taskiq_model_cpu_consumer_group.strip(),
        }
        if not all(lane_queues.values()) or not all(lane_groups.values()):
            raise ValueError("Taskiq lane queue names and consumer groups must not be empty")
        if len(set(lane_queues.values())) != len(lane_queues):
            raise ValueError("Taskiq lane queue names must be distinct")
        if len(set(lane_groups.values())) != len(lane_groups):
            raise ValueError("Taskiq lane consumer groups must be distinct")
        if self.taskiq_worker_lane not in self.taskiq_enabled_lanes:
            raise ValueError("taskiq_worker_lane must be enabled by taskiq_enabled_lanes")
        if not set(self.taskiq_admitted_lanes).issubset(self.taskiq_enabled_lanes):
            raise ValueError("taskiq admitted lanes must be a subset of taskiq enabled lanes")
        for lane, max_async_tasks, prefetch in (
            ("control", self.taskiq_control_max_async_tasks, self.taskiq_control_prefetch),
            ("provider-http", self.taskiq_provider_http_max_async_tasks, self.taskiq_provider_http_prefetch),
            ("provider-browser", self.taskiq_provider_browser_max_async_tasks, self.taskiq_provider_browser_prefetch),
            ("model-cpu", self.taskiq_model_cpu_max_async_tasks, self.taskiq_model_cpu_prefetch),
        ):
            if prefetch > max_async_tasks:
                raise ValueError(f"Taskiq {lane} prefetch must not exceed max async tasks")

        if self.environment == "production":
            if self.debug:
                raise ValueError("BET_DEBUG must be false when BET_ENVIRONMENT is production")
            if self.task_queue_backend == "inprocess":
                raise ValueError("BET_TASK_QUEUE_BACKEND must be taskiq when BET_ENVIRONMENT is production")
            if self.trading_enabled:
                raise ValueError("BET_TRADING_ENABLED must be false when BET_ENVIRONMENT is production")
            if self.trading_paper_enabled:
                raise ValueError("BET_TRADING_PAPER_ENABLED must be false when BET_ENVIRONMENT is production")
        return self

    # Trading is paper-local only. Live execution remains a deliberately
    # non-functional capability even if an environment accidentally enables it.
    trading_enabled: bool = True
    trading_paper_enabled: bool = True
    trading_live_enabled: bool = False
    trading_betfair_read_only_enabled: bool = False
    trading_taskiq_queue_name: str = "bet-trading"
    flumine_root: str = ""

    penaltyblog_python: str = ""
    penaltyblog_bridge: str = ""
    penaltyblog_root: str = ""
    # Backend-owned persistent storage for opaque trusted model artifacts.
    # The model-cpu worker is the only writer; API processes may verify/read.
    model_artifact_root: str = ""
    soccerdata_python: str = ""
    soccerdata_bridge: str = ""
    soccerdata_root: str = ""
    oddsharvester_python: str = ""
    # Kept unset by default.  A credential alone does not enable the licensed
    # source: the registry remains the approval boundary.
    sportmonks_api_token: SecretStr | None = None
    sportmonks_timeout_seconds: int = Field(default=20, ge=1, le=120)

    @property
    def resolved_taskiq_broker_url(self) -> str:
        return self.taskiq_broker_url or self.redis_url

    @property
    def resolved_taskiq_result_backend_url(self) -> str:
        return self.taskiq_result_backend_url or self.redis_url

    model_config = {"env_prefix": "BET_", "env_file": ".env", "extra": "allow"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _first_existing(self, *candidates: Path) -> str:
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return str(candidates[0]) if candidates else ""

    @property
    def resolved_model_artifact_root(self) -> str:
        return self.model_artifact_root or str(self.repo_root / ".model-artifacts")

    @property
    def resolved_penaltyblog_python(self) -> str:
        if self.penaltyblog_python:
            return self.penaltyblog_python
        return self._first_existing(
            self.repo_root / "penaltyblog" / ".venv" / "bin" / "python",
        )

    @property
    def resolved_penaltyblog_bridge(self) -> str:
        if self.penaltyblog_bridge:
            return self.penaltyblog_bridge
        return str(self.repo_root / "backend" / "app" / "bridges" / "penaltyblog_bridge.py")

    @property
    def resolved_penaltyblog_root(self) -> str:
        return self.penaltyblog_root or str(self.repo_root / "penaltyblog")

    @property
    def resolved_soccerdata_python(self) -> str:
        if self.soccerdata_python:
            return self.soccerdata_python
        return self._first_existing(
            self.repo_root / "soccerdata" / ".venv" / "bin" / "python",
        )

    @property
    def resolved_soccerdata_bridge(self) -> str:
        if self.soccerdata_bridge:
            return self.soccerdata_bridge
        return str(self.repo_root / "backend" / "app" / "bridges" / "soccerdata_bridge.py")

    @property
    def resolved_flumine_root(self) -> str:
        return self.flumine_root or str(self.repo_root / "flumine")

    @property
    def resolved_soccerdata_root(self) -> str:
        return self.soccerdata_root or str(self.repo_root / "soccerdata")

    @property
    def resolved_oddsharvester_python(self) -> str:
        if self.oddsharvester_python:
            return self.oddsharvester_python
        return self._first_existing(
            self.repo_root / "OddsHarvester" / ".venv" / "bin" / "python",
        )

    def provider_validation_issues(self, provider: str) -> list[str]:
        checks_by_provider = {
            "penaltyblog": [
                ("BET_PENALTYBLOG_PYTHON", self.resolved_penaltyblog_python),
                ("BET_PENALTYBLOG_BRIDGE", self.resolved_penaltyblog_bridge),
                ("BET_PENALTYBLOG_ROOT", self.resolved_penaltyblog_root),
            ],
            "soccerdata": [
                ("BET_SOCCERDATA_PYTHON", self.resolved_soccerdata_python),
                ("BET_SOCCERDATA_BRIDGE", self.resolved_soccerdata_bridge),
                ("BET_SOCCERDATA_ROOT", self.resolved_soccerdata_root),
            ],
            "oddsharvester": [
                ("BET_ODDSHARVESTER_PYTHON", self.resolved_oddsharvester_python),
            ],
        }
        if provider not in checks_by_provider:
            raise ValueError(f"Unknown bridge provider: {provider}")

        issues: list[str] = []
        for env_name, resolved in checks_by_provider[provider]:
            if not resolved:
                issues.append(f"{env_name} is unset and no default candidate could be derived")
                continue
            if not Path(resolved).exists():
                issues.append(f"{env_name} points to a missing path: {resolved}")
        return issues

    def bridge_validation_issues(self) -> list[str]:
        """Return all provider issues for diagnostics, not global readiness."""
        return [
            issue
            for provider in ("penaltyblog", "soccerdata", "oddsharvester")
            for issue in self.provider_validation_issues(provider)
        ]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
