#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
[[ $# -eq 3 ]] || fail "usage: $0 <current-production-env-file> <previous-immutable-env-file> <https-base-url>"
current=$(require_env_file "$1")
previous=$(require_env_file "$2")
base_url=$3
"$(dirname "$0")/render.sh" "$current" >/dev/null
"$(dirname "$0")/render.sh" "$previous" >/dev/null
restore_immutable_release "$previous"
"$(dirname "$0")/smoke.sh" "$previous" "$base_url"
printf '%s\n' 'Rollback restored and health-checked the explicit prior immutable manifest. Database migrations are not rolled back automatically.'
