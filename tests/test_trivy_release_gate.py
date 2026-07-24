from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/release/gate_trivy_reports.py"


def _run_gate(tmp_path: Path, vulnerabilities: object) -> subprocess.CompletedProcess[str]:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "ArtifactName": "candidate-image",
                "ArtifactType": "container_image",
                "Results": [
                    {
                        "Target": "candidate-image",
                        "Vulnerabilities": vulnerabilities,
                    }
                ]
            }
        )
    )
    return subprocess.run(
        [sys.executable, str(GATE), str(report)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_trivy_gate_retains_unfixed_findings_without_hiding_them(tmp_path: Path) -> None:
    result = _run_gate(
        tmp_path,
        [
            {
                "VulnerabilityID": "CVE-UNFIXED",
                "PkgName": "runtime-lib",
                "InstalledVersion": "1.0",
                "Severity": "CRITICAL",
                "Status": "affected",
            }
        ],
    )

    assert result.returncode == 0
    assert "CRITICAL:affected=1" in result.stdout
    assert "requires explicit release review" in result.stdout
    assert "PASS: no fixable High/Critical findings" in result.stdout


def test_trivy_gate_blocks_fixable_high_or_critical_findings(tmp_path: Path) -> None:
    result = _run_gate(
        tmp_path,
        [
            {
                "VulnerabilityID": "CVE-FIXABLE",
                "PkgName": "runtime-lib",
                "InstalledVersion": "1.0",
                "FixedVersion": "1.1",
                "Severity": "HIGH",
                "Status": "fixed",
            }
        ],
    )

    assert result.returncode == 1
    assert "BLOCKING:" in result.stdout
    assert "CVE-FIXABLE" in result.stdout
    assert "1.0 -> 1.1" in result.stdout


def test_trivy_gate_fails_closed_when_status_is_fixed_without_version(
    tmp_path: Path,
) -> None:
    result = _run_gate(
        tmp_path,
        [
            {
                "VulnerabilityID": "CVE-FIXED-STATUS",
                "PkgName": "runtime-lib",
                "InstalledVersion": "1.0",
                "FixedVersion": "",
                "Severity": "CRITICAL",
                "Status": "fixed",
            }
        ],
    )

    assert result.returncode == 1
    assert "<reported-fixed-version-unavailable>" in result.stdout


def test_trivy_gate_fails_closed_on_malformed_report(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text("{}")

    result = subprocess.run(
        [sys.executable, str(GATE), str(report)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "SchemaVersion must be 2" in result.stderr


def test_trivy_gate_fails_closed_when_severity_is_missing(tmp_path: Path) -> None:
    result = _run_gate(
        tmp_path,
        [
            {
                "VulnerabilityID": "CVE-MALFORMED-SEVERITY",
                "PkgName": "runtime-lib",
                "InstalledVersion": "1.0",
                "FixedVersion": "1.1",
                "Status": "fixed",
            }
        ],
    )

    assert result.returncode == 2
    assert "Severity must be a non-empty string" in result.stderr


def test_trivy_gate_fails_closed_when_fixed_version_has_wrong_type(
    tmp_path: Path,
) -> None:
    result = _run_gate(
        tmp_path,
        [
            {
                "VulnerabilityID": "CVE-MALFORMED-FIXED",
                "PkgName": "runtime-lib",
                "InstalledVersion": "1.0",
                "FixedVersion": ["1.1"],
                "Severity": "CRITICAL",
                "Status": "affected",
            }
        ],
    )

    assert result.returncode == 2
    assert "FixedVersion must be a string when present" in result.stderr


def test_trivy_gate_fails_closed_on_unexpected_severity(tmp_path: Path) -> None:
    result = _run_gate(
        tmp_path,
        [
            {
                "VulnerabilityID": "CVE-UNEXPECTED-SEVERITY",
                "PkgName": "runtime-lib",
                "InstalledVersion": "1.0",
                "Severity": "MEDIUM",
                "Status": "affected",
            }
        ],
    )

    assert result.returncode == 2
    assert "expected a HIGH/CRITICAL-filtered report" in result.stderr


def test_trivy_gate_fails_closed_when_result_target_is_missing(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "ArtifactName": "candidate-image",
                "ArtifactType": "container_image",
                "Results": [{}],
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(GATE), str(report)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Target must be a non-empty string" in result.stderr
