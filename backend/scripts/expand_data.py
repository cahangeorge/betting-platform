"""Expand training data — generates realistic synthetic match data across 5 major leagues.

Creates ~1000 matches with realistic goal distributions, home advantage,
and team-specific attack/defense ratings based on actual league statistics.
"""
import csv
import math
import random
from pathlib import Path

# League configurations based on real statistics (avg goals per match)
LEAGUES = {
    "PL": {
        "name": "Premier League",
        "avg_home": 1.55, "avg_away": 1.18,
        "teams": [
            "Arsenal", "Man City", "Liverpool", "Man Utd", "Tottenham",
            "Newcastle", "Aston Villa", "Brighton", "West Ham", "Crystal Palace",
            "Brentford", "Fulham", "Wolves", "Everton", "Bournemouth",
            "Nottingham", "Burnley", "Sheffield Utd", "Luton", "Chelsea",
        ],
    },
    "LaLiga": {
        "name": "La Liga",
        "avg_home": 1.50, "avg_away": 1.12,
        "teams": [
            "Real Madrid", "Barcelona", "Atletico Madrid", "Real Sociedad",
            "Villarreal", "Athletic Bilbao", "Real Betis", "Valencia",
            "Sevilla", "Osasuna", "Girona", "Las Palmas", "Mallorca",
            "Rayo Vallecano", "Celta Vigo", "Getafe", "Alaves", "Cadiz",
            "Granada", "Almeria",
        ],
    },
    "SerieA": {
        "name": "Serie A",
        "avg_home": 1.48, "avg_away": 1.15,
        "teams": [
            "Inter Milan", "AC Milan", "Juventus", "Napoli", "Roma",
            "Lazio", "Atalanta", "Fiorentina", "Bologna", "Torino",
            "Monza", "Udinese", "Sassuolo", "Empoli", "Cagliari",
            "Lecce", "Genoa", "Frosinone", "Verona", "Salernitana",
        ],
    },
    "Bundesliga": {
        "name": "Bundesliga",
        "avg_home": 1.62, "avg_away": 1.25,
        "teams": [
            "Bayern Munich", "Borussia Dortmund", "Bayer Leverkusen",
            "RB Leipzig", "Eintracht Frankfurt", "Union Berlin",
            "Wolfsburg", "Freiburg", "Bayer Monchengladbach", "Stuttgart",
            "Mainz", "Augsburg", "Werder Bremen", "Hoffenheim",
            "Darmstadt", "Koln", "Bochum", "Heidenheim",
        ],
    },
    "Ligue1": {
        "name": "Ligue 1",
        "avg_home": 1.52, "avg_away": 1.10,
        "teams": [
            "Paris Saint-Germain", "Monaco", "Marseille", "Lille",
            "Rennes", "Nice", "Lens", "Lyon", "Strasbourg", "Nantes",
            "Brest", "Montpellier", "Toulouse", "Reims", "Le Havre",
            "Metz", "Lorient", "Clermont",
        ],
    },
}

# Team strength ratings (attack, defense) — 1.0 = league average
TEAM_RATINGS = {
    # Premier League
    "Arsenal": (1.35, 0.75), "Man City": (1.45, 0.70), "Liverpool": (1.40, 0.78),
    "Man Utd": (1.15, 0.95), "Tottenham": (1.20, 0.90), "Newcastle": (1.18, 0.85),
    "Aston Villa": (1.15, 0.88), "Brighton": (1.10, 0.92), "West Ham": (1.05, 0.95),
    "Crystal Palace": (0.95, 1.00), "Brentford": (1.05, 0.98), "Fulham": (1.00, 1.02),
    "Wolves": (0.92, 1.05), "Everton": (0.88, 1.08), "Bournemouth": (0.95, 1.05),
    "Nottingham": (0.85, 1.10), "Burnley": (0.78, 1.15), "Sheffield Utd": (0.75, 1.18),
    "Luton": (0.80, 1.12), "Chelsea": (1.10, 0.90),
    # La Liga
    "Real Madrid": (1.42, 0.72), "Barcelona": (1.38, 0.75), "Atletico Madrid": (1.20, 0.78),
    "Real Sociedad": (1.10, 0.88), "Villarreal": (1.12, 0.92), "Athletic Bilbao": (1.08, 0.90),
    "Real Betis": (1.05, 0.95), "Valencia": (0.98, 0.98), "Sevilla": (1.02, 0.92),
    "Osasuna": (0.95, 1.00), "Girona": (1.08, 0.95), "Las Palmas": (0.90, 1.02),
    "Mallorca": (0.88, 1.05), "Rayo Vallecano": (0.92, 1.00), "Celta Vigo": (0.95, 1.02),
    "Getafe": (0.85, 1.05), "Alaves": (0.88, 1.05), "Cadiz": (0.80, 1.10),
    "Granada": (0.82, 1.12), "Almeria": (0.78, 1.15),
    # Serie A
    "Inter Milan": (1.35, 0.72), "AC Milan": (1.25, 0.80), "Juventus": (1.18, 0.78),
    "Napoli": (1.22, 0.82), "Roma": (1.12, 0.88), "Lazio": (1.15, 0.90),
    "Atalanta": (1.28, 0.85), "Fiorentina": (1.08, 0.92), "Bologna": (1.05, 0.90),
    "Torino": (0.95, 0.95), "Monza": (0.92, 0.98), "Udinese": (0.90, 1.00),
    "Sassuolo": (0.88, 1.05), "Empoli": (0.82, 1.08), "Cagliari": (0.85, 1.05),
    "Lecce": (0.80, 1.08), "Genoa": (0.88, 1.02), "Frosinone": (0.78, 1.12),
    "Verona": (0.82, 1.08), "Salernitana": (0.75, 1.15),
    # Bundesliga
    "Bayern Munich": (1.50, 0.68), "Borussia Dortmund": (1.35, 0.82),
    "Bayer Leverkusen": (1.32, 0.78), "RB Leipzig": (1.28, 0.80),
    "Eintracht Frankfurt": (1.15, 0.90), "Union Berlin": (0.95, 0.92),
    "Wolfsburg": (1.05, 0.95), "Freiburg": (1.02, 0.92),
    "Bayer Monchengladbach": (1.05, 0.98), "Stuttgart": (1.10, 0.90),
    "Mainz": (0.92, 1.02), "Augsburg": (0.88, 1.05), "Werder Bremen": (0.95, 1.00),
    "Hoffenheim": (1.00, 1.02), "Darmstadt": (0.78, 1.15), "Koln": (0.85, 1.08),
    "Bochum": (0.82, 1.10), "Heidenheim": (0.80, 1.08),
    # Ligue 1
    "Paris Saint-Germain": (1.55, 0.65), "Monaco": (1.20, 0.88),
    "Marseille": (1.12, 0.90), "Lille": (1.08, 0.88), "Rennes": (1.05, 0.92),
    "Nice": (1.00, 0.90), "Lens": (1.08, 0.88), "Lyon": (1.05, 0.95),
    "Strasbourg": (0.95, 1.00), "Nantes": (0.92, 1.02), "Brest": (1.00, 0.88),
    "Montpellier": (0.98, 1.02), "Toulouse": (0.92, 1.00), "Reims": (0.95, 1.02),
    "Le Havre": (0.85, 1.08), "Metz": (0.80, 1.10), "Lorient": (0.82, 1.12),
    "Clermont": (0.80, 1.10),
}


