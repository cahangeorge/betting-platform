import asyncio
import hashlib
import heapq
import json
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import Session, User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.services.auth import (
    create_access_token,
    create_refresh_session,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter()
settings = get_settings()


class AuthAuditJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "event": record.getMessage(),
            "action": getattr(record, "auth_action", "unknown"),
            "outcome": getattr(record, "auth_outcome", "unknown"),
        }
        user_id = getattr(record, "user_id", None)
        if user_id is not None:
            payload["user_id"] = user_id
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _configure_auth_audit_logger() -> logging.Logger:
    audit_logger = logging.getLogger("bet.auth.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    if not any(getattr(handler, "_bet_auth_audit_sink", False) for handler in audit_logger.handlers):
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(AuthAuditJsonFormatter())
        handler._bet_auth_audit_sink = True  # type: ignore[attr-defined]
        audit_logger.addHandler(handler)
    return audit_logger


logger = _configure_auth_audit_logger()


class AuthAttemptLimiter:
    """Bounded, per-process limiter with hashed identity and source bucket keys."""

    def __init__(self) -> None:
        self._identity_attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._source_attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._sources: dict[str, float] = {}
        self._identities: dict[str, float] = {}
        self._source_expiry: list[tuple[float, str]] = []
        self._identity_expiry: list[tuple[float, str]] = []
        self._lock = asyncio.Lock()

    @staticmethod
    def _bucket_key(*, kind: str, value: str) -> str:
        normalized = value.strip().casefold()
        return hashlib.sha256(f"{kind}:{normalized}".encode()).hexdigest()

    @staticmethod
    def _prune_attempts(attempts: deque[float], *, cutoff: float) -> None:
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

    @staticmethod
    def _touch(keys: dict[str, float], expiry: list[tuple[float, str]], *, key: str, now: float, window: int) -> None:
        keys[key] = now
        heapq.heappush(expiry, (now + window, key))

    def _prune_expired_buckets(self, *, now: float, window: int) -> None:
        cutoff = now - window
        for keys, expiry, attempts in (
            (self._sources, self._source_expiry, self._source_attempts),
            (self._identities, self._identity_expiry, self._identity_attempts),
        ):
            while expiry and expiry[0][0] <= now:
                _, key = heapq.heappop(expiry)
                if keys.get(key, now) > cutoff:
                    continue
                keys.pop(key, None)
                attempts.pop(("login", key), None)
                attempts.pop(("signup", key), None)

    async def allow_source(self, *, action: str, source: str) -> bool:
        current = settings
        if not current.auth_rate_limit_enabled:
            return True
        source_key = self._bucket_key(kind="source", value=source)
        now = time.monotonic()
        cutoff = now - current.auth_rate_limit_window_seconds
        async with self._lock:
            self._prune_expired_buckets(now=now, window=current.auth_rate_limit_window_seconds)
            if source_key not in self._sources and len(self._sources) >= current.auth_rate_limit_max_sources:
                return False
            if source_key not in self._sources:
                self._touch(
                    self._sources,
                    self._source_expiry,
                    key=source_key,
                    now=now,
                    window=current.auth_rate_limit_window_seconds,
                )
            attempts = self._source_attempts[(action, source_key)]
            self._prune_attempts(attempts, cutoff=cutoff)
            if len(attempts) >= current.auth_source_max_attempts:
                return False
            attempts.append(now)
            return True

    async def record_identity_failure(self, *, action: str, identity: str) -> bool:
        current = settings
        if not current.auth_rate_limit_enabled:
            return True
        identity_key = self._bucket_key(kind="identity", value=identity)
        maximum = current.auth_signup_max_attempts if action == "signup" else current.auth_login_max_attempts
        now = time.monotonic()
        cutoff = now - current.auth_rate_limit_window_seconds
        async with self._lock:
            self._prune_expired_buckets(now=now, window=current.auth_rate_limit_window_seconds)
            if identity_key not in self._identities and len(self._identities) >= current.auth_rate_limit_max_identities:
                return False
            if identity_key not in self._identities:
                self._touch(
                    self._identities,
                    self._identity_expiry,
                    key=identity_key,
                    now=now,
                    window=current.auth_rate_limit_window_seconds,
                )
            attempts = self._identity_attempts[(action, identity_key)]
            self._prune_attempts(attempts, cutoff=cutoff)
            if len(attempts) >= maximum:
                return False
            attempts.append(now)
            return True

    async def reset(self) -> None:
        async with self._lock:
            self._identity_attempts.clear()
            self._source_attempts.clear()
            self._sources.clear()
            self._identities.clear()
            self._source_expiry.clear()
            self._identity_expiry.clear()


auth_attempt_limiter = AuthAttemptLimiter()


def _log_rate_limit_unavailable(*, action: str) -> None:
    extra: dict[str, object] = {"auth_action": action}
    logger.exception("auth_rate_limit_unavailable", extra=extra)


def _audit_auth_event(*, action: str, outcome: str, user_id: int | None = None) -> None:
    extra: dict[str, object] = {"auth_action": action, "auth_outcome": outcome}
    if user_id is not None:
        extra["user_id"] = user_id
    logger.info("auth_audit", extra=extra)


async def _record_auth_failure(*, action: str, identity: str) -> None:
    try:
        recorded = await auth_attempt_limiter.record_identity_failure(action=action, identity=identity)
    except Exception:
        _log_rate_limit_unavailable(action=action)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication temporarily unavailable. Please try again later.",
        ) from None
    if recorded:
        return
    _audit_auth_event(action=action, outcome="rate_limited")
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many authentication attempts. Please try again later.",
        headers={"Retry-After": str(settings.auth_rate_limit_window_seconds)},
    )


