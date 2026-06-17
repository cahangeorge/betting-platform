#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Betting Platform Setup ==="

if [ ! -f ".env" ]; then
    echo "[1/5] Creating .env from .env.example ..."
    cp .env.example .env
    echo "       Created .env — edit it with production values before deploying."
else
    echo "[1/5] .env already exists — skipping."
fi

echo "[2/5] Building Docker images ..."
docker compose build

echo "[3/5] Starting databases (postgres, redis) ..."
docker compose up -d postgres redis

echo "[4/5] Waiting for databases to become healthy ..."

echo "       Waiting for postgres..."
until docker compose exec -T postgres pg_isready -U betuser -d betting_platform >/dev/null 2>&1; do
    sleep 2
done
echo "       postgres is ready."

echo "       Waiting for redis..."
until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    sleep 1
done
echo "       redis is ready."

echo "[5/5] Running database migrations ..."
docker compose run --rm backend alembic upgrade head
echo "       Migrations complete."

echo "=== Starting full stack ==="
docker compose up -d

echo ""
echo "Services:"
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo "  Nginx:     http://localhost:80"
echo "  Postgres:  localhost:5432"
echo "  Redis:     localhost:6379"
echo ""
echo "Done."
