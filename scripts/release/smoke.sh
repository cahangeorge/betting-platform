#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
[[ $# -eq 2 ]] || fail "usage: $0 <production-env-file> <https-base-url>"
env_file=$(require_env_file "$1")
base_url=${2%/}
[[ "$base_url" =~ ^https:// ]] || fail "smoke target must use https"
"$(dirname "$0")/render.sh" "$env_file" >/dev/null
require_command curl
for path in /health /ready /; do
  curl --fail --silent --show-error --max-time 15 "$base_url$path" >/dev/null
done
compose "$env_file" exec --no-TTY worker python -m app.tasks.runtime worker
compose "$env_file" exec --no-TTY scheduler python -m app.tasks.runtime scheduler
compose "$env_file" exec --no-TTY api python -m app.tasks.smoke
compose "$env_file" exec --no-TTY api python -m app.diagnostics.provider_canary
printf 'Production HTTPS smoke passed for %s\n' "$base_url"
