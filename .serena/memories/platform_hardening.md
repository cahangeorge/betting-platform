# Bet platform hardening checkpoint — 2026-07-24

## Backend/database/task runtime

- Alembic `024` adds durable user-scoped create idempotency; `025` adds `User.session_version`, token `sv`, serialized refresh/logout, and HTTP/WebSocket revocation.
- Authentication has bounded hashed source/identity rate-limit buckets and structured redacted audit events.
- WebSockets enforce global/per-user capacity, bounded accept/send/close, idle/message limits, pending-reservation cleanup, session-version revalidation and logout closure.
- Taskiq tasks use explicit canonical names; runtime heartbeats, recovery probes, queued round trip, invalid-cron quarantine and `XPENDING=0` behavior are verified.

## Frontend/PWA/device UX

- Session epoch/BroadcastChannel logout is terminal across tabs and clears user-scoped betslip drafts.
- Prepare preserves truthful error/partial/empty/retry-only-failed states and stable idempotency keys.
- Root error boundary, Romanian workflow content and match-specific odds accessible names are present.
- Ticket review labels/callout are Romanian; the unused fake zero-result backtest API and types were removed; stale Value Bets 404 copy is truthful.
- PWA manifest supports any orientation; production HTTPS install/public-only cache/offline-recovery/update-with-draft suite passes 3/3.
- Landscape action/bottom-nav geometry, simulated nonzero bottom safe area, coarse-pointer 44px workspace targets, and forced-colors keyboard focus pass in Chromium. The forced-colors system-color outline overrides utility outline removal.
- Real Android/iOS installed-app lifecycle, Windows High Contrast, desktop 200% zoom and screen-reader acceptance remain pre-public operator/hardware QA.

## Release/security hardening

- Combined Python 3.12 production lock contains 204 exact packages across backend/OddsHarvester/penaltyblog/soccerdata; regeneration and strict dry-run pass.
- Frontend image pins pnpm 10.34.5, uses one frozen install, prunes in builder and copies production node_modules to the non-root runner.
- Backend image installs Chromium at shared `/ms-playwright` owned by the non-root app user.
- Direct local production-image proof is now green: frontend image `localhost/bet-frontend:mvp-validation-20260724` runs as UID 1001 and serves HTTP 200; backend image `localhost/bet-backend:mvp-validation-20260724` runs as UID 1001, imports FastAPI and launches bundled Chromium; nginx build/config is green. Rootless Podman could connect but not resolve DNS inside builds, so explicit host-resolved mappings were used without changing the Dockerfiles. These local images came from the dirty checkout and are not registry/release identities.
- Release tags require Alembic/backend/frontend/full Chromium source verification and a real Redis-backed Taskiq worker, scheduler and round-trip smoke before image build/scan.
- CI built-image smoke asserts non-root UID, imports FastAPI, launches bundled Chromium, starts frontend and probes HTTP before release evidence is packaged.
- Exact tested/scanned images are archived with a same-directory checksum and 30-day retention. Protected `v*` publication refuses existing SHA/version refs fail-closed, pushes SHA candidates, captures authoritative digests, performs keyless Cosign sign/verify plus GitHub provenance attest/verify, then promotes version tags and reasserts digest equality. `workflow_dispatch` is evidence-only.
- Actions are commit-pinned; Trivy uses safe action v0.35.0 and binary v0.69.3 with unfixed High/Critical blocking.
- Secret scanner includes Git-visible untracked files locally, fails closed on read errors, scopes fixture markers to its approved test, and uses exact/anchored development placeholders.
- Production Compose requires authenticated Redis DB 0/1 URLs and `requirepass`, private Postgres/Redis, non-root app containers, bounded logs, CPU/memory/PID ceilings, stop grace and tmpfs. Cross-host DB/Redis TLS is target-platform responsibility.
- Rollback restores a known-good immutable application manifest but deliberately does not reverse migrations; MVP migrations must be expand-only/backward compatible and previous images must be exercised against the migrated staging schema.
- `docs/status/release-candidate-reconciliation.md` defines an owner-safe four-commit integration sequence and prohibits bulk staging/reset/clean operations.

## Verification baseline

Backend 530; frontend 121 unit cases; Chromium 56/56 current complete suite plus final adjusted specs 2/2; PWA 3/3; Firefox 1/1; WebKit container 1/1; root contracts 20/20; local frontend/backend/nginx production image gates green; final application, release-hardening and signed-registry reviews C0/H0/M0 APPROVE. Preserve this as a regression baseline, not a substitute for fresh verification.