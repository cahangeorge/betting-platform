# Implementation Roadmap: 2026-06-23 Bet Platform UI and Operations Plan

Date: 2026-06-23  
Scope: implementation tasks for Dashboard, Scrape, Predictii, Bilete, Account, Date, Board deletion, and Configuratii.  
Target: `frontend/` and `backend/` only.

## 1. Assumptions

- The active platform is the SvelteKit app in `frontend/` and FastAPI app in `backend/`.
- `betfront/` and `frontbet/` remain untouched.
- The product spec is implemented incrementally, not as one huge rewrite.
- Existing result settlement/verification APIs should be reused before adding new scraping.
- Board functionality should be removed from navigation and replaced by Dashboard `Viitor` surfaces.
- Historical scraping should be explicit user-selected jobs, not hidden pipeline behavior.

## 2. Implementation order

The dependency order is:

1. data/API contracts and shared frontend types,
2. result verification and pagination foundations,
3. Dashboard historical/future panels,
4. Scrape controls/logs,
5. Predictii controls/metrics,
6. Bilete generation/history/swap UX,
7. Account and Configuratii improvements,
8. Board deletion and navigation cleanup,
9. full verification pass.

## 3. Phase 0: documentation and contract checkpoint

### Task 0.1: Commit product spec and API contracts

Acceptance:

- Product spec exists in `docs/plans/2026-06-23-bet-platform-product-spec.md`.
- API contracts exist in `docs/plans/2026-06-23-bet-platform-data-and-api-contracts.md`.
- Roadmap exists in `docs/plans/2026-06-23-bet-platform-implementation-roadmap.md`.
- Test plan exists in `docs/plans/2026-06-23-bet-platform-test-plan.md`.

Verify:

- `git diff --check docs/plans`.

Files:

- `docs/plans/*.md`.

## 4. Phase 1: API and type foundations

### Task 1.1: Normalize paginated response contracts for Data page

Acceptance:

- Matches, predictions, and tickets can be requested with page/per-page parameters.
- Frontend has a reusable `PaginatedResponse<T>` type.
- Data page can show rows-per-page and next/prev controls above each table.

Verify:

- Backend tests for pagination shape.
- `pnpm check`.

Likely files:

- `backend/app/api/v1/matches.py`
- `backend/app/api/v1/predictions.py`
- `backend/app/api/v1/tickets.py`
- `frontend/src/lib/types.ts`
- `frontend/src/lib/api/*.ts`
- `frontend/src/routes/data/+page.svelte`

### Task 1.2: Add dashboard ticket outcome contract

Acceptance:

- API returns ticket win/loss buckets for today, 7d, 1m, 3m, 6m, 1y.
- API returns ticket details for a selected bucket.
- Frontend API client exposes typed methods.

Verify:

- Backend test seeds won/lost tickets and checks bucket counts.
- Unit test for frontend bucket formatting.

Likely files:

- `backend/app/api/v1/dashboard.py`
- `backend/app/schemas/dashboard.py` or existing schema location
- `frontend/src/lib/api/dashboard.ts`
- `frontend/src/lib/types.ts`

### Task 1.3: Extend future predictions and active ticket contracts

Acceptance:

- Future matches can be listed with generated predictions.
- Active/future tickets can be listed with settled/total progress.
- Current endpoints are reused where possible.

Verify:

- Backend tests for future match with and without prediction.
- Frontend unit test for mapping active ticket progress.

Likely files:

- `backend/app/api/v1/dashboard.py`
- `backend/app/api/v1/predictions.py`
- `backend/app/api/v1/tickets.py`
- `frontend/src/lib/api/dashboard.ts`
- `frontend/src/lib/api/predictions.ts`
- `frontend/src/lib/api/tickets.ts`

Checkpoint after Phase 1:

- `cd backend && pytest`
- `cd frontend && pnpm check && pnpm test:unit`

## 5. Phase 2: Dashboard tabs and charts

### Task 2.1: Add Dashboard `Istoric` / `Viitor` tabs

Acceptance:

- Dashboard shows two top-level tabs.
- `Istoric` contains the historical ticket chart and prediction detail section.
- `Viitor` contains future matches/predictions and future tickets.
- Mobile layout has no accidental x-axis page scroll.

Verify:

- `pnpm check`.
- Playwright route check at desktop and mobile widths.

