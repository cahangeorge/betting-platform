# ADR: Provider Adapter v1 boundary

Date: 2026-08-01
Status: Accepted

## Context

The active Bet platform already invokes `OddsHarvester`, `soccerdata`, and
`penaltyblog` through backend-owned subprocess bridges, while `flumine` remains
an isolated paper/execution dependency. Those integrations expose useful
capabilities, but provider identity, capability checks, and production-use
policy are still implicit in individual services.

Adding more APIs or scrapers before defining one provider boundary would spread
provider-specific behavior into ingestion, prediction, and UI contracts. It
would also conflate open-source code licences with the separate permission to
collect, store, display, or redistribute an upstream provider's data.

## Decision

- Keep `frontend/` provider-agnostic and keep `backend/` as the control plane
  and source of truth.
- Add a small immutable provider contract and registry owned by the backend.
- Describe every provider by a stable key, kind, transport, declared
  capabilities, and fail-closed production policy.
- Reject restricted providers by default. The former compatibility keyword
  `allow_unapproved` has no bypass effect; an `approval_required` or `disabled`
  provider remains closed until a separate explicit, auditable approval
  mechanism is accepted and implemented.
- Represent provider output with a canonical JSON envelope containing provider
  key, capability, source identifier, schema version, observation time, and a
  deterministic SHA-256 payload digest.
- Register only the current local integration boundaries in v1:
  - `OddsHarvester`: odds/data subprocess adapter; production use requires
    explicit upstream approval;
  - `soccerdata`: data-enrichment subprocess adapter; production use requires
    approval for each selected upstream source;
  - `penaltyblog`: local modelling subprocess boundary;
  - `flumine`: execution boundary disabled for the public MVP.
- Do not add a live provider, database migration, API route, worker service, or
  dependency in this slice.
- Keep Taskiq + Redis as execution transport and PostgreSQL as durable business
  truth. Provider-specific worker queues and persistent runtimes are follow-up
  optimizations after the contract is exercised by one licensed API adapter.

## Alternatives considered

- Merge all nested projects into the backend interpreter: rejected because it
  couples independent toolchains and makes dependency or scraper failures part
  of the API process.
- Create one microservice per provider immediately: rejected because no current
  throughput or isolation requirement justifies that operational surface yet.
- Add provider strings directly to existing scrape and match models: rejected
  because it would extend the current implicit contract without capability or
  policy enforcement.
- Treat an open-source licence as permission to use upstream data: rejected;
  code and data rights are separate concerns.

## Consequences

- New providers have one explicit integration boundary and capability test.
- Production callers can fail closed before invoking an unapproved scraper or
  disabled execution adapter.
- Canonical payload hashing becomes available for idempotency and lineage, but
  persistence remains a later migration after identity rules are reviewed.
- Existing bridges continue to work unchanged; adopting the registry in each
  call path can proceed incrementally with regression tests.

## Verification and follow-up

- Contract tests: `backend/tests/test_provider_registry.py`.
- Completed follow-up: the penaltyblog `goal_expectancy` runtime canary now
  authorizes the exact `(penaltyblog, local-model, goal_expectancy)` identity
  through `require_operation` before runtime validation or subprocess work,
  without changing its bridge payload or output contract.
- Completed follow-up: Provider Envelope v2 separates envelope and payload
  schema versions, adds immutable lineage/freshness/provenance metadata and
  quarantines unsupported or invalid input before normalization with a fully
  redacted deterministic artifact.
- Next follow-up: design provider-scoped match/team/competition identity and
  uniqueness in a separate ADR before adding persistence or a licensed API
  canary.
