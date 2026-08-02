# ADR: Checkpointed soccerdata ingestion and staged publication

- Status: Accepted
- Date: 2026-08-01
- Scope: G004 / P3 provider-data platform

## Context

`soccerdata` is the preferred non-odds acquisition adapter, but each upstream
source has a distinct policy, cache, quota and execution profile. A whole-season
fetch cannot be treated as one opaque successful dataset: retries must not
repeat committed pages, partial pages must not become visible, and cache
telemetry must not redefine canonical football content.

## Decision

1. The backend owns an immutable `soccerdata-ingestion/v1` JobSpec. The public
   scheduled job always starts at page zero; subsequent `page` and
   `start_cursor` values are derived only from the validated bridge cursor.
   Page zero also derives an internal generation key from the logical group and
   the complete upstream artifact digest; every continuation must carry and
   prove that same generation.
2. MatchHistory, ESPN and Understat run in `provider-http`; FBref runs in
   `provider-browser`. Every page repeats the fail-closed adapter/source/
   operation authorization before external work.
3. The bridge applies backend-provided TTL, payload and record bounds. It emits
   monotonic page cursors and enforces source RPM between actual upstream
   requests through a process-safe `fcntl` timestamp ledger in the shared
   `SOCCERDATA_DIR`; valid cache hits do not consume quota.
4. PostgreSQL checkpoints are scoped by operation, competition, season and
   page. Each completed page commits independently. A retry replays a fresh
   completed checkpoint and continues at its cursor without fetching that page
   again.
5. Canonical content rows and snapshot membership are separate. A generation
   head owns immutable page-to-dataset associations, so unchanged or reverted
   content can participate in multiple generations without duplicating the
   content row. The terminal page takes a group lock, validates the exact page
   set from one generation, atomically publishes it and marks the former head
   `superseded`. A historical page or changed artifact cannot satisfy
   continuity. Authoritative page-zero `no_data` publishes an explicit empty
   generation head (`terminal_page=-1`) without inventing an empty dataset.
6. Canonical dataset identity hashes stable `source_id + payload` content, not
   acquisition-derived timestamps or cache counters. Cache attestations must
   be unexpired and within bounded future skew; revalidation advances the
   dataset freshness metadata without duplicating observations.
7. Real bridge `timeout` and `transport` failures are translated into the
   durable task-run retry taxonomy. Persistence and publication remain fenced
   by the claimed execution token.
8. Canonical dataset insertion is serialized by its stable dataset key. This
   makes concurrent warm/refresh executions idempotent even though their
   execution-spec digests and checkpoint rows are distinct.

## Consequences

- Page-level retries repeat neither committed database work nor upstream
  acquisition for a still-fresh page.
- Downstream readers see either the previously complete dataset group or the
  newly completed group, never a newly staged partial group.
- Changed page content creates a new immutable page dataset; unchanged content
  reuses the existing canonical dataset through a new generation-page
  membership and renews its freshness attestation. Content can safely follow
  an `A -> B -> A` lifecycle.
- The filesystem quota ledger is deliberately a single-host/shared-cache
  contract. Multi-host provider admission requires a shared rate-limit service
  or provider gateway before those sources can be approved for production.
- Default source descriptors remain `APPROVAL_REQUIRED`; this ADR authorizes no
  live scrape, provider-rights change or production rollout.

## Verification contract

- cold then warm cache yields the same artifact digest and zero warm upstream
  requests;
- invalid/stale/future cache attestations fail closed;
- identical replay creates no duplicate dataset or observation;
- failure after page N commits page N, then retry replays it and fetches N+1;
- terminal publication rejects a page group with a missing predecessor;
- mixed artifact generations cannot publish, old published generations cannot
  satisfy a new run, and successful replacement supersedes the former head;
- identical, reverted and authoritative empty generations advance the head
  without content duplication or stale publication;
- concurrent warm/refresh persistence converges on one dataset and observation;
- clean PostgreSQL migration reaches revision `034` with no autogenerate drift;
- concurrency, stale-fence, cross-cache idempotency, generation isolation and
  staged-page replay gates run against an isolated PostgreSQL database.

## Rollback

Close admission for the two soccerdata task types or keep every upstream source
unapproved. Existing checkpoints, staged pages, observations and lineage remain
auditable; no destructive downgrade or historical deletion is automatic.