Likely files:

- `frontend/src/routes/+page.svelte`
- `frontend/src/lib/components/charts/*`
- possibly new dashboard components under `frontend/src/lib/components/`.

### Task 2.2: Implement ticket win/loss bar chart and details panel

Acceptance:

- Range selector supports today, week, month, 3m, 6m, 1y.
- Bars use green for won and red for lost.
- Clicking a bar opens a panel with matching tickets and leg details.

Verify:

- Frontend unit test for grouping/range labels.
- Playwright clicks bar and sees ticket details.

Likely files:

- `frontend/src/routes/+page.svelte`
- `frontend/src/lib/components/charts/TicketOutcomeBars.svelte`
- `frontend/src/lib/components/TicketDetailsPanel.svelte`
- `frontend/src/lib/api/dashboard.ts`

### Task 2.3: Implement prediction verification chart/details

Acceptance:

- Historical predictions show won/lost/pending/void status.
- Summary metrics show checked/resolved/correct/accuracy.
- Uses local verification API, not re-scraping.

Verify:

- Backend prediction verification tests.
- Playwright sees metrics for seeded prediction.

Likely files:

- `frontend/src/routes/+page.svelte`
- `frontend/src/lib/components/charts/PredictionVerificationChart.svelte`
- `frontend/src/lib/api/predictions.ts`

### Task 2.4: Implement future matches/predictions and future tickets sections

Acceptance:

- Dashboard `Viitor` lists future matches with prediction status.
- Future tickets show progress and expandable leg details.

Verify:

- Playwright seeded future prediction/ticket smoke.

Likely files:

- `frontend/src/routes/+page.svelte`
- `frontend/src/lib/components/FuturePredictionsPanel.svelte`
- `frontend/src/lib/components/FutureTicketsPanel.svelte`

Checkpoint after Phase 2:

- `cd frontend && pnpm check && pnpm test:unit && pnpm build`
- Dashboard Playwright smoke for `/`.

## 6. Phase 3: Scrape page

### Task 3.1: Add automatic scraping actions section

Acceptance:

- Saved scheduled scrape jobs/actions are listed as buttons/cards.
- Enabled/running/last status is visible.

Verify:

- Unit test for scheduled job mapping.
- Browser check `/scrape`.

Likely files:

- `frontend/src/routes/scrape/+page.svelte`
- `frontend/src/lib/api/jobs.ts`

### Task 3.2: Add country/league multiselects from catalog

Acceptance:

- Countries/special competitions are loaded from catalog.
- League dropdown filters by selected countries/competitions.
- Multi-select works for multiple countries and leagues.

Verify:

- Unit test for catalog filtering.
- Playwright selects country and sees expected leagues.

Likely files:

- `frontend/src/routes/scrape/+page.svelte`
- `frontend/src/lib/api/catalog.ts`
- reusable multiselect component if needed.

### Task 3.3: Add historic and future range fields

Acceptance:

- Historic days/weeks/months/years fields exist.
- Future days/weeks/months/years fields exist.
- Submitted scrape job contains both ranges.

Verify:

- Frontend unit test for payload construction.
- Backend test for job parameter persistence if API changes.

Likely files:

- `frontend/src/routes/scrape/+page.svelte`
- `frontend/src/lib/api/data.ts`
- `backend/app/api/v1/data.py`

### Task 3.4: Add avoid rescraping, autoscrape, start scraping controls

Acceptance:

- Controls are visible and persisted in scrape job parameters.
- Avoid rescraping prevents duplicate work when backend supports it.

Verify:

- Frontend unit test for form payload.
- Backend test for duplicate/skip behavior.

Likely files:

- `frontend/src/routes/scrape/+page.svelte`
- `backend/app/services/scraper.py`

### Task 3.5: Add exhaustive logs panel

Acceptance:

- Button toggles logs panel.
- Logs can be filtered by job.
- Logs show actions, warnings, errors, and metadata.

Verify:

- Playwright opens logs panel and sees seeded job log.

Likely files:

- `backend/app/api/v1/jobs.py`
- `backend/app/api/v1/dashboard.py` if reusing job logs
- `frontend/src/routes/scrape/+page.svelte`
- `frontend/src/lib/components/JobLogsPanel.svelte`

Checkpoint after Phase 3:

