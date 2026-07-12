# ruff: noqa
# Kept mechanically aligned with the legacy subprocess contract; refactor separately.
import argparse
import json
import os
import signal
import sys
import traceback
from pathlib import Path

# The tls_requests native library (tls-client-xgo) sends SIGINT to its own
# process group on load.  When this script runs as a child of Node/Vite the
# signal would propagate and kill the parent dev-server.  Creating a new
# session (setsid) isolates this process group completely, and ignoring
# SIGINT prevents self-termination from the stray signal.
try:
    os.setsid()
except OSError:
    pass  # already a session leader
signal.signal(signal.SIGINT, signal.SIG_IGN)


def serialize_value(value):
    try:
        if value != value:
            return None
    except Exception:
        pass

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)


def serialize_records(records):
    return [
        {key: serialize_value(value) for key, value in record.items()}
        for record in records
    ]


def load_soccerdata_paths():
    configured_root = os.environ.get("BET_SOCCERDATA_ROOT")
    if not configured_root:
        raise RuntimeError("BET_SOCCERDATA_ROOT must point to the soccerdata checkout")

    soccerdata_root = Path(configured_root).expanduser().resolve()
    if not soccerdata_root.is_dir():
        raise RuntimeError(f"BET_SOCCERDATA_ROOT does not exist: {soccerdata_root}")

    os.environ.setdefault("SOCCERDATA_LOGLEVEL", "ERROR")
    os.environ.setdefault("SOCCERDATA_DIR", str(Path.home() / ".cache" / "soccerdata"))

    sys.path.insert(0, str(soccerdata_root))
    return soccerdata_root


def get_catalog():
    from soccerdata._config import LEAGUE_DICT

    espn_leagues = []
    clubelo_leagues = []
    matchhistory_leagues = []
    fbref_leagues = []
    sofascore_leagues = []

    for league, mapping in sorted(LEAGUE_DICT.items()):
        if "ESPN" in mapping:
            espn_leagues.append(
                {
                    "label": league,
                    "value": league,
                    "sourceId": mapping["ESPN"],
                }
            )
        if "ClubElo" in mapping:
            clubelo_leagues.append(
                {
                    "label": league,
                    "value": league,
                }
            )
        if "MatchHistory" in mapping:
            matchhistory_leagues.append(
                {
                    "label": league,
                    "value": league,
                    "sourceId": mapping["MatchHistory"],
                }
            )
        if "FBref" in mapping:
            fbref_leagues.append(
                {
                    "label": league,
                    "value": league,
                    "sourceId": mapping["FBref"],
                }
            )
        if "Sofascore" in mapping:
            sofascore_leagues.append(
                {
                    "label": league,
                    "value": league,
                    "sourceId": mapping["Sofascore"],
                }
            )

    understat_leagues = []
    sofifa_leagues = []
    whoscored_leagues = []
    for league, mapping in sorted(LEAGUE_DICT.items()):
        if "Understat" in mapping:
            understat_leagues.append(
                {
                    "label": league,
                    "value": league,
                }
            )
        if "SoFIFA" in mapping:
            sofifa_leagues.append(
                {
                    "label": league,
                    "value": league,
                }
            )
        if "WhoScored" in mapping:
            whoscored_leagues.append(
                {
                    "label": league,
                    "value": league,
                    "sourceId": mapping["WhoScored"],
                }
            )

    return {
        "espnLeagues": espn_leagues,
        "clubEloLeagues": clubelo_leagues,
        "matchHistoryLeagues": matchhistory_leagues,
        "fbrefLeagues": fbref_leagues,
        "sofascoreLeagues": sofascore_leagues,
        "understatLeagues": understat_leagues,
        "sofifaLeagues": sofifa_leagues,
        "whoscoredLeagues": whoscored_leagues,
    }


def _set_fbref_headers():
    from soccerdata import fbref as fbref_module

    fbref_module.FBREF_HEADERS.update(
        {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        }
    )


def _reader_kwargs(payload):
    """Extract common reader constructor kwargs (proxy, no_cache, no_store) from payload."""
    kwargs = {
        "no_cache": bool(payload.get("refresh", False)),
        "no_store": bool(payload.get("no_store", False)),
    }
    proxy = payload.get("proxy")
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


def get_team_mapping(_payload):
    """Read the teamname_replacements.json config file."""
    from soccerdata._config import CONFIG_DIR
    import json as _json
    f = CONFIG_DIR / "teamname_replacements.json"
    if f.is_file():
        with f.open(encoding="utf8") as fh:
            return {"mappings": _json.load(fh)}
    return {"mappings": {}}


