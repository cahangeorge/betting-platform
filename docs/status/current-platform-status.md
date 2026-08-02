# Current Platform Status

Updated: 2026-08-02T08:45:51+03:00
Repository/branch: `/home/gion/Projects/bet` /
`main` at `0620287`
Git state at this handoff refresh:

```text
`main...origin/main` with 174 root worktree entries. `OddsHarvester` is the only
intentionally modified nested project and has 51 worktree entries, including
sanitized HAR fixtures. `penaltyblog` and `soccerdata` remain untouched. No
commit, push, tag, production deployment, or rollout activation was performed.
```

This is the first status document to read in a new coding session. Re-run
`git status --short --branch` before relying on this snapshot.

## 2026-08-02 authorized GitHub publication

- Published the verified nested OddsHarvester changes as
  `8f5f80b feat: harden OddsPortal catalog and browser extraction` on
  `origin/codex/football-catalog-validation-2026-07-17`.
- Published the Bet platform plus the nested revision reference as
  `0e7e1e1 feat: complete provider data platform MVP hardening` on
  `origin/main`.
- The publication was preceded by staged whitespace and credential-shaped
  value scans. No secret-shaped staged value was found; test-only execution
  tokens were reviewed as non-credentials. No tag, GitHub Release, deployment,
  live commercial-data API call, credential rotation, or rollout activation
  was performed.

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

## 2026-08-02 authorized OddsHarvester -> canonical odds live proof

- Completed the final authorized public-source stage without using Sportmonks
  or another commercial football-data API and without modifying the dirty
  nested `OddsHarvester` checkout. The exact Playwright 1223 headless-shell
  prerequisite exists and launched successfully.
- Fresh public discovery returned **1,229** football league candidates. A
  bounded three-league historic validator returned three truthful
  `unavailable` results rather than treating rendered HTTP 200 pages as scrape
  success. The first Brazil Serie A date probe also returned no records, but
  correctly reported that the rendered listing contained fixtures on August
  8-10 instead of the requested August 2.
- The corrected one-league/one-day/one-market canary used Brazil Serie A,
  `2026-08-08`, full-time 1X2, direct egress, concurrency 1, and the hybrid
  `auto` engine. Static discovery produced the typed browser handoff and
  Playwright completed **1/1** in **17.125 seconds**, with zero failures,
  partial results, or warnings. The record contained one bookmaker and three
  complete 1X2 selections.
- The live H2H URL exposed a lineage defect in the backend converter: it used
  the away-team path slug instead of the fragment event ID. The converter now
  prioritizes and validates the fragment ID, removes optional market/scope
  suffixes, and keeps legacy non-H2H path identity. A regression proves that
  two fixtures between the same teams but different fragments cannot collide
  in event or quote identity. The live record now resolves exactly to event
  `ClHgE1DU`.
- A clean temporary PostgreSQL database migrated `001 -> 043`; the real record
  crossed the provider-envelope boundary and materialized one **complete**
  canonical odds snapshot, **3** immutable quotes, and **1** legacy complete
  1X2 entry. The temporary database and role were verified absent afterward.
- An independent review caught one additional high-severity edge case before
  publication: a fragmentless H2H URL still fell back to the repeated team
  slug. The adapter now fails closed for fragmentless H2H URLs and rejects a
  disagreeing explicit `match_id`; the regression suite covers both cases.
- Fresh verification: backend OddsHarvester adapter **14 passed**; complete
  backend **907 passed, 46 skipped**; clean isolated PostgreSQL plus Alembic
  current/head/check **952 passed, 1 skipped**; correctly configured nested
  OddsHarvester non-integration suite **971 passed, 5 skipped, 1 known warning**;
  nested Ruff and whitespace checks passed. Serena reports no diagnostics for
  the corrected adapter. The `bet-core` fast index was refreshed at **6,714
  nodes / 30,248 edges**; focused Repomix evidence
  `837a8cc89ae1e569` packages the adapter, its regression, runbook, and
  checkpoint.
- Decision: **OddsHarvester extraction and canonical odds materialization GO
  locally**. A production-shaped live prediction still needs one current
  soccerdata fixture generation aligned to the exact odds target and the
  trained artifact; this smoke does not fabricate that cross-source identity.
  Protected RC and public MVP remain **HOLD**. No commercial API call,
  credential change, persistent production mutation, nested-project edit,
  commit, push, tag, deployment, or rollout activation occurred.

## 2026-08-02 authorized Understat -> penaltyblog live proof

- The operator authorized the remaining local/public-source work while
  explicitly excluding commercial football-data API platforms. The bounded
  live proof therefore used only soccerdata's Understat reader; it used no
  Sportmonks, credentialed football-data API, odds provider, or OddsHarvester
  traffic.
- Fixed two defects exposed by the authorized smoke without modifying the
  nested `soccerdata` project. Newer Understat readers bypass the common
  request method, so the backend now instruments their direct JSON API path,
  defers cookie acquisition on valid warm-cache reads, applies the configured
  per-source limiter to each actual request, and forces refresh when the
  backend-owned TTL declares a direct-API cache file stale. Understat's naive
  fixture dates are normalized explicitly to UTC at the adapter boundary.
- Final bounded live smoke: `ENG-Premier League`, season `2024`, no-store,
  five returned rows; all five contained UTC dates, goals, and xG. Telemetry
  reported exactly three actual upstream requests and zero cache hits.
  `coverage_complete=false` is expected for this deliberately five-row view.
- Full authorized extraction produced **380/380** historical match-stat rows
  with UTC dates, goals, and xG, terminal coverage, no continuation cursor,
  no-store provenance, and **3** actual Understat requests.
- A clean temporary PostgreSQL database was migrated `001 -> 043`. The 380
  rows were resolved to temporary accepted match identities, persisted as a
  terminal published `ProviderDatasetGeneration`, and trained through the real
  penaltyblog subprocess as `PoissonGoalsModel`: ingestion `completed`, **380
  records / 380 observations**, model artifact `completed`, **380 training
  rows**, artifact file present, and SHA-256 digest verified. The temporary
  database, role, and artifact root were then verified absent.
- Fresh regression evidence after the fixes: cache/UTC suite **11 passed**;
  normal backend suite **906 passed, 46 skipped**; isolated PostgreSQL
  migration/current/head/check clean and complete suite **951 passed, 1
  skipped**; scoped Ruff format/lint and root whitespace checks passed.
- Independent review initially caught the accidental application of the
  Understat naive-UTC convention to MatchHistory. That call site was restored
  to its source representation; UTC coercion is now restricted to the two
  Understat operations. The final review verdict is **APPROVE**, with no
  critical, high, or medium findings.
- Serena resolves the UTC and direct-API cache symbols and reports the modified
  cache test file clean; its bridge diagnostics still contain the known
  environment-only inability to resolve the nested soccerdata runtime. The
  final `bet-core` fast index contains **6,712 nodes / 30,222 edges** and ranks
  the new helper plus warm/stale/direct-API regressions. Focused Repomix output
  `7788aacc47ba17dd` contains **9 files / 58,628 tokens** spanning acquisition,
  canonical ingestion, model training, tests, runbook, and status evidence.
- Decision for this phase: **soccerdata extraction, canonical persistence, and
  penaltyblog training GO locally**. The separately authorized OddsHarvester
  stage is now completed in the newer checkpoint above; an aligned current
  fixture/odds target remains required for live prediction. Protected RC and
  public MVP remain **HOLD**; no persistent production data,
  commercial API call, credential change, nested-project edit, commit, push,
  tag, deployment, or rollout activation occurred.

## 2026-08-02 soccerdata -> penaltyblog operational handoff

- Closed the concrete P3-to-P4 orchestration gap without modifying the nested
  `soccerdata` or `penaltyblog` projects. Every fresh or replayed canonical
  soccerdata page now returns its exact `ProviderDatasetGeneration.id`.
- Scheduled ingestion artifacts expose
  `provider_dataset_generation_ids=[N]`. Only a terminal `completed` page with
  no continuation cursor also exposes `source_generation_id=N`, the exact
  scalar consumed by `TrainModelCommandV1`; partial pages cannot be mistaken
  for a trainable generation. A terminal empty continuation after earlier
  data-bearing pages still publishes and exposes the one verified aggregate
  generation; a wholly empty generation remains non-trainable.
- Independent review found that a fresh checkpoint could retain a generation
  later superseded by a refresh run. Replay now requires the current published
  generation for terminal checkpoints, permits a staged generation only for a
  committed nonterminal page with a continuation cursor, and always rejects a
  superseded generation. SQLite and PostgreSQL regressions cover both staged
  page replay and warm-A -> refresh-B supersession.
- Monitoring now summarizes provider dataset generations and penaltyblog model
  artifacts, making the handoff visible to operators. Unit regressions cover
  terminal/nonterminal artifact semantics, fresh/replayed generation identity,
  and the frontend summary.
- Added an offline contract regression proving that an Understat statistics
  observation using the bridge's camelCase payload projects into the current
  penaltyblog goal feature row. The contract remains honest:
  `football-goals-features/v1` uses date, teams, and goals. xG/statistics remain
  preserved in canonical observations but are not claimed as active v1 model
  features; an xG model requires a separately versioned feature/model change.
- Added `docs/runbooks/soccerdata-penaltyblog-pipeline.md` with the operational
  sequence: approved soccerdata acquisition, terminal generation evidence,
  penaltyblog training, backtest, and the explicit final odds prerequisite.
- Fresh verification:
  - focused soccerdata/model/scheduler suite: **23 passed, 55 deselected**;
  - normal backend suite from the project virtualenv: **902 passed, 46
    skipped**; the skips are the explicit isolated-PostgreSQL gates;
  - clean isolated PostgreSQL: migrations `001 -> 043`, `043 (head)`, one
    head, `alembic check` with no new operations, and the complete suite
    **947 passed, 1 skipped**;
  - isolated penaltyblog scientific runtime: **21 passed**; the real offline
    subprocess benchmark used 80 rows/four targets, made zero network calls,
    preserved exact output parity and measured **75.5%** batch-path
    improvement. The resident worker remains correctly disabled because its
    separate RSS/isolation promotion gates are not proven;
  - targeted Ruff lint and format: passed;
  - frontend `pnpm check`: **0 errors / 0 warnings**; all **34 unit test files**
    passed; production build passed;
  - root `git diff --check`: passed.
- Serena resolved the new result and scheduler artifact symbols. Its backend
  diagnostics still use an environment that cannot resolve the project
  SQLAlchemy installation, and its TypeScript/Svelte diagnostics reported a
  parser error contradicted by the fresh `svelte-check`, unit, and production
  build gates; executable project checks remain authoritative.
