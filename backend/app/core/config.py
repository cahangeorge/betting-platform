"""Pydantic settings – loads from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret(name: str) -> str | None:
    path = Path(f"/run/secrets/{name}")
    if path.exists():
        return path.read_text().strip()
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="betting-platform", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    database_url: str = Field(
        default="sqlite+aiosqlite:///./betting.db",
        alias="DATABASE_URL",
    )
    jwt_secret: str = Field(default="dev-secret-change-in-production-32chars", alias="JWT_SECRET")
    jwt_access_token_expire_minutes: int = Field(default=60, alias="JWT_EXPIRE_MINUTES")

    # Betfair — delayed app key is free, live is £499 one-time
    betfair_app_key: str = Field(default="", alias="BETFAIR_APP_KEY")
    betfair_session_token: str = Field(default="", alias="BETFAIR_SESSION_TOKEN")
    betfair_username: str = Field(default="", alias="BETFAIR_USERNAME")
    betfair_password: str = Field(default="", alias="BETFAIR_PASSWORD")

    # Matchbook — free API up to 1M GET requests/month
    matchbook_username: str = Field(default="", alias="MATCHBOOK_USERNAME")
    matchbook_password: str = Field(default="", alias="MATCHBOOK_PASSWORD")

    # Football-data.org — free tier for live stats
    football_data_api_key: str = Field(default="", alias="FOOTBALL_DATA_API_KEY")

    @classmethod
    def load(cls) -> "Settings":
        overrides = {}
        for secret_name, field_name in [
            ("database_url", "database_url"),
            ("jwt_secret", "jwt_secret"),
            ("betfair_app_key", "betfair_app_key"),
            ("betfair_session_token", "betfair_session_token"),
            ("betfair_username", "betfair_username"),
            ("betfair_password", "betfair_password"),
            ("matchbook_username", "matchbook_username"),
            ("matchbook_password", "matchbook_password"),
        ]:
            if val := _read_secret(secret_name):
                overrides[field_name] = val
        return cls(**overrides)


@lru_cache
def get_settings() -> Settings:
    return Settings.load()