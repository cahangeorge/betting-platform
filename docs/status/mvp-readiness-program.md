# MVP Readiness Program

Updated: 2026-07-29T20:28:26+03:00
Repository: `/home/gion/Projects/bet`
Branch: post-merge status checkpoint based on `main` at `6abb637`
Program status: **ACTIVE — merged source/evidence-only GO; protected RC and public MVP launch HOLD**

This is the durable execution register for reaching a verified MVP. It records
project status, expert findings, phases, task dependencies, verification gates,
blockers, evidence, and the exact completion contract. The canonical session
checkpoint remains `docs/status/current-platform-status.md`; that document must
link here while this program is active.

The commit-safe integration order for the existing dirty checkout is
`docs/status/release-candidate-reconciliation.md`.

## Verified refresh — 2026-07-29

- PR #15 merged the reviewed implementation into `main` as
  `6abb6378e79a872e31af2bd9740b00e14f3330c9`. Post-merge Backend
  `30474183185`, Frontend `30474184976`, and Security `30474183724` passed.
  Evidence-only run `30474329662` passed source verification,
  image build/runtime smoke, scans, SBOMs, secret scan, gating and packaging;
  publication was skipped. RC1 remains quarantined and no RC2 tag exists.
- Fresh Serena, Codebase Memory, Codex Memory and focused Repomix inspection
  was reconciled with Git/source. The current source audit found and locally
  remediated scraper input/SSRF/resource controls, false upcoming-range
  semantics, stale/orphaned deduplication, unknown-job false success and
  missing odds-snapshot dataset/job lineage.
- The Prepare UI now asks for one target day from 1 to 31 days and defaults to
  tomorrow. The frontend sends its browser timezone; the backend persists the
  absolute target date and validates again at execution. Recursive payload
  shape, final normalized size, provider origins, and nginx body size are
  bounded.
- Fresh local gates: Ruff pass; backend **556 passed**; Svelte check **0/0**;
  frontend unit **32 passed**; E2E TypeScript and build pass; targeted Chromium
  **3 passed**;
  integrated health/readiness pass; full Chromium hybrid **57 passed** in
  **3.8 minutes**; Alembic **025 (head)** with no drift; root
  release/security contracts **29 passed** and tracked-secret scan passed.
  Final independent review returned **APPROVE** with no blocking finding.
- The implementation is merged and exact-main evidence-only proof is green.
  This status-only successor must receive its own exact-merge evidence run
  before any tag. Protected RC/public status remains HOLD.

## MVP scope

### Included

- SvelteKit frontend and FastAPI/PostgreSQL backend.
- Authenticated Prepare -> Analyze -> Opportunities -> Tickets ->
  Monitoring/settlement workflow.
- Dataset, prediction, ticket, quote, bankroll, and settlement lineage.
- Scheduled jobs with durable PostgreSQL run history.
- Responsive desktop/mobile web and safe PWA shell.
- Paper execution is excluded from the public MVP. Ticket generation, review,
  activation, monitoring, and settlement analytics remain in scope. Re-enable
  paper execution only through a successor ADR after the deferred readiness
  gates pass.

### Excluded

- External/live bet placement. It remains disabled.
- Archived `betfront/` and pre-existing `frontbet/`.
- Mutating `OddsHarvester/`, `penaltyblog/`, or `soccerdata/` unless a verified
  active-platform blocker requires an explicit scoped change.
- Public production deployment before every mandatory gate is green.

## Completion contract

The program can be marked **MVP GO** only when:

1. every P0 task is complete;
2. every MVP-labelled P1 task is complete or explicitly removed from the MVP
   scope through an accepted ADR;
3. backend, frontend, migration, queue, hybrid browser, PWA, responsive,
   multi-user, failure/recovery, backup/restore, and staging gates pass;
4. the release is built from a clean, reviewed, reproducible Git revision;
5. independent code review and architecture review are clear;
6. the canonical status, Serena memory, and `bet-core` Codebase Memory index
   reflect the same verified state.

## Project status