- Post-fix Codebase Memory fast reindex completed at **6,703 nodes / 30,208
  edges** and ranks the terminal/nonterminal generation handoff plus its
  regressions. Focused Repomix evidence `6c9ced039b32047f` contains **11 files /
  26,955 tokens** across ingestion, scheduling, model contracts, tests,
  monitoring helper, and the runbook.
- Independent final code review: **APPROVE**, with no critical, high, or medium
  findings after the staged-versus-published replay correction.
- The PostgreSQL gate used a unique temporary role and database inside the
  local healthy PostgreSQL container. Cleanup was verified after the suite:
  zero `bet_codex_%` databases and zero `bet_codex_%` roles remained.
- Current decision for this scope: **local extraction-to-training handoff GO**.
  Live provider extraction remains `APPROVAL_REQUIRED`; production-shaped
  prediction targets remain blocked until the separately authorized odds stage
  supplies exact snapshot/entry lineage. Protected RC and public MVP remain
  **HOLD**. No provider request, nested-project mutation, commit, push, tag,
  deployment, or rollout activation occurred.
- Exact next step: run one authorized, bounded soccerdata smoke through a
  terminal generation and penaltyblog train/backtest job, after source rights
  and execution approval exist; then finish the odds acquisition/scraping
  stage and bind forecasts to exact odds lineage.

## 2026-08-02 PDP-104 prediction-bridge policy remediation

- Extended the explicit provider operation map for the three local
  `penaltyblog` operations still used by the active prediction engine:
  `calculate_implied`, `dixon_coles_weights` and `model_fit_predict`.
- Every corresponding prediction path now calls the registry with the exact
  `(penaltyblog, local-model, operation, production)` identity before crossing
  the subprocess boundary. Policy/capability failures are not converted into
  model fallbacks, so the new boundary remains fail-closed.
- Independent review found that the per-target broad exception could absorb a
  `model_fit_predict` policy denial. The gate now executes once at run scope,
  before workers are created, and a regression proves denial propagation with
  zero subprocess calls.
- Regression evidence: targeted provider/strategy suite **62 passed**; full
  normal backend suite **898 passed, 46 skipped**; complete Ruff lint and
  format check passed for **260 files**; scoped and root whitespace checks
  passed. Serena reported no diagnostics for the registry; its backend LSP
  environment still reports pre-existing unresolved virtualenv imports and
  pre-existing typing findings in the prediction/test files, while executable
  Ruff and pytest gates are green.
- Post-change Codebase Memory fast reindex completed at **6,698 nodes / 30,155
  edges** and resolves the authorization helper with three runtime callers plus
  its regression tests. Focused Repomix evidence `0cb80e0ebf7d31b2` contains
  the four changed code/test files (20,184 tokens).
- `PDP-104` remains open rather than overstated as complete: this slice closes
  the active legacy prediction-engine calls, while OddsHarvester/browser and
  non-egress catalog/runtime bridge boundaries still require separately scoped
  policy decisions. No provider traffic or nested-project mutation occurred.
- Current decision remains **local implementation GO**, **protected RC HOLD**
  and **public MVP HOLD**. The external and exact-revision gates listed below
  are unchanged.

## 2026-08-02 multi-source MVP audit and fresh local verification

- Reconciled the current checkout against fresh Git/source, the canonical
  status/program/ADRs, Serena memories `core`, `mvp_readiness`,
  `platform_hardening` and `provider_data_architecture`, Codex Memory, the
  current `bet-core` Codebase Memory graph, and a new focused Repomix pack.
  Fresh checkout and verification remain authoritative: the older Serena
  `core`/`mvp_readiness` snapshots still describe the July 24 Alembic-025
  release candidate, while `provider_data_architecture` and current source
  reflect the later G001-G009 work.
- Codebase Memory currently resolves the new provider-data implementation and
  tests in `bet-core` (the audit snapshot had 6,695 nodes / 30,082 edges
  overall; 4,045 backend nodes
  and 1,400 frontend nodes in the queried scopes). The focused compressed
  Repomix output `497ed5207b1324dc` contains 441 active-platform, migration,
  test, status and release-contract files / 468,446 tokens; nested projects,
  dependencies, caches, builds, HARs and databases were excluded.
- Fresh local verification on the current dirty candidate:
  - backend normal suite: **893 passed, 46 skipped**; the skips are the explicit
    isolated-PostgreSQL gates;
  - automatically created and removed isolated PostgreSQL database: clean
    Alembic `001 -> 043`, `043 (head)`, `alembic check` reported no operations,
    and the complete suite passed **938 passed, 1 skipped**;
  - backend Ruff lint and format: passed; **216 files** already formatted;
  - frontend `pnpm check`: **0 errors / 0 warnings**; unit: **125 passed**;
    E2E TypeScript and production build: passed;
  - Chromium hybrid: **60/60 passed** against the real local FastAPI/PostgreSQL
    backend in 4.1 minutes; production HTTPS PWA: **3/3 passed**;
  - Firefox smoke: **1/1 passed** after installing the matching Playwright
    browser. Host WebKit still lacks three shared libraries, so the same smoke
    ran in the already-present official Playwright `v1.60.0-noble` image and
    passed **1/1**;
  - root production/security contracts: **35/35 passed**; the development,
    Podman-development and production Compose manifests all rendered through
    the installed Podman Compose provider; root `git diff --check` passed.
- No new local implementation defect was confirmed. Provider-data architecture
  remains locally implemented through G009/P8. `PDP-004` is now backed by this
  reproducible no-live-call baseline. `PDP-005`, `PDP-505/505A`, `PDP-603`,
  `PDP-605`, `SEC-001`, `QA-001`, `DB-003`, `OPS-002`, `OPS-003` and `OPS-006`
  remain open because they require exact benchmark/rightsholder decisions,
  authorized provider traffic, protected infrastructure, off-host recovery,
  production-duration soak or release evidence rather than another local code
  patch.
- Fresh read-only GitHub evidence: remote `main` is the same verified commit
  `0620287`; Backend, Frontend, Security and evidence-only Release Build and
  Evidence run `30475963019` are green on that commit; there are no open PRs.
  Those runs predate all 171 current worktree entries, so they do not validate
  the provider-data candidate. The only remote tag remains quarantined
  `v0.1.0-rc.20260725.1`; no GitHub release is published.
- Release decision: **local implementation and verification GO**;
  **protected release candidate HOLD** because the candidate has 171 root
  worktree entries plus 51 intentional `OddsHarvester` entries and is not a
  clean reviewed revision; **public MVP launch HOLD** behind the external gates
  above and explicit tag/publish/rollout authorization. No provider call,
  commit, push, tag, deployment or rollout activation was performed.
- Exact next step: reconcile the current dirty candidate into intentional,
  reviewable commits/PRs without resetting user work or mutating the nested
  project further, then run protected exact-revision CI and evidence-only
  release. Provider canary/promotion and public publication remain separate,
  explicitly authorized steps after rights, credentials, staging, restore,
  observability/on-call and soak evidence exist.

## 2026-08-01 G009/P8 local architecture completion checkpoint

- Closed the final G008 review blocker in the soccerdata replay path. A replay
  miss now closes only the read transaction opened by its own checkpoint
  `SELECT` before external acquisition. If a transaction already belonged to
  the caller, implicit acquisition fails closed before the bridge and neither
  commits nor rolls back caller work; callers must finish that unit of work or
  use the explicit fetch-then-persist split.
- The scheduled runner keeps the production path explicit: authorize and
  replay, end the replay-only transaction, acquire outside PostgreSQL, persist
  under the execution fence, and commit every staged page before following its
  cursor. Terminal publication still requires the exact continuous generation
  page set and remains atomic.
- Fresh post-repair evidence:
  - focused soccerdata/PostgreSQL/scheduler gate: **71 passed**;
  - full backend with PostgreSQL: **938 passed, 1 skipped**;
  - full backend Ruff lint/format: passed;
  - Alembic: `043 (head)`, one head and no new upgrade operations;
  - root production/security contracts: **35 passed**; root and scoped
    `git diff --check`: passed;
  - frontend `pnpm check`: 0 errors/0 warnings; unit: **125 passed**; production
    build passed. The unchanged browser baseline remains hybrid **60/60** and
    production PWA **3/3** from the immediately preceding G007 gate.
- Scheduler checkpoint replay now uses a dedicated short-lived SQLAlchemy
  session. Its rollback cannot expire the long-lived worker's `run`/`job` ORM
  identities; a real PostgreSQL `execute_scheduled_job_run` regression covers
  initial and continuation misses and guards against `MissingGreenlet`.
- The mandatory bounded AI-slop pass was a documented no-op: no masking
  fallback, dead path, duplicate boundary or cleanup-only production edit was
  justified after the ownership repair. Independent final code and
  architecture verdicts are attached to the G009 Ultragoal quality gate.
- Local provider-data architecture is implemented through P8, but this is not
  protected-release or public-rollout authorization. `PDP-603`, `PDP-605`,
  live canary/promotion, provider rights/credentials, `SEC-001`, `QA-001`,
  `DB-003`, `OPS-002`, `OPS-003`, `OPS-006`, signed immutable images,
  protected CI and explicit rollout approval remain **HOLD**.
- Scope is 171 root worktree entries; pre-existing OddsHarvester has 51;
  penaltyblog and soccerdata remain clean. No nested-project edit, live provider
  request, commit, push, tag, deployment or rollout activation occurred.
- Exact next step: obtain protected-environment evidence for the open HOLD
  gates; do not activate provider traffic or publish until separately
  authorized.

## 2026-08-01 G007/P6-P7 provider operations and UI checkpoint

- Added admin-only `GET /api/v1/provider/runtime` and the provider-agnostic
  Monitoring panel for source coverage/freshness/cache/circuit/quota state,
  worker-lane pressure, stable redacted alerts and backfill/normalize/features/
  model progress. Regular users make zero runtime requests and see no operator
  panel.
- Observation coverage is capability-aware: complete odds snapshots and linked
  non-odds datasets count as mapped evidence. Recent observation/checkpoint/run
  reads are bounded; eligible phase work is SQL-filtered before independent
  active/terminal limits so unrelated history cannot crowd it out.
- Cache semantics distinguish hit/miss/mixed/not-applicable/unknown;
  `revalidated` is mixed. A source without persisted runtime evidence is
  `unknown`, never fabricated as healthy. Quota remaining zero, circuit,
  failures, freshness and partial coverage emit stable safe alert codes.