- `cd backend && pytest`
- `cd frontend && pnpm check && pnpm test:unit`
- Playwright `/scrape` smoke.

## 7. Phase 4: Predictii page

### Task 4.1: Add prediction metrics section

Acceptance:

- Shows checked/resolved/won/lost/accuracy/pending.
- Uses verification endpoint or stored verification summary.

Verify:

- Playwright seeded prediction metrics.

Likely files:

- `frontend/src/routes/predict/+page.svelte`
- `frontend/src/lib/api/predictions.ts`

### Task 4.2: Add automatic prediction actions section

Acceptance:

- Saved/running automatic prediction jobs are listed.
- Each shows name, markets, strategies, status, last run.

Verify:

- Unit test for action mapping.

Likely files:

- `frontend/src/routes/predict/+page.svelte`
- `frontend/src/lib/api/jobs.ts`

### Task 4.3: Add future predictions list with period selector

Acceptance:

- User can choose day/week/month display range.
- Future generated predictions are listed with probability/confidence.

Verify:

- Playwright seeded future prediction row visible.

Likely files:

- `frontend/src/routes/predict/+page.svelte`
- `frontend/src/lib/api/predictions.ts`

### Task 4.4: Add prediction run form with exact dedupe

Acceptance:

- Time fields, country/league multiselect, market multiselect, strategy multiselect exist.
- Autopredict and avoid reprediction toggles exist.
- Exact input hash dedupes only identical successful runs.

Verify:

- Backend test: identical input dedupes, changed input creates new run.
- Frontend unit test for canonical payload.

Likely files:

- `backend/app/api/v1/predictions.py`
- `backend/app/services/prediction_engine.py`
- `frontend/src/routes/predict/+page.svelte`
- `frontend/src/lib/api/predictions.ts`

Checkpoint after Phase 4:

- `cd backend && pytest`
- `cd frontend && pnpm check && pnpm test:unit`
- Playwright `/predict` smoke.

## 8. Phase 5: Bilete page

### Task 5.1: Add ticket metrics section

Acceptance:

- Metrics show active/won/lost/void/settled/win rate/stake/return/PnL.
- Metrics reflect settled ticket state.

Verify:

- Backend ticket stats test.
- Playwright sees seeded metrics.

Likely files:

- `frontend/src/routes/tickets/+page.svelte`
- `frontend/src/lib/components/TicketsPanel.svelte`
- `frontend/src/lib/api/tickets.ts`

### Task 5.2: Implement Active tab panels

Acceptance:

- Unfinished tickets are listed.
- Each expands to show minute/status/final score and leg progress.

Verify:

- Playwright expands active ticket and sees leg status.

Likely files:

- `frontend/src/lib/components/TicketsPanel.svelte`
- new ticket panel child components if needed.

### Task 5.3: Implement Istorice tab by ticket-generation job

Acceptance:

- Jobs/batches list generated ticket count.
- Selecting a job shows all tickets and settlement progress.

Verify:

- Backend batch API test.
- Playwright selects seeded batch and sees tickets.

Likely files:

- `backend/app/api/v1/tickets.py`
- `frontend/src/lib/api/tickets.ts`
- `frontend/src/lib/components/TicketsPanel.svelte`

### Task 5.4: Implement Place bet generation form

Acceptance:

- Account selector, ticket count, difficulty/safety, markets, odds interval, generate button exist.
- Generated tickets show immediately in a panel.

Verify:

- Frontend unit test for generation payload.
- Playwright generates from seeded predictions.

Likely files:

- `backend/app/services/ticket_engine.py`
- `backend/app/api/v1/tickets.py`
- `frontend/src/lib/components/TicketsPanel.svelte`

### Task 5.5: Add simple leg swap UX

Acceptance:

- User can select source leg and target slot/ticket.
- Confirming swap recalculates affected ticket probability and odds.
- No raw JSON editing is required.

Verify:

- Backend swap endpoint test.
- Playwright performs a swap and sees updated odds/probability.

Likely files:

- `backend/app/api/v1/tickets.py`
- `backend/app/services/ticket_engine.py`
- `frontend/src/lib/components/TicketSwapPanel.svelte`

Checkpoint after Phase 5:

- `cd backend && pytest`
- `cd frontend && pnpm check && pnpm test:unit && pnpm build`
- Playwright `/tickets` smoke.

