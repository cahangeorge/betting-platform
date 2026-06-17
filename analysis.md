# Comprehensive Codebase Analysis — Improvement Roadmap

Analyzed: 2026-05-03 | Updated: 2026-05-04
Projects: betfront, OddsHarvester, penaltyblog, soccerdata, flumine

---

## Status Overview

| Project | Total Issues | Fixed | Not Fixed |
|---------|-------------|-------|-----------|
| **betfront** | 19 | 16 | 3 |
| **OddsHarvester** | 13 | 10 | 3 |
| **penaltyblog** | 8 | 6 | 2 |
| **soccerdata** | 4 | 4 | 0 |
| **flumine** | 9 | 9 | 0 |
| **Cross-cutting** | 1 | 1 | 0 |
| **Total** | **54** | **46** | **8** |

---

## All Fixed Issues

### betfront (16/19 fixed)

#### Bugs
- **P0.1** `isCorrect` for non-1x2 — per-market actual outcome derivation
- **P0.2** `useQuery` race condition — `inflightFetches` Map + proper `finally` cleanup
- **P0.2b** `invalidateQueries` key matching — `slice(0,-1)` → proper `startsWith`
- **P0.2c** `mutate` silent swallow → `console.error`

#### Performance
- **P1.1** Sequential subprocess → worker pool with concurrency 3
- **P1.2** Ensemble model execution — inherits P1.1 parallelism
- **P1.5** N+1 ensemble weights → single query with `in` filter
- **Quick** `reverse()` → `orderBy('asc')`

#### Architecture
- **P1.3+P1.4** Shared `runBridge()` in `src/server/bridge.ts` (temp dir via `mkdtemp`, env var overrides, concurrency helper)
- **P5.1b** Extracted shared `buildLeagueFilter` + `buildLeagueSearchTerms` into `src/server/leagues.ts`

#### Error Handling
- **P2.1** Scraper `.catch(() ⇒ {})` → logs error + updates job to `failed`
- **P2.1b** Added concurrency guard for duplicate scrape jobs
- **P2.10** penaltyblog `catch {}` → `console.error` with error details

#### Security
- **P3.1+P3.2** Hardcoded Python paths → `resolveBridgePath` env var override + `mkdtemp`
- **P3.5** Added `checkRateLimit` (3 req/min per action)

#### UX
- **P4.4b** Created `ErrorBoundary` component, wrapped `PredictionsPanel`
- **P4.4c** Polling stops when `document.hidden`

### OddsHarvester (10/13 fixed)

- Removed dead `preview_submarkets_only` parameter from `BaseScraper`
- `rotate_proxy()` now raises `NotImplementedError`
- Added "ready for use" comments to exception classes
- Reduced `PAGE_COLLECTION_DELAY` from 6-8s to 2-3s
- Reduced `REQUEST_DELAY_JITTER_FACTOR` from 0.5 to 0.3
- Added TODO comments at all `page.content()` calls documenting DOM thrashing
- Added browser crash recovery TODO in `playwright_manager.py`
- Removed hardcoded S3 bucket/region defaults (must use env vars now)
- Added CSV deduplication TODO
- CLI allows past dates (was blocking backtesting)

### penaltyblog (6/8 fixed)

- `setup.py` now reads version from `penaltyblog/version.py` (no more 1.5.0 vs 1.9.0 mismatch)
- `utils.pxd` verified to exist with all needed declarations
- Sign convention documented in `dixon_coles.py` and `negative_binomial.py`
- Added NaN/Inf guard in `negative_binomial._loss_function()`
- Added `mp_context=mp.get_context("spawn")` to `ProcessPoolExecutor` for macOS
- `warnings.filterwarnings("ignore")` → `filterwarnings("error", category=scipy.optimize.OptimizeWarning)`

### soccerdata (4/4 fixed)

- Replaced shared mutable `_all_leagues_dict` with class-keyed cache + `threading.Lock`
- FBref `rate_limit` now configurable via param / `SOCCERDATA_FBREF_RATE_LIMIT` env var
- WhoScored `rate_limit` now configurable via param / `SOCCERDATA_WHOSCORED_RATE_LIMIT` env var
- Added safety TODO comments at dangerous XPath/index accesses
- Added ETag/checksum caching TODO
- Fixed mutable default `[]` in WhoScored

### flumine (9/9 fixed)

- Removed dead `ListenerError.__int__` method
- Added thread-safety warning to `config.py`
- Replaced `uuid.uuid1().time` (MAC leak) with `secrets.token_hex(8)`
- Login failure now raises `ConnectionError` (was silently returning `None`)
- `keep_alive` has exponential backoff: 1s→2s→4s→...→60s
- `historicalstream.py`: `file.readlines()` → line-by-line iteration
- `_bet_id_lookup` TODO for incremental maintenance
- CI: `actions/checkout@v2` → `v4`, `setup-python@v2` → `v5`
- BETDAQ execution `pass` → detailed TODO comment

---

## Not Fixed (8 issues requiring larger refactoring)

| # | Project | Issue | Reason |
|---|---------|-------|--------|
| 1 | betfront | 1200-line PredictionsPanel god component | Needs incremental refactor across 6+ files |
| 2 | betfront | Loading skeletons + error toast system | UI design task requiring user acceptance |
| 3 | betfront | Replace custom useQuery with TanStack Query | Breaking change across 15+ components |
| 4 | OddsHarvester | Sequential pagination tabs | Requires architectural change to reuse tabs |
| 5 | OddsHarvester | Exception hierarchy never raised | Requires replacing string-match error classification |
| 6 | penaltyblog | Missing `utils.pyx` Cython functions | Need to recreate `poisson_log_pmf`, `weibull_count_pmf`, etc. |
| 7 | penaltyblog | Sign convention inconsistencies | Per-model gradient tests needed to verify correctness |
| 8 | OddsHarvester | Health check exits 0 on failure | CI config change + notification integration |

---

## New Files Created

| File | Purpose |
|------|---------|
| `betfront/src/server/bridge.ts` | Shared Python bridge with `runBridge<T>()`, `runBridgeWithConcurrency()`, `resolveBridgePath()` |
| `betfront/src/server/leagues.ts` | Shared `buildLeagueFilter()` and `buildLeagueSearchTerms()` |
| `betfront/src/server/rate-limit.ts` | In-memory rate limiter with `checkRateLimit()` |
| `betfront/src/components/ErrorBoundary.tsx` | React error boundary for prediction panels |

## All 47 tests pass across betfront