- Migration `043` adds concurrent recent-observability indexes. The operator
  runbook documents disable/drain, failover, replay, lease recovery, bounded
  local repetition and the separate production-soak requirement.
- Fresh G007 evidence:
  - backend API/PostgreSQL focused gate: **15 passed**;
  - full backend suite with PostgreSQL: **934 passed, 1 skipped**;
  - Ruff lint/format: passed; Alembic: `043 (head)`, one head, no new upgrade
    operations;
  - frontend `pnpm check`: 0 errors/0 warnings; unit: **125 passed**;
    E2E TypeScript and production build: passed;
  - full Chromium hybrid suite: **60/60 passed**; production PWA: **3/3
    passed** after explicitly starting the required local backend;
  - bounded lease/recovery repetition: **530/530 passed** across ten
    consecutive runs.
- Independent G007 re-review: **APPROVE** after phase-sample crowd-out,
  revalidation semantics, admin gating and unknown-runtime regressions were
  closed.
- `PDP-603` remains open only for protected-environment trace export and
  production dashboard/retention proof; `PDP-605` remains open for a
  production-duration soak with a real worker restart. Live-authorized E2E,
  provider canary/promotion, commercial rights, credentials and all
  protected/public release gates remain **HOLD**. No live
  provider request, deployment, commit, push, tag or rollout activation was
  performed.
- Scope: 168 root worktree entries; pre-existing OddsHarvester has 51;
  penaltyblog and soccerdata remain clean.
- Exact next step: checkpoint G007, then execute G008 final cleanup,
  architecture-invariant audit, independent code/architecture review and
  durable Serena/Codex/Codebase Memory handoff without publication.

## 2026-08-01 G006/P5 licensed odds foundation checkpoint

- Added the provider-agnostic `odds-observation/v1` row-per-selection contract,
  exact-decimal generic quote persistence and strict provider envelope support.
  Legacy `OddsEntry` is produced only as a complete mapped 1X2 projection.
- Implemented disabled-by-default Sportmonks v3 normalization/acquisition and a
  pure OddsHarvester/OddsPortal converter into the same contract. No nested
  project was modified and no provider/browser call was made.
- Added migrations `039`-`041` for generic odds lineage/runtime state and `042`
  for durable quota reservations. Admission is committed before egress, HTTP
  holds no database row lock/transaction, reconciliation is exact and short,
  and expired unknown outcomes are charged conservatively as `uncertain`.
  Duplicate acquisition identities perform zero second egress.
  Accepted observations commit before terminal quota reconciliation and replay
  by ID after a reconciliation failure. Query authentication is attached below
  ordinary httpx logging; an authorized caplog regression proves the sentinel
  token is absent from logs and safe exceptions.
- Added immutable `licensed-odds-job/v1` scheduled execution on the
  `provider-http` lane, anti-tamper digest, stable per-run 10/25/50/100 canary cohorts,
  pre-admission exclusion, task-run fence and explicit denied/failed/partial
  outcomes. It cannot fall through to the legacy OddsHarvester router.
- Fallback remains a separately authorized, bounded `provider-browser` request
  only for approved transient/quota reasons. Policy, rights, credential and
  schema failures never fall back automatically.
- Added offline provider-shaped parity/statistics benchmark. It proves common
  converter shape, exact fixture price parity and deterministic cohorts, but
  explicitly reports `promotion_proof=false`: three quote identities cannot
  satisfy the formal 99% Wilson lower-bound gate, and live non-inferiority/p95
  evidence is absent.
- Fresh G006 verification:
  - full backend suite with local PostgreSQL: **923 passed, 1 skipped**;
  - focused PostgreSQL-integrated suite: **201 passed**;
  - scheduled/canary focused suite after final routing fixes: **78 passed**;
  - Ruff lint and format over `app`, `tests`, `scripts`: passed;
  - `alembic current`, `heads`, `check`: `042 (head)`, one head, no new upgrade
    operations;
  - root `git diff --check`: passed.
- Independent G006 scraper/security re-review: **ACCEPTED WITH HOLD** after
  durable observation replay, token-log redaction, bounded streaming, truthful
  HTTP 429 taxonomy and per-run canary fixes; its final focused gate passed
  **81 tests**, including PostgreSQL replay/concurrency, plus Ruff/format.
- Commercial rights, retention/model-use/display permission, credentials,
  authentication confirmation, exact purchased quota shape and live calls
  remain unapproved. The current acquisition path refuses day-based policies
  and models only its declared RPM cap; it must not approximate a future
  per-entity/hour entitlement. Therefore
  `PDP-505`/`PDP-505A`, provider promotion and public MVP/release remain
  **HOLD**. The code foundation is complete without activating a provider.
- Scope: no commit, push, tag, deployment, production database change, live
  request, credential use or rollout activation. Root currently has 161
  worktree entries, including the already-started G007 frontend monitoring lane;
  pre-existing OddsHarvester has 51, while penaltyblog and soccerdata are clean.
- Exact next step: checkpoint G006, then complete G007/P6-P7 backend
  observability, operator UI and hybrid end-to-end evidence.

## 2026-08-01 G005/P4 governed penaltyblog model pipeline checkpoint

- Added strict, content-addressed feature, training, model and prediction
  artifact contracts over canonical published provider generations. Train,
  backtest and predict are separate immutable `model-cpu` jobs with exact
  model/config/runtime/data fingerprints, point-in-time cutoffs and bounded
  artifact loading. The penaltyblog nested project remains read-only.
- Prediction uses the backend execution time as the effective forecast time and
  binds every output to the exact provider observation, fixture, odds snapshot,
  odds entry and model artifact. Backtest reuses the pinned trained artifact,
  rejects future/result chronology leakage and persists Brier, log loss,
  accuracy, ECE, resolved-quality rate and coverage.
- Governed ticket use is fail-closed: only completed, fully certified runs with
  complete output fingerprints are eligible. Pinned home/away, kickoff and
  provider competition identity drive scan, activation, refresh and portfolio
  exposure even if mutable Match fields change. Active P4 exposure recomputes
  exact output integrity once per source run before using that fixture.
- Migrations `035`-`036` add the artifact pipeline, exact
  `PredictionRun.model_artifact_id` and append-only terminal artifacts.
  Migration `037` blocks deletion of governed runs retained by ticket lineage;
  `038` adds a concurrently built child index and `ON DELETE RESTRICT` FK that
  closes concurrent insert/delete races. The FK intentionally remains `NOT
  VALID` because one pre-existing local legacy snapshot is orphaned; it still
  enforces new references and parent deletions. The orphan remains an explicit
  reconciliation item rather than having lineage invented or deleted.
- Offline real-host benchmark over 80 generated rows and four targets:
  `3.9994s` four-refit baseline, `1.0772s` serialized training, `1.0114s`
  single-load batch prediction, exact 1X2 parity, zero network calls and 74.7%
  prediction-path reduction. A resident worker remains disabled because RSS
  and isolation promotion gates were not demonstrated.
- Fresh verification:
  - clean temporary PostgreSQL migration `001 -> 038`, `038 (head)` and
    `alembic check` with no new operations;
  - full backend suite with local PostgreSQL: **851 passed, 1 skipped**;
  - focused PostgreSQL artifact/deletion-lineage/race gates: **10 passed**;
  - isolated real penaltyblog runtime: **14 passed**; benchmark contracts:
    **7 passed**;
  - production contracts: **16 passed**; Docker, Podman and production Compose
    rendering: passed;
  - full Ruff lint/format and root diff check: passed.
- Independent final verification: **PASS**. Independent final code review:
  **APPROVE**, after pinned competition, active-run tamper detection and the
  ticket-lineage deletion race were closed with regressions.
- Scope: no nested-project mutation, live provider request, dependency install,
  commit, push, tag, deployment, production database change or rollout
  activation. Root has 132 worktree entries; the pre-existing OddsHarvester
  checkout has 51, while penaltyblog and soccerdata remain clean.
- Exact next step: checkpoint G005 and start G006/P5 common odds contract,
  official Sportmonks versus The Odds API evaluation and a secret-safe
  read-only adapter without live provider calls or canary activation absent
  credentials and source approval. Public MVP/release remains **HOLD**.

## 2026-08-01 G004/P3 checkpointed soccerdata ingestion checkpoint

- Implemented the approved primary non-odds operations: MatchHistory historical
  results, ESPN incremental schedules, Understat schedule/team statistics and
  FBref schedule/team statistics. Penaltyblog scraper overlap remains unmapped;
  its accepted route is still the local modeling operation only.
- Added immutable `soccerdata-ingestion/v1` JobSpecs with source/lane,
  backfill/incremental mode, cache mode, TTL, record/payload/chunk bounds,
  page/start cursor, stable request/group digests and exact scheduler snapshots.
  Public scheduled jobs must start at page zero; derived cursors are monotonic.
- Added migration `034`: page-scoped durable ingestion checkpoints plus nullable
  canonical dataset lineage/freshness/group metadata plus explicit generation
  heads and generation-page memberships. Content identity is independent from
  snapshot membership, so identical or reverted content is reused safely. Page
  work is committed independently and made visible only when the terminal page
  proves the exact membership set from one upstream artifact generation. New
  generations atomically supersede the former head. Page-zero `no_data`
  publishes an explicit empty generation head without inventing an empty
  dataset; a terminal empty page after earlier data retains the data-producing
  completed result.
- Scheduler execution authorizes every page before external work, closes the
  worker transaction during bridge acquisition, heartbeats the lease, persists
  under execution-token fences and commits each page. A retry replays a fresh
  committed page and continues at N+1; real bridge timeout/transport failures
  enter the bounded durable retry taxonomy.
- Backend-owned cache handling now measures actual hits/upstream requests,
  enforces TTL and refresh/no-store behavior, fingerprints no-store results
  rather than stale files, rejects expired/future attestations, and separates
  acquisition telemetry from stable `source_id + payload` content identity.
  Same-content revalidation advances downstream freshness without duplicate
  observations.
- The complete unpaged upstream artifact is fingerprinted before slicing;
  continuations carry that internal generation and fail closed if it changes.
  Dataset-key and group locks make concurrent warm/refresh insertion idempotent
  and prevent historical pages from satisfying a new publication.
- Source RPM is enforced for actual upstream `reader.get` calls by a persistent
  source-scoped `fcntl` ledger in shared `SOCCERDATA_DIR`; valid warm-cache hits
  bypass quota. This is a single-host/shared-cache contract. Multi-host
  production requires a shared limiter/provider gateway before provider
  approval.
- Both development Compose variants now configure and mount soccerdata for the
  `provider-http` and `provider-browser` workers, matching the lane routing for
  FBref. A regression contract covers both workers; the immutable production
  image already contains soccerdata.
