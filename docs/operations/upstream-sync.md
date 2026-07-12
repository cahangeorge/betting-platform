# Upstream sync policy for vendored forks

The platform owns the four forked dependencies below. Their current `master`
branches are preserved as historical source branches and are never force-pushed
or rewritten by automation.

| Local project | Upstream | Platform integration branch |
| --- | --- | --- |
| `OddsHarvester` | `jordantete/OddsHarvester` | `platform` |
| `penaltyblog` | `martineastwood/penaltyblog` | `platform` |
| `soccerdata` | `probberechts/soccerdata` | `platform` |
| `flumine` | `betcode-org/flumine` | `platform` |

Each project has a weekly `.github/workflows/upstream-sync.yml` workflow. Its
first run creates `platform` from the configured `BOOTSTRAP_BRANCH` (the active
custom fork branch for OddsHarvester and `master` for the other projects);
later runs:

1. fetch the named upstream `master`;
2. create a `sync/upstream-<run-id>` merge candidate against `platform`;
3. restore the reviewed `.github/workflows` configuration from `platform`;
4. run the project-specific test command;
5. fast-forward `platform` directly, only after the merge candidate passes its
   project-specific test gate.

Merge conflicts, test failures, and a concurrent update of `platform` leave
`platform` unchanged. The workflow never force-pushes `master` or `platform`.

## One-time GitHub settings

For every fork, open **Settings → Actions → General** and set **Workflow
permissions** to **Read and write permissions**. This lets the repository's
short-lived `GITHUB_TOKEN` update the two managed branches and open a conflict
issue; no app, personal token, or additional secret is required.

The first scheduled or manual dispatch performs the initial upstream comparison.
The workflow's own tests are the required gate, so do not add branch protection
that blocks GitHub Actions from pushing to `platform`. A missing test-data
credential or a failed test fails closed: `platform` remains unchanged.
