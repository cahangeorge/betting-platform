# Frontend Real-Backend E2E Design

## Goal

Add a real browser E2E test system for `frontend/` that exercises:

1. the real frontend,
2. the real backend,
3. the real auth / bankroll / matches / prediction / ticket flows,
4. and, in a separate opt-in suite, the real scrape bridges against live upstream data.

The design must support both:

- a stable default regression suite for regular development, and
- a live end-to-end validation suite for full-stack scrape-to-ticket verification.

## Scope

This work targets the Svelte frontend project in `frontend/`, while intentionally using the running backend in `backend/`.

In scope:

- Playwright-based E2E harness under `frontend/`
- Browser-driven authenticated flows
- Real backend setup and cleanup helpers
- Stable hybrid suite
- Opt-in live scrape suite
- Scripts and config for running both suites

Out of scope:

- Replacing existing shell/API flow scripts in `tests/`
- Mock-only frontend tests
- Making live upstream scraping reliable in CI
- Broad backend refactors unrelated to testability

## Constraints

- The frontend suite must talk to a real backend.
- The hybrid suite must not depend on live upstream scraper success.
- The live suite must intentionally depend on real scraper bridges and upstream data.
- No fake frontend demo fallback is acceptable in tested flows.
- Tests must isolate their own users and data as much as practical.
- The design should fit the current repo rather than inventing a separate test platform.

## Test Suite Split

### Suite A: Hybrid Real-Backend E2E

Purpose:
- Default suite for regression detection.
- Exercises the real frontend and real backend flows with deterministic setup.

Data strategy:
- Try real backend entrypoints first where useful.
- If scrape/bridge/upstream does not produce usable state, seed deterministic data directly into backend storage using controlled setup helpers.

Reliability expectation:
- Should fail on product regressions, not because an upstream site changed HTML.

Default command:
- `npm run test:e2e`

### Suite B: Live Full E2E

Purpose:
- Validate the complete real chain:
  `frontend -> backend -> scraper bridges -> live upstream data -> predictions -> betslip -> tickets`

Data strategy:
- No deterministic fallback for the core live scrape path.
- Fail honestly when bridges, credentials, runtime, or upstream data are broken.

Reliability expectation:
- Intentionally flaky relative to the hybrid suite.
- Opt-in only.

Default command:
- `npm run test:e2e:live`

## Directory Layout

Add this structure under `frontend/`:

```text
frontend/
  playwright.config.ts
  tests/
    e2e/
      fixtures/
      helpers/
        auth.ts
        backend.ts
        cleanup.ts
        seed.ts
        scrape.ts
      hybrid/
        auth-dashboard.spec.ts
        dashboard-slip-ticket.spec.ts
        predict-slip-ticket.spec.ts
        live-value-data.spec.ts
        scrape-job-honesty.spec.ts
      live/
        live-scrape-predict-ticket.spec.ts
```

## Runtime Model

### Frontend

Playwright will run against the real frontend dev server for `frontend/`.

Preferred behavior:
- Start frontend from Playwright config using the project package manager and script.
- Use a fixed local port.

### Backend

The suite assumes a real backend is already running and reachable via environment configuration.

Reason:
- The user explicitly wants backend functionality covered.
- The backend has its own runtime and dependencies and should be treated as an external system from the frontend test harness perspective.

Validation at suite startup:
- health endpoint reachable,
- auth endpoints reachable,
- database-backed API behavior available.

If backend is unavailable, the suite should fail immediately with a clear message.

## Environment Contract

Add explicit E2E environment variables for the frontend test harness:

- `E2E_FRONTEND_URL`
- `E2E_BACKEND_URL`
- `E2E_MODE=hybrid|live`
- `E2E_ALLOW_DB_SEED=1` for hybrid mode setup
- `E2E_LIVE_SCRAPE_TIMEOUT_SECONDS`

Optional:

- `E2E_ADMIN_EMAIL`
- `E2E_ADMIN_PASSWORD`

These are not required if the suite can create isolated test users directly through public auth endpoints.

## Data Setup Strategy

### Shared Principles

- Every run gets a unique test namespace using timestamp or UUID-based emails/names.
- Cleanup must remove test-created tickets, bankrolls, sessions, users, and seeded matches where possible.
- Setup helpers should be idempotent enough for reruns after partial failure.

### Hybrid Mode Setup

Hybrid mode should use a layered setup pipeline:

1. Create a fresh user through public auth endpoints.
2. Create bankroll through backend API.
3. Attempt scrape/data job creation through backend API when that helps validate backend behavior.
4. Check whether the resulting data is sufficient for UI flows.
5. If not sufficient, seed deterministic backend data directly.
6. Seed prediction-ready historical/training data as needed.
7. Seed or trigger prediction runs so frontend predict flows have stable usable state.

This design preserves backend coverage while preventing scraper instability from invalidating the default suite.

### Live Mode Setup

Live mode should:

1. Create a fresh user and bankroll.
2. Trigger real scrape jobs via backend endpoints.
3. Poll for scrape completion / failure.
4. Verify real match data was ingested.
5. Trigger predictions against that real data.
6. Continue to betslip/ticket flow only if data is genuinely present.

