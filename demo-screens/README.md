# Demo screenshots - 2026-07-17

Flux local documentat integral: autentificare -> inventarierea tuturor meciurilor viitoare ale zilei -> analiză -> actualizare cote -> selecție candidați -> preflight bilete -> generare -> revizuire -> activare paper -> istoric.

- Data operațională: **2026-07-17**
- Fus orar: **Europe/Bucharest**
- Dataset analizat: **#162**
- Manifest complet: [`manifest.json`](./manifest.json)
- Capturi: **68 PNG**, numerotate cronologic

## Meciurile zilei luate în calcul

| ID | Ora locală | Competiție | Meci | Rezultat analiză |
|---:|:---:|---|---|---|
| 2156 | 12:30 | NPL South Australia | Campbelltown City - Adelaide Comets | eligibil pentru bilet |
| 2157 | 13:30 | NPL South Australia | West Torrens - Para | eligibil pentru bilet |
| 2041 | 21:00 | Primera Nacional | Deportivo Maipu - San Martin T. | analizat, blocat de `insufficient_home_team_history` și `insufficient_away_team_history` |

Toate cele trei meciuri viitoare disponibile local pentru ziua curentă au fost incluse în dataset și în rulările de analiză. Al treilea meci nu a fost forțat într-un bilet deoarece regulile de calitate au raportat istoric insuficient pentru ambele echipe.

## Rezultatul biletelor

- Run-uri sursă: **#1074-#1081** (7 `completed`, 1 `partial`, 0 `failed`)
- Candidați finali selectați: **15**, proveniți din **2 meciuri eligibile distincte**
- Lot: **#150**, revizia 1
- Bilet **#TKT-1028**: Adelaide Comets `away`, 1X2 @ **4.33**, miză **EUR 10**, retur potențial **EUR 43.30**
- Bilet **#TKT-1029**: West Torrens `home`, 1X2 @ **1.12**, miză **EUR 10**, retur potențial **EUR 11.20**
- Activare: **paper/internă**, ambele bilete `open`, debit intern total **EUR 20**
- Nu a fost trimis niciun ordin extern; acțiunile `Simulează BACK LIMIT` au rămas neexecutate.

Cererea inițială de 3 bilete a fost blocată corect deoarece intervalul implicit de cote lăsa un singur meci eligibil distinct. Captura `52` păstrează blocarea. Configurația a fost ajustată transparent la 2 bilete distincte, interval 1.01-100, iar al doilea preflight a confirmat 15/15 candidați eligibili și 2 meciuri unice.

## Probleme găsite și rezolvate

1. Analiza live eșua la persistarea raportului cu `Object of type datetime is not JSON serializable`. `snapshot_key` este acum serializat ISO-8601; testul de regresie verifică inclusiv `json.dumps`.
2. După activare, UI afișa cele două bilete, dar sumarul și badge-ul indicau `Active 0`. Totalurile sunt acum reîncărcate după activare; captura `67` confirmă `Active 2` în ambele locuri.

## Indexul fazelor

- `01-06`: autentificare, dashboard, Data Hub și încărcarea datasetului
- `07-14`: preflight cu toate cele 3 meciuri și prima analiză, inclusiv eroarea de serializare
- `15-24`: reanalizare după corecție și constatarea cotelor neeligibile/stale
- `25-33`: refresh complet eșuat prin timeout și refresh-uri țintite reușite pentru toate cele 3 meciuri
- `34-44`: analiza finală 1X2, filtre, selecția candidaților și handoff către Bilete
- `45-52`: configurație, preflight și blocarea responsabilă a tentativei de 3 bilete
- `53-59`: ajustarea configurației, preflight reușit și generarea lotului #150
- `60-63`: revizuirea individuală, confirmarea și activarea lotului
- `64-66`: bilete active și istoric
- `67-68`: retestarea defectului UI, `Active 2`, și istoricul final al lotului #150

## Verificare finală

- Backend: `448 passed`
- Frontend type/Svelte check: `0 errors, 0 warnings`
- Frontend unit: `27 passed`
- Playwright hybrid complet: `41 passed`
- Build SvelteKit production: reușit
- Svelte autofixer pentru `TicketsPanel.svelte`: `0 issues`
