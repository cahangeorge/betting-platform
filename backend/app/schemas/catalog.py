from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class LeagueInfo(BaseModel):
    id: str
    name: str
    matches_count: int = 0
    scrape_slug: str | None = None
    # Added fields are optional/defaulted to keep the original catalog contract
    # stable for clients that only consume id/name/scrape_slug.
    source: Literal["static", "discovered"] = "static"
    status: Literal["available", "validation_pending", "unavailable"] = "available"
    source_url: str | None = None
    last_seen_at: datetime | None = None


class CountryInfo(BaseModel):
    country: str
    leagues: list[LeagueInfo] = Field(default_factory=list)


class FootballLeagueDiscoveryInput(BaseModel):
    """A league previously discovered and URL-validated by an offline worker."""

    scrape_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    country_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    country_name: str = Field(min_length=1, max_length=255)
    league_name: str = Field(min_length=1, max_length=255)
    source_url: str = Field(min_length=1, max_length=2048)
    status: Literal["available", "validation_pending", "unavailable"] = "available"
    last_validated_at: datetime | None = None

    @field_validator("country_name", "league_name")
    @classmethod
    def require_non_blank_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_canonical_football_url(self) -> "FootballLeagueDiscoveryInput":
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or parsed.netloc not in {"oddsportal.com", "www.oddsportal.com"}:
            raise ValueError("source_url must be an HTTPS OddsPortal URL")
        if not parsed.path.startswith(f"/football/{self.country_slug}/"):
            raise ValueError("source_url must match country_slug")
        return self


class FootballCatalogRefreshRequest(BaseModel):
    """Validated discovery output; the API deliberately never scrapes live sources."""

    source: str = Field(default="oddsharvester-discovery", min_length=1, max_length=100)
    leagues: list[FootballLeagueDiscoveryInput] = Field(min_length=1, max_length=5000)
    complete_snapshot: bool = False

    @field_validator("source")
    @classmethod
    def require_non_blank_source(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_unique_slugs(self) -> "FootballCatalogRefreshRequest":
        slugs = [league.scrape_slug for league in self.leagues]
        if len(slugs) != len(set(slugs)):
            raise ValueError("leagues must not contain duplicate scrape_slug values")
        return self


class FootballCatalogRefreshResponse(BaseModel):
    created: int
    updated: int
    marked_unavailable: int
    refreshed_at: datetime
