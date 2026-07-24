#!/usr/bin/env bash
set -euo pipefail
umask 077
source "$(cd "$(dirname "$0")/../release" && pwd)/lib.sh"
[[ $# -eq 2 ]] || fail "usage: $0 <production-env-file> <backup.dump>"
[[ "${BET_RESTORE_CONFIRM:-}" == "RESTORE" ]] || fail "set BET_RESTORE_CONFIRM=RESTORE to acknowledge destructive restore"
env_file=$(require_env_file "$1")
backup=$2
require_command python3
postgres_db=$(grep '^POSTGRES_DB=' "$env_file" | tail -n1 | cut -d= -f2-)
database_url=$(grep '^BET_DATABASE_URL=' "$env_file" | tail -n1 | cut -d= -f2-)
application_db=$(
  DATABASE_URL="$database_url" python3 -c \
    'import os, urllib.parse; print(urllib.parse.urlsplit(os.environ["DATABASE_URL"].replace("+asyncpg", "", 1)).path.lstrip("/"))'
)
[[ -n "$postgres_db" && "$application_db" == "$postgres_db" ]] || \
  fail "BET_DATABASE_URL and POSTGRES_DB must target the same database"
"$(dirname "$0")/verify-postgres-backup.sh" "$backup" >/dev/null
"$(dirname "$0")/../release/render.sh" "$env_file" >/dev/null
compose "$env_file" stop api worker scheduler frontend nginx
compose "$env_file" cp "$backup" postgres:/tmp/restore.dump
trap 'compose "$env_file" exec -T postgres rm -f /tmp/restore.dump >/dev/null 2>&1 || true' EXIT
postgres_user=$(grep '^POSTGRES_USER=' "$env_file" | tail -n1 | cut -d= -f2-)
compose "$env_file" exec -T postgres dropdb --if-exists --force -U "$postgres_user" "$postgres_db"
compose "$env_file" exec -T postgres createdb -U "$postgres_user" -O "$postgres_user" "$postgres_db"
compose "$env_file" exec -T postgres pg_restore --no-owner -U "$postgres_user" -d "$postgres_db" /tmp/restore.dump
compose "$env_file" exec -T postgres rm -f /tmp/restore.dump
trap - EXIT
compose "$env_file" run --rm migrate
compose "$env_file" up --detach api worker scheduler frontend nginx
printf '%s\n' 'Restore and Alembic upgrade completed. Run release smoke and application-level integrity checks before reopening traffic.'
