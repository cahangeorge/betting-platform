from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class FootballLeagueCatalog(Base):
    """A cached, validated football competition discovered outside the request path."""

    __tablename__ = "football_league_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    country_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    country_name: Mapped[str] = mapped_column(String(255), nullable=False)
    league_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="oddsharvester-discovery")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="available", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