def set_team_mapping(payload):
    """Write the teamname_replacements.json config file."""
    from soccerdata._config import CONFIG_DIR
    import json as _json
    f = CONFIG_DIR / "teamname_replacements.json"
    mappings = payload.get("mappings", {})
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("w", encoding="utf8") as fh:
        _json.dump(mappings, fh, indent=2, ensure_ascii=False)
    return {"ok": True, "path": str(f)}


def _flatten_columns(df):
    """Flatten multi-level column names into single-level dot-separated strings."""
    if any(isinstance(c, tuple) for c in df.columns):
        df.columns = [
            "_".join(str(p) for p in col if str(p) and str(p) != "nan").strip("_")
            if isinstance(col, tuple)
            else str(col)
            for col in df.columns
        ]
    return df


def get_espn_schedule(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    limit = int(payload.get("limit", 20))
    refresh = bool(payload.get("refresh", False))

    reader = sd.ESPN(
        leagues=league,
        seasons=season,
        **_reader_kwargs(payload),
    )
    df = reader.read_schedule(force_cache=not refresh).reset_index()
    df = df.sort_values("date", ascending=True).head(limit)

    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append(
            {
                "league": record.get("league"),
                "season": record.get("season"),
                "game": record.get("game"),
                "date": record.get("date"),
                "homeTeam": record.get("home_team"),
                "awayTeam": record.get("away_team"),
                "gameId": record.get("game_id"),
                "leagueId": record.get("league_id"),
            }
        )

    return {
        "rows": rows,
        "summary": {
            "league": league,
            "season": season,
            "count": len(rows),
            "source": "ESPN",
            "refresh": refresh,
        },
    }


def get_clubelo_ratings(payload):
    import soccerdata as sd

    date = payload["date"]
    league = payload.get("league")
    limit = int(payload.get("limit", 20))
    refresh = bool(payload.get("refresh", False))

    reader = sd.ClubElo(**_reader_kwargs(payload))
    df = reader.read_by_date(date).reset_index()

    if league:
        df = df[df["league"] == league]

    df = df.sort_values(["rank", "elo"], ascending=[True, False]).head(limit)

    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append(
            {
                "team": record.get("team"),
                "rank": record.get("rank"),
                "elo": record.get("elo"),
                "league": record.get("league"),
                "country": record.get("country"),
                "from": record.get("from"),
                "to": record.get("to"),
            }
        )

    return {
        "rows": rows,
        "summary": {
            "date": date,
            "league": league,
            "count": len(rows),
            "source": "ClubElo",
            "refresh": refresh,
        },
    }


def get_matchhistory_games(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    limit = int(payload.get("limit", 20))
    refresh = bool(payload.get("refresh", False))

    reader = sd.MatchHistory(
        leagues=league,
        seasons=season,
        **_reader_kwargs(payload),
    )
    df = reader.read_games().reset_index()
    df = df.sort_values("date", ascending=False).head(limit)

    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append(
            {
                "league": record.get("league"),
                "season": record.get("season"),
                "game": record.get("game"),
                "date": record.get("date"),
                "homeTeam": record.get("home_team"),
                "awayTeam": record.get("away_team"),
                "homeGoals": record.get("FTHG"),
                "awayGoals": record.get("FTAG"),
                "result": record.get("FTR"),
            }
        )

    return {
        "rows": rows,
        "summary": {
            "league": league,
            "season": season,
            "count": len(rows),
            "source": "MatchHistory",
            "refresh": refresh,
        },
    }


def get_fbref_schedule(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    limit = int(payload.get("limit", 20))
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(
        leagues=league,
        seasons=season,
        **_reader_kwargs(payload),
    )
    df = reader.read_schedule(force_cache=not refresh).reset_index()
    df = df.sort_values("date", ascending=False).head(limit)

    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append(
            {
                "league": record.get("league"),
                "season": record.get("season"),
                "game": record.get("game"),
                "date": record.get("date"),
                "time": record.get("time"),
                "homeTeam": record.get("home_team"),
                "awayTeam": record.get("away_team"),
                "score": record.get("score"),
                "venue": record.get("venue"),
                "week": record.get("week"),
                "attendance": record.get("attendance"),
                "homeXg": record.get("home_xg"),
                "awayXg": record.get("away_xg"),
            }
        )

    return {
        "rows": rows,
        "summary": {
            "league": league,
            "season": season,
            "count": len(rows),
            "source": "FBref",
            "refresh": refresh,
        },
    }


def get_fbref_team_stats(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    stat_type = payload.get("stat_type", "standard")
    limit = int(payload.get("limit", 40))
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(
        leagues=league,
        seasons=season,
        **_reader_kwargs(payload),
    )
    df = reader.read_team_season_stats(stat_type=stat_type).reset_index()
    df = _flatten_columns(df)
    df = df.head(limit)

    rows = serialize_records(df.to_dict(orient="records"))
    columns = list(df.columns)

    return {
        "rows": rows,
        "columns": columns,
        "summary": {
            "league": league,
            "season": season,
            "statType": stat_type,
            "count": len(rows),
            "source": "FBref",
            "refresh": refresh,
        },
    }


def get_clubelo_team_history(payload):
    import soccerdata as sd

    team = payload["team"]
    limit = int(payload.get("limit", 50))
    refresh = bool(payload.get("refresh", False))

    reader = sd.ClubElo(**_reader_kwargs(payload))
    df = reader.read_team_history(team).reset_index()
    df = df.sort_values("from", ascending=False).head(limit)

    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append(
            {
                "date": record.get("from"),
                "team": record.get("team"),
                "elo": record.get("elo"),
                "rank": record.get("rank"),
                "league": record.get("league"),
                "country": record.get("country"),
            }
        )

    return {
        "rows": rows,
        "summary": {
            "team": team,
            "count": len(rows),
            "source": "ClubElo",
            "refresh": refresh,
        },
    }


def get_sofascore_standings(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    refresh = bool(payload.get("refresh", False))

    reader = sd.Sofascore(
        leagues=league,
        seasons=season,
        **_reader_kwargs(payload),
    )
    df = reader.read_league_table(force_cache=not refresh).reset_index()

    rows = []
    for i, record in enumerate(serialize_records(df.to_dict(orient="records")), start=1):
        rows.append(
            {
                "pos": i,
                "team": record.get("team"),
                "mp": record.get("MP"),
                "won": record.get("W"),
                "drawn": record.get("D"),
                "lost": record.get("L"),
                "gf": record.get("GF"),
                "ga": record.get("GA"),
                "gd": record.get("GD"),
                "pts": record.get("Pts"),
            }
        )

    return {
        "rows": rows,
        "summary": {
            "league": league,
            "season": season,
            "count": len(rows),
            "source": "Sofascore",
            "refresh": refresh,
        },
    }


def get_fbref_shot_events(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    game_id = payload.get("game_id")
    limit = int(payload.get("limit", 100))
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(
        leagues=league,
        seasons=season,
        **_reader_kwargs(payload),
    )

    match_ids = [game_id] if game_id else None
    df = reader.read_shot_events(match_id=match_ids, force_cache=not refresh)

    if df.empty:
        return {
            "rows": [],
            "summary": {
                "league": league,
                "season": season,
                "gameId": game_id,
                "count": 0,
                "source": "FBref",
                "refresh": refresh,
            },
        }

    df = df.reset_index().head(limit)

    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append(
            {
                "game": record.get("game"),
                "date": record.get("date"),
                "team": record.get("team"),
                "player": record.get("player"),
                "minute": record.get("minute"),
                "xg": record.get("xg"),
                "psxg": record.get("psxg"),
                "outcome": record.get("outcome"),
                "distance": record.get("distance"),
                "bodyPart": record.get("body_part"),
                "notes": record.get("notes"),
            }
        )

    return {
        "rows": rows,
        "summary": {
            "league": league,
            "season": season,
            "gameId": game_id,
            "count": len(rows),
            "source": "FBref",
            "refresh": refresh,
        },
    }


def get_sofascore_schedule(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    refresh = bool(payload.get("refresh", False))

    reader = sd.Sofascore(leagues=[league], seasons=[season])
    df = reader.read_schedule(force_cache=not refresh)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "count": 0, "source": "Sofascore"}}

    df = df.reset_index()
    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append({
            "game": record.get("game"),
            "date": record.get("date"),
            "homeTeam": record.get("home_team"),
            "awayTeam": record.get("away_team"),
            "homeScore": record.get("home_score"),
            "awayScore": record.get("away_score"),
            "status": record.get("status"),
            "round": record.get("round"),
        })
    return {"rows": rows, "summary": {"league": league, "season": season, "count": len(rows), "source": "Sofascore"}}


def get_understat_schedule(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    refresh = bool(payload.get("refresh", False))

    reader = sd.Understat(leagues=[league], seasons=[season])
    df = reader.read_schedule(include_matches_without_data=True, force_cache=not refresh)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "count": 0, "source": "Understat"}}

    df = df.reset_index()
    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append({
            "game": record.get("game"),
            "gameId": record.get("game_id"),
            "date": record.get("date"),
            "homeTeam": record.get("home_team"),
            "awayTeam": record.get("away_team"),
            "homeGoals": record.get("home_goals"),
            "awayGoals": record.get("away_goals"),
            "homeXg": record.get("home_xg"),
            "awayXg": record.get("away_xg"),
            "isResult": record.get("is_result"),
        })
    return {"rows": rows, "summary": {"league": league, "season": season, "count": len(rows), "source": "Understat"}}


def get_understat_team_match_stats(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    refresh = bool(payload.get("refresh", False))

    reader = sd.Understat(leagues=[league], seasons=[season])
    df = reader.read_team_match_stats(force_cache=not refresh)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "count": 0, "source": "Understat"}}

    df = _flatten_columns(df.reset_index())
    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append({
            "game": record.get("game"),
            "date": record.get("date"),
            "homeTeam": record.get("home_team"),
            "awayTeam": record.get("away_team"),
            "homeXg": record.get("home_xg"),
            "awayXg": record.get("away_xg"),
            "homeNpXg": record.get("home_np_xg"),
            "awayNpXg": record.get("away_np_xg"),
            "homePpda": record.get("home_ppda"),
            "awayPpda": record.get("away_ppda"),
            "homeDeep": record.get("home_deep_completions"),
            "awayDeep": record.get("away_deep_completions"),
            "homeGoals": record.get("home_goals"),
            "awayGoals": record.get("away_goals"),
        })
    return {"rows": rows, "summary": {"league": league, "season": season, "count": len(rows), "source": "Understat"}}


def get_understat_player_season_stats(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    refresh = bool(payload.get("refresh", False))

    reader = sd.Understat(leagues=[league], seasons=[season])
    df = reader.read_player_season_stats(force_cache=not refresh)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "count": 0, "source": "Understat"}}

    df = _flatten_columns(df.reset_index())
    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append({
            "player": record.get("player"),
            "team": record.get("team"),
            "games": record.get("games"),
            "goals": record.get("goals"),
            "assists": record.get("assists"),
            "xg": record.get("xg"),
            "xa": record.get("xa"),
            "shots": record.get("shots"),
            "keyPasses": record.get("key_passes"),
            "yellowCards": record.get("yellow_cards"),
            "redCards": record.get("red_cards"),
            "minutes": record.get("minutes"),
            "npg": record.get("npg"),
            "npxg": record.get("npxg"),
        })
    return {"rows": rows, "summary": {"league": league, "season": season, "count": len(rows), "source": "Understat"}}


def get_understat_shot_events(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    match_id = payload.get("match_id")
    limit = int(payload.get("limit", 200))
    refresh = bool(payload.get("refresh", False))

    reader = sd.Understat(leagues=[league], seasons=[season])
    match_ids = [match_id] if match_id else None
    df = reader.read_shot_events(match_id=match_ids)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "count": 0, "source": "Understat"}}

    df = df.reset_index().head(limit)
    rows = []
    for record in serialize_records(df.to_dict(orient="records")):
        rows.append({
            "game": record.get("game"),
            "player": record.get("player"),
            "team": record.get("team"),
            "minute": record.get("minute"),
            "xg": record.get("xg"),
            "result": record.get("result"),
            "situation": record.get("situation"),
            "shotType": record.get("shot_type"),
            "x": record.get("x"),
            "y": record.get("y"),
            "lastAction": record.get("last_action"),
        })
    return {"rows": rows, "summary": {"league": league, "season": season, "matchId": match_id, "count": len(rows), "source": "Understat"}}


def get_fbref_player_season_stats(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    stat_type = payload.get("stat_type", "standard")
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(leagues=league, seasons=season, **_reader_kwargs(payload))
    df = reader.read_player_season_stats(stat_type=stat_type)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "statType": stat_type, "count": 0, "source": "FBref"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.head(500).to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "statType": stat_type, "count": len(rows), "source": "FBref"}}


