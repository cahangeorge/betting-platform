from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.catalog import (
    CountryInfo,
    FootballCatalogDiscoveryValidationRequest,
    FootballCatalogDiscoveryValidationResponse,
    FootballCatalogRefreshRequest,
    FootballCatalogRefreshResponse,
    FootballCatalogValidationRequest,
    FootballCatalogValidationResponse,
    LeagueInfo,
)
from app.services.football_catalog import (
    discover_and_validate_football_catalog,
    load_football_catalog,
    refresh_football_catalog,
    validate_pending_football_catalog,
)
from app.services.python_bridge import BridgeError

router = APIRouter()

# Adapted from OddsHarvester's Sport.FOOTBALL league mapping.  Keep this data
# backend-local: the API must remain available when the scraper checkout is not
# mounted, while its `scrape_slug` remains the stable OddsHarvester CLI key.
FOOTBALL_LEAGUE_URLS: dict[str, str] = {
    "france-ligue-1": "https://www.oddsportal.com/football/france/ligue-1",
    "france-ligue-2": "https://www.oddsportal.com/football/france/ligue-2/",
    "france-coupe-de-france": "https://www.oddsportal.com/football/france/coupe-de-france",
    "germany-bundesliga": "https://www.oddsportal.com/football/germany/bundesliga",
    "germany-bundesliga-2": "https://www.oddsportal.com/football/germany/2-bundesliga/",
    "germany-dfb-pokal": "https://www.oddsportal.com/football/germany/dfb-pokal",
    "england-premier-league": "https://www.oddsportal.com/football/england/premier-league",
    "england-championship": "https://www.oddsportal.com/football/england/championship",
    "england-fa-cup": "https://www.oddsportal.com/football/england/fa-cup",
    "spain-laliga": "https://www.oddsportal.com/football/spain/laliga",
    "spain-laliga2": "https://www.oddsportal.com/football/spain/laliga2/",
    "spain-copa-del-rey": "https://www.oddsportal.com/football/spain/copa-del-rey",
    "italy-serie-a": "https://www.oddsportal.com/football/italy/serie-a",
    "italy-serie-b": "https://www.oddsportal.com/football/italy/serie-b/",
    "italy-coppa-italia": "https://www.oddsportal.com/football/italy/coppa-italia",
    "usa-mls": "https://www.oddsportal.com/football/usa/mls",
    "brazil-serie-a": "https://www.oddsportal.com/football/brazil/serie-a-betano",
    "brazil-serie-b": "https://www.oddsportal.com/football/brazil/serie-b/",
    "mexico-liga-mx": "https://www.oddsportal.com/football/mexico/liga-mx",
    "liga-portugal": "https://www.oddsportal.com/football/portugal/liga-portugal",
    "liga-portugal-2": "https://www.oddsportal.com/football/portugal/liga-portugal-2/",
    "eredivisie": "https://www.oddsportal.com/football/netherlands/eredivisie",
    "champions-league": "https://www.oddsportal.com/football/europe/champions-league",
    "europa-league": "https://www.oddsportal.com/football/europe/europa-league",
    "jupiler-pro-league": "https://www.oddsportal.com/football/belgium/jupiler-pro-league/",
    "denmark-superliga": "https://www.oddsportal.com/football/denmark/superliga/",
    "colombia-primera-a": "https://www.oddsportal.com/football/colombia/primera-a/",
    "austria-bundesliga": "https://www.oddsportal.com/football/austria/bundesliga/",
    "bulgaria-parva-liga": "https://www.oddsportal.com/football/bulgaria/efbet-league",
    "australia-a-league": "https://www.oddsportal.com/football/australia/a-league/",
    "greece-super-league": "https://www.oddsportal.com/football/greece/super-league/",
    "romania-superliga": "https://www.oddsportal.com/football/romania/superliga/",
    "saudi-professional-league": "https://www.oddsportal.com/football/saudi-arabia/saudi-professional-league/",
    "scotland-premiership": "https://www.oddsportal.com/football/scotland/premiership/",
    "switzerland-super-league": "https://www.oddsportal.com/football/switzerland/super-league/",
    "turkey-super-lig": "https://www.oddsportal.com/football/turkey/super-lig/",
    "world-cup": "https://www.oddsportal.com/football/world/world-championship-2026/",
    "croatia-hnl": "https://www.oddsportal.com/football/croatia/hnl/",
    "czech-republic-chance-liga": "https://www.oddsportal.com/football/czech-republic/chance-liga/",
    "slovakia-nike-liga": "https://www.oddsportal.com/football/slovakia/nike-liga/",
    "hungary-nb-i": "https://www.oddsportal.com/football/hungary/nb-i/",
    "serbia-super-liga": "https://www.oddsportal.com/football/serbia/mozzart-bet-super-liga/",
    "ukraine-premier-league": "https://www.oddsportal.com/football/ukraine/premier-league/",
    "belarus-vysshaya-liga": "https://www.oddsportal.com/football/belarus/vysshaya-liga/",
    "ireland-premier-division": "https://www.oddsportal.com/football/ireland/premier-division/",
    "japan-j1-league": "https://www.oddsportal.com/football/japan/j1-league/",
    "japan-j2-j3-league": "https://www.oddsportal.com/football/japan/j2-j3-league/",
    "argentina-liga-profesional": "https://www.oddsportal.com/football/argentina/liga-profesional/",
    "conference-league": "https://www.oddsportal.com/football/europe/conference-league/",
    "poland-ekstraklasa": "https://www.oddsportal.com/football/poland/ekstraklasa/",
    "finland-veikkausliiga": "https://www.oddsportal.com/football/finland/veikkausliiga/",
    "copa-sudamericana": "https://www.oddsportal.com/football/south-america/copa-sudamericana",
    "copa-libertadores": "https://www.oddsportal.com/football/south-america/copa-libertadores",
    "morocco-botola-pro": "https://www.oddsportal.com/football/morocco/botola-pro",
    "egypt-premier-league": "https://www.oddsportal.com/football/egypt/premier-league",
    "peru-liga-1": "https://www.oddsportal.com/football/peru/liga-1",
    "chile-primera-division": "https://www.oddsportal.com/football/chile/primera-division",
    "south-korea-k-league-1": "https://www.oddsportal.com/football/south-korea/k-league-1",
    "china-super-league": "https://www.oddsportal.com/football/china/super-league",
    "russia-premier-league": "https://www.oddsportal.com/football/russia/premier-league",
    "india-isl": "https://www.oddsportal.com/football/india/isl",
    "south-africa-premiership": "https://www.oddsportal.com/football/south-africa/betway-premiership",
    "uruguay-liga": "https://www.oddsportal.com/football/uruguay/liga-auf-uruguaya",
    "ecuador-liga-pro": "https://www.oddsportal.com/football/ecuador/liga-pro",
    "paraguay-copa-de-primera": "https://www.oddsportal.com/football/paraguay/copa-de-primera",
    "costa-rica-primera-division": "https://www.oddsportal.com/football/costa-rica/primera-division",
    "thailand-thai-league-1": "https://www.oddsportal.com/football/thailand/thai-league-1",
    "qatar-qsl": "https://www.oddsportal.com/football/qatar/qsl",
    "uae-league": "https://www.oddsportal.com/football/united-arab-emirates/uae-league",
    "uzbekistan-super-league": "https://www.oddsportal.com/football/uzbekistan/super-league",
    "indonesia-super-league": "https://www.oddsportal.com/football/indonesia/super-league",
    "wales-cymru-premier": "https://www.oddsportal.com/football/wales/cymru-premier",
    "northern-ireland-nifl-premiership": "https://www.oddsportal.com/football/northern-ireland/nifl-premiership",
    "estonia-meistriliiga": "https://www.oddsportal.com/football/estonia/meistriliiga",
    "algeria-ligue-1": "https://www.oddsportal.com/football/algeria/ligue-1",
    "england-league-one": "https://www.oddsportal.com/football/england/league-one",
    "england-league-two": "https://www.oddsportal.com/football/england/league-two",
    "england-national-league": "https://www.oddsportal.com/football/england/national-league",
    "germany-3-liga": "https://www.oddsportal.com/football/germany/3-liga",
    "france-national": "https://www.oddsportal.com/football/france/national",
    "netherlands-eerste-divisie": "https://www.oddsportal.com/football/netherlands/eerste-divisie",
    "belgium-challenger-pro-league": "https://www.oddsportal.com/football/belgium/challenger-pro-league",
    "turkey-1-lig": "https://www.oddsportal.com/football/turkey/1-lig",
    "scotland-championship": "https://www.oddsportal.com/football/scotland/championship",
    "romania-liga-2": "https://www.oddsportal.com/football/romania/liga-2",
    "denmark-1st-division": "https://www.oddsportal.com/football/denmark/1st-division",
    "greece-super-league-2": "https://www.oddsportal.com/football/greece/super-league-2",
    "austria-2-liga": "https://www.oddsportal.com/football/austria/2-liga",
    "switzerland-challenge-league": "https://www.oddsportal.com/football/switzerland/challenge-league",
    "argentina-primera-nacional": "https://www.oddsportal.com/football/argentina/primera-nacional",
    "usa-usl-championship": "https://www.oddsportal.com/football/usa/usl-championship",
    "mexico-liga-de-expansion": "https://www.oddsportal.com/football/mexico/liga-de-expansion-mx",
    "concacaf-champions-cup": "https://www.oddsportal.com/football/north-central-america/concacaf-champions-cup",
    "afc-champions-league": "https://www.oddsportal.com/football/asia/afc-champions-league",
    "uefa-nations-league": "https://www.oddsportal.com/football/europe/uefa-nations-league",
}

