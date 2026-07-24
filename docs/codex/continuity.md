# Bet Continuity and Memory Policy

This document is the operational continuity contract for the Bet repository.
It complements the mandatory rules in `AGENTS.md`; it does not replace them.

## Canonical sources

When two sources disagree, use this order:

1. Current files and fresh runtime/test evidence.
2. `git status`, `git diff`, commits, and repository history.
3. `docs/status/current-platform-status.md` and accepted ADRs.
4. An approved issue tracker, if one is configured later.
5. Serena and the `bet-core` Codebase Memory index.
6. Codex Memories and other semantic recall.
7. Old transcripts or unverified summaries.

Retrieval tools locate evidence; they do not override the repository. The
canonical status contains current session state, while ADRs contain durable
decisions and their rationale.

## Start-of-session workflow

From `/home/gion/Projects/bet`:

```bash
pwd
git status --short --branch
git submodule status
cat AGENTS.md
cat docs/status/current-platform-status.md
```

Then:

1. Read only the ADRs relevant to the requested work.
2. Compare status claims with current source, Git, or the smallest useful test.
3. Run `codebase-memory-mcp cli index_status --project bet-core` and
   `codebase-memory-mcp cli detect_changes --project bet-core` before relying
   on the structural index for impact analysis.
4. Use Serena or `rg` to confirm exact symbols and references.
5. State the confirmed repository/branch, dirty state, objective, fresh
   evidence, blockers, and next step before editing.

Use Codex `resume` for the same unresolved task when exact conversational
context matters. Prefer a new session when the objective changed or this
contract and the canonical status provide enough handoff context.

## End-of-session workflow

1. Run the smallest checks that prove the changed behavior or documentation.
2. Update `docs/status/current-platform-status.md` using
   `docs/status/handoff-template.md`; preserve useful prior evidence as clearly
   dated history.
3. Create or update an ADR only for a durable, material decision.
4. Record blockers, unverified work, and one exact next step.
5. Run `serena memories check` if Serena memories changed.
6. Detect Codebase Memory changes and reindex only when the criteria below are
   met.
7. Create a Git checkpoint only when explicitly requested; never commit or push
   automatically.
8. Confirm that no credentials or sensitive values entered tracked files or
   semantic memories.

## Codebase Memory

The repository is indexed as `bet-core`. Automatic indexing and watching are
disabled, so freshness is explicit and deterministic.

Status and change detection:

```bash
codebase-memory-mcp cli index_status --project bet-core
codebase-memory-mcp cli detect_changes --project bet-core
```

Reindex after structural source changes, moved/added symbols, route or schema
changes, dependency-boundary changes, or any `.cbmignore` change. Also reindex
before high-impact analysis if `detect_changes` reports relevant source files.
Minor prose-only edits do not require reindexing unless indexed ADR discovery
must be refreshed.

Run the deterministic refresh from the repository root:

```bash
codebase-memory-mcp cli index_repository \
  --repo-path /home/gion/Projects/bet \
  --name bet-core \
  --mode moderate
codebase-memory-mcp cli detect_changes --project bet-core
codebase-memory-mcp cli index_status --project bet-core
```

Success means `index_status` reports `ready` and `detect_changes` is reconciled
with the real Git dirty state. A clean repository should report no changed
files. An intentionally dirty repository will continue to report working-tree
paths after reindexing because change detection is Git-relative; reindexing must
not be mistaken for committing those files. `.cbmignore` is a versionable
security and scope artifact; review its diff before every refresh. Codebase
Memory indexes are regenerable and are not a canonical backup.

## Serena and semantic memory

- Use Serena for symbol navigation, references, and deliberate durable notes.
- Keep `mem:core` as the discovery root and preserve valid `mem:` references.
- Run `serena memories check` after memory edits or major refactors.
- Store only stable, non-obvious conventions that would otherwise require
  costly rediscovery.
- Do not store transient test results, daily task state, transcript copies,
  credentials, tokens, cookies, private URLs, or connection strings.
- Correct stale or sensitive Codex Memories through the supported memory-update
  note workflow; do not treat a remembered statement as current evidence.

## Retention and backup

| Asset | Retention | Backup/recovery |
| --- | --- | --- |
| Git source, `AGENTS.md`, status, ADRs, and tracked Serena memories | Keep in repository history; ADRs are superseded, not deleted | Authorized Git remote after an intentional commit/push |
| Current status | Keep one canonical file; replace stale session state while retaining useful dated evidence | Git history after publication |
| Codex transcripts and local Codex Memories | Sensitive local working records, not the canonical project archive; this policy introduces no automatic deletion schedule | Promote durable decisions/results to versioned status or ADRs; any off-host backup or deletion schedule requires an explicit owner, audit need, retention period, and supported-tool procedure |
| Codebase Memory graph | No retention requirement | Regenerate from Git plus `.cbmignore`; backup is optional only to save indexing time |
| Secrets | Never retain in these layers | Approved secret manager or ignored local `.env` only |

Unpublished local files are not backed up merely because this policy exists.
Before cleanup or machine migration, verify that important versioned work is on
an authorized remote and export only the sensitive local history that has a
real audit requirement.

## Beads decision

Beads is deferred. Until explicitly approved and installed,
`docs/status/current-platform-status.md` is the canonical source for the active
objective, blockers, and exact next step; do not duplicate these in a local
task graph.

Reconsider a Beads pilot only if at least one of these persists:

- several long-lived tasks have real dependency/blocker relationships;
- multiple agents repeatedly lose ownership or readiness state across sessions;
- cross-repository work cannot be represented clearly in the canonical status
  and the existing remote issue tracker;
- a pilot owner can define backup, restore, and a single canonical task source.

Installing Beads, changing an external issue tracker, or making it canonical
requires explicit user approval and a documented migration decision.