def get_fbref_team_match_stats(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    stat_type = payload.get("stat_type", "schedule")
    team = payload.get("team") or None
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(leagues=league, seasons=season, **_reader_kwargs(payload))
    df = reader.read_team_match_stats(stat_type=stat_type, team=team)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "statType": stat_type, "count": 0, "source": "FBref"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.head(500).to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "statType": stat_type, "count": len(rows), "source": "FBref"}}


def get_espn_matchsheet(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    match_id = payload.get("match_id")
    limit = int(payload.get("limit", 100))
    refresh = bool(payload.get("refresh", False))

    reader = sd.ESPN(leagues=league, seasons=season, **_reader_kwargs(payload))
    match_id_int = int(match_id) if match_id else None
    df = reader.read_matchsheet(match_id=match_id_int)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "matchId": match_id, "count": 0, "source": "ESPN"}}

    df = _flatten_columns(df.reset_index())
    # Drop the 'roster' column — it contains the full raw ESPN roster JSON
    # (150+ KB per row) which overwhelms the server function response.
    for col in ("roster",):
        if col in df.columns:
            df = df.drop(columns=[col])
    df = df.head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "matchId": match_id, "count": len(rows), "source": "ESPN"}}


def get_espn_lineup(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    match_id = payload.get("match_id")
    limit = int(payload.get("limit", 200))
    refresh = bool(payload.get("refresh", False))

    reader = sd.ESPN(leagues=league, seasons=season, **_reader_kwargs(payload))
    match_id_int = int(match_id) if match_id else None
    df = reader.read_lineup(match_id=match_id_int)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "matchId": match_id, "count": 0, "source": "ESPN"}}

    df = _flatten_columns(df.reset_index())
    for col in ("roster",):
        if col in df.columns:
            df = df.drop(columns=[col])
    df = df.head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "matchId": match_id, "count": len(rows), "source": "ESPN"}}


