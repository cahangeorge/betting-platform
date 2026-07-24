from app.api.v1.catalog import CATALOG, FOOTBALL_LEAGUE_URLS


def _catalog_by_slug():
    return {league.scrape_slug: (country.country, league) for country in CATALOG for league in country.leagues}


def test_catalog_exposes_every_supported_odds_harvester_football_league():
    catalog = _catalog_by_slug()

    assert len(FOOTBALL_LEAGUE_URLS) == 95
    assert set(catalog) == set(FOOTBALL_LEAGUE_URLS)
    assert all(league.scrape_slug and league.name and country for country, league in catalog.values())


def test_catalog_derives_country_from_the_canonical_oddsportal_url():
    catalog = _catalog_by_slug()

    assert catalog["england-premier-league"][0] == "England"
    assert catalog["world-cup"][0] == "World"
    assert catalog["copa-libertadores"][0] == "South America"
    assert catalog["afc-champions-league"][0] == "Asia"
    assert catalog["concacaf-champions-cup"][0] == "North & Central America"
