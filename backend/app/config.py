import warnings
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

DEVELOPMENT_ENVIRONMENTS = {"development", "test"}
SECURE_ENVIRONMENTS = {"staging", "production"}
INSECURE_JWT_SECRETS = {
    "dev-secret-change-in-production",
    "dev-jwt-secret-change-in-production",
    "replace-this-in-non-dev",
}
JWT_SECRET_MIN_LENGTH = 32


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

    scheduled_jobs_enabled: bool = False
    scheduled_jobs_interval_seconds: int = 60
    task_queue_backend: str = "inprocess"
    task_run_lease_seconds: int = 300
    task_publish_retry_seconds: int = 15
    task_publish_max_attempts: int = 5
    task_publish_replay_grace_seconds: int = 900
    redis_url: str = "redis://localhost:6379/0"
    taskiq_broker_url: str = ""
    taskiq_result_backend_url: str = ""
    taskiq_queue_name: str = "bet"
    taskiq_consumer_group: str = "bet-workers"
    taskiq_poll_interval_seconds: int = 60
    taskiq_result_ttl_seconds: int = 86400
    taskiq_runtime_heartbeat_seconds: int = 10
    taskiq_runtime_stale_seconds: int = 30

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
    soccerdata_python: str = ""
    soccerdata_bridge: str = ""
    soccerdata_root: str = ""
    oddsharvester_python: str = ""

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
