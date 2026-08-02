# ADR: Governed penaltyblog model pipeline

- Date: 2026-08-01
- Status: Accepted
- Scope: G005 / PDP-400..407

## Context

The legacy prediction path fits a model while serving each target and can use
ad-hoc `Match` rows without proving the provider generation, observation time,
identity decision, model configuration, runtime, serialized bytes, or odds
snapshot that produced the output. That path remains available for analysis,
but it is not the governed P4 contract.

## Decision

The backend owns a versioned `penaltyblog-model-pipeline/v1` boundary:

1. A strict feature schema and model spec are fingerprinted with canonical JSON
   that rejects unknown fields, unsupported values and non-finite numbers.
2. Training pins one published `ProviderDatasetGeneration`, verifies exact page
   membership, accepted observations, retained bodies, temporal cutoffs and
   accepted match mappings, then writes a content-addressed feature artifact.
3. The approved deterministic penaltyblog model is fitted once. Its pickle is
   opaque trusted execution state: only the model-cpu subprocess writes/loads
   it beneath `BET_MODEL_ARTIFACT_ROOT`; byte digest and exact runtime
   fingerprint are verified before load.
4. Runtime attestation binds Python, penaltyblog version and exact Git revision,
   NumPy/SciPy/Pandas, `uv.lock`, image digest when available and BLAS threads.
5. `train_model`, `backtest_model` and `predict_model` are distinct immutable
   scheduled commands routed to `model-cpu`; Redis transports only the durable
   run ID. Enqueue snapshots and digests are revalidated by the worker.
6. Batch prediction loads the artifact once and calls `predict_many` once. A run
   is `completed` only for an exact output count and valid finite 1X2
   probabilities. Every governed prediction binds the model version, pinned
   generation, backend execution time as forecast time, output fingerprint and
   a complete same-match odds snapshot observed no later than forecast and
   before kickoff. Team and kickoff metadata come from the pinned observation,
   not from a later mutable `Match` row.
7. Historical holdout evaluation verifies and loads the exact pinned model and
   feature artifacts; it does not silently refit and attribute a different
   model. It persists Brier score, log loss, accuracy, expected calibration
   error, resolved quality rate, coverage, fold evidence, forecast time and odds
   lineage. Training observations after the model cutoff fail closed. Realized
   scores come from the pinned result observation rather than mutable match
   state. Results observed after their historical forecast remain retrospective
   evidence and are not prospective certification proof.
8. Governed ticket use requires a completed run, exact run/model fingerprints,
   the exact typed training artifact, a complete odds-bound prediction count and
   recomputed output fingerprint, plus the existing certification/monitoring
   gate. P4 runs without a model version/artifact are rejected. Legacy
   unversioned compatibility remains isolated outside the P4 contract.

The artifact volume is durable and shared by API verification and the model-cpu
worker in development and production Compose. A one-shot root initializer owns
the mounted volume for the unprivileged runtime UID. Model workers run the
image-installed penaltyblog interpreter rather than a host virtualenv symlink.
Production images inject the exact penaltyblog revision because Git metadata is
not copied into the image. PostgreSQL prevents update/delete of terminal
artifact evidence, and pickle verification plus deserialization use the same
bounded byte snapshot. Governed ticket exposure revalidates the exact
prediction-run output fingerprint before using pinned team, kickoff and
competition data. A trigger plus an indexed `RESTRICT` foreign key prevent run
deletion from downgrading retained ticket lineage, including concurrent
insert/delete races. The foreign key is initially `NOT VALID` to preserve one
known legacy orphan for explicit reconciliation while still enforcing all new
references and parent deletions.

## Model allowlist

- `PoissonGoalsModel`
- `DixonColesGoalModel`
- `BivariatePoissonGoalModel`
- `NegativeBinomialGoalModel`
- `ZeroInflatedPoissonGoalsModel`

Bayesian and Weibull variants remain analysis-only until deterministic seeding
and reproducibility are proven.

## Performance decision

The serialized single-load batch subprocess replaces per-target refitting. An
offline host benchmark over 80 generated rows and four targets preserved exact
1X2 parity and reduced the prediction path by 74.7%. This is smoke evidence, not a
formal production p95 claim. A resident/preloaded worker stays disabled unless
exact parity, process isolation, RSS below 4 GiB and either at least 40% lower
p50 or 30% fewer seconds/result are all demonstrated.

## Consequences

- Pickle remains a code-execution format, so storage keys can never be supplied
  by clients and load is forbidden outside the digest/runtime-gated subprocess.
- Artifact publication is append-only; rollback retires/disables a model
  version but preserves inputs, evaluations, outputs and audit history.
- The initial contract deliberately binds one primary provider generation.
  Multi-source features require a later explicit artifact-generation junction.
- No live provider call, ticket activation, deployment or public rollout is
  authorized by this ADR.
