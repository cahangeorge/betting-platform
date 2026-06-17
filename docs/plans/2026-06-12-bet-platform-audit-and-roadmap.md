# Bet Platform Audit and Roadmap

> For Hermes: use this as the anchor plan for the next implementation passes. The primary UI is the Svelte/SvelteKit app in `frontend/`.

## Goal
Turn the current project into a trustworthy PWA that helps a human user:
1. scrape matches and odds,
2. run predictions on scraped matches,
3. build tickets from those predictions,
4. track results, bankroll, and model performance.

## Current architecture snapshot
- Frontend: `frontend/` — SvelteKit 2 + Svelte 5, PWA-capable shell, same-origin `/api/*` client.
- Backend: `backend/` — FastAPI + SQLAlchemy + Postgres, prediction/ticket/auth endpoints.
- External bridges: OddsHarvester / penaltyblog / soccerdata invoked from backend bridge services.
- Existing spec: `IMPLEMENTATION-SPEC.md`.

## Audit summary
The app now boots and the Svelte frontend is the right primary UI target, but the core product workflow is still incomplete.

Current state in one sentence:
- The platform looks like a betting assistant, but the most important chain `scrape -> predict -> create ticket` is not yet reliable end to end.

## Evidence-backed findings

### P0 — mission-critical blockers

1. Scrape jobs do not ingest real match/odds data into the domain tables.
- Files:
  - `backend/app/api/v1/data.py`
  - `backend/app/services/scraper.py`
  - `backend/app/models/match.py`
  - `backend/app/models/scrape.py`
- Problem:
  - scrape endpoints create/execute jobs, but job output is stored as job output text instead of normalized `Match` / `OddsEntry` / source-linked records.
- Consequence:
  - prediction and ticket flows cannot depend on fresh scraped data.

2. Shared betslip flow is not wired as a real app-wide state flow.
- Files:
  - `frontend/src/routes/+page.svelte`
  - `frontend/src/routes/+layout.svelte`
  - `frontend/src/lib/components/BetSlipDrawer.svelte`
  - `frontend/src/lib/components/BetslipFAB.svelte`
- Problem:
  - dashboard dispatches `betslip:add`, but the drawer/fab are not backed by a single shared store and mobile FAB count is hardcoded.
- Consequence:
  - users cannot reliably move from opportunity discovery to ticket assembly.

3. Predictions are not persisted at a selection/outcome level suitable for ticket creation.
- Files:
  - `backend/app/services/prediction_engine.py`
  - `backend/app/models/prediction.py`
  - `backend/app/services/ticket_engine.py`
  - `backend/app/schemas/ticket.py`
- Problem:
  - prediction rows do not model outcome/selection cleanly, and ticket legs do not point back to prediction selections.
- Consequence:
  - no trustworthy bridge from prediction result to actionable ticket leg.

4. Backend can report successful prediction runs even when results are empty or synthetic.
- Files:
  - `backend/app/services/prediction_engine.py`
  - `backend/app/api/v1/strategies.py`
- Problem:
  - bridge failures are partially swallowed; strategy runs may still complete with fake fallback probabilities.
- Consequence:
  - user trust is damaged because success does not always mean valid predictions.

5. Ticket workflow integrity is too weak for the product mission.
- Files:
  - `backend/app/api/v1/tickets.py`
  - `backend/app/services/ticket_engine.py`
  - `backend/app/schemas/ticket.py`
- Problem:
  - settlement response contract is inconsistent, creation uses weak `legs: list[dict]`, and bankroll ownership/funds checks are incomplete.
- Consequence:
  - ticket lifecycle is fragile and not audit-safe.

6. Live/value-bet surfaces can silently fall back to demo betting data.
- Files:
  - `frontend/src/routes/live/+page.ts`
  - `frontend/src/routes/value-bets/+page.ts`
- Problem:
  - fake data is returned on API failure without a strong user-facing distinction.
- Consequence:
  - users may mistake demo intelligence for real betting opportunities.

### P1 — major product gaps

7. Navigation does not make the core workflow obvious, especially on mobile.
- Files:
  - `frontend/src/lib/components/Sidebar.svelte`
  - `frontend/src/lib/components/BottomNav.svelte`
  - `frontend/src/lib/components/CommandPalette.svelte`
- Problem:
  - `scrape` is missing from primary navigation while secondary browsing surfaces are prominent.

8. Auth/public route experience is mismatched with the operational dashboard home.
- Files:
  - `frontend/src/routes/+layout.server.ts`
  - `frontend/src/routes/+page.svelte`
- Problem:
  - `/` is public, but behaves like a logged-in operating dashboard that mostly degrades to empty state when unauthenticated.

9. PWA shell exists, but install/offline/update UX is incomplete.
- Files:
  - `frontend/src/service-worker.ts`
  - `frontend/static/manifest.json`
  - `frontend/src/app.html`
