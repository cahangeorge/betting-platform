# ADR: Provider worker lanes and fenced execution

Date: 2026-08-01
Status: Accepted

## Context

The backend already uses Taskiq + Redis Streams for transport and PostgreSQL
for durable run history. A single generic queue currently mixes control work,
HTTP provider calls, browser scraping and CPU-heavy model execution. A slow
browser process can therefore delay control jobs, while a worker restart can
leave an old process able to finish after a lease has been reclaimed.

P2.5 requires isolation without turning providers into autonomous services. The
worker contract must remain backend-owned, carry no business payload in Redis,
and preserve the provider identity, observation lineage and idempotency rules
accepted by the identity ADR.

This ADR extends (and does not replace) `2026-07-08-taskiq-redis-postgres-run-
history.md`, `2026-07-30-hybrid-scraping-pipeline-v2.md` and the provider data
platform architecture ADR.

## Decision

### Logical lanes and physical queues

Use four logical lanes:

| Lane | Work | Physical queue | Initial worker cap |
| --- | --- | --- | --- |
| `control` | scheduling, recovery, outbox and short control tasks | `bet` (legacy queue) | 1 process, 2 async tasks, prefetch 2 |
| `provider-http` | approved API/HTTP adapters and cache reads | `bet-provider-http` | 1 process, 4 async tasks, prefetch 4 |
| `provider-browser` | Playwright/Patchright/Camoufox browser work | `bet-provider-browser` | 1 process, 1 async task, prefetch 1 |
| `model-cpu` | penaltyblog/model fitting, scoring and backtests | `bet-model-cpu` | 1 process, 1 async task, prefetch 1 |

Each dedicated queue has its own consumer group and runtime heartbeat. The
legacy `bet` queue remains the compatibility target for control tasks during
rollout. Trading keeps its existing separate broker and is outside this ADR.
The caps are safe initial values, not a promise of available host capacity;
raising them requires measured RSS, PID and latency evidence.

### Backend-owned work contract and canonical broker

PostgreSQL is authoritative for the work specification. A Redis/Taskiq message
contains only a stable `run_id` (and the versioned task envelope required to
route it); it never contains provider credentials, raw provider payloads or a
second business copy of the work. A worker loads the run and its persisted
specification, validates the contract version and lane, then executes through
the existing backend bridge/policy services.

`legacy-control/v0` is the server default and backfill contract for pre-existing
runs. Every `world_cup_pipeline` path, including scheduled variants, and every
autonomous session path selects `control`/`legacy-control/v0`/`max_attempts=1`
from the operation-to-lane registry. These runs are never silently upgraded to
a fenced lane. New work must opt into the explicit `worker-lanes/v1` contract
and receive a lane from that same validated registry. Binary rollback is
therefore a legacy-only operation: the old worker consumes
`bet`/`legacy-control/v0`, while fenced workers must not be pointed at legacy
payloads.

The canonical broker remains `backend/app/tasks/broker.py` and its single
`RedisStreamBroker` configuration. Dedicated consumers use the same broker
contract with a validated physical `queue_name`/Taskiq dynamic queue label;
they do not introduce four competing decorators or four independent task
registries. Every consumer group is unique per physical queue. The routing
registry validates the lane before publishing and rejects arbitrary caller
queue labels.

New work uses an explicit operation-to-lane registry. Routing is not inferred
from provider names, arbitrary task-name substrings or caller-selected queues.
Composite scrape-plus-predict operations are routed to `provider-browser`
until they are decomposed; pure model operations use `model-cpu`. The existing
`world_cup_pipeline` and any autonomous session-based execution remain on the
legacy control path and are excluded from v2 lane rollout until decomposed into
backend-owned run specifications. Unknown or unsupported operations fail closed
in `control` and are recorded as a policy failure.

### Migration 033 minimum schema

Migration `033_provider_worker_lanes` adds the following additive fields.

`scheduled_job_runs`:

- `queue_lane` (`varchar(32)`, non-null, default `control`);
- `queue_contract_version` (`varchar(32)`, non-null, server default
  `legacy-control/v0` for the expand/backfill phase; new fenced rows set
  `worker-lanes/v1` explicitly);
- `execution_token` (`varchar(64)`, nullable until a run is claimed);
- `queue_wait_ms`, `peak_rss_bytes`, `peak_pid_count` (nullable non-negative
  telemetry columns);
- `failure_kind` (`varchar(64)`) and `retry_disposition` (`varchar(32)`);
- `metrics` (nullable JSON object for request/cache/fallback/freshness and
  other bounded lane metrics);
- an index on `(queue_lane, status, queued_at)`.

`next_attempt_at` already exists from migration 009 and remains the durable
execution retry/recovery schedule; migration 033 does not duplicate it.

