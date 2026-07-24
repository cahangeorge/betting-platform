#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 ]] || {
  printf 'ERROR: usage: %s <fully-qualified-image:tag>\n' "$0" >&2
  exit 2
}

command -v docker >/dev/null 2>&1 || {
  printf 'ERROR: required command not found: docker\n' >&2
  exit 1
}

reference=$1
diagnostic=$(mktemp "${TMPDIR:-/tmp}/bet-registry-inspect.XXXXXX")
trap 'rm -f "$diagnostic"' EXIT

if docker buildx imagetools inspect "$reference" >"$diagnostic" 2>&1; then
  printf 'ERROR: refusing to overwrite existing registry reference: %s\n' \
    "$reference" >&2
  exit 1
fi

# Only explicit OCI Distribution absence codes are accepted. Authentication,
# transport, rate-limit, and unclassified registry failures stop publication.
if grep -Eqi 'MANIFEST_UNKNOWN|NAME_UNKNOWN|manifest unknown' "$diagnostic"; then
  exit 0
fi

printf 'ERROR: could not prove registry reference absence: %s\n' "$reference" >&2
cat "$diagnostic" >&2
exit 1