- Problem:
  - service worker and manifest exist, but there is no clear install prompt UX, update UX, or offline-aware route behavior.

10. Data Hub, Scrape, Predict, and Tickets are not yet one connected operational system.
- Files:
  - `frontend/src/routes/data/+page.svelte`
  - `frontend/src/routes/scrape/+page.svelte`
  - `frontend/src/routes/predict/+page.svelte`
  - `frontend/src/routes/tickets/+page.server.ts`
  - `frontend/src/lib/components/TicketsPanel.svelte`
- Problem:
  - each area exists, but the handoff between them is partial or manual.

### P2 — quality, trust, and maintainability gaps

11. There is effectively no automated test coverage in the repo right now.
- Evidence:
  - no `frontend` test files found
  - no backend `test_*.py` or `*_test.py` files found
- Consequence:
  - regressions in the betting workflow are likely during iteration.

12. Auth/session design is only partially implemented.
- Files:
  - `backend/app/api/v1/auth.py`
  - `backend/app/services/auth.py`
  - `backend/app/models/user.py`
- Problem:
  - refresh/session persistence and revocation model is incomplete compared with the schema shape.

13. Analytics/model attribution is not yet trustworthy enough for strategic decision-making.
- Files:
  - `backend/app/api/v1/analytics.py`
  - `backend/app/services/ensemble.py`
  - `backend/app/models/prediction.py`
- Problem:
  - PnL attribution by model and ensemble logic need stronger identity/linkage.

## Roadmap

## Phase 1 — restore truth in the core data flow
Priority: highest
Outcome: scraped data becomes real match/odds data, prediction runs are honest, and tickets rest on valid data.

### Task 1.1: Build normalized scrape ingestion
Files:
- Modify: `backend/app/services/scraper.py`
- Modify: `backend/app/api/v1/data.py`
- Modify: `backend/app/models/match.py`
- Modify: `backend/app/models/scrape.py`
- Add/modify: migration if schema changes are needed under `backend/alembic/versions/`

Deliverables:
- scraper execution stores parsed records, not only raw output
- upsert path for matches, odds, and source ids
- raw scrape payload retained for audit/debug

Verification:
- start a scrape job
- confirm new/updated `Match` and related rows exist
- confirm frontend `/data` and `/predict` can see scraped matches without demo fallback

### Task 1.2: Remove misleading fake success paths
Files:
- Modify: `backend/app/services/prediction_engine.py`
- Modify: `backend/app/api/v1/strategies.py`
- Modify: `frontend/src/routes/live/+page.ts`
- Modify: `frontend/src/routes/value-bets/+page.ts`

Deliverables:
- no synthetic fallback predictions in real runs
- no silent demo betting data without explicit demo state
- failed/partial states surfaced honestly

Verification:
- force bridge failure and confirm run/job status becomes failed/partial
- confirm UI shows explicit error/demo banner instead of pretending data is real

