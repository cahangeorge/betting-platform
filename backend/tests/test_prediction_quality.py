from types import SimpleNamespace

from app.services.prediction_quality import (
    build_market_consensus,
    evaluate_prediction_quality,
    team_training_stats,
)


def _match(home, away, home_score, away_score):
    return SimpleNamespace(
        home_team=home,
        away_team=away,
        home_score=home_score,
        away_score=away_score,
    )


def _odds(market, home, draw, away, bookmaker):
    return SimpleNamespace(
        market=market,
        home_odds=home,
        draw_odds=draw,
        away_odds=away,
        bookmaker=bookmaker,
    )


def test_team_training_stats_are_perspective_aware():
    training = [
        _match("USA", "England", 0, 0),
        _match("Iran", "USA", 0, 1),
        _match("Netherlands", "USA", 3, 1),
    ]

    stats = team_training_stats(training, "USA")

    assert stats == {"matches": 3, "wins": 1, "draws": 1, "losses": 1, "goals_for": 2, "goals_against": 3}


def test_build_market_consensus_accepts_oddsharvester_full_time_markets_and_best_prices():
    odds_entries = [
        _odds("1x2:FullTime", 1.57, 4.2, 5.4, "Fortuna.ro"),
        _odds("1x2:FullTime", 1.72, 3.9, 5.6, "Betano.ro"),
        _odds("btts:FullTime", 1.9, None, 1.8, "Other"),
    ]

    consensus = build_market_consensus(
        "1x2",
        odds_entries,
        implied_probabilities={"home": 0.58, "draw": 0.25, "away": 0.17},
    )

    assert consensus["odds"]["home"] == {"odds": 1.72, "bookmaker": "Betano.ro"}
    assert consensus["odds"]["away"] == {"odds": 5.6, "bookmaker": "Betano.ro"}
    assert consensus["pick"] == "home"


def test_sparse_team_history_and_market_disagreement_blocks_ticket_eligibility():
    training = [
        _match("England", "USA", 0, 0),
        _match("Iran", "USA", 0, 1),
        _match("Netherlands", "USA", 3, 1),
        _match("Tunisia", "Australia", 0, 1),
        _match("Australia", "Denmark", 1, 0),
        _match("Argentina", "Australia", 2, 1),
    ]
    target = SimpleNamespace(home_team="USA", away_team="Australia")
    model_probabilities = {"home": 0.22, "draw": 0.172, "away": 0.606}
    market_consensus = {
        "pick": "home",
        "probabilities": {"home": 0.58, "draw": 0.25, "away": 0.17},
        "odds": {
            "home": {"odds": 1.72, "bookmaker": "Betano.ro"},
            "draw": {"odds": 4.55, "bookmaker": "Book"},
            "away": {"odds": 5.6, "bookmaker": "Betano.ro"},
        },
    }

    report = evaluate_prediction_quality(
        training_matches=training,
        target_match=target,
        market="1x2",
        model_probabilities=model_probabilities,
        market_consensus=market_consensus,
    )

    assert report["model"]["pick"] == "away"
    assert report["market"]["pick"] == "home"
    assert report["training"]["home_team"]["matches"] == 3
    assert report["training"]["away_team"]["matches"] == 3
    assert report["reliability"]["label"] == "unreliable"
    assert report["reliability"]["is_ticket_eligible"] is False
    assert "insufficient_home_team_history" in report["reliability"]["block_reasons"]
    assert "market_disagreement" in report["reliability"]["block_reasons"]


def test_sufficient_history_market_alignment_and_positive_ev_is_ticket_eligible():
    training = []
    for index in range(25):
        training.append(_match("USA", f"Team {index}", 2, 0))
        training.append(_match(f"Other {index}", "Australia", 1, 1))
    target = SimpleNamespace(home_team="USA", away_team="Australia")

    report = evaluate_prediction_quality(
        training_matches=training,
        target_match=target,
        market="1x2",
        model_probabilities={"home": 0.62, "draw": 0.23, "away": 0.15},
        market_consensus={
            "pick": "home",
            "probabilities": {"home": 0.57, "draw": 0.25, "away": 0.18},
            "odds": {"home": {"odds": 1.85, "bookmaker": "Book"}},
        },
    )

    assert report["reliability"]["label"] == "reliable"
    assert report["reliability"]["is_ticket_eligible"] is True
    assert report["edge"]["home"] > 0


def test_low_edge_blocks_ticket_without_marking_prediction_unreliable():
    training = []
    for index in range(25):
        training.append(_match("USA", f"Team {index}", 2, 0))
        training.append(_match(f"Other {index}", "Australia", 1, 1))
    target = SimpleNamespace(home_team="USA", away_team="Australia")

    report = evaluate_prediction_quality(
        training_matches=training,
        target_match=target,
        market="1x2",
        model_probabilities={"home": 0.55, "draw": 0.27, "away": 0.18},
        market_consensus={
            "pick": "home",
            "probabilities": {"home": 0.55, "draw": 0.27, "away": 0.18},
            "odds": {"home": {"odds": 1.8, "bookmaker": "Book"}},
        },
    )

    assert report["reliability"]["label"] == "reliable"
    assert report["reliability"]["is_ticket_eligible"] is False
    assert report["reliability"]["block_reasons"] == ["edge_below_ticket_threshold"]
