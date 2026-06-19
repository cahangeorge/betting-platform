# Overview: Old TanStack `frontbet/` Platform

## Purpose

`frontbet/` was a sports betting analytics dashboard built with TanStack Start. It combined odds scraping, historical football data, prediction modeling, ticket generation, and a placeholder trading surface.

## Stack

| Area | Implementation |
|---|---|
| Framework | TanStack Start, React 19 |
| Bundler | Vite 7 |
| Routing | TanStack Router file-based routes in `src/routes` |
| Data fetching | TanStack Query |
| Server actions | `createServerFn` from `@tanstack/react-start` |
| Database | Prisma 7 + SQLite via `better-sqlite3` adapter |
| Styling | Tailwind CSS 4, CSS custom properties, Radix primitives |
| Forms/tables | TanStack Form, TanStack Table dependencies were installed; many screens used local state + custom primitives |
| External Python | `OddsHarvester`, `penaltyblog`, `soccerdata`, optional `flumine` concept |

## Commands from old app

```bash
pnpm dev            # Vite dev server on port 3000
pnpm build          # Vite production build
pnpm preview        # Preview production build
pnpm test           # Vitest
pnpm db:generate    # Prisma client generation
pnpm db:push        # Push SQLite schema
pnpm db:migrate     # Prisma migration dev
pnpm db:studio      # Prisma Studio
pnpm db:seed        # Seed database
```

## Active-vs-legacy decision

The active product is now:

```txt
frontend/  -> SvelteKit/Svelte 5 UI
backend/   -> FastAPI/Postgres API
```

The archived TanStack app had useful product surface area but duplicated concerns now owned by the current platform. Future work should port concepts rather than reviving the old app.

## External project expectations in old app

The old app assumed sibling repos and local virtual environments:

```txt
../OddsHarvester/.venv/bin/python
../penaltyblog/.venv/bin/python
../soccerdata/.venv/bin/python
```

Bridge scripts lived inside `frontbet/scripts/`:

```txt
penaltyblog_bridge.py
soccerdata_bridge.py
```

The current backend should eventually own these bridge scripts directly so no active service depends on a deleted UI app.
