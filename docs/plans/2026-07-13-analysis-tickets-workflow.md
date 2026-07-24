# Implementation Plan: Argentina Analysis and Tickets Workflow

## Current status

Implemented and verified as part of the platform-hardening branch. The durable
handoff, current migration head, verification counts, known residuals, and
new-session commands are maintained in
[`docs/status/current-platform-status.md`](../status/current-platform-status.md).

## Objective

Complete the operator path from the persisted Argentina all-leagues scrape through every active strategy, then generate and review tickets without losing dataset, prediction-run, or candidate lineage. The active UX contract is `DESIGN.md`; this plan translates the user's approved request into implementation slices.

## Verified starting point

- Scrape job `#198` requested all six configured Argentina leagues and completed healthy.
- Dataset `#33` contains 40 upcoming matches from the four leagues that returned fixtures; all 40 records resolve deterministically to persisted matches.
- Active strategy catalog: IDs `3`, `29`-`34` (seven active strategies).
- Database migration head: `015`.
- Existing targeted baseline: backend 78 tests, frontend 30 tests, and `pnpm check` pass.

## Decisions

- "All strategies" means every active catalog strategy; inactive strategies remain visible and disabled.
- A healthy scrape may include fewer leagues than requested when a league returns no fixtures. UI must show requested-versus-returned coverage honestly.
- Analyze sends all selected strategies in one batch request so dataset resolution occurs once; retry sends only failed strategy IDs.
- Tickets accepts multiple prediction run IDs from one dataset. The legacy singular run ID remains supported.
- Multi-run lineage is persisted in `generation_report.prediction_run_ids`; `source_prediction_run_id` remains the backwards-compatible primary run and each leg retains its exact `model_prediction_id`.
- Generated tickets remain drafts until explicit review and activation.

## Tasks

1. **Analysis orchestration**
   - One batch request for all selected active strategies.
   - Stable per-strategy terminal states and failed-only retry.
   - Structured dataset-resolution errors rendered as actionable text.
   - Verify with backend/frontend unit tests.

2. **Analysis trust and responsive UX**
   - Ineligible predictions cannot enter the bet slip; eligible legs preserve prediction lineage.
   - Dataset coverage, run IDs, reliability, and disabled reasons remain visible on mobile and desktop.
   - Select controls have programmatic labels; sticky actions avoid mobile navigation/FAB overlap.
   - Verify with `pnpm check` and browser viewports.

3. **Multi-run ticket generation**
   - API accepts `run_ids`, validates ownership/status/same dataset, and validates prediction IDs against the full allowed run set.
   - Batch and response expose all source run IDs without a schema migration.
   - Verify single-run backward compatibility and multi-run generation tests.

4. **Tickets interaction hardening**
   - Analyze handoff uses all transferred run IDs.
   - Polling cannot erase an in-progress batch review.
   - History mutations are limited to generated drafts; active/watchlist labels remain truthful.
   - Verify unit, Svelte, build, and browser tests.

5. **Runtime proof**
   - Start backend on `8001` and frontend on `5175` against the migrated local Postgres database.
   - Run dataset `#33` across all active strategies and capture terminal outcomes.
   - Verify Analyze -> Tickets handoff and generated-draft review in Chromium at mobile and desktop widths.

## Boundaries

- Preserve all current uncommitted work and nested submodules.
- No live/external bet placement; paper-local execution only.
- Do not claim six leagues returned data when only four returned fixtures.
- Do not silently fall back to an unrelated latest dataset or prediction run.
- Training-history insufficiency and per-strategy failures remain visible rather than synthesized as success.

## Completion criteria

- Every active strategy receives a terminal result for dataset `#33`.
- Dataset resolution is performed once per all-strategy attempt.
- Multi-strategy candidate selections can generate one lineage-safe draft batch.
- Analyze and Tickets pass targeted tests, `pnpm check`, build, and browser verification without console errors or body overflow.
