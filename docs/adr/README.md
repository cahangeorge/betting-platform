# Architecture Decision Records

Use this directory for durable Bet decisions that affect multiple components,
are costly to reverse, concern security/auth/data/infrastructure, have serious
alternatives, or are likely to be reopened later. Routine session state belongs
in `docs/status/current-platform-status.md`, not in an ADR.

## Naming and lifecycle

- Name new records `YYYY-MM-DD-short-decision-title.md` to match the existing
  repository convention.
- Use one of: `Proposed`, `Accepted`, `Deprecated`, or
  `Superseded by <relative ADR path>`.
- Never delete an accepted historical ADR. Add a new ADR and mark the old one
  superseded when the decision changes.
- Link implementation files and verification evidence, but do not copy large
  code or transcript sections.

## Template

```markdown
# ADR: Short decision title

Date: YYYY-MM-DD
Status: Proposed | Accepted | Deprecated | Superseded by ...

## Context

What problem, constraints, and forces require a durable decision?

## Decision

What was chosen and what is explicitly in or out of scope?

## Alternatives considered

- Option: benefits, costs, and why it was not selected.

## Consequences

- Positive, negative, operational, security, and migration consequences.

## Verification and references

- Relevant implementation paths, plans, test commands, or successor ADRs.
```

The existing Taskiq decision predates this template and remains valid; improve
or supersede it only when its underlying decision changes.
