# Migrarea API: frontbet → betfront backend + SvelteKit frontend

## Context
`frontbet` folosește acțiuni server-side și legături directe către proiecte Python.  
`betfront` (`backend/` + `frontend/`) trebuie să folosească un strat de API REST stabil și versionat (`/api/v1/*`) + servicii de bridge controlate.

## Mapping curent (ce există deja)

| Domeniu | `frontbet` (server actions / helpers) | `backend` actual | Status |
|---|---|---|---|
| Matches / datasets | `src/server/scraper.ts`, `src/server/soccerdata.ts` | `api/v1/data.py`, `services/scraper.py` | P1 |
| Odds + match ingestion | `src/server/scraper.ts` + Prisma job payload | `models/scrape.py`, `services/scraper.py`, `api/v1/jobs.py` | P0 |
| Predicții | `src/server/predictions.ts`, `src/server/penaltyblog*.ts` | `services/prediction_engine.py`, `api/v1/predictions.py`, `services/python_bridge.py` | P0 |
| Tickets | `src/server/tickets.ts`, `mcp` UI state | `api/v1/tickets.py`, `services/ticket_engine.py` | P0 |
| User/account | UI local + implicit | `api/v1/auth.py`, `api/v1/bankroll.py` | P1 |
| Live context | Pagini dedicate + date demonstrative | `api/v1/live.py`, `/live` + `/value-bets` | P1 |
| Catalog/market | UI static + dataset fields | `api/v1/catalog.py` | P1 |
| Jobs + rezultat | UI polling job/status | `api/v1/jobs.py`, `models/job.py` | P1 |

## Gap-uri API de acoperit înainte de release

1. **Standardizarea modelului de predicție**
- lipsă: `prediction` la nivel de selecție `(match_id, market, outcome)` cu snapshot odds + EV.
- nevoie: endpoint de `GET /api/v1/predictions` cu agregat + metadate de model/run;
- nevoie: endpoint de `POST /api/v1/predictions/run` care cere input deterministic.

2. **Trasabilitatea ticketelor**
- lipsă: legătură directă între predicție (selection) și picioarele din bilet.
- nevoie: endpointul de ticket să accepte `prediction_selection_id` + `odds_snapshot_id`.

3. **Unicitatea datelor scrape-uite**
- gap: unele joburi raportează succes fără număr de meciuri/odduri persistate.
- nevoie: contract explicit de rezultat job cu `persisted_matches`, `persisted_odds`, `errors`.

4. **Stare „live” separată de demo**
- gap: unele page-uri pot trece pe demo fallback fără indicator clar.
- nevoie: endpointuri de stare `isDemo`, `isDataStale`, `source` per payload.

5. **PWA & sync offline**
- gap: API nu are endpoint de heartbeat/version.
- nevoie: `GET /api/v1/health` cu `schema_version`, `jobs_active`, `bridge_ready`.

## Adapter de tranziție recomandat
- Definim un `client API intern` în `frontend/src/lib/api/` care:
  - normalizează răspunsurile vechi (`snake_case`/`camelCase`, id-uri, paginare),
  - întoarce erori tipizate (`BridgeError`, `NoDataError`, `DemoDataWarning`),
  - ascunde diferențele de backend de UI.
- Frontend nu apelează direct bridge-urile Python; backend răspunde prin servicii.

## Schimbări de prioritate (ordine de implementare)

1. **P0:** job ingestion + prediction persistence + ticket selection links.
2. **P1:** dashboard+live contracts, state de demo, job health/trace.
3. **P2:** catalog extins, paginare unitară, filtre globale.

## Contract minim pentru stabilitate
- `200` valid: date reale persistate, cu `source` + `generated_at`.
- `200` zero-result: explicit `{ status: "empty", reason, can_retry }`.
- `5xx`: eșec de bridge/scrape clar în payload + ID job + retry token.
- Niciun endpoint de producție nu returnează date simulate fără `is_demo: true`.
