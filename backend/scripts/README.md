# Backend operational scripts

## E2E fixture cleanup

`cleanup_e2e_fixtures.py` inventories only fixtures matching the exact namespace
created by Playwright: `13 digit timestamp + hyphen + 8 lowercase alphanumerics`.
User rows require the exact generated email
`e2e-<namespace>@example.com`; the display name is reported context rather than
a deletion key so legacy fixture names may drift without hiding stale users.

Dry-run is the default and makes no changes:

```bash
cd backend
./.venv/bin/python -m scripts.cleanup_e2e_fixtures
```

The report includes dependency counts and cross-reference blockers. Applying a
plan requires both an explicit flag and confirmation phrase:

```bash
./.venv/bin/python -m scripts.cleanup_e2e_fixtures \
  --apply \
  --confirm-token DELETE-ONLY-E2E-FIXTURES
```

The token may instead be supplied as
`BET_E2E_CLEANUP_CONFIRMATION=DELETE-ONLY-E2E-FIXTURES`. The apply path runs in
one transaction and deletes in FK-safe child-to-parent order. It refuses plans
where E2E-named strategies, datasets, batches, or matches are referenced by
non-E2E records. Never run `--apply` against production without reviewing the
complete dry-run output and database backup policy.

## Strategy CRUD isolation decision

Strategy CRUD remains available to authenticated users because the current
product contract explicitly lets users create, edit, and duplicate strategies.
The existing `strategies` table has no owner column, so switching only the API
to admin-only would silently break that contract without solving ownership.

For a multi-tenant deployment, implement a migration that distinguishes global
system templates from user-owned strategies, for example nullable
`strategies.user_id` plus immutable/admin-managed system rows. Then scope list,
read, update, delete, duplicate, analysis selection, and E2E cleanup to that
ownership model. Until that coordinated migration is approved, admin-only CRUD
is intentionally not applied.