- Fresh verification on an automatically removed isolated PostgreSQL role and
  database:
  - clean Alembic `001 -> 034`, `034 (head)`, and `alembic check` with no new
    operations;
  - complete backend suite with every PostgreSQL gate enabled: **787 passed**;
  - dedicated G004 PostgreSQL concurrency, cross-cache idempotency,
    stale-fence resume, generation isolation/supersession and staged-page
    replay/publication and identical/reverted/empty lifecycle gates: **6
    passed**;
  - focused G004/cache/scheduler gate: **46 passed**;
  - targeted Ruff format/lint and root diff check: passed.
  - production contracts: **14 passed**; Docker and Podman Compose rendering:
    passed after the browser-worker wiring repair.
- Durable architecture decision:
  [`docs/adr/2026-08-01-soccerdata-checkpointed-ingestion.md`](../adr/2026-08-01-soccerdata-checkpointed-ingestion.md).
  Default upstream descriptors remain `APPROVAL_REQUIRED`; no live provider
  call, source approval, nested-project mutation, deployment or rollout was
  performed.
- Independent final architecture re-review: **CLEAR** after content identity
  was separated from generation membership and the identical/reverted/empty
  lifecycle regressions passed.
- Root has 100 worktree entries; the pre-existing OddsHarvester checkout has
  51, while penaltyblog and soccerdata remain clean.
- Exact next step: checkpoint G004 and start G005/P4 versioned penaltyblog
  feature/model artifacts, reproducible train/backtest/predict separation and
  throughput evidence over canonical datasets. Public MVP/release remains
  **HOLD** behind provider rights, protected release, staging and P6 gates.

## 2026-08-01 G003/P2.5 worker-isolation checkpoint

- Implemented migration `033` and four backend-owned lanes: `control`,
  `provider-http`, `provider-browser` and `model-cpu`. Redis/Taskiq receives
  only the durable `run_id`; PostgreSQL owns lane/version, outbox delivery
  generation, bounded retry, leases and execution-token fencing.
- Preserved `control/legacy-control/v0` for pre-033 rows and the undecomposed
  World Cup pipeline. New v1 work uses explicit operation contracts and cannot
  be silently rerouted to control or another lane.
- Added lane-specific configurable backlog caps under PostgreSQL advisory
  transaction locks, bounded concurrency/prefetch/timeouts and distinct
  Compose resource/PID/egress boundaries. A real PostgreSQL gate admits exactly
  one of two concurrent browser runs at cap while control remains independent.
- Separated consumer enablement from new-work admission. A provider lane can
  reject new work while its publisher, lease recovery and dedicated consumer
  drain the original v1 queue. Production defaults remain control-only;
  provider pools are opt-in, and immutable restore starts only enabled pools.
- Retryable timeout/transport/provider/resource failures reuse one run/outbox,
  increment execution attempt and outbox generation, respect durable backoff,
  rotate the fencing token and terminalize at the lane limit. Scrape business
  persistence and terminal run state commit in one fenced transaction; no
  exactly-once promise is made for external provider/browser effects.
- Retry, lease recovery, reconciliation and publication now share the canonical
  PostgreSQL lock order `task_outbox -> scheduled_job_runs`. The two-transaction
  regression holds the outbox row, updates the run and releases both while a
  retry waits, proving the former inverse-order deadlock is closed. Both
  scheduled and direct scrape execution apply retry before any separate run
  fence lock; the non-retry/success branch retains the explicit fence check.
- Added baseline lane snapshots and stable alert evaluation for queue age,
  retries, fallback, freshness and resource thresholds. Workers record genuine
  cgroup-v2 `memory.peak`/`pids.peak` only when exposed; notification delivery
  and production dashboards remain P6 operational gates.
- Fresh verification:
  - complete backend with PostgreSQL gates: **737 passed**;
  - dedicated G003 PostgreSQL retry/fence, lock-order and concurrent-cap gates:
    **3 passed**;
  - real Redis/Taskiq delayed-browser versus control HOL probe: passed;
  - Alembic: **033 (head)** and `alembic check` found no operations;
  - Ruff lint/format, production contracts (**14 passed**), release shell syntax,
    root diff check and development/Podman Compose rendering: passed.
- Independent architecture re-review: **CLEAR**. The previous retry,
  admission/drain, rollback, resource-metric and acceptance-harness blockers
  are closed. Production drain automation, alert delivery and dashboards remain
  explicitly deferred to P6 and do not authorize rollout.
- Independent final code review after the lock-order regression: **APPROVE**.
- Independent completion verification after the scheduled-scrape ordering fix:
  **PASS**, with no blocking gap.
- Serena provider architecture memory was refreshed and checked; the `bet-core`
  Codebase Memory index was refreshed to **5,838 nodes / 23,927 edges** and is
  ready. Git-relative change detection correctly remains dirty.
- Scope: no nested-project mutation, live provider request, dependency install,
  commit, push, tag, deployment, production database change or rollout
  activation. Root has 89 worktree entries; the pre-existing `OddsHarvester`
  has 51, while `penaltyblog` and `soccerdata` remain clean.
- Exact next step: checkpoint G003 and start G004/P3 soccerdata ingestion with
  approved-source/cache/freshness contracts.
  Public MVP/release remains **HOLD** behind protected-release, provider-rights,
  staging and P6 operational gates.

The completed owner-safe path from the former dirty checkout to the clean
candidate is recorded
in
[`docs/status/release-candidate-reconciliation.md`](release-candidate-reconciliation.md).

## 2026-08-01 G002/P2 provider identity and observation checkpoint

- Accepted the provider-scoped identity/observation ADR and implemented
  revisions `030`-`032`: immutable validated observations, occurrence
  receipts, conflict/quarantine/dataset lineage, canonical Team/Competition,
  temporal provider mappings, typed candidates and nullable Match identity
  FKs. Existing Match text fields and reads remain unchanged.
- Accepted persistence now resolves the trusted `(adapter_key, source_key)`
  from the provider registry, including v1 adapter matching. Unsupported,
  invalid or sensitive accepted envelopes become digest-only, reason-coded
  quarantine records. Production body retention remains fail-closed until the
  trusted source descriptor declares an approved period.
- Identity transitions use advisory locks, exact predecessor checks,
  canonical decision digests, non-overlapping temporal intervals and a
  composite `RESTRICT` FK binding selected candidate, predecessor and target.
  A deterministic `exact-singleton/v1` resolver and stable open-review queue
  leave ambiguous candidate sets pending.
- E2E cleanup discovers provider lineage, blocks external receipts/links and
  external conflict counterparts, and uses one documented cleanup-only
  selected-candidate nulling exception before deleting the complete E2E
  candidate/history cycle.
- Local revision-029 preflight: 7,463 Match rows,
  `pg_total_relation_size(matches)=2,162,688` bytes, zero duplicate legacy
  source tuples resolving to multiple Matches; migration lock budget 2s/10s.
- Fresh isolated PostgreSQL evidence:
  - clean `001 -> 032` and separate `029 -> 032`: passed;
  - `alembic current`: `032 (head)`; `alembic check`: no operations;
  - actual invalid same-name index recovery: all three indexes ended
    `indisvalid=true`;
  - offline SQL: three concurrent indexes and three FK validations;
  - real concurrency/retention/RESTRICT/cleanup/resolver-race suite:
    **14 passed**;
  - previous committed backend image unlinked Match create/read/update/delete
    smoke on expanded schema: passed.
- Fresh backend/static evidence: complete suite with PostgreSQL gates enabled
  **693 passed**; normal suite is expected to skip the 14 isolated PostgreSQL
  gates; Ruff lint and targeted
  format checks passed; root `git diff --check` passed.
- `PDP-203`, `PDP-204` and `PDP-205` are implemented. `PDP-206` remains open:
  no legacy lineage was invented or backfilled without demonstrable provider
  identity and a canonical envelope/digest.
- Independent final gates: acceptance **PASS**, architecture **CLEAR**, code
  review **APPROVE**. Review fixes closed the composite-FK NULL bypass, unified
  advisory-to-row lock ordering for resolver/manual decisions, revalidated the
  exact singleton under lock, and stopped masking unrelated integrity errors.
- Scope: no nested-project mutation, live provider request, dependency install,
  commit, push, tag, deployment, production database change or rollout
  activation. Root has 66 worktree entries; pre-existing `OddsHarvester` has
  51, while `penaltyblog` and `soccerdata` remain clean.
- Exact next step after independent G002 acceptance: checkpoint G002 and start
  G003/P2.5 worker isolation. Public MVP/release remains **HOLD** behind the
  protected-release, provider-rights, staging and operational gates.

## 2026-08-01 G001/P1 provider-policy implementation checkpoint

- Completed Ultragoal `G001-p1-provider-policy-implement-adapter` and plan
  tasks `PDP-100`, `PDP-100A`, `PDP-101`, `PDP-102`, `PDP-103`, `PDP-105`,
  `PDP-106` and `PDP-107`. `PDP-104` remains intentionally incremental for
  later provider lanes.
- Added explicit adapter/source capability, production, quota and freshness
  contracts. The exact `(penaltyblog, local-model, goal_expectancy)` canary is
  policy-gated before runtime validation or subprocess work; the existing
  bridge payload and output contract are unchanged.
- Provider decisions now emit structured redacted allow/reject events with
  safe adapter/source/context, outcome, reason code and trusted operation
  identity. Unknown identifiers are not echoed into logs or exceptions, and
  the compatibility `allow_unapproved` keyword has no bypass effect.
- Provider Envelope v2 separates `envelope_version` from payload
  `schema_version`, adds adapter/source/runtime/job/run/correlation identity,
  immutable freshness and allowlisted provenance, and preserves v1 payload
  schema/digest compatibility.
- Unsupported or invalid envelopes enter deterministic, fully redacted
  quarantine before version-specific normalization. Regression coverage
  includes invalid/naive timestamps, NaN/Inf, cycles, unordered values,
  non-string/custom-key collisions, provenance auth-state rejection and real
  metadata immutability.
- Fresh local evidence:
  - provider/bridge target: **68 passed**;
  - complete backend suite: **647 passed**;
  - `backend/.venv/bin/ruff check app tests alembic`: passed;
  - targeted `ruff format --check`: passed;
  - root `git diff --check`: passed;
  - independent acceptance verifier: **PASS**;
  - independent code review: **APPROVE**, zero material findings.
- Scope remained bounded: no G001 migration, API route, dependency, live
  provider request, nested-project mutation, commit, push, tag, deployment or
  rollout activation.
