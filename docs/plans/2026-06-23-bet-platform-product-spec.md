# Bet Platform Product Spec: Dashboard, Scrape, Predictii, Bilete, Account, Date, Configuratii

Date: 2026-06-23  
Platform target: `frontend/` SvelteKit + `backend/` FastAPI/Postgres  
Scope: current platform only. Do not implement this in `betfront/` or `frontbet/`.

## 1. Objective

Build the current betting platform into an operator dashboard where a user can:

1. choose what football data to scrape,
2. run and schedule predictions for selected markets and strategies,
3. generate and adjust betting tickets,
4. monitor active/future work,
5. verify whether predictions and tickets won or lost,
6. inspect raw scraped matches, generated predictions, generated tickets, and logs.

The UI must be understandable for a non-expert user: important actions should be visible, forms should use guided dropdowns/multiselects, and tickets should expose simple panels for inspecting and swapping selections.

## 2. Product-wide rules

- Primary UI routes live under `frontend/src/routes/`.
- Current API clients live under `frontend/src/lib/api/` and should keep using same-origin `/api/*` requests.
- Backend routes live under `backend/app/api/v1/`.
- Result verification should be local-first: use stored final scores and stored odds/predictions/tickets; fetch or scrape only missing final scores or missing status data.
- Historic scraping must be explicit. Do not hide historical scraping inside an opaque pipeline when the user selected concrete history fields.
- Automatic jobs must be inspectable: user can see saved/running job actions and full job logs.
- Every list/table with potentially many rows needs pagination controls.
- Labels may be Romanian in the UI, but code should use clear English identifiers.

## 3. Navigation and route changes

| Route | Decision |
|---|---|
| `/` | Keep as Dashboard and split into `Istoric` and `Viitor` tabs. |
| `/scrape` | Expand into the four requested scraping sections plus full logs panel. |
| `/predict` | Use as `Predictii`; expand into metrics, automatic actions, future predictions, and prediction form. |
| `/tickets` | Use as `Bilete`; expand into metrics and `Active`, `Istorice`, `Place bet` tabs. |
| `/account` | List betting accounts and allow creating a new account. |
| `/data` | Add tabs for scraped matches, generated predictions, generated tickets with row count and pagination controls above each table. |
| `/board` | Delete route and remove it from navigation/search. If future match board functionality is needed, move it into Dashboard `Viitor`. |
| `/configuratii` | Add new configuration route for prediction strategies. |

## 4. Dashboard page

### 4.1 Layout

Dashboard must have two top-level tabs:

1. `Istoric`
   - Section 1: ticket win/loss bar chart.
   - Section 2: prediction details chart per match.
2. `Viitor`
   - Section 3: future matches with generated predictions.
   - Section 4: future tickets already created.

### 4.2 Istoric section 1: ticket win/loss bars

Requirements:

- Chart type: grouped or stacked bar chart.
- Values: winning tickets and losing tickets.
- Colors:
  - won: green,
  - lost: red,
  - void/pending can be neutral only if included.
- Range selector in top-right:
  - today,
  - 7 days,
  - 1 month,
  - 3 months,
  - 6 months,
  - 1 year.
- Clicking a bar opens a side/bottom panel listing tickets in that bucket.
- Each listed ticket must show:
  - ticket status,
  - created date,
  - total odds,
  - stake,
  - chance/probability of winning,
  - payout/PnL if settled.
- Expanding a ticket must show each match/leg:
  - home team and away team,
  - market type,
  - selected outcome,
  - model win probability,
  - market odds at creation time,
  - final score,
  - leg result.

Acceptance criteria:

- A settled winning ticket appears in the green count for its date bucket.
- A settled losing ticket appears in the red count for its date bucket.
- Selecting a bar filters the details panel to exactly that date/range bucket.
- The panel does not require re-scraping to show final scores when final scores already exist locally.

### 4.3 Istoric section 2: prediction details per match

Requirements:

- Show prediction verification for historical matches.
- Support market types currently used by the backend, including at minimum:
  - `1x2`,
  - `btts`,
  - `over_under_2_5` and compatible aliases.
- Show for each prediction/match:
  - match,
  - league/country,
  - kickoff date,
  - market,
  - predicted outcome,
  - actual outcome,
  - model probability,
  - odds/implied probability if stored,
  - status: won/lost/pending/void/unresolved.
- Include metrics at chart level:
  - checked predictions,
  - resolved predictions,
  - correct predictions,
  - accuracy.

Acceptance criteria:

- Historical predictions with final scores are classified without new scraping.
- Predictions for unfinished matches remain pending/unresolved.

### 4.4 Viitor section 3: future matches with predictions

Requirements:

- List future matches available from scraped data.
- Show generated predictions for each future match.
- Each row/card should show:
  - kickoff time,
  - country and league,
  - teams,
  - market,
  - predicted outcome,
  - probability,
  - confidence/reliability signal,
  - linked prediction run/job.
- Filters:
  - period, e.g. today/week/month,
  - country,
  - league,
  - market type.

Acceptance criteria:

