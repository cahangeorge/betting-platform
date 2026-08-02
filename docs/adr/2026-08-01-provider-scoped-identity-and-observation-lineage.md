# ADR: Provider-scoped identity and observation lineage

Date: 2026-08-01
Status: Accepted

## Context

`matches.id` is already the canonical key used by odds, statistics,
predictions, evaluations and tickets. Provider identity is not canonical:
`Match.external_id` is global and non-unique, while `MatchSource` stores only a
broad source string and source ID. Team and competition identity exists only as
text on `matches`.

Provider Envelope v2 now distinguishes adapter and upstream source, carries
version/job/run/correlation/freshness/provenance lineage and quarantines invalid
input before normalization. Persisting multiple providers without a separate
identity and observation model would reintroduce global external IDs, overwrite
conflicting observations and auto-promote ambiguous name matches.

The migration must be expand-only, remain compatible with the previous backend
image and preserve the existing dirty-worktree migration chain whose current
head is `029`.

## Decision

### Preserve the existing canonical Match key

- Keep `matches.id` as the canonical Match primary key.
- Add nullable `home_team_id`, `away_team_id` and `competition_id` foreign keys
  only after the new canonical tables exist.
- Keep `home_team`, `away_team`, `competition` and `external_id` unchanged for
  compatibility. They are not used as new provider uniqueness keys.
- Use `RESTRICT` for canonical identity foreign keys. Identity and mapping
  history is not deleted through ORM `delete-orphan` cascades.

### Add canonical Team and Competition entities

Create `teams` and `competitions` with stable integer primary keys, sport,
display name, normalized name, optional country code, lifecycle timestamps and
non-unique lookup indexes. Names are intentionally not globally unique.

### Use typed temporal provider mappings

Create separate Team, Competition and Match mapping tables. Each mapping has:

- `(adapter_key, source_key, source_id)` upstream identity;
- nullable canonical foreign key;
- state `pending_review`, `accepted` or `rejected`;
- confidence `NUMERIC(5,4)`, resolver kind/ID, rule version, reason and a
  deterministic decision digest;
- evidence observation, nullable typed `selected_candidate_id`,
  `predecessor_mapping_id`, `valid_from`, nullable `valid_to` and timestamps.

Database checks enforce:

- confidence is null or in `[0, 1]`;
- `valid_to` is null or later than `valid_from`;
- pending/rejected mappings have no canonical target;
- accepted mappings have a canonical target;
- pending/rejected mappings remain target-free whether open or closed.

There is one current row for an upstream identity across all states using a
partial unique index on `(adapter_key, source_key, source_id)` where
`valid_to IS NULL`. Mapping states are `pending_review`, `accepted` and
`rejected`; a closed accepted row already represents a superseded historical
decision, so no state rewrite is needed. Closing may change only `valid_to`,
closure timestamp and `closed_by_decision_digest`. Canonical target, original
state/digest, resolver, reason and evidence are immutable. The only exception
is the guarded E2E fixture cleanup: inside the same validated delete
transaction it may clear `selected_candidate_id` solely to break the mutual
`RESTRICT` cycle before deleting both the selected candidate and its complete
E2E-only mapping history. That exception is not available to production
retention or ordinary mapping commands.

Every transition closes the current row and inserts a new decision linked by
`predecessor_mapping_id`:

- no current row -> open `pending_review`;
- pending -> closed pending plus open accepted/rejected;
- rejected -> closed rejected plus new pending when new evidence arrives;
- accepted remap -> closed accepted plus new accepted.

The decision digest is SHA-256 over canonical JSON containing entity type,
adapter/source/source ID, new state, canonical target, predecessor, selected
candidate, evidence observation, resolver kind/ID, rule version, normalized
reason and confidence. Generated timestamps are excluded. A transaction-scoped
PostgreSQL advisory lock derived from `(entity_type, adapter_key, source_key,
source_id)` serializes first insert and every transition; unique-conflict retry
reloads the winner and compares the decision digest. Every command carries
`expected_predecessor_mapping_id`; after acquiring the lock, a mismatch is a
stale-decision error. A remap is a distinct explicit command and a stale accept
is never reinterpreted automatically as a remap.

An accepted decision with `selected_candidate_id` must reference a candidate
owned by the predecessor pending mapping and its canonical target must equal the
accepted target. The FK uses `RESTRICT`. Direct deterministic resolutions may
leave it null.

Pending mappings are the review queue. Candidate targets are stored in three
typed candidate tables rather than an unvalidated list of IDs in JSON. Each
candidate has mapping and canonical-target foreign keys using `RESTRICT`, a
positive rank, confidence in `[0, 1]` and redacted evidence. Unique constraints
cover `(mapping_id, canonical_target_id)` and `(mapping_id, rank)`; indexes cover
`(mapping_id, rank)` and the canonical target.

### Separate valid observations, conflicts and quarantine

`provider_observation_slots` owns one unique `observation_slot_key`. The ingest
transaction creates or locks this row before inserting any observation.

`provider_observations` stores only validated upstream facts. It preserves:

- adapter/source identity, capability and upstream source ID;
- normalized envelope and payload schema versions;
- timezone-aware observed/ingested timestamps;
- immutable freshness and allowlisted provenance;
- exact canonical `payload_json` and `envelope_json` text plus SHA-256 digests;
- deterministic `observation_key` and `observation_slot_key`;
- normalization/conflict state and retention timestamps.

Keys are SHA-256 over canonical JSON arrays with timezone normalized to UTC:

```text
observation_key = SHA256([
  adapter_key, source_key, capability, source_id, observed_at_utc,
  envelope_version, schema_version, payload_digest
])
observation_slot_key = SHA256([
  adapter_key, source_key, capability, source_id, observed_at_utc,
  envelope_version, schema_version
])
```

`(adapter_key, source_key, observation_key)` is unique, so exact replay returns
the existing row. Two different payloads in the same slot are both retained
and linked through `provider_observation_conflicts`; neither is promoted
automatically. Conflict rows use `left_observation_id < right_observation_id`,
unique `(left_observation_id, right_observation_id)`, `RESTRICT` on both
foreign keys and an indexed slot key. The service verifies both observations
have the same slot key and inserts the canonical ordered pair with
`ON CONFLICT DO NOTHING`.

Slot serialization is atomic: the same transaction (1) creates/locks the slot,
(2) inserts or resolves exact replay, (3) links every different-digest sibling,
(4) marks the affected observations/slot conflicted and (5) commits. A real
PostgreSQL test must start two different-payload transactions against an empty
slot and prove that both observations and their conflict row survive.

`provider_observation_receipts` is append-only ingestion lineage. Every
occurrence records observation FK (`RESTRICT`), provider job/run/correlation,
adapter/transport/conversion versions, exact received envelope text/digest,
received timestamp, immutable snapshot values for internal
scrape-job/scheduled-run/origin-dataset IDs, and separate nullable convenience
FKs. Its deterministic receipt key hashes observation key, provider IDs,
versions, envelope digest and immutable snapshot IDs; it is unique per source.
Exact fact replay therefore reuses the observation but persists a separate
receipt when run or envelope lineage differs.

Invalid or unsupported envelopes use a separate
`provider_observation_quarantine` table containing only raw digest, stable
reason code, reader version, fully redacted diagnostic metadata and retention
timestamps. It never stores raw payloads, headers, cookies or credentials.

Internal scrape-job, scheduled-run and origin-dataset foreign keys on receipts
are convenience links using `SET NULL`; immutable external provider IDs and
digests remain. Dataset reuse is many-to-many through
`provider_observation_dataset_links`, unique on `(observation_id, dataset_id)`,
with `RESTRICT` on both sides. A dataset link means the fact was reused by that
dataset; `origin_dataset_id` on a receipt means that ingestion occurrence came
from it. Mapping evidence and candidate/conflict foreign keys use `RESTRICT`.

### Define v1 persistence explicitly

The v1 reader remains supported. A v1 record can enter accepted observation
storage only when a trusted caller supplies an explicit `source_key` and
`conversion_version`, and its `provider_key` matches the adapter identity. The
row stores `envelope_version='1.0'`, `original_envelope_version=NULL`,
`converted_from_v1=true` and the explicit conversion version. Otherwise it is
quarantined as missing source identity. No source identity is inferred from
`source_id` or a dataset name.

For v1, observation and receipt preserve the exact canonical original v1
envelope text/digest; they do not synthesize a v2 envelope. The supplied source
identity and conversion version are separate receipt/conversion fields. For v2,
the received and normalized envelope versions are identical.

Accepted persistence is secret-safe too: capability-specific payload schema
validation and recursive sensitive-key rejection run before writing canonical
payload/envelope text. Headers, cookies, credentials, tokens and request auth
metadata are never accepted as observation provenance or payload metadata.

### Deliver three expand-only revisions

1. Revision `030`: observation slots, validated facts, receipts, conflicts,
   dataset links and redacted quarantine; all are new tables.
2. Revision `031`: canonical Team/Competition, typed temporal mappings and
   candidate review tables, plus nullable/no-default Match foreign-key columns.
   Match constraints are added `NOT VALID` under bounded `lock_timeout` and
   `statement_timeout`; the migration does no table backfill.
3. Revision `032`: create the three Match FK indexes concurrently outside the
   DDL transaction, detect/drop invalid same-name indexes before retry, then
   validate the FK constraints under explicit timeouts.

Before `031/032`, record Match row count/table size, duplicate legacy source
tuples and expected lock budget. New mapping-table indexes are regular indexes
because the tables are empty. Failure recovery must leave `029/030/031`
operational and remove only an invalid concurrent index, never data.

The 2026-08-01 local preflight at revision `029` recorded 7,463 Match rows,
`pg_total_relation_size(matches)=2,162,688` bytes, and zero duplicate legacy
`(match_sources.source, source_id)` groups resolving to more than one Match.
The accepted migration lock budget is `lock_timeout=2s` and
`statement_timeout=10s`. These figures are evidence for the local development
snapshot, not a substitute for repeating the preflight on staging/production.

