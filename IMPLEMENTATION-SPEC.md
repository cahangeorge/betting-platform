# Implementation Specification

## Overview

4-phase implementation of enhanced betting platform features. All phases parallel, no priority order.

## Backend Structure

Location: `/home/gion/Projects/bet/backend/`

### Models to Extend

**MatchStat** (`app/models/match.py`) — add fields:
- `yellow_cards_home: int | None = None`
- `yellow_cards_away: int | None = None`
- `red_cards_home: int | None = None`
- `red_cards_away: int | None = None`
- `fouls_home: int | None = None`
- `fouls_away: int | None = None`
- `offsides_home: int | None = None`
- `offsides_away: int | None = None`

### New Models to Create

**Strategy** (`app/models/strategy.py`):
- `id: int (PK)`
- `name: str` (e.g., "Poisson", "Dixon-Coles", "xG Ensemble")
- `description: str | None`
- `model_type: str` (poisson, dixon_coles, elo, xg, ensemble, negbin, zip, weibull)
- `parameters: JSON` (model-specific params)
- `weights: JSON | None` (for ensemble: model weights)
- `is_active: bool = True`
- `created_at, updated_at`

**PredictionRun** already exists — add `strategy_id: int | None (FK)` to link runs to strategies.

### New Endpoints

**Dashboard** (`app/api/v1/dashboard.py`):
- `GET /api/v1/dashboard/summary` — stats: total matches, total tickets, win rate, P&L, active bankroll
- `GET /api/v1/dashboard/recent-tickets?limit=10&date_from=&date_to=` — recent tickets with match info
- `GET /api/v1/dashboard/upcoming?days=7` — upcoming matches with odds
- `GET /api/v1/dashboard/job-logs?limit=20` — recent job logs

**Analytics** (`app/api/v1/analytics.py`):
- `GET /api/v1/analytics/pnl?period=30d&group_by=day` — time-series P&L aggregation
- `GET /api/v1/analytics/pnl/by-league` — P&L per league
- `GET /api/v1/analytics/pnl/by-model` — P&L per prediction model
- `GET /api/v1/analytics/equity-curve?period=30d` — bankroll over time

**League Catalog** (`app/api/v1/catalog.py`):
- `GET /api/v1/catalog/countries` — list of countries with leagues
- `GET /api/v1/catalog/leagues?country=Italy` — leagues for a country
- `GET /api/v1/catalog/leagues/all` — all leagues grouped by country

**Strategies** (`app/api/v1/strategies.py`):
- `GET /api/v1/strategies` — list all strategies
- `POST /api/v1/strategies` — create strategy
- `GET /api/v1/strategies/{id}` — get strategy
- `PUT /api/v1/strategies/{id}` — update strategy
- `DELETE /api/v1/strategies/{id}` — delete strategy
- `POST /api/v1/strategies/{id}/run` — execute strategy on selected matches

**Jobs Enhanced** (`app/api/v1/jobs.py`) — extend existing:
- `POST /api/v1/jobs` — now accepts `scrape` and `predict` task types with strategy_id

### API Response Formats

**Dashboard Summary:**
```json
{
  "total_matches": 5256,
  "total_tickets": 142,
  "win_rate": 55.8,
  "total_pnl": 1234.56,
  "active_bankroll": 10000,
  "pending_bets": 3
}
```

**Recent Tickets:**
```json
[{
  "id": 1,
  "reference": "TKT-001",
  "type": "accumulator",
  "status": "won",
  "stake": 10,
  "total_odds": 5.2,
  "potential_return": 52,
  "actual_return": 52,
  "legs": [{
    "match_id": 1,
    "home_team": "AC Milan",
    "away_team": "Inter",
    "market": "1X2",
    "selection": "Home",
    "odds": 2.1,
    "status": "won",
    "home_score": 2,
    "away_score": 1
  }],
  "created_at": "2026-06-05T15:00:00Z"
}]
```

**P&L Time Series:**
```json
[{
  "date": "2026-06-01",
  "pnl": 45.20,
  "cumulative_pnl": 234.56,
  "bets_count": 5,
  "wins": 3
}]
```

**Countries/Leagues:**
```json
[{
  "country": "Italy",
  "leagues": [
    {"id": "serie_a", "name": "Serie A", "matches_count": 380},
    {"id": "serie_b", "name": "Serie B", "matches_count": 380}
  ]
}]
```

**Strategies:**
```json
[{
  "id": 1,
  "name": "Dixon-Coles",
  "model_type": "dixon_coles",
  "description": "Bivariate Poisson with Dixon-Coles correlation parameter",
  "parameters": {"rho": -0.13, "home_advantage": 0.25},
  "is_active": true,
  "last_run": "2026-06-05T12:00:00Z",
  "avg_edge": 3.2,
  "avg_win_rate": 57.1
}]
```

**Strategy Run Request:**
```json
{
  "match_ids": [1, 2, 3],
  "markets": ["1X2", "over_under_2.5", "btts"],
  "parameters": {}
}
```

## Frontend Structure

Location: `/home/gion/Projects/bet/frontend/`

### Design System

- **Framework:** SvelteKit 2 + Svelte 5 (runes)
- **UI:** shadcn-svelte (bits-ui, CVA, cn())
- **Charts:** layerchart (AreaChart, BarChart, LineChart)
- **Theme:** `app.css` with HSL tokens, `@custom-variant dark`
- **No rounded corners** — `--radius: 0rem`
- **Football colors:** `--football-green`, `--football-blue`, `--football-gold`, `--football-red`
- **Fonts:** Inter (body), JetBrains Mono (data), Oswald (team names — currently mapped to Inter)
- **API client:** `$lib/api/client.ts` with `ApiClient` base class, all endpoints use `/api/v1/*`

