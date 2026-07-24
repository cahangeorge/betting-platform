import asyncio
from datetime import datetime, timezone
from io import StringIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Request, Response
from pydantic import ValidationError

from app.api.deps import get_current_user
from app.api.v1 import auth as auth_api
from app.config import Settings
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

    async def execute(self, statement):
        value = self.user if getattr(statement, "is_select", False) else None
        if not getattr(statement, "is_select", False):
            value = 1 if self.consumable_sessions > 0 else None
            if value is not None:
                self.consumable_sessions -= 1

        class _Result:
            def scalar_one_or_none(self):
                return value

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
        value.decode("latin-1") for key, value in response.raw_headers if key.decode("latin-1").lower() == "set-cookie"
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


@pytest.mark.asyncio
async def test_auth_rate_limit_uses_real_json_audit_sink_without_pii(monkeypatch):
    await auth_api.auth_attempt_limiter.reset()
    monkeypatch.setattr(auth_api, "settings", _rate_settings(identity_max=1, source_max=10))
    sink = StringIO()
    handler = next(handler for handler in auth_api.logger.handlers if getattr(handler, "_bet_auth_audit_sink", False))
    original_stream = handler.setStream(sink)
    request = Request({"type": "http", "client": ("198.51.100.17", 4567)})
    try:
        await auth_api._enforce_auth_rate_limit(action="login", request=request)
        await auth_api._record_auth_failure(action="login", identity="audit@example.com")
        with pytest.raises(HTTPException):
            await auth_api._record_auth_failure(action="login", identity="audit@example.com")
    finally:
        handler.setStream(original_stream)

    output = sink.getvalue()
    assert '"event":"auth_audit"' in output
    assert '"action":"login"' in output
    assert '"outcome":"rate_limited"' in output
    assert "198.51.100.17" not in output
    assert "audit@example.com" not in output
    await auth_api.auth_attempt_limiter.reset()


def _rate_settings(*, identity_max: int = 10, source_max: int = 1000, max_sources: int = 10, max_identities: int = 10):
    return SimpleNamespace(
        auth_rate_limit_enabled=True,
        auth_rate_limit_window_seconds=60,
        auth_login_max_attempts=identity_max,
        auth_signup_max_attempts=identity_max,
        auth_source_max_attempts=source_max,
        auth_rate_limit_max_sources=max_sources,
        auth_rate_limit_max_identities=max_identities,
        cookie_secure=False,
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
    )


@pytest.mark.asyncio
async def test_successful_logins_do_not_consume_identity_failure_limit(monkeypatch):
    await auth_api.auth_attempt_limiter.reset()
    monkeypatch.setattr(auth_api, "settings", _rate_settings(identity_max=1, source_max=100))
    user = SimpleNamespace(id=7, email="user@example.com", password_hash=auth_api.hash_password("password123"))

    class Db:
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: user)

        def add(self, _value):
            return None

        async def commit(self):
            return None

    request = Request({"type": "http", "client": ("127.0.0.1", 1234)})
    body = LoginRequest(email="user@example.com", password="password123")
    for _ in range(10):
        await auth_api.login(body=body, request=request, response=Response(), db=Db())
    assert not auth_api.auth_attempt_limiter._identities

    with pytest.raises(HTTPException) as first_failure:
        await auth_api.login(
            body=LoginRequest(email="user@example.com", password="wrong-password"),
            request=request,
            response=Response(),
            db=Db(),
        )
    assert first_failure.value.status_code == 401
    with pytest.raises(HTTPException) as limited:
        await auth_api.login(
            body=LoginRequest(email="user@example.com", password="wrong-password"),
            request=request,
            response=Response(),
            db=Db(),
        )
    assert limited.value.status_code == 429
    await auth_api.auth_attempt_limiter.reset()


@pytest.mark.asyncio
async def test_source_spray_identity_bounds_and_expiry_are_fail_closed(monkeypatch):
    limiter = auth_api.AuthAttemptLimiter()
    monkeypatch.setattr(auth_api, "settings", _rate_settings(source_max=2, max_sources=1, max_identities=2))

    assert await limiter.allow_source(action="signup", source="source-one")
    assert await limiter.allow_source(action="signup", source="source-one")
    assert not await limiter.allow_source(action="signup", source="source-one")
    assert len(limiter._sources) == 1
    assert await limiter.record_identity_failure(action="signup", identity="one@example.com")
    assert await limiter.record_identity_failure(action="signup", identity="two@example.com")
    assert not await limiter.record_identity_failure(action="signup", identity="three@example.com")
    assert len(limiter._identities) == 2
    assert all("@" not in key for key in limiter._identities)


