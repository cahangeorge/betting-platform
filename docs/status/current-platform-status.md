# Current Platform Status

Updated: 2026-07-24T10:52:26+03:00
Repository/branch: `/home/gion/Projects/bet` / `agent/demo-tickets-2026-07-17`
Dirty state at this handoff refresh:

```text
Clean working tree at 40352aed38f98600a621954c67c82b600faab223.
The branch is five commits ahead of
origin/agent/demo-tickets-2026-07-17. No reset, clean, checkout, history
rewrite, or submodule mutation was performed.
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
- Phase 2 security/release foundation: **local gates green; external release gates pending**.
- Phase 3 product/UX: **local implemented scope and browser/PWA gates green**.
- Phase 4 adversarial QA/staging: **local gates green; protected staging and external operations evidence pending**.
- Phase 5 release candidate: **clean local revision complete; push, protected
  release, and external staging gates in progress**.
- Paper execution: **excluded from public MVP** by accepted ADR
  [`2026-07-23-exclude-paper-execution-from-mvp.md`](../adr/2026-07-23-exclude-paper-execution-from-mvp.md).
- Verdict: **clean local release-candidate validation GO; public release/MVP
  launch HOLD pending external evidence**.

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
clean integrated revision, and protected CI build/publish/pull proof.

Durable knowledge synchronization at this checkpoint:

- Serena memories `core`, `mvp_readiness`, and `platform_hardening` now record
  the current `025`/auth/WS/idempotency/Taskiq/release state.
- Native Codebase Memory reindexed `bet-core` in moderate mode to **5,237
  nodes / 19,762 edges**; actual and expected graph counts match and the result
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

Push the clean branch, inspect all GitHub checks and protected
`registry-release` environment/tag/package controls, then run one disposable
signed GHCR tag from the verified SHA. Deploy only verified digest-pinned
images to protected staging. Keep public release/MVP launch **HOLD** until
external credential rotation, secret-manager, DNS/TLS/firewall, off-host
backup storage and restore, staging two-user scrape-to-settlement evidence,
observability/on-call/soak/canary, and protected CI build/publish/pull evidence
are recorded.

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
