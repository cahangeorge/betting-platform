# Workflow: Prediction and Analytics

## Predict page workflow

`/predict` had four tabs:

1. `Prediction`
2. `Train & Predict`
3. `Analytics`
4. `Prediction History`

## Prediction tab

### High-level flow

1. Select prediction data mode.
2. Prepare historical match data.
3. Prepare upcoming/schedule match data.
4. Select prediction model.
5. Run prediction.
6. Inspect market probability outputs.
7. Generate candidate tickets from value bets.

### Historical data sources

- Local OddsHarvester-backed history.
- SoccerData-backed history.
- MatchHistory/ESPN-style season and date windows.

### Controls remembered from implementation

- Prediction preparation mode.
- Source selector.
- Season(s), years, months, weeks, days options.
- Max matches limit.
- Schedule source.
- Date from/to for upcoming matches.
- Prediction model selector.
- Ticket generation source.
- Ticket build strategies.

### Important validation logic

The old panel enforced minimum data thresholds conceptually:

- At least about 50 historical rows for model fitting.
- At least about 5 upcoming rows for a meaningful run.

### Market output groups

Prediction results displayed probability blocks for:

- 1X2.
- Double chance.
- Draw no bet.
- Totals: over/under 1.5, 2.5, 3.5.
- BTTS yes/no.
- Asian handicap simplified home/away.
- Full-time, first-half, and second-half variants when available.

## Train & Predict tab

This was a concept surface for ML classifier training from sports-betting style workflows.

### Controls

- League.
- Division.
- Year start.
- Year end.
- Classifier.
- Odds type.
- Initial cash.
- Stake per bet.

### Behavior

- CTA was disabled.
- Explained intended workflow: fetch history, train classifier, simulate betting, save predictions.

## Analytics tab

`AnalyticsPanel` was a broad penaltyblog-powered toolkit.

### Betting tools

- Implied probability from odds.
- Kelly criterion.
- Multi-Kelly staking.
- Value bet detection.
- Arbitrage detection.
- Hedge calculator.
- Odds conversion.

### Rating systems

- Elo.
- Pi.
- Colley.
- Massey.

### Backtest

- CSV match data input.
- Model selector.
- Market selector.
- Probability threshold.
- Starting bankroll.
- Stake per bet.
- Time decay xi.

### FPL

Fantasy Premier League-related controls existed in the analytics toolkit.

### Matchflow pipeline

`MatchflowPanel` supported:

- Source type: path/file/folder or inline JSON data.
- Dynamic processing steps.
- Step types for filtering, selecting fields, renaming, sorting, grouping/aggregating, limiting, sampling, Opta event/qualifier filters.
- Execute, infer schema, and explain plan actions.
- Result table rendering.

### Pitch visualization

`PitchVizPanel` supported:

- Provider selector.
- Theme selector.
- Title.
- Width and height.
- Orientation.
- View.
- JSON data text area.
- Layer list with type and mappings (`x`, `y`, `end_x`, `end_y`, color, size).
- Render pitch.
- Export HTML/SVG.

### Opta mappings

`OptaMappingsPanel` supported:

- Loading Opta event and qualifier mapping tables.
- Filtering by ID, name, or description.
- Separate visual sections for events and qualifiers.

### Bayesian diagnostics

`BayesianDiagnosticsPanel` supported:

- Numerical diagnostics tab.
- Visual plots tab.
- Match data input: home goals, away goals, home teams, away teams.
- Plot type selector.
- Rendered diagnostic output.

## Prediction history tab

Displayed saved `PredictionSession` records and nested `Prediction` rows.

### Features

- Filter by source.
- Filter by model.
- Probability market groups.
- Highlight highest probabilities.
- Accuracy badge when actual outcomes were available.
- Delete sessions.

## Migration notes for Svelte platform

- Preserve the workflow steps but simplify UI around current backend strategy runs.
- Keep probability market grouping because it maps well to ticket creation.
- Keep Analytics as a separate advanced/debug surface, not the primary user path.
- Avoid fake success: if bridges fail or produce empty results, show explicit warnings/errors.
