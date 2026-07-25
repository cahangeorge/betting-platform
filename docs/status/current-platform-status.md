# Current Platform Status

Updated: 2026-07-25T11:02:34+03:00
Repository/branch: `/home/gion/Projects/bet` / `agent/release-uv-runtime-remediation-2026-07-25`
Git state at this handoff refresh:

```text
PR #12 is merged into current `origin/main` as
`3550b9cf58d75bb4a1f2f02fee56493d03bd76af`. Protected tag
`v0.1.0-rc.20260725.1` points to that exact SHA. Tag run `30149673025` passed
source verification plus all image builds/runtime smoke, then failed closed on
two newly fixable High findings carried only by the build-time `uv`/`uvx`
binaries in the backend runtime image. `publish-signed-images` was skipped, so
no GHCR image or partial publication occurred. Remediation commit `eac1ad0`
removes `uv` after dependency/browser installation and adds fail-closed runtime
contracts. The failed tag remains immutable and quarantined; a new reviewed
revision and new RC tag are required. The three tracked submodules are clean
and unchanged.
```

This is the first status document to read in a new coding session. Re-run
`git status --short --branch` before relying on this snapshot.

## Objective

Execute the full Bet MVP-readiness program: preserve the existing dirty work,
keep project/task/phase state durable, start the integrated development stack,
run backend/frontend/browser/PWA verification, remediate every mandatory
security, correctness, accessibility, operations, and recovery blocker, and
finish with an evidence-backed MVP GO/HOLD decision.

The detailed task registry, phase dependencies, gates, and completion contract
are maintained in
[`docs/status/mvp-readiness-program.md`](mvp-readiness-program.md). That file is
the active execution register; this file remains the canonical session
checkpoint and must summarize its latest verified state.

The completed owner-safe path from the former dirty checkout to the clean
candidate is recorded
in
[`docs/status/release-candidate-reconciliation.md`](release-candidate-reconciliation.md).

Current program state:

- Phase 0 durable checkpoint and baseline: **complete**.
- Phase 1 reproducible development runtime: **complete locally**.
- Phase 2 security/release foundation: **application/source gates green;
  container residual-risk policy accepted; strict fail-closed gate blocked the
  first protected RC on newly fixable build-tool findings; local remediation is
  green and clean CI evidence is pending**.
- Phase 3 product/UX: **local implemented scope and browser/PWA gates green**.
- Phase 4 adversarial QA/staging: **local and branch E2E gates green; protected staging and external operations evidence pending**.
- Phase 5 release candidate: **PR #8 through #12 merged; exact main
  evidence-only run was green; RC `v0.1.0-rc.20260725.1` is quarantined after a
  fail-closed Trivy block before publication; remediation review/CI, a new RC,
  signed GHCR proof, and external staging gates remain**.
- Paper execution: **excluded from public MVP** by accepted ADR
  [`2026-07-23-exclude-paper-execution-from-mvp.md`](../adr/2026-07-23-exclude-paper-execution-from-mvp.md).
- Verdict: **local application/runtime GO; release-candidate and public MVP
  launch HOLD until the remediation is merged and clean CI proves zero fixable
  High/Critical findings, followed by a new protected signed release and the
  external operational evidence**.

## 2026-07-25 failed RC and build-tool remediation checkpoint

This section supersedes the exact-tag continuation in the merged-main evidence
checkpoint below.

- Authorized protected tag `v0.1.0-rc.20260725.1` was created and pushed on
  exact main SHA `3550b9cf58d75bb4a1f2f02fee56493d03bd76af`.