- Fresh dirty-state audit: **50** root worktree entries and **51** existing
  `OddsHarvester` entries; `penaltyblog` and `soccerdata` remain clean.
- Exact next implementation step: G002/P2 must first accept a separate
  provider-scoped identity/schema ADR, then add only an expand-only migration
  plus replay/idempotency tests. Public MVP/release remains **HOLD** behind the
  existing protected-release, provider-rights, staging and operational gates.

## 2026-08-01 provider data architecture and execution-plan checkpoint

- Completed a fresh read-only study of the active SvelteKit/FastAPI platform,
  bridge surfaces, provider registry, Taskiq/PostgreSQL boundaries and the
  three nested OSS projects. Three specialist discovery lanes mapped backend
  integration, requirements/gates and scraper/model performance/rights risks.
- Accepted the architecture in
  [`2026-08-01-provider-data-platform-architecture.md`](../adr/2026-08-01-provider-data-platform-architecture.md):
  backend/PostgreSQL retain domain ownership; `soccerdata` is the primary
  non-odds ingestion adapter, `penaltyblog` is the model/feature engine,
  licensed APIs are preferred for production odds, and `OddsHarvester` remains
  a bounded odds fallback.
- The design separates `adapter_key` from the actual upstream `source_key`,
  requires Provider Envelope v2 compatibility/quarantine, makes multi-source
  identity an ADR/migration gate and introduces backend-owned HTTP/browser/model
  worker pools before ingest/canary workloads.
- The approved execution register is
  [`2026-08-01-provider-data-platform-execution-plan.md`](../plans/2026-08-01-provider-data-platform-execution-plan.md).
  It includes P0-P8, an explicit dependency DAG, ownership, rollback, named
  verification harnesses and a pre-registered cold/warm statistical benchmark.
- Sequential expert gates: architect verdict **REVISE**; all five findings were
  incorporated. Critic verdict **REVISE**; the DAG, exact slice, v2 gate and
  executable evidence protocol were strengthened. Final critic re-review:
  **APPROVE**, no remaining blocker.
- No runtime/source implementation, migration, nested-project edit, live
  provider call, commit, push, tag, deployment or rollout activation was
  performed in this planning checkpoint.
- Final dirty-state audit: **47** root worktree entries and **51**
  `OddsHarvester` entries; `penaltyblog` and `soccerdata` remain clean.
- Fresh verification: provider registry **13 passed**; Alembic reports
  **029 (head)**; targeted Ruff passed; root `git diff --check` passed; and
  `serena memories check` reported no referential-integrity issue.
- Exact first implementation slice: `PDP-100 + PDP-100A + PDP-101 + PDP-102`
  for `provider_canary.verify_provider_runtime` -> penaltyblog
  `goal_expectancy`, `(adapter_key=penaltyblog, source_key=local-model)`,
  capability `predictions`, execution context `canary`, allowed/no-bypass,
  unchanged bridge payload and output.
- Public MVP status remains **HOLD** behind the existing protected release,
  provider-rights, staging, backup/restore, observability and explicit rollout
  authorization gates.

## 2026-08-01 Provider Adapter v1 foundation checkpoint

- Added an immutable backend-owned provider boundary in
  `backend/app/providers/` without changing an existing bridge, API route,
  database model, migration, dependency, or nested project.
- The registry describes the current integration roles and capabilities for
  `OddsHarvester`, `soccerdata`, `penaltyblog`, and `flumine`. Production access
  fails closed for unapproved scraping/data sources and for the execution
  adapter excluded from the public MVP.
- Provider records can now be represented as canonical JSON envelopes with a
  stable source ID, timezone-aware observation time, schema version, and
  deterministic SHA-256 digest. Persistence and provider-scoped identity remain
  explicit follow-up work rather than an unreviewed migration in this slice.
- Accepted ADR
  [`2026-08-01-provider-adapter-v1.md`](../adr/2026-08-01-provider-adapter-v1.md)
  records why the nested projects remain isolated adapters instead of being
  merged into the API interpreter or prematurely split into microservices.
- Fresh verification:
  - `backend/.venv/bin/pytest -q tests/test_provider_registry.py`: **13 passed**;
  - `backend/.venv/bin/pytest -q`: **598 passed**;
  - `backend/.venv/bin/ruff check app tests alembic`: passed;
  - root `git diff --check`: passed.
- Fresh dirty-state audit: **42** root worktree entries and **51**
  `OddsHarvester` entries; `penaltyblog` and `soccerdata` remain clean. No
  commit, push, tag, production deployment, live provider call, or rollout
  activation was performed.
- Release boundary is unchanged: local foundation work is green, while the
  protected release candidate and public MVP remain **HOLD** behind the existing
  clean-revision, protected staging, operational, provider-rights, and explicit
  authorization gates.
- This older next step is superseded by the exact `PDP-100/100A/101/102` slice
  recorded in the newer provider data architecture checkpoint above.

## 2026-07-31 encrypted XHR and proxy-safety checkpoint

- The OddsPortal public-bundle decoder is implemented and pinned to
  `DECODER_REVISION=app-CxDlN6Pk-2026-07-31`: outer Base64, PBKDF2-HMAC-SHA256,
  AES-256-CBC/PKCS7, optional gzip, then strict JSON/schema validation.
- Historic/upcoming listing discovery now uses the encrypted XHR feed with
  trusted-host bootstrap, strict pagination/count/duplicate checks, timestamp
  filtering, and truthful `total=0` attestation.
- Explicit football matches support validated XHR extraction for full-time
  `1x2`, `over_under_2_5`, and `btts`, including exact `scopeId=2`, provider
  catalog mapping, finite decimal odds greater than one, and browser fallback
  for unsupported semantics or upstream drift.
- The fast path uses sticky listing/match transactions, per-egress pacing,
  bounded one-alternate failover, circuit breakers for direct/single/multi
  egress, and egress+geo-separated decoded/provider caches capped at 16 MiB of
  serialized JSON. Unexpected programming errors now propagate instead of
  being hidden by browser fallback.
- Camoufox remains a residual recovery engine. It reuses the same
  `ProxyManager`; multi-proxy mode creates one context per proxy and preserves
  blacklist/health state rather than leaking to direct egress or immediately
  retrying an unhealthy proxy.
- Fresh verification in `OddsHarvester/`:
  - targeted Ruff plus **122 passed**;
  - full non-integration pytest **964 passed, 5 skipped, 1 warning**;
  - full `ruff check src tests scripts` and nested `git diff --check` passed;
  - Serena/Pyright source-narrowing errors are cleared; its remaining errors
    are isolated interpreter/import-resolution noise for installed
    `cryptography` and `scrapling` packages;
  - independent code review: **APPROVE**; independent architecture review:
    **CLEAR**, with the representative live multi-proxy canary retained as an
    operational gate rather than a source blocker.
- Live direct-egress evidence:
  - Austria 2024/2025 listing page: **50 trusted links in 2.10 seconds**;
  - an earlier current-event canary decoded all three markets successfully in
    **2.425 seconds**;
  - the final direct-event attempt received ordinary HTML with HTTP 200 on the
    XHR URL and was truthfully classified as a soft block (**0/1 success**).
    This confirms that proxies can improve fault isolation but cannot guarantee
    that blocking disappears.
- No proxy endpoints or credentials were supplied, so multi-proxy live
  throughput, geo/provider parity, cooldown recovery, and the requested
  Australia + Austria + Argentina two-year workload remain unverified.
- Release/rollout state remains **HOLD**. Exact next step: run a bounded
  representative canary with 3-5 authorized same-geo proxies, 1-2 concurrent
  transactions per proxy, all three markets, and compare direct/XHR/browser
  parity, p50/p95, fallback rate, missing-market counts, and soft-block
  taxonomy before making a minutes-level SLA claim.

## 2026-07-31 no-proxy adaptive Camoufox checkpoint

- The no-proxy `auto` path now protects the shared direct IP with
  per-egress request jitter, exponential cooldown (default 15 seconds, capped
  at 300), a single reserved half-open recovery probe, and reset-on-success.
- `ScraplingProxyError` failures are classified as rate-limited rather than
  generic unknown failures. Result metadata preserves aggregate egress health
  and every XHR egress attempt without logging credentials or raw proxy URLs.
- Before the same direct/single egress moves from XHR to stealth/browser, or
  from Playwright to Camoufox, the orchestrator honors the remaining cooldown.
  A multi-proxy pool can use a healthy alternate egress without this extra
  same-IP delay.
- A soft-block observed by XHR is retained as an anti-bot signal. If
  Playwright later fails generically for the residual URL, Camoufox is now
  attempted even for a single match; it is not launched when Playwright has
  already recovered the result.
- Configuration is documented through `OH_XHR_COOLDOWN_BASE` and
  `OH_XHR_COOLDOWN_MAX`. Invalid, negative, NaN, or infinite values fail back
  to safe defaults.
- Fresh verification in `OddsHarvester/`:
  - focused adaptive/cascade tests: **63 passed**;
  - full non-integration pytest: **971 passed, 5 skipped, 1 warning**;
  - full Ruff and nested/root `git diff --check`: passed;
  - Serena reports no new source type errors; its unresolved Scrapling import
    remains isolated interpreter-resolution noise.
- Bounded live evidence on the previously used Melbourne Victory/Sydney URL:
  - `auto`, one HTTP worker and 1.5-second pacing applied a **10-second**
    adaptive cooldown and stopped without aggressive retries;
  - forced Camoufox headless completed in **17.338 seconds**, but the requested
    fragment `6o920ieL` no longer resolved and the page served event
    `0MigFJZi`; both Playwright and Camoufox correctly rejected the identity
    mismatch and emitted **0/1 success**;
  - the fresh observed fragment `0MigFJZi` then completed through forced
    Camoufox headless in **23.240 seconds**, **1/1 success**, with **7** 1X2,
    **7** over/under 2.5, and **6** BTTS bookmaker rows.
- These canaries prove the cooldown, Camoufox execution, identity guard, and
  successful no-proxy browser extraction. They do not prove that Camoufox can
  bypass a hard IP limit. Exact next step: run a bounded current-listing
  `auto` parity canary, then a representative multi-country sample before
  widening the workload.

## 2026-07-30 hybrid scraping pipeline v2 checkpoint

- Implemented deterministic cohort rollout, report `1.1`, persistent
  Scrapling sessions, resource blocking, truthful discovery attestation,
  capability-safe Camoufox fallback, operator-only Stagehand repair,
  validation-cache upsert, versioned recipe approval lineage, and batched odds
  ingestion with job-scoped immutable snapshot lineage.