| Project/surface | Current status | MVP role | Main gap |
| --- | --- | --- | --- |
| `frontend/` | LOCAL GATES GREEN | Current UI | protected staging plus real-device/manual zoom acceptance |
| `backend/` | LOCAL GATES GREEN | Current API | shared multi-replica edge/WS controls and production observability |
| PostgreSQL/Alembic | LOCAL GATES GREEN | Durable state | `025 (head)`, no drift; off-host recovery remains external |
| Redis/Taskiq | LOCAL GATES GREEN | Async jobs | production soak/monitoring remains external |
| `OddsHarvester/` | ACTIVE BRIDGE / EXTERNAL COVERAGE HOLD | live scraping | local bridge executed truthfully but returned `no_fixtures`; provider coverage and complete protected live lifecycle remain external |
| `penaltyblog/` | PARTIAL | prediction bridge | real staging inference is not in the current live gate |
| `soccerdata/` | LOCAL CANARY GREEN | data bridge | protected staging lifecycle remains required |
| `flumine/` | EXCLUDED | post-MVP paper execution | accepted ADR excludes paper execution from public MVP |
| PWA | LOCAL GATES GREEN | installable shell | production HTTPS offline/recovery/update suite passed; installed-device lifecycle remains |
| Mobile/desktop design | LOCAL GATES GREEN | operator UI | 320–1920 plus landscape/safe-area/touch/forced-colors browser gates passed; hardware/manual zoom remains |
| DevOps/release | PR #14 MERGED / MAIN EVIDENCE GREEN / LOCAL DIFF | deployment | main `515fcd1`: run `30151025646` passed source and build/scan/package with publication skipped; current hardening still requires reviewed commit/PR and clean evidence before exact-tag approval |
| QA | LOCAL GATES GREEN / STAGING HOLD | release evidence | real protected two-user staging lifecycle is absent |
| `betfront/` | ARCHIVED/DIRTY | none | preserve; do not include in current MVP |

Tracked submodules were clean at program start and remain unchanged. The
formerly dirty parent checkout was reconciled into clean candidate
`40352aed38f98600a621954c67c82b600faab223`, then runner-only CI findings were
remediated in local candidate `3543ebb`, without reset, clean, or history
rewrite. Follow-up `d20c583` removed two CI timing races and was published with
all five branch workflows green. PR #7 was subsequently merged into `main` as
`881a436`. PR #8 through #10 subsequently closed the Ruff install,
OddsHarvester/lineage, and vulnerable `ecdsa` dependency gates. Current remote
`main` at that checkpoint was `3930d0e`; evidence-only run `30116510025` passed source verification,
image builds, and runtime smoke, then stopped on 115 High/Critical
operating-system findings without an available fixed version. Candidate run
`30120739636` then passed source/image/runtime gates and correctly blocked 72
fixable High/Critical findings across the frontend and nginx images while
skipping publication. The follow-up upgraded those runtime dependencies and
base images; PR #11 evidence below proved the image remediation before
independent review added the strict schema hardening verified below.

PR #11 then passed Backend, Frontend, Security, and Hybrid E2E on `cc0645c`.
Evidence-only run `30123023608` passed source/build/runtime/scan/SBOM/package,
reported backend 115 unresolved High/Critical findings without a fixed version,
frontend/nginx zero, fixable zero, and skipped publication. Independent review
found a malformed-finding bypass in the otherwise-green gate. The local
follow-up validates report identity/schema and per-finding types/required
fields, with adversarial regressions. Code review is `APPROVE`, architecture is
`CLEAR`, all PR gates passed on `f897e6f`, and final evidence-only run
`30124777407` passed with the same exact finding counts and publication
skipped.

PR #11 merged as main `e2ea635`. Post-merge Backend, Frontend, and Security
passed, and main evidence-only run `30126304645` passed source verification,
all image build/runtime/scan/SBOM/package gates, and artifact upload with the
same exact finding counts and publication skipped.

## Verified refresh — 2026-07-24

