from types import SimpleNamespace

from app.api.v1.predictions import _build_value_candidates


def _prediction(quality_report):
    odds = [SimpleNamespace(market="1x2:FullTime", home_odds=2.1, draw_odds=3.4, away_odds=4.0, bookmaker="Book")]
    match = SimpleNamespace(
        id=7,
        competition="World Cup",
        home_team="USA",
        away_team="Australia",
        match_date=None,
        odds=odds,
    )
    return SimpleNamespace(
        id=42,
        match=match,
        market="1x2",
        home_prob=0.62,
        draw_prob=0.23,
        away_prob=0.15,
        model_type="PoissonGoalsModel",
        quality_report=quality_report,
    )


def test_value_bets_exclude_unreliable_quality_reports_by_default():
    run = SimpleNamespace(
        model_type="PoissonGoalsModel",
        model_predictions=[
            _prediction({"reliability": {"is_ticket_eligible": False, "label": "unreliable", "block_reasons": ["market_disagreement"]}})
        ],
    )

    assert _build_value_candidates(run, min_edge=0, max_results=10) == []


def test_value_bets_can_include_unreliable_predictions_explicitly_for_debugging():
    run = SimpleNamespace(
        model_type="PoissonGoalsModel",
        model_predictions=[
            _prediction({"reliability": {"is_ticket_eligible": False, "label": "unreliable", "block_reasons": ["market_disagreement"]}})
        ],
    )

    items = _build_value_candidates(run, min_edge=0, max_results=10, include_unreliable=True)

    assert len(items) == 1
    assert items[0].reliability == "unreliable"
    assert items[0].quality_reasons == ["market_disagreement"]
