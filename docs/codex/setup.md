# Bet Codex Setup

Bet uses a lightweight repo-local setup plus global Codex tooling.

## Files

- `AGENTS.md` — canonical workspace instructions.
- `CLAUDE.md` / `GEMINI.md` — pointers to `AGENTS.md`.
- `.mcp.json` — Svelte MCP server for the active SvelteKit frontend.
- `.codex/config.toml` — repo-local pointer to `.codex/model-instructions.md`.
- `.codex/model-instructions.md` — Bet-specific Codex instructions.
- `.codex/agents/*.toml` — project-specific agent roles.
- `.agents/README.md` — documents that plugins/hooks remain global.
- `.serena/project.yml` — project-aware Serena code-navigation configuration.
- `docs/codex/model-routing.md` — model/agent routing policy for quality and token efficiency.

## Global dependencies used

Do not vendor these into the repo unless explicitly requested:

- `context7` for current framework/library docs.
- `playwright` and `chrome-devtools` MCP for browser verification.
- `serena` for code navigation.
- `repomix` for repo context packaging.
- `oh-my-codex` for optional workflow/team orchestration.

## Current platform commands

Frontend commands run from `frontend/`:

```sh
pnpm dev
pnpm check
pnpm test:unit
pnpm test:e2e
pnpm build
```

Backend commands run from `backend/`:

```sh
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
pytest
alembic upgrade head
```

Integrated local defaults:

- frontend: `127.0.0.1:5175`
- backend: `127.0.0.1:8001`

## Boundaries

- Do not run app dependency installs from the root.
- Do not touch `betfront/` unless legacy work is explicitly requested.
- Treat `OddsHarvester/`, `penaltyblog/`, and `soccerdata/` as submodules/nested projects with their own status and instructions.
