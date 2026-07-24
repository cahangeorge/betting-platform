#!/usr/bin/env python3
"""Fail when tracked text files contain common plaintext secret shapes.

The scanner intentionally reports only file, line, and rule identifiers. It
never prints the matched value. Provider-side secret scanning remains useful,
but this deterministic local gate prevents the known class of tracked config
credential from recurring without sending repository contents to a third party.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    rule_id: str
    pattern: re.Pattern[str]


RULES = (
    Rule("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    Rule("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    Rule("github-token", re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{30,}\b")),
    Rule("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    Rule("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    Rule("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    Rule(
        "bearer-token",
        re.compile(r"(?i)\bbearer\s+(?P<value>[A-Za-z0-9_./+=:-]{20,})\b"),
    ),
    Rule(
        "credential-assignment",
        re.compile(
            r"""(?ix)
            ["']?
            (?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|
               jwt[_-]?secret|password|passwd|private[_-]?key)
            ["']?
            \s*[:=]\s*
            (?P<value>
                ["'][A-Za-z0-9_./+=:@${}<>-]{20,}["']
                |
                (?=[A-Za-z0-9_./+=:@${}<>-]{20,})
                (?=[A-Za-z0-9_./+=:@${}<>-]*[0-9])
                [A-Za-z0-9_./+=:@${}<>-]+
            )
            """
        ),
    ),
)
ALLOW_TEST_FIXTURE_MARKER = "secret-scan: allow-test-fixture"
TEST_FIXTURE_PATHS = frozenset({Path("tests/test_secret_scanner.py")})
PURE_ENV_REFERENCE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")
SAFE_ENV_DEFAULT_REFERENCE = re.compile(
    r"\$\{[A-Za-z_][A-Za-z0-9_]*:-(?:"
    r"dev-secret-change-in-production|"
    r"dev-jwt-secret-change-in-production|"
    r"not-a-real-dev-password"
    r")\}"
)

IGNORED_VALUE_PREFIXES = (
    "{env:",
    "<",
    "process.env",
    "os.environ",
    "replace-",
    "replace_",
    "your-",
    "your_",
    "generate-",
)
IGNORED_EXACT_VALUES = frozenset(
    {
        "dev-secret-change-in-production",
        "dev-jwt-secret-change-in-production",
        "not-a-real-dev-password",
    }
)


def is_ignored_value(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    return (
        bool(PURE_ENV_REFERENCE.fullmatch(normalized))
        or normalized in IGNORED_EXACT_VALUES
        or normalized.startswith(IGNORED_VALUE_PREFIXES)
    )


def scan_text(
    text: str,
    *,
    allow_test_fixture_markers: bool = False,
) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if allow_test_fixture_markers and ALLOW_TEST_FIXTURE_MARKER in line:
            continue
        scan_line = SAFE_ENV_DEFAULT_REFERENCE.sub("{env:VARIABLE}", line)
        scan_line = PURE_ENV_REFERENCE.sub("{env:VARIABLE}", scan_line)
        for rule in RULES:
            match = rule.pattern.search(scan_line)
            if not match:
                continue
            value = match.groupdict().get("value")
            if value is not None and is_ignored_value(value):
                continue
            findings.append((line_number, rule.rule_id))
    return findings


def git_files(repo_root: Path, *arguments: str) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return [
        repo_root / path.decode("utf-8", errors="surrogateescape")
        for path in result.stdout.split(b"\0")
        if path
    ]


def repository_files(repo_root: Path, *, include_untracked: bool = False) -> list[Path]:
    paths = git_files(repo_root)
    if include_untracked:
        paths.extend(git_files(repo_root, "--others", "--exclude-standard"))
    return list(dict.fromkeys(paths))


def scan_repository(
    repo_root: Path, *, include_untracked: bool = False
) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for path in repository_files(repo_root, include_untracked=include_untracked):
        if not path.is_file():
            continue
        relative_path = path.relative_to(repo_root)
        try:
            payload = path.read_bytes()
        except OSError:
            findings.append((relative_path, 0, "read-error"))
            continue
        if b"\0" in payload:
            continue
        text = payload.decode("utf-8", errors="replace")
        for line_number, rule_id in scan_text(
            text,
            allow_test_fixture_markers=relative_path in TEST_FIXTURE_PATHS,
        ):
            findings.append((relative_path, line_number, rule_id))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Git repository root (defaults to this script's parent repository)",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="also scan untracked files that are not ignored by Git",
    )
    args = parser.parse_args()

    findings = scan_repository(
        args.root.resolve(),
        include_untracked=args.include_untracked,
    )
    scope = "Tracked and untracked" if args.include_untracked else "Tracked"
    if findings:
        print(f"{scope} plaintext secret candidates detected (values redacted):")
        for path, line_number, rule_id in findings:
            location = f"{path}:{line_number}" if line_number else str(path)
            print(f"- {location} [{rule_id}]")
        return 1

    print(f"{scope} plaintext secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