COUNTRY_NAMES = {
    "czech-republic": "Czech Republic",
    "north-central-america": "North & Central America",
    "south-africa": "South Africa",
    "south-america": "South America",
    "south-korea": "South Korea",
    "saudi-arabia": "Saudi Arabia",
    "united-arab-emirates": "United Arab Emirates",
    "usa": "USA",
}

# Preserve the existing public identifiers and high-visibility display names.
LEGACY_IDS = {
    "italy-serie-a": "serie_a",
    "italy-serie-b": "serie_b",
    "england-premier-league": "premier_league",
    "england-championship": "championship",
    "spain-laliga": "la_liga",
    "germany-bundesliga": "bundesliga",
    "france-ligue-1": "ligue_1",
    "eredivisie": "eredivisie",
    "liga-portugal": "primeira_liga",
    "turkey-super-lig": "super_lig",
    "greece-super-league": "super_league",
    "jupiler-pro-league": "pro_league",
    "scotland-premiership": "scottish_premiership",
    "russia-premier-league": "russian_premier",
    "brazil-serie-a": "brasileirao",
    "argentina-liga-profesional": "liga_profesional",
    "usa-mls": "mls",
    "mexico-liga-mx": "liga_mx",
    "japan-j1-league": "j1_league",
    "south-korea-k-league-1": "k_league_1",
    "saudi-professional-league": "saudi_pro_league",
    "austria-bundesliga": "bundesliga_at",
    "switzerland-super-league": "super_league_ch",
    "denmark-superliga": "superliga",
    "poland-ekstraklasa": "ekstraklasa",
    "czech-republic-chance-liga": "fortuna_liga",
    "romania-superliga": "liga_1",
    "croatia-hnl": "hnl",
    "world-cup": "world_cup",
}