- Protected release run
  [30149673025](https://github.com/cahangeorge/betting-platform/actions/runs/30149673025)
  recorded:
  - `verify-source`: **success**;
  - all three image builds and runtime smoke: **success**;
  - backend/frontend/nginx Trivy scans: completed;
  - `build-scan-and-package`: **failure** at the fixable-finding gate;
  - `publish-signed-images`: **skipped**.
- The retained vulnerability artifact reports backend **40** High/Critical
  entries: **38 unresolved** (**32 High / 6 Critical**) plus exactly **2
  fixable High** entries. Frontend and nginx remain at **0**.
- Both blocking entries are `GHSA-4w2j-m93h-cj5j` for embedded
  `quinn-proto 0.11.14 -> 0.11.15`, targeted only at
  `/usr/local/bin/uv` and `/usr/local/bin/uvx`. Source, Serena, and the current
  Codebase Memory graph confirm that the application does not invoke these
  tools at runtime.
- No release image was preserved or published because the gate failed before
  the scanned-image handoff and publish job. The failed tag is retained as an
  immutable quarantined release attempt; it must not be rerun, moved, deleted,
  or overwritten.
- Remediation commit `eac1ad0` uninstalls the build-only `uv` package after the
  exact production dependency graph and Playwright Chromium are installed. The
  release runtime smoke now fails if `uv`, `uvx`, or the Python `uv` package is
  present.
- Fresh local proof:
  - root release/security contracts **29/29**;
  - actionlint `1.7.12`, workflow YAML, release shell syntax, tracked-secret
    scan, and `git diff --check`: pass;
  - backend Ruff clean and pytest **545/545**;
  - an offline-derived image from the exact prior validated backend image
    successfully uninstalled `uv`; `uv`, `uvx`, and `pip show uv` were absent;
    `dpkg --audit`, FastAPI, all three Python bridges, writable non-root HOME,
    and real Chromium launch passed;
  - a full local rebuild remains unable to resolve PyPI from the Podman build
    namespace, so clean CI remains the authoritative rebuild/Trivy proof.

Exact continuation order:

1. Push the remediation branch and require all PR checks plus the protected
   release evidence workflow on its clean revision.
2. Merge only after the complete backend report returns to **0 fixable**
   High/Critical findings and all three SBOMs are retained.
3. After merged-main evidence is green, issue a new version tag; never reuse
   `v0.1.0-rc.20260725.1`.
4. Verify exact digest continuity, Cosign signatures, GitHub attestations,
   protected version promotion, and overwrite refusal for all three GHCR
   destinations.
5. Public MVP launch remains **HOLD** until credential rotation, protected
   two-user staging, secret-manager/TLS/DNS/firewall, off-host restore,
   monitoring/on-call, 48–72 hour soak, canary, rollback, and applicable
   compliance evidence are complete.

## 2026-07-25 merged-main backend evidence checkpoint

This section supersedes the PR #12 and clean-image-evidence continuation items
below.

- PR [#12](https://github.com/cahangeorge/betting-platform/pull/12) merged at
  `2026-07-25T00:14:24Z` as exact main commit
  `3550b9cf58d75bb4a1f2f02fee56493d03bd76af`.
- Evidence-only run
  [30135830444](https://github.com/cahangeorge/betting-platform/actions/runs/30135830444)
  completed successfully on that exact SHA:
  - `verify-source` passed in **8m49s**, including Alembic, backend, Taskiq,
    frontend, and the full Chromium hybrid gate;
  - `build-scan-and-package` passed in **5m19s**, including all three image
    builds, the expanded non-root backend runtime smoke, Trivy, three CycloneDX
    SBOMs, secret scan, and evidence packaging;
  - `publish-signed-images` was **skipped** and the protected image-preservation
    steps were skipped because the event was `workflow_dispatch`, not a tag.
- The downloaded exact reports contain:
  - backend **38** unresolved findings: **32 High / 6 Critical**, **0 fixable**;
  - frontend **0** and nginx **0**;
  - the backend package set exactly matches the prior local applicability
    projection after removal of **77/115** former entries.
- The hardened fail-closed report gate accepted the exact three reports:
  `PASS: no fixable High/Critical findings`. Unfixed backend findings remain
  explicit risk evidence rather than being filtered out.
- Evidence artifacts:
  - `release-evidence-3550b9cf58d75bb4a1f2f02fee56493d03bd76af`;
  - `vulnerability-evidence-3550b9cf58d75bb4a1f2f02fee56493d03bd76af`;
  - `backend.cdx.json`, `frontend.cdx.json`, and `nginx.cdx.json` are present.
- GitHub emitted non-blocking Node.js 20 action-runtime deprecation warnings;
  the runner forced those pinned actions to Node.js 24 and both jobs passed.
  This is a future workflow-maintenance item, not an MVP release blocker.
- A fresh remote tag query still returned no `v*` release tag. No GHCR
  publication or deployment was performed.

Exact continuation order:

1. Obtain explicit approval naming the exact RC tag and GHCR destinations
   before any tag is created. Proposed next candidate:
   `v0.1.0-rc.20260725.1` targeting
   `ghcr.io/cahangeorge/betting-platform-{api,frontend,nginx}`.
2. After that separate approval, create the tag on exact main `3550b9c`, watch
   the protected workflow, and verify digest continuity, Cosign signatures,
   GitHub attestations, and overwrite refusal. This still does not authorize a
   public deployment.
3. Public MVP launch remains **HOLD** until credential rotation, protected
   two-user staging, secret-manager/TLS/DNS/firewall, off-host restore,
   monitoring/on-call, 48–72 hour soak, canary, rollback, and applicable
   compliance evidence are complete.

## 2026-07-25 backend residual-risk remediation checkpoint

This section supersedes the backend applicability-review continuation item from
the 2026-07-24 checkpoint below.

- Serena (`core`, `mvp_readiness`, `platform_hardening`), the current
  Codebase Memory graph, a fresh focused Repomix pack, Git/source, the canonical
  task register, and the downloaded main evidence artifact were reconciled.
  Fresh source and verification remain authoritative.
- A final moderate Codebase Memory refresh completed at **5,270 nodes / 20,133
  edges**, status `indexed`. The fresh focused Repomix pack is
  `6cc041fd97be3dc8` (**524 files**), with nested/legacy projects and generated
  dependency/build trees excluded.
- Fresh read-only remote verification still resolves `refs/heads/main` to
  `e2ea6355a0dad284cdb0dccdcaf8430cebbc1a6c` and returns no `v*` release tag.
- The backend report from main evidence run `30126304645` contains **115**
  unresolved OS findings (**96 High / 19 Critical**) and **0 fixable**
  findings. Package/runtime applicability review found that **77** report
  entries came from build-only or unnecessary headful-runtime packages:
  `linux-libc-dev` 40, non-base Perl packages 24,
  `libcurl3t64-gnutls` 7, and `xvfb`/`xserver-common` 6.
- `backend/Dockerfile.production` now removes `gcc`, `g++`, `git`,
  `libpq-dev`, and `xvfb` plus their auto-installed dependencies after the
  locked Python graph and Playwright Chromium are installed. It also gives the
  non-root UID 1001 a writable `/home/appuser`, required for clean direct
  bridge imports and runtime caches.
- The release image smoke now fails closed on `dpkg --audit`, direct
  `asyncpg`/OddsHarvester/penaltyblog/soccerdata imports, exact HOME identity
  and a real write/delete probe in that home, in addition to FastAPI, non-root
  UID, and Chromium launch. This preserves the local pruning proof in the next
  clean CI evidence run.
- Local image `localhost/bet-backend:mvp-pruned-20260725`
  (`66ccac01858d55e46023b227a06bfdbf8b15c3097bece0446b002a12054ae8d5`)
  built successfully. Runtime proof passed as UID 1001 with FastAPI,
  `asyncpg`, OddsHarvester, penaltyblog, soccerdata, writable HOME, and a real
  headless Chromium launch.
- Comparing the built image package inventory with the exact prior report shows
  **77/115 prior findings removed**. The **38** prior entries whose packages
  remain are **32 High / 6 Critical**, all without a reported fixed version;
  they are retained for explicit evidence review rather than hidden.
- A fresh local Trivy scan could not start because the host DNS resolver timed
  out while fetching `mirror.gcr.io/aquasec/trivy-db:2`; therefore the next
  clean CI image report remains the authoritative post-patch count. The
  existing fail-closed gate accepts the prior report only as unresolved risk
  and still reports `PASS: no fixable High/Critical findings`.
- Fresh verification after the patch:
  - root release/security contracts **29/29**, actionlint `1.7.12`, tracked and
    untracked plaintext-secret scan, workflow YAML, shell syntax, and
    `git diff --check`;
  - backend Ruff clean and pytest **545/545**;
  - PostgreSQL Alembic `025 (head)` and `alembic check` reports no new upgrade
    operations;
  - frontend `pnpm check` 0 diagnostics, unit **121/121**, and production build
    on Vite `8.1.5`;
  - local rebuilt-image UID/package/runtime smoke passed.

Exact continuation order:

1. Obtain separate authorization to merge green, mergeable PR #12.
2. After the authorized merge, run an evidence-only `Release Build and
   Evidence` workflow on exact `main`. Confirm the new backend Trivy report and
   all three SBOMs; publication must remain skipped.
3. Only after that evidence is green may the owner separately approve an exact
   RC tag and GHCR destination. No tag, image publication, or deployment is
   authorized by this checkpoint.
4. Public MVP launch remains **HOLD** until credential rotation, protected
   two-user staging lifecycle, real secret-manager/TLS/DNS/firewall,
   off-host restore, monitoring/on-call, 48–72 hour soak, canary, rollback, and
   applicable compliance evidence are complete.

## 2026-07-24 final evidence and container-risk checkpoint

This section supersedes the older PR #8 continuation instructions below.

- The pre-PR #11 `main` baseline was
  `3930d0ebdf73cb58a0f7b30aaed0ec64e6e7fb3b`.
  PR #8 (Ruff declaration), PR #9 (portable OddsHarvester release runtime,
  scrape-dataset lineage and browser timing fixes), and PR #10 (replace
  vulnerable `python-jose`/`ecdsa` with PyJWT) are merged.
- `main` Backend, Frontend, and Security runs on `3930d0e` passed. PR #10 Hybrid
  E2E passed **56/56**.
- Evidence-only release run
  [30116510025](https://github.com/cahangeorge/betting-platform/actions/runs/30116510025)
  passed `verify-source` completely, including Alembic, backend **545/545**,
  frontend check/unit/build, Taskiq worker/scheduler smoke, and Chromium
  **56/56**. It built and runtime-smoked all three production images.
- That run stopped at the backend Trivy step with **115** operating-system
  findings (**96 High / 19 Critical**) for which the report showed no fixed
  version. Frontend/nginx scanning, SBOM packaging, and publication were
  skipped. `publish-signed-images` remained skipped and nothing was published.
- The local candidate changes the evidence contract rather than hiding those
  findings: every image writes a complete unfiltered JSON report, the reports
  are uploaded even when the gate fails, missing/malformed reports fail closed,
  and any High/Critical finding with an available fixed version blocks
  automatically. Unfixed findings remain explicit release evidence and require
  owner risk review before an RC tag can be approved. The decision is recorded
  as **Accepted** in
  [`2026-07-24-auditable-container-vulnerability-gate.md`](../adr/2026-07-24-auditable-container-vulnerability-gate.md).
- Evidence-only release run
  [30120739636](https://github.com/cahangeorge/betting-platform/actions/runs/30120739636)
  then proved the new contract end to end: `verify-source`, all three image
  builds, and runtime smoke passed; the auditable gate stopped on **72 fixable
  High/Critical findings** and uploaded the complete vulnerability reports.
  `publish-signed-images` was skipped and nothing was published.
- The current remediation upgrades the frontend toolchain to SvelteKit
  `2.70.1`, Svelte `5.56.7`, Vite `8.1.5`, the Vite Svelte plugin `7.2.0`, and
  PostCSS `8.5.23`; removes unused npm/Corepack tooling from the non-root
  frontend runtime image; and pins both nginx images to
  `nginx:1.30.4-alpine@sha256:97d490c...`. Local image inspection confirmed
  that the formerly reported fixable packages are absent or at/above Trivy's
  fixed versions. The local Trivy binary checksum passed, but its database
  resolver could not reach the registry from this host; the authoritative
  clean-revision proof therefore came from CI run `30123023608` below.
- PR [#11](https://github.com/cahangeorge/betting-platform/pull/11) merged on
  2026-07-24 at final docs head `5dafac8` as main merge commit `e2ea635`. Its
  Backend, Frontend, Security, and Hybrid E2E checks all passed.
- Evidence-only run
  [30123023608](https://github.com/cahangeorge/betting-platform/actions/runs/30123023608)
  passed `verify-source` and `build-scan-and-package`. It built, runtime-smoked,
  audited, and SBOM-packaged all three images. The final reports contain
  backend **115** unresolved findings (**96 High / 19 Critical**) with no
  `FixedVersion`, frontend **0**, nginx **0**, and **0 fixable** findings.
  `publish-signed-images` was skipped.
- Independent review found one fail-closed schema-validation bypass in the
  Python gate. The local follow-up now validates report identity/schema,
  non-empty results, required finding fields, field types, and the
  High/Critical-only severity contract; four adversarial regressions cover
  missing severity, non-string `FixedVersion`, unexpected severity, and a
  result object without its target identity. Targeted tests are **18/18**,
  Ruff is clean, Serena reports no diagnostics, and the hardened gate accepts
  the downloaded reports above.
- The final hardening SHA is `f897e6fa0e12a1305217b67a61a7eb65d204d1ff`.
  Backend, Frontend, Security, and Hybrid E2E all passed on that exact head;
  Hybrid passed in **7m32s**. Independent review concluded `APPROVE` with zero
  findings and architecture `CLEAR`.
- Final evidence-only run
  [30124777407](https://github.com/cahangeorge/betting-platform/actions/runs/30124777407)
  passed `verify-source` (**8m21s**) and `build-scan-and-package` (**5m26s**).
  Its exact reports again contain backend **115** unresolved findings (**96
  High / 19 Critical**) with no fixed version, frontend **0**, nginx **0**, and
  **0 fixable** findings. Three CycloneDX SBOMs and both evidence artifacts
  were uploaded; `publish-signed-images` was skipped.
- Post-merge Backend, Frontend, and Security runs passed on exact main
  `e2ea6355a0dad284cdb0dccdcaf8430cebbc1a6c`. Main evidence-only run
  [30126304645](https://github.com/cahangeorge/betting-platform/actions/runs/30126304645)
  passed `verify-source` (**7m50s**) and `build-scan-and-package` (**5m22s**).
  Its exact downloaded reports contain backend **115** unresolved findings
  (**96 High / 19 Critical**), frontend **0**, nginx **0**, and **0 fixable**
  findings. The hardened local gate accepted those exact reports, three
  CycloneDX SBOMs and both evidence artifacts were uploaded, and
  `publish-signed-images` was skipped.
- Fresh local verification on the synced tree:
  - backend Ruff and **545/545** pytest;
  - root release/security contracts **29/29**, Ruff, tracked/untracked secret
    scan, actionlint `1.7.12` with verified checksum, workflow YAML, shell
    syntax, and `git diff --check`;
  - frontend `pnpm check` 0 diagnostics, unit **121/121**, E2E TypeScript, and
    production build on Vite `8.1.5`; production dependency audit has only one
    Low finding and no High/Critical finding;
  - Chromium hybrid **56/56**, one worker, zero retries, **3.7m**;
  - after workflow-dispatch run `30120738580` exposed a duplicated transient
    lock/banner assertion, the two affected live-state tests passed **2/2**
    locally with the dedicated lock contract still intact;
  - production HTTPS PWA **3/3** with backend active;
  - Alembic `025 (head)` and `alembic check` with no upgrade operations.
- Codebase Memory was refreshed to **5,270 nodes / 20,126 edges**, status
  `ready`. The latest compressed whole-workspace Repomix pack remains
  `7fb2a326972893e0`; it was not regenerated because the current blocker and
  patch are narrow release-policy/script changes and fresh source/CI evidence
  is stronger.

Exact continuation order:

1. The product owner accepted the auditable container vulnerability policy on
   2026-07-24. This does not authorize a tag, GHCR publication, deployment, or
   public launch.
2. Merge this docs-only post-merge checkpoint after its normal PR checks. It
   does not change runtime or image build inputs, so it does not require
   another image-evidence run.
3. Do not approve or push a release tag until the exact backend residual-risk
   report is reviewed for runtime applicability and package-removal options.
4. Only after explicit approval naming both the exact
   tag and destination may an RC tag be pushed to GHCR. Protected staging,
   secrets/TLS/DNS/firewall, off-host restore, observability/on-call,
   soak/canary, rollback, and applicable compliance evidence still gate public
   MVP launch.

## 2026-07-24 main integration and release-gate checkpoint

Historical checkpoint (superseded by the section above):

- PR
  [#7](https://github.com/cahangeorge/betting-platform/pull/7) was retargeted
  to `main`, marked ready, and merged at `2026-07-24T09:50:40Z`.
  `origin/main` is merge commit `881a436971d28ef1736bf8c74894a0f9124ade83`;
  the commit has a valid GitHub signature.
- Post-merge `main` runs on exact SHA `881a436` passed:
  Backend `30084042800`, Frontend `30084042748`, and Security `30084042782`.
- GitHub environment `registry-release` now exists. Its custom deployment
  policy allows only tag pattern `v*`. Active repository ruleset
  `Protect release tags` (`19677671`) prevents update/deletion of matching
  release tags and requires verified commit signatures.
- No release tag exists and no GHCR release image was published. The attempted
  local tag command was rejected before execution by the external-egress safety
  gate because publishing the exact RC payload needs a new explicit
  confirmation.
- Evidence-only release run
  [30084295728](https://github.com/cahangeorge/betting-platform/actions/runs/30084295728)
  started correctly on `881a436`, passed checkout, toolchain, dependency-lock,
  Chromium, and Alembic steps, then failed at `Backend static and test gates`
  with exit `127`: `ruff: command not found`. Build/package/publish jobs were
  skipped; nothing was published.
- Root cause: `.github/workflows/release.yml` correctly installs
  `backend[dev]` and then calls Ruff, but `backend/pyproject.toml` did not
  declare Ruff in the `dev` extra.
- Fix commit `1131157` adds `ruff>=0.15.17,<0.16` to the backend `dev` extra on
  branch `agent/release-ruff-gate-2026-07-24`. Local verification passed:
  editable `.[dev]` install, Ruff, **532/532** pytest, and `git diff --check`.
- PR
  [#8](https://github.com/cahangeorge/betting-platform/pull/8) is open against
  `main` and contains the dependency declaration plus this durable handoff.
  Before the handoff push, Backend, Frontend, and Security were green and
  Hybrid E2E run `30084630886` was in progress. The handoff push restarts the
  applicable PR checks; inspect the current PR head and checks next session.
- Independent required deployment review is still unavailable because the
  repository currently has only collaborator `cahangeorge`. The environment
  therefore has tag restriction but no second-person reviewer gate.

Exact continuation order:

1. Re-run `git status --short --branch`, then inspect PR #8 and Hybrid E2E run
   `30084630886`.
2. If every PR #8 check is green, merge PR #8 into `main`.
3. Run `Release Build and Evidence` with `workflow_dispatch` on the new `main`
   and require complete `verify-source` plus `build-scan-and-package` success.
   `publish-signed-images` must remain skipped in this evidence-only run.
4. Ask for explicit approval naming the exact tag and destination:
   `v0.1.0-rc.20260724.1` → GitHub Container Registry for
   `cahangeorge/betting-platform`. Do not push the tag without that approval.
5. After approval, tag the newly verified `main` SHA, watch the protected
   release workflow, verify all three GHCR digests, Cosign signatures, GitHub
   attestations, and non-overwrite evidence.
6. Keep public MVP launch **HOLD** until protected staging, secrets/TLS/DNS,
   off-host restore, observability/on-call, soak/canary, rollback, and any
   applicable compliance gates are evidenced.

## 2026-07-24 published CI-remediation candidate

The first GitHub Actions run on `41333eb` exposed real runner-only defects in
backend dependency versions, bridge layout, a Playwright locator, Nginx
hardening, and the first-deployment/recovery path. Commit `3543ebb`
(`fix(release): close CI and first-deploy gates`) closes those findings:

- exact CI-like backend environment (FastAPI `0.139.2`, Starlette `1.3.1`,
  Flumine `3.1.0`) passed Ruff, **41/41** targeted live/API/trading tests and
  **531/531** full tests; Alembic remains `025 (head)` with no drift;
- live overview now has an ASGI HTTP response-model test and the WebSocket gate
  validates the public `/api/v1/live/ws` ASGI match, without FastAPI private
  serialization or included-router internals;
- Flumine uses the installed distribution when the optional local checkout is
  absent and still fails closed for an explicitly invalid configured checkout;
- hybrid CI checks out submodules, installs and imports OddsHarvester, and uses
  the runner Python for the bridge; the affected local hybrid scenarios passed
  **5/5**, one worker, zero retries;
- Nginx runs as UID `101` on internal `8080/8443`; release CI now proves UID,
  HTTP `308`, and a real temporary-certificate HTTPS handshake before packaging.
  Equivalent local smoke returned `uid=101 http=308 https=502`;
- the first-deployment bootstrap is committed and fail-closed, restore runs
  Alembic before applications restart, publish checks out repository scripts,
  and Security executes the production contracts;
- root production/security contracts are **21/21**; secret scan, actionlint,
  YAML, shell syntax and diff checks pass;
- independent backend, frontend and final release/UI reviewers reported
  **PASS / APPROVE**, with no P1/P2 code issue remaining.

The user explicitly authorized public repository publication. Follow-up commit
`d20c583` closes the two remaining runner timing failures:

- FastAPI request-scoped `yield` cleanup commits after the response, so
  scheduled-job create/toggle now commits before returning; its regression
  test proves immediate visibility and the exact CI-like backend suite passes
  **532/532**;
- the live-value test now waits for either actionable or locked asynchronous
  candidate state instead of branching on an early locator count.

All five branch workflows are green on exact SHA `d20c583`:

- Backend — run `30082364070`;
- Frontend — run `30082364092`;
- Security — run `30082364108`;
- Compose Smoke — run `30082364068`;
- Hybrid E2E — run `30082364057`, **56/56**.

The branch is therefore a published, CI-green candidate. This does not yet
authorize or prove the protected `v*` tag/GHCR/staging release.

## 2026-07-24 clean release-candidate integration

Owner-authorized integration produced five explicit commits without bulk
staging or history rewriting:

- `4b123b4` — backend schema, security, tenancy, idempotency, and Taskiq runtime;
- `34a952a` — frontend session, workflow, responsive UX, and PWA;
- `ddf0dfd` — production images, signed release workflow, security, and operations;
- `6c4394e` — canonical status, ADRs, runbook, Serena, and continuity;
- `40352ae` — repository-wide backend Ruff formatting required by the clean gate.

Fresh verification on `40352ae`:

- backend Ruff format/check passed; **530/530** tests passed; Alembic is
  `025 (head)` with `alembic check` reporting no upgrade operations;
- frontend `pnpm check` passed with 0 errors/0 warnings; **121/121** unit
  cases, E2E typecheck, and production build passed;
- root contracts **20/20**, secret scan, actionlint, YAML parse, shell syntax,
  both Compose renders, Serena integrity, and Git diff/status checks passed;
- Chromium hybrid **56/56** passed in 9.3m with one worker and no retries;
  PWA production **3/3**, Firefox **1/1**, and official-container WebKit
  **1/1** passed;
- runtime remained ready at backend `127.0.0.1:8001`, frontend
  `127.0.0.1:5175`, PostgreSQL `5433`, and Redis `6380`.

Repomix refreshed the whole workspace at output ID `8f2867d9900ff53a`
(1,167 files). Codebase Memory `bet-core` was reindexed in moderate mode at
**5,237 nodes / 19,762 edges**.

After the CI remediation and durable handoff commits, Repomix produced a fresh
compressed whole-workspace pack at output ID `7fb2a326972893e0`: **1,154 files /
2,470,226 tokens / 138,612 lines**, excluding the already inventoried large
HAR, build, cache, and dependency artifacts.

## 2026-07-24 final local verification refresh

Evidence already confirmed in this checkout:

- Backend: Ruff passed; **530 pytest** passed. Alembic is at **025 head** with
  no migration drift.
- Root release contracts: **20 production-contract/secret tests** passed;
  tracked-plus-untracked local secret scanner passed; both Compose files pass config and render
  validation; `bash -n` and `git diff --check` passed.
- Runtime: `/health` and `/ready` return 200; `/ready` now requires Redis plus
  fresh worker and scheduler heartbeats and reports `task_runtime: ready`;
  frontend returns 200; runtime smoke, queued-message recovery, lost-stream
  outbox recovery, and provider canary passed. The final process audit caught
  older Bet processes falling back to `localhost:6379`, which on this machine
  belongs to Smartwork. API, worker, and scheduler were stopped and restarted
  explicitly on Bet Redis `127.0.0.1:6380` (DB 0, result DB 1); the Taskiq
  round-trip then passed and `/ready` remained fully ready.
- Frontend: `pnpm check` passed with **0** diagnostics; all **32 unit files /
  121 test cases** passed; `pnpm check:e2e` and production build passed.
- Browser before the final audit/P1 fixes: two complete Chromium hybrid passes,
  **46/46** each with `retries=0`, followed by **47/47** twice after the first
  audit slice. After the complete P1 slice, the exact command
  `pnpm exec playwright test --project=chromium-hybrid --retries=0` passed
  **52/52 twice consecutively** in 9.3m and 9.4m; this includes same-tab
  betslip ownership, cross-tenant REST/settlement isolation, and user-scoped
  prediction WebSocket isolation. After the device/accessibility additions, a
  fresh single-worker Chromium run with `retries=0` passed **56/56** in 10.3m;
  the two tests adjusted during that run were then rerun against the final
  files and passed **2/2**. Final Firefox smoke passed **1/1**. Host WebKit
  could not start because three shared libraries are absent, while the same
  official smoke passed **1/1** in the official Playwright `v1.60.0-noble`
  container.
- PWA: production-build HTTPS install/cache/offline, in-shell offline/recovery
  announcements, and update-with-draft preservation passed **3/3** after the
  manifest stopped forcing portrait-only orientation.
- Production image build/runtime: all three local image gates are now proven.
  Rootless Podman could reach external hosts but could not perform DNS lookups
  from build containers, so validation supplied explicit host-resolved
  mappings without changing the Dockerfiles. The frontend image
  `localhost/bet-frontend:mvp-validation-20260724` built from the pinned Node
  digest, ran as UID 1001, and returned `/about` 200; image ID
  `ad05990f46ef...`, local digest `sha256:6aaad448e85c...`. The backend image
  `localhost/bet-backend:mvp-validation-20260724` built the **204-package**
  strict lock plus bundled Playwright Chromium, ran as UID 1001, imported
  FastAPI, and launched Chromium; image ID `91ba6a3e1c77...`, local digest
  `sha256:827552c95c94...`. The pinned nginx image previously built and passed
  `nginx -t` with temporary TLS and Compose upstream names. These local
  dirty-checkout digests are not registry/release identities; the protected
  workflow must reproduce the build and scan from a clean revision.
- Release hardening after the final application audit found two invalid
  GitHub Action SHA pins. `pnpm/action-setup` is now pinned to verified
  `v6.0.9` commit `0ebf471...`; the removed Trivy reference was replaced with
  the official known-safe `trivy-action v0.35.0` commit `57a97c7...` and Trivy
  binary `v0.69.3`, following
  [GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23).
  All 12 unique action references are full-SHA pinned; the five newly added
  registry/signing/attestation pins and the existing release pins resolve to
  their reviewed official versions.
- Tag releases now depend on a source-verification job that runs Alembic,
  backend Ruff/pytest, frontend check/unit/typecheck/build, and the complete
  Chromium hybrid suite before any image build or scan. That job now also
  starts a real Redis-backed Taskiq worker and scheduler, requires both runtime
  probes, and executes the Taskiq round-trip smoke. CI Postgres/Redis service
  images are digest pinned, unfixed High/Critical findings are no longer
  ignored, and image identities are retained in release evidence.
- Protected `v*` tag releases now preserve the exact images that passed runtime
  smoke, Trivy, SBOM, and secret gates, then publish them to GHCR under
  `sha-<git-sha>`. The workflow captures registry digests, signs and verifies
  each digest with keyless Cosign, creates and verifies three GitHub provenance
  attestations, refuses existing SHA/version references, and promotes the
  version tag only after both verification systems pass. `workflow_dispatch`
  remains evidence-only. The workflow uses `GITHUB_TOKEN` plus ephemeral OIDC;
  protected-environment configuration and one disposable real tag execution
  remain external evidence gates.
- Release evidence is now gated on executing the locally built production
  images in CI: the backend and frontend must run as non-root, the backend must
  import the FastAPI app and launch bundled Chromium from `/ms-playwright`, and
  the frontend must start and answer an HTTP probe before packaging can begin.
- The repository scanner now includes Git-visible untracked files in the local
  gate, fails closed with a redacted `read-error` finding, permits fixture
  markers only in the approved scanner test path, and uses exact/anchored
  development placeholders rather than substring exemptions. Its adversarial
  review ended at **Critical 0 / High 0 / Medium 0 — APPROVE**.
- The backend image now installs Chromium into shared
  `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` and grants the non-root runtime user
  access. A combined Python 3.12 production lock covers backend plus all three
  bridge projects: **204 exact packages**, lock regeneration matched, and a
  fresh temporary-venv `uv pip install --dry-run --strict` succeeded.
- Frontend builds now pin `pnpm 10.34.5`, perform one frozen dependency
  installation, prune to production dependencies in the builder, and copy the
  resulting `node_modules` into the non-root runtime image instead of resolving
  dependencies a second time. A fresh pinned-pnpm install, check, 121 unit
  cases, E2E typecheck, production build, and Chromium authenticated smoke all
  passed.
- The final Luna frontend/PWA/UX audit found no P0/P1 regression. Its locally
  actionable content findings were closed: ticket-review labels are now
  Romanian, the unused fake zero-result backtest API stub and types were
  removed, the stale 404 copy was corrected, and the PWA permits any
  orientation. Svelte MCP autofix found no component errors; `pnpm check`,
  121 unit cases, E2E typecheck/build, the five affected Chromium flows, and
  PWA **2/2** all passed after the change.
- A follow-up device/accessibility audit added landscape `844x390` collision
  proof, simulated nonzero bottom safe-area geometry, coarse-pointer 44 CSS-px
  touch-target assertions, and a Chromium forced-colors keyboard-focus smoke.
  The implementation fixed High Contrast focus fallback with a system-color
  outline that overrides utility-level outline removal. The affected Chromium
  scenarios passed locally, and the expanded PWA production suite passed
  **3/3**. Actual iOS/Android installed-app lifecycle, Windows High Contrast,
  and manual desktop 200% zoom remain hardware/operator acceptance gates.
- The final independent UI gate ran the current complete Chromium hybrid suite
  single-worker with no retries and passed **56/56** in 10.3m. The final
  forced-colors and coarse-pointer specs passed **2/2** again after their last
  test-only refinements; Firefox passed **1/1**, and WebKit passed **1/1** in
  the official Playwright container. The host-only WebKit startup failure is
  classified as an environment limitation (`libicu74`, `libxml2`, and
  `libflite1` absent), not an application failure.
- Recovery: the guarded E2E cleanup removed the accumulated fixture namespaces;
  the final post-P1 cleanup removed 14 no-direct-DB WebKit namespaces and the
  final dry-run reported `Namespaces: 0`. A non-destructive PostgreSQL
  dump/restore drill into a
  temporary database passed again at Alembic `025`; schema/version and key row
  counts matched the source.
- Mandatory local P1 remediation is implemented and freshly tested:
  - auth signup/login uses bounded, hashed identity/source rate-limit buckets,
    fail-closed guard behavior, `429`/`Retry-After`, and structured audit events
    without raw email, source, token, or password data;
  - WebSocket admission is bounded globally and per user with idle, message
    size, send-timeout/backpressure, and user-scoped prediction delivery;
  - Prepare distinguishes transport/catalog/job errors from empty states,
    preserves partial/all-failed attempt reasons, and retries only failed work
    without duplicate job creation;
  - terminal session expiry has one logout path that clears user-owned drafts,
    disconnects WebSockets, stops reconnects, and returns to login;
  - a SvelteKit application error/recovery boundary is present; Analyze and
    Tickets retain truthful API-backed status polling rather than fake progress;
  - workflow content is operationally consistent and the tenant isolation gate
    covers jobs, predictions, bankroll, trading, settlement, and WebSockets.
- Migrations `024` and `025` close two late correctness gaps:
  - `024` adds durable per-user create idempotency for scrape/scheduled-job POST
    requests. Identical `Idempotency-Key` replays return the original resource;
    a mismatched body conflicts instead of creating duplicates.
  - `025` adds `users.session_version`. Access tokens carry the version;
    refresh/logout are serialized; logout invalidates all access tokens and
    active WebSockets, including cross-worker command/broadcast paths.
- The final auth/WebSocket adversarial pass covers fresh handshake and command
  revalidation, global/per-user capacity, pending-reservation cleanup under
  exception/cancellation, concurrent disconnect during broadcast, backpressure,
  safe close diagnostics, and redacted audit logging.
- Taskiq `0.12.4` was found to derive poison absolute-path task names when a
  task module ran as `__main__`. Every active job/trading task now has an
  explicit canonical name; the 11 obsolete pending poll ticks were acknowledged
  without deleting the stream, and both health and scheduled-poll round trips
  pass with `XPENDING=0`.
- Legacy invalid cron rows are quarantined individually instead of aborting the
  scheduler batch. The live poll disabled the two invalid local rows and
  returned `scheduled_poll_error=False return=0`.
- Prepare now keeps a stable idempotency key per logical attempt, retries only
  failed work, preserves job IDs/reasons, keeps the wire contract
  `Hours`/`Days`/`Weeks` plus `historic_seasons`, and presents Romanian labels
  without translating protocol values.
- Odds buttons now expose match-specific accessible names. This removed an
  ambiguous Playwright selector that could choose a different real match with
  the same odds; the affected modal/mobile/ticket-validation flows pass 4/4
  before both final full-suite runs.
- The new auth and WebSocket limits are documented in `backend/.env.example`
  and explicitly wired into the production Compose contract. They are
  deliberately per API process; multi-replica public production still needs
  shared edge rate limiting plus shared WebSocket pub/sub/admission control.
- Independent release review found seven High issues. Six locally actionable
  issues were remediated: scheduled-job ownership spoofing, strict job/cron
  validation, scheduled ticket replay idempotency, user-scoped betslip drafts,
  recursive submodule checkout, and automatic known-good restore on failed
  deployment smoke. A final independent re-review found and then approved the
  multi-container Taskiq heartbeat correction. The final P1 re-review then
  iterated through WebSocket cancellation/cache/concurrency findings and ended
  at **Critical 0 / High 0 / Medium 0 — APPROVE**. External credential
  revocation remains open.
- A separate final release-hardening review found missing image runtime smoke
  and two scanner masking fallbacks. Those were remediated and the focused
  re-review ended at **Critical 0 / High 0 / Medium 0 — APPROVE**, with
  **20/20** root contracts, scanner, Ruff, actionlint, YAML, shell, and
  diff checks green.
- The signed-registry follow-up review initially found a broken image-archive
  checksum path and a fail-open registry existence preflight. Both were closed:
  checksum creation/verification now use the same directory, the executable
  registry guard accepts only explicit OCI absence codes and fails closed for
  existing/auth/network/unclassified results, image handoff retention matches
  the 30-day protected-environment window, and partial-publication quarantine
  is documented. Independent re-review ended at **Critical 0 / High 0 /
  Medium 0 — APPROVE**.
- The production Compose contract now requires authenticated Redis DB 0/DB 1
  URLs, enables Redis `requirepass`, keeps Redis/PostgreSQL private, and applies
  configurable CPU, memory, PID, stop-grace, tmpfs, and bounded local-log
  defaults. A fresh production render passed without printing resolved secret
  values. Cross-host Redis/PostgreSQL still requires TLS supplied by the target
  platform.

Public launch remains blocked by external credential rotation, protected
environment/tag/package configuration plus an actual signed GHCR tag run,
secret-manager setup, DNS/valid TLS/firewall, off-host backup/restore rehearsal,
staging lifecycle with two-user evidence, observability/on-call/soak/canary,
and protected CI build/publish/pull proof.

Durable knowledge synchronization at this checkpoint:

- Serena memories `core`, `mvp_readiness`, and `platform_hardening` now record
  the current `025`/auth/WS/idempotency/Taskiq/release state.
- Native Codebase Memory reindexed `bet-core` after `d20c583` in moderate mode
  to **5,248 nodes / 19,986 edges**; actual and expected graph counts match and the result
  is `indexed`.
- The final compressed whole-workspace Repomix pack is output
  `59a58de9391eb430`: **1,153 files / 2,467,034 tokens / 138,366 lines**;
  the very large tracked OddsHarvester HAR fixtures were excluded from this
  compressed analysis pack after also being inventoried by an unfiltered
  `f36c4ad6eefdb705` **1,164-file / 50,053,755-token** pack.
  The final full-content active-platform/release pack is output
  `233d99f089e79988`: **556 files / 788,286 tokens / 84,088 lines**. Targeted
  grep verified the real Taskiq release gate, signed exact-digest GHCR flow,
  fail-closed registry guard, forced-colors/coarse-pointer/safe-area coverage,
  and PWA offline/recovery test in the packed snapshot.

## Repomix whole-workspace study - 2026-07-23

The findings in this subsection are the initial static snapshot. The current
verification refresh above supersedes them: the literal secret was removed
locally and scanning was added, paper execution was excluded by ADR, tunnel
CORS was restricted, Alembic drift was reconciled through `025`, and production
release workflows were added. Provider-side credential revocation remains an
external blocker.

This read-only study covered the active platform, all three tracked submodules,
and the ignored local `flumine/` and `betfront/` checkouts. No application code,
submodule, dependency, database, runtime, commit, push, or deployment action was
performed.

Fresh inventory and checkout evidence:

- The initial full Repomix pack contained 1,102 files and approximately 50.7M
  tokens; OddsHarvester HAR captures dominated the payload.
- The optimized structural pack retained 1,063 files and approximately 977K
  tokens after excluding generated caches, databases, HAR captures, notebooks,
  and other bulky test data.
- Separate optimized packs covered 137 `flumine/` files and 179 archived
  `betfront/` files that the root `.gitignore` intentionally excludes.
- The active product contains 25 SvelteKit page routes and 109 FastAPI HTTP or
  WebSocket route decorators. `backend/app` plus `frontend/src` contains 47,225
  source lines.
- Fresh nested status: `OddsHarvester/`, `penaltyblog/`, `soccerdata/`, and
  `flumine/` are clean. Archived `betfront/` already has local modified/deleted
  files and remains outside parent Git tracking; preserve that work.
- Parent branch divergence is 20 commits ahead and 5 commits behind
  `origin/main`. Parent dirty state remains 29 tracked modifications plus 6
  untracked files.

Highest-priority findings:

1. **P0 secret exposure:** tracked `.kilo/kilo.json` contains a plaintext
   third-party API key. Treat it as compromised: revoke/rotate it, replace it
   with environment-based injection, and add repository secret scanning. The
   value is intentionally omitted here.
2. **P1 paper-trading reproducibility:** both Compose files enable paper
   trading and mount `./flumine`, while `flumine/` is optional, ignored, and not
   initialized by `scripts/bootstrap-external-projects.sh`. The paper adapter
   requires that local checkout, but account health currently checks flags and
   account metadata rather than adapter readiness. A fresh clone can therefore
   report a healthy paper account and fail only when execution begins.
3. **P1 credentialed tunnel CORS:** `backend/app/main.py` accepts every
   `*.trycloudflare.com` origin with credentials, independent of an explicit
   development-mode gate. Replace this with explicit environment allow-lists
   before exposing an authenticated tunnel.
4. **P1 migration risk:** the known broad Alembic ORM/index drift remains a
   separate reviewed-migration task; this study did not rerun `alembic check`.
5. **P2 documentation drift:** `.gitmodules` tracks `platform`, while
   `docs/external-projects.md` still says `master`; that document and `AGENTS.md`
   understate the active paper-trading integration. `DESIGN.md` retains resolved
   open questions, and the older implementation roadmap still labels the final
   verification phase as in progress.
6. **P2 maintainability concentration:** major behavior is concentrated in
   `backend/app/services/ticket_engine.py` (2,656 lines),
   `frontend/src/routes/prepare/+page.svelte` (2,104),
   `frontend/src/lib/components/TicketsPanel.svelte` (1,734), and
   `frontend/src/routes/analyze/+page.svelte` (1,365). Future changes in these
   files need narrow regression-first slices.
7. **P2 CI coverage:** root CI has strong backend/frontend/hybrid checks, but
   Compose CI validates configuration only, the root workflows do not run the
   nested project suites, and no root secret-scanning workflow is present.

Fresh commands/results:

- `pwd`, `git status --short --branch`, `git submodule status`: passed and
  reconciled with the dirty checkpoint.
- Repomix full/optimized workspace packs plus separate `flumine/` and
  `betfront/` packs: completed successfully.
- Direct path-only secret validation confirmed `.kilo/kilo.json` is tracked;
  no secret value was printed into this handoff.
- Nested `git status --short --branch`: clean for active nested projects and
  already dirty for archived `betfront/`.
- `git diff --check`: passed.

Verification gap:

- Backend/frontend/unit/browser/database/runtime tests were not rerun because
  this was a static architecture and risk study. The 2026-07-19 product gate
  results below remain historical evidence rather than fresh runtime proof.

## Product remediation update - 2026-07-19

The RepoWise audit findings were split across frontend, backend, DevOps, and QA
lanes and the P0/P1 scope was implemented in the shared checkout.

Completed product changes:

- The production service worker now deduplicates precache entries, caches only
  known public build/static assets, treats `/api` as network-only, and never
  persists authenticated navigation responses.
- Legacy value feeds without trust/freshness metadata fail closed as
  monitor-only, `ou_2_5` aliases are canonicalized in the betslip, and manual
  WebSocket disconnect no longer schedules a reconnect.
- The root layout opens the live WebSocket only for authenticated users and
  disconnects it when authentication disappears.
- `/api/v1/live/ws` authenticates before accept, validates Origin, tracks the
  connected user, scopes prediction updates to that user, and closes the socket
  when the access token expires.
- Live overview selects the latest completed prediction run per match instead
  of using one latest run globally.
- Migration `022` enforces one execution intent per `(user_id, ticket_id)`;
  paper execution handles the concurrent uniqueness conflict and completes the
  delivery state consistently on terminal failures.
- User-triggered `POST /jobs/run-due` is scoped to an owned `job_id` for
  non-admin users. The hybrid workflow uses that selector, so it cannot claim
  unrelated due jobs from a persistent database.
- The calendar-dependent prediction calibration test now anchors quote time to
  the target match instead of wall-clock time.

### Historical intermediate verification snapshot

The following numbers were captured during an earlier remediation checkpoint
and are retained for audit chronology. They are superseded by the
`2026-07-23 verification refresh` near the top of this document.

- Backend Ruff: passed; backend pytest: **459 passed**.
- PostgreSQL: migration `022 (head)`, zero duplicate `(user_id, ticket_id)`
  groups, and the new unique constraint confirmed in the catalog.
- Frontend `pnpm check`: **0 errors, 0 warnings**; unit tests: **28 passed**;
  `pnpm build` and `pnpm check:e2e`: passed.
- Chromium service-worker proof: one activated registration, 110/110 unique
  cache entries, one `/offline.html`, zero cached `/api` entries, and no live
  WebSocket opened on the public `/about` page.
- Full hybrid Playwright: 41 tests passed directly and one transient
  `net::ERR_ABORTED` navigation passed on retry. The affected test then passed
  once in isolation and three consecutive times with retries disabled.
- The scoped scrape/predict/ticket/settlement scenario passed without starting
  any unrelated scraper and left no new scheduled-job runs after cleanup.
- `git diff --check`: passed; nested projects remained untouched.
- At that checkpoint RepoWise/Codebase Memory was
  `ready` with 4,944 nodes and 18,119 edges. Change detection reports the same
  35 unique dirty paths as Git, including the pre-existing continuity work.

Risks and gaps recorded at that intermediate checkpoint:

- At that time `alembic check` reported broader legacy ORM/index drift (45 removal
  candidates, 11 addition candidates, and 2 constraint differences). Migration
  `022` was applied correctly. This specific drift is now superseded: migration
  `025` is current and the final `alembic check` reports no new operations.
- The former stateless-access-token gap is superseded by migration `025`:
  access tokens and WebSockets bind `users.session_version`, while serialized
  logout increments the version, removes refresh sessions, and closes active
  connections. Cross-worker command and broadcast paths revalidate the version
  from the database before continuing.
- The live Playwright project still proves scraping only; a protected staging
  workflow is needed for a complete external live predict/ticket lifecycle.
- The feature branch remains divergent from `origin/main` and is not integrated
  or deployed by this session.
- During the initial E2E audit, the previous unscoped `run-due` call claimed one
  existing scrape job. It completed with zero records and no remaining external
  process; its audit trail was preserved. The new API/test scoping prevents a
  recurrence.

## Earlier continuity adoption completed

- `AGENTS.md` now points to this canonical handoff and defines the mandatory
  start/end session workflow.
- `docs/codex/continuity.md` defines source precedence, deterministic
  `bet-core` detection/reindexing, Serena and semantic-memory rules, retention,
  backup, secret handling, and the decision to defer Beads.
- `docs/status/handoff-template.md` provides the reusable, evidence-based
  status shape.
- `docs/adr/README.md` documents the existing date-based ADR convention,
  lifecycle, and template; the existing Taskiq record is explicitly marked
  `Accepted`.
- `.cbmignore` is an explicit versionable scope/security artifact for the
  current Bet index.

## Earlier continuity verification

These checks belong to the earlier documentation-adoption lane. Current product
verification is recorded in the remediation update above.

- `git rev-parse --show-toplevel` -> `/home/gion/Projects/bet`.
- `git branch --show-current` -> `agent/demo-tickets-2026-07-17`.
- `git submodule status` -> `OddsHarvester`, `penaltyblog`, and `soccerdata`
  remain at their recorded commits; no nested project was modified here.
- `codebase-memory-mcp cli index_status --project bet-core` -> `ready`, branch
  `agent/demo-tickets-2026-07-17`, base/current HEAD
  `5963d3fe5534f1377459ea6eacba71ba660ad94a` before this documentation edit.
- `codebase-memory-mcp cli detect_changes --project bet-core` initially
  reported only `.cbmignore`; after the documentation edits it reports pending
  repository changes, as expected.
- `codebase-memory-mcp cli index_repository --repo-path
  /home/gion/Projects/bet --name bet-core --mode moderate` -> `indexed`; final
  `index_status` -> `ready` with 4,913 nodes and 17,777 edges.
- Final `detect_changes` -> 7 unique working-tree paths (10 raw entries), which
  reconciles with this intentionally dirty documentation adoption. Reindexing
  does not clear Git-relative dirty-state detection.
- A local relative-link/path check resolved every referenced path in
  `AGENTS.md` and the four continuity documents.
- `serena memories check` -> `No referential integrity issues found`.

## Earlier continuity lane gaps

- Backend, frontend, database, health, and Playwright checks were not rerun in
  this documentation-only lane. The 2026-07-17 results below are historical.
- The index is refreshed, but the continuity files remain uncommitted; therefore
  Git-relative change detection correctly remains non-zero.
- No commit, push, deployment, dependency installation, Beads installation, or
  external issue-tracker change was performed.

## Earlier continuity lane risks

- No blocker for the repository documentation.
- Future structural product edits can make Codebase Memory stale again; use the
  documented detect/reindex workflow before high-impact graph analysis.
- This working tree is intentionally dirty with the adoption files listed
  above; preserve them and any later user work.

## Exact next step

Finish PR #14 checks, produce clean release evidence on the reviewed revision,
merge it, and rerun evidence-only verification on exact merged `main`. If all
gates remain green and the three reports contain zero fixable High/Critical
findings, create new immutable tag `v0.1.0-rc.20260725.2` for
`ghcr.io/cahangeorge/betting-platform-{api,frontend,nginx}`. Never reuse RC1.
Keep public release/MVP launch **HOLD** until protected publication evidence,
secret-manager, DNS/TLS/firewall, off-host backup/restore, protected two-user
staging, observability/on-call/soak/canary/rollback, and applicable compliance
evidence are recorded.

## Historical platform snapshot

The product facts and evidence below were carried forward from the previous
handoff. They were last product-verified on 2026-07-17 on branch
`codex/platform-hardening-2026-07-12`; they are useful context, not fresh proof
for the current branch.

## Active platform

- Product UI: `frontend/` (SvelteKit 2, Svelte 5), local dev port `5175`.
- Product API: `backend/` (FastAPI, SQLAlchemy, Alembic), local dev port `8001`.
- Database: PostgreSQL; verified migration head is `021`.
- `betfront/` is archived. Do not use it for current UI work.
- `OddsHarvester/`, `penaltyblog/`, and `soccerdata/` are nested projects. Inspect
  their own status and instructions before any change.

## Historical implemented workflow

The current operator path is:

```text
Prepare -> Analyze -> Tickets review -> explicit activation -> Monitoring/settlement
```

Implemented contracts:

- Analyze can execute multiple active strategies while preserving exact dataset
  and prediction-run lineage.
- Tickets accepts multiple `run_ids`, retains each leg's model prediction, and
  keeps generated batches non-financial until explicit activation.
- Ownership checks, deduplication, batch lifecycle rules, and E2E cleanup are
  enforced by the backend.
- Quote evidence is persisted through generation, refresh, activation, and
  closing; migration `021` makes refresh/closing history append-only and
  revisioned.
- CLV uses the latest deterministic quote revision and prefers activation over
  refresh over generation as its reference evidence.
- Bankroll policies support conservative flat/fractional-Kelly staking, hard
  ticket/open-exposure limits, cooldowns, and explicit automation controls.
- League exposure uses exact rolling `league_window_hours` windows based on real
  kickoff times. Accumulator stakes are deduplicated and missing kickoff context
  fails closed.
- Model governance, validation evidence, calibration/CLV monitoring, public SEO,
  legal pages, responsible-gambling content, and responsive workflow surfaces
  are present in the active platform.
- Refresh tokens are unique, session-bound, single-use, transactionally rotated,
  revoked on logout, and restored before protected SvelteKit page loaders run.
- Global strategy mutations are admin-only in both API authorization and UI;
  non-admin users receive a read-only catalog.
- Keyboard navigation includes a working skip link, focus-trapped command
  palette, visual-order arrow traversal, and focused-item activation.
- External/live bet placement remains disabled; supported execution is local
  paper simulation only.

## Historical database lineage

Recent migration chain:

```text
012 prediction run lineage
013 ticket batch prediction lineage
014 prediction run match-count backfill
015 concurrent prediction-run guard
016 ticket-leg audit snapshots
017 odds quote lineage
018 bankroll risk policy
019 model governance
020 monitoring snapshot ownership
021 revisioned ticket quote history (current head)
```

Migration `021` was verified on PostgreSQL with downgrade `021 -> 020`, upgrade
`020 -> 021`, and final `alembic current` output `021 (head)`.

## Historical verification evidence

Verification completed on 2026-07-17:

- `backend/.venv/bin/ruff check app tests alembic`: passed.
- `backend/.venv/bin/pytest -q`: **447 passed**.
- `git diff --check`: passed.
- `frontend/pnpm check`: **0 errors, 0 warnings**.
- `frontend/pnpm test:unit`: **27 passed**.
- `frontend/pnpm build`: passed.
- Hybrid Playwright, Chromium, no retries: **41 passed** in approximately 3.0m.
- Refresh-only SSR rotation stability loop: **15/15 passed** without retries.
- Backend health: `GET http://127.0.0.1:8001/health` returned
  `{"status":"ok","app":"bet-backend"}`.
- Frontend `http://127.0.0.1:5175/about` returned HTTP `200`.

These are historical verification results, not a substitute for rerunning the
smallest relevant checks after new edits.

## Historical residuals and current cautions

1. The platform hardening changes were collected on
   `codex/platform-hardening-2026-07-12`; inspect branch/PR state before adding
   follow-up work.
2. The parent sees `OddsHarvester` as modified from pre-existing nested work. It
   was not changed by the platform-hardening implementation.
3. `alembic check` still reports historical ORM/index drift across older tables.
   The drift introduced around `ticket_leg_quote_snapshots` was resolved; the
   remaining report is broader legacy alignment work and must not be converted
   blindly into a destructive migration.
4. Local dev processes may no longer be alive in a future session even though
   they were healthy when this status was written.

## Product verification runbook

Start every session with the shorter continuity workflow in
`docs/codex/continuity.md`. When current product claims need revalidation, use
the commands below from the repository root:

```bash
cat AGENTS.md
git status --short --branch
git submodule status
```

Then verify the current platform without touching nested projects:

```bash
cd backend
.venv/bin/alembic current
.venv/bin/ruff check app tests alembic
.venv/bin/pytest -q

cd ../frontend
pnpm check
pnpm test:unit
pnpm build
```

For an integrated local run:

```bash
# backend/ - do not omit these values on this multi-project machine:
export BET_TASK_QUEUE_BACKEND=taskiq
export BET_REDIS_URL=redis://127.0.0.1:6380/0
export BET_TASKIQ_RESULT_BACKEND_URL=redis://127.0.0.1:6380/1

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
.venv/bin/taskiq worker app.tasks.broker:broker app.tasks.jobs \
  --workers 1 --max-async-tasks 10 --log-level WARNING
.venv/bin/python -m app.tasks.scheduler

# frontend/
pnpm dev
```

Run Playwright only after both services are reachable. The integrated defaults
are frontend `127.0.0.1:5175` and backend `127.0.0.1:8001`.
PostgreSQL and Redis for Bet are exposed at `127.0.0.1:5433` and
`127.0.0.1:6380`; `127.0.0.1:6379` is not a Bet runtime endpoint on this
machine.

## Primary implementation references

- Workflow plan: `docs/plans/2026-07-13-analysis-tickets-workflow.md`
- Product/UI contract: `DESIGN.md`
- Quote lineage: `backend/app/models/odds_lineage.py`,
  `backend/app/services/clv_tracking.py`,
  `backend/alembic/versions/021_revision_ticket_quote_history.py`
- Risk controls: `backend/app/services/portfolio_risk.py`,
  `backend/app/services/risk_policy.py`
- Ticket orchestration: `backend/app/services/ticket_engine.py`
- Browser proof: `frontend/tests/e2e/hybrid/`
