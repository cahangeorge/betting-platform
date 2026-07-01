# Agent Instructions - `bet` workspace

Multi-project sports betting analytics workspace. The current product platform is the SvelteKit frontend in `frontend/` plus the FastAPI backend in `backend/`.

**Default target: `frontend/` (SvelteKit/Svelte 5).** `betfront/` is an archived Astro/React project; do not modify or run it unless the user explicitly asks for legacy/archive work. `frontbet/` is a distinct pre-existing legacy project; do not touch it unless explicitly told to.

## Sub-projects

| Project | Stack | Role | Install | Test |
|---|---|---|---|---|
| [frontend/](frontend/package.json) | Node 22, pnpm, SvelteKit 2, Svelte 5, Vite 6, Tailwind 4 | Current web platform UI | `pnpm install` | `pnpm check`, `pnpm test:unit`, `pnpm test:e2e` |
| [backend/](backend/pyproject.toml) | Python >=3.12, FastAPI, SQLAlchemy async, Alembic, Postgres | Current API, auth, prediction/ticket services, Python bridge host | `pip install -e .[dev]` | `pytest` |
| [OddsHarvester/](OddsHarvester/CLAUDE.md) | Python >=3.12, uv, Playwright | CLI scraper for OddsPortal.com | `uv sync && uv run playwright install chromium` | `uv run pytest tests/ -q` |
| [penaltyblog/](penaltyblog/README.md) | Python >=3.10, setuptools + Cython | Football predictive models, scrapers, ratings | `pip install -e .` | `pytest` or `make test` |
| [soccerdata/](soccerdata/README.rst) | Python >=3.10, uv, Selenium | Multi-source football data scrapers | `uv sync` | `make test` |
| [flumine/](flumine/README.md) | Python >=3.9, pip | Betfair/Betdaq trading framework, standalone | `pip install -e .` | `pytest` |
| [betfront/](betfront/package.json) | Node, pnpm, Astro + React, Prisma + SQLite | Archived legacy web app and bridge scripts | Only if asked | Only if asked |

## Current platform: `frontend/`

Run all frontend commands from `frontend/`. Do not install or run app commands from the repo root.

| Command | What |
|---|---|
| `pnpm dev` | Vite/SvelteKit dev server on `127.0.0.1:5175` with `--strictPort` |
| `pnpm build` | Production SvelteKit build with `@sveltejs/adapter-node` |
| `pnpm preview` | Preview the built app |
| `pnpm check` | `svelte-kit sync && svelte-check --tsconfig ./tsconfig.json` |
| `pnpm test:unit` | Node test runner for `tests/unit/**/*.test.ts` |
| `pnpm test:e2e` | Hybrid Playwright tests, Chromium, `E2E_MODE=hybrid` |
| `pnpm test:e2e:live` | Live Playwright tests, Chromium, `E2E_MODE=live` |

Frontend details:

- SvelteKit routes live under `frontend/src/routes/`; shared UI lives under `frontend/src/lib/components/`; API clients live under `frontend/src/lib/api/`; shared state lives under `frontend/src/lib/stores/`.
- The Vite dev server proxies `/api` to `http://localhost:8001`. For integrated local testing, start the backend on port `8001`.
- The frontend API client intentionally uses same-origin `/api` requests so auth cookies flow through SvelteKit/Vite proxy behavior.
- Playwright config is `frontend/playwright.config.ts`. Hybrid tests live under `frontend/tests/e2e/hybrid/`; live tests live under `frontend/tests/e2e/live/`; artifacts are written outside the app at `.playwright-artifacts/frontend/test-results`.
- Use `lucide-svelte` for icons and keep UI changes consistent with the existing SvelteKit design system.
- This is a Svelte 5 project. When writing or modifying Svelte code, use the official Svelte MCP docs first, and run the Svelte MCP autofixer on changed `.svelte` or `.svelte.ts` components before finalizing.
- Prefer SvelteKit conventions: route `+page.svelte`/`+page.ts`/`+page.server.ts`, `$lib` imports, server-only code in `$lib/server`, and `svelte-check` for diagnostics.

## Current backend: `backend/`

Run all backend commands from `backend/`.

| Command | What |
|---|---|
| `pip install -e .[dev]` | Install FastAPI backend with test dependencies |
| `uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload` | Local API server for the Svelte frontend proxy |
| `pytest` | Backend test suite |
| `alembic upgrade head` | Apply database migrations |

Backend details:

- Environment variables use the `BET_` prefix. Defaults are loaded from `backend/.env` by Pydantic settings.
- Default local DB URL is `postgresql+asyncpg://postgres:postgres@localhost:5432/bet`; Docker/Podman compose files use their own Postgres service credentials.
- API entrypoint is `backend/app/main.py`; API routes are under `backend/app/api/v1/`; services are under `backend/app/services/`; SQLAlchemy models are under `backend/app/models/`.
- Backend bridge paths can point into `penaltyblog`, `soccerdata`, `OddsHarvester`, and legacy bridge scripts. Do not move sibling projects without updating bridge settings.

## Docker / composed runs

- `docker-compose.yml` runs backend on host port `8000` and frontend on host port `5173`.
- `docker-compose.podman.yml` runs backend on `127.0.0.1:8001`, frontend on `127.0.0.1:5174`, and nginx on `127.0.0.1:8080`.
- Do not assume compose ports match `pnpm dev`; inspect the active compose file before testing.

## Lint / format per project

| Project | Command |
|---|---|
| frontend | `pnpm check` |
| backend | `ruff format . && ruff check --fix .` when ruff is installed |
| OddsHarvester | `uv run ruff format . && uv run ruff check --fix src/` |
| penaltyblog | `black .` |
| soccerdata | `make format && make lint && make mypy` |
| flumine | `black .` |
| betfront | Archived; only run legacy checks if explicitly asked |

## Cross-project dataflow

```
frontend (SvelteKit) -> backend (FastAPI/Postgres) -> UI/API responses
                              ^
                              |
soccerdata -------------------+
OddsHarvester ----------------+
penaltyblog (models) ---------+   invoked through backend bridge services

flumine - standalone trading framework, not wired into current platform
betfront/frontbet - legacy/archive projects, not default targets
```

## Key constraints

- **Default to `frontend/` for UI work.** Do not use `betfront/` unless the user explicitly asks for the archived Astro project.
- **One project at a time.** `cd` into the sub-project before running install/test/lint/dev commands. Never install app dependencies at the repo root.
- **Do not unify package managers.** Use pnpm for `frontend`, pip for `backend`, uv for `OddsHarvester` and `soccerdata`, and each project's documented toolchain elsewhere.
- **Use Svelte tooling for Svelte changes.** Consult Svelte MCP docs for Svelte/SvelteKit questions, run Svelte MCP autofixer for changed components, then run `pnpm check`.
- **For integrated frontend tests**, ensure the backend is reachable at `http://127.0.0.1:8001` or set `E2E_BACKEND_URL`; the frontend dev server uses `127.0.0.1:5175`.
- **Network scrapers** hit live sites. Prefer mocked/VCR unit tests. Integration tests can break on upstream HTML changes; fix selectors or adapters rather than skipping failures.
- **Cython** in penaltyblog: rebuild after edits via `pip install -e .`.
- **Secrets never commit:** backend `BET_*` secrets, database URLs, Betfair creds, StatsBomb/Opta keys, and scraper credentials. Cache dir: `SOCCERDATA_DIR` for soccerdata.
- **No monorepo CI assumption.** Check each sub-project's own workflows and scripts before claiming CI coverage.
- **OddsHarvester** has its own [CLAUDE.md](OddsHarvester/CLAUDE.md) with detailed architecture and release process; read it before modifying that project.

## Codex Setup

Bet uses a lightweight repo-local setup that documents workspace behavior while keeping shared runtime tooling global.

- Canonical workspace guide: `AGENTS.md`
- Codex config: `.codex/config.toml`
- Codex model instructions: `.codex/model-instructions.md`
- Project agent roles: `.codex/agents/*.toml`
- Agent setup notes: `.agents/README.md`
- Codex setup docs: `docs/codex/setup.md`
- Svelte MCP registration for the active frontend: `.mcp.json`

Global MCP servers, shared skills, hooks, and the oh-my-codex plugin stay in `$CODEX_HOME` / `~/.codex`. Respect nested project/submodule instructions before changing `OddsHarvester/`, `penaltyblog/`, or `soccerdata/`.

## Model / Agent Routing

Use `docs/codex/model-routing.md` for cost/performance routing.

- Explorer agents use `gpt-5.3-codex-spark` with low reasoning for cheap read-only lookup.
- Executor agents use `gpt-5.4` with medium reasoning for normal implementation.
- Verifier/risk-review agents use `gpt-5.5` with high reasoning only for final evidence, high-risk decisions, or repeated failures.
- Do not load every skill/agent up front; activate only what the current task needs.
