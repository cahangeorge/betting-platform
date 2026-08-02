# Bet provider data architecture checkpoint - 2026-08-01

Canonical source files:

- `docs/status/current-platform-status.md`
- `docs/status/mvp-readiness-program.md`
- `docs/architecture/provider-data-platform.md`
- `docs/plans/2026-08-01-provider-data-platform-execution-plan.md`
- `docs/adr/2026-08-01-provider-data-platform-architecture.md`
- `docs/adr/2026-08-01-provider-adapter-v1.md`

Treat fresh Git/source/tests as stronger than this memory.

## Accepted architecture

- FastAPI/PostgreSQL remain the domain and lineage owners; Redis/Taskiq remain execution transport.
- Frontend stays provider-agnostic.
- `soccerdata` is the primary approved non-odds ingestion adapter.
- `penaltyblog` is the primary local feature/rating/model/backtest engine; its scrapers are not implicitly allowed.
- Licensed APIs are preferred for production odds/live data.
- `OddsHarvester` remains a bounded odds adapter/fallback subject to upstream approval.
- Separate `adapter_key` from actual upstream `source_key`; rights, quota, capability and freshness policy are source-scoped.
- Provider Envelope v2 must add versions, correlation, freshness and provenance, preserve v1 compatibility, and quarantine invalid/unknown-major payloads before normalization.
- Multi-source Team/Competition/Match identity requires a separate accepted ADR and expand-only migration gate.
- Use backend-owned, separately deployable HTTP/browser/model worker pools for isolation without autonomous provider APIs/databases.
- Benchmark cold/warm lanes with pre-registered coverage, parity, confidence and resource criteria before promotion.

## Approved execution

The P0-P8 dependency DAG and gates live only in the canonical plan. Do not duplicate the task graph in memory.

Completed first implementation slice (G001/P1):

- tasks `PDP-100 + PDP-100A + PDP-101 + PDP-102 + PDP-103 + PDP-105 + PDP-106 + PDP-107`;
- caller `backend/app/diagnostics/provider_canary.py::verify_provider_runtime`;
- operation `goal_expectancy`;
- identity `(adapter_key=penaltyblog, source_key=local-model)`;
- capability `predictions`;
- execution context `canary`, allowed with no bypass;
- preserve the existing bridge payload and output assertion;
- no migration, API route, nested-project edit or live provider call.

The source descriptor now owns explicit production, quota and freshness
policy. Provider Envelope v2 keeps `envelope_version` separate from payload
`schema_version`, freezes freshness/provenance metadata, rejects auth state,
and produces deterministic fully redacted quarantine artifacts before
normalization. Provider policy decisions record safe adapter/source/context,
outcome, reason code and trusted operation identity for allow and reject paths.

G002/P2 now has an accepted provider-scoped identity/schema ADR and revisions
`030`-`032`. The backend owns trusted-registry observation persistence,
digest-only quarantine, receipts/conflicts/retention, canonical
Team/Competition, temporal Team/Competition/Match mappings, typed review
candidates, a deterministic exact-singleton resolver, and a stable review
queue. Local PostgreSQL evidence includes clean `001 -> 032`, `029 -> 032`,
invalid concurrent-index recovery, 13 real concurrency/retention/RESTRICT/
cleanup gates, and previous-image unlinked Match CRUD. `PDP-206` remains open;
do not invent legacy lineage without demonstrable identity and canonical
envelope evidence.

G003/P2.5 adds backend-owned `control`, `provider-http`, `provider-browser` and
`model-cpu` lanes under migration `033`. Redis carries only `run_id` as the
business payload; PostgreSQL owns lane/version, delivery generation, bounded
retry, lease and execution-token fencing. `control/legacy-control/v0` remains
the compatibility contract for old rows and the undecomposed World Cup flow.
New-work admission is separate from consumer enablement so a lane can reject
new work while its original v1 queue drains; v1 work is never repatriated to
control. PostgreSQL advisory locks enforce configurable lane backlog caps.
Baseline observability consists of bounded lane snapshots, real cgroup-v2 peak
counters when available, and stable alert evaluation; notification delivery
and dashboards remain P6. Retry, lease recovery, reconciliation and publication
use canonical database lock order `task_outbox -> scheduled_job_runs`;
scheduled and direct scrape retries do not pre-lock the run. G003 closed with
737 backend tests, 3 dedicated PostgreSQL gates, architecture CLEAR,
independent verifier PASS and code review APPROVE. The next implementation gate
is G004/P3 soccerdata ingestion.

G004/P3 adds backend-owned, checkpointed `soccerdata-ingestion/v1` jobs for the
approved non-odds operations. MatchHistory and ESPN use `provider-http`;
Understat uses `provider-http`; FBref uses `provider-browser`. Public jobs start
at page zero and derive immutable monotonic cursors internally. Each page is
authorized before external work, acquired outside the database transaction,
then committed under the execution-token fence. Page datasets remain staged
until a terminal page proves continuous predecessors and publishes the group.
Canonical content is separate from generation-page membership, allowing
identical and reverted content to be reused across snapshot heads. Page-zero
`no_data` advances an explicit empty generation head without creating an empty
canonical dataset.

Canonical content identity hashes source plus payload and excludes acquisition
timestamps/cache telemetry. Cache attestations are TTL/future-skew checked;
valid warm hits bypass upstream quota, while actual upstream reads use a
source-scoped persistent `fcntl` rate ledger in the shared soccerdata cache
directory. This limiter is a single-host/shared-filesystem contract and must be
replaced by a shared limiter or provider gateway before horizontal rollout.
Timeout/transport `BridgeError` failures enter the durable retry taxonomy; a
retry replays already committed pages and resumes at the next cursor. Both
development Compose variants now mount/configure soccerdata on the HTTP and
browser workers; production uses the immutable image. Source descriptors stay
`APPROVAL_REQUIRED`, and no live provider access is authorized by this work.

