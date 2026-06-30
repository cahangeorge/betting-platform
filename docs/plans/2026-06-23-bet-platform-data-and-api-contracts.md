# Bet Platform Data and API Contracts

Date: 2026-06-23  
Scope: contracts needed to implement the 2026-06-23 product spec.  
Platform target: `frontend/` + `backend/`.

## 1. Contract principles

- The backend is the source of truth for matches, odds, predictions, tickets, jobs, and accounts.
- Frontend components should not infer settlement or verification from display-only fields.
- Result verification should be local-first:
  1. use stored final score/status when present,
  2. settle predictions/tickets from those local facts,
  3. scrape/fetch only missing match results/statuses,
  4. update only changed matches/tickets/predictions.
- Avoid full re-scraping for verification. Verification needs final scores and match status, not a complete odds/history scrape.
- Any long-running external scrape/prediction action must be represented as an inspectable job with logs.

## 2. Existing API inventory

Current backend route files already expose these useful surfaces:

| Area | Existing API surface |
|---|---|
| Dashboard | `/api/v1/dashboard/summary`, `/recent-tickets`, `/upcoming`, `/job-logs` |
| Analytics | `/api/v1/analytics/pnl`, `/pnl/by-league`, `/pnl/by-model`, `/equity-curve` |
| Scrape/data | `/api/v1/data/scrape`, `/scrape/{job_id}/execute`, `/world-cup-pipeline`, `/datasets` |
| Catalog | `/api/v1/catalog/countries`, `/leagues`, `/leagues/all` |
| Jobs | `/api/v1/jobs`, `/jobs/{job_id}`, `/jobs/{job_id}/toggle` |
| Matches | `/api/v1/matches`, `/matches/{match_id}`, `/matches/{match_id}/odds` |
| Predictions | `/api/v1/predictions/catalog`, `/run`, `/runs`, `/runs/{run_id}`, `/verification`, `/value-bets` |
| Strategies | `/api/v1/strategies`, `/strategies/{strategy_id}`, `/strategies/{strategy_id}/run` |
| Tickets | `/api/v1/tickets`, `/tickets/stats`, `/tickets/settle-due`, `/tickets/{ticket_id}`, `/tickets/{ticket_id}/place`, `/tickets/{ticket_id}/settle`, `/tickets/batches` |
| Account/bankroll | `/api/v1/bankroll`, `/bankroll/{id}/accounts`, `/bankroll/{id}/ledger` |
| Auth | `/api/v1/auth/signup`, `/login`, `/logout`, `/me` |

The product spec should reuse these endpoints where possible and add small missing endpoints only where the current contracts cannot support the UI cleanly.

## 3. Core domain records

### 3.1 Match

Required fields for UI and settlement:

- `id`
- `source`
- `source_match_id`
- `country`
- `league`
- `season`
- `home_team`
- `away_team`
- `kickoff_at`
- `status`: scheduled/live/finished/postponed/cancelled/unknown
- `minute`: nullable live minute
- `home_score`: nullable integer
- `away_score`: nullable integer
- `final_score`: derived display string when both scores exist
- `last_result_checked_at`
- `updated_at`

Indexes/filters needed:

- kickoff date range,
- status,
- country + league,
- source/source_match_id.

### 3.2 Odds snapshot / market price

Required fields:

- `id`
- `match_id`
- `bookmaker` or source label
- `market_type`
- `selection`
- `odds_decimal`
- `implied_probability`
- `captured_at`
- `source`

Use cases:

- ticket leg shows market odds at creation,
- prediction row shows market odds/implied probability,
- odds interval filter in `Bilete > Place bet`.

### 3.3 Prediction run

Required fields:

- `id`
- `created_at`
- `status`: queued/running/succeeded/partial/failed
- `input_hash`
- `input_params`: JSON with interval, countries, leagues, markets, strategies, model config
- `strategy_ids`
- `market_types`
- `match_count`
- `prediction_count`
- `started_at`
- `finished_at`
- `error_message`

Use cases:

- avoid reprediction by exact `input_hash`,
- list prediction automations/runs,
- show generated predictions for future matches,
- verify historical predictions by run.

### 3.4 Prediction selection

A prediction should be stored at selection/outcome level.

Required fields:

- `id`
- `prediction_run_id`
- `match_id`
- `strategy_id` or `model_name`
- `market_type`
- `selection`
- `probability`
- `confidence` or reliability score
- `odds_decimal`: odds snapshot used when prediction was generated
- `implied_probability`
- `edge` / expected value when available
- `status`: pending/won/lost/void/unresolved
- `actual_outcome`: nullable
- `settled_at`: nullable

Supported initial market settlement:

- `1x2`: home/draw/away,
- `btts`: yes/no,
- `over_under_2_5`: over/under.

### 3.5 Ticket batch / generation job

Required fields:

- `id`
- `created_at`
- `status`
- `input_params`: account, count, difficulty/safety, markets, odds interval, strategy filters
- `ticket_count`
- `tickets_settled_count`
- `tickets_total_count`
- `matches_settled_count`
- `matches_total_count`

Use cases:

- `Bilete > Istorice` lists jobs with generated ticket counts and settlement progress.

### 3.6 Ticket

Required fields:

- `id`
- `batch_id`: nullable for manually created tickets
- `bankroll_id` / account id
- `status`: draft/active/won/lost/void/cancelled
- `stake`
- `total_odds`
- `win_probability`
- `potential_return`
- `return_amount`
- `pnl`
- `created_at`
- `placed_at`
- `settled_at`
- `legs_settled_count`
- `legs_total_count`

### 3.7 Ticket leg

Required fields:

- `id`
- `ticket_id`
- `match_id`
- `model_prediction_id` / prediction selection id where available
- `market_type`
- `selection`
- `odds_decimal`
- `probability`
- `status`: pending/won/lost/void/unresolved
- `home_score`
- `away_score`: optional denormalized display snapshot or joined from match
- `settled_at`

Use cases:

- settlement,
- dashboard ticket panel,
- active ticket progress,
- ticket swap UX.

### 3.8 Strategy

Required fields:

- `id`
- `name`
- `strategy_type`
- `source`: custom/penaltyblog/soccerdata/other
- `market_types`
- `config`: typed JSON
- `enabled`
- `created_at`
- `updated_at`

Additional operation:

- duplicate strategy by copying all editable fields under a new name.

### 3.9 Scrape job / scheduled job

Required fields:

- `id`
- `job_type`
- `name`
- `status`
- `parameters`: countries, leagues, historic/future ranges, avoid_rescraping, autoscrape
- `created_at`
- `started_at`
- `finished_at`
- `records_inserted`
- `records_updated`
- `records_skipped`
- `error_message`

### 3.10 Job log

Required fields:

- `id`
- `job_id`
- `timestamp`
- `level`: debug/info/warning/error
- `action`
- `message`
- `metadata`: JSON

The UI logs panel should query by `job_id`, `level`, and pagination parameters.

## 4. Proposed endpoint contracts

This section lists the endpoint shape needed by the product spec. If an existing endpoint already supports the shape, reuse it. If not, add a narrow endpoint rather than overloading unrelated routes.

### 4.1 Dashboard historical tickets chart

`GET /api/v1/dashboard/ticket-outcomes?range=7d&bucket=day`

Response:

```json
{
  "range": "7d",
  "bucket": "day",
  "items": [
    {
      "bucket_start": "2026-06-23T00:00:00Z",
      "bucket_end": "2026-06-24T00:00:00Z",
      "won": 3,
      "lost": 2,
      "void": 0,
      "ticket_ids": ["..."]
    }
  ]
}
```

`GET /api/v1/dashboard/ticket-outcomes/{bucket_key}/tickets?range=7d`

Response should reuse ticket detail models including legs, odds, probabilities, and final score.

### 4.2 Prediction verification summary

Existing candidate: `GET /api/v1/predictions/verification?run_id=...`

Required response shape:

```json
{
  "run_id": "optional",
  "checked_predictions": 100,
  "resolved_predictions": 80,
  "correct_predictions": 52,
  "accuracy": 65.0,
  "items": [
    {
      "prediction_id": "...",
      "match_id": "...",
      "match_label": "Home vs Away",
      "kickoff_at": "2026-06-20T19:00:00Z",
      "market_type": "1x2",
      "predicted_outcome": "home",
      "actual_outcome": "home",
      "probability": 0.61,
      "odds_decimal": 1.95,
      "status": "won",
      "final_score": "2-0"
    }
  ]
}
```

### 4.3 Future matches with predictions

Option A: extend `GET /api/v1/dashboard/upcoming` to include prediction details.

Option B: add:

`GET /api/v1/predictions/upcoming?from=...&to=...&country=...&league=...&market_type=...`

Response item:

```json
{
  "match_id": "...",
  "kickoff_at": "2026-06-25T18:00:00Z",
  "country": "England",
  "league": "Premier League",
  "home_team": "Team A",
  "away_team": "Team B",
  "predictions": [
    {
      "prediction_id": "...",
      "run_id": "...",
      "market_type": "1x2",
      "selection": "home",
      "probability": 0.58,
      "confidence": 0.72,
      "odds_decimal": 2.1
    }
  ]
}
```

### 4.4 Future/active tickets

Existing candidates:

- `GET /api/v1/tickets?status=active`
- `GET /api/v1/tickets/{ticket_id}`
- `POST /api/v1/tickets/settle-due`

Required filters:

- status,
- date range,
- batch/job id,
- pagination.

### 4.5 Scrape catalog

Existing candidates:

- `GET /api/v1/catalog/countries`
- `GET /api/v1/catalog/leagues`
- `GET /api/v1/catalog/leagues/all`

Required behavior:

- countries endpoint includes special groups such as World Cup when supported,
- leagues endpoint accepts selected country/group filters,
- returned IDs are stable enough for saved jobs.

### 4.6 Scrape job create/run

Existing candidates:

- `POST /api/v1/data/scrape`
- `POST /api/v1/data/scrape/{job_id}/execute`
- `GET /api/v1/data/scrape`
- `GET /api/v1/data/scrape/{job_id}`

Required create input:

```json
{
  "job_type": "scrape_odds",
  "name": "England Premier League next 7d + 2y history",
  "countries": ["england"],
  "leagues": ["premier-league"],
  "historic_range": { "days": 0, "weeks": 0, "months": 0, "years": 2 },
  "future_range": { "days": 7, "weeks": 0, "months": 0, "years": 0 },
  "avoid_rescraping": true,
  "autoscrape": false
}
```

### 4.7 Job logs

Existing candidate: `GET /api/v1/dashboard/job-logs`

If it does not return exhaustive logs, add:

`GET /api/v1/jobs/{job_id}/logs?level=info&page=1&per_page=100`

Response:

```json
{
  "items": [
    {
      "timestamp": "2026-06-23T10:00:00Z",
      "level": "info",
      "action": "records_upserted",
      "message": "Inserted 4 matches, updated 12 odds rows",
      "metadata": { "inserted": 4, "updated": 12 }
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 100
}
```

### 4.8 Prediction run create with avoid reprediction

Existing candidate: `POST /api/v1/predictions/run`

Required input additions:

```json
{
  "interval": { "days": 7, "weeks": 0, "months": 0, "years": 0 },
  "countries": ["england"],
  "leagues": ["premier-league"],
  "market_types": ["1x2", "btts"],
  "strategy_ids": ["..."],
  "autopredict": false,
  "avoid_reprediction": true
}
```

Required behavior:

- Compute canonical `input_hash` from exact normalized input.
- If `avoid_reprediction=true` and a successful run with same hash exists, return that run with `deduped: true`.
- If any input differs, create a new run.

### 4.9 Strategy duplicate

Existing strategy CRUD exists. Add if missing:

`POST /api/v1/strategies/{strategy_id}/duplicate`

