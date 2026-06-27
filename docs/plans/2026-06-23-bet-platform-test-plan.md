# Test Plan: 2026-06-23 Bet Platform Product Plan

Date: 2026-06-23  
Scope: verification strategy for the Dashboard, Scrape, Predictii, Bilete, Account, Date, Board deletion, and Configuratii implementation.

## 1. Test commands

Run backend commands from `backend/`:

```bash
pytest
```

Run frontend commands from `frontend/`:

```bash
pnpm check
pnpm test:unit
pnpm build
pnpm test:e2e
```

For targeted hybrid browser checks, use the existing Playwright config under `frontend/playwright.config.ts` and the `frontend/tests/e2e/hybrid/` directory.

## 2. Backend unit/integration tests

### 2.1 Result verification and settlement

Coverage:

- prediction verification for `1x2`, `btts`, `over_under_2_5`,
- ticket leg settlement,
- full ticket settlement,
- pending/unresolved behavior for unfinished matches,
- void/cancelled behavior where supported.

Acceptance:

- Finished match with home win settles home `1x2` prediction as won.
- Finished match with away win settles home `1x2` prediction as lost.
- Unfinished match remains pending/unresolved.
- Ticket with all winning legs becomes won.
- Ticket with any losing leg becomes lost.

Likely tests:

- `backend/tests/test_result_settlement.py`
- new tests for aliases and edge cases as markets expand.

### 2.2 Dashboard ticket outcome API

Coverage:

- range bucket generation for today, 7d, 1m, 3m, 6m, 1y,
- won/lost/void counts,
- selected bucket ticket details,
- user ownership/auth filtering if applicable.

Acceptance:

- Seeded won and lost tickets land in correct date buckets.
- Bucket details return only tickets from selected bucket.

### 2.3 Prediction run exact dedupe

Coverage:

- `avoid_reprediction=true` with identical inputs returns existing successful run,
- changed interval/country/league/market/strategy/model config creates new run,
- failed runs do not block new run unless explicitly designed otherwise.

Acceptance:

- Canonical input hash is stable across equivalent ordering/formatting.
- Different semantic input creates different hash.

### 2.4 Scrape job parameters and avoid rescraping

Coverage:

- scrape job stores countries/leagues/historic range/future range/toggles,
- avoid rescraping skips already complete records,
- changed range or league triggers additional work,
- logs are persisted for every important action.

Acceptance:

- Created job can be fetched with the same parameters submitted.
- Logs include job-created and completion/error actions.

### 2.5 Ticket generation and swap

Coverage:

- ticket generation respects account, count, difficulty, markets, odds min/max,
- generated tickets link back to prediction selections,
- swap validates source/target legs,
- swap recalculates total odds and probability,
- invalid duplicate/conflicting swap is rejected.

Acceptance:

- Swapping two legs returns updated tickets.
- Invalid swap returns a clear validation error and does not mutate tickets.

### 2.6 Strategy create/edit/duplicate

Coverage:

- list strategies,
- create custom strategy,
- edit strategy fields,
- duplicate strategy,
- duplicated strategy can be used in prediction run form.

Acceptance:

- Duplicate strategy has a new id and copied editable configuration.

### 2.7 Pagination contracts

Coverage:

- matches pagination,
- prediction runs/generated predictions pagination,
- tickets pagination.

Acceptance:

- Responses include `items`, `total`, `page`, `per_page`.
- `per_page` is capped to a safe maximum.

## 3. Frontend unit tests

Use Node tests under `frontend/tests/unit/`.

### 3.1 Form payload builders

Coverage:

- Scrape page payload:
  - countries,
  - leagues,
  - historic range,
  - future range,
  - avoid rescraping,
  - autoscrape.
- Predictii page payload:
  - interval,
  - countries/leagues,
  - markets,
  - strategies,
  - autopredict,
  - avoid reprediction.
- Bilete generation payload:
  - account,
  - ticket count,
  - difficulty/safety,
  - markets,
  - min/max odds.

Acceptance:

- Payloads match API contract exactly.

### 3.2 Range and bucket helpers

Coverage:

- dashboard range labels,
- chart bucket formatting,
- date range conversion for today/week/month/3m/6m/1y.

Acceptance:

- Range selection produces expected query parameters and display labels.

### 3.3 Catalog filtering

Coverage:

- selected countries filter leagues,
- special competitions remain selectable,
- multi-country selection merges leagues without duplicates.

Acceptance:

- League options are stable and sorted/presented consistently.

### 3.4 Ticket probability and swap mapping

Coverage:

- display source/target ticket options,
- changed tickets update total odds/probability from backend response,
- validation state for incomplete source/target selection.

Acceptance:

- UI cannot submit a swap with missing IDs.

### 3.5 Page load data typing

Coverage:

