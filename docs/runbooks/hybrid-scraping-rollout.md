# Hybrid scraping pipeline v2 rollout

The hybrid pipeline is implemented and remains disabled by default in checked
configuration:

```env
BET_SCRAPE_PIPELINE_V2_PERCENT=0
```

An evidence-qualified local development worker may run at `100`; this does not
change the safe production default or authorize a public rollout.

## Runtime order

1. bounded persistent Scrapling HTTP sessions;
2. bounded Scrapling stealth;
3. Playwright with nonessential resources blocked;
4. Camoufox only after anti-bot or repeated navigation failures.

Explicit trusted match links skip listing discovery and go directly to the
browser extractor. For listing pages, a successful HTTP response that contains
neither a trusted match link nor an explicit no-fixtures signal raises the
typed `StaticListingRequiresBrowserError`; the auto cascade records
`static_listing_requires_browser` and hands off directly to Playwright instead
of repeating the same static listing through stealth.

An unavailable or failed optional Camoufox attempt is recorded and preserves
the primary Playwright result. Stagehand is not part of the scrape hot path.
The production image installs `oddsharvester[camoufox]` and embeds the pinned
Camoufox `152.0.4-beta.28` Linux x86_64 browser. The build verifies SHA-256
`924f3109ccd6d47cd6a0384d67a345fadf975d48b6319f8dbbd5954c588982bd`
before extraction, and the release workflow launches the browser during image
smoke testing. The runtime disables Camoufox's default network-fetched addon,
so worker startup and browser launch remain offline-capable.

Operators may generate a non-active candidate locally:

```bash
cd OddsHarvester
UV_CACHE_DIR=/tmp/uv-cache uv sync --extra dev --extra stagehand
OH_STAGEHAND_API_KEY=... OH_STAGEHAND_MODEL=... \
  .venv/bin/python scripts/propose_stagehand_recipe.py \
  --page https://www.oddsportal.com/football/example/ \
  --output /tmp/stagehand-recipe.json
```

Never persist model keys, cookies, authorization headers, proxy credentials,
or raw HAR files. Candidate recipes require deterministic verification and
operator approval before activation.

## Trusted links and readiness optimization

- HTTP discovery accepts only HTTPS match URLs on the exact configured
  OddsPortal host, with no userinfo, nonstandard port, query string, traversal,
  or malformed path/fragment.
- Browser readiness is condition-based only when the target market and period
  were already active before navigation and no submarket transition occurred.
  The optimized path waits for trusted match-team DOM and bookmaker-row
  signals.
- New or uncertain market/period/submarket transitions retain the legacy
  bounded delays. Existing bookmaker rows are never accepted as proof that a
  newly selected market finished loading.
- All fast readiness behavior is gated by
  `ODDSHARVESTER_PIPELINE_V2=1`; v1 retains the original waits.

## Canary stages

Set `BET_SCRAPE_PIPELINE_V2_PERCENT` to `10`, `25`, `50`, then `100`. Observe
at least 20 completed jobs at each stage. Advance only when:

- result parity is at least 99%;
- success rate is no more than one percentage point below v1;
- p50 duration is at least 40% lower, or seconds/result is at least 30% lower;
- anti-bot incidence does not materially increase;
- worker RSS remains below 4 GiB;
- no ownership, lineage, idempotency, `observed_at`, or report-contract
  regression occurs.

The cohort is stable and nested across stages. The backend hashes
`scrape-pipeline-v2:<job_id>` with SHA-256, maps the first 64 bits into a
`0..99` bucket, and enables v2 when the bucket is below the configured
percentage. Do not replace this with `job_id % 100`: sequential job IDs would
otherwise produce long all-v1 and all-v2 blocks instead of a representative
canary.

Local one-off publishers must fail closed on transport configuration. Set and
verify both `BET_TASK_QUEUE_BACKEND=taskiq` and
`BET_SCRAPE_PIPELINE_V2_PERCENT=<stage>` before creating runs. The development
default transport is `inprocess`; relying on that default from a short-lived
script can leave audit rows without a live executor.

## Local post-review canary evidence

The authoritative staged cohort was rerun after the final SSRF and stale-odds
readiness fixes. Every stage used Taskiq, 20 terminal direct-match jobs, one
match/result and six odds writes per job, `100%` success/parity, and zero
anti-bot reports:

| Stage | Jobs | v2 / v1 | v2 p50 | v1 p50 | p50 improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| 10% | `#528-#547` | 2 / 18 | 3.285 s | 11.053 s | 70.3% |
| 25% | `#548-#567` | 7 / 13 | 3.711 s | 9.993 s | 62.9% |
| 50% | `#568-#587` | 11 / 9 | 3.097 s | 9.961 s | 68.9% |
| 100% | `#588-#607` | 20 / 0 | 3.232 s | n/a | n/a |

At 100%, v2 used 3.319 seconds/result. The two-worker Taskiq parent, resource
tracker, and forkserver used about 143 MiB aggregate RSS while idle after the
cohort, below the 4 GiB gate.

These controlled direct-match cohorts prove the staged local rollout contract.
They do not replace a broader mixed-league soak or protected staging evidence
required for public production promotion.

## Rollback

Set `BET_SCRAPE_PIPELINE_V2_PERCENT=0` and restart backend/worker processes.
No schema rollback is required. Do not promote a canary when the production
image lacks an optional browser capability; the fallback remains safely
capability-gated until that image is built and smoke-tested.