`task_outbox` adds `queue_lane` and the same contract version, both non-null
with `control`/`legacy-control/v0` defaults for existing rows, plus a
status/lane/available-at index. `UNIQUE(run_id)` remains the single durable
outbox row per run. The outbox service must reject a row whose lane or contract
version does not equal the referenced run. Existing rows are backfilled to
`control`/`legacy-control/v0` and remain publishable during rollout. The
composite unique key on
`scheduled_job_runs(id, queue_lane, queue_contract_version)` and the matching
composite foreign key from `task_outbox` prevent lane/contract drift. Lane
allow-list checks and non-negative telemetry checks are enforced in the
database. A `running => execution_token IS NOT NULL` check is deliberately
deferred until the N-1 drain has completed; the application fence is enforced
first so legacy rows can be drained safely. No provider payload is copied into
these columns.

`task_outbox.delivery_generation` is additive. `attempts` continues to count
publish failures in the current generation. The lease reaper reuses the same
outbox row, increments `delivery_generation`, resets `attempts` to zero and
sets `pending`; it never inserts a second outbox row or violates `UNIQUE(run_id)`.

### Lease, fencing and retry taxonomy

Claiming a queued or expired run occurs in one PostgreSQL transaction under the
existing claim lock. The claimant generates a fresh random `execution_token`,
increments the attempt, sets `running`, records `claimed_at` and
`lease_expires_at`, and returns the token to the worker. Heartbeats, progress
telemetry and terminal updates include both `run_id` and token and use a
conditional update that matches the current token and `running` status. A
reclaimed run invalidates the old token. A worker that loses the token must stop
before its next backend-owned write; late heartbeats and finishes become no-op
stale-attempt events.

Before committing a business-side effect in the same database transaction, the
execution path calls a conditional fence helper (for example,
`assert_task_run_fence(db, run_id, execution_token)`) which performs a
`SELECT ... FOR UPDATE` or token-predicate update and raises a stale-fence
error when no matching `running` row remains. The helper and the effect commit
belong to the same transaction; heartbeat renewal uses a separate short
transaction and may never resurrect a lost token. This prevents a stale worker
from changing current run state. External effects—HTTP requests, provider
writes, browser actions or model subprocesses—cannot be rolled back by
PostgreSQL; fencing therefore does **not** promise exactly-once external side
effects. Adapters must use stable idempotency keys, observation digests and
reconciliation on retry. The platform promises at-most-one committed backend
result for a valid token, not exactly-once execution of an upstream call.

Failure kinds are bounded and machine-readable:

- `timeout`, `transport`, `provider_429`, `provider_5xx`, `process_lost` and
  `resource_limit` are transient and retryable;
- `anti_bot`, `forbidden`, `policy_denied`, `validation`, `schema`,
  `contract_mismatch` and `identity_conflict` are terminal unless an operator
  creates a new approved run;
- `stale_fence`, `lease_expired` and `cancelled` are terminal for the attempt;
  recovery may create/requeue a new attempt without copying business state.

Initial maximum attempts are 4 for `provider-http`, 2 for
`provider-browser`, and 3 for `model-cpu`/`control`. Backoff is bounded and
jittered. Transport publication retries remain governed by the existing
outbox; execution retries never bypass PostgreSQL run history.

The scheduler owns a PostgreSQL lease reaper. Under the scheduler/advisory
lock it moves expired `running` rows to `queued`, clears
`lease_expires_at`/heartbeat, invalidates `execution_token`, sets bounded
`next_attempt_at`, and preserves the same run identity. Exhausted attempts move
to a terminal timeout state. The reaper exclusively reuses the existing outbox
row, increments its delivery generation, resets publish-failure attempts to
zero and sets it pending; it never inserts a second row or increments outbox
delivery attempts for an execution retry. Execution `attempt` and outbox `attempts` are
separate counters. A redelivered Taskiq message is claimed before lease
recovery when possible; only an expired lease can be reclaimed, and a stale
message cannot finish a newer attempt.

### Admission control, backpressure and outbox replay

Backpressure is decided from PostgreSQL active counts and lane caps while
holding a fixed two-key `pg_advisory_xact_lock(namespace, lane_id)`. The lock
helper owns stable constants `LANE_ADVISORY_LOCK_NAMESPACE=8462033` and lane IDs
`1=control`, `2=provider-http`, `3=provider-browser`, `4=model-cpu`; callers use
the helper rather than inventing lock numbers. The `_scheduler_lock`
process/local lock is only a contention optimization; it is not authority and
cannot replace the PostgreSQL advisory lock. Redis queue depth is a signal,
not business truth. When a lane is saturated, admission fails before a durable
run/outbox row is created. API callers receive a bounded `503` with
`Retry-After`; scheduled work remains due and the scheduler continues other
lanes, recovery and outbox dispatch. Queue age measures already admitted work
rather than work admitted beyond the cap. Control is never rejected because a
provider lane is full.

Admission and consumer lifecycle are separate controls. An admitted lane may
create new runs. A draining lane rejects new admission while its publisher,
lease recovery, retries and dedicated consumer remain enabled for existing
work. A disabled lane may lose its consumer only after the drain gate passes.
Disabling admission never changes a persisted lane, contract version, task name
or run identity.