- Future scraped matches without predictions are distinguishable from future matches with predictions.
- User can identify which upcoming matches are already covered by a prediction job.

### 4.5 Viitor section 4: future tickets

Requirements:

- List created tickets that are not fully settled.
- Show:
  - ticket id/reference,
  - created date,
  - kickoff range,
  - number of legs,
  - settled legs / total legs,
  - status,
  - total odds,
  - chance/probability of winning.
- Expanding a ticket should show the same leg detail model used by the historical ticket panel.

Acceptance criteria:

- Active/future tickets are visible without going to `/tickets`.
- Ticket settlement progress is visible as complete/total legs or complete/total tickets.

## 5. Scrape page

### 5.1 Section 1: `scraping-uri automate`

Requirements:

- List saved automatic scraping actions/jobs.
- Each action button/card shows:
  - name,
  - target countries/leagues,
  - schedule or trigger type,
  - enabled/running state,
  - last run status,
  - last run time.
- User can start or toggle configured jobs where supported by the backend.

Acceptance criteria:

- Saved scheduled scraping jobs are visible and can be distinguished from one-off runs.

### 5.2 Section 2: `selectie de date`

Requirements:

- Multiselect for countries/competitions that can be scraped.
- Include special competition groups such as:
  - World Cup,
  - friendlies/amicale,
  - other supported international sections.
- Multiselect for leagues, filtered by selected countries/competitions.
- Use the backend catalog as source of truth when available.

Acceptance criteria:

- Selecting a country filters the league dropdown to relevant leagues.
- World Cup and other special categories can be selected without breaking country filtering.

### 5.3 Section 3: history and future date ranges

Requirements:

Provide numeric fields for historic scrape range:

- days,
- weeks,
- months,
- years.

Provide numeric fields for future match range:

- days,
- weeks,
- months,
- years.

Behavior:

- Historic range controls how much past data is scraped.
- Future range controls which upcoming fixtures are scraped.
- For every future fixture, if involved teams do not have enough local historical data, the system may enqueue explicit history scrape jobs for those teams.
- Avoid repeated historical scraping when local records already satisfy the requested range and `avoid rescraping` is enabled.

Acceptance criteria:

- User can request future fixtures and historical context from the same page.
- Any backfill scrape is created as a normal inspectable scrape job, not as a hidden internal scrape.

### 5.4 Section 4: scrape controls

Requirements:

- Toggle or button: `avoid rescraping`.
- Toggle or button: `autoscrape`.
- Button: `start scraping`.
- Start action creates an inspectable job with all selected inputs stored in job parameters.

Acceptance criteria:

- Starting scraping with the same inputs and `avoid rescraping` enabled does not duplicate already-complete data unnecessarily.
- Starting scraping with changed inputs creates a new job or expands missing coverage.

### 5.5 Full logs panel

Requirements:

- A visible button toggles the logs panel.
- Panel shows exhaustive job logs/actions, including:
  - job created,
  - parameters selected,
  - bridge invocation,
  - source/country/league/season,
  - records parsed,
  - records inserted/updated/skipped,
  - warnings,
  - errors,
  - completion status.
- Logs must support at least filtering by job id and status.

Acceptance criteria:

- Operator can diagnose exactly what happened in a scraping job from the UI.

## 6. Predictii page

The user requested three sections but listed four. Implement as four sections because the listed functionality has four distinct responsibilities.

### 6.1 Section 1: prediction metrics

Requirements:

- Show metrics for won/lost predictions:
  - checked predictions,
  - resolved predictions,
  - won/correct predictions,
  - lost/incorrect predictions,
  - accuracy percentage,
  - pending predictions.
- Metrics should support a selected time range when the data model supports it.

Acceptance criteria:

- Metrics update from stored prediction verification, not from guessed UI-only state.

### 6.2 Section 2: `predictii automate`

Requirements:

- List saved/running automatic prediction actions.
- Each action shows:
  - name,
  - selected countries/leagues,
  - markets,
  - strategy/model list,
  - schedule or trigger,
  - enabled/running state,
  - last run status.

Acceptance criteria:

- User can identify which prediction automations exist and whether they are active.

### 6.3 Section 3: `predictii pentru meciuri viitoare`

Requirements:

- List predictions already generated for future matches.
- User can select a display period, for example:
  - 1 day,
  - 1 week,
  - 1 month.
- Rows/cards show:
  - match,
  - kickoff,
  - country/league,
  - market,
  - selected outcome,
  - probability,
  - confidence/reliability,
  - linked strategy/model.

Acceptance criteria:

- A prediction generated for a future match appears in this section without needing ticket generation.

### 6.4 Section 4: prediction run form

Requirements:

Subsection: time interval fields

- Numeric fields for days, weeks, months, years.
- These fields select matches available for prediction from already scraped future fixtures.

Subsection: country/league multiselect

- Same country/league selection behavior as Scrape page.

Subsection: market and strategy selection

- Multiselect market types.
- Multiselect strategies, including strategies from penaltyblog and any existing project strategies imported/configured into the backend.

