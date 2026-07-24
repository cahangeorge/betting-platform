import pytest
from fastapi import Response
from pydantic import ValidationError

from app.api.v1 import auth as auth_api
from app.config import Settings


def _production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "jwt_secret": "x" * 32,
        "cookie_secure": True,
        "debug": False,
        "task_queue_backend": "taskiq",
        "cors_origins": "https://app.example.com",
        "trading_enabled": False,
        "trading_paper_enabled": False,
        "trading_live_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def _cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1") for key, value in response.raw_headers if key.decode("latin-1").lower() == "set-cookie"
    ]


def test_development_allows_local_fallback_secret_and_insecure_cookies():
    settings = Settings(
        environment="development",
        jwt_secret="dev-secret-change-in-production",
        cookie_secure=False,
    )

    assert settings.is_secure_environment is False


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("jwt_secret", ["", "dev-secret-change-in-production", "replace-this-in-non-dev", "short"])
def test_secure_environments_reject_missing_fallback_or_short_jwt_secrets(environment, jwt_secret):
    with pytest.raises(ValidationError, match="BET_JWT_SECRET"):
        Settings(environment=environment, jwt_secret=jwt_secret, cookie_secure=True)


def test_secure_environments_reject_insecure_auth_cookies():
    with pytest.raises(ValidationError, match="BET_COOKIE_SECURE"):
        _production_settings(cookie_secure=False)


def test_production_accepts_hardened_configuration():
    settings = _production_settings()

    assert settings.is_secure_environment is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"debug": True}, "BET_DEBUG"),
        ({"task_queue_backend": "inprocess"}, "BET_TASK_QUEUE_BACKEND"),
        ({"cors_origins": "https://app.example.com,*"}, "BET_CORS_ORIGINS"),
        ({"trading_enabled": True}, "BET_TRADING_ENABLED"),
        ({"trading_paper_enabled": True}, "BET_TRADING_PAPER_ENABLED"),
        ({"trading_live_enabled": True}, "BET_TRADING_LIVE_ENABLED"),
    ],
)
def test_production_rejects_incompatible_runtime_configuration(overrides, message):
    with pytest.raises(ValidationError, match=message):
        _production_settings(**overrides)


def test_staging_allows_paper_trading_but_rejects_live_trading():
    settings = Settings(
        environment="staging",
        jwt_secret="x" * 32,
        cookie_secure=True,
        trading_enabled=True,
        trading_paper_enabled=True,
        trading_live_enabled=False,
    )

    assert settings.trading_paper_enabled is True

    with pytest.raises(ValidationError, match="BET_TRADING_LIVE_ENABLED"):
        Settings(
            environment="staging",
            jwt_secret="x" * 32,
            cookie_secure=True,
            trading_live_enabled=True,
        )


def test_staging_rejects_wildcard_cors_with_credentials():
    with pytest.raises(ValidationError, match="BET_CORS_ORIGINS"):
        Settings(
            environment="staging",
            jwt_secret="x" * 32,
            cookie_secure=True,
            cors_origins="https://staging.example.com,*",
        )


@pytest.mark.parametrize(
    ("runtime_settings", "expects_secure"),
    [
        (Settings(environment="development", jwt_secret="dev-secret-change-in-production", cookie_secure=False), False),
        (_production_settings(), True),
    ],
)
def test_auth_cookie_flags_follow_validated_runtime_configuration(monkeypatch, runtime_settings, expects_secure):
    response = Response()
    monkeypatch.setattr(auth_api, "settings", runtime_settings)

    auth_api._set_auth_cookies(response, access_token="access", refresh_token="refresh")

    headers = _cookie_headers(response)
    assert len(headers) == 2
    assert all("HttpOnly" in header and "SameSite=lax" in header for header in headers)
    assert all(("Secure" in header) is expects_secure for header in headers)
