# ADR: Provider-oriented data platform architecture

Date: 2026-08-01
Status: accepted

## Context

Bet already integrates `OddsHarvester`, `soccerdata` and `penaltyblog`, but the
projects overlap partially in scraping and currently expose broad bridge
surfaces. Using every available scraper for every data type would duplicate
requests, increase anti-bot risk, complicate identity matching and make
performance impossible to reason about.

Provider Adapter v1 introduced a fail-closed registry and canonical output
envelope. The next decision is how those adapters cooperate as a system.

## Decision

- Keep the FastAPI backend as a modular-monolith control plane.
- Separate adapter identity from upstream source identity. Policy, rights,
  quota and freshness are evaluated per `(adapter_key, source_key)`.
- Use `soccerdata` as the default non-odds ingestion adapter for approved
  fixtures, results, statistics, lineups and xG sources.
- Use `penaltyblog` primarily for features, ratings, models and backtesting over
  canonical persisted data; do not use its scrapers as an implicit duplicate.
- Use licensed APIs as the preferred production route for odds and live data.
- Keep `OddsHarvester` as a bounded odds adapter/fallback where rights and
  operational approval exist.
- Persist provider-scoped identity and observation lineage before multi-source
  production rollout.
- Keep PostgreSQL authoritative and Redis/Taskiq as transport/coordination.
- Keep frontend contracts provider-agnostic.
- Use separately deployable backend-owned worker pools for HTTP, browser and
  model workloads when isolation is required; they share queue contracts and
  PostgreSQL lineage and do not become autonomous provider microservices.
- Do not create provider-owned APIs/databases until measurement demonstrates a
  stronger independent boundary.

## Drivers

1. throughput and lower time-to-data without browser fan-out;
2. auditable lineage, idempotency and provider rights;
3. reversible delivery inside the current tested platform.

## Alternatives considered

### Use OddsHarvester for all football data

Rejected. It specializes in odds/markets and browser/XHR extraction; using it
for statistics and model inputs increases cost and does not match its boundary.

### Use soccerdata and penaltyblog scrapers interchangeably

Rejected. The overlap creates duplicate upstream load, inconsistent cache and
two normalization paths for the same domain.

### Merge nested projects into backend

Rejected. Their dependency/toolchain lifecycles are independent and already
isolated by subprocess bridges.

### One autonomous microservice per provider immediately

Rejected for now. The current bottlenecks are provider I/O, identity, caching,
browser fan-out and lineage; more services add operations without evidence that
process isolation is the missing constraint.

The strongest counterargument is security/dependency/failure isolation: one
image carrying browser stacks, native model dependencies and all credentials
increases blast radius and head-of-line blocking. The synthesis is separate
worker pools/images/egress/secrets under backend-owned contracts, without
splitting domain ownership or persistence.

### API-only, delete all scrapers

Not selected. It is the preferred production direction, but coverage, historic
depth and budget must be proven first. Scrapers remain bounded fallbacks.

## Consequences

Positive:

- less duplicate scraping and clearer performance ownership;
- lower browser usage for non-odds data;
- uniform policy and audit across current and future providers;
- incremental migration without rewriting API/UI;
- clean path to licensed API canaries.

Negative:

- requires provider-scoped identity and observation persistence;
- requires upstream-scoped policy rather than one policy for an aggregator;
- cache freshness must be governed explicitly;
- some source coverage remains approval/licensing dependent;
- subprocess bridges remain an operational boundary until profiling justifies
  a different deployment model.

## Follow-ups

1. completed: architecture and critic review accepted this ADR;
2. completed: adapter/source descriptors, source policy/quota/freshness,
   redacted policy decisions, one capability-enforced read-only bridge slice
   and Provider Envelope v2/quarantine passed independent verification;
3. next: accept a separate identity/schema ADR before migration;
4. establish minimum queue/resource isolation before provider ingestion;
5. run a statistically valid controlled cold/warm benchmark;
6. evaluate and canary one licensed API;
7. promote only through the existing protected release gates.

## References

- `docs/architecture/provider-data-platform.md`
- `docs/plans/2026-08-01-provider-data-platform-execution-plan.md`
- `docs/adr/2026-08-01-provider-adapter-v1.md`
- `docs/adr/2026-07-30-hybrid-scraping-pipeline-v2.md`
