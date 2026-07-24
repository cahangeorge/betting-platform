# Bet MVP readiness checkpoint — 2026-07-24 13:03 EEST

Canonical truth lives in `docs/status/current-platform-status.md`. The phase/task register is `docs/status/mvp-readiness-program.md`; commit history and release reconciliation are in `docs/status/release-candidate-reconciliation.md`.

## Read first next session

1. `git status --short --branch`
2. `git submodule status`
3. `docs/status/current-platform-status.md`
4. PR #8 and Hybrid E2E run `30084630886`

Treat fresh checkout and CI state as authoritative over this snapshot.

## Current checkout and GitHub state

- Local branch: `agent/release-ruff-gate-2026-07-24`.
- Code HEAD before the documentation refresh: `1131157` (`fix(ci): install Ruff in backend dev extras`), synchronized with origin.
- Tracked nested projects remain clean/unchanged: OddsHarvester `6046613`, penaltyblog `dd81473`, soccerdata `6d0ccab`.
- PR #7 merged the complete MVP candidate into `main` at signed merge commit `881a436971d28ef1736bf8c74894a0f9124ade83`.
- Post-merge exact-SHA runs passed: Backend `30084042800`, Frontend `30084042748`, Security `30084042782`.
- PR #8 is open and mergeable against `main` from commit `1131157`. Backend, Frontend, and Security are green; Hybrid E2E run `30084630886` was IN_PROGRESS when this checkpoint was saved.

## Release controls and evidence

- GitHub environment `registry-release` exists with a custom tag-only deployment policy matching `v*`.
- Active tag ruleset `Protect release tags` (`19677671`) prevents update/deletion of matching release tags and requires verified commit signatures.
- Only collaborator `cahangeorge` exists, so no genuinely independent reviewer gate is configured yet.
- No `v0.1.0-rc.20260724.*` tag exists and no GHCR release image has been published.
- Evidence-only release workflow run `30084295728` on `881a436` passed checkout, toolchain, production-lock regeneration, Chromium install and Alembic, then failed at backend static/test gate with exit 127: `ruff: command not found`. Build/package/publish were skipped.
- Root cause: release workflow installs `backend[dev]`, but Ruff was not declared in the dev extra.
- Fix `1131157` adds `ruff>=0.15.17,<0.16` to `backend/pyproject.toml`. Fresh local proof: editable `.[dev]` install succeeded, Ruff passed, and pytest passed **532/532**; `git diff --check` passed before the documentation refresh.
- The external-egress safety gate rejected the tag-push command before execution. Exact approval must name tag `v0.1.0-rc.20260724.1` and GitHub Container Registry destination for `cahangeorge/betting-platform` before trying again.

## Stable local/branch MVP evidence

- Complete branch candidate before merge: all five workflows green on `31eb4bb` / code commit `d20c583`; Hybrid E2E **56/56**.
- Backend exact CI-like gate: Ruff clean, **532/532**, Alembic `025 (head)` and no drift.
- Frontend: Svelte check 0 diagnostics, unit **121/121**, E2E typecheck and production build pass.
- Browser/PWA: Chromium hybrid **56/56**, PWA **3/3**, Firefox **1/1**, WebKit **1/1** in official Playwright container.
- Runtime: backend `127.0.0.1:8001`, frontend `127.0.0.1:5175`, PostgreSQL `5433`, Redis `6380`; readiness included database/schema/task queue/task runtime.
- Release/security contracts **21/21** plus secret scan, actionlint, YAML, shell and diff gates passed.
- Whole-workspace Repomix compressed refresh: output `7fb2a326972893e0`, 1,154 files / 2,470,226 tokens / 138,612 lines, excluding large HAR/build/cache/dependency artifacts.

## Phase status

- Phase 0 durable inventory/checkpoint: complete.
- Phase 1 reproducible development runtime: complete locally.
- Phase 2 security/release foundation: main integrated; environment/tag controls exist; PR #8 must close the release-only Ruff install gap.
- Phase 3 product/responsive UX/PWA: local MVP scope green; paper execution excluded by accepted ADR.
- Phase 4 adversarial QA/recovery: local and branch E2E green; protected staging/off-host/deployed evidence pending.
- Phase 5 release candidate: main integration complete; evidence-only release rerun, exact approved signed tag, GHCR evidence and external staging/operations remain.
- Verdict: local development/release-candidate validation GO; public MVP launch HOLD.

## Exact next steps

1. Inspect PR #8 and wait for Hybrid E2E run `30084630886`.
2. Merge PR #8 only after every check is green.
3. Run `Release Build and Evidence` via `workflow_dispatch` on the new `main`; require `verify-source` and `build-scan-and-package` success while publish stays skipped.
4. Obtain explicit approval for tag `v0.1.0-rc.20260724.1` publishing to GHCR for `cahangeorge/betting-platform`.
5. Push the tag only after approval; verify three registry digests, Cosign signatures, GitHub attestations and overwrite protection.
6. Continue protected staging/two-user flow, production secrets/TLS/DNS/firewall, off-host restore with RPO/RTO, observability/on-call, 48–72h soak, canary and deployed rollback. Keep public MVP HOLD until evidenced.