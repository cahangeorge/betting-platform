#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
[[ $# -eq 4 ]] || fail "usage: $0 <production-env-file> <backup-directory> <https-base-url> <known-good-immutable-env-file>"
env_file=$(require_env_file "$1")
backup_dir=$2
base_url=$3
known_good=$(require_env_file "$4")
known_good_snapshot=''
activation_started=0

cleanup() {
  [[ -z "$known_good_snapshot" ]] || rm -f -- "$known_good_snapshot"
}

restore_after_failure() {
  local status=$?
  trap - ERR
  if [[ "$activation_started" -eq 1 ]]; then
    printf '%s\n' 'Deployment failed after activation began; restoring the recorded known-good immutable manifest.' >&2
    if ! restore_immutable_release "$known_good_snapshot"; then
      printf '%s\n' 'ERROR: automatic restoration of the known-good immutable manifest failed.' >&2
    fi
  fi
  cleanup
  exit "$status"
}

trap restore_after_failure ERR
trap cleanup EXIT

"$(dirname "$0")/render.sh" "$env_file" >/dev/null
"$(dirname "$0")/render.sh" "$known_good" >/dev/null
known_good_snapshot=$(snapshot_immutable_manifest "$known_good")
"$(dirname "$0")/../db/backup-postgres.sh" "$env_file" "$backup_dir"
compose "$env_file" pull
activation_started=1
compose "$env_file" up --detach --remove-orphans --wait --wait-timeout 180
compose "$env_file" ps
"$(dirname "$0")/smoke.sh" "$env_file" "$base_url"
record_known_good_manifest "$env_file" "$known_good"
activation_started=0
printf '%s\n' 'Deploy and mandatory HTTPS/provider/Taskiq smoke completed successfully.'
