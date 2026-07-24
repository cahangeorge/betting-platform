#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
env_file=$(require_env_file "$@")
require_command docker
validate_immutable_images "$env_file"
validate_required_values "$env_file"
compose "$env_file" config --quiet
printf '%s\n' 'Production compose template validated without rendering secret values.'
