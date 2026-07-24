from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_tracked_secrets.py"
SPEC = importlib.util.spec_from_file_location("scan_tracked_secrets", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SecretScannerTests(unittest.TestCase):
    def test_detects_plaintext_config_secret_without_exposing_value(self) -> None:
        findings = MODULE.scan_text(
            '{"BRAVE_API_KEY": "actual-secret-value-123456"}'  # secret-scan: allow-test-fixture
        )
        self.assertEqual(findings, [(1, "credential-assignment")])

    def test_allows_environment_reference_and_examples(self) -> None:
        text = "\n".join(
            (
                '{"BRAVE_API_KEY": "{env:BRAVE_API_KEY}"}',
                'BET_JWT_SECRET="replace-this-in-non-dev"',
                "POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-not-a-real-dev-password}",
                'errors.password = "Parola trebuie să aibă cel puțin 8 caractere";',
                'autocomplete={mode === "login" ? "current-password" : "new-password"}',
            )
        )
        self.assertEqual(MODULE.scan_text(text), [])

    def test_shell_default_with_plaintext_secret_is_not_treated_as_a_pure_reference(
        self,
    ) -> None:
        text = "BET_JWT_SECRET=${BET_JWT_SECRET:-actual-secret-value-123456}"  # secret-scan: allow-test-fixture
        self.assertEqual(
            MODULE.scan_text(text),
            [(1, "credential-assignment")],
        )

    def test_placeholder_words_inside_production_values_do_not_bypass_scan(
        self,
    ) -> None:
        text = "\n".join(
            (
                "BET_JWT_SECRET=prod-example-customer-secret-2026",  # secret-scan: allow-test-fixture
                "BET_JWT_SECRET=actual-dummy-production-secret-2026",  # secret-scan: allow-test-fixture
            )
        )
        self.assertEqual(
            MODULE.scan_text(text),
            [
                (1, "credential-assignment"),
                (2, "credential-assignment"),
            ],
        )

    def test_detects_private_key_header(self) -> None:
        findings = MODULE.scan_text(
            "-----BEGIN PRIVATE KEY-----"  # secret-scan: allow-test-fixture
        )
        self.assertEqual(findings, [(1, "private-key")])

    def test_detects_unquoted_env_yaml_and_bearer_values(self) -> None:
        text = "\n".join(
            (
                "BRAVE_API_KEY=actual-secret-value-123456",  # secret-scan: allow-test-fixture
                "client_secret: actual-yaml-secret-value-123456",  # secret-scan: allow-test-fixture
                "Authorization: Bearer actual-bearer-token-value-123456",  # secret-scan: allow-test-fixture
            )
        )
        self.assertEqual(
            MODULE.scan_text(text),
            [
                (1, "credential-assignment"),
                (2, "credential-assignment"),
                (3, "bearer-token"),
            ],
        )

    def test_fixture_marker_requires_explicit_approved_fixture_scope(self) -> None:
        text = (
            "api_key=actual-secret-value-123456 "  # secret-scan: allow-test-fixture
            "# secret-scan: allow-test-fixture"
        )
        self.assertEqual(
            MODULE.scan_text(text),
            [(1, "credential-assignment")],
        )
        self.assertEqual(
            MODULE.scan_text(text, allow_test_fixture_markers=True),
            [],
        )

    def test_include_untracked_adds_only_git_visible_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text("ignored.txt\n")
            (root / "tracked.txt").write_text("tracked\n")
            (root / "untracked.txt").write_text("untracked\n")
            (root / "ignored.txt").write_text("ignored\n")
            subprocess.run(
                ["git", "add", ".gitignore", "tracked.txt"],
                cwd=root,
                check=True,
            )

            tracked = {
                path.relative_to(root)
                for path in MODULE.repository_files(root)
            }
            working_tree = {
                path.relative_to(root)
                for path in MODULE.repository_files(root, include_untracked=True)
            }

            self.assertEqual(tracked, {Path(".gitignore"), Path("tracked.txt")})
            self.assertEqual(
                working_tree,
                {Path(".gitignore"), Path("tracked.txt"), Path("untracked.txt")},
            )

    def test_fixture_marker_does_not_bypass_repository_scan_outside_approved_test(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            source = root / "production.py"
            source.write_text(
                "api_key=actual-secret-value-123456 "  # secret-scan: allow-test-fixture
                "# secret-scan: allow-test-fixture\n"
            )
            subprocess.run(["git", "add", "production.py"], cwd=root, check=True)

            self.assertEqual(
                MODULE.scan_repository(root),
                [(Path("production.py"), 1, "credential-assignment")],
            )

    def test_repository_scan_fails_closed_when_tracked_file_cannot_be_read(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            source = root / "tracked.txt"
            source.write_text("safe\n")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)

            with mock.patch.object(Path, "read_bytes", side_effect=OSError("denied")):
                self.assertEqual(
                    MODULE.scan_repository(root),
                    [(Path("tracked.txt"), 0, "read-error")],
                )

    def test_repository_scan_allows_marker_only_in_approved_fixture_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            fixture = root / "tests" / "test_secret_scanner.py"
            fixture.parent.mkdir()
            fixture.write_text(
                "api_key=actual-secret-value-123456 "  # secret-scan: allow-test-fixture
                "# secret-scan: allow-test-fixture\n"
            )
            subprocess.run(
                ["git", "add", "tests/test_secret_scanner.py"],
                cwd=root,
                check=True,
            )

            self.assertEqual(MODULE.scan_repository(root), [])


if __name__ == "__main__":
    unittest.main()
