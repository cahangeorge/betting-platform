# Release Candidate Reconciliation Plan

Updated: 2026-07-24T13:03:01+03:00
Branch: `agent/release-ruff-gate-2026-07-24`
Status: **MAIN INTEGRATION COMPLETE; RELEASE-ONLY RUFF FIX OPEN IN PR #8**

This plan converted the intentionally dirty, locally verified MVP checkout into
a reviewable release-candidate revision without losing existing work. The owner
explicitly authorized continuation, including commit, push, and release
evidence. Production deployment still requires a configured target and
verifiable external credentials/infrastructure.

The former checkout had **105 tracked-change entries** and **59 untracked
entries** representing **72 untracked files**. It is now clean at
`40352aed38f98600a621954c67c82b600faab223`, five commits ahead of the remote
branch. The three tracked nested projects remain clean and unchanged:

- `OddsHarvester`: `6046613805667b8d7287f7a925f937b9f0dbfde5`
- `penaltyblog`: `dd81473a40f29ddcf62a85c006cd28e6d83acd80`
- `soccerdata`: `6d0ccabcdfca3b670e130f5639721335df82a7a3`

## Actual integration and release history

The recommended sequence below was executed, then hardened through CI:

1. `4b123b4` — backend MVP/runtime/tenancy slice.
2. `34a952a` — frontend workflow, responsive UX, and PWA slice.
3. `ddf0dfd` — production/release supply-chain slice.
4. `6c4394e` — durable documentation and handoff slice.
5. `40352ae` — isolated backend Ruff formatting.
6. `3543ebb` — first CI/first-deploy remediation.
7. `d20c583` — hybrid timing-race remediation.
8. `31eb4bb` — final green branch checkpoint.
9. PR #7 merged the complete candidate into `main` as signed merge commit
   `881a436`; post-merge Backend, Frontend, and Security runs passed.
10. `registry-release` and its tag-only `v*` deployment policy were created.
    Active ruleset `Protect release tags` now prevents release-tag mutation or
    deletion and requires verified commit signatures.
11. Evidence-only release run `30084295728` exposed one undeclared tool:
    `ruff: command not found` after successful checkout/toolchain/lock/Chromium/
    Alembic setup. No build/package/publish job ran.
12. Fix `1131157` declares Ruff in `backend[dev]`; local install, Ruff and all
    **532** backend tests passed. PR #8 is open and its Hybrid E2E gate was
    still running when this checkpoint was recorded.

No release tag or GHCR release artifact exists at this checkpoint.

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

Completed local evidence:

1. five explicit reviewed commits, including one isolated mechanical Ruff
   formatting commit;
2. backend **530/530**, frontend **121/121**, root **20/20**, Alembic `025`,
   Chromium **56/56**, PWA **3/3**, Firefox **1/1**, WebKit **1/1**;
3. `git status --short` empty and all three submodule pointers unchanged;
4. Serena memory integrity and Codebase Memory reindex green.

Remaining external sequence:

1. finish and merge PR #8 after every check passes;
2. rerun evidence-only `Release Build and Evidence` on the new `main`;
3. obtain explicit approval for tag `v0.1.0-rc.20260724.1` publishing to GHCR;
4. run and verify the protected tag workflow, then deploy only its verified
   registry digests to protected staging.

## External follow-on

The clean revision does not itself close provider credential rotation,
protected GHCR/environment configuration, secret manager/DNS/TLS/firewall,
two-user real staging lifecycle, off-host restore, observability/on-call,
48–72-hour soak, canary, deployed rollback, hardware accessibility, or legal
approval. Public MVP remains **HOLD** until those results are recorded in the
canonical status documents.
