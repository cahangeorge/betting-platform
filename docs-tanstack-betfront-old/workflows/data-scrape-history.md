# Workflow: Data, Scraping, SoccerData, and Match History

## Data page workflow

`/data` had two tabs:

1. `Scrape` — collect data from OddsHarvester or SoccerData.
2. `History` — browse normalized stored matches and odds.

## OddsHarvester scrape workflow

### Controls

- Command mode: upcoming or historic.
- Date range for upcoming jobs.
- Season selector for historic jobs.
- Sports selector.
- Countries and leagues selectors.
- Market selectors through `OddsHarvesterFilters`.
- Per-market period selector/badge.
- Concurrency.
- Request delay in seconds.
- Bookies filter.
- Odds format.
- Target bookmaker.
- Output format.
- Proxy URL.
- Match links text area for direct match URLs.
- Headless and preview-style options were represented in the old implementation plan.

### Execution

- `runUpcoming` and `runHistoric` were TanStack server functions.
- Server built CLI args for `OddsHarvester`.
- CLI output was persisted to JSON and parsed.
- Matches were normalized to `Match` rows.
- Odds were normalized to `OddsEntry` rows.
- Job status moved through pending/running/success/failed.
- Running jobs were tracked globally to support cancellation.

### History result

- Each scrape created a `ScrapeJob`.
- Each job owned many `Match` rows.
- Each match owned many `OddsEntry` rows.
- The History tab could link from job to filtered match list.

## SoccerData workflow

### Sources

- ESPN
- FBref
- Sofascore
- Understat
- WhoScored
- SoFIFA
- MatchHistory
- ClubElo

### Operations

ESPN:
- schedule
- matchsheet
- lineup

FBref:
- schedule
- team season stats
- team match stats
- team season aggregate
- player season stats
- player match stats
- shot events
- lineup
- events
- leagues catalog
- seasons catalog

Sofascore:
- schedule
- standings
- leagues catalog
- seasons catalog

Understat:
- schedule
- team match stats
- player season stats
- player match stats
- shot events
- leagues catalog
- seasons catalog

WhoScored:
- schedule
- season stages
- missing players
- events
- leagues catalog
- seasons catalog

SoFIFA:
- teams
- players
- team ratings
- player ratings
- leagues catalog
- FIFA versions

MatchHistory:
- games

ClubElo:
- ratings by date
- team history

### SoccerData controls

- Provider.
- Operation.
- Leagues multiselect.
- Date.
- Season.
- Stat type for FBref/Understat.
- Team field; required for ClubElo team history.
- Optional match ID.
- Team mapping editor for standard names and aliases.

### Persistence

Generic provider results were saved as `ScrapedDataset` records:

- source
- operation
- sport
- league
- season
- date
- statType
- params JSON
- rowCount
- full data JSON
- summary JSON

## Match browser workflow

`MatchesTable` provided:

- Team search.
- Job/country/league grouping.
- Date sorting and sport sorting.
- Status calculation: upcoming, in progress, played.
- Expandable odds details.
- Market grouping and labels.
- Average/best odds and implied probability display.
- Bulk selected match deletion.

## Migration notes for Svelte platform

- Keep the two-tab mental model: `Scrape` and `History`.
- Keep explicit job honesty: show running/failed/cancelled states and logs.
- Keep country/league/market filters but back them with FastAPI endpoints, not TanStack server functions.
- Persist scrape outputs into normalized backend tables, not only raw job output.