Input:

```json
{ "name": "Copy of Balanced 1x2" }
```

Response: strategy response for the created copy.

### 4.10 Ticket generation and swapping

Existing candidate: `POST /api/v1/tickets` may be reused for creation if it supports generated ticket batches. Otherwise add:

`POST /api/v1/tickets/generate`

Input:

```json
{
  "account_id": "...",
  "ticket_count": 10,
  "difficulty": "balanced",
  "market_types": ["1x2", "btts"],
  "min_odds": 1.4,
  "max_odds": 3.5
}
```

Response:

```json
{
  "batch_id": "...",
  "tickets": [
    {
      "ticket_id": "...",
      "win_probability": 0.42,
      "total_odds": 4.2,
      "legs": []
    }
  ]
}
```

For swapping legs:

`POST /api/v1/tickets/batches/{batch_id}/swap-legs`

Input:

```json
{
  "source_ticket_id": "...",
  "source_leg_id": "...",
  "target_ticket_id": "...",
  "target_leg_id": "..."
}
```

Response should return updated source and target tickets with recalculated odds/probability.

### 4.11 Data page pagination

Recommended query conventions:

- `GET /api/v1/matches?page=1&per_page=25&status=finished`
- `GET /api/v1/predictions/runs?page=1&per_page=25`
- `GET /api/v1/tickets?page=1&per_page=25`

All paginated responses should use:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "per_page": 25
}
```

If legacy endpoints return arrays, frontend can temporarily paginate client-side, but server-side pagination is the target for large tables.

## 5. Verification and settlement setup

### 5.1 Most performant result-checking setup

Do not re-run full scraping to verify tickets/predictions. Use this staged setup:

1. Scheduled lightweight result sync
   - Query only matches that are scheduled/live/pending and whose kickoff time is in the past or near future.
   - Fetch final score/status only.
   - Upsert match status and score.

2. Local settlement job
   - Run `settle_due_tickets` and prediction verification against local match rows.
   - Update ticket legs, ticket status, prediction status, returns, and PnL.

3. Targeted scrape fallback
   - If final score is missing after expected completion, enqueue a targeted result scrape for that match/league/date only.
   - Do not scrape odds/history again unless explicitly requested.

4. UI refresh
   - Dashboard and Bilete read stored settlement state.
   - Predictii reads stored verification state or calculates lightweight verification from local match results.

Benefits:

- minimal network calls,
- fast UI,
- deterministic re-checks,
- auditable state,
- avoids upstream scraper load and HTML fragility.

### 5.2 Settlement logic requirements

Initial market settlement:

- `1x2`
  - home wins if `home_score > away_score`,
  - draw if equal,
  - away wins if `away_score > home_score`.
- `btts`
  - yes if both teams score at least one goal,
  - no otherwise.
- `over_under_2_5`
  - over if total goals > 2.5,
  - under if total goals < 2.5.

A ticket is:

- won if all non-void legs are won,
- lost if at least one leg is lost,
- pending if at least one required leg is unresolved and none are lost,
- void if all legs are void or cancelled according to business rules.

## 6. Frontend type contracts

Add or reuse TypeScript types under `frontend/src/lib/types.ts` for:

- `DashboardTicketOutcomeBucket`,
- `DashboardTicketOutcomeDetail`,
- `PredictionVerificationSummary`,
- `UpcomingPredictionMatch`,
- `ScrapeRangeInput`,
- `ScrapeJobLogEntry`,
- `PredictionRunInput`,
- `TicketBatchSummary`,
- `GeneratedTicket`,
- `TicketSwapRequest`,
- `PaginatedResponse<T>`.

## 7. Compatibility notes

- Current endpoints may not exactly match these target contracts; implement adapters in `frontend/src/lib/api/` while backend changes land incrementally.
- Existing `/api/v1/predictions/verification` and `/api/v1/tickets/settle-due` are the preferred foundation for result verification.
- Existing `/api/v1/catalog/*` should remain the source of truth for country/league multiselects.
