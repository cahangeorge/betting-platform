#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== Initializing forked external project submodules ==="
git submodule update --init --recursive OddsHarvester penaltyblog soccerdata

echo
printf '%-18s %s\n' "Project" "Status"
for project in OddsHarvester penaltyblog soccerdata; do
  if [ -d "$project" ]; then
    commit="$(git -C "$project" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    printf '%-18s %s\n' "$project" "present @ $commit"
  else
    printf '%-18s %s\n' "$project" "missing"
  fi
done

echo
cat <<'HELP'
Next runtime setup steps, run only the projects you need:

  cd OddsHarvester
  uv sync
  uv run playwright install chromium

  cd penaltyblog
  python -m venv .venv
  . .venv/bin/activate
  pip install -e .

  cd soccerdata
  uv sync

See docs/external-projects.md and backend/.env.example for backend bridge paths.
HELP
