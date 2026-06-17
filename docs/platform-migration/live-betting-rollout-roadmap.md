# Roadmap: Live Betting Section (verificare planuri + config actuale)

## Obiectiv
Secțiunea live să fie operațională, nu doar demo: job polling, cotații în timp real, recomandări filtrabile pe siguranță.

## Niveluri de maturitate

### Nivel 0 — Verificare
- Confirmare că `backend` are endpointuri active (`/api/v1/live/*`), stări de job și cache control.
- Verificare `bridge` readiness pentru sursele folosite.
- Măsurare latență refresh per pagină.

### Nivel 1 — Live candid
- Ingestă doar meciuri active (`status != finished`).
- Păstrează `as_of` la fiecare cotă.
- Afișează:
  - live odds,
  - scor curent,
  - schimbări mari (de la X%).
- Nu recomandă automată; doar etichete informativ.

### Nivel 2 — Live cu recomandări
- Adaugă `live_value_candidates` (EV + spread + edge intraday).
- UI permite `Add to slip` doar dacă `data_age < 30s` și `source_ok = true`.
- Include warning pe piețe instabile.

### Nivel 3 — Live full
- Streaming (polling adaptiv 2-15s).
- gestionare evenimente: gol/red card/penalty prin reconciliere manuală sau feed ext.
- Settlement semi-automat pentru meciuri finalizate.

## Tehnici / instrumente suplimentare
- **Queue orchestration**: refresh jobs în backoff exponențial la rate-limit.
- **Caching stratificat**: hot matches în memorie scurt-term, istoric persistent.
- **Guardrails**:
  - rate-limit pe endpointuri live,
  - circuit-breaker pe surse cu degringoladă,
  - degradare la `demo` doar explicit.

## Verificare configurare
- Pentru fiecare job live:
  - source uptime,
  - timeout per request,
  - retries,
  - last_success_at.
- Pentru fiecare recomandare:
  - `selection_age`,
  - `odds_freshness`,
  - `model_drift_flag`.

## Test plan (în 3 etape)
1. **Test local deterministic** (fără internet) — verify UI states, empty/fallback behavior, failure banners.
2. **Test hybrid** — backend real + date parțial reale + seed.
3. **Test live full** — scrapere reale + end-to-end predict → ticket → settle.

## Milestones
1. week 1: separă live state from demo + heartbeat + health.
2. week 2: implement stream-like refresh + confidence + lock rules pentru bilet.
3. week 3: settlement path + audit trace.
4. week 4: regim de stabilizare + observability (dashboard error + latency).
