# External Forked Projects

The active platform is the SvelteKit frontend in `frontend/` plus the FastAPI backend in `backend/`.

The backend also integrates with several forked upstream projects. These are tracked as Git submodules so a fresh clone can initialize the expected sibling project directories.

## Default submodules

| Path | Fork URL | Branch | Purpose |
|---|---|---|---|
| `OddsHarvester/` | `https://github.com/cahangeorge/OddsHarvester.git` | `master` | OddsPortal scraper used by backend scrape jobs |
| `penaltyblog/` | `https://github.com/cahangeorge/penaltyblog.git` | `master` | Football statistical models and prediction utilities |
| `soccerdata/` | `https://github.com/cahangeorge/soccerdata.git` | `master` | Historical football data providers and scrapers |

## Optional local projects

| Path | Status | Purpose |
|---|---|---|
| `flumine/` | Optional, still ignored | Betfair/Betdaq trading framework; not wired into the active platform by default |
| `betfront/` | Archived legacy app, still ignored | Astro/React legacy project; do not use for current platform work unless explicitly requested |
| `frontbet/` | Removed from active workspace | Old TanStack Start platform; technical details preserved in `docs-tanstack-betfront-old/` |

## Clone/init commands

For a fresh clone:

```bash
git clone --recurse-submodules https://github.com/cahangeorge/betting-platform.git
```

If the repo is already cloned:

```bash
git submodule update --init --recursive
```

To update submodules to the latest commit on their configured branch:

```bash
git submodule update --remote --merge OddsHarvester penaltyblog soccerdata
```

Then commit the changed gitlink hashes in the root repo if the update is intentional.

## Runtime setup

Run setup commands from each submodule directory, not from the root.

```bash
cd OddsHarvester
uv sync
uv run playwright install chromium

cd ../penaltyblog
python -m venv .venv
. .venv/bin/activate
pip install -e .

cd ../soccerdata
uv sync
test -x .venv/bin/python
```

Backend bridge defaults expect repo-local paths such as:

```txt
OddsHarvester/.venv/bin/python
penaltyblog/.venv/bin/python
soccerdata/.venv/bin/python
```

The soccerdata bridge uses an existing Python interpreter. After `cd soccerdata && uv sync`, verify `soccerdata/.venv/bin/python` exists, then set `BET_SOCCERDATA_PYTHON` to that executable or another existing interpreter with soccerdata installed. You can override the other bridge paths in `backend/.env` with the `BET_*` variables documented in `backend/.env.example`.

## Important constraints

- Do not copy vendor code into the root repo.
- Do not run package installation from the root for these submodules.
- Keep submodule commits intentional and reviewable.
- Treat live scrapers as unstable external integrations; prefer mocked/HAR tests where possible.
