from pydantic import BaseModel


class LeagueInfo(BaseModel):
    id: str
    name: str
    matches_count: int = 0
    scrape_slug: str | None = None


class CountryInfo(BaseModel):
    country: str
    leagues: list[LeagueInfo] = []
