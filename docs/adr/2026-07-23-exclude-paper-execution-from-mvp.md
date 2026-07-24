# ADR: Exclude paper execution from the public MVP

Date: 2026-07-23
Status: Accepted

## Context

The current platform contains paper-execution code and local Compose defaults,
but its runtime depends on an ignored, non-reproducible `flumine/` checkout.
Readiness does not yet prove adapter availability, the accounting lifecycle is
not fully reconciled through settlement/P&L, and Redis publish/crash recovery
has not been demonstrated. Presenting this capability in the public MVP would
therefore overstate operational and financial correctness.

The core MVP value remains the authenticated Prepare -> Analyze ->
Opportunities -> Tickets -> Monitoring/settlement analytics workflow. It does
not require automatic paper or external order execution.

## Decision

- Public MVP deployments disable both live and paper execution.
- Ticket generation, review, activation, monitoring, and settlement analytics
  remain in scope.
- Production configuration must set `BET_TRADING_ENABLED=false` and
  `BET_TRADING_PAPER_ENABLED=false`.
- UI/API surfaces must not claim that an order was sent to a bookmaker or paper
  adapter when execution is disabled.
- Paper execution can return to release scope only through a successor ADR
  after reproducible dependency, adapter readiness, accounting, idempotency,
  queue recovery, and failure-injection gates pass.

## Alternatives considered

- Include paper execution now: rejected because a fresh clone cannot reproduce
  the adapter and current readiness/accounting evidence is incomplete.
- Remove all paper-execution code: rejected because the code can remain behind
  disabled capability flags while it is hardened post-MVP.
- Treat local manual demonstrations as sufficient: rejected because they do
  not prove settlement accounting, concurrency, or crash recovery.

## Consequences

- The MVP release surface is smaller and avoids misleading execution claims.
- `TRD-002` through `TRD-004` move out of mandatory MVP scope, but remain
  tracked post-MVP work.
- Production deployment and readiness checks must fail closed if execution is
  accidentally enabled without the required adapter/runtime contract.
- Paper execution can still be tested explicitly in isolated development
  environments; it is not a production-supported MVP capability.

## Verification and references

- Program register: `docs/status/mvp-readiness-program.md`
- Current config: `backend/app/config.py`
- Paper adapter: `backend/app/adapters/flumine_paper.py`
- Execution service: `backend/app/services/trading_execution.py`
- Required production check: rendered deployment environment contains both
  execution flags set to `false`.
