# Production release, rollback, and PostgreSQL recovery

## Scope and non-goals

`deploy/production/compose.yml` is a **production topology template**, not an automatic deployment system. It runs only immutable images, has no source mounts or reload commands, keeps PostgreSQL and Redis on the internal network, and runs migrations once before API, worker, scheduler, frontend, and TLS nginx start.

The external platform must provide: a private registry, a secret manager, DNS, TLS certificate/key material, durable backup storage, staging, monitoring/alerting, and an operator with production authority. The scripts deliberately fail if these are absent.

## Required release inputs

Create a secret-manager-rendered environment file outside Git from `deploy/production/.env.example`.

- Every image variable must be `image@sha256:<64 hex>`; mutable tags and `latest` are rejected.
- TLS paths must point to certificate/key files already deployed on the host or
  mounted by the platform. The nginx image runs as UID/GID `101`; both files
  must be readable by that identity without making the private key
  world-readable.
- PostgreSQL and application secret values have no development defaults.
- Redis requires one raw password plus authenticated DB 0/DB 1 URLs. Percent-encode
  reserved password characters in `BET_REDIS_URL` and
  `BET_TASKIQ_RESULT_BACKEND_URL`; never copy the raw value into logs or Git.
- The bundled topology assumes PostgreSQL and Redis remain on the same protected
  host/private network. A cross-host deployment requires encrypted transport
  (`sslmode` for PostgreSQL and `rediss://` for Redis) before launch.
- Container CPU, memory, PID, and local-log ceilings are conservative starting
  values. Tune them from staging measurements; do not remove the ceilings to
  conceal capacity or disk-retention problems.
- Keep the last known-good immutable environment file in protected release storage. It is the rollback manifest.

Validate the template without rendering or printing resolved secret values:

```bash
scripts/release/render.sh /secure/bet/release.env
```

## First deployment bootstrap

`deploy.sh` is deliberately an upgrade-only path: it requires an existing
known-good manifest and a running PostgreSQL service so it can take a mandatory
pre-deploy backup. A new host has neither. Bootstrap it exactly once with the
separate fail-closed command:

```bash
BET_BOOTSTRAP_CONFIRM=BOOTSTRAP scripts/release/bootstrap.sh \
  /secure/bet/release.env \
  https://bet.example.com \
  /secure/bet/known-good-release.env
```

Bootstrap refuses an existing known-good path, validates immutable images and
required values, pulls the images, starts the complete topology, runs the same
mandatory smoke, and only then records the first known-good manifest. If smoke
fails, it stops candidate containers without deleting PostgreSQL or Redis
volumes. Inspect and explicitly clean a failed first-deployment state before
retrying; never use bootstrap for an upgrade.

## Release procedure

1. Trigger the tag release only from a reviewed clean revision. Its
   `verify-source` job must pass Alembic upgrade/drift, backend Ruff/pytest,
   frontend static/unit/build, and the complete retry-free Chromium hybrid
   suite before image work starts. Every third-party action must resolve from
   its reviewed full commit SHA.
2. Produce and vulnerability-scan API, frontend, and nginx images in CI;
   publish their registry digests, SBOMs, signatures/attestations, and retained
   image-identity evidence to the release record. The repository workflow
   preserves the exact scanned images, publishes them first under
   `sha-<git-sha>`, captures authoritative GHCR digests, signs and verifies each
   digest with keyless Cosign, creates and verifies GitHub provenance
   attestations, then promotes the protected version tag. A manual dispatch is
   evidence-only and cannot publish.
3. Deploy the exact release environment file to staging; run migrations, smoke
   tests, UI/E2E, worker/scheduler health checks, and backup/restore rehearsal
   there. Before promotion, prove the previous application images still start
   and pass their mandatory smoke against the post-migration staging schema.
   MVP migrations must be expand-only and backward compatible; destructive
   contract/drop work is split into a later release after every old application
   version is retired.
4. For every upgrade after bootstrap, ensure the protected backup directory
   exists and has enough free space. The deploy command creates a mandatory
   pre-deploy archive there before changing services.
5. Submit the immutable production topology and require its HTTPS, Taskiq, and
   provider smoke to pass:
   ```bash
   scripts/release/deploy.sh \
     /secure/bet/release.env \
     /secure/bet/backups \
     https://bet.example.com \
     /secure/bet/known-good-release.env
   ```
6. Verify the newly created backup archive independently:
   ```bash
   scripts/db/verify-postgres-backup.sh /secure/bet/backups/bet-postgres-<timestamp>.dump
   ```
   The deploy command fails unless the smoke succeeds. Before activation it
   snapshots the supplied known-good immutable manifest; if activation or the
   mandatory smoke fails, it automatically restores that snapshot and waits for
   the application services to be healthy. After a successful smoke it records
   the candidate as the new known-good manifest atomically. That smoke validates
   public TLS, `/health`, `/ready`, the frontend, a real Redis/Taskiq round-trip, and an internal
   provider canary for penaltyblog prediction, soccerdata loading, and a
   headless OddsHarvester Chromium launch.
