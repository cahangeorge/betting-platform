# Visual Blocks and Component Behavior

## Global layout

### `Header`

- Sticky top header with translucent/backdrop blur background.
- Brand pill labelled `TanStack Start`.
- Navigation links:
  - Home
  - Data
  - Predict
  - Tickets
- External TanStack X/GitHub icon links.
- `ThemeToggle` on the right.

### `Footer`

- Top border, centered responsive content.
- Copyright text.
- Kicker text: `Built with TanStack Start`.
- TanStack X/GitHub icons repeated.

### `ThemeToggle`

- Supported modes: `light`, `dark`, `auto`.
- Persisted in `localStorage.theme`.
- Applied class to `<html>` and updated `color-scheme`.

## UI primitives in `components/ui.tsx`

- `Badge` — rounded status badge with colors for `pending`, `running`, `success`, `failed`.
- `Button` — variants `primary`, `secondary`, `danger`, `ghost`.
- `Input` — rounded input with lagoon focus ring.
- `Label` — small uppercase label.
- `Card` — rounded translucent panel.
- `Select` — Radix Select wrapper; forbids empty-string option values.
- `MultiSelect` — searchable grouped multiselect, supports exclusive values and visible-label limits.
- `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` — Radix Tabs wrappers.
- `DialogContent` — Radix Dialog content with close button.
- `Tooltip` — Radix tooltip.
- `Spinner` — loading indicator.

## Reusable visual language

- `page-wrap` constrained the page width.
- `island-shell` was the main glassy card container.
- `display-title` used Fraunces for hero/page headings.
- `island-kicker` used uppercase small label text.
- `feature-card` used hover/animated card style.
- Layout preferred rounded `2xl`/`[2rem]` cards, soft borders, glass surfaces, and lagoon/sea/palm palette.

## Data UI blocks

### `DataHubPanel`

Primary block for data collection. It switched between:

- OddsHarvester source.
- SoccerData source.

Used cards, labels, selects, multiselects, date inputs, result panels, and a job list.

### `OddsHarvesterFilters`

Reusable filter block for:

- Sports multiselect.
- Countries multiselect.
- Leagues grouped by country.
- Market groups as pills or grouped multiselects.
- Per-market period badges; clicking badge cycled period.
- Bulk period buttons when markets were selected.

### `JobsList`

Operational job table/list:

- Polling running jobs.
- Progress bar from parsed CLI output.
- Buttons for refresh, view matches, cancel, rerun, delete.
- Optional expandable job log.

### `MatchesTable`

History browser:

- Team filter input.
- Date range support from parent.
- Sort by date or sport.
- Grouping by scrape job, country, league.
- Expandable match rows showing odds detail.
- Market summary and detailed odds outcomes.
- Bulk selection and delete selected matches.

## Prediction UI blocks

### `PredictionsPanel`

Multi-step operational prediction surface:

1. Prepare historical data.
2. Prepare upcoming/schedule matches.
3. Select model.
4. Run predictions.
5. Build tickets from value bets.

It included process panels, logs, model controls, league/source selectors, date selectors, and results tables with market probability groups.

### `TrainPredictTab`

Disabled/waiting training concept for ML classifiers:

- League, division, year range.
- Classifier selection.
- Odds type.
- Initial cash and stake per bet.
- CTA disabled with explanation.

### `PredictionHistoryTab`

Historical prediction session browser:

- Filters by source/model.
- Probability display by market groups.
- Accuracy badge based on stored prediction outcomes.
- Delete session action.

### `AnalyticsPanel`

Toolkit page with tabs:

- Betting
- Ratings
- Backtest
- FPL
- Matchflow
- Pitch
- Opta
- Bayesian

It was backed by penaltyblog bridge operations and specialized analytics components.

## Tickets UI blocks

### `TicketsPanel`

Three tabs:

- Manual Build
- Prediction Build
- Saved Tickets

Contained browsers for matches/predictions, a selection dialog, ticket builder stats, save actions, and saved ticket list.

### `FlumineTab`

Paper/live trading concept card:

- Market selector.
- Strategy type selector: back, lay, back+lay.
- Execution mode: simulated/live.
- Max bet and max loss.
- Disabled `Start Strategy` CTA with bridge-in-progress notice.