- HAR recording now uses a temporary quarantine path, sanitizes and scans
  before atomic promotion, and deletes raw material on every failure path.
- Recipe persistence now accepts only an explicit harmless-header allowlist,
  enforces one active version per recipe key, and transactionally retires the
  previous active version during approval.
- Alembic is at `029 (head)` and `alembic check` reports no new operations.
- Fresh evidence:
  - backend Ruff passed; full pytest **583 passed**;
  - OddsHarvester Ruff passed; unit pytest **907 passed, 5 skipped**;
  - HAR/Playwright integration **12 passed, 27 skipped, 2 deselected**;
  - frontend Svelte check **0/0**, unit **32 passed**, production build passed;
  - root production contract **10 passed** and `git diff --check` passed;
  - Svelte MCP autofixer found no issues;
  - Serena reports no meaningful scraper type diagnostics; remaining findings
    are only dependency-resolution noise in Serena's isolated environment;
  - final independent code review: **APPROVE**, with no remaining findings in
    the three re-reviewed remediation areas;
  - Codebase Memory refreshed to `bet-core` 5403/20783 and
    `odds-harvester` 1910/9717 nodes/edges; focused Repomix pack
    `4411c29348e76bcf`.
- Local implementation and regression gates are **GO**. Hybrid rollout remains
  **0% / HOLD** until the staged 10/25/50/100 canary collects at least 20 jobs
  per stage and meets the ADR performance/parity/RSS gates. Public MVP release
  remains independently HOLD under the existing protected-release and
  external-operations requirements.
- This checkpoint is superseded by the production-image and canary checkpoint
  below.

## 2026-07-30 production image and hybrid canary checkpoint

- The production dependency input now installs `OddsHarvester[camoufox]`. The
  image embeds Chromium plus Camoufox `152.0.4-beta.28`, verifies the pinned
  Camoufox archive SHA-256 before extraction, disables the runtime-fetched UBO
  addon, and retains the Firefox/GTK runtime libraries required by Camoufox.
- The exact post-canary local production image is
  `4250804a63572d2ac139082ae0dd92bd62f0a5b43524ba224e6e59c9b3c59ced`
  (**4,633,563,260 bytes**, configured as non-root `appuser`). Its final smoke
  launched both Chromium and Camoufox offline, imported the backend plus all
  bridge projects, passed the Debian package audit, and confirmed that
  `uv`/`uvx` are absent.
- The sequential `job_id % 100` rollout bucket was replaced with a stable
  SHA-256 bucket over `scrape-pipeline-v2:<job_id>`. This keeps the
  10/25/50/100 cohorts nested while dispersing sequential job IDs. The runbook
  now also requires one-off publishers to verify Taskiq transport explicitly.
- An initial one-off canary publication accidentally inherited the development
  `inprocess` transport. Jobs `#368`-`#387`, runs `#315`-`#334`, and their
  outbox rows were preserved and marked truthfully as cancelled/failed during
  recovery; nothing was deleted. Replacement publication verified
  `transport=taskiq` before creating any run.
- The first real 20-job listing cohort (`#388`-`#407`) reached terminal state
  but was not a valid performance sample: 18 selected leagues had no fixtures
  for the target date. It nevertheless exposed a real v2 defect:
  `FetcherSession` was treated as the HTTP client instead of as the context
  manager that returns the client, causing `AttributeError`; HTTP/3 also
  produced QUIC handshake timeouts.
- The Scrapling lifecycle now:
  - leases the client returned by `FetcherSession.__enter__()`;
  - configures Chrome impersonation on the session manager and leaves HTTP/3
    disabled;
  - closes partial initialization and all managers best-effort, even when one
    close fails;
  - skips redundant Scrapling work for explicit match links;
  - can hand safely discovered public match links to Playwright instead of
    repeating browser discovery.
- Live recovery evidence:
  - Scrapling HTTP fetched the public match URL with HTTP 200 instead of
    raising `AttributeError`;
  - an `auto` run completed **1/1** by recording HTTP and stealth `no_records`
    before a successful Playwright fallback;
  - static league-listing responses still lacked trusted `eventRow` content,
    while Playwright found the match after hydration. The safe behavior remains
    browser fallback; selectors were not widened to arbitrary links.
- The controlled comparable cohort (`#408`-`#427`) completed **20/20** with
  result parity and success rate **100%**:
  - v1: 18 jobs, p50 **10,239.5 ms**, **10,331.56 ms/result**;
  - v2: 2 jobs, p50 **14,653 ms**, **14,653 ms/result**.
  This cohort ran before the explicit-link short-circuit and proved correctness
  but failed the performance gate because the redundant attempts made v2 about
  43% slower. Rollout was immediately returned to **0%** and was not advanced
  to 25%.
- Fresh post-fix verification:
  - backend full pytest **584 passed** and Ruff passed;
  - OddsHarvester unit pytest **914 passed, 5 skipped, 39 deselected** and Ruff
    passed;
  - focused backend/OddsHarvester regressions passed;
  - root production contract **10 passed** and `git diff --check` passed;
  - independent post-canary review: **APPROVE** after the partial-session
    cleanup and typing findings were fixed;
  - Codebase Memory refreshed to `bet-core` **5,404 / 20,794** and
    `odds-harvester` **1,915 / 9,783** nodes/edges.
- Current runtime is healthy in development: backend `/health` and `/ready`
  return 200, two bounded Taskiq workers are active at
  `BET_SCRAPE_PIPELINE_V2_PERCENT=0`, and the Tailscale frontend route
  `http://100.93.65.128:5175/` reaches the public UI route.
- Verdict: production capability packaging and source correctness are **GO**;
  staged rollout remains **HOLD at 0%**. Exact next step: prove a real listing
  discovery speedup without weakening trusted-link extraction, then rerun a
  representative 20-job 10% canary before considering 25%.

This checkpoint is superseded by the post-review rollout completion below.

## 2026-07-30 post-review hybrid rollout completion

- Static listing discovery now uses a typed browser handoff: an HTTP response
  with neither trusted event links nor an explicit no-fixtures signal records
  `static_listing_requires_browser` and skips the redundant stealth request.
- Discovered links are accepted only when they are HTTPS URLs on the exact
  configured host, with no userinfo, nonstandard port, query string, traversal,
  or malformed match path/fragment.
- The v2 direct-match path replaces unconditional delays with trusted DOM
  readiness only when the target market and period were already active before
  navigation and no submarket transition occurred. Uncertain transitions keep
  the legacy waits, preventing stale bookmaker rows from satisfying a new
  market selection.
- The final adversarial review initially found the link-trust and stale-row
  risks above. Rollout was returned to 0%, the candidate image build was
  stopped, both issues were fixed with regressions, and the reviewer then
  returned **APPROVE** with no Critical, High, or Medium findings.
- The authoritative post-review Taskiq cohorts all completed with result
  parity, one match/result and six odds writes per job, and zero anti-bot
  reports:

| Stage | Jobs | v2 / v1 | v2 p50 | v1 p50 | Improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| 10% | `#528-#547` | 2 / 18 | 3.285 s | 11.053 s | 70.3% |
| 25% | `#548-#567` | 7 / 13 | 3.711 s | 9.993 s | 62.9% |
| 50% | `#568-#587` | 11 / 9 | 3.097 s | 9.961 s | 68.9% |
| 100% | `#588-#607` | 20 / 0 | 3.232 s | n/a | n/a |

- At 100%, v2 used **3.319 seconds/result**. The idle Taskiq parent, resource
  tracker, and forkserver used about **143 MiB aggregate RSS**, below the 4 GiB
  gate.
- Fresh final verification:
  - OddsHarvester full unit suite **928 passed, 5 skipped, 39 deselected**;
    Ruff and nested `git diff --check` passed;
  - backend full pytest **584 passed** and Ruff passed;
  - frontend Svelte check reported **0 errors / 0 warnings**, unit tests
    **32/32 passed**, the production build passed, and the targeted Chromium
    Prepare/pagination E2E **2/2 passed**;
  - root production contract **10 passed** and root `git diff --check` passed;
  - a final direct live v2 match completed **1/1 in 4.539 s** with six
    bookmakers;
  - Codebase Memory was refreshed to `bet-core` **5,404 / 20,794** and
    `odds-harvester` **1,936 / 9,988** nodes/edges.
- External DNS was unavailable to the fresh Podman dependency build. Because
  dependency inputs and browser artifacts were unchanged, the final source was
  layered offline over the already smoke-tested immutable image. The exact
  final local image is
  `16dec9ee42f2e31fbcd36da70f3950273241f2446269e0d9c0d8c18eecb58f6e`
  (**4,636,510,974 bytes**, non-root `appuser`). Its final offline smoke
  launched Chromium and Camoufox, imported the backend and bridge projects,
  passed the Debian package audit, and confirmed `uv`/`uvx` are absent.
- Current development runtime is healthy: backend `/health` and `/ready`
  return 200, the frontend returns 200 at
  `http://100.93.65.128:5175/about`, and the Taskiq worker runs with
  `BET_TASK_QUEUE_BACKEND=taskiq` and
  `BET_SCRAPE_PIPELINE_V2_PERCENT=100`.
- Verdict: implementation, regression gates, exact local image, and staged
  **local development rollout are GO at 100%**. Public MVP release remains
  **HOLD**: the candidate is still dirty/uncommitted and has not passed a new
  commit/PR, protected CI, exact-image staging, broader mixed-league soak, or
  explicitly authorized public promotion.
- Exact next step: reconcile the reviewed dirty candidate into an intentional
  commit/PR, run protected CI and exact-image staging/soak, then request an
  explicit new release-candidate/public rollout approval.

## 2026-07-31 local scraper runtime recovery

- The active user scrape was initially launched with UI engine `auto`, but the
  development runtime omitted `BET_SCRAPE_PIPELINE_V2_PERCENT`; the backend
  defaulted to `0`, selected Playwright, and processed the queue serially.
- PostgreSQL and Redis were restarted, Alembic reports `029 (head)`, and the
  complete local platform was relaunched with Taskiq plus
  `BET_SCRAPE_PIPELINE_V2_PERCENT=100`.
- Two bounded Taskiq workers are active, each limited to one task and one
  prefetched message. Live job logs prove jobs `#674` and `#678` selected
  `engine=auto`, `pipeline_v2_enabled=true`, and rollout percentage `100`.
- Fresh runtime probes: backend `/health` **200**, `/ready` **200** with
  database/schema/task queue/task runtime ready, and frontend `/about` **200**
  on `127.0.0.1:5175`.
- The focused backend rollout-selection regression passed: **2 passed**, and
  `git diff --check` passed after the runtime handoff update.