def get_fbref_team_season_stats(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    stat_type = payload.get("stat_type", "standard")
    opponent_stats = bool(payload.get("opponent_stats", False))
    limit = int(payload.get("limit", 40))
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(leagues=league, seasons=season, **_reader_kwargs(payload))
    df = reader.read_team_season_stats(stat_type=stat_type, opponent_stats=opponent_stats)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "statType": stat_type, "count": 0, "source": "FBref"}}

    df = _flatten_columns(df.reset_index()).head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "statType": stat_type, "count": len(rows), "source": "FBref"}}


def get_fbref_player_match_stats(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    stat_type = payload.get("stat_type", "summary")
    match_id = payload.get("match_id") or None
    limit = int(payload.get("limit", 200))
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(leagues=league, seasons=season, **_reader_kwargs(payload))
    df = reader.read_player_match_stats(stat_type=stat_type, match_id=match_id)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "statType": stat_type, "matchId": match_id, "count": 0, "source": "FBref"}}

    df = _flatten_columns(df.reset_index()).head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "statType": stat_type, "matchId": match_id, "count": len(rows), "source": "FBref"}}


def get_fbref_lineup(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    match_id = payload.get("match_id") or None
    limit = int(payload.get("limit", 200))
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(leagues=league, seasons=season, **_reader_kwargs(payload))
    df = reader.read_lineup(match_id=match_id)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "matchId": match_id, "count": 0, "source": "FBref"}}

    df = _flatten_columns(df.reset_index()).head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "matchId": match_id, "count": len(rows), "source": "FBref"}}


