# Data Model from Old TanStack App

The old app used Prisma with SQLite. These concepts are useful for migration, but the current platform should implement them in FastAPI/Postgres models.

## `ScrapeJob`

Tracked OddsHarvester runs.

Fields:

- `id`
- `command`: `upcoming` or `historic`
- `sport`
- `markets`: comma-separated market names
- `league`
- `date`: YYYYMMDD for upcoming jobs
- `season`: historic season
- `headless`
- `status`: pending/running/success/failed
- `output`: raw CLI output
- `startedAt`
- `finishedAt`
- relation: `matches`

## `Match`

Normalized match from a scrape job.

Fields:

- `id`
- `jobId`
- `sport`
- `league`
- `homeTeam`
- `awayTeam`
- `matchDate`
- `matchUrl`
- `homeScore`
- `awayScore`
- `createdAt`
- relation: `job`
- relation: `odds`

## `OddsEntry`

Normalized odds per match/bookmaker/market.

Fields:

- `id`
- `matchId`
- `market`
- `submarket`
- `bookmaker`
- `oddsHome`
- `oddsDraw`
- `oddsAway`
- `oddsOver`
- `oddsUnder`
- `oddsYes`
- `oddsNo`
- `createdAt`

## `PredictionSession`

Top-level prediction run metadata.

Fields:

- `id`
- `league`
- `source`
- `model`
- `config` JSON string
- `matchCount`
- `createdAt`
- relation: `predictions`

## `Prediction`

Per-match prediction output.

Main fields:

- teams, date, league
- `homeWinProb`, `drawProb`, `awayWinProb`
- `predictedGoalsHome`, `predictedGoalsAway`
- `predictedOutcome`
- `confidence`

Derived market fields:

- double chance: `dc1X`, `dcX2`, `dc12`
- draw no bet: `dnbHome`, `dnbAway`
- totals: `over15`, `under15`, `over25`, `under25`, `over35`, `under35`
- BTTS: `bttsYes`, `bttsNo`
- Asian handicap: `ahHome`, `ahAway`
- first-half equivalents prefixed `ht`
- second-half equivalents prefixed `sh`

Value-bet fields:

- `isValueBet`
- `valueBetMarket`
- `bookmakerOdds`
- `expectedValue`

Outcome tracking:

- `actualOutcome`
- `isCorrect`

## `Ticket`

Saved betting ticket.

Fields:

- `id`
- `name`
- `currency`
- `stake`
- `bankroll`
- `selections`: JSON `TicketSelection[]`
- `combinedOdds`
- `combinedProbability`
- `expectedValue`
- `potentialReturn`
- `createdAt`

## `ScrapedDataset`

Generic cache for SoccerData and provider outputs.

Fields:

- `id`
- `source`
- `operation`
- `sport`
- `league`
- `season`
- `date`
- `statType`
- `params` JSON
- `rowCount`
- `data` JSON
- `summary` JSON
- `createdAt`

Indexes:

- by `source`
- by `source`, `league`, `season`

## Migration warning

The old `Ticket.selections` JSON approach was flexible but weakly typed. In the current backend, ticket legs should be strongly modeled and should link to matches, odds, and/or prediction selections when possible.
