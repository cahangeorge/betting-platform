from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "bet-backend"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/bet"
    auto_create_schema: bool = False
    seed_dev_admin: bool = False
    dev_admin_email: str = "admin@betfront.com"
    dev_admin_password: str = "admin123"
    dev_admin_name: str = "Admin"

    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000,http://localhost:3002,http://localhost:8080"

    cookie_secure: bool = False

    bridge_timeout_seconds: int = 180
    oddsharvester_timeout_seconds: int = 600

    scheduled_jobs_enabled: bool = True
    scheduled_jobs_interval_seconds: int = 60

    penaltyblog_python: str = ""
    penaltyblog_bridge: str = ""
    soccerdata_python: str = ""
    soccerdata_bridge: str = ""
    oddsharvester_python: str = ""

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
        return self._first_existing(
            self.repo_root / "frontbet" / "scripts" / "penaltyblog_bridge.py",
            self.repo_root / "betfront" / "scripts" / "penaltyblog_bridge.py",
        )

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
        return self._first_existing(
            self.repo_root / "frontbet" / "scripts" / "soccerdata_bridge.py",
            self.repo_root / "betfront" / "scripts" / "soccerdata_bridge.py",
        )

    @property
    def resolved_oddsharvester_python(self) -> str:
        if self.oddsharvester_python:
            return self.oddsharvester_python
        return self._first_existing(
            self.repo_root / "OddsHarvester" / ".venv" / "bin" / "python",
        )

    def bridge_validation_issues(self) -> list[str]:
        checks = [
            ("BET_PENALTYBLOG_PYTHON", self.resolved_penaltyblog_python),
            ("BET_PENALTYBLOG_BRIDGE", self.resolved_penaltyblog_bridge),
            ("BET_SOCCERDATA_PYTHON", self.resolved_soccerdata_python),
            ("BET_SOCCERDATA_BRIDGE", self.resolved_soccerdata_bridge),
            ("BET_ODDSHARVESTER_PYTHON", self.resolved_oddsharvester_python),
        ]

        issues: list[str] = []
        for env_name, resolved in checks:
            if not resolved:
                issues.append(f"{env_name} is unset and no default candidate could be derived")
                continue
            if not Path(resolved).exists():
                issues.append(f"{env_name} points to a missing path: {resolved}")
        return issues


@lru_cache()
def get_settings() -> Settings:
    return Settings()
