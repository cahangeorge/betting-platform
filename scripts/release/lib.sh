#!/usr/bin/env bash
set -euo pipefail

readonly RELEASE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly PRODUCTION_COMPOSE="$RELEASE_ROOT/deploy/production/compose.yml"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"; }
require_file() { [[ -f "$1" ]] || fail "required file not found: $1"; }

require_env_file() {
  [[ $# -eq 1 ]] || fail "usage: $0 <production-env-file>"
  require_file "$1"
  printf '%s\n' "$1"
}

compose() {
  local env_file=$1; shift
  docker compose --env-file "$env_file" -f "$PRODUCTION_COMPOSE" "$@"
}

snapshot_immutable_manifest() {
  local manifest=$1 snapshot
  require_env_file "$manifest" >/dev/null
  snapshot=$(mktemp "${TMPDIR:-/tmp}/bet-known-good-manifest.XXXXXX.env")
  chmod 600 "$snapshot"
  cp -- "$manifest" "$snapshot"
  printf '%s\n' "$snapshot"
}

record_known_good_manifest() {
  local candidate=$1 known_good=$2 directory temporary
  require_env_file "$candidate" >/dev/null
  require_env_file "$known_good" >/dev/null
  directory=$(dirname "$known_good")
  temporary=$(mktemp "$directory/.bet-known-good-manifest.XXXXXX")
  chmod 600 "$temporary"
  cp -- "$candidate" "$temporary"
  mv -f -- "$temporary" "$known_good"
}

restore_immutable_release() {
  local env_file=$1
  compose "$env_file" pull api worker scheduler frontend nginx
  compose "$env_file" up --detach --no-deps --wait --wait-timeout 180 api worker scheduler frontend nginx
  compose "$env_file" ps
}

validate_immutable_images() {
  local env_file=$1 key value
  for key in POSTGRES_IMAGE REDIS_IMAGE BET_API_IMAGE BET_FRONTEND_IMAGE NGINX_IMAGE; do
    value=$(grep -E "^${key}=" "$env_file" | tail -n1 | cut -d= -f2- || true)
    [[ "$value" =~ @sha256:[a-fA-F0-9]{64}$ ]] || fail "$key must be pinned as an image@sha256 digest"
  done
}

validate_required_values() {
  local env_file=$1 key value
  for key in BET_PUBLIC_HOST BET_HTTP_PORT BET_HTTPS_PORT TLS_CERT_PATH TLS_KEY_PATH POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB BET_DATABASE_URL REDIS_PASSWORD BET_REDIS_URL BET_TASKIQ_RESULT_BACKEND_URL BET_JWT_SECRET; do
    value=$(grep -E "^${key}=" "$env_file" | tail -n1 | cut -d= -f2- || true)
    [[ -n "$value" && "$value" != "__SECRET_FROM_MANAGER__" ]] || fail "$key is missing or still a placeholder"
  done
}
