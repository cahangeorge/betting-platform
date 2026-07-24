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
    status: Literal["available", "validation_pending", "validation_passed", "unavailable"] = "available"
    source_url: str | None = None
    last_seen_at: datetime | None = None
    scrape_capability: Literal["full", "upcoming"] = "full"


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


class FootballCatalogValidationRequest(BaseModel):
    country: str | None = Field(default=None, min_length=1, max_length=255)
    limit: int = Field(default=20, ge=1, le=25)


class FootballCatalogValidationOutcome(BaseModel):
    scrape_slug: str
    status: Literal["available", "validation_pending", "unavailable"]
    detail: str
    match_count: int = Field(default=0, ge=0)


class FootballCatalogValidationResponse(BaseModel):
    requested: int
    checked: int
    results_page_ok: int
    unavailable: int
    pending: int
    outcomes: list[FootballCatalogValidationOutcome] = Field(default_factory=list)


class FootballCatalogDiscoveryValidationRequest(BaseModel):
    """Run a bounded live discovery and validation workflow for selected countries."""

    countries: list[str] = Field(min_length=1, max_length=20)
    max_attempts: int = Field(default=3, ge=1, le=5)
    batch_size: int = Field(default=20, ge=1, le=25)

    @field_validator("countries")
    @classmethod
    def normalize_countries(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            country = value.strip()
            if not country:
                raise ValueError("countries must not contain blank values")
            key = country.casefold()
            if key not in seen:
                normalized.append(country)
                seen.add(key)
        if not normalized:
            raise ValueError("at least one country is required")
        return normalized


class FootballCatalogWorkflowAttempt(BaseModel):
    attempt: int = Field(ge=1)
    discovered: int = Field(ge=0)
    created: int = Field(ge=0)
    updated: int = Field(ge=0)
    checked: int = Field(ge=0)
    available: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    pending: int = Field(ge=0)


class FootballCatalogDiscoveryValidationResponse(BaseModel):
    countries: list[str]
    attempts_used: int = Field(ge=0)
    discovered: int = Field(ge=0)
    available: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    pending: int = Field(ge=0)
    stop_reason: Literal["all_validated", "attempt_limit", "no_candidates"]
    attempts: list[FootballCatalogWorkflowAttempt] = Field(default_factory=list)
