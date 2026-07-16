# Platform Hardening

- Canonical status: `docs/status/current-platform-status.md`.
- Active product: `frontend/` SvelteKit + `backend/` FastAPI/PostgreSQL.
- Canonical flow: Prepare -> Analyze -> Tickets review -> explicit activation ->
  Monitoring/settlement.
- Migration head verified at `021`; quote refresh/closing evidence is append-only
  and revisioned.
- Risk uses real kickoff, exact rolling `league_window_hours`, accumulator stake
  deduplication, and fail-closed missing context.
- Generated ticket batches remain non-financial until explicit activation.
- External placement is disabled; paper-local simulation only.
- Last 2026-07-16 gates: backend 430 tests, frontend 24 unit tests, Svelte check
  clean, production build clean, Playwright hybrid 38/38 without retries.
- Parent checkout is intentionally dirty and uncommitted. Never reset/clean it;
  inspect the nested `OddsHarvester` status separately.
- `alembic check` retains broad historical index/ORM drift. Quote-history drift
  was fixed; do not autogenerate a destructive catch-all migration.
