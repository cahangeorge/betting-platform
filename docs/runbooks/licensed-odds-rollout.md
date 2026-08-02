# Licensed odds lane rollout and rollback

Status: offline contract only. No provider has commercial approval, retention
approval, credentials or live-call authorization.

## Admission sequence

1. Keep the default Sportmonks and OddsHarvester source descriptors
   `APPROVAL_REQUIRED`.
2. Record written rights/retention/model-use/display approval and approved
   source descriptor in a reviewed change. Credential presence alone is never
   approval.
   The approved descriptor must express the purchased quota unit/window
   exactly; the current runtime must not approximate per-entity/hour terms with
   its RPM-only Sportmonks admission path.
3. Run mocked contract/migration/quota/parity verification.
4. In an approved staging environment, preregister workload strata, original
   job IDs, structural keys, success definition, non-inferiority assumptions,
   sample size, latency method and exclusions.
5. Admit deterministic monotonic cohorts at 10/25/50/100. Each stage requires
   at least 20 unique original logical jobs as smoke evidence. Retries are not
   independent observations. A 100% evidence cohort is not public release.

The scheduled command is `licensed-odds-job/v1` with only `scope` and
`canary_stage_percent`. It contains no URL, credential, policy override or
fallback flag. Cohort identity is stable for the scheduled run and scope, so
delivery retries remain in the same bucket while recurring runs sample the
configured percentage. Excluded runs return
`licensed_odds_canary_excluded` before quota admission.

## Quota reservation and recovery

1. Reap expired reservations in a short committed transaction.
2. Configure/lock the source runtime state, create a unique reservation and
   commit it before network egress.
3. Perform HTTP without a database transaction or runtime-state row lock.
4. Commit accepted immutable ProviderObservations as the recovery payload.
5. Reconcile the reservation exactly once in a fresh short transaction.
6. A charged or released reservation is terminal. A duplicate acquisition key
   returns an explicit no-egress result rather than calling the provider again.
7. If reconciliation fails after staging, a retry reloads the observation IDs
   and reconciles with zero new egress. If no payload was committed, expiry
   changes the reservation to `uncertain`, charges it conservatively and opens
   the circuit; automatic retries must not guess whether the provider was called.

## Promotion gates

- Structural parity denominator is the union of comparable canonical
  match/bookmaker/market/period/line/selection keys. Unknown/unmapped keys are
  gaps, not exclusions. The one-sided 95% Wilson lower bound must be at least
  99% before speed is considered.
- Price differences are reported separately because asynchronous provider
  updates make exact volatile-price equality an invalid structural gate.
- Success non-inferiority uses a one-sided 95% lower bound on candidate minus
  baseline and must remain at least -1 percentage point. Sample size is
  computed before collection for at least 80% power.
- p95 uses nearest rank per preregistered stratum. Fewer than 100 original jobs
  is provisional; eligible strata use a seeded bootstrap interval.
- RSS, quota, credential-redaction and provider-rights gates from the canonical
  plan remain mandatory.

## Fallback

A provider-http run never launches OddsHarvester directly. It may emit a bounded
correlated fallback request for `quota_exhausted`, `timeout`, `upstream_5xx` or
`transient_circuit_open` only when both source descriptors and fallback policy
are approved. Control/outbox then creates a separate `provider-browser` run.
Authorization, credential, rights, policy and schema failures never fall back.
Every request fixes competition/market/window/event/page bounds.

The licensed scheduler does not auto-enqueue fallback today because its command
does not yet contain that bounded scope. A future integration must add the
immutable bounds, authorize both sources, then persist a separate
`provider-browser` outbox entry. A reason code alone never launches a browser.

## Rollback

1. Set candidate admission to 0; do not disable consumers needed to drain work.
2. Drain already admitted provider-http runs under their original queue/fence.
3. Restore the prior approved source selector.
4. Keep immutable observations, snapshots, parity reports and queue history.
5. Do not delete, rewrite, retry under a different source identity or count
   fallback attempts as original jobs.
6. Quota exhaustion makes zero upstream calls and returns an explicit outcome.

## Offline evidence boundary

`backend/scripts/benchmark_odds_provider_contracts.py` runs provider-shaped
fixtures only: no network and no browser. It validates common normalization,
deterministic cohorts and statistical calculations, but sets
`promotion_proof=false`. Live `PDP-505`/`PDP-505A` remain blocked on commercial
approval, credentials, preregistration and sufficiently powered observations.
