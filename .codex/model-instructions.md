# Bet Codex Model Instructions

Always read `AGENTS.md` first. This repo-local setup complements the global Codex/OMX setup in `~/.codex`; it must not duplicate global MCP registrations, hooks, plugins, or credentials.

## Workflow

- Start with `git status --short --branch` at the root and, when touching nested repos, inspect their own status too.
- Treat `OddsHarvester/`, `penaltyblog/`, and `soccerdata/` as submodules/nested projects; do not mutate them unless the task explicitly includes them.
- Current platform is `frontend/` SvelteKit plus `backend/` FastAPI. `betfront/` is archived legacy UI unless explicitly requested.
- Use installed Agent Skills when relevant; for non-trivial changes use plan -> incremental implementation -> verification -> review.
- For Svelte changes, use Svelte MCP or current official docs first and run Svelte checks/autofix when available.
- For browser-visible behavior, prefer Playwright or Chrome DevTools MCP evidence.

## Verification defaults

Frontend commands run from `frontend/`:

- `pnpm check`
- `pnpm test:unit`
- `pnpm test:e2e`
- `pnpm build`

Backend commands run from `backend/`:

- `pytest`
- `uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload`
- `alembic upgrade head`

Integrated local defaults: frontend `127.0.0.1:5175`, backend `127.0.0.1:8001`.


## Model routing

Use `docs/codex/model-routing.md` as the routing policy.

- Start with `gpt-5.3-codex-spark` explorer agents for read-only lookup.
- Use `gpt-5.4` medium for normal implementation.
- Escalate to `gpt-5.5` high only for verification gates, high-risk architecture, security/auth/billing, migrations, scraper brittleness, or repeated failures.
- Keep context small: activate only the skill/agent docs needed for the current task.
