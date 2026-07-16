# Current Platform Status

> Last verified: 2026-07-17, branch `codex/platform-hardening-2026-07-12`.
> This is the first status document to read in a new coding session. Re-check the
> real checkout before relying on the snapshot.

## Active platform

- Product UI: `frontend/` (SvelteKit 2, Svelte 5), local dev port `5175`.
- Product API: `backend/` (FastAPI, SQLAlchemy, Alembic), local dev port `8001`.
- Database: PostgreSQL; verified migration head is `021`.
- `betfront/` is archived. Do not use it for current UI work.
- `OddsHarvester/`, `penaltyblog/`, and `soccerdata/` are nested projects. Inspect
  their own status and instructions before any change.

## Implemented workflow

The current operator path is:

```text
Prepare -> Analyze -> Tickets review -> explicit activation -> Monitoring/settlement
```

Implemented contracts:

- Analyze can execute multiple active strategies while preserving exact dataset
  and prediction-run lineage.
- Tickets accepts multiple `run_ids`, retains each leg's model prediction, and
  keeps generated batches non-financial until explicit activation.
- Ownership checks, deduplication, batch lifecycle rules, and E2E cleanup are
  enforced by the backend.
- Quote evidence is persisted through generation, refresh, activation, and
  closing; migration `021` makes refresh/closing history append-only and
  revisioned.
- CLV uses the latest deterministic quote revision and prefers activation over
  refresh over generation as its reference evidence.
- Bankroll policies support conservative flat/fractional-Kelly staking, hard
  ticket/open-exposure limits, cooldowns, and explicit automation controls.
- League exposure uses exact rolling `league_window_hours` windows based on real
  kickoff times. Accumulator stakes are deduplicated and missing kickoff context
  fails closed.
- Model governance, validation evidence, calibration/CLV monitoring, public SEO,
  legal pages, responsible-gambling content, and responsive workflow surfaces
  are present in the active platform.
- Refresh tokens are unique, session-bound, single-use, transactionally rotated,
  revoked on logout, and restored before protected SvelteKit page loaders run.
- Global strategy mutations are admin-only in both API authorization and UI;
  non-admin users receive a read-only catalog.
- Keyboard navigation includes a working skip link, focus-trapped command
  palette, visual-order arrow traversal, and focused-item activation.
- External/live bet placement remains disabled; supported execution is local
  paper simulation only.

## Database lineage

Recent migration chain:

```text
012 prediction run lineage
013 ticket batch prediction lineage
014 prediction run match-count backfill
015 concurrent prediction-run guard
016 ticket-leg audit snapshots
017 odds quote lineage
018 bankroll risk policy
019 model governance
020 monitoring snapshot ownership
021 revisioned ticket quote history (current head)
```

Migration `021` was verified on PostgreSQL with downgrade `021 -> 020`, upgrade
`020 -> 021`, and final `alembic current` output `021 (head)`.

## Last verification evidence

Fresh verification completed on 2026-07-17:

- `backend/.venv/bin/ruff check app tests alembic`: passed.
- `backend/.venv/bin/pytest -q`: **447 passed**.
- `git diff --check`: passed.
- `frontend/pnpm check`: **0 errors, 0 warnings**.
- `frontend/pnpm test:unit`: **27 passed**.
- `frontend/pnpm build`: passed.
- Hybrid Playwright, Chromium, no retries: **41 passed** in approximately 3.0m.
- Refresh-only SSR rotation stability loop: **15/15 passed** without retries.
- Backend health: `GET http://127.0.0.1:8001/health` returned
  `{"status":"ok","app":"bet-backend"}`.
- Frontend `http://127.0.0.1:5175/about` returned HTTP `200`.

These are historical verification results, not a substitute for rerunning the
smallest relevant checks after new edits.

## Known residuals and cautions

1. The platform hardening changes are collected on
   `codex/platform-hardening-2026-07-12`; inspect branch/PR state before adding
   follow-up work.
2. The parent sees `OddsHarvester` as modified from pre-existing nested work. It
   was not changed by the platform-hardening implementation.
3. `alembic check` still reports historical ORM/index drift across older tables.
   The drift introduced around `ticket_leg_quote_snapshots` was resolved; the
   remaining report is broader legacy alignment work and must not be converted
   blindly into a destructive migration.
4. Local dev processes may no longer be alive in a future session even though
   they were healthy when this status was written.

## New-session checklist

From the repository root:

```bash
cat AGENTS.md
git status --short --branch
git submodule status
```

Then verify the current platform without touching nested projects:

```bash
cd backend
.venv/bin/alembic current
.venv/bin/ruff check app tests alembic
.venv/bin/pytest -q

cd ../frontend
pnpm check
pnpm test:unit
pnpm build
```

For an integrated local run:

```bash
# backend/
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# frontend/
pnpm dev
```

Run Playwright only after both services are reachable. The integrated defaults
are frontend `127.0.0.1:5175` and backend `127.0.0.1:8001`.

## Primary implementation references

- Workflow plan: `docs/plans/2026-07-13-analysis-tickets-workflow.md`
- Product/UI contract: `DESIGN.md`
- Quote lineage: `backend/app/models/odds_lineage.py`,
  `backend/app/services/clv_tracking.py`,
  `backend/alembic/versions/021_revision_ticket_quote_history.py`
- Risk controls: `backend/app/services/portfolio_risk.py`,
  `backend/app/services/risk_policy.py`
- Ticket orchestration: `backend/app/services/ticket_engine.py`
- Browser proof: `frontend/tests/e2e/hybrid/`