def get_fbref_events(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    match_id = payload.get("match_id") or None
    limit = int(payload.get("limit", 200))
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    reader = sd.FBref(leagues=league, seasons=season, **_reader_kwargs(payload))
    df = reader.read_events(match_id=match_id)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "matchId": match_id, "count": 0, "source": "FBref"}}

    df = _flatten_columns(df.reset_index()).head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "matchId": match_id, "count": len(rows), "source": "FBref"}}


def get_understat_player_match_stats(payload):
    import soccerdata as sd

    league = payload["league"]
    season = payload["season"]
    match_id = payload.get("match_id")
    limit = int(payload.get("limit", 200))
    refresh = bool(payload.get("refresh", False))

    reader = sd.Understat(leagues=league, seasons=season, **_reader_kwargs(payload))

    match_id_val = None
    if match_id:
        try:
            match_id_val = [int(match_id)]
        except (ValueError, TypeError):
            match_id_val = None

    df = reader.read_player_match_stats(match_id=match_id_val)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "matchId": match_id, "count": 0, "source": "Understat"}}

    df = _flatten_columns(df.reset_index()).head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "matchId": match_id, "count": len(rows), "source": "Understat"}}


def get_sofifa_leagues(payload):
    import soccerdata as sd

    refresh = bool(payload.get("refresh", False))

    reader = sd.SoFIFA(**_reader_kwargs(payload))
    df = reader.read_leagues()

    if df.empty:
        return {"rows": [], "summary": {"count": 0, "source": "SoFIFA"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"count": len(rows), "source": "SoFIFA"}}