- The pre-restart batch contains 28 rows from `#671` through `#698`: one
  completed, one failed, 23 pending, two actively executing, and one stale
  running row awaiting normal lease recovery. The queue is intentionally
  retained rather than deleted or silently recreated.
- The canonical integrated-start command below now exports the v2 percentage
  explicitly and starts two bounded workers, preventing a future restart from
  silently falling back to Playwright-only execution.
- Exact next step: monitor the two active auto-engine jobs and the stale lease
  recovery; reduce to one worker if anti-bot signals or resource pressure
  increase.

Current program state:

- Phase 0 durable checkpoint and baseline: **complete**.
- Phase 1 reproducible development runtime: **complete locally**.
- Phase 2 security/release foundation: **complete on merged main; scraper
  input/SSRF/resource hardening, truthful upcoming-date semantics,
  freshness-aware deduplication, and odds lineage remediation are merged and
  evidence-only release proof is green**.
- Phase 3 product/UX: **local implemented scope and browser/PWA gates green**.
- Phase 4 adversarial QA/staging: **local and branch E2E gates green; protected staging and external operations evidence pending**.
- Phase 5 release candidate: **PR #15 is merged as `6abb637`; post-merge CI and
  exact-main evidence-only run `30474329662` are green; RC
  `v0.1.0-rc.20260725.1` remains quarantined and no new exact tag is
  authorized**.
- Paper execution: **excluded from public MVP** by accepted ADR
  [`2026-07-23-exclude-paper-execution-from-mvp.md`](../adr/2026-07-23-exclude-paper-execution-from-mvp.md).
- Verdict: **merged source, post-merge CI, and evidence-only release GO;
  protected release-candidate and public MVP launch HOLD until an exact tag is
  explicitly authorized, the signed protected release passes, and all external
  operational evidence is complete**.

## 2026-07-30 in-process scrape fan-out remediation checkpoint

- Fresh PostgreSQL inspection correlated the user-created Australia/Austria/
  Argentina jobs `#620`-`#643` with runs `#567`-`#589`. They were all
  delivered through the development `inprocess` transport. Prepare enqueued
  every bounded batch immediately; the transport previously created an
  unbounded asyncio task for each one.
- Historic batches of five leagues therefore competed concurrently for
  Chromium/OddsPortal capacity. Jobs `#620`, `#622`-`#627`, and `#631`-`#637`
  exhausted their per-batch bridge budgets (1,200–2,100 seconds). Jobs `#628`
  to `#630` completed only degraded (21, 32, and 82 records respectively).
  Two upcoming batches (`#638`, `#643`) produced zero-record CLI failures
  during the same fan-out, while four sibling upcoming batches completed.
  No sampled report signalled anti-bot detection.
- The default in-process dispatcher now serializes only browser-heavy
  `scrape_job` runs with `BET_INPROCESS_SCRAPE_MAX_CONCURRENCY=1`; other
  in-process task types retain their prior behavior. Taskiq continues to own
  concurrency when explicitly configured. This prevents a large Prepare
  submission from launching many browser processes simultaneously.
- Fresh verification: targeted task-run/task-queue tests **24 passed**, Ruff
  passed, and `git diff --check` passed. The nested catalog/standings
  regression remains independently green (**13 passed**); its change exposed
  4 Algeria, 14 Argentina, 27 Australia, and 19 Austria candidates in one
  controlled live discovery.
- Existing failed rows were preserved. Do not automatically retry their
  historic/upcoming requests: they contact the external provider. Exact next
  step: terminalize the stale in-process run and inspect the remaining pending
  job through the durable recovery path, then retry only selected one-league
  batches under the new serialization and compare report health/records before
  a wider replay.

### Controlled rerun after fan-out repair

- At explicit operator request, created new audit-preserving jobs `#644`-`#669`
  for Austria, Australia, and Argentina. The rerun uses the same 48 supported
  league selections in ten bounded historic batches for each of the two actual
  past seasons (`2024-2025`, `2025-2026`), plus six bounded upcoming batches
  for `20260731`.
- The former two-year date range could also name `2026-2027` at the July
  boundary. It was intentionally excluded from this rerun because it is a
  future season, not historical work. Total queued work is **26 jobs**:
  **20 historic** + **6 upcoming**.
- Fresh 30-second database observation: jobs `#644` and `#645` reached their
  truthful partial terminal states, job `#646`/run `#592` was running with a
  current heartbeat, and the remaining **23** runs were queued. No second
  scraper run was concurrently active, confirming the new in-process
  serialization under real queue traffic.
- Keep the dev server alive while this in-process queue drains. Do not modify
  watched backend files or restart the process; doing so would interrupt
  in-memory delivery. Use Taskiq for durable multi-process execution.

### Live HTTP/XHR and browser-engine proof

- A real Scrapling `Fetcher` response exposed an empty callable `text` handler
  while its `body` contained the complete HTML. `_response_text` now falls back
  to `body` when rendered text is empty. The regression failed before the fix
  and the focused Scrapling plus scraper-app tests now pass **42/42**; Ruff and
  nested `git diff --check` also pass.
- Comparable single-match live runs against the same historic A-League Women
  event produced:
  - `scrapling-http`: HTTP 200 in **1.787s**, but 0 records because the static
    response represented a stale H2H event;
  - `scrapling-stealth`: HTTP 200 in **6.523s**, but the same truthful stale
    event rejection and 0 records;
  - Camoufox headless: **1/1** record with five bookmakers in **11.696s**;
  - Playwright headless: **1/1** record with five bookmakers in **9.733s**.
    The two successful records were identical except for `scraped_date`.
- Camoufox `152.0.4-beta.28` was fetched into the machine cache for this live
  test; no browser artifact was added to Git.
- A Playwright network capture using the full event/market fragment proved that
  the page hydrates through HTTP 200 XHR requests to `?eventId=...` and
  `/match-event/...dat`. Direct response inspection showed Base64-wrapped,
  non-JSON payloads that are not gzip, zlib, bzip2, or LZMA. The current
  Scrapling adapter therefore proves fast transport only; it does **not** yet
  prove valid HTTP/XHR record extraction.
- Plain Chromium telemetry identified the session as
  `automation:headless`/`flashscore_bot`. Camoufox successfully extracted the
  same record, but this single run is correctness evidence rather than proof of
  lower detection risk or faster large-batch throughput.
- Exact next step: reverse or reuse the site's in-browser payload decoder in a
  bounded experiment and require record parity against the browser path before
  enabling HTTP/XHR extraction. Until then, retain Camoufox/Playwright as the
  valid extraction path and improve batch throughput with bounded workers,
  browser/context reuse, cache, and representative canaries.

## 2026-07-30 failed scraping jobs remediation checkpoint

### Recent scrape-job pagination

- Root cause of the apparently truncated job history: the backend endpoint
  defaulted to `per_page=20`, while Prepare called `/api/v1/data/scrape`
  without `page` or `per_page` and rendered no pagination controls.
- The existing array response remains backward-compatible. The endpoint now
  returns ownership-filtered `X-Total-Count`, `X-Page`, and `X-Per-Page`
  headers, while Prepare requests the selected page explicitly.
- Prepare now shows the visible item range and total, previous/next controls,
  a direct page selector, and page sizes of 10, 20, 50, or 100. Creating or
  retrying jobs resets the list to page 1 so the newest jobs are visible.
- Concurrent polling responses are request-ordered, preventing an older
  10-second refresh from overwriting a page the user selected afterward.
- Fresh verification: backend pagination regressions **2 passed**; full
  backend Ruff passed and pytest **561 passed**; Svelte MCP autofixer reported
  no issues; `pnpm check` reported **0 errors / 0 warnings**; frontend unit
  tests **32 passed**; E2E TypeScript check and production build passed;
  targeted Chromium Prepare flow **2 passed**, including page 1/2/3 and
  20-to-10 rows-per-page changes; root contracts **29 passed** and
  `git diff --check` passed. The refreshed `bet-core` Codebase Memory fast
  index contains **5,321 nodes / 20,337 edges**.

### Live rerun incident and recovery

- The user reran the same large scope at approximately `2026-07-30 01:22
  +03:00`, creating bounded jobs `#341`-`#365`.
- Job `#341` completed in about 18 minutes with 233 matches and 1,022 odds
  rows. Job `#342` completed its upstream collection in about 23 minutes with
  327 matches and 1,851 odds rows, but its scheduled run did not finish for
  another 27 minutes.
- Fresh PostgreSQL activity evidence showed a transaction/heartbeat deadlock:
  the scrape executor had updated the result but waited for
  `_task_run_heartbeat` to exit, while the final heartbeat transaction waited
  on the executor's uncommitted `scheduled_job_runs` row. Because local Taskiq
  intentionally has one worker slot, all later jobs remained queued.
- The blocked heartbeat database session was terminated without terminating
  the ingestion transaction. Job `#342` and run `#247` then committed
  successfully.
- `execute_scrape_job_run` now commits or rolls back the scrape result inside
  the heartbeat context, before heartbeat shutdown. A regression test asserts
  this ordering.
- The worker was restarted with the fixed source and conservative
  `--workers 1 --max-async-tasks 1 --max-prefetch 1` settings. At
  `2026-07-30T02:38:13+03:00`, job `#344` / run `#249` was `running`, its
  heartbeat was advancing, and PostgreSQL reported no blocked sessions.
- A second queue-liveness defect became visible after `#344` completed: the
  stale-published outbox recovery treated runs `#250`-`#270` as unconfirmed
  deliveries while they were legitimately waiting behind the long serial
  scrape, replayed them until the attempt limit, and marked them `timed_out`
  before they ever started.
- Outbox replay now leaves a published queued run untouched while an earlier
  Taskiq delivery is still queued or running. The regression locks the
  conservative single-worker backlog contract instead of converting queue wait
  time into false delivery failure.
- Operational recovery retained all audit rows. An initial replacement attempt
  created in-process runs `#271`-`#291` because the one-off process did not
  explicitly override the local default transport; those runs were cancelled
  with a truthful recovery error before completion and the scrape jobs remained
  pending. The worker and scheduler were then restarted with
  `BET_TASK_QUEUE_BACKEND=taskiq`, replacement Taskiq runs `#292`-`#312` were
  created, and job `#345` / run `#292` entered `running` under the single
  worker.
- Job `#343` is a separate upstream failure: OddsHarvester exited before
  discovering any URL or selecting an engine for the five-league historic
  batch. Its report records zero URLs, zero records, one exception warning,
  `cli_error=true`, and no anti-bot signal. The original CLI exception text was
  not retained by the existing sanitized report, so this row is truthful but
  does not support a more specific retrospective diagnosis.
