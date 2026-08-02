# ADR: Provider-agnostic licensed odds ingestion lane

- Status: Accepted for offline implementation; live activation blocked
- Date: 2026-08-01
- Scope: G006/P5

## Context

The existing `OddsEntry` is a compatibility projection for one bookmaker/market
with `home/draw/away` float columns. It cannot faithfully represent arbitrary
bookmakers, selections, totals, handicaps, periods or exact decimal lines. The
platform already owns provider policy, immutable Provider Envelope v2
observations, provider-scoped match identity, HTTP/browser worker isolation and
exact odds-snapshot lineage. P5 must extend those boundaries instead of creating
provider-specific databases or APIs.

Official-source evaluation selected Sportmonks Football API v3 Standard Odds as
the first implementation candidate because its football entity IDs, bookmaker
and market identities, and fixed 10-second latest-update feed fit incremental
normalization. The Odds API v4 remains a future shadow/parity and historical
snapshot candidate. This is a technical ordering only; neither source is
commercially approved.

## Decision

1. The common immutable payload is `odds-observation/v1`, row-per-selection.
   Quote identity is bookmaker + canonical market + period + exact decimal line
   + selection. Provider quote/market/bookmaker IDs, provider update time,
   stopped/suspended state and source event identity are preserved.
2. A generic `odds_quotes` table stores exact decimal normalized quotes. The
   existing `OddsEntry` remains a derived, complete-1X2-only compatibility
   projection for existing prediction/ticket code.
3. `OddsSnapshot` gains nullable typed lineage to the accepted immutable
   `ProviderObservation` plus contract/digest/mapping metadata. No legacy
   snapshot is backfilled without evidence.
4. A generic PostgreSQL provider runtime-state row owns pessimistic quota
   reservation, reconciliation and circuit/half-open state. It is keyed by
   `(adapter_key, source_key)`, not a provider-specific table.
5. The first adapter is `sportmonks-v3-odds` / source
   `sportmonks-football-v3-standard-odds`, disabled by policy with
   `APPROVAL_REQUIRED`. Offline tests inject an allowed registry and fake HTTP
   transport; production/canary/test contexts do not bypass source approval.
6. The token is process-local to `provider-http`, represented as `SecretStr`,
   never included in a JobSpec, envelope, persistence field, digest, log, error
   or shared Compose environment. Public Sportmonks documentation is internally
   inconsistent about header authentication, so the initial client uses the
   documented `api_token` request parameter only inside the transport boundary,
   disables redirects, and redacts all request failures. Live use remains
   blocked until Sportmonks confirms the approved authentication method.
7. OddsHarvester maps to the same common contract only through an explicit,
   bounded `oddsharvester/oddsportal` browser job. HTTP workers never invoke the
   browser fallback synchronously. Policy/auth/schema failures never trigger a
   silent fallback; only pre-approved quota/transient failure classes may create
   a correlated browser request.
8. Parity separates structural coverage from volatile price differences.
   Canary cohorts are deterministic and monotonic at 10/25/50/100. Twenty
   original logical jobs per stage are smoke only. Formal success
   non-inferiority requires a preregistered one-sided 95% confidence interval
   with lower bound at least -1 percentage point and at least 80% power.
   Structural parity requires a one-sided Wilson lower bound of at least 99%.
   p95 claims require at least 100 independent original jobs per stratum and a
   seeded bootstrap interval.
9. Rollback sets new-provider admission to zero and drains admitted HTTP work;
   it never deletes immutable observations. Quota exhaustion produces zero
   egress and an explicit result. A 100% canary is still not public release.
10. Quota admission uses the durable `provider_quota_reservations` ledger.
    Reservation and commit happen before egress, HTTP runs without a database
    row lock or open transaction, and reconciliation happens in a new short
    transaction. Expired unknown outcomes become conservative `uncertain`
    charges and open the circuit; the same acquisition identity never performs
    a second egress automatically. Successful normalized ProviderObservations
    are committed as the durable recovery payload before terminal quota
    reconciliation; a retry reloads their IDs without new egress.
11. `fetch_latest_odds` is an immutable `licensed-odds-job/v1` command on the
    `provider-http` lane. Its stable scheduled-run acquisition cohort is checked before
    admission at 10/25/50/100, excluded work has zero egress, and the job can
    never fall through to the legacy browser scraper.

## Consequences

- Migrations are expand-only and provider-agnostic.
- Unknown bookmaker/market mappings remain visible denominator gaps and make a
  snapshot partial/ticket-ineligible; no fuzzy mapping is silent.
- Live credentials, calls, retention, derived-model use, public display and
  multi-domain rights remain external approval gates.
- The implemented admission policy models the currently declared local RPM
  contract only. Sportmonks evaluation describes per-entity/hour commercial
  quota, so activation remains HOLD until the purchased entitlement is
  represented exactly rather than approximated.
- No new SDK dependency is required; the existing HTTP stack is sufficient.
- Provider raw-data redistribution, bookmaker logos and execution remain out of
  scope.
- Safe failure reasons preserve timeout, upstream-5xx, quota-exhaustion and
  transient-circuit taxonomy without exception URLs. Query authentication is
  attached below the ordinary httpx logging boundary.
- The scheduler deliberately performs no automatic fallback enqueue and no
  guessed bookmaker mapping. Until bounded competition/market/window scope and
  explicit bookmaker mappings are approved, fallback stays authorization-gated
  and canonical snapshots remain honestly `partial`.
- Offline parity fixtures demonstrate converter compatibility only. Their
  three comparable quote identities produce a 100% point estimate but an
  insufficient Wilson lower bound, so they deliberately cannot satisfy the
  formal 99% promotion gate.

## Official references

- [Sportmonks authentication](https://docs.sportmonks.com/v3/welcome/authentication)
- [Sportmonks latest updated odds](https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/standard-odds-feed/pre-match-odds/get-last-updated-odds)
- [Sportmonks odd entity](https://docs.sportmonks.com/v3/endpoints-and-entities/entities/odd-and-prediction)
- [Sportmonks pricing](https://www.sportmonks.com/football-api/plans-pricing/)
- [Sportmonks terms](https://www.sportmonks.com/terms-of-service/)
- [The Odds API v4 guide](https://the-odds-api.com/liveapi/guides/v4/)
- [The Odds API pricing](https://the-odds-api.com/)
- [The Odds API terms](https://the-odds-api.com/terms-and-conditions.html)
