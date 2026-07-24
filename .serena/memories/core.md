# Bet workspace — canonical project memory

## Source of truth

- Repository: `/home/gion/Projects/bet`.
- Every new session starts with `git status --short --branch`, `git submodule status`, `AGENTS.md`, then `docs/status/current-platform-status.md`.
- Phase/task detail: `docs/status/mvp-readiness-program.md`.
- Integration history: `docs/status/release-candidate-reconciliation.md`.
- Detailed current checkpoint: `mem:mvp_readiness`.
- Treat checkout files, Git state, and fresh CI/runtime verification as authoritative over memory snapshots.
- Current platform is `frontend/` SvelteKit/Svelte 5 plus `backend/` FastAPI/PostgreSQL. Do not modify archived `betfront/`/`frontbet/` or tracked nested `OddsHarvester/`, `penaltyblog/`, `soccerdata/` unless explicitly scoped.

## Runtime contract

- Frontend dev: `http://127.0.0.1:5175`.
- Backend dev: `http://127.0.0.1:8001`; health `/health`; readiness `/ready` and `/api/v1/ready`.
- Bet local infrastructure: PostgreSQL `127.0.0.1:5433`, Redis `127.0.0.1:6380`; avoid fallback to another project's Redis on 6379.
- Current database schema: Alembic `025`.

## Current release posture — 2026-07-24 13:03 EEST

- Local development/release-candidate validation: GO.
- Public MVP launch: HOLD until protected release plus staging/production operational gates are evidenced.
- PR #7 merged the verified platform candidate into `main` as signed commit `881a436`; post-merge Backend, Frontend, and Security runs passed.
- GitHub environment `registry-release` and `v*` tag-only policy exist. Active `Protect release tags` ruleset prevents update/deletion and requires verified commits. A second independent reviewer is not configured because only collaborator `cahangeorge` exists.
- Evidence-only release run `30084295728` found `ruff: command not found`; no build/package/publish occurred.
- Fix branch `agent/release-ruff-gate-2026-07-24`, commit `1131157`, declares Ruff in `backend[dev]`. Local editable install, Ruff, and **532/532** backend tests passed.
- PR #8 is open/mergeable; Backend, Frontend, and Security were green and Hybrid run `30084630886` was in progress at checkpoint time.
- No RC tag and no GHCR release artifact exist. Exact tag/destination approval is still required before publishing `v0.1.0-rc.20260724.1` to GHCR.
- Stable evidence: frontend check 0 diagnostics, unit 121/121, Chromium hybrid 56/56, PWA 3/3, Firefox 1/1, WebKit 1/1 official container; root release/security contracts 21/21; Alembic 025/no drift; nested projects unchanged.
- Latest compressed whole-workspace Repomix pack: `7fb2a326972893e0`, 1,154 files / 2,470,226 tokens / 138,612 lines.

## Exact next step

Inspect PR #8 and Hybrid run `30084630886`; merge only when every check is green. Rerun evidence-only `Release Build and Evidence` on the new `main`. After it passes, obtain explicit approval naming exact tag `v0.1.0-rc.20260724.1` and GHCR destination `cahangeorge/betting-platform`; only then publish and verify digests, Cosign signatures, GitHub attestations, and overwrite refusal. Protected staging/restore/observability/soak/canary/rollback remain required before public MVP GO.