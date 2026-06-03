# Stats momentum test
***
* (already in smoke) 1-14 pass with bot running on port 8000

Manual curl check for stats endpoints:
  GET  /api/v1/stats/momentum/{match_id}
  GET  /api/v1/stats/history/{match_id}
  POST /api/v1/stats/ingest/{match_id}?source=opta&elapsed=35&xg_home=0.8&xg_away=0.3&possession_home=62&possession_away=38&shots_on_target_home=4&shots_on_target_away=2&dangerous_attacks_home=12&dangerous_attacks_away=5&cards_home=1&cards_away=2