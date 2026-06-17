#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Detect container runtime (podman-compose or docker compose)
if command -v podman-compose &>/dev/null; then
    COMPOSE="podman-compose"
elif docker compose ps postgres &>/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    echo "Error: no container runtime found. Install podman-compose or docker compose."
    exit 1
fi

if ! $COMPOSE ps postgres 2>/dev/null | grep -q "Up"; then
    echo "Error: postgres is not running. Run scripts/setup.sh first."
    exit 1
fi

echo "=== Seeding Database ==="

echo "[1/3] Creating admin user (admin@betfront.com / admin123) ..."
$COMPOSE exec -T backend python -c "
import asyncio
from app.database import async_session_factory
from app.models.user import User
from app.services.auth import hash_password

async def seed():
    async with async_session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.email == 'admin@betfront.com'))
        existing = result.scalar_one_or_none()
        if existing:
            if not existing.is_admin:
                existing.is_admin = True
                await db.commit()
                print('       Admin user exists but is_admin was False — fixed to True.')
            else:
                print('       Admin user already exists with admin privileges — skipping.')
        else:
            admin = User(
                email='admin@betfront.com',
                name='Admin',
                password_hash=hash_password('admin123'),
                is_admin=True,
            )
            db.add(admin)
            await db.commit()
            print('       Admin user created with is_admin=True.')

asyncio.run(seed())
"

echo "[2/3] Creating sample bankroll ..."
$COMPOSE exec -T backend python -c "
import asyncio
from app.database import async_session_factory
from app.models.bankroll import Bankroll

async def seed():
    async with async_session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(select(Bankroll).limit(1))
        existing = result.scalar_one_or_none()
        if existing:
            print('       Bankroll already exists — skipping.')
        else:
            bankroll = Bankroll(
                name='Main Bankroll',
                initial_balance=10000.00,
                current_balance=10000.00,
                currency='GBP',
            )
            db.add(bankroll)
            await db.commit()
            print('       Sample bankroll created (\$10,000.00).')

asyncio.run(seed())
"

echo "[3/3] Running initial scrape job ..."
$COMPOSE exec -T backend python -c "
print('       Triggering initial scrape...')
print('       Scrape skipped — run POST /api/v1/data/scrape via API instead.')
"

echo ""
echo "=== Seeding complete ==="
echo "  Admin login:  admin@betfront.com / admin123"
echo "  Bankroll:     \$10,000.00"
echo ""