No migration backfills data, rewrites current Match strings, changes API
reads or enables a provider. Production rollback is the previous application
image on the expanded schema only before dual-write creates provider lineage.
After dual-write, the rollback target must be a cleanup/lineage-aware image;
the older image is not claimed compatible with provider-linked deletes.
Destructive downgrade is not the rollout plan.

Matches, canonical entities and datasets become delete-restricted while
provider lineage references them. The current image updates E2E cleanup to
delete provider conflicts/candidates/links/receipts/observations/mappings in
dependency order. Production retention tombstones bodies and entities rather
than erasing identity history. This is an intentional behavior change activated
only with dual-write.

### Backfill and retention gates

- Do not auto-backfill Team or Competition from names.
- Backfill an existing `MatchSource` only when one provider-scoped tuple maps to
  exactly one Match and the adapter/source identity is demonstrable.
- Do not invent observations for legacy datasets without a canonical envelope
  and digest.
- Keep identity decisions, source identity and all digests permanently.
- Canary/test accepted payload and envelope bodies default to 30 days.
  Production persistence fails closed until the source descriptor declares an
  approved retention period. Legal, dataset and model holds extend it.
- Accepted `payload_json` and `envelope_json` become null only when
  `body_purged_at` is non-null; a database check enforces the body/purge-state
  pair. Purge never removes lineage or digests.
- Receipt `received_envelope_json` follows the same source-policy deadline and
  becomes null only with `body_purged_at`; its envelope digest, receipt key and
  immutable internal ID snapshots remain permanent even when convenience FKs
  later become null.
- Quarantine never has a raw body. Its redacted diagnostic metadata defaults to
  30 days and becomes null only with `metadata_purged_at`; raw digest, reader
  version and reason code remain permanent.
- Do not activate purge until dependency-aware retention tests pass.

## Alternatives considered

- **Replace `matches` with a new canonical Match table:** rejected because it
  would migrate every odds, prediction, evaluation and ticket foreign key.
- **Extend `MatchSource` only:** rejected because it cannot model Team or
  Competition identity, temporal remaps, candidates or observation lineage.
- **One polymorphic mapping table:** rejected because conditional foreign keys
  and state checks are weaker and ORM behavior is more fragile.
- **One observation table including quarantine:** rejected because invalid
  input may lack trusted source, time or schema fields and must not retain raw
  data.
- **Unique normalized names:** rejected because clubs and competitions can
  share names across country, level, season and sport.
- **One combined migration:** rejected to keep observation replay semantics and
  canonical identity review independently reversible at the application layer.

## Consequences

Positive:

- provider replay, conflict and mapping decisions become deterministic and
  auditable;
- ambiguous entities remain reviewable instead of being auto-promoted;
- existing API/read paths continue to work, and the previous image remains
  compatible during the schema-before-dual-write phase;
- downstream datasets and predictions can cite immutable observation and
  mapping versions.

Negative:

- typed mappings and candidates add several tables and some deliberate schema
  duplication;
- dual-write/resolver adoption is a later feature-flagged step;
- real PostgreSQL concurrency and previous-image compatibility evidence is
  mandatory before promotion;
- retention policy remains blocked for sources without approved data rights.

## Verification and references

Required before promoting the migration implementation:

- clean database upgrade `001 -> head` and existing database `029 -> head`;
- previous backend image smoke against the expanded schema;
- exact ORM/index/constraint alignment and `alembic check` review;
- concurrent identical replay produces one observation;
- same slot/different digest retains both observations and conflict evidence;
- simultaneous first-slot conflicting inserts cannot commit without a conflict
  row, and crash/retry between fact and conflict work remains atomic;
- exact replay from two different runs keeps one fact and two receipts;
- competing mapping decisions produce one current row;
- first pending insert, pending accept/reject, rejected-to-pending and competing
  remaps preserve predecessor/closed intervals and decision lineage;
- stale `expected_predecessor_mapping_id` commands fail without mutation, and a
  selected candidate must belong to the pending predecessor and match target;
- pending ambiguity cannot gain a canonical target or become accepted without
  an explicit decision;
- canonical deletion cannot erase observation or mapping history;
- v1 original-envelope/conversion, v2 persistence and quarantine secrecy tests;
- old-image read/write/delete smoke before dual-write and explicit failure or
  cleanup-aware rollback proof after lineage exists;
- observation/receipt/quarantine purge checks retain permanent digests, keys and
  immutable lineage snapshots;
- `031/032` lock-timeout, invalid-index cleanup and retry evidence.

References:

- `docs/architecture/provider-data-platform.md`
- `docs/plans/2026-08-01-provider-data-platform-execution-plan.md`
- `docs/adr/2026-08-01-provider-data-platform-architecture.md`
- `backend/app/models/match.py`
- `backend/app/models/scrape.py`
- `backend/app/models/odds_lineage.py`
- `backend/app/models/prediction.py`
- `backend/app/providers/contracts.py`
- `backend/app/services/scraper.py`
- `backend/app/services/analysis_flow.py`