7. In staging, run the live upstream scrape suite and the authenticated
   dataset → prediction → ticket → settlement canary before promotion. Internal
   provider readiness does not replace this upstream-dependent gate.
8. Observe application logs, PostgreSQL, Redis, worker queue lag, scheduler
   runs, error rate, and authentication flows before declaring success.

Do not run two migration jobs concurrently. Compose gates API, worker, and scheduler on the one-shot `migrate` service finishing successfully.

## Protected GHCR publication and signing

Before the first release tag:

1. Create the GitHub environment `registry-release`; protect it with a `v*`
   deployment rule, an independent required reviewer, prevention of self-review,
   and no administrative bypass where the repository plan supports those
   controls.
2. Add a tag ruleset that restricts creation, update, deletion, and force-push
   for `v*`. A tag author otherwise has effective release authority.
3. Confirm GitHub Actions can create or update the three repository-linked
   packages:
   `ghcr.io/<owner>/<repo>-api`,
   `ghcr.io/<owner>/<repo>-frontend`, and
   `ghcr.io/<owner>/<repo>-nginx`.
4. Decide package visibility explicitly. New GHCR packages may not be public,
   and changing visibility is an administrative release decision.
5. Approve the privacy characteristics of public Sigstore Fulcio/Rekor before
   keyless signing a private repository. The workflow identity is included in
   the certificate and transparency record.
6. Confirm the repository plan supports artifact attestations. Private/internal
   repository attestations require the applicable GitHub Enterprise Cloud
   entitlement; without it, the protected release is expected to stop at the
   attestation gate.

The workflow uses only the scoped `GITHUB_TOKEN` for GHCR and ephemeral GitHub
OIDC for Cosign and `actions/attest`; no registry PAT, Cosign private key, or
Cosign password is required. It refuses to overwrite an existing SHA or version
reference. Deployment manifests must use the recorded
`ghcr.io/...@sha256:<digest>` values, never either tag.

Approve or reject `registry-release` within 30 days. The exact scanned-image
handoff artifact is retained for 30 days to match GitHub's maximum environment
wait; after expiry, cancel the run and create a new reviewed version tag rather
than rebuilding under the old tag.

A successful protected tag retains:

- local image identities and three CycloneDX SBOMs;
- exact registry names and digests;
- exact Cosign workflow identity and OIDC issuer;
- three GitHub attestation URLs;
- proof that the SHA tag and version tag resolve to the same digest.

Rerun the release contract only with a new version tag. A rerun of an existing
tag is expected to fail closed rather than overwrite published evidence.

Publication is intentionally conservative but is not registry-transactional.
If a job stops after publishing only some SHA references or version tags:

1. mark the version quarantined and do not deploy any of its images;
2. retain the failed workflow evidence and enumerate every created digest/tag;
3. have a registry administrator remove only the quarantined partial
   references after confirming they were never deployed, or retain them under
   a documented failed-release retention policy;
4. fix the cause in a new reviewed revision and issue a new version tag;
5. never rerun or overwrite the partially published version.

## Rollback

Use the protected previous immutable manifest; do not edit image tags in place:

```bash
scripts/release/rollback.sh \
  /secure/bet/current.env \
  /secure/bet/previous-good.env \
  https://bet.example.com
```

Rollback switches application images, waits for them to become healthy, and
fails unless the previous manifest passes the same mandatory smoke. It does
**not** reverse Alembic migrations automatically or pretend that PostgreSQL and
Redis state can be rolled back like stateless images. The release is permitted
only after the previous application version has passed staging smoke against
the upgraded schema. Any non-expand-only migration needs an explicitly tested
restore/downgrade recovery plan and a separate maintenance decision before it
can be released.

## Database restore (destructive)

Restore is intentionally gated by `BET_RESTORE_CONFIRM=RESTORE`, verifies
SHA-256 plus PostgreSQL archive format, stops traffic-serving services,
restores, runs the selected image's one-shot Alembic migration to head, then
restarts them:

```bash
BET_RESTORE_CONFIRM=RESTORE scripts/db/restore-postgres.sh \
  /secure/bet/release.env /secure/bet/backups/bet-postgres-<timestamp>.dump
```

Immediately execute release smoke plus application integrity checks. A restore rehearsal in staging is required before public MVP launch.

## Explicit launch blockers not solved by repository files

- A successful protected disposable tag proving GHCR publication, Cosign and
  GitHub attestation verification, digest-pinned pull/run smoke, package
  retention/visibility, and overwrite refusal.
- Secret-manager injection and rotation, including revocation of the tracked third-party credential identified by security review.
- DNS, valid public TLS certificate issuance/renewal, and network/firewall policy.
- Off-host encrypted backup retention and tested object-store recovery.
- Staging deployment, real browser/E2E and worker/scheduler failure-recovery evidence.
- Production metrics, logs, traces, alerts, on-call ownership, and incident response.