Outbox replay selects pending/expired rows by `queue_lane` and preserves the
run's lane and contract version. A stale predecessor check is scoped to the
same run and lane, not globally across unrelated lanes. Replay is idempotent:
duplicate transport messages resolve to the same `run_id` and token claim.
Pending and retry generations always republish to their original dedicated
queue. A `worker-lanes/v1` row is never rewritten or repatriated to control.

### Metrics and readiness

Every run records queue wait, execution runtime, attempt number, retry/failure
kind, fallback count, freshness outcome and (where the worker can measure it)
peak RSS and PID count. Metrics and structured events include lane and run ID,
with credentials, cookies, authorization headers and provider payloads
redacted. The G003 baseline provides a bounded PostgreSQL snapshot collector
and stable alert evaluator for queue age, runtime inputs, retry/fallback rate,
freshness, RSS and PID caps. Notification delivery and production dashboards
remain the P6 operational rollout gate rather than being implied here.

Readiness requires the scheduler plus every enabled lane heartbeat:
`worker:control`, `worker:provider-http`, `worker:provider-browser` and
`worker:model-cpu`. A disabled lane is not required to be ready. Missing or
stale lane heartbeat fails worker readiness and is visible in the existing live
runtime endpoint.

### Compose rollout and rollback

Compose adds one worker service definition per lane, initially using the common
backend image and read-only nested-project mounts. Each service receives only
its lane queue, cap, timeout and resource settings. The first rollout enables
control and HTTP lanes, then browser and model lanes after queue-age and RSS
evidence. Later releases may split images, egress and secrets when the threat
model or benchmark justifies it; this ADR does not grant provider credentials
to a lane.

Rollout is staged so old and new binaries can coexist:

1. **N:** apply migration 033 with `control`/`legacy-control/v0` defaults and
   backfill, keeping the legacy `bet` consumer authoritative;
2. **N-1:** deploy fence-aware code, lane registry and reaper while accepting
   legacy control messages; drain old runs and observe dual metrics;
3. enable new routing and dedicated consumers for HTTP, browser and model,
   while control remains on `bet`;
4. after the N-1 drain, enable the database running-token enforcement check and
   reject un-fenced claims. If the check cannot be added safely in-place, ship
   it as follow-up migration `034` after the drain;
5. retire legacy routing only after queue-age, restart and resource gates pass.

Rollback is drain-first, not queue repatriation. Operators first remove a lane
from the admission set everywhere while leaving it consumer-enabled. Existing
queued/running runs, scheduled retries and pending outbox generations drain
through the original physical queue and `worker-lanes/v1` contract. The lane
may become disabled only after PostgreSQL has no active run or pending outbox,
Redis has no pending delivery/lag, no live lease or retry remains, and final
heartbeat/metrics evidence is captured. Only then may readiness omit the lane
and Compose scale its consumer to zero.

A lane-aware binary may be rolled back to a binary that does not understand v1
only after every v1 lane passes that drain gate. During an emergency API/control
rollback, the last fence-aware scheduler, outbox publisher and dedicated
consumers remain until v1 work is terminal. Migration 033 and run/outbox history
remain intact. A lane must not be admitted in production until heartbeat,
routing and recovery tests pass.

## Alternatives considered

- **One queue with more generic workers:** rejected; it preserves browser/CPU
  head-of-line blocking and makes resource limits ambiguous.
- **A microservice/database per provider:** rejected; it duplicates policy and
  lineage and adds operational boundaries before measurement justifies them.
- **Redis as the lease or business authority:** rejected; Redis transport state
  is reconstructible and cannot provide the audit and idempotency guarantees of
  PostgreSQL.
- **Exactly-once claims for upstream calls:** rejected; external HTTP/browser
  effects are not transactional with PostgreSQL.

## Consequences

Positive:

- control jobs progress independently of slow browser/model work;
- queue/resource behavior is measurable per lane;
- restarts recover through durable run history and fenced attempts;
- adapter identity, freshness and observation lineage remain backend-owned.

Negative:

- migration and compose configuration become more explicit;
- four lane heartbeats and dashboards must be operated;
- browser/model capacity may initially be lower than a permissive shared pool;
- external side effects still require adapter-level idempotency and repair.

## Verification and acceptance gates

Implementation must add `backend/tests/test_provider_worker_isolation.py` and
extend task-run, Taskiq runtime/config and production-contract tests. Before
the P2.5 gate is marked complete, evidence must show:

1. a blocked browser job does not delay a control job;
2. lane caps and backpressure hold under controlled load;
3. a worker restart/process loss recovers the lease without duplicate committed
   backend state;
4. real local Redis/Taskiq integration records queue age, retries and terminal
   state for each lane;
5. resource probes record RSS/PID bounds and alert/recovery behavior;
6. clean migration upgrades and `alembic check` pass;
7. all tests use mocked/local providers—no live provider, credential or public
   rollout is part of acceptance.

Relevant implementation paths are `backend/app/models/job.py`,
`backend/app/services/task_runs.py`, `backend/app/services/scheduled_jobs.py`,
`backend/app/tasks/broker.py`, `backend/app/tasks/runtime.py`,
`backend/app/tasks/jobs.py`, `docker-compose.yml` and
`docker-compose.podman.yml`.