def poisson_sample(lam: float) -> int:
    """Sample from Poisson distribution."""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p < L:
            break
    return k - 1


def generate_match(home_team: str, away_team: str, league_key: str,
                   league_cfg: dict, season: str, matchday: int) -> dict:
    """Generate a single match result based on team ratings."""
    h_atk, h_def = TEAM_RATINGS.get(home_team, (1.0, 1.0))
    a_atk, a_def = TEAM_RATINGS.get(away_team, (1.0, 1.0))

    home_advantage = 1.12  # ~12% home advantage

    # Expected goals using modified Poisson
    home_xg = league_cfg["avg_home"] * h_atk * home_advantage / a_def
    away_xg = league_cfg["avg_away"] * a_atk / h_def

    # Add some randomness to team form (±10%)
    home_xg *= random.uniform(0.90, 1.10)
    away_xg *= random.uniform(0.90, 1.10)

    home_goals = poisson_sample(home_xg)
    away_goals = poisson_sample(away_xg)

    # Generate date
    year = int(season.split("-")[0])
    month = 8 + (matchday // 10)  # Start in August
    day = (matchday % 28) + 1
    if month > 12:
        month -= 12
        year += 1
    date = f"{year}-{month:02d}-{day:02d}"

    return {
        "Date": date,
        "HomeTeam": home_team,
        "AwayTeam": away_team,
        "FTHG": home_goals,
        "FTAG": away_goals,
        "League": league_key,
    }


def generate_season(league_key: str, league_cfg: dict, season: str) -> list[dict]:
    """Generate a full season of matches (round-robin, each pair plays twice)."""
    teams = league_cfg["teams"]
    matches = []
    matchday = 0

    # Generate all pairings (home and away)
    pairings = []
    for i, home in enumerate(teams):
        for j, away in enumerate(teams):
            if i != j:
                pairings.append((home, away))

    random.shuffle(pairings)

    # Split into matchdays (10 matches per matchday for 20-team league)
    matches_per_day = len(teams) // 2
    for idx in range(0, len(pairings), matches_per_day):
        batch = pairings[idx:idx + matches_per_day]
        matchday += 1
        for home, away in batch:
            matches.append(generate_match(home, away, league_key, league_cfg, season, matchday))

    return matches


def main():
    output_path = Path(__file__).resolve().parent.parent / "data" / "historical_matches.csv"
    all_matches = []

    # Generate 3 seasons (2021-22, 2022-23, 2023-24)
    seasons = ["2021-2022", "2022-2023", "2023-2024"]

    for season in seasons:
        for league_key, league_cfg in LEAGUES.items():
            matches = generate_season(league_key, league_cfg, season)
            all_matches.extend(matches)

    # Shuffle all matches
    random.shuffle(all_matches)

    # Write to CSV
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "League"])
        writer.writeheader()
        writer.writerows(all_matches)

    print(f"Generated {len(all_matches)} matches across {len(LEAGUES)} leagues and {len(seasons)} seasons")
    print(f"Output: {output_path}")

    # Show league breakdown
    from collections import Counter
    league_counts = Counter(m["League"] for m in all_matches)
    for league, count in sorted(league_counts.items()):
        print(f"  {league}: {count} matches")


if __name__ == "__main__":
    main()
