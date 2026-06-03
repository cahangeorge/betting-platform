"""User and Session models."""
from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="users")
    bankrolls: Mapped[list["Bankroll"]] = relationship("Bankroll", back_populates="user")
    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="user")


class Session(Base):
    __tablename__ = "session"

    user_id: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="sessions")