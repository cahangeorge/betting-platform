# Bet MVP readiness checkpoint — 2026-07-24

Canonical detail lives in `docs/status/current-platform-status.md` and `docs/status/mvp-readiness-program.md`. The integration sequence is in `docs/status/release-candidate-reconciliation.md`.

## Current revision and delivery state

- Local candidate HEAD: `3543ebb` (`fix(release): close CI and first-deploy gates`).
- Working tree was clean immediately after this commit; the branch is one commit ahead of `origin/agent/demo-tickets-2026-07-17` at `41333eb`.
- Push of `3543ebb` was attempted but blocked by the execution policy because the destination is a public GitHub repository and this exact payload needs explicit user authorization to publish. Do not claim remote CI is current until that push succeeds.
- Codebase Memory `bet-core` was reindexed in moderate mode after `3543ebb`: 5,247 nodes / 19,958 edges, status indexed.

## Phase status

- Phase 0 — durable inventory/checkpoint: complete.
- Phase 1 — reproducible development runtime: complete locally; dev stack ready and Alembic head `025`.
- Phase 2 — security/release foundation: local gates green; remote CI and external release controls pending.
- Phase 3 — product, responsive UX and PWA: local MVP scope green; paper execution excluded by ADR.
- Phase 4 — adversarial QA/recovery: local gates green; protected staging/off-host/deployed evidence pending.
- Phase 5 — clean local release candidate complete; public launch HOLD on push/remote CI, protected release, staging and external operations gates.

## Fresh evidence for `3543ebb`

- Backend exact CI-like environment: FastAPI 0.139.2, Starlette 1.3.1, Flumine 3.1.0; Ruff clean; targeted live HTTP/WebSocket/trading 41/41; full suite 531/531; Alembic `025 (head)` and no drift. Flumine falls back to the installed package when no local checkout exists, while an explicitly invalid checkout still fails closed.
- FastAPI tests use the real ASGI `/api/v1/live/overview` route and the public ASGI matcher for `/api/v1/live/ws`; they no longer depend on private `serialize_response` or direct inspection of included-router internals.
- Frontend: `pnpm check` 0 diagnostics, unit 121/121, E2E typecheck and adapter-node build pass. The affected betslip accessibility suite passed 4/4 and the two originally failing hybrid specs passed 5/5 together, single worker, zero retries.
- Hybrid CI now checks out submodules recursively, installs backend plus editable OddsHarvester, verifies `import oddsharvester`, and binds `BET_ODDSHARVESTER_PYTHON` to the runner Python; this removes the missing-venv failure without creating a false-ready bridge.
- Release/security: 21 production/scanner contracts, tracked-plus-untracked secret scan, actionlint, YAML, shell syntax and `git diff --check` pass. Security CI runs the production contracts.
- Nginx production/dev images run non-root on internal 8080/8443. The release workflow now creates temporary TLS material, verifies non-root UID, HTTP 308 and HTTPS/TLS 502 against absent dummy upstreams before packaging. Equivalent local smoke passed `uid=101 http=308 https=502`, key mode 0640.
- First-deploy `scripts/release/bootstrap.sh` is committed and fail-closed; normal deploy remains upgrade-only. Restore runs migrations before restarting applications. Publish job checks out the repository before executing the registry overwrite guard.
- Independent backend, frontend and final release/UI reviewers reported PASS/APPROVE with no P1/P2 code issue remaining.

## Earlier complete evidence still applicable

- Complete Chromium hybrid 56/56, PWA production 3/3, Firefox 1/1, WebKit 1/1 in the official Playwright container.
- Runtime `/ready` database/schema/task_queue/task_runtime ready; Taskiq round trip/provider canary pass.
- Local production frontend/backend images run as UID 1001; backend imports FastAPI and launches bundled Chromium.
- Non-destructive PostgreSQL dump/restore drill passed at Alembic 025.
- Whole-workspace Repomix inventory `8f2867d9900ff53a` captured the unfiltered 1,167-file tree. Final compressed refresh after `8039d42`, excluding large HAR/build/cache artifacts, is output `7fb2a326972893e0`: 1,154 files / 2,470,226 tokens / 138,612 lines.

## Public launch HOLD gates

- Explicit authorization to publish `3543ebb`, then push and obtain all GitHub Actions checks green on the current revision.
- Provider-side revocation/rotation proof for the previously tracked third-party credential.
- Configure a protected `registry-release` environment and tag rules. The repository currently has only collaborator `cahangeorge`, so an independent required reviewer cannot be configured without adding another trusted reviewer.
- Execute one disposable signed GHCR tag after CI and protection controls are proven.
- Real secret manager, production JWT/DB/TLS lifecycle, DNS, valid TLS and firewall/network policy.
- Protected staging two-user scrape → dataset → prediction → ticket → settlement flow and worker/scheduler failure recovery.
- Off-host encrypted backup retention and restore rehearsal with measured RPO/RTO.
- Production observability, alert routing, owner/on-call, 48–72 hour soak, canary and deployed rollback proof.
- Hardware/manual accessibility acceptance and legal/compliance approval if applicable.

Do not call the public MVP launched until every gate above has evidence in the canonical status documents.