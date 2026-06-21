# TanStack Frontbet Legacy Archive

This folder preserves the technical and product details of the old `frontbet/` TanStack Start implementation before removing it from the active workspace.

Current active platform: `frontend/` — SvelteKit/Svelte 5.

Archived legacy platform: `frontbet/` — TanStack Start + React 19 + Vite 7 + Prisma/SQLite.

## Why this archive exists

The project is standardizing on the SvelteKit platform. The TanStack implementation contained useful product ideas, page layouts, visual block patterns, data workflows, and integration details for OddsHarvester, soccerdata, penaltyblog, and flumine. Those details are captured here so future Svelte work can port or reference them without keeping the old app source directory in the root workspace.

## File map

- `overview.md` — stack, architecture, commands, project boundaries.
- `pages/routes.md` — route-level UX and page behavior.
- `components/visual-blocks.md` — reusable visual blocks and component behavior.
- `workflows/data-scrape-history.md` — Data page, OddsHarvester, SoccerData, job history, match browser.
- `workflows/predict-analytics.md` — prediction, model training, analytics toolkit.
- `workflows/tickets-trading.md` — tickets, value bets, saved tickets, Flumine concept.
- `reference/data-model.md` — Prisma/SQLite schema concepts.
- `reference/server-functions.md` — TanStack server functions and bridges.
- `reference/ui-style-system.md` — design tokens, theme behavior, layout classes.
- `reference/file-inventory.md` — key source files preserved as an inventory.

## Important migration note

Do not re-enable `frontbet/` as a product platform. Reuse only the documented concepts in the SvelteKit `frontend/` and FastAPI `backend/` current platform.
