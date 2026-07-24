#!/usr/bin/env bash
set -euo pipefail
umask 077
source "$(cd "$(dirname "$0")/../release" && pwd)/lib.sh"
[[ $# -eq 2 ]] || fail "usage: $0 <production-env-file> <backup-directory>"
env_file=$(require_env_file "$1")
backup_dir=$2
[[ -d "$backup_dir" && -w "$backup_dir" ]] || fail "backup directory must exist and be writable"
"$(dirname "$0")/../release/render.sh" "$env_file" >/dev/null
require_command sha256sum
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_file="$backup_dir/bet-postgres-$stamp.dump"
temp_file="$backup_file.partial"
trap 'rm -f "$temp_file" "$temp_file.sha256"' EXIT
compose "$env_file" exec -T postgres pg_dump -U "$(grep '^POSTGRES_USER=' "$env_file" | cut -d= -f2-)" -d "$(grep '^POSTGRES_DB=' "$env_file" | cut -d= -f2-)" -Fc > "$temp_file"
[[ -s "$temp_file" ]] || fail "database dump is empty"
mv "$temp_file" "$backup_file"
sha256sum "$backup_file" > "$backup_file.sha256"
chmod 600 "$backup_file" "$backup_file.sha256"
trap - EXIT
printf 'Backup created: %s\n' "$backup_file"
