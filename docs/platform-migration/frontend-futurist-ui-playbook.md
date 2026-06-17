# UI Playbook: Futuristic Football + SvelteKit PWA

## Direcție vizuală
- Atmosferă: blur + glassmorphism + neon accent pentru piețe și cote.
- Paletă: `football-night` (deep blue, graphite, emerald, violet accent micro), dar fără dominație de mov.
- Fonturi:
  - heading / teams: `Orbitron` sau similar futurist,
  - body: `Manrope` sau `Inter` latente,
  - numerice/odd-uri: `JetBrains Mono`.
- Textură: gradient animat subtil pe fundal + particule fine (low-cost CSS), fără a afecta performanța.

## Principii UX
1. Conversie rapidă: din descoperire direct în bilet (`1 tap` de la rezultat la bet-slip).
2. Transparență: badge clar `real` / `stale` / `demo`.
3. Mobile-first, touch target clar pentru selectare piețe.
4. Vizibilitate risc: semnale color pentru `edge`, `volatilitate`, `source_ok`.
5. Feedback imediat: toate acțiunile de bet-slip + job-uri confirmate vizual + toast + undo.

## Componente obligatorii (SvelteKit)
- **Glass cards**: `dashboard`, `match cards`, `live odds`, `prediction tiles`.
- **Odds ticker strip**: șir scrollat de cote pentru meciuri active.
- **Edge meter**: bară de color progresivă (low/medium/high).
- **Prediction lens**: popup mini-care arată scor istoric + factorii principali.
- **Betslip rail**: persistentă pe mobile (bottom drawer) + desktop sidebar.
- **Motion**:
  - entering: fade-up + blur release (150-220ms),
  - updates de live: scale 1.0 -> 1.02 pentru piese noi,
  - noisemesh discret pe secțiuni de pariuri.

## Layout pentru mission-critical pages

### `/scrape`
- card-uri de job cu timeline (queued/running/succeeded/failed),
- quick presets (league + period),
- monitor per-șansă (match count, odds count, avg confidence, duration).

### `/predict`
- split view:
  - filtrare pe ligă/land/interval,
  - tabel pe selecții cu sortare pe edge + confidence,
  - action `add to slip` direct pe fiecare rând.

### `/tickets`
- stadiu ticket cu timeline `created -> evaluated -> live -> settled`,
- indicator ROI, stake, risk score.

### `/live`
- grid de meciuri active cu `state delta` (evenimente, goluri, cote schimbare),
- switch `simulation mode` on pentru meciuri fără stream real.

## Tema tehnică (CSS-first)
- variabile CSS în `frontend/src/app.css`:
  - `--surface`, `--surface-soft`, `--surface-border`,
  - `--glass-bg`, `--glass-blur`, `--shadow-strong`.
- carduri cu `backdrop-filter: blur(16px)` + `background: color-mix`.
- animații prin clase utility + `prefers-reduced-motion` fallback.
- tokenizare de culoare per status (`--status-live`, `--status-demo`, `--status-stale`, `--status-locked`).

## Faza de implementare UI
1. **Faza A – Stabilizare**: refactor navigație, unificare bet-slip, indicatori real/demo.
2. **Faza B – Futurism**: aplicație de texturi, glass cards, motion și edge meter.
3. **Faza C – Live premium**: stream polling optimizat + ticket confidence tooltips.

## KPI de acceptanță
- Timp mediu de adăugare a unei selecții: ≤ 2 clicuri.
- Rată de conversie predict→ticket: +30% vs versiunea TanStack.
- Scădere erori UI la stare demo: 0 incident reportat fără etichetă „demo”.
