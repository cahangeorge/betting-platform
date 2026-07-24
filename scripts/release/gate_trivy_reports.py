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


class Arguments(argparse.Namespace):
    reports: list[Path]


def _required_text(
    value: dict[str, Any],
    field: str,
    *,
    context: str,
) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{context}: {field} must be a non-empty string")
    return raw.strip()


def _optional_text(
    value: dict[str, Any],
    field: str,
    *,
    context: str,
) -> str:
    if field not in value:
        return ""
    raw = value[field]
    if not isinstance(raw, str):
        raise ValueError(f"{context}: {field} must be a string when present")
    return raw.strip()


def inspect_report(path: Path) -> tuple[list[dict[str, str]], Counter[str]]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: unreadable Trivy JSON report: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{path}: Trivy report must be a JSON object")
    if payload.get("SchemaVersion") != 2:
        raise ValueError(f"{path}: Trivy report SchemaVersion must be 2")
    if payload.get("ArtifactType") != "container_image":
        raise ValueError(f"{path}: Trivy report ArtifactType must be container_image")
    _required_text(payload, "ArtifactName", context=str(path))

    results = payload.get("Results")
    if not isinstance(results, list):
        raise ValueError(f"{path}: Trivy report must contain a Results array")
    if not results:
        raise ValueError(f"{path}: Trivy report Results array must not be empty")

    blocking: list[dict[str, str]] = []
    unresolved: Counter[str] = Counter()
    for result_index, result in enumerate(results):
        if not isinstance(result, dict):
            raise ValueError(f"{path}: every Trivy result must be an object")
        result_context = f"{path}: Results[{result_index}]"
        target = _required_text(result, "Target", context=result_context)
        vulnerabilities = result.get("Vulnerabilities")
        if vulnerabilities is None:
            continue
        if not isinstance(vulnerabilities, list):
            raise ValueError(f"{path}: Vulnerabilities must be an array or null")

        for vulnerability_index, vulnerability in enumerate(vulnerabilities):
            if not isinstance(vulnerability, dict):
                raise ValueError(f"{path}: every vulnerability must be an object")
            vulnerability_context = (
                f"{result_context}.Vulnerabilities[{vulnerability_index}]"
            )
            severity = _required_text(
                vulnerability,
                "Severity",
                context=vulnerability_context,
            ).upper()
            if severity not in BLOCKING_SEVERITIES:
                raise ValueError(
                    f"{vulnerability_context}: unexpected Severity {severity!r}; "
                    "expected a HIGH/CRITICAL-filtered report"
                )

            finding = {
                "id": _required_text(
                    vulnerability,
                    "VulnerabilityID",
                    context=vulnerability_context,
                ),
                "package": _required_text(
                    vulnerability,
                    "PkgName",
                    context=vulnerability_context,
                ),
                "severity": severity,
                "status": _required_text(
                    vulnerability,
                    "Status",
                    context=vulnerability_context,
                ),
                "installed": _required_text(
                    vulnerability,
                    "InstalledVersion",
                    context=vulnerability_context,
                ),
                "fixed": _optional_text(
                    vulnerability,
                    "FixedVersion",
                    context=vulnerability_context,
                ),
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
    args = parser.parse_args(namespace=Arguments())

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
