"""Pydantic settings – loads from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
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
    football_data_api_key: str = Field(default="", alias="FOOTBALL_DATA_API_KEY")

    @classmethod
    def load(cls) -> "Settings":
        overrides = {}
        if db_url := _read_secret("database_url"):
            overrides["database_url"] = db_url
        if jwt := _read_secret("jwt_secret"):
            overrides["jwt_secret"] = jwt
        return cls(**overrides)


@lru_cache
def get_settings() -> Settings:
    return Settings.load()