If any step fails, the suite fails with a concrete reason tied to the real chain.

## Flow Coverage

### Hybrid Flow 1: Auth -> Dashboard

Path:
- signup or login
- land on authenticated dashboard
- verify operational widgets render
- verify no redirect loops and no fake empty public shell

Checks:
- authenticated navbar state
- dashboard sections visible
- real backend-driven content or explicit empty state

### Hybrid Flow 2: Dashboard -> Betslip -> Tickets -> Place Ticket

Path:
- authenticate
- open dashboard
- add a selection from dashboard
- navigate to tickets
- confirm betslip state survives
- place ticket through real backend

Checks:
- betslip count updates
- ticket review reflects selected legs
- ticket creation response is persisted and visible in UI

### Hybrid Flow 3: Predict -> Add Result -> Tickets -> Place Ticket

Path:
- authenticate
- open predict page
- use existing or seeded prediction results
- add a prediction result to betslip
- navigate to tickets
- place ticket

Checks:
- result rows render from backend state
- add action updates shared betslip
- placed ticket reflects selected market/selection

### Hybrid Flow 4: Live / Value / Data Surfaces Honesty

Path:
- authenticate
- visit `/live`, `/value-bets`, `/data`

Checks:
- pages render real backend-fed state
- if data is absent, explicit unavailable or empty states appear
- no fake demo dataset is silently shown

### Hybrid Flow 5: Scrape Job Honesty

Path:
- authenticate
- visit scrape page
- trigger scrape job through UI or test-assisted API setup
- observe status transitions

Checks:
- queued/running/completed/failed states surface honestly
- frontend does not treat failed scrape as success

### Live Flow 1: Full Live Scrape -> Predict -> Ticket

Path:
- authenticate
- trigger real scrape
- wait for real ingestion
- open data/predict pages
- run or consume predictions
- add to betslip
- place ticket

Checks:
- upstream-fed data appears in UI
- prediction flow works on that data
- ticket creation succeeds on selections derived from the live path

## Test Isolation and Cleanup

Cleanup helpers should remove:

- sessions for test users,
- test users,
- bankrolls and ledger entries tied to them,
- tickets, ticket legs, settlements, placements tied to them,
- prediction runs and seeded predictions owned by the test namespace,
- deterministic seeded matches used only for hybrid mode.

Live-ingested external data should not be broadly deleted unless namespaced in a safe way. Hybrid seeded data must be namespaced to allow targeted cleanup.

## Playwright Configuration

The config should:

- use one project initially for Chromium,
- start the frontend web server,
- reuse backend URL from env,
- separate hybrid and live tests by directory or grep tags,
- support longer timeouts for live scrape mode,
- emit traces/screenshots on failure,
- keep reporters simple and local-first.

Recommended initial behavior:

- default reporter: `list`
- retries: low in hybrid, zero or one in live
- screenshots: `only-on-failure`
- trace: `retain-on-failure`

## Helper Boundaries

### `auth.ts`

Responsibilities:
- signup/login test users
- establish browser auth state

### `backend.ts`

Responsibilities:
- health checks
- low-level API helpers
- polling helpers

### `seed.ts`

Responsibilities:
- deterministic hybrid data seeding
- namespaced historical matches
- prediction-ready fixtures in real backend storage

### `scrape.ts`

Responsibilities:
- create/execute scrape jobs
- poll status
- verify resulting ingestion

### `cleanup.ts`

Responsibilities:
- delete test-created entities
- tolerate partial prior failures

This keeps test specs focused on user behavior rather than setup mechanics.

## Failure Semantics

Hybrid suite failures should clearly distinguish:

- backend unavailable,
- setup helper failure,
- UI regression,
- ticket/prediction API regression,
- scrape endpoint honesty regression.

Live suite failures should clearly distinguish:

- backend unavailable,
- bridge/runtime misconfiguration,
- scrape job execution failure,
- no usable ingested data,
- downstream predict/ticket regression.

The report should make it obvious whether the product failed or the live external chain failed.

## Scripts

Add scripts to `frontend/package.json`:

- `test:e2e` for hybrid suite
- `test:e2e:live` for live suite

Optional follow-up:

- `test:e2e:headed`
- `test:e2e:debug`

The default suite should not require the live scrape chain.

## Why This Design

This design gives the user both requested qualities:

- a real frontend plus real backend regression suite that is practical to run often,
- and a true live-system validation suite that covers scraping through ticket placement.

It avoids the main failure mode of E2E systems for scraper-driven products: making every regression test depend on unstable upstream websites.

## Implementation Notes

- Start with Chromium only.
- Start with one stable authenticated storage-state path only if needed; otherwise create users per test.
- Prefer API-assisted setup over brittle UI setup for non-user-facing prerequisites like bankroll creation and deterministic data preparation.
- Keep live suite opt-in and explicitly documented as environment-sensitive.

## Open Decisions Resolved

- The project will support both live and hybrid modes.
- The hybrid suite will be the default.
- The live suite will intentionally exercise real scrape bridges and upstream data.
- Backend setup helpers are allowed to use backend APIs and targeted database preparation for hybrid mode.