def get_sofifa_versions(payload):
    import soccerdata as sd

    refresh = bool(payload.get("refresh", False))

    reader = sd.SoFIFA(**_reader_kwargs(payload))
    df = reader.read_versions()

    if df.empty:
        return {"rows": [], "summary": {"count": 0, "source": "SoFIFA"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"count": len(rows), "source": "SoFIFA"}}


def get_sofifa_teams(payload):
    import soccerdata as sd

    league = payload.get("league") or None
    refresh = bool(payload.get("refresh", False))

    reader = sd.SoFIFA(leagues=league, **_reader_kwargs(payload))
    df = reader.read_teams()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "SoFIFA"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "SoFIFA"}}


def get_sofifa_players(payload):
    import soccerdata as sd

    league = payload.get("league") or None
    team = payload.get("team") or None
    refresh = bool(payload.get("refresh", False))

    reader = sd.SoFIFA(leagues=league, **_reader_kwargs(payload))
    df = reader.read_players(team=team)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "SoFIFA"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "SoFIFA"}}


def get_sofifa_team_ratings(payload):
    import soccerdata as sd

    league = payload.get("league") or None
    refresh = bool(payload.get("refresh", False))

    reader = sd.SoFIFA(leagues=league, **_reader_kwargs(payload))
    df = reader.read_team_ratings()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "SoFIFA"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "SoFIFA"}}


def get_sofifa_player_ratings(payload):
    import soccerdata as sd

    league = payload.get("league") or None
    team = payload.get("team") or None
    player = payload.get("player") or None
    refresh = bool(payload.get("refresh", False))

    reader = sd.SoFIFA(leagues=league, **_reader_kwargs(payload))
    df = reader.read_player_ratings(team=team, player=player)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "SoFIFA"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "SoFIFA"}}


def get_fbref_leagues(payload):
    import datetime
    import soccerdata as sd
    from soccerdata._config import LEAGUE_DICT

    league = payload.get("league")
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    leagues = league if league else [l for l, m in LEAGUE_DICT.items() if "FBref" in m]
    year = datetime.date.today().year
    season = f"{(year - 1) % 100:02d}{year % 100:02d}"

    reader = sd.FBref(leagues=leagues, seasons=season, **_reader_kwargs(payload))
    df = reader.read_leagues()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "FBref"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "FBref"}}


def get_fbref_seasons(payload):
    import datetime
    import soccerdata as sd
    from soccerdata._config import LEAGUE_DICT

    league = payload.get("league")
    refresh = bool(payload.get("refresh", False))

    _set_fbref_headers()

    leagues = league if league else [l for l, m in LEAGUE_DICT.items() if "FBref" in m]
    year = datetime.date.today().year
    seasons = [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(year - 9, year + 1)]

    reader = sd.FBref(leagues=leagues, seasons=seasons, **_reader_kwargs(payload))
    df = reader.read_seasons()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "FBref"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "FBref"}}


def get_sofascore_leagues(payload):
    import datetime
    import soccerdata as sd
    from soccerdata._config import LEAGUE_DICT

    league = payload.get("league")
    refresh = bool(payload.get("refresh", False))

    leagues = league if league else [l for l, m in LEAGUE_DICT.items() if "Sofascore" in m]
    year = datetime.date.today().year
    season = f"{(year - 1) % 100:02d}{year % 100:02d}"

    reader = sd.Sofascore(leagues=leagues, seasons=season, **_reader_kwargs(payload))
    df = reader.read_leagues()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "Sofascore"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "Sofascore"}}


def get_sofascore_seasons(payload):
    import datetime
    import soccerdata as sd
    from soccerdata._config import LEAGUE_DICT

    league = payload.get("league")
    refresh = bool(payload.get("refresh", False))

    leagues = league if league else [l for l, m in LEAGUE_DICT.items() if "Sofascore" in m]
    year = datetime.date.today().year
    seasons = [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(year - 9, year + 1)]

    reader = sd.Sofascore(leagues=leagues, seasons=seasons, **_reader_kwargs(payload))
    df = reader.read_seasons()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "Sofascore"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "Sofascore"}}