## 9. Phase 6: Account, Data, Configuratii, Board deletion

### Task 6.1: Account list/create

Acceptance:

- Account page lists bankroll/account records.
- User can create a new betting account.
- Newly created account can be selected on `Bilete > Place bet`.

Verify:

- Backend account create test if missing.
- Playwright creates account and sees it in tickets form.

Likely files:

- `frontend/src/routes/account/+page.svelte`
- `backend/app/api/v1/bankroll.py`

### Task 6.2: Data page tabs and pagination controls

Acceptance:

- Tabs: scraped matches, generated predictions, generated tickets.
- Each table has rows-per-page, previous, next controls above it.

Verify:

- Playwright switches tabs and changes page size.

Likely files:

- `frontend/src/routes/data/+page.svelte`
- `frontend/src/lib/api/matches.ts`
- `frontend/src/lib/api/predictions.ts`
- `frontend/src/lib/api/tickets.ts`

### Task 6.3: Configuratii strategy management page

Acceptance:

- `/configuratii` exists.
- Strategies are listed and editable.
- User can create a strategy.
- User can duplicate a strategy and edit the copy.

Verify:

- Backend duplicate endpoint test.
- Playwright creates/duplicates strategy.

Likely files:

- `backend/app/api/v1/strategies.py`
- `frontend/src/routes/configuratii/+page.svelte`
- `frontend/src/lib/api/strategies.ts`
- navigation components.

### Task 6.4: Delete Board page from UI

Acceptance:

- `/board` route files are removed or route redirects intentionally.
- Sidebar and command palette no longer show Board.
- Any valuable future-match content is represented on Dashboard `Viitor`.

Verify:

- `rg "Board|/board" frontend/src` returns no active nav references except redirects/tests if intentionally kept.
- Playwright navigation smoke does not include Board.

Likely files:

- `frontend/src/routes/board/*`
- `frontend/src/lib/components/Sidebar.svelte`
- `frontend/src/lib/components/CommandPalette.svelte`

Checkpoint after Phase 6:

- `cd backend && pytest`
- `cd frontend && pnpm check && pnpm test:unit && pnpm build`

## 10. Phase 7: integrated verification and cleanup

### Task 7.1: End-to-end scrape to prediction to ticket verification smoke

Acceptance:

- Seed or create a finished match.
- Generate prediction.
- Generate ticket.
- Run settlement/verification.
- Dashboard, Predictii, Bilete, and Date all show consistent status.

Verify:

- Python Playwright or frontend Playwright hybrid test.

### Task 7.2: Mobile/desktop layout verification

Acceptance:

- No accidental page-level x-axis scroll on Dashboard, Scrape, Predictii, Bilete, Account, Date, Configuratii.

Verify:

- Playwright checks `document.documentElement.scrollWidth <= clientWidth` at widths 1440, 1024, 390, 320.

### Task 7.3: Final code quality pass

Acceptance:

- No dead Board nav references.
- No silent fake-data fallbacks in operational screens.
- Docs reflect implemented contracts.

Verify:

- `git diff --check`
- `cd backend && pytest`
- `cd frontend && pnpm check && pnpm test:unit && pnpm build`
- relevant Playwright suite.

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---:|---|
| Full product scope is large | High | Implement by vertical slices and keep each checkpoint shippable. |
| Scraper/live sources are slow or fragile | High | Keep result verification local-first and scrape only missing scores. |
| Current endpoints return arrays instead of paginated objects | Medium | Add adapters first; migrate endpoints incrementally. |
| Strategy configs differ by model/source | Medium | Store typed display metadata where available and fallback to JSON editor only for advanced fields. |
| Ticket swap can create invalid duplicate legs | Medium | Validate at backend before saving and return recalculated ticket summaries. |
| Board deletion removes useful future fixture visibility | Low | Move useful future views into Dashboard `Viitor` before removing nav. |

## 12. Current status tracker

Use this section during implementation and publication.

### 2026-07-01 implementation status update

Implemented in this pass:

- Backend scheduled-job orchestration now supports:
  - `verify_results` / settlement-style hourly checks,
  - `generate_tickets`,
  - `scrape_then_predict`,
  - `predict -> tickets`,
  - `scrape -> predict -> tickets`,
  - scheduled `world_cup_pipeline` routing to the real pipeline service.
