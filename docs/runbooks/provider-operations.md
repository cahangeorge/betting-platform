# Provider operations: disable, drain, recover and replay

Status: local/operator contract. This runbook does not authorize a provider,
credential, live call, production change or browser fallback.

## Safety invariants

- PostgreSQL is business truth; Redis/Taskiq is delivery only.
- Disable **admission** before stopping consumers. Keep the original lane
  enabled until its admitted work drains.
- Never delete or rewrite ProviderObservations, quota reservations, task runs,
  outbox rows or checkpoints to make a retry appear clean.
- Never move a v1 run to another lane, reuse another source identity, copy an
  execution token, or place credentials in a JobSpec/operator note.
- A raw HTTP 200, discovered link or queued task is not success. Require the
  terminal run state and the provider runtime/lineage evidence.

## Observe

Administrators use `GET /api/v1/provider/runtime` or the Monitoring page. The
endpoint is admin-only; non-admin clients neither request it nor render the
panel. The response is deliberately bounded and redacted:

- source runtime: circuit and quota counters, reconciliation time, safe
  coverage/freshness/quality aggregates;
- a source without persisted runtime evidence is `unknown`, never implicitly
  healthy; soccerdata cache revalidation is `mixed` because it both reuses the
  local representation and performs upstream validation;
- lane runtime: queued/running, oldest queue age, retries, fallbacks,
  freshness failures, peak RSS/PID count;
- pipeline progress: bounded queued/running/attention counts for
  backfill, normalize, features and model, derived only from persisted run and
  lineage aggregates. Eligible active and terminal runs are filtered in SQL
  before their independent bounded samples, so unrelated history cannot hide
  active provider/model work;
- stable alert codes only, never raw exception text, URLs, payloads or tokens.

Investigate these alert codes:

| Code | First action |
|---|---|
| `queue_age_high` | Stop new admission for the affected lane; keep consumers draining. |
| `rss_high` / `pid_high` | Stop admission, capture the terminal run/worker evidence, restart only the affected worker pool. |
| `retry_rate_high` | Inspect failure taxonomy and upstream health; do not increase attempts reflexively. |
| `fallback_rate_high` | Keep automatic fallback disabled and verify source rights/scope. |
| `freshness_failure` | Block ticket/model promotion from stale or partial inputs. |
| `quota_exhausted` | Perform zero new egress until the exact provider window resets. |

## Disable and drain one provider

1. Pause the exact scheduled job in Monitoring (or through the authenticated
   scheduled-job API). This prevents new logical acquisitions.
2. In a reviewed configuration change, return the source descriptor to
   `APPROVAL_REQUIRED` before removing/rotating credentials. Credential absence
   is not the policy control.
3. If all new work on a lane must stop, remove that lane from
   `BET_TASKIQ_ADMITTED_LANES`. Do **not** remove it from
   `BET_TASKIQ_ENABLED_LANES` until queued/running counts reach zero.
4. Confirm the runtime endpoint shows no new admission and the original lane
   drains. Preserve immutable observations and terminal history.
5. Only then stop/restart the affected worker pool. Do not restart unrelated
   browser/model/control workers.

## Worker restart and lease recovery

1. Stop admission and allow the graceful worker timeout first.
2. If a worker disappears, leave the run and outbox rows intact. The scheduler
   requeues an expired lease using a new execution fence until `max_attempts`;
   stale workers cannot finish under the old fence.
3. Restart the same lane consumer with the same queue contract. It receives
   only `run_id` and reloads durable state from PostgreSQL.
4. Verify one terminal run, no duplicate observation/snapshot, and a cleared
   queued/running count. An exhausted lease becomes a terminal failure rather
   than looping forever.

Regression evidence lives in:

- `backend/tests/test_task_runs.py` (stale lease claim/fencing);
- `backend/tests/test_provider_worker_isolation.py` (expired lease recovery,
  alert evaluation and lane admission/drain);
- `backend/tests/test_worker_lanes_postgres.py` (PostgreSQL concurrency);
- `backend/tests/test_licensed_odds_postgres.py` (reservation lock and staged
  observation replay after reconciliation failure).

## Replay by workload

### Licensed odds

- Same acquisition identity: zero second egress. If accepted observations were
  staged, the retry reloads their receipt-bound IDs, reconciles quota exactly
  once and continues materialization.
- Reserved with no staged observation after an ambiguous crash: expiry becomes
  `uncertain`, charges conservatively and opens the circuit. Investigate before
  an operator creates a new explicit acquisition identity.
- `quota_exhausted`, timeout, 5xx and transient-circuit reason codes do not by
  themselves launch OddsHarvester. Browser fallback still requires approved
  source rights and an immutable bounded competition/market/time window.

### soccerdata

- Replay the original JobSpec. Completed pages are loaded from their durable
  checkpoint and execution resumes at the next cursor.
- Never edit page/start cursor/generation keys in a public scheduled job or mix
  pages from different upstream artifact generations.

### OddsHarvester

- Preserve the original scrape job and queue history. Verify the exact browser
  binary prerequisite, then create a bounded smoke job; do not recreate failed
  queue rows or infer success from discovery/HTTP status.
- OddsPortal H2H links encode the event identity in the URL fragment. The
  backend adapter must use that fragment (before optional market/scope
  suffixes), not either team slug in the path; otherwise repeated fixtures
  between the same teams can corrupt event and quote lineage.

## Failover and rollback

- Licensed API to OddsHarvester failover is intentionally **not automated**.
  The current licensed JobSpec lacks the bounded fallback scope and both sources
  remain approval-gated.
- Rollback sets candidate admission to zero, drains admitted provider-http work
  and restores only the previous approved source selector. Observations, parity
  evidence and quota history remain immutable.
- A 100% canary is still not protected release or public rollout approval.

## Local verification/soak gate

Use mocked/provider-shaped fixtures only unless live calls are separately
authorized:

```bash
cd backend
set -a; source .env; set +a
BET_TEST_POSTGRES_URL="$BET_DATABASE_URL" .venv/bin/pytest -q \
  tests/test_task_runs.py \
  tests/test_provider_worker_isolation.py \
  tests/test_worker_lanes_postgres.py \
  tests/test_provider_runtime_postgres.py \
  tests/test_licensed_odds_postgres.py
```

The 2026-08-01 G007 local recovery repetition ran this exact 53-test subset ten
times consecutively: **530/530 passed**, with each iteration completing in
1.73-1.98 seconds. This is bounded regression evidence for stale-lease fencing,
replay and PostgreSQL concurrency; it is not a production-duration soak or
promotion proof. A promotion soak must additionally record duration, workload,
real worker restart timestamps, runtime snapshots and every terminal state.