Subsection: automatic behavior

- Toggle: `autopredictie`.
- Toggle: `avoid reprediction`.
- `avoid reprediction` applies only when all inputs are exactly identical to an existing successful prediction run:
  - interval fields,
  - country selection,
  - league selection,
  - markets,
  - strategies,
  - relevant model configuration.
- Any difference in inputs should allow a new prediction run.

Acceptance criteria:

- Re-running with identical inputs and `avoid reprediction` enabled does not duplicate predictions.
- Re-running with one changed input creates a new prediction run.

## 7. Bilete page

### 7.1 Section 1: ticket metrics

Requirements:

- Show metrics for won/lost tickets:
  - active tickets,
  - won tickets,
  - lost tickets,
  - void tickets,
  - settled tickets,
  - win rate,
  - stake,
  - return,
  - PnL.

Acceptance criteria:

- Metrics reflect stored ticket settlement state.

### 7.2 Section 2: ticket tabs

#### Tab: `Active`

Requirements:

- List unfinished tickets.
- Each ticket opens in an expandable panel.
- Panel shows:
  - ticket status,
  - legs settled / total,
  - current minute/status for live/in-progress matches where available,
  - final score when finished,
  - leg result when resolved.

Acceptance criteria:

- A ticket with unfinished matches remains active.
- A ticket becomes historical when all legs are resolved.

#### Tab: `Istorice`

Requirements:

- List each ticket-generation job.
- Each job row/card shows:
  - job id/name,
  - run time,
  - number of generated tickets,
  - tickets settled / total tickets,
  - matches settled / total matches.
- Selecting a job opens a panel with all generated tickets.
- Each ticket in the panel shows:
  - chance/probability,
  - odds,
  - stake if assigned,
  - status,
  - legs.
- User can swap matches/legs between tickets through the simplest high-performance UX for non-experts:
  - select a source leg,
  - select a target ticket/slot,
  - confirm swap,
  - immediately recalculate ticket chance and total odds.

Acceptance criteria:

- User can inspect a historical ticket-generation job and see generated tickets.
- User can perform a ticket leg swap without editing raw JSON or technical fields.

#### Tab: `Place bet`

Requirements:

Fields:

- betting account selector,
- number of tickets to create,
- difficulty/chance/safety level,
- market type multiselect,
- odds interval with min and max values,
- button: generate automatic tickets.

After generating tickets:

- Show all tickets in a panel.
- Each ticket shows chance/probability and total odds.
- Allow swapping matches/legs between tickets using the same simple swap UX from `Istorice`.

Acceptance criteria:

- User can generate tickets from existing predictions.
- Generated tickets are shown immediately and can be adjusted before placement.

## 8. Account page

Requirements:

- List all bankrolls/accounts relevant for betting.
- Allow creating a new account.
- Account fields should include at minimum:
  - name,
  - bookmaker/provider,
  - currency,
  - starting/current balance where supported,
  - enabled/disabled status where supported.

Acceptance criteria:

- User can create a new betting account and then select it in `Bilete > Place bet`.

## 9. Date page

Requirements:

Three tabs:

1. `meciuri scrapeuite`,
2. `predictii generate`,
3. `bilete generate`.

For each tab:

- show a table,
- place controls above the table:
  - rows per page selector,
  - previous page button,
  - next page button,
  - current page/total summary if available.

Acceptance criteria:

- User can inspect scraped matches, predictions, and tickets without loading all rows at once.
- Pagination state is visible before the table.

## 10. Board page deletion

Requirements:

- Delete `/board` route.
- Remove Board from:
  - sidebar navigation,
  - command palette,
  - any secondary nav/menu.
- If the route is visited, it may 404 or redirect to Dashboard `Viitor` depending on implementation preference.

Acceptance criteria:

- No primary UI path points users to `/board`.

## 11. Configuratii page

### 11.1 Prediction strategies section

Requirements:

- Show strategy types/configurations from available project integrations, including penaltyblog-derived strategies where exposed by backend.
- Each strategy can be expanded/edited in form fields.
- Fields should be typed and validated where possible.

### 11.2 Create strategy

Requirements:

- User can create a new strategy by filling fields.
- Strategy must have:
  - name,
  - market support,
  - model/strategy type,
  - parameters/configuration,
  - enabled status.

### 11.3 Duplicate strategy

Requirements:

- User can duplicate an existing strategy.
- Duplicated strategy opens in edit mode or appears with a clear copied name.
- User can edit and save the duplicate.

Acceptance criteria:

- User can edit, create, duplicate, and then use strategies in `Predictii`.

## 12. Definition of done

A page or section is complete only when:

- Backend/API data needed by the UI is available or explicitly documented as a stub/gap.
- Frontend shows real API state and does not silently present fake data as real.
- Empty/loading/error states are clear.
- `frontend`: `pnpm check`, `pnpm test:unit`, and relevant Playwright tests pass.
- `backend`: `pytest` passes for changed backend behavior.
- Browser-visible layout is checked at desktop and mobile widths for no unintended x-axis scroll.
