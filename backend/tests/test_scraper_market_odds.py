from datetime import datetime, timedelta, timezone

from app.services.scraper import _derive_match_status, _market_key_to_odds


def test_market_key_to_odds_accepts_oddsharvester_btts_keys():
    assert _market_key_to_odds("btts_market", {"odds_yes": "1.92", "odds_no": "1.88"}) == (1.92, None, 1.88)


def test_market_key_to_odds_accepts_oddsharvester_over_under_keys():
    assert _market_key_to_odds("over_under_2_5_market", {"odds_over": "1.91", "odds_under": "1.95"}) == (
        1.91,
        None,
        1.95,
    )


def test_future_match_with_placeholder_scores_stays_scheduled():
    status = _derive_match_status(
        {"home_score": "0", "away_score": "0"},
        datetime.now(timezone.utc) + timedelta(hours=2),
    )

    assert status == "scheduled"