- Frontend Scrape/Tickets surfaces now expose:
  - saved automatic verification jobs,
  - saved automatic ticket-generation jobs,
  - saved scrape -> predict orchestration,
  - saved scrape -> predict -> tickets orchestration.
- Test coverage added:
  - backend scheduler tests for ticket-generation and full orchestration dispatch,
  - frontend unit coverage for scheduled-job bucket classification,
  - hybrid Playwright spec `frontend/tests/e2e/hybrid/scrape-predict-tickets-settle.spec.ts`.

Known bugs / operational gaps still present:

- Backend startup still warns that `BET_SOCCERDATA_PYTHON` points to a missing local path; this did not block the verified hybrid flows, but it is still an environment bug for broader bridge coverage.
- The new hybrid E2E orchestration spec creates scheduled jobs through the API and verifies their UI visibility; it does not yet click every new “save job” button in the browser.
- This branch validated targeted backend tests and targeted browser tests, but did not rerun the full backend `pytest` suite or the entire Playwright suite.

What was verified in this pass:

- `git diff --check`
- `cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_scheduled_jobs.py`
- `cd frontend && pnpm check`
- `cd frontend && pnpm test:unit`
- `cd frontend && pnpm build`
- hybrid Playwright:
  - `scrape-job-honesty.spec.ts`
  - `dashboard-slip-ticket.spec.ts`
  - `scrape-predict-tickets-settle.spec.ts`

Still recommended before calling the whole platform fully closed:

- run full `cd backend && pytest`,
- run the broader `pnpm test:e2e` suite,
- add one browser spec that saves the new scheduled jobs via UI controls instead of only creating them through the API,
- fix/verify the local `soccerdata` bridge runtime path.

| Phase | Status | Implementation notes | Verification status |
|---|---|---|---|
| Phase 0: documentation and contract checkpoint | Done | Product spec, API contracts, roadmap, and test plan are present under `docs/plans/`. | `git diff --check docs/plans` before publish. |
| Phase 1: API and type foundations | Done | Backend response contracts were expanded for dashboard, predictions, tickets, jobs, strategies, and scrape semantics; frontend shared types and API clients were aligned around typed/paginated data. | Covered by backend contract tests and frontend unit/check commands. |
| Phase 2: Dashboard tabs and charts | Done | Dashboard now separates historical/future views, ticket outcome metrics, future matches, and generated-ticket visibility. | Covered by dashboard/auth hybrid smoke coverage and frontend checks. |
| Phase 3: Scrape page | Done | Scrape controls support explicit historical job inputs, saved/inspectable jobs, duplicate-scrape skipping, persisted job logs, bridge timeout plumbing, and saved scrape -> predict / scrape -> predict -> tickets orchestration. | Covered by scrape semantics tests, scrape catalog unit tests, targeted hybrid scrape-job coverage, and the new hybrid orchestration spec. |
| Phase 4: Predictii page | Done | Prediction catalog/run APIs and UI now expose richer controls, metrics, run history, verification/value-bet surfaces, and dedupe-oriented request semantics. | Covered by API contract tests, prediction visibility hybrid smoke coverage, and frontend checks. |
| Phase 5: Bilete page | Done | Tickets now expose generation/history/place-bet panels, ticket-leg status details, swap/recalculation helpers, backend validation/settlement paths, plus saved automatic verification and automatic ticket-generation job controls. | Covered by ticket creation validation, result settlement tests, ticket helper unit tests, dashboard slip/ticket hybrid smoke coverage, and the new hybrid orchestration/settlement spec. |
| Phase 6: Account, Data, Configuratii, Board deletion | Done | Account/Data routes were updated, `/configuratii` was added for strategy management/duplication, Board route/tests were removed, and navigation/search now point to current surfaces. | Covered by strategy semantics tests, data page load tests, layout auth gating, and frontend checks. |
| Phase 7: integrated verification and cleanup | In progress | The dedicated hybrid `scrape -> predict -> tickets -> settle` flow now exists and passes locally; full-suite backend and browser verification is still pending for full platform closure. | Completed this pass: `git diff --check`, targeted scheduler pytest, `pnpm check`, `pnpm test:unit`, `pnpm build`, and three targeted hybrid Playwright specs. Remaining recommended gate: full backend `pytest` and broader Playwright suite. |
