# Release Candidate Reconciliation Plan

Updated: 2026-07-24T05:39:32+03:00
Branch: `agent/demo-tickets-2026-07-17`
Status: **OWNER AUTHORIZED INTEGRATION; COMMIT/PUSH/RELEASE EVIDENCE IN PROGRESS**

This plan converts the intentionally dirty, locally verified MVP checkout into
a reviewable release-candidate revision without losing existing work. It does
not authorize staging, committing, pushing, tag creation, or production
deployment. Those actions require an explicit owner decision because the
checkout contains pre-existing work and release credentials/infrastructure are
external.

At this checkpoint `git status --short` reports **105 tracked-change entries**
and **59 untracked entries** representing **72 untracked files**. The three
tracked nested projects are clean and their current pointers must remain
unchanged:

- `OddsHarvester`: `6046613805667b8d7287f7a925f937b9f0dbfde5`
- `penaltyblog`: `dd81473a40f29ddcf62a85c006cd28e6d83acd80`
- `soccerdata`: `6d0ccabcdfca3b670e130f5639721335df82a7a3`

## Integration invariants

1. Never use `git reset`, `git clean`, bulk checkout, or an implicit
   `git add -A`.
2. Stage only reviewed path groups with `git add -- <explicit paths>`.
3. Do not include `.env`, secrets, runtime databases, Playwright artifacts,
   generated build output, or nested-project working trees.
4. Keep migrations `022` through `025` in chronological order and review them
   before the backend code that depends on them.
5. Paper/live execution stays excluded from the public MVP.
6. Every candidate commit must pass its focused gate; the final revision must
   pass the complete release gate.

## Recommended commit sequence

### RC-1 — backend schema, security, idempotency, and task runtime

Scope:

- `backend/alembic/versions/022_*.py` through `025_*.py`;
- backend models, schemas, configuration, authentication and API dependencies;
- scheduled-job, ticket, bridge and idempotency services;
- Taskiq broker, canonical task names, scheduler, heartbeat, smoke and recovery
  probes;
- corresponding backend tests.

Required gate:

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/alembic check
.venv/bin/alembic current
```

Expected evidence: Ruff clean, **530 tests**, `025 (head)`, no migration drift.

### RC-2 — frontend session, workflow, responsive UX, and PWA

Scope:

- authentication/session epoch and cookie behavior;
- API clients, betslip/live stores, Prepare/Analyze/Tickets workflow;
- global error recovery, navigation, accessibility, responsive layout;
- service worker, manifest, offline page and PWA banners;
- frontend unit, hybrid, accessibility and PWA tests.

Required gate:

```bash
cd frontend
pnpm check
pnpm test:unit
pnpm check:e2e
pnpm build
pnpm exec playwright test --project=chromium-hybrid --retries=0 --workers=1
pnpm test:e2e:pwa
```

Expected evidence: 0 Svelte diagnostics, **121 unit cases**, **56/56**
Chromium, and **3/3** PWA.

### RC-3 — production images, release workflow, security, and operations

Scope:

- production Dockerfiles and `.dockerignore` files;
- production Compose/nginx topology and environment template;
- exact Python dependency lock;
- backup/restore and release scripts;
- secret scanner and production-contract tests;
- commit-pinned GitHub workflows, Taskiq source gate, image runtime smoke,
  scanning/SBOM, signed GHCR publication, attestations and rollback.

Required gate:

```bash
backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests
backend/.venv/bin/ruff check tests scripts
backend/.venv/bin/python scripts/scan_tracked_secrets.py --include-untracked
actionlint .github/workflows/*.yml
find scripts -type f -name '*.sh' -print0 | xargs -0 bash -n
git diff --check
```

Expected evidence: **20/20** root contracts plus clean scanner, actionlint,
YAML, shell and diff checks.

The current Dockerfiles also have direct local build/runtime proof:

- frontend image
  `localhost/bet-frontend:mvp-validation-20260724`,
  image ID `ad05990f46ef...`, local digest `sha256:6aaad448e85c...`;
  production `/about` returned 200 as UID 1001;
- backend image
  `localhost/bet-backend:mvp-validation-20260724`,
  image ID `91ba6a3e1c77...`, local digest `sha256:827552c95c94...`;
  UID 1001, FastAPI import, and bundled Chromium launch passed;
- nginx image `localhost/bet-nginx:mvp-validation` previously passed
  `nginx -t` with the production topology.

These are dirty-checkout local artifacts, not registry identities and not
release evidence. The protected workflow must rebuild, scan, publish, sign and
attest the clean revision.

### RC-4 — durable documentation and decision record

Scope:

- `AGENTS.md` and Codex continuity/setup files;
- ADR index and the accepted paper-execution exclusion ADR;
- production runbook;
- current platform checkpoint, MVP program, and this reconciliation plan;
- Serena memories.

Required gate:

```bash
serena memories check
git diff --check
git status --short --branch
git submodule status
```

## Final clean-revision gate

After the four reviewed commits:

1. run the complete backend/frontend/root/browser/PWA gate from the candidate
   revision;
2. confirm `git status --short` is empty;
3. confirm the three submodule pointers equal the hashes above;
4. push a review branch, obtain review, and merge without rewriting the
   evidence-producing revision;
5. configure the protected `registry-release` environment and execute one
   disposable `v*` tag;
6. deploy only the verified registry digests to protected staging.

## External follow-on

The clean revision does not itself close provider credential rotation,
protected GHCR/environment configuration, secret manager/DNS/TLS/firewall,
two-user real staging lifecycle, off-host restore, observability/on-call,
48–72-hour soak, canary, deployed rollback, hardware accessibility, or legal
approval. Public MVP remains **HOLD** until those results are recorded in the
canonical status documents.