@pytest.mark.asyncio
async def test_auth_rate_limit_heap_expiry_releases_bounded_bucket_capacity(monkeypatch):
    limiter = auth_api.AuthAttemptLimiter()
    monkeypatch.setattr(auth_api, "settings", _rate_settings(max_sources=1, max_identities=1))
    assert await limiter.allow_source(action="login", source="source-one")
    assert await limiter.record_identity_failure(action="login", identity="one@example.com")
    limiter._prune_expired_buckets(now=float("inf"), window=60)

    assert await limiter.allow_source(action="login", source="source-two")
    assert await limiter.record_identity_failure(action="login", identity="two@example.com")
    assert len(limiter._sources) == 1
    assert len(limiter._identities) == 1


@pytest.mark.asyncio
async def test_auth_rate_limit_fails_closed_when_the_guard_is_unavailable(monkeypatch):
    async def unavailable(**_kwargs):
        raise RuntimeError("guard unavailable")

    monkeypatch.setattr(auth_api.auth_attempt_limiter, "allow_source", unavailable)
    request = Request({"type": "http", "client": ("198.51.100.18", 4567)})

    with pytest.raises(HTTPException) as exc_info:
        await auth_api._enforce_auth_rate_limit(action="signup", request=request)

    assert exc_info.value.status_code == 503


def test_secure_environments_require_auth_rate_limiting():
    with pytest.raises(ValidationError, match="BET_AUTH_RATE_LIMIT_ENABLED"):
        Settings(
            environment="staging",
            jwt_secret="x" * 32,
            cookie_secure=True,
            auth_rate_limit_enabled=False,
        )


class _SerializedSessionDb:
    def __init__(self, user, *, pause_refresh: bool = False, pause_logout: bool = False):
        self.user = user
        self.sessions = {"sid"}
        self.lock = asyncio.Lock()
        self.pause_refresh = pause_refresh
        self.pause_logout = pause_logout
        self.refresh_delete_started = asyncio.Event()
        self.logout_delete_started = asyncio.Event()
        self.release_delete = asyncio.Event()

    async def execute(self, statement):
        if getattr(statement, "is_select", False):
            await self.lock.acquire()
            return SimpleNamespace(scalar_one_or_none=lambda: self.user)
        sql = str(statement)
        is_refresh_delete = "session_id" in sql
        if is_refresh_delete:
            self.refresh_delete_started.set()
            if self.pause_refresh:
                await self.release_delete.wait()
            consumed = "sid" in self.sessions
            self.sessions.discard("sid")
            return SimpleNamespace(scalar_one_or_none=lambda: 1 if consumed else None)
        self.logout_delete_started.set()
        if self.pause_logout:
            await self.release_delete.wait()
        self.sessions.clear()
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def add(self, session):
        self.sessions.add(session.session_id)

    async def commit(self):
        if self.lock.locked():
            self.lock.release()


@pytest.mark.asyncio
async def test_refresh_then_logout_revokes_the_rotated_session_after_lock_interleaving():
    user = _auth_user(user_id=7)
    db = _SerializedSessionDb(user, pause_refresh=True)
    token = create_refresh_token(user.id, "sid")
    refresh_task = asyncio.create_task(auth_api.refresh_auth(Response(), token, db))
    await db.refresh_delete_started.wait()
    logout_task = asyncio.create_task(auth_api.logout(Response(), token, db))
    await asyncio.sleep(0)
    db.release_delete.set()
    await refresh_task
    await logout_task

    assert db.sessions == set()


@pytest.mark.asyncio
async def test_logout_then_refresh_cannot_create_a_new_session_after_lock_interleaving():
    user = _auth_user(user_id=7)
    db = _SerializedSessionDb(user, pause_logout=True)
    token = create_refresh_token(user.id, "sid")
    logout_task = asyncio.create_task(auth_api.logout(Response(), token, db))
    await db.logout_delete_started.wait()
    refresh_task = asyncio.create_task(auth_api.refresh_auth(Response(), token, db))
    await asyncio.sleep(0)
    db.release_delete.set()
    await logout_task
    with pytest.raises(HTTPException) as refresh_error:
        await refresh_task

    assert refresh_error.value.status_code == 401
    assert db.sessions == set()