| Check | Result |
| --- | --- |
| Backend Ruff / pytest | PASS; synced current tree, Ruff clean, **545 passed** |
| Alembic | **025 head**, no drift |
| Root production-contract/secret tests | **29 passed**; tracked-plus-untracked local secret scanner passed |
| Compose contracts | both config and render checks passed |
| Shell/repository checks | `bash -n` and `git diff --check` passed |
| Runtime | `/health`, frontend HTTP 200; `/ready` includes Bet Redis `6380` plus fresh worker/scheduler heartbeats; final Taskiq round-trip passed |
| Recovery/provider | runtime smoke, queued-message recovery, lost-stream outbox recovery, provider canary passed |
| Frontend | pinned `pnpm 10.34.5`; `pnpm check` 0 diagnostics; **32 files / 121 unit cases**; `check:e2e` and build passed |
| Chromium hybrid | fresh local **56/56** (3.7m, one worker), `retries=0`; PR #11 hardening head also passed the complete suite in **7m32s** |
| Published branch/main CI | PR hardening SHA `f897e6f` and docs head `5dafac8`: all PR gates PASS; merged main `e2ea635`: Backend, Frontend, Security and evidence-only run `30126304645` PASS |
| Firefox / WebKit | official smoke **1/1** on each engine; host WebKit lacked runtime libraries, so the verified WebKit run used the official Playwright `v1.60.0-noble` container |
| PWA | production HTTPS service-worker suite **3/3**, including offline/recovery announcements and draft-safe update |
| Recovery hygiene | final strict cleanup removed interrupted E2E fixtures and ended at `Namespaces: 0`; fresh temporary-DB dump/restore passed at Alembic `025` with matching schema/version/key row counts |
| Release workflow supply chain | full-SHA actions; known-safe Trivy Action `v0.35.0` + binary `v0.69.3`; real Taskiq source gate; exact scanned-image GHCR handoff; non-root image runtime smoke; merged-main run `30126304645` passed with fixable=0, frontend/nginx=0, backend=115 unresolved, three CycloneDX SBOMs, and publication skipped |
| Production dependency lock | combined backend/OddsHarvester/penaltyblog/soccerdata Python 3.12 lock, **204 exact packages**; regeneration and strict dry-run passed |
| Local production containers | remediated frontend build + UID 1001 + HTTP 200 PASS, with unused npm/Corepack tooling absent; backend 204-package build + UID 1001 + FastAPI import + bundled Chromium PASS; pinned nginx `1.30.4` build/runtime PASS and formerly fixable Alpine packages meet or exceed reported fixed versions. Explicit host-resolved mappings worked around rootless Podman container DNS |

Exact post-P1 Chromium gate:

```bash
cd frontend
pnpm exec playwright test --project=chromium-hybrid --retries=0
# 52 passed (9.3m)
pnpm exec playwright test --project=chromium-hybrid --retries=0
# 52 passed (9.4m)
pnpm exec playwright test --project=chromium-hybrid --retries=0 --workers=1
# 56 passed (10.3m), current complete suite after device/accessibility coverage
```

The independent P1 review iterated through auth/WebSocket cancellation,
identity-map, disconnect-concurrency, diagnostics, Taskiq naming, and regression
coverage findings. Its final verdict is **Critical 0 / High 0 / Medium 0 —
APPROVE**.

The final release-hardening review additionally closed image-runtime proof and
secret-scanner masking gaps. Its focused re-review is **Critical 0 / High 0 /
Medium 0 — APPROVE**. The Luna frontend/PWA/UX audit found no P0/P1 issue; its
content/localization/backtest/orientation findings were fixed and verified with
five affected Chromium flows plus the production PWA suite.

The signed-registry review then found and closed a checksum-path blocker plus a
fail-open reference preflight. Executable regression tests cover existing,
explicitly absent, and network-error registry outcomes; the independent
re-review is **Critical 0 / High 0 / Medium 0 — APPROVE**.

Local verdict: **development validation GO**. This is not a release GO because
the completion contract includes external and revision-level gates.
Release/MVP launch remains **HOLD** pending external credential rotation,
protected GitHub/GHCR configuration and one real signed tag run,
secret-manager setup, DNS/valid TLS/firewall, off-host backup/restore rehearsal,
staging lifecycle and two-user evidence, observability/on-call/soak/canary,
and protected tag container-build/publish/pull proof.

The published branch candidate is `d20c583`; preserve all existing work and do
not reset or clean it. The documentation refresh following that commit is the
only expected local delta until it is committed.

## Fresh baseline at program start

| Check | Result |
| --- | --- |
| Backend Ruff | PASS |
| Backend pytest | 477 passed |
| Frontend `pnpm check` | PASS, 0 errors/warnings |
| Frontend unit tests | 28 passed |
| Frontend E2E TypeScript check | PASS |
| Frontend production build | PASS |
| `docker-compose.yml` config | PASS |
| `docker-compose.podman.yml` config | PASS |
| `git diff --check` | PASS |
| Backend `127.0.0.1:8001` | UP; `/health` and `/ready` return 200 |
| Frontend `127.0.0.1:5175` | UP; `/about` returns 200 |
| PostgreSQL / Redis | UP and healthy on `127.0.0.1:5433` / `127.0.0.1:6380` |
| Fresh Alembic | `022 (head)` before and after `upgrade head` |
| Fresh full hybrid UI | 44 tests, Chromium, `retries=0` — running at this checkpoint |

Codebase Memory start state:

- project: `bet-core`;
- status: `ready`;
- graph: 4,944 nodes / 18,119 edges;
- change detection reports the intentional dirty checkout.

