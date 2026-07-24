# Bet MVP readiness checkpoint — 2026-07-24

Canonical detail lives in `docs/status/current-platform-status.md` and `docs/status/mvp-readiness-program.md`. The completed integration sequence and remaining external release steps are in `docs/status/release-candidate-reconciliation.md`. Clean candidate: `40352aed38f98600a621954c67c82b600faab223`.

## Phase status

- Phase 0 — durable inventory/checkpoint: complete.
- Phase 1 — reproducible development runtime: complete locally; dev stack live and Alembic head `025`.
- Phase 2 — security/release foundation: local gates green; external credential/infrastructure/revision gates pending.
- Phase 3 — product, responsive UX and PWA: local MVP scope green; paper execution excluded by ADR.
- Phase 4 — adversarial QA/recovery: local gates green; protected staging/off-host/deployed evidence pending.
- Phase 5 — clean local release candidate complete; public launch HOLD on protected remote release and external operations gates.

## Fresh local evidence

- Backend: Ruff clean; 530 pytest; Alembic `025`, no drift.
- Frontend: pinned pnpm 10.34.5; Svelte check 0 diagnostics; 32 unit files/121 cases; E2E typecheck/build; complete current-files Chromium 56/56 in 10.3m with one worker and zero retries; final adjusted forced-colors/coarse-pointer specs 2/2; PWA production 3/3; Firefox 1/1; WebKit 1/1 in the official Playwright v1.60.0-noble container.
- Device/accessibility: landscape 844x390, simulated bottom safe area, coarse-pointer 44 CSS-px workspace targets, and forced-colors keyboard focus are automated. Actual iOS/Android installed PWA, Windows High Contrast, desktop 200% zoom and screen reader remain manual/hardware gates.
- Release/security: 20 production/scanner contracts; tracked-plus-untracked fail-closed secret scan; Ruff/actionlint/YAML/shell/diff checks; production Compose render. Release source verification starts a real Redis Taskiq worker/scheduler and runs a round-trip smoke.
- Production images: frontend pinned production Dockerfile built locally and served `/about` HTTP 200 as UID 1001. Backend production Dockerfile built the exact 204-package lock and bundled Playwright Chromium; UID 1001, FastAPI import and Chromium launch passed. Nginx build/config proof is green. Rootless Podman DNS required explicit host-resolved build mappings, not Dockerfile changes. Local digests are dirty-checkout evidence only.
- Signed supply chain: exact images that passed runtime/scans/SBOM are handed off; protected tag publication uses fail-closed overwrite guards, GHCR SHA tags, authoritative registry digests, keyless Cosign sign/verify, GitHub provenance attest/verify, then version-tag promotion. Actual protected tag execution remains external.
- Runtime/recovery: `/ready` reports database/schema/task_queue/task_runtime ready; worker/scheduler runtime, Taskiq round trip and provider canary pass; non-destructive PostgreSQL dump/restore at Alembic 025 has matching schema/version/key row counts.
- Independent final reviews: application, release-hardening, and signed-registry scopes all Critical 0 / High 0 / Medium 0 — APPROVE.

## Public launch HOLD gates

- Provider-side revocation/rotation proof for the previously tracked third-party credential.
- Push clean candidate `40352ae`, inspect GitHub checks, and obtain remote review evidence without rewriting the verified revision.
- Configure protected `registry-release` environment, tag rules and package access/visibility, then run one disposable signed GHCR tag.
- Real secret manager, production JWT/DB/TLS lifecycle, DNS, valid TLS and firewall/network policy.
- Protected staging two-user scrape → dataset → prediction → ticket → settlement flow and worker/scheduler failure recovery.
- Off-host encrypted backup retention and restore rehearsal with measured RPO/RTO.
- Production observability, alert routing, owner/on-call, 48–72 hour soak, canary and deployed rollback proof.
- Hardware/manual accessibility acceptance and legal/compliance approval if applicable.

Do not call the public MVP launched until every gate above has evidence in the canonical status documents.