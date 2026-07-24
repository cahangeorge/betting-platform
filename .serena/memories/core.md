# Bet workspace — canonical project memory

## Source of truth

- Repository: `/home/gion/Projects/bet`.
- Read `AGENTS.md`, then `docs/status/current-platform-status.md`, `docs/status/mvp-readiness-program.md`, and `docs/status/release-candidate-reconciliation.md` at every new release-readiness session.
- Treat checkout files, Git state, and fresh verification as authoritative over memories.
- Current platform is `frontend/` (SvelteKit/Svelte 5) plus `backend/` (FastAPI/PostgreSQL). `betfront/` and `frontbet/` are legacy; `OddsHarvester/`, `penaltyblog/`, and `soccerdata/` are nested projects and must not be mutated implicitly.

## Runtime contract

- Frontend dev: `http://127.0.0.1:5175`.
- Backend dev: `http://127.0.0.1:8001`; health `/health`; readiness `/ready` and `/api/v1/ready`.
- Local Bet infrastructure uses PostgreSQL `127.0.0.1:5433` and Redis `127.0.0.1:6380`; do not let API/worker/scheduler fall back to another project's Redis on `6379`.
- Current database schema head: Alembic `025`.
- Durable task runtime uses Taskiq/Redis and explicit canonical task names.

## Current release posture — 2026-07-24

- Local development validation: GO.
- Public Internet MVP: HOLD until the external deployment gates in the canonical status documents are closed.
- Current dirty state at the latest refresh: 105 tracked-change status entries and 59 untracked status entries representing 72 untracked files. Preserve it; do not reset, clean, bulk checkout, stage, commit, push, or mutate submodules without explicit owner scope.
- Fresh evidence: backend Ruff + 530 pytest; frontend Svelte check 0 diagnostics, 32 unit files/121 cases, E2E typecheck/build; final current-files Chromium complete 56/56 with one worker and retries=0; final adjusted specs 2/2; PWA 3/3; Firefox 1/1; WebKit 1/1 in the official Playwright container; root release/scanner contracts 20/20; final application, release-hardening, and signed-registry reviews Critical 0 / High 0 / Medium 0 — APPROVE.
- Dev stack is live on 8001/5175 with DB/schema/task_queue/task_runtime ready. Taskiq worker/scheduler smoke, provider canary, and a non-destructive Alembic-025 PostgreSQL restore drill passed.
- Local production images now have direct runtime proof. Frontend `localhost/bet-frontend:mvp-validation-20260724` built and returned HTTP 200 as UID 1001. Backend `localhost/bet-backend:mvp-validation-20260724` built the 204-package strict lock, ran as UID 1001, imported FastAPI, and launched bundled Chromium. Nginx build/config proof is green. Explicit host mappings worked around rootless Podman container DNS without changing Dockerfiles. These dirty-checkout local images are not release identities.
- Codebase Memory `bet-core` moderate index: 5,237 nodes / 19,762 edges, actual=expected, status indexed.
- Repomix latest snapshots: compressed whole workspace `59a58de9391eb430` (1,153 files / 2,467,034 tokens); active platform/release `233d99f089e79988` (556 files / 788,286 tokens).

## Exact next step

Follow `docs/status/release-candidate-reconciliation.md` under explicit owner approval to produce a clean reviewed integration revision. Then configure protected GitHub/GHCR controls, run one disposable signed tag proving exact scanned-image digest continuity, deploy those digest-pinned images to protected staging, and collect two-user lifecycle, off-host restore, observability, 48–72 hour soak, canary and rollback evidence before public launch.