Repomix checkpoints:

- whole workspace packed as output `92adccd74cf9d894`;
- 1,102 files were inventoried;
- the 50M-token raw size is dominated by tracked OddsHarvester HAR fixtures,
  so investigation uses compressed structure plus incremental grep/read rather
  than loading the payload wholesale.
- previous focused active-platform pack: output `cf52e568d9bfd189`, 499 files,
  approximately 370K tokens; it confirmed migration `023`, cross-container
  runtime-role discovery, replay idempotency, and recursive production
  submodule checkout at that checkpoint.
- final compressed whole-workspace pack: output `59a58de9391eb430`,
  **1,153 files / 2,467,034 tokens / 138,366 lines** after excluding the
  inventoried large HAR fixtures;
- final full-content active-platform/release pack: output
  `233d99f089e79988`, **556 files / 788,286 tokens / 84,088 lines**. Targeted
  grep confirmed the Taskiq release gate, signed GHCR flow, fail-closed
  registry guard, device/accessibility coverage, and PWA recovery test.
- final post-remediation compressed whole-workspace refresh: output
  `7fb2a326972893e0`, **1,154 files / 2,470,226 tokens / 138,612 lines**,
  excluding the previously inventoried HAR/build/cache/dependency artifacts.

Final durable index checkpoint:

- Serena `core`, `mvp_readiness`, and `platform_hardening` memories are current;
  `serena memories check` passed.
- Native MCP moderate reindex after `d20c583` produced **5,248 nodes / 19,986
  edges**, status `indexed`.
- `detect_changes` continues to enumerate the intentional dirty checkout
  relative to Git `HEAD`; actual and expected graph sizes match.

## Prioritized findings

### P0 — release blockers

| ID | Task | Status | Completion evidence |
| --- | --- | --- | --- |
| SEC-001 | Revoke/rotate the tracked third-party credential and remove the literal from `.kilo/kilo.json` without recording its value | BLOCKED-EXTERNAL | provider rotation proof plus clean secret scan |
| SEC-002 | Add repository secret scanning and prevent tracked plaintext credentials | COMPLETE-local | fail-closed tracked/untracked scanner + 11 regression tests + CI workflow validation |
| SEC-003 | Fail startup outside development for default JWT, insecure cookies, and unsafe production settings | COMPLETE | secure-runtime config/cookie tests included in 477-pass backend suite |
| OPS-001 | Add a distinct production deployment contract: TLS, private DB/Redis, immutable images, no reload/source mounts/default credentials | COMPLETE-local | production Compose/render validation, pinned images, health-gated smoke |
| DB-001 | Track, review, apply, and verify migration `022`; keep duplicate execution protection in the release artifact | COMPLETE-local | `022 (head)`, no drift, migration/tests/catalog proof |
| QA-001 | Prove a real staging flow instead of only seeded predictions | PENDING-external | authenticated scrape -> dataset -> predict -> ticket -> settlement evidence |

`SEC-001` requires access to the external credential provider. Local remediation
continues in parallel, but public release remains blocked until rotation is
confirmed.

### P1 — mandatory MVP work

