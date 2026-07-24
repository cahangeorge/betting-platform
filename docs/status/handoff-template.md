# Bet Session Handoff Template

Copy the sections below into `docs/status/current-platform-status.md`; do not
create competing current-status files. Replace every placeholder and preserve
older evidence only when its date and historical nature remain explicit.

```markdown
# Current Platform Status

Updated: YYYY-MM-DDTHH:MM:SS+TZ
Repository/branch: `/home/gion/Projects/bet` / `branch-name`
Dirty state: exact `git status --short` summary, or `clean`

## Objective

One concrete outcome for the active work.

## Completed

- Durable facts implemented in the current working tree.

## Fresh verification

- `exact command` -> exact concise result and timestamp/date.

## Not completed / not verified

- Work that remains or claims carried forward without a fresh check.

## Blockers and risks

- A concrete blocker/risk, or `None known`.

## Exact next step

1. One executable next action, including the relevant path or command.
```

Do not write “tests pass”, “almost done”, or “looks good” without exact current
evidence. Never include credentials, tokens, cookies, private connection URLs,
or copied transcript content.
