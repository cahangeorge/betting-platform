# Sports Betting Intelligence Dashboard — Feature Research

> Professional analytics platform (not consumer betting site). Focus: data, models, edge detection, bankroll, and comparison tools.

---

## 1. Core Data Views

### Odds Matrix
- **What:** Grid showing bookmaker odds across multiple markets (1X2, O/U, BTTS, Asian Handicap) for each match.
- **Why:** Instant visual scan for best available price per market.
- **SvelteKit:** Data table with sticky headers, row-level sparklines for line movement. Use `svelte-table-kit` (TanStack Table v8 wrapper) for sorting, pagination, and virtual scrolling over large match lists.

### Value Bet Feed
- **What:** Auto-ranked list of positive-EV opportunities with edge %, confidence score, best bookmaker, and Kelly stake suggestion.
- **Why:** The primary decision surface. Filters noise; surfaces only actionable edges.
- **SvelteKit:** Reactive store (`$state` in Svelte 5) fed by polling or SSE. Each card is a reusable component with color-coded edge severity.

### Prediction Cards
- **What:** Match-level panel showing model probabilities (ensemble + individual models), Monte Carlo simulations, and narrative summary.
- **Why:** Transparency into model reasoning. Builds trust in the engine.
- **SvelteKit:** Expandable accordion card. Inner tabs: Probabilities / Simulations / Narrative. Use `shadcn-svelte` Accordion + Tabs primitives.

### Bankroll Tracker
- **What:** Live view of total bankroll, open exposure per bookmaker, pending P&L, and risk-adjusted allocation.
- **Why:** Prevents overexposure. Ties directly to Kelly/flat staking discipline.
- **SvelteKit:** Summary KPI bar + detail drill-down. Sync via server load + periodic revalidation.

---

## 2. Visualization Components

### Odds Movement Charts
- **What:** Time-series of opening/closing odds per bookmaker for a market.
- **Why:** Identifies sharp money direction and market efficiency.
- **SvelteKit:** `svelte-lightweight-charts-pro` or `lightweight-charts-svelte` (TradingView wrapper). Line/Area series with multiple panes. Best-in-class performance for large tick histories.

### Model Probability Bars
- **What:** Horizontal stacked bars showing model-implied probabilities vs market-implied probabilities side by side.
- **Why:** Immediate visual gap = edge.
- **SvelteKit:** Custom SVG component (lightweight, no library needed). Color gap zones: green (edge), red (no edge), grey (uncertain).

### Edge Indicators
- **What:** Badges or heatmap cells showing edge % per match/market.
- **Why:** At-a-glance prioritization.
- **SvelteKit:** Tailwind gradient badges (`bg-emerald-500` to `bg-rose-500`). For heatmaps, CSS grid with `title` tooltips.

### Bankroll Equity Curves
- **What:** Cumulative P&L over time with drawdown shading and benchmark overlay.
- **Why:** Measures true performance independent of variance.
- **SvelteKit:** Lightweight Charts AreaSeries with baseline. Or `chart.js` + `chartjs-adapter-date-fns` if more annotation flexibility is needed.

---

## 3. Interactive Elements

### Filters, Sorting, Multi-Select
- **What:** League, date, market type, model confidence, edge threshold filters.
- **Why:** Users manage thousands of matches; noise reduction is critical.
- **SvelteKit:**
  - Multi-select: `svelte-multiselect` (keyboard accessible, zero runtime deps).
  - Query builder: `@svar-ui/svelte-filter` for advanced AND/OR rule construction.
  - Table sorting: `svelte-table-kit` built-in.

### Date Range Pickers
- **What:** Custom ranges (Today, This Week, Season) + manual calendar selection.
- **Why:** Time-based analysis is central to backtesting and bankroll review.
- **SvelteKit:** `beyonk/svelte-datepicker` supports range selection and SvelteKit SSR (requires `dayjs` as `noExternal` in Vite config).

---

## 4. Real-Time Features

### Live Match Tracker
- **What:** In-play scores, minute, key events, and live odds tickers.
- **Why:** For in-play model adjustments and trade-out decisions.
- **SvelteKit:** SSE endpoint (`+server.ts` with `ReadableStream`) is simplest for one-way data push. For bi-directional needs (e.g., user alerts), use `svelte-realtime` (typed RPC + streams over uWebSockets).

