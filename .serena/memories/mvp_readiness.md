# Bet MVP readiness checkpoint — 2026-07-24

Canonical detail lives in `docs/status/current-platform-status.md` and `docs/status/mvp-readiness-program.md`. The integration sequence is in `docs/status/release-candidate-reconciliation.md`.

## Current revision and delivery state

- Published branch HEAD: `d20c583` (`fix(ci): remove hybrid timing races`) on `origin/agent/demo-tickets-2026-07-17`.
- Local working tree is clean and synchronized with origin.
- All five branch workflows are green on the exact SHA `d20c583`: Backend run `30082364070`, Frontend `30082364092`, Security `30082364108`, Compose Smoke `30082364068`, Hybrid E2E `30082364057`.
- Codebase Memory `bet-core` was reindexed in moderate mode after `d20c583`: 5,248 nodes / 19,986 edges, status indexed.

## Phase status

- Phase 0 — durable inventory/checkpoint: complete.
- Phase 1 — reproducible development runtime: complete locally; dev stack ready and Alembic head `025`.
- Phase 2 — security/release foundation: local and branch CI gates green; protected release controls and real tag evidence pending.
- Phase 3 — product, responsive UX and PWA: local MVP scope green; paper execution excluded by ADR.
- Phase 4 — adversarial QA/recovery: local and branch E2E green; protected staging/off-host/deployed evidence pending.
- Phase 5 — published branch candidate and branch CI complete; public launch HOLD on protected release, staging and external operations gates.

## Fresh evidence for `d20c583`

- Exact CI-like backend: FastAPI 0.139.2, Starlette 1.3.1, Flumine 3.1.0; Ruff clean; full suite **532/532**; Alembic `025 (head)` and no drift.
- FastAPI 0.118+ runs default request-scoped yield-dependency cleanup after the response. Scheduled-job create/toggle now commits before returning, preventing an immediate follow-up request from racing the transaction. A regression test proves the pre-response commit.
- Hybrid live-value UI waits reactively for either an actionable or locked candidate instead of branching on an early `count()` before asynchronous data rendering.
- The two previously failing GitHub scenarios passed locally 2/2 twice, single worker, zero retries. The final GitHub Hybrid E2E run passed all 56 tests.
- Frontend check remains 0 diagnostics, unit 121/121, E2E typecheck and adapter-node build pass.
- Hybrid CI checks out submodules recursively, installs backend plus editable OddsHarvester, verifies `import oddsharvester`, and binds `BET_ODDSHARVESTER_PYTHON` to the runner Python.
- Release/security: 21 production/scanner contracts, tracked-plus-untracked secret scan, actionlint, YAML, shell syntax and diff checks pass.
- Nginx production/dev images run non-root on internal 8080/8443. Release CI proves UID, HTTP 308, and a temporary-certificate HTTPS handshake before packaging. Equivalent local smoke passed `uid=101 http=308 https=502`, key mode 0640.
- First-deploy bootstrap is committed and fail-closed; restore migrates before app restart; registry publish checks out guard scripts.
- Independent backend, frontend and final release/UI reviews reported PASS/APPROVE after their findings were closed.

## Earlier complete evidence still applicable

- Complete Chromium hybrid 56/56 locally, PWA production 3/3, Firefox 1/1, WebKit 1/1 in the official Playwright container.
- Runtime `/ready` reports database/schema/task_queue/task_runtime ready; Taskiq round trip/provider canary pass.
- Local production frontend/backend images run as UID 1001; backend imports FastAPI and launches bundled Chromium.
- Non-destructive PostgreSQL dump/restore drill passed at Alembic 025.
- Whole-workspace Repomix inventory `8f2867d9900ff53a` captured the unfiltered tree. Compressed refresh `7fb2a326972893e0` covers 1,154 files / 2,470,226 tokens / 138,612 lines excluding large HAR/build/cache artifacts.

## Public launch HOLD gates

- Configure a protected `registry-release` environment and protected `v*` tag rules. GitHub currently lists only collaborator `cahangeorge`; a genuinely independent required reviewer cannot be configured until another trusted reviewer is added.
- Execute one disposable signed GHCR tag only after release controls are approved.
- Provider-side revocation/rotation proof for the previously tracked third-party credential.
- Real secret manager, production JWT/DB/TLS lifecycle, DNS, valid TLS and firewall/network policy.
- Protected staging two-user scrape → dataset → prediction → ticket → settlement flow and worker/scheduler failure recovery.
- Off-host encrypted backup retention and restore rehearsal with measured RPO/RTO.
- Production observability, alert routing, owner/on-call, 48–72 hour soak, canary and deployed rollback proof.
- Hardware/manual accessibility acceptance and legal/compliance approval if applicable.

Do not call the public MVP launched until every gate above has evidence in the canonical status documents.