#!/usr/bin/env python3
"""Gate release images on fixable High/Critical Trivy findings.

The complete, unfiltered Trivy JSON reports remain release artifacts. This
gate fails closed on malformed reports and on High/Critical findings for which
Trivy provides a fixed version. Unfixed findings remain visible for explicit
release risk review instead of being discarded from the evidence.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def inspect_report(path: Path) -> tuple[list[dict[str, str]], Counter[str]]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: unreadable Trivy JSON report: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("Results"), list):
        raise ValueError(f"{path}: Trivy report must contain a Results array")

    blocking: list[dict[str, str]] = []
    unresolved: Counter[str] = Counter()
    for result in payload["Results"]:
        if not isinstance(result, dict):
            raise ValueError(f"{path}: every Trivy result must be an object")
        vulnerabilities = result.get("Vulnerabilities")
        if vulnerabilities is None:
            continue
        if not isinstance(vulnerabilities, list):
            raise ValueError(f"{path}: Vulnerabilities must be an array or null")

        target = _text(result.get("Target")) or "<unknown-target>"
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                raise ValueError(f"{path}: every vulnerability must be an object")
            severity = _text(vulnerability.get("Severity")).upper()
            if severity not in BLOCKING_SEVERITIES:
                continue

            finding = {
                "id": _text(vulnerability.get("VulnerabilityID"))
                or "<unknown-vulnerability>",
                "package": _text(vulnerability.get("PkgName")) or "<unknown-package>",
                "severity": severity,
                "status": _text(vulnerability.get("Status")) or "unknown",
                "installed": _text(vulnerability.get("InstalledVersion")) or "<unknown>",
                "fixed": _text(vulnerability.get("FixedVersion")),
                "target": target,
            }
            if finding["fixed"] or finding["status"].lower() == "fixed":
                if not finding["fixed"]:
                    finding["fixed"] = "<reported-fixed-version-unavailable>"
                blocking.append(finding)
            else:
                unresolved[f"{severity}:{finding['status']}"] += 1

    return blocking, unresolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail on fixable High/Critical findings while retaining complete "
            "Trivy reports for explicit unfixed-risk review."
        )
    )
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()

    all_blocking: list[tuple[Path, dict[str, str]]] = []
    all_unresolved: Counter[str] = Counter()
    try:
        for report in args.reports:
            blocking, unresolved = inspect_report(report)
            all_blocking.extend((report, finding) for finding in blocking)
            all_unresolved.update(unresolved)
    except ValueError as exc:
        parser.exit(2, f"ERROR: {exc}\n")

    if all_unresolved:
        summary = ", ".join(
            f"{key}={count}" for key, count in sorted(all_unresolved.items())
        )
        print(
            "UNFIXED-RISK: retained in release evidence and requires explicit "
            f"release review ({summary})"
        )
    else:
        print("UNFIXED-RISK: no unresolved High/Critical findings")

    if not all_blocking:
        print("PASS: no fixable High/Critical findings")
        return 0

    for report, finding in all_blocking:
        print(
            "BLOCKING: "
            f"{report} {finding['severity']} {finding['id']} "
            f"{finding['package']} {finding['installed']} -> {finding['fixed']} "
            f"status={finding['status']} target={finding['target']}"
        )
    print(f"FAIL: {len(all_blocking)} fixable High/Critical finding(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