def get_understat_leagues(payload):
    import datetime
    import soccerdata as sd
    from soccerdata._config import LEAGUE_DICT

    league = payload.get("league")
    refresh = bool(payload.get("refresh", False))

    leagues = league if league else [l for l, m in LEAGUE_DICT.items() if "Understat" in m]
    year = datetime.date.today().year
    season = f"{(year - 1) % 100:02d}{year % 100:02d}"

    reader = sd.Understat(leagues=leagues, seasons=season, **_reader_kwargs(payload))
    df = reader.read_leagues()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "Understat"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "Understat"}}


def get_understat_seasons(payload):
    import datetime
    import soccerdata as sd
    from soccerdata._config import LEAGUE_DICT

    league = payload.get("league")
    refresh = bool(payload.get("refresh", False))

    leagues = league if league else [l for l, m in LEAGUE_DICT.items() if "Understat" in m]
    year = datetime.date.today().year
    seasons = [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(year - 9, year + 1)]

    reader = sd.Understat(leagues=leagues, seasons=seasons, **_reader_kwargs(payload))
    df = reader.read_seasons()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "Understat"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "Understat"}}


WHOSCORED_BROWSER = "/usr/bin/chromium"


def _make_whoscored_reader(leagues, seasons, payload):
    import soccerdata as sd
    return sd.WhoScored(
        leagues=leagues,
        seasons=seasons,
        **_reader_kwargs(payload),
        path_to_browser=WHOSCORED_BROWSER,
        headless=True,
    )


def get_whoscored_leagues(payload):
    import datetime
    from soccerdata._config import LEAGUE_DICT

    league = payload.get("league")
    refresh = bool(payload.get("refresh", False))

    leagues = league if league else [l for l, m in LEAGUE_DICT.items() if "WhoScored" in m]
    year = datetime.date.today().year
    season = f"{(year - 1) % 100:02d}{year % 100:02d}"

    reader = _make_whoscored_reader(leagues, season, payload)
    df = reader.read_leagues()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "WhoScored"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "WhoScored"}}


def get_whoscored_seasons(payload):
    import datetime
    from soccerdata._config import LEAGUE_DICT

    league = payload.get("league")
    refresh = bool(payload.get("refresh", False))

    leagues = league if league else [l for l, m in LEAGUE_DICT.items() if "WhoScored" in m]
    year = datetime.date.today().year
    seasons = [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(year - 5, year)]

    reader = _make_whoscored_reader(leagues, seasons, payload)
    df = reader.read_seasons()

    if df.empty:
        return {"rows": [], "summary": {"league": league, "count": 0, "source": "WhoScored"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "count": len(rows), "source": "WhoScored"}}


def get_whoscored_season_stages(payload):
    league = payload["league"]
    season = payload["season"]
    refresh = bool(payload.get("refresh", False))

    reader = _make_whoscored_reader(league, season, payload)
    df = reader.read_season_stages(force_cache=not refresh)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "count": 0, "source": "WhoScored"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "count": len(rows), "source": "WhoScored"}}


def get_whoscored_schedule(payload):
    league = payload["league"]
    season = payload["season"]
    limit = int(payload.get("limit", 100))
    refresh = bool(payload.get("refresh", False))

    reader = _make_whoscored_reader(league, season, payload)
    df = reader.read_schedule(force_cache=not refresh)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "count": 0, "source": "WhoScored"}}

    df = _flatten_columns(df.reset_index()).head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "count": len(rows), "source": "WhoScored"}}


def get_whoscored_missing_players(payload):
    league = payload["league"]
    season = payload["season"]
    match_id = payload.get("match_id")
    refresh = bool(payload.get("refresh", False))

    match_id_val = None
    if match_id:
        try:
            match_id_val = int(match_id)
        except (ValueError, TypeError):
            match_id_val = None

    reader = _make_whoscored_reader(league, season, payload)
    df = reader.read_missing_players(match_id=match_id_val, force_cache=not refresh)

    if df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "matchId": match_id, "count": 0, "source": "WhoScored"}}

    df = _flatten_columns(df.reset_index())
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "matchId": match_id, "count": len(rows), "source": "WhoScored"}}