### Task 1.3: Document and validate bridge/runtime prerequisites
Files:
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/python_bridge.py`
- Add: `backend/.env.example` or backend setup documentation

Deliverables:
- bridge paths/env are explicit and validated at startup or first use
- operator can tell what is missing immediately

Verification:
- unset a bridge env var and confirm clear error message
- set valid paths and confirm a bridge call succeeds

## Phase 2 — make predictions actionable and ticket-safe
Priority: highest
Outcome: predictions can become auditable ticket candidates.

### Task 2.1: Redesign prediction persistence around selections
Files:
- Modify: `backend/app/models/prediction.py`
- Modify: `backend/app/services/prediction_engine.py`
- Modify: `backend/app/schemas/prediction.py`
- Modify: `backend/alembic/versions/*.py`

Deliverables:
- one prediction selection record per match + market + outcome/selection
- store probability, odds snapshot, implied probability, edge/EV, source model/run

Verification:
- run predictions for 1X2 + BTTS + O/U
- confirm DB rows distinguish selections correctly

### Task 2.2: Link ticket legs to prediction selections
Files:
- Modify: `backend/app/models/ticket.py`
- Modify: `backend/app/services/ticket_engine.py`
- Modify: `backend/app/schemas/ticket.py`
- Modify: migration under `backend/alembic/versions/`

Deliverables:
- ticket leg references source prediction selection
- ticket creation validates selections and market consistency

Verification:
- create ticket from a prediction row
- inspect stored linkage and replayability

### Task 2.3: Harden bankroll/ticket integrity
Files:
- Modify: `backend/app/services/ticket_engine.py`
- Modify: `backend/app/api/v1/tickets.py`
- Modify: `backend/app/schemas/ticket.py`

Deliverables:
- strong leg schema instead of `list[dict]`
- bankroll ownership and sufficient funds enforced
- settlement response matches declared schema

Verification:
- insufficient funds -> clear failure
- чужой bankroll / foreign bankroll -> denied
- settlement endpoint returns schema-valid response

## Phase 3 — make the Svelte UI a real workflow app
Priority: high
Outcome: a user can naturally go from scrape to prediction to ticket creation in the PWA.

### Task 3.1: Introduce a shared betslip store
Files:
- Add: `frontend/src/lib/stores/betslip.ts`
- Modify: `frontend/src/lib/components/BetSlipDrawer.svelte`
- Modify: `frontend/src/lib/components/BetslipFAB.svelte`
- Modify: `frontend/src/routes/+layout.svelte`
- Modify: any page that currently adds betting actions

Deliverables:
- one source of truth for betslip state
- mobile/desktop drawers share the same legs
- FAB count is real

Verification:
- add from dashboard, navigate to predict/tickets, confirm state persists in-app

### Task 3.2: Re-center IA around the core mission
Files:
- Modify: `frontend/src/lib/components/Sidebar.svelte`
- Modify: `frontend/src/lib/components/BottomNav.svelte`
- Modify: `frontend/src/lib/components/CommandPalette.svelte`
- Optionally modify: `frontend/src/routes/+layout.server.ts`

Deliverables:
- primary nav emphasizes `Dashboard`, `Scrape`, `Predict`, `Tickets`, `Account`
- `Data`, `Board`, `Live`, `Value Bets` become secondary/supporting surfaces

Verification:
- mobile nav exposes the full main workflow without hidden steps

### Task 3.3: Connect high-intent pages to ticket creation
Files:
- Modify: `frontend/src/routes/+page.svelte`
- Modify: `frontend/src/routes/predict/+page.svelte`
- Modify: `frontend/src/routes/value-bets/+page.svelte`
- Modify: `frontend/src/routes/live/+page.svelte`
- Modify: `frontend/src/lib/components/TicketsPanel.svelte`

Deliverables:
- prediction rows can be added directly to betslip
- value bets can be added directly to betslip
- live opportunities can be added directly to betslip
- tickets page becomes the final review/place-bet step

Verification:
- full user path works:
  - scrape or choose upcoming match
  - run prediction
  - add selection to betslip
  - open tickets page
  - place ticket successfully

### Task 3.4: Fix public/authenticated route strategy
Files:
- Modify: `frontend/src/routes/+layout.server.ts`
- Modify: `frontend/src/routes/+page.svelte`
- Possibly add/modify: onboarding/public landing route content

Decision to make:
- either `/` becomes a true public onboarding route,
- or `/` becomes authenticated and `/board` serves as the public discovery route.

Verification:
- anonymous user sees a coherent experience, not an empty operations dashboard

## Phase 4 — finish the PWA and analytics trust layer
Priority: medium-high
Outcome: installable, resilient, measurable product.

### Task 4.1: PWA UX completion
Files:
- Modify: `frontend/src/service-worker.ts`
- Modify: `frontend/src/app.html`
- Add: install/update/offline UI components in `frontend/src/lib/components/`
- Wire into: `frontend/src/routes/+layout.svelte`

Deliverables:
- install prompt UX
- update available notification
- offline/limited-connectivity banners
- safe degraded behavior for key routes

### Task 4.2: Analytics/model attribution repair
Files:
- Modify: `backend/app/api/v1/analytics.py`
- Modify: `backend/app/services/ensemble.py`
- Modify: `backend/app/models/prediction.py`
- Possibly modify: `backend/app/models/ticket.py`

Deliverables:
- PnL by model and strategy uses real links
- ensemble logic works on actual model identity

### Task 4.3: Add automated tests around the product spine
Files:
- Add frontend tests under a new test convention in `frontend/`
- Add backend tests under `backend/tests/`

Minimum coverage to add:
- scrape ingestion
- prediction run failure/success semantics
- ticket creation validation
- shared betslip store behavior
- auth route gating

## Recommended execution order
1. Phase 1.1
2. Phase 1.2
3. Phase 2.1
4. Phase 2.2
5. Phase 2.3
6. Phase 3.1
7. Phase 3.2
8. Phase 3.3
9. Phase 3.4
10. Phase 4.1
11. Phase 4.2
12. Phase 4.3

## Short version
If we do only the most important things first, do these in order:
1. real scrape ingestion
2. honest prediction statuses, no fake/demo fallbacks
3. selection-level prediction model
4. ticket validation + prediction linkage
5. shared betslip store
6. nav/workflow rewrite around scrape -> predict -> tickets

## Notes from current inspection
- Frontend currently passes `pnpm -s check` and `pnpm -s build`.
- Backend compiles and targeted Ruff checks pass.
- No frontend or backend tests were found in the repo during this audit.
- Dev servers are currently runnable, but functional completeness is still behind the mission.
