# ADR: Hybrid scraping pipeline v2

Date: 2026-07-30
Status: Accepted

## Context

Recent bounded live jobs showed that queue concurrency improves throughput, but
the dominant cost remains repeated browser navigation and per-record database
work. A five-league historical scrape typically spends tens of minutes inside
OddsHarvester, while provider layout drift and anti-bot responses require a
truthful fallback path rather than treating every empty result as success.

The platform must improve throughput without weakening the existing provider
allowlist, result lineage, idempotency, `no_fixtures` semantics, resource
bounds, or immutable job history.

## Decision

- Introduce an opt-in hybrid v2 pipeline selected deterministically by scrape
  job ID and `BET_SCRAPE_PIPELINE_V2_PERCENT`.
- Keep the deterministic extraction path primary:
  persistent Scrapling HTTP first, then the existing hardened
  Playwright/Patchright-compatible browser path.
- Add Camoufox as an explicit anti-bot fallback. It is not the default engine
  and must not run concurrently with the primary browser in the same job.
- Use Stagehand v3 only as an optional local repair assistant for DOM/parser
  drift. It may propose a candidate recipe from one representative page, but
  it never extracts every match, writes application data, or activates a
  persistent recipe without deterministic validation and operator approval.
- Persist validation-cache and recipe metadata in PostgreSQL without cookies,
  authorization headers, model keys, or other credentials.
- Evolve the additive scrape-report contract to version `1.1`; the backend
  continues to accept `1.0` during rollout.
- Preserve the existing v1 path as the immediate rollback target. Setting the
  rollout percentage to zero disables v2 without data migration rollback.
- Roll out in stages of 10, 25, 50, and 100 percent after at least 20 observed
  jobs per stage meet the acceptance gates.

## Alternatives considered

- Increase browser workers only: improves queue service rate but retains the
  same expensive navigation cost and raises memory/anti-bot pressure.
- Replace the scraper with Stagehand: rejected because per-match LLM inference
  is slower, less deterministic, cost-bearing, and inappropriate for the hot
  path.
- Use Camoufox for every request: rejected because the additional browser
  runtime and binary footprint should be paid only for confirmed anti-bot or
  repeated navigation failures.
- Activate learned recipes automatically: rejected because provider drift can
  silently corrupt odds data; candidates require independent deterministic
  validation.

## Consequences

- Scrape attempts and fallbacks become observable and independently
  reversible.
- The runtime gains optional Camoufox and Stagehand dependencies plus a
  Camoufox browser artifact when those capabilities are enabled.
- Local operators must budget for only one heavy browser family at a time per
  job and retain the existing bounded Taskiq worker configuration.
- Candidate repair recipes require a small operational approval workflow.
- Report readers and dashboards must tolerate both `1.0` and `1.1` until the
  canary is complete.

## Verification and references

- OddsHarvester orchestration: `OddsHarvester/src/oddsharvester/core/`
- Backend contract and ingestion: `backend/app/services/scraper.py`
- Backend configuration: `backend/app/config.py`
- Database migrations: `backend/alembic/versions/`
- Rollout gates:
  - result parity at least 99%;
  - success rate no more than one percentage point below v1;
  - p50 duration at least 40% lower or seconds/result at least 30% lower;
  - no material anti-bot increase;
  - no more than 4 GiB RSS per worker;
  - no lineage, ownership, idempotency, or `observed_at` regressions.