| ID | Area | Task | Status |
| --- | --- | --- | --- |
| SEC-004 | API | replace wildcard credentialed tunnel CORS/WS origin acceptance with explicit environment allowlists | COMPLETE |
| SEC-005 | Auth | add rate limiting/anti-abuse and audit visibility for signup/login | COMPLETE-local — bounded hashed source/identity buckets, fail-closed guard, `429`/`Retry-After`, and redacted audit events; shared edge limiting remains a scale gate |
| SEC-006 | Sessions | make logout invalidate existing access tokens and WebSockets across workers | COMPLETE-local — migration `025`, token `sv`, serialized refresh/logout, fresh handshake/command/broadcast checks |
| DB-002 | Alembic | reconcile the known legacy ORM/index drift through a reviewed non-destructive plan | COMPLETE-local — `alembic check` clean at 025 |
| DB-003 | Recovery | implement and prove backup, restore, and release rollback procedures | PARTIAL — scripts + fresh local restore drill green; rollback contract green; off-host/deployed rehearsal pending |
| JOB-001 | Taskiq | run Redis/worker integration tests for publish, consume, lease, retry, crash, and recovery | COMPLETE-local — real worker/Redis probes green; canonical names prevent absolute-path poison tasks; `XPENDING=0` |
| JOB-002 | Durability | reconcile messages marked `published` when Redis loses them before consumption | COMPLETE — stale published replay + lost-stream probe |
| JOB-003 | Idempotency | prevent a recovered scheduled run from creating a second ticket batch after a business commit | COMPLETE — stable run key + migration `023` uniqueness + replay tests |
| JOB-004 | Create idempotency | make scrape/scheduled-job POST retries safe across browser/network retries | COMPLETE — migration `024`, per-user operation/body fingerprint, `201` first create, `200` replay, `409` mismatch |
| TRD-001 | Scope | decide through ADR whether paper trading is included in MVP | COMPLETE — excluded by accepted ADR |
| TRD-002 | Flumine | make the checkout/dependency reproducible and add adapter readiness | DEFERRED post-MVP |
| TRD-003 | Accounting | settle paper balance/P&L idempotently against execution intent/order | DEFERRED post-MVP |
| TRD-004 | Concurrency | prove exactly one PostgreSQL intent/debit under concurrent requests | DEFERRED post-MVP |
| BE-001 | Jobs | validate scheduled task type/config/cron rather than silently accepting/falling back | COMPLETE — invalid legacy cron rows are quarantined individually and the batch continues |
| BE-002 | WebSocket | add backpressure/timeouts/connection limits or explicitly bound MVP capacity | COMPLETE-local — global/per-user admission, idle/message/send bounds, slow-client disconnect, session-version revocation, cross-worker revalidation, and user-scoped updates; shared pub/sub/admission remains a scale gate |
| BE-003 | Readiness | expose API, DB, Redis, worker, scheduler, bridge, and optional paper readiness truthfully | COMPLETE for MVP scope; paper excluded |
| FE-001 | Prepare | distinguish backend/catalog/job failures from truthful empty states | COMPLETE — separate catalog/job errors, honest empty states, and retry actions |
| FE-002 | Prepare | report partial multi-season job creation with created IDs and safe retry semantics | COMPLETE — successful IDs/reasons retained; only failed work retries; stable `Idempotency-Key` prevents duplicate creates; wire enums/keys remain protocol-safe |
| FE-003 | Auth UX | centralize expired-session logout/redirect and stop socket reconnect loops | COMPLETE — terminal `401` drives one teardown, owned-draft clear, socket disconnect, and login redirect |
| FE-004 | Errors | add an application-specific SvelteKit error/recovery boundary | COMPLETE — root `+error.svelte` recovery surface |
| FE-005 | Realtime | make Analyze/Tickets progress truthful through polling or scoped events | COMPLETE — existing API-backed Analyze status and Tickets/final-result polling verified; no synthetic progress |
| FE-006 | Tenant UX | scope session betslip drafts to the authenticated user and clear on logout/mismatch | COMPLETE — unit + same-tab two-user browser test |
| PWA-001 | Install | add real 192/512 PNG and maskable icons; prove HTTPS installability | COMPLETE-local — production HTTPS browser proof; manifest supports any orientation |
| PWA-002 | Offline | align offline/connectivity copy with the actual no-private-cache policy | COMPLETE — offline/recovery status is announced and the recovery copy explicitly says no action is replayed automatically |
| PWA-003 | Update | prevent service-worker activation from discarding active workflow/betslip state | COMPLETE-local — update confirmation preserves user-scoped draft |
| UX-001 | Betslip | make the drawer an accessible modal with focus trap, Escape, close action, and focus return | COMPLETE-local |
| UX-002 | Mobile | prevent FAB, sticky workflow CTA, bottom navigation, and safe area collisions | COMPLETE-local — portrait, `844x390` landscape, and simulated 34px bottom safe-area geometry pass |
| UX-003 | Navigation | provide accessible names for icon-only sidebar links | COMPLETE-local |
| UX-004 | Content | make the MVP workflow language consistent | COMPLETE — Prepare copy/statuses align with the MVP flow; odds controls have match-specific accessible names; ticket-review copy is Romanian |
| QA-002 | Tenant | add cross-user isolation gates for jobs, predictions, WS, trading, bankroll, and settlement | COMPLETE-local — REST/settlement isolation plus user-scoped prediction WebSocket tests |
| QA-003 | Browser | run all hybrid tests with retries disabled and eliminate flaky waits/cleanup ambiguity | COMPLETE-local — repeated retry-free Chromium gates |
| OPS-002 | CI/CD | build, scan, publish, deploy, smoke, and retain immutable rollback artifacts | PARTIAL / RC1 QUARANTINED — exact scanned-image handoff, GHCR digest publication, keyless Cosign, GitHub attestations, non-overwrite, version promotion, and auto-rollback are implemented and contract-tested. Tag run `30149673025` failed before image preservation/publication, so no GHCR image was published; new reviewed revision/tag and protected publication proof remain |
| OPS-006 | CI supply chain | pin and validate actions/scanners, gate release tags on application tests, scan current source and images | REMEDIATION-CI PENDING — exact main `3550b9c` passed evidence-only run `30135830444`, but protected tag run `30149673025` later blocked on two newly fixable High findings in build-only `uv`/`uvx`. Local commit `eac1ad0` removes the build tool after installation and adds absence smoke/contracts; root 29/29, backend 545/545, Ruff/actionlint/YAML/shell/secret/diff checks and derived-image runtime smoke pass. Clean rebuilt-image Trivy/SBOM evidence remains mandatory before a new tag |
| BE-004 | Container scraper runtime | make the production Chromium install available to the non-root backend runtime user | COMPLETE-CI — shared `/ms-playwright`, non-root UID, `dpkg --audit`, direct bridge imports, writable HOME, and Chromium launch passed in exact main image smoke |
| BE-005 | Production dependencies | resolve backend plus all bridge projects from one exact Python 3.12 dependency graph | COMPLETE-local — 204-package uv lock, regeneration diff and strict dry-run green |
| FE-007 | Container dependencies | pin pnpm and avoid a second mutable production dependency resolution | COMPLETE-local — `pnpm 10.34.5`, one frozen install, builder prune and copied production node_modules; SvelteKit `2.70.1`/Vite `8.1.5`; unused npm/Corepack removed from runtime; check, 121 unit tests, E2E typecheck, build, and High/Critical production dependency audit green |
| OPS-003 | Observability | health/metrics/logs/alerts for API, DB, Redis, worker, scheduler, queues, scrapers | PARTIAL — truthful readiness/heartbeats; alerts/on-call external |
| OPS-004 | Recovery | restore the recorded known-good immutable manifest automatically when deploy smoke fails | COMPLETE-local — deterministic failed-smoke contract test |
| OPS-005 | Runtime isolation | prevent Bet from silently using another project's Redis on shared development hosts | COMPLETE-local — API/worker/scheduler explicitly use `127.0.0.1:6380`; Taskiq round-trip and readiness passed |

