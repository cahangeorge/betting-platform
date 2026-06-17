# Data Flow & Prediction Engine (meciuri viitoare + scor istoric)

## Obiectiv
Crearea biletelor trebuie să se bazeze pe:
1. meciuri viitoare cu cote curate,
2. scoruri istorice relevante (echipă acasă/dușman/forme),
3. output predictiv cu probabilitate + edge + justificare.

## Fluxul propus

1. **Ingestă surse**
- `OddsHarvester` produce meciuri viitoare + piețe.
- `soccerdata` produce istoricul și statisticile brute.
- `penaltyblog` produce predicții sau scoruri auxiliare.

2. **Normalizează + validează**
- fiecare meci primește un ID canonical (sursă, competiție, dată, echipe).
- odds-urile sunt mapate pe piețe standardizate (`1x2`, `over_under`, `btts`, etc.).
- scorurile istorice includ medii pe ultimele `N` partide, home/away forma, H2H dacă există.

3. **Persistență**
- `Match` + `Team` + `League` + `Country` + `OddsEntry` + `PredictionSession` + `PredictionSelection`.
- la rulare, se salvează și snapshot-ul de model (`model_version`, `params`, `features_hash`).

4. **Predictie**
- pentru fiecare meci eligibil:
  - colectăm feature set de istoric (`past_goals_for`, `past_goals_against`, `home_advantage`, forma recentă),
  - rulăm una sau mai multe strategii,
  - generăm selecții cu `probability`, `implied_probability`, `edge`, `confidence`.

5. **Bet-slip și ticket**
- utilizatorul alegă selecții pe UI,
- biletul stochează:
  - `selection_id`,
  - `odds_snapshot_at_selection`,
  - `stake`, `status` (`pending`, `won`, `lost`, `void`).

6. **Settlement**
- la scor final, ticketele se rezolvă prin regulă de piață.
- rezultatul salvează `actual_outcome`, `settled_at`, `actual_odds`.

## Design de date pentru predictii

### Obiect minim `PredictionSelection`
- `match_id`
- `market` (`1x2`, `over_under`, `btts`, `asian_handicap`, ...)
- `selection` (ex: `home`, `over_2_5`, `yes`)
- `model_name` (`poisson`, `dixon_coles`, `ensemble`)
- `probability`
- `implied_probability`
- `edge`
- `expected_value`
- `odds_snapshot_id`
- `as_of` (timestamp)

### Obiect minim `MatchSignal` (feature derivat)
- scoruri medii pe ultimele 5/10 meciuri,
- goluri primite/scorate pe teren propriu/deplasare,
- rate BTTS, over/under din istoric,
- ritm recent (days since last match),
- forță echipe (elo sau rating intern dacă există).

## Tehnologii / tehnici recomandate
- **Model mix**: rulează minim două metode (baseline statistic + ensemble simplu) pentru stabilitate.
- **Kalman-like smoothing** pe sezoane pentru reducerea șocurilor la meciuri noi.
- **Backtest la rulare**: comparație win rate/ROI pe set de meciuri istorice înainte de a publica strategia.
- **Recalibrare periodică**: recalculare model la schimbări mari de piață (cozi de meciuri, loturi noi).

## Live section integration
- `/live` să nu prezinte predicții speculative ca live bets reale.
- pentru live se folosesc două tipuri:
  - `live_value_candidates` (cu coeficient de risc mai mare, refresh mai des),
  - `live_monitor_only` (informații fără recomandare directă).
- semnalizarea în UI: `confidence_band`, `data_age`, `source_ok`.

## Criterii de calitate
1. 100% din bilet trebuie să aibă sursă validă de scor/cotație.
2. Nu se permite bet-slip pe meciuri fără interval de cote la min. `30` secunde.
3. Orice prediction fără margine minimă (`edge`) clară se marchează ca `low_confidence`.
4. P0 checks automate: dacă `job` termină fără `persisted_matches > 0` -> ticket flow blocat.
