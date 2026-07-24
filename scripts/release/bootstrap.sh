#!/usr/bin/env bash
set -euo pipefail
umask 077
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

[[ $# -eq 3 ]] || \
  fail "usage: $0 <production-env-file> <https-base-url> <new-known-good-immutable-env-file>"
[[ "${BET_BOOTSTRAP_CONFIRM:-}" == "BOOTSTRAP" ]] || \
  fail "set BET_BOOTSTRAP_CONFIRM=BOOTSTRAP to acknowledge first-deployment bootstrap"

env_file=$(require_env_file "$1")
base_url=$2
known_good=$3
[[ ! -e "$known_good" ]] || \
  fail "bootstrap refuses an existing known-good manifest; use deploy.sh for upgrades"

activation_started=0

stop_failed_bootstrap() {
  local status=$?
  trap - ERR
  if [[ "$activation_started" -eq 1 ]]; then
    printf '%s\n' \
      'Bootstrap failed after activation began; stopping candidate containers without deleting volumes.' >&2
    compose "$env_file" down --remove-orphans >/dev/null 2>&1 || true
  fi
  exit "$status"
}

trap stop_failed_bootstrap ERR

"$(dirname "$0")/render.sh" "$env_file" >/dev/null
compose "$env_file" pull
activation_started=1
compose "$env_file" up --detach --remove-orphans --wait --wait-timeout 180
compose "$env_file" ps
"$(dirname "$0")/smoke.sh" "$env_file" "$base_url"
record_known_good_manifest "$env_file" "$known_good"
activation_started=0
printf '%s\n' \
  'First deployment bootstrapped and recorded as the initial known-good immutable manifest.'
