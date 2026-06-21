#!/usr/bin/env python3
"""Playwright Python E2E flow for today's scrape -> history -> predictions -> tickets.

The script intentionally uses Playwright's browser and APIRequestContext so one
runtime verifies both the Svelte UI and the authenticated FastAPI workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

from playwright.sync_api import APIRequestContext, Page, Playwright, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / ".playwright-artifacts" / "python-flow"
PREDICTABLE_MARKETS = ["1x2", "btts", "over_under_2_5"]
PREDICTION_MARKETS = ["1x2", "btts", "ou_2_5"]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def season_for_day(day: date) -> str:
    start = day.year if day.month >= 7 else day.year - 1
    return f"{start}-{start + 1}"


def require_ok(response, label: str) -> Any:
    text = response.text()
    if not response.ok:
        raise RuntimeError(f"{label} failed: HTTP {response.status} {text[:1000]}")
    if not text:
        return None
    try:
        return response.json()
    except Exception as exc:  # pragma: no cover - diagnostic path
        raise RuntimeError(f"{label} returned non-JSON: {text[:1000]}") from exc


class AuthenticatedAPI:
    """Small Playwright API wrapper that refreshes JWTs after long scrapes."""

    def __init__(self, playwright: Playwright, public_request: APIRequestContext, backend: str, email: str, password: str):
        self.playwright = playwright
        self.public_request = public_request
        self.backend = backend
        self.email = email
        self.password = password
        self.context: APIRequestContext | None = None
        self.login_count = 0
        self.login()

    def login(self) -> None:
        login = require_ok(
            self.public_request.post("/api/v1/auth/login", data={"email": self.email, "password": self.password}),
            "login",
        )
        token = login["access_token"]
        if self.context is not None:
            self.context.dispose()
        self.context = self.playwright.request.new_context(
            base_url=self.backend,
            extra_http_headers={"Authorization": f"Bearer {token}"},
        )
        self.login_count += 1

    def dispose(self) -> None:
        if self.context is not None:
            self.context.dispose()
            self.context = None

    def _call(self, method: str, path: str, label: str, *, payload: dict[str, Any] | None = None, timeout_ms: int = 30_000) -> Any:
        if self.context is None:
            self.login()

        def send():
            assert self.context is not None
            if method == "GET":
                return self.context.get(path, timeout=timeout_ms)
            if method == "POST":
                return self.context.post(path, data=payload or {}, timeout=timeout_ms)
            raise ValueError(method)

        response = send()
        if response.status == 401:
            self.login()
            response = send()
        return require_ok(response, label)

    def get(self, path: str, label: str, *, timeout_ms: int = 30_000) -> Any:
        return self._call("GET", path, label, timeout_ms=timeout_ms)

    def post(self, path: str, payload: dict[str, Any], label: str, *, timeout_ms: int = 30_000) -> Any:
        return self._call("POST", path, label, payload=payload, timeout_ms=timeout_ms)


def screenshot(page: Page, artifact_dir: Path, name: str) -> str:
    path = artifact_dir / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def derive_oddsharvester_league_slug(match_detail: dict[str, Any]) -> str | None:
    for source in match_detail.get("sources", []) or []:
        url = source.get("url")
        if not url:
            continue
        parts = [part for part in urlparse(url).path.split("/") if part]
        # Expected OddsPortal shape: /football/{country}/{league}/{match}/
        if len(parts) >= 3 and parts[0] == "football":
            return f"{parts[1]}-{parts[2]}"

    league = str(match_detail.get("league") or "")
    normalized = league.lower()
    if "world" in normalized and ("championship" in normalized or "cup" in normalized):
        # Backend demo/current World Cup data is named "World Championship 2026",
        # while OddsHarvester's scrape slug is the generic OddsPortal slug.
        return "world-cup"
    if league:
        return slugify(league)
    return None


def summarize_job(job: dict[str, Any]) -> dict[str, Any]:
    output = job.get("output")
    parsed_output: Any = None
    if isinstance(output, str) and output:
        try:
            parsed_output = json.loads(output)
        except json.JSONDecodeError:
            parsed_output = output[:1000]
    return {
        "id": job.get("id"),
        "status": job.get("status"),
        "league": job.get("league"),
        "error": job.get("error"),
        "output": parsed_output,
    }


def scrape_params(
    *,
    args: argparse.Namespace,
    command: str,
    ymd: str | None = None,
    slug: str | None = None,
    season: str | None = None,
    markets_override: list[str] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "command": command,
        "sport": "football",
        "odds_history": args.odds_history,
        "headless": True,
        "bookies_filter": "all",
        "concurrency": args.concurrency,
        "request_delay": args.request_delay,
    }
    if markets_override is not None:
        params["all_markets"] = False
        params["markets"] = markets_override
    elif args.market_mode == "all":
        params["all_markets"] = True
    else:
        params["all_markets"] = False
        params["markets"] = PREDICTABLE_MARKETS
    if ymd:
        params["date"] = ymd
    if slug:
        params["leagues"] = [slug]
    if command == "historic":
        params["season"] = season
        params["max_pages"] = args.historic_max_pages
    return params


def append_error(summary: dict[str, Any], step: str, error: BaseException | str) -> None:
    summary["errors"].append({"step": step, "error": str(error)})


def safe_step(summary: dict[str, Any], step: str, func: Callable[[], Any]) -> Any | None:
    try:
        return func()
    except Exception as exc:  # pragma: no cover - e2e diagnostic path
        append_error(summary, step, exc)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", default=os.getenv("FRONTEND_URL", "http://127.0.0.1:5175"))
    parser.add_argument("--backend", default=os.getenv("BACKEND_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--date", default=os.getenv("FLOW_DATE", date.today().isoformat()))
    parser.add_argument("--timeout-minutes", type=int, default=int(os.getenv("FLOW_TIMEOUT_MINUTES", "12")))
    parser.add_argument("--max-historic-leagues", type=int, default=int(os.getenv("FLOW_MAX_HISTORIC_LEAGUES", "0")), help="0 means all discovered leagues")
    parser.add_argument("--historic-season", default=os.getenv("FLOW_HISTORIC_SEASON"))
    parser.add_argument("--historic-max-pages", type=int, default=int(os.getenv("FLOW_HISTORIC_MAX_PAGES", "2")))
    parser.add_argument("--ticket-stake", type=float, default=float(os.getenv("FLOW_TICKET_STAKE", "10")))
    parser.add_argument("--market-mode", choices=["all", "predictable"], default=os.getenv("FLOW_MARKET_MODE", "all"), help="all scrapes every configured football market; predictable limits scraping to markets the prediction engine can price")
    parser.add_argument("--today-league-slug", default=os.getenv("FLOW_TODAY_LEAGUE_SLUG"), help="Optional OddsHarvester league slug to bound today's scrape while keeping the requested date filter")
    parser.add_argument("--competition-filter", default=os.getenv("FLOW_COMPETITION_FILTER"), help="Optional backend competition filter for the downstream match/prediction set")
    parser.add_argument("--historic-market-mode", choices=["same", "one-x-two"], default=os.getenv("FLOW_HISTORIC_MARKET_MODE", "same"), help="Use one-x-two to ingest historic scores faster while keeping today scrape unchanged")
    parser.add_argument("--prediction-markets", default=os.getenv("FLOW_PREDICTION_MARKETS", ",".join(PREDICTION_MARKETS)), help="Comma-separated prediction markets, e.g. 1x2,btts,ou_2_5")
    parser.add_argument("--odds-history", action="store_true", help="Also scrape odds movement history; much slower.")
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("FLOW_SCRAPE_CONCURRENCY", "2")))
    parser.add_argument("--request-delay", type=float, default=float(os.getenv("FLOW_SCRAPE_REQUEST_DELAY", "1.0")))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    flow_day = date.fromisoformat(args.date)
    ymd = flow_day.strftime("%Y%m%d")
    iso_start = f"{flow_day.isoformat()}T00:00:00+00:00"
    iso_end = f"{flow_day.isoformat()}T23:59:59+00:00"
    historic_season = args.historic_season or season_for_day(flow_day)
    timeout_ms = args.timeout_minutes * 60_000

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_dir = ARTIFACT_ROOT / f"today-full-flow-{stamp}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "date": flow_day.isoformat(),
        "backend": args.backend,
        "frontend": args.frontend,
        "artifact_dir": str(artifact_dir),
        "market_mode": args.market_mode,
        "requested_scrape_markets": "all_football" if args.market_mode == "all" else PREDICTABLE_MARKETS,
        "odds_history": args.odds_history,
        "today_league_slug": args.today_league_slug,
        "competition_filter": args.competition_filter,
        "historic_market_mode": args.historic_market_mode,
        "prediction_markets": [m.strip() for m in args.prediction_markets.split(",") if m.strip()],
        "user": None,
        "screenshots": [],
        "today_scrape_job": None,
        "historic_scrape_jobs": [],
        "matches_today": 0,
        "matches_with_odds": 0,
        "team_history": {},
        "discovered_league_slugs": [],
        "prediction_runs": [],
        "value_bets": 0,
        "created_ticket": None,
        "auth_relogins": 0,
        "warnings": [],
        "errors": [],
    }

    browser = None
    public_request = None
    api: AuthenticatedAPI | None = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headed)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            public_request = p.request.new_context(base_url=args.backend)

            # UI smoke verification.
            for route, name in [("/", "01-home"), ("/scrape", "02-scrape"), ("/predict", "03-predict"), ("/tickets", "04-tickets")]:
                def visit(route=route, name=name):
                    page.goto(f"{args.frontend}{route}", wait_until="domcontentloaded", timeout=30_000)
                    return screenshot(page, artifact_dir, name)

                shot = safe_step(summary, f"ui:{route}", visit)
                if shot:
                    summary["screenshots"].append(shot)

            # Authenticated API context.
            unique = int(time.time())
            email = f"playwright-flow-{unique}@example.test"
            password = f"Passw0rd!-{unique}"
            require_ok(
                public_request.post(
                    "/api/v1/auth/signup",
                    data={"email": email, "name": f"Playwright Flow {unique}", "password": password},
                ),
                "signup",
            )
            summary["user"] = email
            api = AuthenticatedAPI(p, public_request, args.backend, email, password)

            # Scrape today's football matches. In default mode this requests all configured
            # football markets and all bookmakers; predictable mode is a bounded diagnostic
            # mode for markets currently supported by predictions/value-bet matching.
            today_params = scrape_params(args=args, command="upcoming", ymd=ymd, slug=args.today_league_slug)
            today_job = safe_step(
                summary,
                "today_scrape_create",
                lambda: api.post(
                    "/api/v1/data/scrape",
                    {"job_type": "scrape_odds", "league": args.today_league_slug, "params": today_params},
                    f"create today's {args.market_mode} scrape job",
                ),
            )
            if today_job:
                executed_today = safe_step(
                    summary,
                    "today_scrape_execute",
                    lambda: api.post(
                        f"/api/v1/data/scrape/{today_job['id']}/execute",
                        {},
                        f"execute today's {args.market_mode} scrape job",
                        timeout_ms=timeout_ms,
                    ),
                )
                if executed_today:
                    summary["today_scrape_job"] = summarize_job(executed_today)
                    if executed_today.get("status") != "completed":
                        summary["errors"].append({"step": "today_scrape", "job": summary["today_scrape_job"]})

            # Load today's matches, then inspect detail sources to derive historical league slugs.
            matches_query = f"/api/v1/matches?date_from={iso_start}&date_to={iso_end}&per_page=200"
            if args.competition_filter:
                matches_query += f"&competition={quote(args.competition_filter)}"
            matches_payload = api.get(
                matches_query,
                "list today's matches",
            )
            matches = matches_payload.get("matches", [])
            summary["matches_today"] = len(matches)
            summary["matches_with_odds"] = sum(1 for m in matches if m.get("odds"))
            if not matches:
                summary["errors"].append({"step": "matches_today", "error": "No matches found for requested date"})

            league_slugs: list[str] = []
            league_names: list[str] = []
            teams: set[str] = set()
            for match in matches:
                teams.add(match.get("home_team", ""))
                teams.add(match.get("away_team", ""))
                if match.get("league") and match["league"] not in league_names:
                    league_names.append(match["league"])
                detail = safe_step(summary, f"match_detail:{match['id']}", lambda match=match: api.get(f"/api/v1/matches/{match['id']}", f"match detail {match['id']}"))
                if detail:
                    slug = derive_oddsharvester_league_slug(detail)
                    if slug and slug not in league_slugs:
                        league_slugs.append(slug)

            if args.max_historic_leagues > 0:
                league_slugs = league_slugs[: args.max_historic_leagues]
            summary["discovered_league_slugs"] = league_slugs

            # Scrape historical context for each discovered league. This is the closest
            # backend-supported equivalent to per-team history: after league history is
            # ingested, prediction training filters by competition and team participation
            # comes from those stored matches.
            historic_markets = ["1x2"] if args.historic_market_mode == "one-x-two" else None
            for slug in league_slugs:
                hist_params = scrape_params(
                    args=args,
                    command="historic",
                    slug=slug,
                    season=historic_season,
                    markets_override=historic_markets,
                )
                hist_job = safe_step(
                    summary,
                    f"historic_scrape_create:{slug}",
                    lambda slug=slug, hist_params=hist_params: api.post(
                        "/api/v1/data/scrape",
                        {"job_type": "scrape_odds", "league": slug, "params": hist_params},
                        f"create historic scrape job {slug}",
                    ),
                )
                if not hist_job:
                    continue
                executed_hist = safe_step(
                    summary,
                    f"historic_scrape_execute:{slug}",
                    lambda slug=slug, hist_job=hist_job: api.post(
                        f"/api/v1/data/scrape/{hist_job['id']}/execute",
                        {},
                        f"execute historic scrape job {slug}",
                        timeout_ms=timeout_ms,
                    ),
                )
                if executed_hist:
                    summary["historic_scrape_jobs"].append(summarize_job(executed_hist))

            # Verify that each team has at least some stored finished history after historical scrapes.
            missing_team_history: list[str] = []
            for team in sorted(t for t in teams if t):
                payload = safe_step(summary, f"history_check:{team}", lambda team=team: api.get(f"/api/v1/matches?team={team}&status=finished&per_page=1", f"history check {team}"))
                if not payload:
                    continue
                total = payload.get("total", 0)
                summary["team_history"][team] = total
                if total < 1:
                    missing_team_history.append(team)
            if missing_team_history:
                summary["warnings"].append({"missing_team_history": missing_team_history[:50], "count": len(missing_team_history)})

            # Run predictions for each discovered competition. Models support only 1x2, BTTS, OU 2.5.
            model_keys = ["PoissonGoalsModel", "DixonColesGoalModel", "BivariatePoissonGoalModel"]
            prediction_markets = [m.strip() for m in args.prediction_markets.split(",") if m.strip()]
            for league_name in league_names:
                for model_key in model_keys:
                    run = safe_step(
                        summary,
                        f"prediction:{league_name}:{model_key}",
                        lambda league_name=league_name, model_key=model_key: api.post(
                            "/api/v1/predictions/run",
                            {
                                "league": league_name,
                                "sport": "football",
                                "model_key": model_key,
                                "markets": prediction_markets,
                                "training_limit": 380,
                                "target_mode": "future",
                                "target_limit": 50,
                                "max_goals": 10,
                            },
                            f"prediction {league_name} {model_key}",
                            timeout_ms=timeout_ms,
                        ),
                    )
                    if run:
                        summary["prediction_runs"].append({"league": league_name, "model": model_key, **run})

            # Value bets from the latest completed run; min_edge=-100 means return any model/odds match.
            value_bets_payload = safe_step(summary, "value_bets", lambda: api.get("/api/v1/predictions/value-bets?min_edge=-100&max_results=100", "value bets"))
            items = value_bets_payload.get("items", []) if value_bets_payload else []
            summary["value_bets"] = len(items)

            if items:
                legs = []
                used_matches = set()
                for item in items:
                    if item["match_id"] in used_matches:
                        continue
                    used_matches.add(item["match_id"])
                    source = item.get("source") or ""
                    bookmaker = source.split(":", 1)[1] if source.startswith("odds:") else None
                    legs.append(
                        {
                            "model_prediction_id": item["id"],
                            "match_id": item["match_id"],
                            "selection": item["selection"],
                            "market": item["market"],
                            "odds": item["odds"],
                            "bookmaker": bookmaker,
                        }
                    )
                    if len(legs) >= 3:
                        break
                ticket = safe_step(
                    summary,
                    "ticket_create",
                    lambda: api.post(
                        "/api/v1/tickets",
                        {
                            "ticket_type": "single" if len(legs) == 1 else "accumulator",
                            "stake": args.ticket_stake,
                            "bankroll_id": None,
                            "legs": legs,
                        },
                        "create ticket from value bets",
                    ),
                )
                if ticket:
                    summary["created_ticket"] = ticket
            else:
                summary["errors"].append({"step": "ticket", "error": "No value-bet/model-odds candidates available for ticket creation"})

            summary["auth_relogins"] = api.login_count

    except Exception as exc:  # pragma: no cover - e2e diagnostic path
        append_error(summary, "unhandled", exc)
    finally:
        summary["auth_relogins"] = api.login_count if api is not None else summary.get("auth_relogins", 0)
        for cleanup in (
            (api.dispose if api is not None else None),
            (public_request.dispose if public_request is not None else None),
            (browser.close if browser is not None else None),
        ):
            if cleanup is None:
                continue
            try:
                cleanup()
            except Exception:
                pass
        summary_path = artifact_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    hard_failure_steps = {"today_scrape", "today_scrape_create", "today_scrape_execute", "matches_today", "ticket", "ticket_create", "unhandled"}
    hard_failures = [err for err in summary["errors"] if err.get("step") in hard_failure_steps]
    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
