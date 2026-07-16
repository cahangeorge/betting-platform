from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.api.deps import get_current_user
from app.api.v1 import auth as auth_api
from app.database import get_db
from app.main import app
from app.models.user import Session, User
from app.schemas.auth import LoginRequest, SignupRequest
from app.services.auth import create_access_token, create_refresh_token, decode_token


class _EmptyListResult:
    def scalars(self):
        return self

    def all(self):
        return []


class _StrategyReadDb:
    async def execute(self, _statement):
        return _EmptyListResult()


class _RefreshDb:
    def __init__(self, user, *, consumable_sessions: int = 0):
        self.user = user
        self.consumable_sessions = consumable_sessions
        self.rotated_sessions = []

    async def execute(self, _statement):
        consumed = self.consumable_sessions > 0
        if consumed:
            self.consumable_sessions -= 1

        class _Result:
            def scalar_one_or_none(self):
                return 1 if consumed else None

        return _Result()

    async def get(self, model, object_id):
        assert model is User
        if self.user is not None and object_id == self.user.id:
            return self.user
        return None

    def add(self, session):
        assert isinstance(session, Session)
        self.rotated_sessions.append(session)

    async def commit(self):
        return None


def _auth_user(*, user_id: int = 7, is_admin: bool = False):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=user_id,
        email=f"user-{user_id}@example.com",
        name="Test User",
        is_admin=is_admin,
        created_at=now,
        updated_at=now,
    )


def _cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.decode("latin-1").lower() == "set-cookie"
    ]


def test_refresh_tokens_are_unique_and_session_bound():
    first = create_refresh_token(7)
    second = create_refresh_token(7)

    assert first != second
    assert decode_token(first)["sid"] == decode_token(first)["jti"]
    assert decode_token(first)["sid"] != decode_token(second)["sid"]


@pytest.mark.asyncio
async def test_non_admin_can_read_strategies_but_cannot_mutate_global_catalog():
    async def non_admin_user():
        return _auth_user(is_admin=False)

    async def strategy_db():
        yield _StrategyReadDb()

    app.dependency_overrides[get_current_user] = non_admin_user
    app.dependency_overrides[get_db] = strategy_db
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            read_response = await client.get("/api/v1/strategies")
            assert read_response.status_code == 200
            assert read_response.json() == []

            mutations = [
                ("POST", "/api/v1/strategies", {"name": "Blocked", "model_type": "poisson"}),
                ("PUT", "/api/v1/strategies/1", {"name": "Blocked"}),
                ("DELETE", "/api/v1/strategies/1", None),
                ("POST", "/api/v1/strategies/1/duplicate", {"name": "Blocked copy"}),
            ]
            for method, path, payload in mutations:
                response = await client.request(method, path, json=payload)
                assert response.status_code == 403, (method, path, response.text)
                assert response.json() == {"detail": "Admin access required"}
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("request_model", [SignupRequest, LoginRequest])
@pytest.mark.parametrize("password", ["a" * 73, "ă" * 37])
def test_auth_requests_reject_passwords_over_72_utf8_bytes(request_model, password):
    with pytest.raises(ValidationError, match="72 UTF-8 bytes"):
        request_model(email="person@example.com", password=password)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/auth/signup", "/api/v1/auth/login"])
@pytest.mark.parametrize("password", ["a" * 73, "ă" * 37])
async def test_auth_endpoints_return_422_for_passwords_over_72_utf8_bytes(path, password):
    async def unused_db():
        yield object()

    app.dependency_overrides[get_db] = unused_db
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(path, json={"email": "person@example.com", "password": password})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 422
    assert "72 UTF-8 bytes" in response.text


@pytest.mark.asyncio
async def test_refresh_rotates_auth_cookies_and_returns_current_user():
    user = _auth_user(user_id=42)
    response = Response()
    refresh_token = create_refresh_token(user.id)
    db = _RefreshDb(user, consumable_sessions=1)

    refreshed_user = await auth_api.refresh_auth(
        response=response,
        refresh_token=refresh_token,
        db=db,
    )

    assert refreshed_user is user
    headers = _cookie_headers(response)
    assert any("access_token=" in header and "HttpOnly" in header and "SameSite=lax" in header for header in headers)
    assert any("refresh_token=" in header and "HttpOnly" in header and "SameSite=lax" in header for header in headers)
    rotated_cookie = next(header for header in headers if header.startswith("refresh_token="))
    rotated_token = rotated_cookie.split(";", 1)[0].split("=", 1)[1]
    assert rotated_token != refresh_token
    assert decode_token(rotated_token)["sid"] == db.rotated_sessions[0].session_id

    with pytest.raises(HTTPException) as replay_error:
        await auth_api.refresh_auth(
            response=Response(),
            refresh_token=refresh_token,
            db=db,
        )
    assert replay_error.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token", "user"),
    [
        (None, _auth_user()),
        ("not-a-token", _auth_user()),
        (create_access_token(7), _auth_user()),
        (create_refresh_token(999), None),
    ],
)
async def test_refresh_rejects_missing_invalid_wrong_type_or_unknown_user(token, user):
    with pytest.raises(HTTPException) as exc_info:
        await auth_api.refresh_auth(
            response=Response(),
            refresh_token=token,
            db=_RefreshDb(user),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or expired refresh token"


@pytest.mark.asyncio
async def test_refresh_endpoint_returns_declared_user_response_and_rotated_tokens():
    user = _auth_user(user_id=23)

    async def refresh_db():
        yield _RefreshDb(user, consumable_sessions=1)

    app.dependency_overrides[get_db] = refresh_db
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={"refresh_token": create_refresh_token(user.id)},
        ) as client:
            response = await client.post("/api/v1/auth/refresh")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert response.json()["email"] == user.email
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    access_cookie = next(cookie for cookie in cookies if cookie.startswith("access_token="))
    refresh_cookie = next(cookie for cookie in cookies if cookie.startswith("refresh_token="))
    assert decode_token(access_cookie.split(";", 1)[0].split("=", 1)[1])["type"] == "access"
    assert decode_token(refresh_cookie.split(";", 1)[0].split("=", 1)[1])["type"] == "refresh"


@pytest.mark.asyncio
async def test_logout_revokes_the_presented_refresh_session_and_clears_cookies():
    token = create_refresh_token(7)
    db = _RefreshDb(_auth_user(), consumable_sessions=1)
    response = Response()

    result = await auth_api.logout(response=response, refresh_token=token, db=db)

    assert result == {"message": "Logged out successfully"}
    assert db.consumable_sessions == 0
    headers = _cookie_headers(response)
    assert any(header.startswith('access_token=""') and "Max-Age=0" in header for header in headers)
    assert any(header.startswith('refresh_token=""') and "Max-Age=0" in header for header in headers)
