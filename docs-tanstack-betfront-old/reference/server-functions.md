# Server Functions and Bridge Inventory

The old TanStack app used `createServerFn` for server-side operations. The current platform should expose equivalent functionality through FastAPI endpoints/services.

## Dataset functions

From `src/server/datasets.ts`:

- `saveScrapedDataset`
- `listScrapedDatasets`
- `getScrapedDataset`
- `deleteScrapedDataset`

Purpose: generic persistence for provider results.

## OddsHarvester/scraper functions

From `src/server/scraper.ts`:

- `runUpcoming`
- `runHistoric`
- `getJobs`
- `getLeagueCatalog`
- `getJobById`
- `getJobOutput`
- `getRunningJobs`
- `cancelJob`
- `getMatches`
- `restartJob`
- `deleteJob`
- `deleteJobs`
- `deleteMatches`

Important internal responsibilities:

- Build CLI args for upcoming/historic commands.
- Persist job metadata.
- Spawn OddsHarvester process.
- Parse progress from output.
- Persist matches and odds.
- Reconcile orphaned running jobs.
- Track running child processes for cancellation.

## SoccerData functions

From `src/server/soccerdata.ts`:

- `getSoccerDataCatalog`
- `getEspnSchedule`, `getEspnMatchsheet`, `getEspnLineup`
- `getClubEloRatings`, `getClubEloTeamHistory`
- `getMatchHistoryGames`
- `getFBrefSchedule`, `getFBrefTeamStats`, `getFBrefTeamMatchStats`, `getFBrefTeamSeasonStats`, `getFBrefPlayerSeasonStats`, `getFBrefPlayerMatchStats`, `getFBrefShotEvents`, `getFBrefLineup`, `getFBrefEvents`
- `getSofascoreSchedule`, `getSofascoreStandings`, `getSofascoreLeagues`, `getSofascoreSeasons`
- `getUnderstatSchedule`, `getUnderstatTeamMatchStats`, `getUnderstatPlayerSeasonStats`, `getUnderstatPlayerMatchStats`, `getUnderstatShotEvents`, `getUnderstatLeagues`, `getUnderstatSeasons`
- `getWhoScoredSchedule`, `getWhoScoredSeasonStages`, `getWhoScoredMissingPlayers`, `getWhoScoredEvents`, `getWhoScoredLeagues`, `getWhoScoredSeasons`
- `getSoFIFALeagues`, `getSoFIFAVersions`, `getSoFIFATeams`, `getSoFIFAPlayers`, `getSoFIFATeamRatings`, `getSoFIFAPlayerRatings`
- `getTeamMapping`, `setTeamMapping`

Purpose: call Python soccerdata bridge and return provider-specific rows/catalogs.

## Penaltyblog functions

From `src/server/penaltyblog.ts`:

- `getPenaltyblogCatalog`
- `runPenaltyblogOperation`
- `getPenaltyblogHistoricalMatches`
- `countHistoricalMatches`

Helper responsibilities:

- Pick odds from 1X2 entries.
- Sort historical matches.
- Build season variants.
- Normalize SoccerData schedules.
- Select recent matches.
- Map Frontbet DB match rows into penaltyblog-compatible historical match contracts.
- Resolve historical matches from SoccerData where needed.

## Prediction persistence

From `src/server/predictions.ts`:

- `savePredictionSession`
- `getPredictionSessions`
- `deletePredictionSession`
- `updatePredictionResult`

## Ticket functions

From `src/server/tickets.ts`:

- `getTicketSports`
- `getPredictionLeagues`
- `getMatchesForTickets`
- `saveTicket`
- `getTickets`
- `deleteTicket`
- `findValueBets`
- `generateTicketFromPredictions`

Important internal responsibilities:

- Market display names.
- Outcome labels.
- Market group normalization.
- Ticket stat calculation.
- League search terms.
- Value-bet matching between predictions and available odds.

## Bridge paths from old app

The old code hard-coded bridge paths similar to:

```txt
/home/gion/Apps/bet/penaltyblog/.venv/bin/python
/home/gion/Apps/bet/frontbet/scripts/penaltyblog_bridge.py
/home/gion/Apps/bet/soccerdata/.venv/bin/python
/home/gion/Apps/bet/frontbet/scripts/soccerdata_bridge.py
```

The current backend should avoid hard-coded user-specific paths and use `BET_*` environment variables plus repo-local defaults.
