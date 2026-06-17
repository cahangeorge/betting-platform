from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import world_cup_pipeline


def test_recent_world_cup_seasons_uses_last_ten_years():
    seasons = world_cup_pipeline.recent_world_cup_seasons(
        10,
        today=datetime(2026, 6, 17, tzinfo=timezone.utc),
    )

    assert seasons == [2018, 2022]


def test_market_matching_accepts_prediction_aliases():
    assert world_cup_pipeline._market_matches("ou_2_5", "over_under_2_5:full_time")
    assert world_cup_pipeline._market_matches("1x2", "1x2:full_time")
    assert world_cup_pipeline._market_matches("btts", "btts:full_time")


def test_best_odds_for_selection_uses_matching_market_and_best_price():
    odds_entries = [
        SimpleNamespace(market="over_under_2_5:full_time", home_odds=1.91, draw_odds=None, away_odds=1.86, bookmaker="A"),
        SimpleNamespace(market="over_under_2_5:full_time", home_odds=1.95, draw_odds=None, away_odds=1.82, bookmaker="B"),
        SimpleNamespace(market="1x2:full_time", home_odds=2.0, draw_odds=3.2, away_odds=4.0, bookmaker="C"),
    ]

    odds, bookmaker = world_cup_pipeline._best_odds_for_selection("ou_2_5", "over", odds_entries)

    assert odds == 1.95
    assert bookmaker == "B"


def test_build_difficulty_ticket_tiers_creates_seven_top_lists():
    candidates = [
        {
            "match_id": index,
            "match": f"Team {index}A vs Team {index}B",
            "league": "World Cup",
            "kickoff": None,
            "market": "1x2",
            "selection": "home",
            "probability": 0.8 - index * 0.01,
            "odds": 1.4 + index * 0.05,
            "bookmaker": "Book",
            "model_types": ["PoissonGoalsModel"],
            "model_prediction_id": index,
            "expected_return_score": (0.8 - index * 0.01) * (1.4 + index * 0.05),
        }
        for index in range(1, 10)
    ]

    tiers = world_cup_pipeline._build_difficulty_ticket_tiers(candidates, per_tier_count=10)

    assert [tier["level"] for tier in tiers] == [1, 2, 3, 4, 5, 6, 7]
    assert len(tiers[0]["tickets"]) == 9
    assert len(tiers[6]["tickets"]) == 10
    assert tiers[0]["tickets"][0]["ticket_type"] == "single"
    assert tiers[6]["tickets"][0]["ticket_type"] == "accumulator"
    assert tiers[6]["tickets"][0]["leg_count"] == 7
    assert len({leg["match_id"] for leg in tiers[6]["tickets"][0]["legs"]}) == 7