### P2 — hardening after mandatory gates

- Split the largest backend/frontend monoliths only through regression-first
  slices.
- Add iOS install guidance and expiring install-prompt dismissal.
- Restrict service-worker cache cleanup to the application cache prefix.
- Add WebSocket pub/sub before horizontal API scaling.
- Add nested-project CI appropriate to active bridge contracts.
- Complete manual desktop 200% zoom, actual Windows High Contrast, installed
  iOS/Android PWA lifecycle, and screen-reader acceptance on target hardware.
- Add retention and artifact-storage policies for scrape payloads/logs.
- Reconcile documentation drift for submodule branches and Flumine integration.

## Execution phases

### Phase 0 — durable checkpoint and baseline

Status: **COMPLETE**

- [x] Repomix whole-workspace audit.
- [x] Six expert lanes: FE, BE, DevOps, QA, PWA, mobile/desktop design.
- [x] Create this phase/task register.
- [x] Link/update canonical current status.
- [x] Write Serena program memory and refresh `mem:core`.
- [x] Run Codebase Memory change detection and native MCP reindex; docs/Serena
      remain intentionally excluded by `.cbmignore`, graph is ready at
      final graph metrics are recorded in the canonical status after this sync.
- [x] Start PostgreSQL, Redis, backend, and frontend and capture health evidence.

Exit: documentation, Serena, Codebase Memory, Git state, and live baseline agree.

### Phase 1 — reproducible development runtime

Status: **COMPLETE locally**

- [x] Start PostgreSQL and Redis on the intended local ports.
- [x] Apply migrations and prove head `025`.
- [x] Start backend API, worker, and scheduler; trading runner excluded with paper scope.
- [x] Start frontend on `127.0.0.1:5175`.
- [x] Verify API/frontend/DB/Redis/worker/scheduler health and authenticated login.
- [x] Preserve commands/results and record every blocker in this register.

Exit: a new developer can start the stack using documented commands and obtain
truthful health/readiness without hidden local assumptions.

### Phase 2 — security and release foundation

Status: **LOCAL GATES GREEN; EXTERNAL RELEASE GATES PENDING**

- [ ] SEC-001 external provider credential rotation.
- [x] SEC-002 through SEC-005 local implementation and verification.
- [x] OPS-001 foundation, `.dockerignore`, production topology, and local
      release/rollback contracts.