def get_whoscored_events(payload):
    league = payload["league"]
    season = payload["season"]
    match_id = payload.get("match_id")
    limit = int(payload.get("limit", 500))
    refresh = bool(payload.get("refresh", False))

    match_id_val = None
    if match_id:
        try:
            match_id_val = int(match_id)
        except (ValueError, TypeError):
            match_id_val = None

    reader = _make_whoscored_reader(league, season, payload)
    df = reader.read_events(match_id=match_id_val, force_cache=not refresh, output_fmt="events")

    if df is None or df.empty:
        return {"rows": [], "summary": {"league": league, "season": season, "matchId": match_id, "count": 0, "source": "WhoScored"}}

    df = _flatten_columns(df.reset_index()).head(limit)
    rows = serialize_records(df.to_dict(orient="records"))
    return {"rows": rows, "summary": {"league": league, "season": season, "matchId": match_id, "count": len(rows), "source": "WhoScored"}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_path = Path(args.output)

    try:
        load_soccerdata_paths()
        payload = json.loads(args.payload)
        operation = payload["operation"]

        if operation == "catalog":
            result = get_catalog()
        elif operation == "espn_schedule":
            result = get_espn_schedule(payload)
        elif operation == "clubelo_ratings":
            result = get_clubelo_ratings(payload)
        elif operation == "matchhistory_games":
            result = get_matchhistory_games(payload)
        elif operation == "fbref_schedule":
            result = get_fbref_schedule(payload)
        elif operation == "fbref_team_stats":
            result = get_fbref_team_stats(payload)
        elif operation == "clubelo_team_history":
            result = get_clubelo_team_history(payload)
        elif operation == "sofascore_standings":
            result = get_sofascore_standings(payload)
        elif operation == "fbref_shot_events":
            result = get_fbref_shot_events(payload)
        elif operation == "sofascore_schedule":
            result = get_sofascore_schedule(payload)
        elif operation == "understat_schedule":
            result = get_understat_schedule(payload)
        elif operation == "understat_team_match_stats":
            result = get_understat_team_match_stats(payload)
        elif operation == "understat_player_season_stats":
            result = get_understat_player_season_stats(payload)
        elif operation == "understat_shot_events":
            result = get_understat_shot_events(payload)
        elif operation == "fbref_player_season_stats":
            result = get_fbref_player_season_stats(payload)
        elif operation == "fbref_team_match_stats":
            result = get_fbref_team_match_stats(payload)
        elif operation == "espn_matchsheet":
            result = get_espn_matchsheet(payload)
        elif operation == "espn_lineup":
            result = get_espn_lineup(payload)
        elif operation == "fbref_team_season_stats":
            result = get_fbref_team_season_stats(payload)
        elif operation == "fbref_player_match_stats":
            result = get_fbref_player_match_stats(payload)
        elif operation == "fbref_lineup":
            result = get_fbref_lineup(payload)
        elif operation == "fbref_events":
            result = get_fbref_events(payload)
        elif operation == "understat_player_match_stats":
            result = get_understat_player_match_stats(payload)
        elif operation == "sofifa_leagues":
            result = get_sofifa_leagues(payload)
        elif operation == "sofifa_versions":
            result = get_sofifa_versions(payload)
        elif operation == "sofifa_teams":
            result = get_sofifa_teams(payload)
        elif operation == "sofifa_players":
            result = get_sofifa_players(payload)
        elif operation == "sofifa_team_ratings":
            result = get_sofifa_team_ratings(payload)
        elif operation == "sofifa_player_ratings":
            result = get_sofifa_player_ratings(payload)
        elif operation == "fbref_leagues":
            result = get_fbref_leagues(payload)
        elif operation == "fbref_seasons":
            result = get_fbref_seasons(payload)
        elif operation == "sofascore_leagues":
            result = get_sofascore_leagues(payload)
        elif operation == "sofascore_seasons":
            result = get_sofascore_seasons(payload)
        elif operation == "understat_leagues":
            result = get_understat_leagues(payload)
        elif operation == "understat_seasons":
            result = get_understat_seasons(payload)
        elif operation == "whoscored_leagues":
            result = get_whoscored_leagues(payload)
        elif operation == "whoscored_seasons":
            result = get_whoscored_seasons(payload)
        elif operation == "whoscored_season_stages":
            result = get_whoscored_season_stages(payload)
        elif operation == "whoscored_schedule":
            result = get_whoscored_schedule(payload)
        elif operation == "whoscored_missing_players":
            result = get_whoscored_missing_players(payload)
        elif operation == "whoscored_events":
            result = get_whoscored_events(payload)
        elif operation == "team_mapping_get":
            result = get_team_mapping(payload)
        elif operation == "team_mapping_set":
            result = set_team_mapping(payload)
        else:
            raise ValueError(f"Unsupported operation: {operation}")

        output_path.write_text(json.dumps({"ok": True, "result": result}), encoding="utf-8")
    except Exception as exc:
        output_path.write_text(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(limit=10),
                }
            ),
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    main()