DISPLAY_NAMES = {
    "spain-laliga": "La Liga",
    "spain-laliga2": "La Liga 2",
    "usa-mls": "MLS",
    "brazil-serie-a": "Brasileirão",
    "liga-portugal": "Primeira Liga",
    "liga-portugal-2": "Liga Portugal 2",
    "jupiler-pro-league": "Pro League",
    "scotland-premiership": "Scottish Premiership",
    "russia-premier-league": "Russian Premier League",
    "saudi-professional-league": "Saudi Pro League",
    "turkey-super-lig": "Süper Lig",
    "world-cup": "World Cup",
    "czech-republic-chance-liga": "Chance Liga",
    "japan-j1-league": "J1 League",
    "japan-j2-j3-league": "J2/J3 League",
    "south-korea-k-league-1": "K League 1",
    "hungary-nb-i": "NB I",
    "india-isl": "Indian Super League",
    "qatar-qsl": "Qatar Stars League",
    "uae-league": "UAE League",
    "northern-ireland-nifl-premiership": "NIFL Premiership",
    "afc-champions-league": "AFC Champions League",
    "uefa-nations-league": "UEFA Nations League",
    "concacaf-champions-cup": "CONCACAF Champions Cup",
    "germany-dfb-pokal": "DFB-Pokal",
}


def _display_name(slug: str, country_slug: str) -> str:
    if slug in DISPLAY_NAMES:
        return DISPLAY_NAMES[slug]
    prefix = f"{country_slug}-"
    league = slug.removeprefix(prefix)
    return league.replace("-", " ").title()


def _build_catalog() -> list[CountryInfo]:
    by_country: dict[str, list[LeagueInfo]] = defaultdict(list)
    for slug, url in FOOTBALL_LEAGUE_URLS.items():
        country_slug = url.rstrip("/").split("/")[-2]
        country = COUNTRY_NAMES.get(country_slug, country_slug.replace("-", " ").title())
        by_country[country].append(
            LeagueInfo(
                id=LEGACY_IDS.get(slug, slug.replace("-", "_")),
                name=_display_name(slug, country_slug),
                scrape_slug=slug,
            )
        )
    return [CountryInfo(country=country, leagues=leagues) for country, leagues in by_country.items()]


CATALOG = _build_catalog()


@router.get("/countries", response_model=list[CountryInfo])
async def list_countries(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await load_football_catalog(db, CATALOG)


@router.get("/leagues", response_model=list[LeagueInfo])
async def list_leagues(
    country: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    catalog = await load_football_catalog(db, CATALOG)
    if country:
        for item in catalog:
            if item.country.lower() == country.lower():
                return item.leagues
        return []
    return [league for item in catalog for league in item.leagues]


@router.get("/leagues/all", response_model=list[CountryInfo])
async def list_all_leagues(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await load_football_catalog(db, CATALOG)


@router.post("/football/refresh", response_model=FootballCatalogRefreshResponse)
async def refresh_football_catalog_cache(
    body: FootballCatalogRefreshRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Persist an already validated discovery payload; this endpoint never contacts OddsPortal."""
    return await refresh_football_catalog(db, body)


@router.post("/football/validate", response_model=FootballCatalogValidationResponse)
async def validate_pending_football_catalog_candidates(
    body: FootballCatalogValidationRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Validate a small, rate-limited pending batch against rendered Results pages."""
    try:
        return await validate_pending_football_catalog(db, country=body.country, limit=body.limit)
    except BridgeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post(
    "/football/discover-validate",
    response_model=FootballCatalogDiscoveryValidationResponse,
)
async def discover_and_validate_football_catalog_candidates(
    body: FootballCatalogDiscoveryValidationRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Discover selected countries and retry validation within the requested attempt limit."""
    try:
        return await discover_and_validate_football_catalog(db, body)
    except BridgeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