- [ ] OPS-002 protected signed-registry and deployment execution evidence;
      repository workflow/contracts are implemented.
- [x] DB-001 and DB-002.
- [ ] DB-003 off-host restore rehearsal; local dump/restore and rollback
      contract validation are green.
- [x] Explicit paper-trading MVP decision ADR.

Exit: no tracked secret/default security exposure; production configuration is
fail-closed, reproducible, private, TLS-capable, migratable, and recoverable.

### Phase 3 — product correctness and UX

Status: **LOCAL MVP SCOPE GREEN; PAPER EXECUTION DEFERRED BY ADR**

- [x] FE-001 through FE-006.
- [x] BE-001 through BE-003 for the bounded single-process MVP capacity.
- [x] PWA-001 through PWA-003.
- [x] UX-001 through UX-004.
- [x] Paper execution excluded; TRD-002 through TRD-004 deferred by ADR.

Exit: core workflows are truthful, recoverable, accessible, and usable across
the supported viewport/device matrix.

### Phase 4 — adversarial QA and staging

Status: **LOCAL GATES GREEN; STAGING AND EXTERNAL RELEASE EVIDENCE PENDING**

- [x] Static/unit/build gates.
- [x] PostgreSQL migration and scheduled replay uniqueness gates.
- [x] Redis/Taskiq failure and recovery gates.
- [x] Full hybrid Chromium with `retries=0`, repeated cleanly.
- [x] Firefox/WebKit smoke.
- [x] PWA install/offline/update tests on a production build over HTTPS.
- [x] Landscape, simulated safe-area, coarse-pointer touch targets, and
      Chromium forced-colors focus resilience.
- [x] Multi-user/RBAC/ownership tests for jobs, predictions, bankroll, trading,
      settlement, WebSockets, and user-scoped drafts.
- [ ] Real staging end-to-end flow.
- [x] Local backup/restore drill and rollback contract validation.
- [ ] Off-host backup/restore and deployed rollback evidence.

Exit: two consecutive clean complete runs, no retries, skipped core flow, data
leak, duplicate financial mutation, stale queue state, or unexplained fixture.

### Phase 5 — release candidate and MVP decision

Status: **IN PROGRESS — PR #12 and exact merged-main evidence complete; first
protected tag failed closed before publication; remediation PR/CI, a new signed
publication, and external gates remain**

- [x] Clean/reconciled Git revision and pinned nested dependencies — PR #7
      merged as signed `main` commit `881a436`; tracked submodules unchanged.
- [ ] Actual protected immutable publish run with
      security/dependency/container scans, signed digests, and attestations;
      repository workflow/contracts and pre-publication merged-main evidence
      are green. Authorized RC `v0.1.0-rc.20260725.1` failed closed before
      publication on two newly fixable build-tool findings and is quarantined;
      PR #14 plus a new immutable tag must complete the contract.
- [x] Independent local code review and architecture invariant review; final
      verdict Critical 0 / High 0 / Medium 0 — APPROVE.
- [ ] Staging soak for at least 48–72 hours.
- [ ] Canary deployment and verified rollback.
- [x] Final local status/Serena/Codebase Memory synchronization.
- [x] Final current decision with evidence: local development GO, public MVP
      launch HOLD until the remaining release gates pass.

Exit: every item in the completion contract is proven.

## Verification gates

### G0 — source/security

```bash
git status --short --branch
git diff --check
git submodule status
```

Additional requirements: clean secret scan, reviewed diff, no untracked release
migration, branch reconciliation, no unauthorized nested-project changes.

### G1 — backend/frontend

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/python -m pytest -q -p no:cacheprovider

cd ../frontend
pnpm check
pnpm test:unit
pnpm check:e2e
pnpm build
```

### G2 — database

- clean PostgreSQL upgrade to head;
- upgrade from the previous real head using representative data;
- reviewed `alembic check`;
- duplicate precheck and uniqueness catalog proof;
- downgrade/re-upgrade only on a backup/restore staging copy.

### G3 — queue/failure recovery

- Redis + Taskiq worker, not only in-process mode;
- publish/consume, lost broker, retry, stale lease, worker crash/restart;
- exactly-once/idempotent terminal database state.

### G4 — browser/UI

- all hybrid specs, Chromium, `retries=0`;
- 320, 390, 768, 1024, 1440, and 1920 widths;
- keyboard-only and accessible modal behavior;
- light/dark, mobile safe area, FAB/CTA/bottom-nav geometry;
- landscape, coarse-pointer 44px targets, and forced-colors keyboard focus;
- Firefox/WebKit core smoke.

### G5 — PWA

- production build over HTTPS;
- manifest/icons/install;
- one active SW and bounded cache names;
- no API/private HTML in CacheStorage;
- offline fallback honesty;
- safe update with active workflow/betslip state;
- reconnect after network recovery and no reconnect after logout.
- visible offline/recovery announcements with explicit no-auto-replay copy.

### G6 — staging core

```text
signup/login/refresh/logout
  -> real scrape
  -> persisted dataset
  -> real prediction
  -> value eligibility
  -> ticket draft/review
  -> activation
  -> optional paper execution
  -> result refresh
  -> settlement
