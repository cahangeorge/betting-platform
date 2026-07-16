from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
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
async def signup(body: SignupRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(user.id)
    refresh_session = create_refresh_session(user.id)
    db.add(refresh_session)
    refresh_token = create_refresh_token(user.id, refresh_session.session_id)
    await db.commit()

    _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)

    return TokenResponse(access_token=access_token)


@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(user.id)
    refresh_session = create_refresh_session(user.id)
    db.add(refresh_session)
    refresh_token = create_refresh_token(user.id, refresh_session.session_id)
    await db.commit()

    _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)

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

    user = await db.get(User, user_id)
    if user is None:
        raise _refresh_auth_error()

    rotated_access_token = create_access_token(user.id)
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
    session_id = payload.get("sid") if payload and payload.get("type") == "refresh" else None
    if session_id:
        await db.execute(delete(Session).where(Session.session_id == str(session_id)))
        await db.commit()
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user
