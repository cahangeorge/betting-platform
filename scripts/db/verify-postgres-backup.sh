#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")/../release" && pwd)/lib.sh"
[[ $# -eq 1 ]] || fail "usage: $0 <backup.dump>"
backup=$1
require_file "$backup"
require_file "$backup.sha256"
require_command sha256sum
require_command pg_restore
( cd "$(dirname "$backup")" && sha256sum -c "$(basename "$backup").sha256" )
pg_restore --list "$backup" >/dev/null
printf 'Backup checksum and PostgreSQL archive format verified: %s\n' "$backup"
