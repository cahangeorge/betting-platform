# Feature Parity Matrix: Frontbet → Betfront (SvelteKit PWA)

**Scop:** păstrarea funcționalităților utile din first platform (`frontbet` / TanStack) și mutarea lor în noua țintă (`frontend` + `backend`) fără regresii de produs.

## Modul de comparare
- Coloana „Existing” = implementare prezentă în `frontbet`.
- Coloana „Target current” = starea actuală în `backend/` + `frontend/`.
- Coloana „Prioritate” = impact pentru fluxul „scrape → predict → ticket”.
- Coloana „Acțiune” = păstrat, refăcut sau poate fi eliminat.

| Feature | Existing (frontbet) | Target current | Prioritate | Acțiune |
|---|---|---|---|---|
| Auth + cont utilizator | parțial, non-final | implemented (signup/login + sesiune), poate fi consolidat | P0 | Păstrat, unificat cu sesiune + profil bankroll |
| Scrape jobs (OddsHarvester) | complet funcțional, cu istoric joburi | backend are endpointuri `jobs`, UI are pagină `/scrape` | P0 | Păstrat, standardizat pe rezultate persistente + cancel |
| Provider data ingest (soccerdata) | pagini dedicate, caching dataset | backend are servicii de fetch și modelare `scrape` | P0 | Păstrat, mutat în flow unificat Match/Odds |
| Predictive models (penaltyblog bridge) | server action + sesiuni + rezultate | bridge invocations + endpointuri `predictions` | P0 | Păstrat, refăcut pe model de `selection` (market/outcome) |
| Tickets/betslip | pagină ticket + drawer + selecții | drawer/betslip există, încă în rafinare | P0 | Păstrat, mutat la model de ticket auditabil |
| Data Hub / matches | `data-hub` + filtre + detalii | `data` + tabele + detalii backend | P1 | Păstrat, îmbunătățit cu taburi previzionate |
| Match/odds visual table | prezent în frontbet | prezent, dar neuniform la state real/fallback | P1 | Păstrat, standardizare schema și validări |
| Value bet logic | prezent, compară odd-uri și probabilitate | secțiune `/value-bets`, dar cu ambiguități când date lipsă | P1 | Păstrat + clarificare stări demo/fail |
| Live odds + tracker | minim în frontbet | `/live` existent cu date parțial reale | P1 | Păstrat, migrat la stream/update incremental |
| Dashboard operațional | implicit din pagina principală | `/+page.svelte` nou, conectat la backend | P1 | Păstrat ca hub principal |
| Charts/analitică | minimal | layerchart + componente dedicate | P1 | Păstrat, extins pe dashboard/performanță |
| E2E + smoke workflows | testare fragmentară | suită nouă hybrid/live în curs | P1 | Păstrat + consolidat |
| PWA install/offline | absent | shell PWA prezent | P2 | Întărit cu update/install states |

## Features ce rămân necesare (nu se elimină)
1. Flux complet de creație bilet pe bază de predictii (același output ca before, + trasabilitate).
2. Scraping-ul de meciuri + cotații pe mai multe piețe.
3. Integrare istoric scoruri echipe (penaltyblog + soccerdata) pentru features predictive.
4. Dashboard de urmărire rezultate / bankroll / PnL.
5. Stare clară de eroare când orice dependență externă nu livrează date.

## Ce poate fi eliminat (fără impact de produs)
- Artefacte generate local (`node_modules`, `test-results`, baze locale temporare).
- Configurații duplicate între proiecte (nu alegerile de framework).
- Scripturi demonstrative care nu intră în fluxul productiv.

## Recomandare de migrare
- Păstrează fluxul de produse din frontbet ca „source truth of behavior”, dar mută implementarea în:
  - `backend/app/` (orchestrare, normalizare date, reguli ticket),
  - `frontend/src/` (UX + păstrarea experienței).
- Nu menține două implementări active de business logic în paralel; frontbet rămâne arhivă de feature behavior.