- Fresh verification after the deadlock fix: targeted task/scrape tests
  **48 passed**; backend Ruff passed; full backend pytest **559 passed**; root
  production/release contracts **29 passed**; `git diff --check` passed.
  Serena source inspection confirmed the commit-before-heartbeat-exit ordering,
  and the refreshed `bet-core` Codebase Memory fast index contains **5,309
  nodes / 20,266 edges**.
- Fresh verification after the backlog-liveness fix: targeted task-run tests
  **21 passed**; backend Ruff passed; full backend pytest **562 passed**.

### Controlled local scrape-throughput canary

- Completed five-league historic reports show that upstream
  OddsHarvester/Playwright dominates job duration: `#341` used **1,043.880s**,
  `#342` used **1,298.696s**, and `#344` used **972.885s**. Successful historic
  auto-engine runs used Playwright; database ingestion is not the primary
  bottleneck.
- Runtime Results-page validation also precedes each historic bridge launch:
  it took about **78s** for job `#345` and **125s** for job `#346`. This
  validation is correctness-sensitive and was not bypassed.
- At `2026-07-30T03:07:51+03:00`, a second local Taskiq worker with a unique
  runtime heartbeat identity claimed job `#346` while the original worker
  continued job `#345`. Both workers remain bounded to one active task and one
  prefetched message, so the canary raises queue throughput from one to at most
  two simultaneous scrape batches rather than restoring the failed
  ten-concurrent-job configuration.
- With both Playwright jobs active, the measured aggregate was about **205% CPU**
  and **3,011 MiB RSS** across 20 scraper/Chromium processes. The 12-core host
  still reported about **12 GiB available RAM**, and `/ready` remained green
  for database, schema, task queue, and task runtime.
- Both canary jobs completed successfully while overlapping:
  - job `#345` completed healthy with **485 records**, **1,921.291s** upstream
    time, and about **33m25s** end-to-end;
  - job `#346` completed degraded/partial with **328/331 successful records**
    (**99.1%**), **1,301.120s** upstream time, and about **23m50s**
    end-to-end; neither canary reported an anti-bot signal.
  Their upstream cost was approximately **3.96s/record**, matching prior serial
  samples (`#342` and `#344`) closely. The second worker therefore doubled
  queue service capacity without measurable per-record slowdown in this
  canary. Jobs `#347` and `#348` then started concurrently on the two workers.
- Local Docker and Podman compose now use configurable
  `BET_TASKIQ_WORKERS`, defaulting to **2** for development while retaining
  `--max-async-tasks 1 --max-prefetch 1`. Operators can set the value back to
  **1** on smaller hosts or when upstream throttles. The protected production
  compose and release workflow remain conservatively fixed at one worker.
- Fresh configuration evidence: both local compose files render `--workers 2`
  by default, the explicit `BET_TASKIQ_WORKERS=1` override renders one worker,
  root contracts **29 passed**, and `git diff --check` passed.

- Fresh PostgreSQL evidence for the last user-launched jobs:
  - job `#335`, historic `2026-2027`, 34 leagues: failed after the bounded
    3600-second bridge run;
  - jobs `#336` and `#337`, historic `2025-2026` and `2024-2025`, 34 leagues:
    catalog validation failed after 600 seconds;
  - job `#338`, upcoming `20260730`, 34 leagues: failed after 600 seconds.
- Root cause was combined resource amplification: all four Chromium-heavy jobs
  started concurrently under Taskiq `--max-async-tasks 10`, while each request
  still passed all 34 leagues to one OddsHarvester process. A prior five-league
  historic run needed about 29 minutes, so concurrency control alone could not
  make a 34-league historic subprocess complete inside the 3600-second cap.
- The local remediation now:
  - creates historic jobs in batches of at most **5 leagues** and upcoming jobs
    in batches of at most **10 leagues** from Prepare;
  - rejects oversized persisted/API jobs with HTTP 422 and revalidates them at
    execution, preventing direct clients or old payloads from bypassing the
    bounds;
  - scales the OddsHarvester timeout by validated batch size, including historic
    catalog validation, while retaining the 3600-second hard cap;
  - runs at most two Taskiq jobs at a time in local development by default,
    with one active task and one-message prefetch per worker; production compose
    and release verification remain fixed at one worker;
  - reports the truthful batched historical job count in the large-scope
    confirmation and prevents scheduled upcoming automations from silently
    saving selections above 10 leagues.
- Fresh real runtime evidence:
  - an authenticated 11-league upcoming create request returned **HTTP 422**;
  - bounded job `#339` (`brazil-serie-a`, one league) completed in **62s** with
    dataset `258`, 2 matches, and 13 odds rows;
  - bounded background/Taskiq job `#340` (`brazil-serie-b`, one league), run
    `#245`, returned HTTP 202 and completed in **43s** with the valid
    `no_fixtures` outcome and dataset `259`;
  - `/ready` returned `ready` for database, schema, task queue, and task runtime;
    the original active worker command is
    `--workers 1 --max-async-tasks 1 --max-prefetch 1`; the controlled canary
    adds a separate worker with the same per-worker limits.
- Fresh verification:
  - Serena source navigation and the fresh `bet-core` Codebase Memory graph
    were reconciled with the working tree; the final fast reindex contains
    **5,308 nodes / 20,254 edges**;
  - backend Ruff: pass; backend pytest: **558 passed**;
  - root production/release contracts: **29 passed**;
  - frontend Svelte MCP autofixer: no issues; `pnpm check`: **0 errors / 0
    warnings**; unit tests: **32 passed**; E2E TypeScript check and production
    build: pass;
  - Playwright `prepare-guided-flow.spec.ts`: **1 passed** using the installed
    browser cache. An initial invocation pointed `PLAYWRIGHT_BROWSERS_PATH` at
    an empty temporary cache and failed before browser launch; rerunning against
    the installed cache passed;
  - `git diff --check`: pass.
- Old failed job rows `#335`-`#338` remain immutable operational history. A
  repeat of the same UI selection will now enqueue **25 bounded jobs** (21
  historic plus 4 upcoming) and the worker will process them serially; this
  large live-site rerun was not started automatically.
- Exact next step: keep the validated two-worker local setting through the
  remaining queue, monitor upstream anti-bot/timeout rates and RAM, and fall
  back to `BET_TASKIQ_WORKERS=1` if either increases materially.

## 2026-07-29 implementation audit and scraper-hardening checkpoint

This section supersedes older continuation instructions that still name a PR
or remediation branch as pending.

- Fresh source/Git verification found clean aligned `main` at `515fcd1` before
  this implementation slice; remote inspection confirmed PR #14 merged, main
  evidence run `30151025646` green, RC1 quarantined, and no RC2 tag.
- Serena (`core`, `mvp_readiness`, `platform_hardening`), the refreshed
  `bet-core` Codebase Memory graph, and a focused compressed Repomix pack
  (`2d641a6d55ba6b2e`) were reconciled against current source. After the
  implementation and final review correction, `bet-core` was reindexed to
  **5,301 nodes / 20,226 edges** and the focused Repomix pack was refreshed as
  `cef78098a045226e`. Older
  memories were useful for continuity but were not treated as current release
  proof.
- The audit found two source-level launch blockers in the scraper path:
  authenticated arbitrary network/resource parameters, plus an upcoming
  `future_days` contract that promised an interval while the bridge targeted
  one day and could reuse stale/no-longer-existing datasets.
- The local remediation now:
  - accepts only supported scrape job types and commands;
  - restricts base URLs and match links to HTTPS allowlisted provider origins
    and bounds links, leagues, markets, concurrency, delay, pages and timeouts;
    recursive payload shape is bounded, final normalized parameters are capped
    at 64 KiB, and both nginx entry points cap request bodies at 1 MiB;
  - materializes upcoming offsets to an absolute `YYYYMMDD` target at creation,
    using the browser's validated IANA timezone or UTC fallback;
  - reuses historical season datasets durably, but reuses upcoming datasets
    only when the dataset still exists and completion is at most 10 minutes old;
  - records `dataset_id` and `scrape_job_id` on odds snapshots without
    rewriting existing provenance;
  - returns HTTP 422 for invalid scraper payloads instead of creating or
    fabricating successful jobs;
  - changes Prepare to one truthful target day (1–31 days), defaulting to
    tomorrow, with browser regressions for the new contract.
- Fresh verification on the local candidate:
  - backend Ruff: pass; backend pytest: **556 passed**;
  - Alembic current/heads: **025 (head)**; `alembic check`: **no new upgrade
    operations detected**;
  - root release/security contracts: **29 passed**; tracked plaintext-secret
    scan and `git diff --check`: pass;
  - frontend Svelte MCP autofixer: no issues; `pnpm check`: **0 errors / 0
    warnings**; unit tests: **32 passed**; E2E TypeScript check and production
    build: pass;
  - targeted Playwright Prepare/security checks: **3 passed**;
  - integrated `/health`: **200**; `/ready`: **200** with database, schema,
    task queue and task runtime ready; frontend root: expected anonymous
    **302** to `/about`;
  - full Chromium hybrid: **57 passed** in **3.8 minutes**;
  - final independent code review: **APPROVE**, with no remaining Critical,
    High, or Medium findings in the reviewed scope.
- A real local scheduled upstream scrape executed during runtime verification
  and returned a truthful `no_fixtures`/zero-record dataset. This proves runtime
  bridge execution and honest status handling, not provider coverage or a
  complete real scrape -> prediction -> ticket lifecycle.

Exact next step: merge this documentation-only checkpoint and rerun
evidence-only proof on its exact merge commit before considering a tag. Creating
or pushing a new RC tag still requires explicit owner authorization; public
rollout remains blocked by the external operational gates.

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

Start only G002/P2 design: map the existing Match/team/competition, dataset,
odds and prediction lineage, then accept a separate provider-scoped
identity/schema ADR before changing SQLAlchemy models or Alembic. After that
gate, implement an expand-only ProviderObservation and provider mapping slice
with replay/idempotency/conflict tests. Do not edit nested projects, call a
live provider, deploy, or activate rollout. Keep public release/MVP launch
**HOLD** until the existing protected publication, provider-rights, staging,
backup/restore, observability/on-call/soak/canary and explicit rollout gates
are evidenced.

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
export BET_SCRAPE_PIPELINE_V2_PERCENT=100

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
.venv/bin/taskiq worker app.tasks.broker:broker app.tasks.jobs \
  --workers 2 --max-async-tasks 1 --max-prefetch 1 --log-level WARNING
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