```

Run with at least two users and prove ownership isolation. External/live bet
placement must remain disabled.

### G7 — operations/release

- private DB/Redis, TLS, secure cookies, explicit origins;
- migration as a controlled one-off job;
- backup/restore drill with RPO/RTO evidence;
- metrics/logs/alerts and queue/scrape health;
- immutable canary deployment and tested rollback;
- protected GHCR tag publication with exact scanned-image digest continuity,
  Cosign verification, GitHub attestation verification, and overwrite refusal;
- 48–72 hour clean soak.

## Immediate execution order

1. Finish PR #14 checks and clean release evidence; merge only when Trivy
   reports zero fixable High/Critical findings and all three SBOMs are retained.
2. Rerun evidence-only verification on exact merged `main`, then create new tag
   `v0.1.0-rc.20260725.2` for
   `ghcr.io/cahangeorge/betting-platform-{api,frontend,nginx}`. Never reuse RC1.
3. Verify the protected signed release, digest continuity, attestations,
   version promotion, and overwrite refusal for all three images.
4. Execute protected staging lifecycle/two-user, off-host backup/restore,
   observability/soak/canary, secret-manager, and digest-pinned deployment
   evidence.
5. Re-evaluate the release/MVP launch HOLD verdict.

## Current blockers and unknowns

- External credential rotation requires provider access.
- The actual production infrastructure, domain, TLS terminator, secret manager,
  backup provider, and monitoring provider are not represented in the checkout.
- Legal/compliance approval for any public gambling or real-money surface is
  outside the repository and remains an external launch gate if applicable.
- Paper execution is excluded from MVP by accepted ADR
  `2026-07-23-exclude-paper-execution-from-mvp.md`.
- PR #11 merged into `main` as `e2ea635`; Backend, Frontend, Security, and
  evidence-only run `30126304645` are green.
- PR #12 merged into `main` as `3550b9c`.
- Exact-main evidence run `30135830444` passed source and image gates. Backend
  retains 38 unresolved findings (32 High / 6 Critical), all without fixed
  versions; frontend/nginx and fixable findings are zero. Three SBOMs and both
  evidence artifacts are present; publication was skipped.
- Pinned GitHub actions still declare the deprecated Node.js 20 runtime; the
  runner forced Node.js 24 and the workflow passed. Upgrade those actions in a
  future maintenance lane.
- Protected tag `v0.1.0-rc.20260725.1` exists on exact SHA `3550b9c`.
  Run `30149673025` passed source and runtime smoke but failed the fixable
  vulnerability gate on build-only `uv`/`uvx`. Scanned-image preservation and
  `publish-signed-images` were skipped; no GHCR artifact was produced by that
  run. The tag is immutable/quarantined and must not be reused.
- PR #14 carries commit `eac1ad0`, which uninstalls `uv` before runtime and
  fails the image smoke if `uv`, `uvx`, or package metadata remain. Local
  contracts, backend tests, image runtime proof, and independent review are
  green; complete clean CI/Trivy/SBOM evidence is still required.
- GitHub currently lists only collaborator `cahangeorge`; a genuinely
  independent required reviewer for `registry-release` cannot be configured
  until another trusted reviewer is added.

## Exact next step

Finish PR #14 checks, run clean release evidence on its reviewed revision,
merge it, and repeat evidence-only verification on exact merged `main`. If the
three image reports contain zero fixable High/Critical findings and all SBOMs
are retained, create new tag `v0.1.0-rc.20260725.2` for the authorized GHCR
destinations `ghcr.io/cahangeorge/betting-platform-{api,frontend,nginx}` and
verify signed digest/attestation continuity. Never reuse RC1. Keep public
MVP launch HOLD until protected publication proof and the external release
gates in the verification refresh are evidenced.
