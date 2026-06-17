from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.catalog import CountryInfo, LeagueInfo

router = APIRouter()

CATALOG: list[CountryInfo] = [
    CountryInfo(
        country="Italy",
        leagues=[
            LeagueInfo(id="serie_a", name="Serie A", matches_count=380, scrape_slug="italy-serie-a"),
            LeagueInfo(id="serie_b", name="Serie B", matches_count=380, scrape_slug="italy-serie-b"),
        ],
    ),
    CountryInfo(
        country="England",
        leagues=[
            LeagueInfo(id="premier_league", name="Premier League", matches_count=380, scrape_slug="england-premier-league"),
            LeagueInfo(id="championship", name="Championship", matches_count=552, scrape_slug="england-championship"),
        ],
    ),
    CountryInfo(
        country="Spain",
        leagues=[
            LeagueInfo(id="la_liga", name="La Liga", matches_count=380, scrape_slug="spain-laliga"),
        ],
    ),
    CountryInfo(
        country="Germany",
        leagues=[
            LeagueInfo(id="bundesliga", name="Bundesliga", matches_count=306, scrape_slug="germany-bundesliga"),
        ],
    ),
    CountryInfo(
        country="France",
        leagues=[
            LeagueInfo(id="ligue_1", name="Ligue 1", matches_count=380, scrape_slug="france-ligue-1"),
        ],
    ),
    CountryInfo(
        country="Netherlands",
        leagues=[
            LeagueInfo(id="eredivisie", name="Eredivisie", matches_count=306, scrape_slug="eredivisie"),
        ],
    ),
    CountryInfo(
        country="Portugal",
        leagues=[
            LeagueInfo(id="primeira_liga", name="Primeira Liga", matches_count=306, scrape_slug="liga-portugal"),
        ],
    ),
    CountryInfo(
        country="Turkey",
        leagues=[
            LeagueInfo(id="super_lig", name="Süper Lig", matches_count=380, scrape_slug="turkey-super-lig"),
        ],
    ),
    CountryInfo(
        country="Greece",
        leagues=[
            LeagueInfo(id="super_league", name="Super League", matches_count=240, scrape_slug="greece-super-league"),
        ],
    ),
    CountryInfo(
        country="Belgium",
        leagues=[
            LeagueInfo(id="pro_league", name="Pro League", matches_count=340, scrape_slug="jupiler-pro-league"),
        ],
    ),
    CountryInfo(
        country="Scotland",
        leagues=[
            LeagueInfo(id="scottish_premiership", name="Scottish Premiership", matches_count=228, scrape_slug="scotland-premiership"),
        ],
    ),
    CountryInfo(
        country="Russia",
        leagues=[
            LeagueInfo(id="russian_premier", name="Russian Premier League", matches_count=240, scrape_slug="russia-premier-league"),
        ],
    ),
    CountryInfo(
        country="Brazil",
        leagues=[
            LeagueInfo(id="brasileirao", name="Brasileirão", matches_count=380, scrape_slug="brazil-serie-a"),
        ],
    ),
    CountryInfo(
        country="Argentina",
        leagues=[
            LeagueInfo(id="liga_profesional", name="Liga Profesional", matches_count=276, scrape_slug="argentina-liga-profesional"),
        ],
    ),
    CountryInfo(
        country="USA",
        leagues=[
            LeagueInfo(id="mls", name="MLS", matches_count=476, scrape_slug="usa-mls"),
        ],
    ),
    CountryInfo(
        country="Mexico",
        leagues=[
            LeagueInfo(id="liga_mx", name="Liga MX", matches_count=306, scrape_slug="mexico-liga-mx"),
        ],
    ),
    CountryInfo(
        country="Japan",
        leagues=[
            LeagueInfo(id="j1_league", name="J1 League", matches_count=306, scrape_slug="japan-j1-league"),
        ],
    ),
    CountryInfo(
        country="South Korea",
        leagues=[
            LeagueInfo(id="k_league_1", name="K League 1", matches_count=228, scrape_slug="south-korea-k-league-1"),
        ],
    ),
    CountryInfo(
        country="Saudi Arabia",
        leagues=[
            LeagueInfo(id="saudi_pro_league", name="Saudi Pro League", matches_count=306, scrape_slug="saudi-professional-league"),
        ],
    ),
    CountryInfo(
        country="Austria",
        leagues=[
            LeagueInfo(id="bundesliga_at", name="Bundesliga", matches_count=198, scrape_slug="austria-bundesliga"),
        ],
    ),
    CountryInfo(
        country="Switzerland",
        leagues=[
            LeagueInfo(id="super_league_ch", name="Super League", matches_count=198, scrape_slug="switzerland-super-league"),
        ],
    ),
    CountryInfo(
        country="Denmark",
        leagues=[
            LeagueInfo(id="superliga", name="Superliga", matches_count=198, scrape_slug="denmark-superliga"),
        ],
    ),
    CountryInfo(
        country="Sweden",
        leagues=[
            LeagueInfo(id="allsvenskan", name="Allsvenskan", matches_count=240, scrape_slug=None),
        ],
    ),
    CountryInfo(
        country="Norway",
        leagues=[
            LeagueInfo(id="eliteserien", name="Eliteserien", matches_count=240, scrape_slug=None),
        ],
    ),
    CountryInfo(
        country="Poland",
        leagues=[
            LeagueInfo(id="ekstraklasa", name="Ekstraklasa", matches_count=306, scrape_slug="poland-ekstraklasa"),
        ],
    ),
    CountryInfo(
        country="Czech Republic",
        leagues=[
            LeagueInfo(id="fortuna_liga", name="Fortuna Liga", matches_count=245, scrape_slug="czech-republic-chance-liga"),
        ],
    ),
    CountryInfo(
        country="Romania",
        leagues=[
            LeagueInfo(id="liga_1", name="Liga I", matches_count=306, scrape_slug="romania-superliga"),
        ],
    ),
    CountryInfo(
        country="Croatia",
        leagues=[
            LeagueInfo(id="hnl", name="HNL", matches_count=198, scrape_slug="croatia-hnl"),
        ],
    ),
    CountryInfo(
        country="World",
        leagues=[
            LeagueInfo(id="world_cup", name="World Cup", matches_count=64, scrape_slug="world-cup"),
        ],
    ),
]


@router.get("/countries", response_model=list[CountryInfo])
async def list_countries(
    _user: User = Depends(get_current_user),
):
    return CATALOG


@router.get("/leagues", response_model=list[LeagueInfo])
async def list_leagues(
    country: str | None = Query(None),
    _user: User = Depends(get_current_user),
):
    if country:
        for c in CATALOG:
            if c.country.lower() == country.lower():
                return c.leagues
        return []
    all_leagues = []
    for c in CATALOG:
        all_leagues.extend(c.leagues)
    return all_leagues


@router.get("/leagues/all", response_model=list[CountryInfo])
async def list_all_leagues(
    _user: User = Depends(get_current_user),
):
    return CATALOG
