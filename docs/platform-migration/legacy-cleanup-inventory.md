# Legacy Cleanup Inventory (frontbet)

## Obiectiv
Curățenie fără pierdere de logică: păstrăm doar codul care descrie comportamentul de produs, eliminăm doar artefacte local-dezvoltare.

## Ce **se poate șterge sigur** (non-tracked/build/cache)
- `frontbet/node_modules/`  
  - dependențele Node sunt regenerate prin `pnpm install`.
- `frontbet/test-results/`  
  - rapoarte Playwright din rulări locale.
- `frontbet/dev.db`  
  - bază SQLite locală de test.
- `frontbet/prisma/dev.db`  
  - copie locală de dezvoltare.
- `frontbet/src/generated/prisma/dev.db`  
  - fișier gol/caché de generare.
- `frontbet/scripts/__pycache__/`  
  - cache Python temporar.
- `frontbet/downloaded_files/`  
  - lock-uri / fișiere temporare din rulări automate.
- fișiere de test manual de unică folosință:
  - `frontbet/test_bridge_sqlite.mjs`
  - `frontbet/test_bridge_real.mjs`
  - `frontbet/test_prisma.mjs`
  - `frontbet/test_seroval.mjs`

### Status la 2026-06-12
- executat: `frontbet/node_modules/`, `frontbet/test-results/`
- executat: `frontbet/dev.db`, `frontbet/prisma/dev.db`, `frontbet/src/generated/prisma/dev.db`
- executat: `frontbet/scripts/__pycache__/`
- executat: `frontbet/downloaded_files/`
- executat: `frontbet/test_bridge_sqlite.mjs`, `frontbet/test_bridge_real.mjs`, `frontbet/test_prisma.mjs`, `frontbet/test_seroval.mjs`
- arhivat: `frontbet/.vscode/`, `frontbet/.cta.json`, `frontbet/.cursorrules`, `frontbet/package-lock.json`
  - noua locație: `docs/archive/frontbet/`

## Ce **se păstrează** (comportament de produs)
- `frontbet/src/routes/*`  
  - UX + workflow-uri care arată ce a existat la versiunea anterioră.
- `frontbet/src/server/*`  
  - maparea datelor și integrarea Python bridges.
- `frontbet/src/lib/*` + `src/components/*`  
  - elemente de referință pentru paritate.
- `frontbet/IMPLEMENTATION.md` și `frontbet/README.md`
  - documentație de istoric tehnic.
- `frontbet/.vscode/`, `frontbet/.cta.json`, `frontbet/.cursorrules`, `frontbet/package-lock.json`
  - arhive/metadata de dezvoltare; acum arhivate în `docs/archive/frontbet/`.

## Ce **poate fi arhivat temporar** (nu se șterge imediat)
- `frontbet/IMPLEMENTATION.md` (se poate muta într-un dosar `docs/archive/frontbet/` dacă devine prea mare).
- `frontbet/README.md`.

## Reguli de rulare
1. Nu ștergem fișiere nețelese ca cod de business.
2. Nu ștergem subproiecte `penaltyblog/soccerdata/OddsHarvester`.
3. Nu ștergem bridge scripts sau contracte API folosite ca referință.
4. Toate ștergerile sunt doar din layer-ul local (`frontbet`), fără a afecta `betfront`.