### Pages to Create/Modify

**Dashboard** (`src/routes/+page.svelte`) — REWRITE:
Replace current home page with 4-section dashboard:
1. **Recent Tickets** — Card grid with match scores, expandable details, date filter dropdown, scrollable, "View All" links to /data
2. **Upcoming Matches** — Match cards with date filter, "Predict" button (navigates to /predict with match selected), "Add to Ticket" button (adds to betslip)
3. **Account P&L** — LineChart (P&L over time) + stat cards (balance, P&L, ROI), period selector (7d/30d/90d/1y/custom)
4. **Job Logs** — Collapsible/expandable accordion of recent job runs with status, duration, errors

**Data Hub** (`src/routes/data/+page.svelte`) — REWRITE:
Unified data table with:
- Tab switcher: Matches | Predictions | Tickets
- Full-width data table with all columns
- Column selector (show/hide columns)
- Filters panel: date range, league, status, search
- Export button (CSV)
- Click row to open detail modal
- Pagination (server-side)

**Scraping** (`src/routes/scrape/+page.svelte`) — CREATE NEW:
Full page workflow:
- Country multi-select (searchable dropdown)
- League multi-select (grouped by country, searchable)
- Date range: "Past History" section (From/To date pickers) + "Future Matches" section (days/weeks/months/year selector)
- Auto-scrape toggle + interval selector (user-defined: hours/days/weeks)
- "Start Scrape" button → creates job
- Job list showing active/completed scrapes
- Per-match team scrape: select a match → "Scrape Both Teams" button
- Dedup toggle (skip existing matches)

**Predictions** (`src/routes/predict/+page.svelte`) — REWRITE:
- Same country/league/time selectors as Scraping page
- Strategy multi-select (checkboxes from /api/v1/strategies)
- Market multi-select (1X2, Over/Under, BTTS, Both Teams Score, Asian Handicap)
- "Run Prediction" button
- Results table: per-match, per-strategy, per-market
- Each row: match, strategy, market, predicted outcome, probability, confidence, edge
- Add new strategy button → modal to create strategy
- Auto-prediction toggle + interval

### API Client Additions

Create `$lib/api/dashboard.ts`:
```typescript
export const dashboardApi = {
  getSummary: () => get('/api/v1/dashboard/summary'),
  getRecentTickets: (params?: {limit?: number; date_from?: string; date_to?: string}) => get(`/api/v1/dashboard/recent-tickets?...`),
  getUpcoming: (days?: number) => get(`/api/v1/dashboard/upcoming?days=${days || 7}`),
  getJobLogs: (limit?: number) => get(`/api/v1/dashboard/job-logs?limit=${limit || 20}`)
};
```

Create `$lib/api/analytics.ts`:
```typescript
export const analyticsApi = {
  getPnl: (period?: string, group_by?: string) => get(`/api/v1/analytics/pnl?period=${period || '30d'}&group_by=${group_by || 'day'}`),
  getPnlByLeague: () => get('/api/v1/analytics/pnl/by-league'),
  getPnlByModel: () => get('/api/v1/analytics/pnl/by-model'),
  getEquityCurve: (period?: string) => get(`/api/v1/analytics/equity-curve?period=${period || '30d'}`)
};
```

Create `$lib/api/catalog.ts`:
```typescript
export const catalogApi = {
  getCountries: () => get('/api/v1/catalog/countries'),
  getLeagues: (country?: string) => get(`/api/v1/catalog/leagues${country ? `?country=${country}` : ''}`),
  getAllLeagues: () => get('/api/v1/catalog/leagues/all')
};
```

Create `$lib/api/strategies.ts`:
```typescript
export const strategiesApi = {
  list: () => get('/api/v1/strategies'),
  create: (data) => post('/api/v1/strategies', data),
  get: (id) => get(`/api/v1/strategies/${id}`),
  update: (id, data) => put(`/api/v1/strategies/${id}`, data),
  remove: (id) => del(`/api/v1/strategies/${id}`),
  run: (id, data) => post(`/api/v1/strategies/${id}/run`, data)
};
```

### Component Patterns

Use existing shadcn components from `$lib/components/ui/`:
- `Button`, `Card`, `Input`, `Select`, `Tabs`, `Badge`, `Table`, `Tooltip`, `Dialog`, `Sheet`, `Separator`, `DropdownMenu`, `Skeleton`

Use `cn()` from `$lib/utils.ts` for class merging.

All components use Svelte 5 runes: `$state`, `$derived`, `$effect`, `$props`, `{@render}`.

Charts use `layerchart`:
```svelte
<script>
  import { LineChart, BarChart, AreaChart } from 'layerchart';
</script>
```

Polling pattern (for live data):
```typescript
let interval: ReturnType<typeof setInterval>;
$effect(() => {
  fetchData();
  interval = setInterval(fetchData, 5000);
  return () => clearInterval(interval);
});
```

### File Naming

- Pages: `src/routes/<page>/+page.svelte`
- Page load: `src/routes/<page>/+page.ts` or `+page.server.ts`
- Components: `src/lib/components/<Name>.svelte`
- API modules: `src/lib/api/<domain>.ts`
- Types: `src/lib/types.ts`
