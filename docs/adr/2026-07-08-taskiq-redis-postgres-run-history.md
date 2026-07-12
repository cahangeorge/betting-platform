# ADR: Taskiq + Redis workers with Postgres run history

Date: 2026-07-08

## Decision

Use FastAPI as the API process, Taskiq + Redis Streams as the long-running job execution layer, and Postgres as the durable source of truth for scheduled jobs, run history, lineage, tickets, and settlement.

## Included

- `taskiq` + `taskiq-redis` for background workers.
- Dedicated API, worker, and scheduler processes.
- `scheduled_job_runs` in Postgres for status, artifacts, attempts, errors, and durations.
- Inline queue backend for deterministic tests.
- Cython only for measured CPU-bound hotspots after profiling.

## Excluded

- Celery
- Dragonfly
- ClickHouse
- NestJS
- Go Fiber
- PyPy
- Mojo

## Rationale

The current bottlenecks are orchestration, long-running scrapes, DB round trips, prediction batching, and truthful lineage. A full backend rewrite or alternate datastore would increase migration risk without addressing the immediate bottlenecks. Taskiq fits the async FastAPI backend with less operational surface than Celery, while Postgres keeps business truth auditable.

## Consequences

- FastAPI no longer owns long-running execution by default.
- Redis is transport/runtime infrastructure, not business truth.
- Postgres run history is the UI and audit contract.
- Future performance work must be profiling-led before Cython changes.