- server-loaded bankroll/account data on Account/Tickets/Data pages,
- no `any`-driven route data fallbacks.

Acceptance:

- `pnpm check` passes and unit tests cover page data normalizers.

## 4. Playwright browser tests

### 4.1 Dashboard

Scenarios:

1. Dashboard tabs:
   - open `/`,
   - see `Istoric` and `Viitor`,
   - switch tabs.
2. Ticket outcome bars:
   - seed won/lost tickets,
   - select 7d range,
   - click a bar,
   - see details panel with ticket leg final score.
3. Prediction verification:
   - seed finished match and prediction,
   - see checked/resolved/correct/accuracy metrics.
4. Future dashboard:
   - seed future match with prediction,
   - seed active ticket,
   - see both on `Viitor`.

Acceptance:

- No accidental x-axis page scroll at desktop and mobile widths.

### 4.2 Scrape

Scenarios:

1. Automatic jobs list is visible.
2. Country multiselect filters leagues.
3. Historic/future numeric fields submit expected job parameters.
4. Avoid rescraping/autoscrape toggles are included.
5. Logs panel opens and shows seeded logs.

Acceptance:

- Starting a scrape job shows a created/running/succeeded/failed state and logs.

### 4.3 Predictii

Scenarios:

1. Metrics section shows seeded verification counts.
2. Automatic prediction actions are visible.
3. Future predictions list filters by day/week/month.
4. Prediction form can select interval/countries/leagues/markets/strategies.
5. Avoid reprediction dedupes identical run and allows changed input.

Acceptance:

- Future prediction generated by backend appears without creating a ticket.

### 4.4 Bilete

Scenarios:

1. Metrics show won/lost/active ticket counts.
2. Active tab expands unfinished ticket and shows leg status/minute/final score.
3. Istorice tab selects a generation job and shows generated tickets.
4. Place bet tab generates tickets from seeded predictions.
5. Swap UX changes a leg and updates affected ticket totals.
6. Verify results button settles due ticket and updates UI.

Acceptance:

- A seeded finished winning ticket becomes won after settlement.
- A generated ticket can be adjusted without editing raw data.

### 4.5 Account

Scenarios:

1. List accounts.
2. Create account.
3. New account appears in `Bilete > Place bet` account selector.

### 4.6 Date

Scenarios:

1. Tabs exist: scraped matches, generated predictions, generated tickets.
2. Rows-per-page selector changes visible rows or request size.
3. Next/prev controls work.
4. Pagination controls are above each table.

### 4.7 Configuratii

Scenarios:

1. Open `/configuratii`.
2. List strategies.
3. Edit strategy field and save.
4. Create strategy.
5. Duplicate strategy and edit copy.
6. Duplicated strategy appears in Predictii strategy multiselect.

### 4.8 Board deletion

Scenarios:

1. Sidebar does not contain Board.
2. Command palette does not contain Board.
3. Bottom/secondary nav does not contain Board.
4. Direct `/board` behavior is intentional: 404 or redirect to `/`/Dashboard `Viitor`.

## 5. Python Playwright smoke tests

Use Python Playwright when testing full backend/frontend integration with direct database setup/cleanup.

Recommended smoke scenario:

1. Create test user/session.
2. Create bankroll/account.
3. Seed finished match with final score.
4. Seed prediction run and prediction selection.
5. Seed ticket linked to prediction selection.
6. Open frontend `/predict` and verify prediction metrics.
7. Open `/tickets`, run result verification/settlement.
8. Assert database ticket status, leg status, return, PnL.
9. Clean up seeded rows.

Acceptance:

- Prediction and ticket status agree across backend response, frontend UI, and database state.

## 6. Layout/no horizontal overflow checks

Run for these routes:

- `/`,
- `/scrape`,
- `/predict`,
- `/tickets`,
- `/account`,
- `/data`,
- `/configuratii`.

Widths:

- 1440,
- 1024,
- 390,
- 320.

Browser assertion:

```js
const overflow = await page.evaluate(() => ({
  clientWidth: document.documentElement.clientWidth,
  scrollWidth: document.documentElement.scrollWidth
}));
expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
```

## 7. Manual exploratory checklist

- Empty states are understandable.
- Loading states do not shift layout badly.
- Error states do not pretend fake data is real.
- Long-running jobs communicate progress.
- Logs can be copied/read easily.
- Ticket panels remain usable on mobile.
- Market labels are consistent across Scrape, Predictii, Bilete, Dashboard, and Data.
- Romanian UI labels are clear and consistent.

## 8. Release gate

Before considering the full plan done:

```bash
cd backend && pytest
cd ../frontend && pnpm check && pnpm test:unit && pnpm build && pnpm test:e2e
```

Also run at least one integrated Playwright smoke with real frontend/backend and seeded data.