### Odds Alerts
- **What:** User-defined triggers (e.g., "alert me if Edge > 3% on Liverpool U2.5").
- **Why:** Automation of opportunity scanning.
- **SvelteKit:** Alert rules stored in DB; background worker evaluates triggers on odds update. UI toast via a Svelte store. Use server-side timer/queue (e.g., `node-cron` or `bullmq`) for periodic scanning.

### Push Notifications
- **Why:** Value bets decay quickly; immediacy matters.
- **SvelteKit:** Web Push API via `web-push` library. Store VAPID keys in env. Trigger from same worker that evaluates alerts.

---

## 5. Comparison Tools

### Model vs Market
- **What:** Overlay chart of model probability vs market-implied probability over time.
- **Why:** Shows when market is converging to or diverging from model.
- **SvelteKit:** Dual LineSeries in Lightweight Charts. Sync time axis.

### Bookmaker Comparison
- **What:** Side-by-side odds grid for a single match across configured bookmakers.
- **Why:** Always bet at the best price.
- **SvelteKit:** Simple table with conditional formatting highlighting the best odds per outcome.

### League Performance
- **What:** Aggregation table: ROI, yield, bets placed, win rate, CLV per league.
- **Why:** Detects where the model has genuine edge vs where it is noise.
- **SvelteKit:** Pivot table view using `svelte-table-kit` with groupBy.

---

## 6. Export / Sharing

### CSV Export
- **What:** Export current filtered view (value bets, history, bankroll log) to CSV.
- **Why:** External analysis, tax records, offline review.
- **SvelteKit:** Server-side generation in `+server.ts` using `csv-stringify` streaming to response. No client-side bloat.

### Bet Slip Sharing
- **What:** Shareable link or image card summarizing a bet recommendation.
- **Why:** Syndicate research, community discussion.
- **SvelteKit:** Screenshot via `html-to-image` or server-side `satori` + `resvg` for OG images. Short URL stored in KV/cache.

### Report Generation
- **What:** Weekly/monthly PDF summary: P&L, best/worst bets, model calibration chart.
- **Why:** Professional documentation for investors or personal discipline.
- **SvelteKit:** Generate HTML template server-side, convert to PDF with `puppeteer` or `playwright` in headless worker. Or use `jsPDF` + `autoTable` for simpler tabular reports.

---

## 7. Onboarding & Empty States

### Onboarding
- **What:** 3-step flow: connect bookmaker APIs (optional), set bankroll, configure alert thresholds.
- **Why:** Reduces time-to-value. Professional users expect configuration before data.
- **SvelteKit:** Route `/onboarding` with persistent step state in URL query params. Use `shadcn-svelte` Stepper.

### Empty States
- **What:** Friendly illustrations + primary action when no value bets match filters, no bankroll history yet, or no alerts configured.
- **Why:** Prevents abandonment. Guides next action.
- **SvelteKit:** Reusable `<EmptyState icon title action />` component. Use `lucide-svelte` icons. Keep copy direct: "No edges found today. Try lowering the confidence threshold or expanding leagues."

---

## Recommended Stack Summary

| Layer | Choice |
|---|---|
| Framework | SvelteKit 2 + Svelte 5 (Runes) |
| Charts | `lightweight-charts-svelte` (odds/equity), custom SVG (probability bars) |
| Tables | `svelte-table-kit` (TanStack Table v8) |
| Filters | `svelte-multiselect`, `@svar-ui/svelte-filter` |
| Date | `beyonk/svelte-datepicker` |
| Realtime | SSE for one-way; `svelte-realtime` if bi-directional needed |
| UI Primitives | `shadcn-svelte` + `lucide-svelte` |
| PDF/Images | `satori` + `resvg` (OG cards); `puppeteer` (reports) |

---

## Key Constraints
- Do **not** build a consumer bet placement UI. No wager buttons, no casino games.
- Data accuracy > visual polish. Every number needs provenance (model version, timestamp, bookmaker source).
- Professional users want density, not whitespace. Optimize for information density over marketing aesthetics.
