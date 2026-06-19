# Page and Route Inventory

## Root shell: `src/routes/__root.tsx`

### Visual structure

- Global HTML document shell.
- Inline theme initialization script before paint.
- `Header` at top, route children in the middle, `Footer` at bottom.
- Wrapped in `TanStackQueryProvider`.
- Optional devtools when `?devtools=1` in development.

### Functional details

- Uses `createRootRouteWithContext<{ queryClient: QueryClient }>()`.
- Adds stylesheet link from `styles.css?url`.
- Includes TanStack Router, Query, Store devtools only when enabled.
- Theme script reads `localStorage.theme`, supports `light`, `dark`, and `auto`.

## Home: `/`

### Visual blocks

- Large rounded hero island with radial gradient decorations.
- Kicker: `FrontBet — Sports Betting Dashboard`.
- Headline: `Odds. Data. Edge.`
- Three CTA pills: Data, Predict, Tickets.
- Three feature cards below: Data, Predict, Tickets & Trading.

### Functionality

- Pure navigation page.
- Explains the workflow: scrape odds, predict outcomes, generate tickets/trading ideas.

## Data: `/data`

### Visual blocks

- Page heading: `Scrape & Browse Data`.
- Tabs:
  - `🕷 Scrape`
  - `📊 History`

### Functionality

- Search params:
  - `tab`, default `scrape`
  - `dateFrom`, default today
  - `dateTo`, default today
- Loader prefetched:
  - OddsHarvester league catalog
  - SoccerData catalog
- Scrape tab rendered `DataHubPanel`.
- History tab rendered `MatchesTable` with date range state in URL.

## Redirect: `/data-hub`

Redirected to `/data`.

## Predict: `/predict`

### Visual blocks

- Page heading: `Predict Match Outcomes`.
- Tabs:
  - `🔮 Prediction`
  - `🧠 Train & Predict`
  - `📐 Analytics`
  - `📋 Prediction History`

### Functionality

- Search param `tab`, default `prediction`.
- Loader prefetched league and SoccerData catalogs.
- `Prediction` tab used `PredictionsPanel`.
- `Train & Predict` used `TrainPredictTab`.
- `Analytics` used `AnalyticsPanel`.
- `Prediction History` used `PredictionHistoryTab`.

## Redirect: `/predictions`

Redirected to `/predict`.

## Tickets: `/tickets`

### Visual blocks

- Page heading: `Generate Tickets & Trade`.
- Tabs:
  - `🎫 Generate Tickets`
  - `📈 Flumine`

### Functionality

- Search param `tab`, default `generate`.
- Loader prefetched league and SoccerData catalogs.
- `Generate Tickets` rendered `TicketsPanel`.
- `Flumine` rendered `FlumineTab`.

## Redirect: `/matches`

Redirected to `/data?tab=history`.

## Redirect: `/about`

Redirected to `/`.

## MCP endpoint: `/mcp`

### Functionality

- Registered a sample MCP server with an `addTodo` tool.
- POST handler delegated to `handleMcpRequest(request, server)`.
- This was not a product page; it was a server route/demo integration.