def _request_source(request: Request) -> str:
    # Do not trust forwarding headers unless the deployment configures a trusted proxy.
    # This process-local key is never persisted or emitted in audit logs.
    return request.client.host if request.client else "unknown"


async def _enforce_auth_rate_limit(*, action: str, request: Request) -> None:
    try:
        allowed = await auth_attempt_limiter.allow_source(action=action, source=_request_source(request))
    except Exception:
        _log_rate_limit_unavailable(action=action)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication temporarily unavailable. Please try again later.",
        ) from None
    if allowed:
        return
    _audit_auth_event(action=action, outcome="rate_limited")
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many authentication attempts. Please try again later.",
        headers={"Retry-After": str(settings.auth_rate_limit_window_seconds)},
    )


def _set_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


def _refresh_auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await _enforce_auth_rate_limit(action="signup", request=request)
    result = await db.execute(select(User).where(User.email == body.email))
    existing = result.scalar_one_or_none()
    if existing:
        await _record_auth_failure(action="signup", identity=body.email)
        _audit_auth_event(action="signup", outcome="rejected")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(user.id, getattr(user, "session_version", 0))
    refresh_session = create_refresh_session(user.id)
    db.add(refresh_session)
    refresh_token = create_refresh_token(user.id, refresh_session.session_id)
    await db.commit()

    _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    _audit_auth_event(action="signup", outcome="succeeded", user_id=user.id)

    return TokenResponse(access_token=access_token)


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await _enforce_auth_rate_limit(action="login", request=request)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        await _record_auth_failure(action="login", identity=body.email)
        _audit_auth_event(action="login", outcome="rejected")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(user.id, getattr(user, "session_version", 0))
    refresh_session = create_refresh_session(user.id)
    db.add(refresh_session)
    refresh_token = create_refresh_token(user.id, refresh_session.session_id)
    await db.commit()

    _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    _audit_auth_event(action="login", outcome="succeeded", user_id=user.id)

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=UserResponse)
async def refresh_auth(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise _refresh_auth_error()

    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise _refresh_auth_error()
    try:
        user_id = int(payload["sub"])
        session_id = str(payload["sid"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _refresh_auth_error() from exc

    locked_user = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = locked_user.scalar_one_or_none()
    if user is None:
        raise _refresh_auth_error()

    consumed_session = await db.execute(
        delete(Session)
        .where(
            Session.session_id == session_id,
            Session.user_id == user_id,
            Session.expires_at > datetime.now(timezone.utc),
        )
        .returning(Session.id)
    )
    if consumed_session.scalar_one_or_none() is None:
        raise _refresh_auth_error()

    rotated_access_token = create_access_token(user.id, getattr(user, "session_version", 0))
    rotated_session = create_refresh_session(user.id)
    db.add(rotated_session)
    rotated_refresh_token = create_refresh_token(user.id, rotated_session.session_id)
    await db.commit()
    _set_auth_cookies(
        response,
        access_token=rotated_access_token,
        refresh_token=rotated_refresh_token,
    )
    return user


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(refresh_token) if refresh_token else None
    user_id = payload.get("sub") if payload and payload.get("type") == "refresh" else None
    if user_id is not None:
        try:
            parsed_user_id = int(user_id)
        except (TypeError, ValueError):
            parsed_user_id = None
        if parsed_user_id is not None:
            locked_user = await db.execute(select(User).where(User.id == parsed_user_id).with_for_update())
            user = locked_user.scalar_one_or_none()
            if user is not None:
                # Revoke every refresh session while holding the user-row lock so a
                # concurrent refresh cannot mint a new session after logout.
                user.session_version = getattr(user, "session_version", 0) + 1
                await db.execute(delete(Session).where(Session.user_id == parsed_user_id))
                await db.commit()
                from app.api.v1.live import manager

                await manager.revoke_user(parsed_user_id)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user