G004 closed its offline gate with migration `034`, full PostgreSQL-backed
backend verification, dedicated concurrency/resume/publication gates,
production contracts, Compose rendering and independent acceptance PASS. The
next implementation gate is G005/P4 penaltyblog modeling over canonical
datasets; nested penaltyblog remains read-only.

G005/P4 adds strict content-addressed feature/training/model/prediction
artifacts and immutable train/backtest/predict jobs on `model-cpu`. Prediction
and historical evaluation use point-in-time canonical generations, exact
provider observations, typed odds snapshot/entry lineage and runtime/model/data
fingerprints. Backtest reuses the trained artifact and rejects chronology
leakage. The real offline penaltyblog smoke preserved exact 1X2 parity and
reduced the four-target prediction path by 74.7%; the resident worker stays
disabled because RSS/isolation promotion was not proven.

Ticket eligibility is fail-closed for P4. Pinned provider home/away, kickoff and
competition identity drive scan, activation, refresh and portfolio exposure;
active exposures revalidate the exact output fingerprint once per run.
Migrations `035`-`036` own artifacts and append-only terminal evidence, `037`
blocks deletion of governed runs with retained ticket lineage, and `038` adds
an indexed `RESTRICT` FK that closes the concurrent insert/delete race. The FK
is intentionally `NOT VALID` because one known local legacy snapshot is
orphaned; new references and parent deletes are enforced, while reconciliation
must not invent or silently delete lineage. G005 closed at Alembic `038`, full
PostgreSQL backend **851 passed, 1 skipped**, independent verifier PASS and code
review APPROVE. The next implementation gate is G006/P5 licensed odds lane;
live provider calls and rollout remain unauthorized.

G006/P5 adds the strict provider-agnostic `odds-observation/v1` contract,
Sportmonks v3 and OddsHarvester/OddsPortal converters, exact-decimal canonical
quotes and complete-1X2-only legacy projections. Migrations `039`-`041` add the
generic odds/runtime foundation and `042` adds durable quota reservations.
Quota reservation commits before HTTP, no database row lock crosses egress,
reconciliation is exact, expired ambiguous calls become conservative
`uncertain` charges, and duplicate acquisition identities never call upstream
again automatically.
Accepted ProviderObservations commit before terminal quota reconciliation and
replay by ID after reconciliation failure; query authentication is attached
below ordinary httpx logging.

`fetch_latest_odds` is an immutable, secret-free `licensed-odds-job/v1` on the
`provider-http` lane with stable per-run 10/25/50/100 canary cohorts and pre-admission
exclusion. It cannot fall through to the browser scraper. OddsHarvester remains
a separate, bounded and authorized provider-browser fallback only for approved
transient/quota reasons. Offline fixtures and statistical harnesses are not
promotion evidence; `PDP-505`/`PDP-505A`, commercial rights, credentials, live
calls and public rollout remain HOLD. Fresh focused evidence: 201 PostgreSQL-
integrated tests, Ruff pass and Alembic `042` with no new upgrade operations.
The next implementation gate is G007/P6-P7 observability/operator surfaces.

G007/P6-P7 adds a bounded, redacted, admin-only provider runtime API and a
provider-agnostic Monitoring panel. It exposes safe source coverage,
freshness, cache/circuit/quota state, lane pressure, stable alert codes and
backfill/normalize/features/model phase aggregates. Observation coverage is
capability-aware; SQL filters eligible phase work before independent bounded
active/terminal samples. `revalidated` cache evidence is `mixed`, and missing
persisted runtime state is `unknown`, never implicitly healthy. Non-admin
clients make zero runtime requests. Migration `043` adds recent-observability
indexes and the operator runbook covers disable/drain/failover/replay.

Fresh local gates: PostgreSQL/API 15 passed, full backend 934 passed/1 skipped,
Alembic 043 head/check, frontend check 0/0, 125 unit, build and E2E typecheck,
60/60 hybrid, 3/3 production PWA, plus 530/530 bounded recovery repetitions.
Independent G007 review APPROVE. Protected-environment trace/dashboard proof,
production-duration worker-restart soak, live-authorized E2E, provider
commercial/credential/canary approval and every protected/public release gate
remain HOLD. The next gate is G008 final cleanup,
invariant audit, independent reviews and durable handoff; do not deploy or
publish from this checkpoint.

G009/P8 resolves the final soccerdata transaction-boundary review blocker.
Replay miss rolls back only the transaction opened by its own read probe before
external acquisition. If the caller already owns a transaction, implicit fetch
fails closed before the bridge without committing or rolling back caller work;
the supported composed path is explicit fetch followed by batch persistence.
The scheduled runner probes replay in a dedicated short-lived session so its
rollback cannot expire the worker's run/job ORM identities, then independently
commits every staged page before following its cursor, while terminal
generation publication remains atomic. Fresh local evidence: 71 focused
soccerdata/PostgreSQL/scheduler tests, full backend 938
passed/1 skipped, Ruff/format, Alembic 043 head/check, root contracts 35,
frontend check 0/0, unit 125 and build; preceding browser evidence remains
hybrid 60/60 and PWA 3/3. The bounded cleanup was a justified no-op. Local
architecture completion does not authorize live provider calls, protected
release or public rollout; all external gates in the canonical plan/status
remain HOLD.

Sequential review: architect requested revisions; critic requested revisions; all blockers were incorporated; final critic verdict APPROVE.

Release boundary remains unchanged: local foundation work may proceed, but protected RC and public MVP remain HOLD behind existing external gates.
