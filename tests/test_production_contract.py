from __future__ import annotations

import unittest
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


class ProductionContractTests(unittest.TestCase):
    @staticmethod
    def _manifest(api_digest: str) -> str:
        digest = "a" * 64
        return "\n".join(
            (
                f"POSTGRES_IMAGE=registry.example/postgres@sha256:{digest}",
                f"REDIS_IMAGE=registry.example/redis@sha256:{digest}",
                f"BET_API_IMAGE=registry.example/api@sha256:{api_digest}",
                f"BET_FRONTEND_IMAGE=registry.example/frontend@sha256:{digest}",
                f"NGINX_IMAGE=registry.example/nginx@sha256:{digest}",
                "BET_PUBLIC_HOST=bet.example.com",
                "BET_HTTP_PORT=80",
                "BET_HTTPS_PORT=443",
                "TLS_CERT_PATH=/secure/tls.crt",
                "TLS_KEY_PATH=/secure/tls.key",
                "POSTGRES_USER=release-user",
                "POSTGRES_PASSWORD=release-password",
                "POSTGRES_DB=bet",
                "BET_DATABASE_URL=postgresql+asyncpg://release-user:release-password@postgres/bet",
                "REDIS_PASSWORD=ci-redis-pass",
                "BET_REDIS_URL=redis://:ci-redis-pass@redis:6379/0",
                "BET_TASKIQ_RESULT_BACKEND_URL=redis://:ci-redis-pass@redis:6379/1",
                "BET_JWT_SECRET=release-jwt-secret",
                "",
            )
        )

    def test_deploy_smoke_failure_restores_known_good_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            docker_log = root / "docker.log"
            (bin_dir / "docker").write_text(
                "#!/bin/sh\n"
                'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n'
                "case \"$*\" in *'exec -T postgres pg_dump'*) printf 'fake-backup' ;; esac\n"
            )
            (bin_dir / "curl").write_text("#!/bin/sh\nexit 1\n")
            for command in (bin_dir / "docker", bin_dir / "curl"):
                command.chmod(0o755)

            candidate = root / "candidate.env"
            known_good = root / "known-good.env"
            candidate.write_text(self._manifest("b" * 64))
            original_known_good = self._manifest("c" * 64)
            known_good.write_text(original_known_good)
            backup_dir = root / "backups"
            backup_dir.mkdir()

            result = subprocess.run(
                [
                    str(ROOT / "scripts/release/deploy.sh"),
                    str(candidate),
                    str(backup_dir),
                    "https://bet.example.com",
                    str(known_good),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "DOCKER_LOG": str(docker_log),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "restoring the recorded known-good immutable manifest", result.stderr
            )
            self.assertEqual(known_good.read_text(), original_known_good)
            commands = docker_log.read_text()
            self.assertIn(
                "up --detach --remove-orphans --wait --wait-timeout 180", commands
            )
            self.assertIn(
                "up --detach --no-deps --wait --wait-timeout 180 api worker scheduler frontend nginx",
                commands,
            )

    def test_first_deployment_bootstrap_records_initial_known_good_without_backup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            docker_log = root / "docker.log"
            (bin_dir / "docker").write_text(
                '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$DOCKER_LOG"\nexit 0\n'
            )
            (bin_dir / "curl").write_text("#!/bin/sh\nexit 0\n")
            for command in (bin_dir / "docker", bin_dir / "curl"):
                command.chmod(0o755)

            candidate = root / "candidate.env"
            candidate.write_text(self._manifest("b" * 64))
            known_good = root / "known-good.env"

            result = subprocess.run(
                [
                    str(ROOT / "scripts/release/bootstrap.sh"),
                    str(candidate),
                    "https://bet.example.com",
                    str(known_good),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "DOCKER_LOG": str(docker_log),
                    "BET_BOOTSTRAP_CONFIRM": "BOOTSTRAP",
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(known_good.read_text(), candidate.read_text())
            commands = docker_log.read_text()
            self.assertIn(
                "up --detach --remove-orphans --wait --wait-timeout 180", commands
            )
            self.assertNotIn("pg_dump", commands)

    def test_compose_forces_secure_runtime_and_disables_execution(self) -> None:
        compose = (ROOT / "deploy/production/compose.yml").read_text()

        self.assertIn("BET_ENVIRONMENT: production", compose)
        self.assertIn('BET_COOKIE_SECURE: "true"', compose)
        self.assertIn("BET_TASK_QUEUE_BACKEND: taskiq", compose)
        self.assertIn(
            "BET_REDIS_URL: ${BET_REDIS_URL:?set authenticated Redis DB 0 URL",
            compose,
        )
        self.assertIn(
            "BET_TASKIQ_RESULT_BACKEND_URL: ${BET_TASKIQ_RESULT_BACKEND_URL:",
            compose,
        )
        self.assertIn("BET_ODDSHARVESTER_PYTHON: /usr/local/bin/python", compose)
        self.assertIn('BET_TRADING_ENABLED: "false"', compose)
        self.assertIn('BET_TRADING_PAPER_ENABLED: "false"', compose)
        self.assertIn('BET_TRADING_LIVE_ENABLED: "false"', compose)
        self.assertIn("test: [CMD, python, -m, app.tasks.runtime, worker]", compose)
        self.assertIn("test: [CMD, python, -m, app.tasks.runtime, scheduler]", compose)
        self.assertIn("REDIS_PASSWORD: ${REDIS_PASSWORD:", compose)
        self.assertIn(
            'redis-server --appendonly yes --requirepass "$$REDIS_PASSWORD"', compose
        )
        self.assertIn("REDISCLI_AUTH=$$REDIS_PASSWORD redis-cli ping", compose)
        self.assertIn("driver: local", compose)
        self.assertIn('mem_limit: "${BET_CONTAINER_MEMORY_LIMIT:-2g}"', compose)
        self.assertIn('pids_limit: "${BET_CONTAINER_PIDS_LIMIT:-512}"', compose)
        self.assertIn("tmpfs: [/tmp:rw,noexec,nosuid,size=256m]", compose)
        self.assertNotIn("--reload", compose)
        self.assertNotIn("./nginx/nginx.conf:/etc/nginx/nginx.conf", compose)

    def test_database_and_redis_are_not_published(self) -> None:
        compose = (ROOT / "deploy/production/compose.yml").read_text()
        postgres_block = compose.split("  postgres:", 1)[1].split("\n  redis:", 1)[0]
        redis_block = compose.split("  redis:", 1)[1].split("\n  migrate:", 1)[0]

        self.assertNotIn("ports:", postgres_block)
        self.assertNotIn("ports:", redis_block)
        self.assertIn("internal: true", compose)

    def test_release_inputs_pin_base_images_and_github_actions(self) -> None:
        for dockerfile in (
            ROOT / "backend/Dockerfile.production",
            ROOT / "frontend/Dockerfile",
            ROOT / "nginx/Dockerfile.production",
        ):
            from_lines = [
                line
                for line in dockerfile.read_text().splitlines()
                if line.startswith("FROM ")
            ]
            self.assertTrue(from_lines)
            self.assertTrue(all("@sha256:" in line for line in from_lines), dockerfile)

        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            for line in workflow.read_text().splitlines():
                if "uses:" not in line:
                    continue
                reference = line.split("uses:", 1)[1].strip().split()[0]
                self.assertRegex(reference, r"@[0-9a-f]{40}$", workflow)

        release_workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("submodules: recursive", release_workflow)
        self.assertIn("needs: verify-source", release_workflow)
        self.assertIn("Full Chromium hybrid gate", release_workflow)
        self.assertIn("-e ../OddsHarvester", release_workflow)
        self.assertIn("python -c 'import oddsharvester'", release_workflow)
        self.assertIn(
            "BET_ODDSHARVESTER_PYTHON=$(command -v python)",
            release_workflow,
        )
        self.assertLess(
            release_workflow.index("Verify portable bridge runtime"),
            release_workflow.index("Full Chromium hybrid gate"),
        )
        self.assertIn("Verify real Redis Taskiq worker and scheduler", release_workflow)
        self.assertIn("BET_TASK_QUEUE_BACKEND: taskiq", release_workflow)
        self.assertIn(
            "taskiq worker app.tasks.broker:broker app.tasks.jobs", release_workflow
        )
        self.assertIn("python -m app.tasks.runtime worker", release_workflow)
        self.assertIn("python -m app.tasks.runtime scheduler", release_workflow)
        self.assertIn("python -m app.tasks.smoke", release_workflow)
        self.assertIn(
            "playwright test --project=chromium-hybrid --retries=0",
            release_workflow,
        )
        self.assertIn("release-evidence/images.json", release_workflow)
        self.assertLess(
            release_workflow.index("submodules: recursive"),
            release_workflow.index("-f backend/Dockerfile.production"),
        )

        safe_trivy_action = (
            "aquasecurity/trivy-action@57a97c7e7821a5776cebc9bb87c984fa69cba8f1"
        )
        self.assertEqual(release_workflow.count(safe_trivy_action), 6)
        self.assertEqual(release_workflow.count("version: v0.69.3"), 6)
        self.assertNotIn(
            "a9c7b0f06e461e9d4b4d1711f154ee024b8d7ab8",
            release_workflow,
        )
        self.assertNotIn("ignore-unfixed: true", release_workflow)

        workflow_text = "\n".join(
            path.read_text() for path in (ROOT / ".github/workflows").glob("*.yml")
        )
        safe_pnpm_action = "pnpm/action-setup@0ebf47130e4866e96fce0953f49152a61190b271"
        self.assertEqual(workflow_text.count(safe_pnpm_action), 3)
        self.assertNotIn(
            "f40ffcd9367d9f12939873eb1018b921a783ffaa",
            workflow_text,
        )

        security_workflow = (ROOT / ".github/workflows/security.yml").read_text()
        self.assertIn("fetch-depth: 0", security_workflow)
        self.assertIn("ACTIONLINT_VERSION: 1.7.12", security_workflow)
        self.assertIn(
            "ACTIONLINT_SHA256: "
            "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
            security_workflow,
        )
        self.assertIn("sha256sum --check", security_workflow)
        self.assertEqual(security_workflow.count(safe_trivy_action), 1)
        self.assertIn("scanners: vuln,secret,misconfig", security_workflow)
        self.assertIn("version: v0.69.3", security_workflow)
        self.assertIn(
            "tests/test_production_contract.py tests/test_secret_scanner.py",
            security_workflow,
        )

        for workflow_name in ("backend.yml", "hybrid-e2e.yml"):
            workflow = (ROOT / ".github/workflows" / workflow_name).read_text()
            self.assertRegex(workflow, r"image: postgres:[^\n]+@sha256:[0-9a-f]{64}")
            self.assertRegex(workflow, r"image: redis:[^\n]+@sha256:[0-9a-f]{64}")

        hybrid_workflow = (ROOT / ".github/workflows/hybrid-e2e.yml").read_text()
        self.assertIn("-e ../OddsHarvester", hybrid_workflow)
        self.assertIn("python -c 'import oddsharvester'", hybrid_workflow)
        self.assertIn("BET_ODDSHARVESTER_PYTHON=$(command -v python)", hybrid_workflow)

    def test_release_publishes_only_protected_tag_digests_after_all_gates(self) -> None:
        release = (ROOT / ".github/workflows/release.yml").read_text()
        publish_job = release.split("\n  publish-signed-images:", 1)[1]

        self.assertIn("needs: build-scan-and-package", publish_job)
        self.assertIn("github.event_name == 'push'", publish_job)
        self.assertIn("github.ref_type == 'tag'", publish_job)
        self.assertIn("startsWith(github.ref_name, 'v')", publish_job)
        self.assertIn("environment: registry-release", publish_job)
        self.assertIn("packages: write", publish_job)
        self.assertIn("id-token: write", publish_job)
        self.assertIn("attestations: write", publish_job)
        permission_block = publish_job.split("permissions:", 1)[1].split("steps:", 1)[0]
        self.assertEqual(
            {line.strip() for line in permission_block.splitlines() if line.strip()},
            {
                "contents: read",
                "packages: write",
                "id-token: write",
                "attestations: write",
            },
        )
        self.assertNotIn("workflow_dispatch", publish_job)
        self.assertNotIn("secrets.PAT", release)
        self.assertNotIn("PERSONAL_ACCESS_TOKEN", release)
        self.assertNotIn("COSIGN_PRIVATE_KEY", release)
        self.assertNotIn("COSIGN_PASSWORD", release)

        self.assertEqual(
            release.count("org.opencontainers.image.source=$source_label"),
            3,
        )
        self.assertIn("docker save --output release-images/candidates.tar", release)
        self.assertIn("sha256sum candidates.tar > candidates.tar.sha256", release)
        self.assertIn("sha256sum --check candidates.tar.sha256", publish_job)
        self.assertIn("retention-days: 30", release)
        self.assertIn(
            "Refuse to overwrite existing immutable release references", publish_job
        )
        self.assertIn(
            'scripts/release/assert-registry-ref-absent.sh "$name:$tag"',
            publish_job,
        )
        self.assertIn(
            "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            publish_job,
        )
        self.assertLess(
            publish_job.index("uses: actions/checkout@"),
            publish_job.index("scripts/release/assert-registry-ref-absent.sh"),
        )
        self.assertIn("ghcr.io/${repository}-api", publish_job)
        self.assertIn("ghcr.io/${repository}-frontend", publish_job)
        self.assertIn("ghcr.io/${repository}-nginx", publish_job)
        self.assertIn('docker push "$sha_ref"', publish_job)
        self.assertIn(
            'docker buildx imagetools inspect "$sha_ref"',
            publish_job,
        )
        self.assertIn('cosign sign --yes "$ref"', publish_job)
        self.assertIn(
            "${{ steps.publish.outputs.api_name }}@"
            "${{ steps.publish.outputs.api_digest }}",
            publish_job,
        )
        self.assertIn('--certificate-identity "$identity"', publish_job)
        self.assertIn(
            '--certificate-oidc-issuer "$issuer"',
            publish_job,
        )
        self.assertEqual(
            publish_job.count(
                "uses: actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6"
            ),
            3,
        )
        self.assertEqual(publish_job.count("push-to-registry: true"), 3)
        self.assertEqual(publish_job.count("create-storage-record: false"), 3)
        self.assertIn('gh attestation verify "oci://$ref"', publish_job)
        self.assertIn("--prefer-index=false", publish_job)
        self.assertIn("registry-evidence/registry.json", publish_job)
        self.assertLess(
            release.index("name: Scan tracked secrets"),
            release.index("name: Preserve exact scanned images"),
        )
        self.assertLess(
            publish_job.index("name: Verify GitHub provenance attestations"),
            publish_job.index("name: Promote verified digests"),
        )

    def test_registry_reference_guard_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            docker = bin_dir / "docker"
            docker.write_text(
                "#!/bin/sh\n"
                'case "$DOCKER_SCENARIO" in\n'
                "  existing) printf '%s\\n' 'manifest present'; exit 0 ;;\n"
                "  missing) printf '%s\\n' 'MANIFEST_UNKNOWN: manifest unknown' >&2; exit 1 ;;\n"
                "  network) printf '%s\\n' 'dial tcp: network is unreachable' >&2; exit 1 ;;\n"
                "esac\n"
                "exit 2\n"
            )
            docker.chmod(0o755)
            guard = ROOT / "scripts/release/assert-registry-ref-absent.sh"
            environment = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
            }

            results = {
                scenario: subprocess.run(
                    [str(guard), "ghcr.io/example/bet-api:v1.2.3"],
                    env={**environment, "DOCKER_SCENARIO": scenario},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                for scenario in ("existing", "missing", "network")
            }

            self.assertNotEqual(results["existing"].returncode, 0)
            self.assertIn("refusing to overwrite", results["existing"].stderr)
            self.assertEqual(results["missing"].returncode, 0)
            self.assertNotEqual(results["network"].returncode, 0)
            self.assertIn("could not prove", results["network"].stderr)

    def test_container_runtime_dependencies_are_reproducible_and_non_root_accessible(
        self,
    ) -> None:
        backend = (ROOT / "backend/Dockerfile.production").read_text()
        compose = (ROOT / "deploy/production/compose.yml").read_text()
        frontend = (ROOT / "frontend/Dockerfile").read_text()
        package = (ROOT / "frontend/package.json").read_text()

        self.assertIn("ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright", backend)
        self.assertIn("pip install --no-cache-dir uv==0.11.25", backend)
        self.assertIn(
            "--requirement backend/requirements-production.lock",
            backend,
        )
        self.assertNotIn("pip install --no-cache-dir \\\n    ./backend", backend)
        self.assertIn(
            'chown -R appuser:appuser /app "$PLAYWRIGHT_BROWSERS_PATH"', backend
        )
        self.assertLess(
            backend.index("ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright"),
            backend.index("python -m playwright install --with-deps chromium"),
        )
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH: /ms-playwright", compose)

        self.assertIn('"packageManager": "pnpm@10.34.5"', package)
        self.assertEqual(frontend.count("npm install -g pnpm@10.34.5"), 1)
        self.assertEqual(frontend.count("pnpm install --frozen-lockfile"), 1)
        self.assertIn("pnpm build && pnpm prune --prod", frontend)
        self.assertIn("COPY --from=builder /app/node_modules ./node_modules", frontend)

        release = (ROOT / ".github/workflows/release.yml").read_text()
        smoke = release.index("name: Smoke built production images")
        evidence = release.index("name: Prepare release evidence directory")
        self.assertLess(smoke, evidence)
        self.assertIn("--entrypoint id bet-api:", release)
        self.assertIn("from app.main import app", release)
        self.assertIn("playwright.chromium.launch()", release)
        self.assertIn('PLAYWRIGHT_BROWSERS_PATH"] == "/ms-playwright"', release)
        self.assertIn("--entrypoint id bet-frontend:", release)
        self.assertIn("--entrypoint id bet-nginx:", release)
        self.assertIn("curl --fail --silent --show-error --location", release)
        self.assertIn('docker logs "$frontend_id"', release)
        self.assertIn("openssl req -x509 -newkey rsa:2048", release)
        self.assertIn("--publish 127.0.0.1:38080:8080", release)
        self.assertIn("--publish 127.0.0.1:38443:8443", release)
        self.assertIn("https://127.0.0.1:38443/", release)

        production_input = (ROOT / "backend/requirements-production.in").read_text()
        production_lock = (ROOT / "backend/requirements-production.lock").read_text()
        for project in ("backend", "OddsHarvester", "penaltyblog", "soccerdata"):
            self.assertIn(f"-e {project}", production_input)
            self.assertIn(f"-e {project}", production_lock)
        self.assertIn("pyjwt==", production_lock)
        self.assertNotIn("python-jose==", production_lock)
        self.assertNotIn("ecdsa==", production_lock)
        for line in production_lock.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "-e ")):
                continue
            self.assertRegex(stripped, r"^[a-z0-9_.-]+==[^=]+$")

    def test_tls_edge_rate_limits_auth_and_proxies_websockets(self) -> None:
        nginx = (ROOT / "deploy/production/nginx/nginx.conf").read_text()
        nginx_dockerfile = (ROOT / "nginx/Dockerfile.production").read_text()
        compose = (ROOT / "deploy/production/compose.yml").read_text()

        self.assertIn("listen 8080", nginx)
        self.assertIn("listen 8443 ssl", nginx)
        self.assertIn("USER nginx", nginx_dockerfile)
        self.assertIn("EXPOSE 8080 8443", nginx_dockerfile)
        self.assertIn(":8080", compose)
        self.assertIn(":8443", compose)
        self.assertIn("Strict-Transport-Security", nginx)
        self.assertIn("auth_login_per_ip", nginx)
        self.assertIn("auth_signup_per_ip", nginx)
        self.assertIn("limit_req_status 429", nginx)
        self.assertIn("proxy_set_header Upgrade $http_upgrade", nginx)
        self.assertIn("location = /login", nginx)
        self.assertIn("location = /signup", nginx)

    def test_release_validation_does_not_render_resolved_secrets(self) -> None:
        render = (ROOT / "scripts/release/render.sh").read_text()
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        backup = (ROOT / "scripts/db/backup-postgres.sh").read_text()
        restore = (ROOT / "scripts/db/restore-postgres.sh").read_text()
        smoke = (ROOT / "scripts/release/smoke.sh").read_text()
        deploy = (ROOT / "scripts/release/deploy.sh").read_text()
        rollback = (ROOT / "scripts/release/rollback.sh").read_text()
        runbook = (ROOT / "docs/runbooks/production-release.md").read_text()

        self.assertIn("config --quiet", render)
        self.assertNotIn("compose.rendered.yml", workflow)
        self.assertIn("umask 077", backup)
        self.assertIn("dropdb --if-exists --force", restore)
        self.assertIn("BET_DATABASE_URL and POSTGRES_DB", restore)
        self.assertIn("rm -f /tmp/restore.dump", restore)
        self.assertIn("run --rm migrate", restore)
        self.assertLess(
            restore.index("run --rm migrate"), restore.index("up --detach api")
        )
        self.assertIn("app.tasks.smoke", smoke)
        self.assertIn("app.diagnostics.provider_canary", smoke)
        self.assertIn("app.tasks.runtime worker", smoke)
        self.assertIn("app.tasks.runtime scheduler", smoke)
        self.assertIn("backup-postgres.sh", deploy)
        self.assertIn("smoke.sh", deploy)
        self.assertIn("--wait --wait-timeout", deploy)
        self.assertIn("smoke.sh", rollback)
        self.assertIn("known-good-immutable-env-file", deploy)
        self.assertIn("snapshot_immutable_manifest", deploy)
        self.assertIn("trap restore_after_failure ERR", deploy)
        self.assertIn("restore_immutable_release", deploy)
        self.assertIn("record_known_good_manifest", deploy)
        bootstrap = (ROOT / "scripts/release/bootstrap.sh").read_text()
        self.assertIn("BET_BOOTSTRAP_CONFIRM", bootstrap)
        self.assertIn("record_known_good_manifest", bootstrap)
        self.assertNotIn("backup-postgres.sh", bootstrap)
        self.assertIn(
            "--no-deps --wait --wait-timeout 180",
            (ROOT / "scripts/release/lib.sh").read_text(),
        )
        self.assertLess(
            rollback.index("restore_immutable_release"), rollback.index("smoke.sh")
        )
        self.assertIn("previous application images still start", runbook)
        self.assertIn("expand-only and backward compatible", runbook)
        self.assertIn("reverse Alembic migrations automatically", runbook)


if __name__ == "__main__":
    unittest.main()
