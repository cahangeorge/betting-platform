# Provider Data Platform Execution Plan

Updated: 2026-08-01
Status: local architecture through P8 complete; protected/live gates remain HOLD
Owner: Bet platform backend/control plane

## Outcome

Implementam o platforma de date in care `soccerdata` colecteaza in principal
fixtures/results/statistics, `penaltyblog` modeleaza datasetul canonic,
`OddsHarvester` colecteaza strict cotele care nu vin prin API, iar backend-ul
aplica politica, identitate, persistenta, lineage si orchestration.

## Scope

Included:

- `backend/`, `frontend/`, PostgreSQL, Redis/Taskiq;
- provider contracts si bridge wrappers;
- identitate multi-sursa si observatii versionate;
- benchmark, observabilitate, canary si rollback;
- documentatie, Serena si Codex Memory.

Excluded fara o decizie separata:

- modificarea proiectelor nested;
- microservicii noi;
- live/paper bet execution;
- credentiale, provider production activation sau scraping live neaprobat;
- commit, push, tag sau deploy.

## Acceptance criteria globale

- frontend-ul nu expune reguli specifice providerului;
- toate apelurile externe declara provider + capability si trec policy gate;
- toate observatiile au source ID, observed_at, schema version si digest;
- identitatea este provider-scoped si deduplicarea este idempotenta;
- Taskiq/Redis ramane transport, PostgreSQL ramane adevar durabil;
- joburile au stari terminale reale si lineage complet;
- benchmark-ul separa cold/warm cache si browser/API;
- fiecare faza are teste, rollback si evidence checkpoint;
- documentele canonice si memoriile indica acelasi checkpoint;
- public MVP ramane HOLD pana la gate-urile externe deja deschise.

## Dependency DAG

```text
P0 -> P1 -> P2 --------------------+
             \                     |
              +-> P2.5 ------------+-> P3 -> P4
                                   +-> P5
                         P3 + P4 + P5 -> P6 -> P7 -> P8
```

- P2.5 poate fi implementat in paralel cu migration work din P2 numai dupa ce
  identity ADR si queue payload contract sunt acceptate.
- P3 si P5 nu incep pana cand gate-urile P1, P2 si P2.5 sunt toate trecute.
- P4 poate pregati harness/golden data in paralel, dar promovarea depinde de un
  dataset canonic P3.
- P6 poate adauga observabilitate incremental, dar soak/SLO gate depinde de
  lane-urile P3-P5 folosite efectiv.

## P0 — Reconciliere si baseline

Tasks:

- [x] `PDP-000` inventariaza Git, submodule, porturi si platforma activa;
- [x] `PDP-001` reconciliaza Provider Adapter v1 cu bridge-urile existente;
- [x] `PDP-002` documenteaza matricea source-of-truth si arhitectura tinta;
- [x] `PDP-003` refresh-uieste headerul registrului MVP pentru SHA `0620287`,
  dirty state curent si Alembic 029;
- [x] `PDP-004` captureaza baseline local reproducibil fara apeluri live;
- [ ] `PDP-005` defineste datasetul exact de benchmark si drepturile surselor.

Gate:

- nicio contradictie intre status, program, ADR si source;
- nested projects raman nemodificate in aceasta faza;
- baseline-ul contine versiuni, comenzi si rezultate exacte.

Checkpoint 2026-08-02: baseline-ul reproducibil fara provider egress este
capturat in `docs/status/current-platform-status.md`: isolated PostgreSQL
`001 -> 043`, 938 passed/1 skipped, Ruff, frontend check/unit/typecheck/build,
Chromium 60/60, PWA 3/3, Firefox/WebKit 1/1, 35 contracte root si trei renderuri
Compose. `PDP-005` ramane separat deschis pana la selectia exacta a datasetului
formal si aprobarea drepturilor surselor; fixture-urile locale nu pot inchide
acea decizie.

Verification:

```bash
git status --short --branch
git submodule status
cd backend && .venv/bin/python -m pytest -q tests/test_provider_registry.py
cd backend && .venv/bin/ruff check app tests alembic
git diff --check
```

Rollback: document-only; eliminarea noilor linkuri/documente readuce starea
anterioara fara schimbare runtime.

## P1 — Capability enforcement la bridge

Tasks:

- [x] `PDP-100` defineste mapping operation -> capability pentru operatiile
  bridge folosite de platforma;
- [x] `PDP-100A` separa `adapter_key` de `source_key` si defineste descriptor,
  rights/quota/freshness policy per upstream;
- [x] `PDP-101` adauga un context explicit de executie
  (`production`, `canary`, `test`) fara boolean generic raspandit;
- [x] `PDP-102` ruteaza un apel read-only existent prin policy/capability gate
  folosind explicit `adapter_key` si `source_key`;
- [x] `PDP-103` adauga teste pentru unknown/missing capability,
  approval-required si disabled;
- [ ] `PDP-104` extinde treptat enforcement-ul la toate bridge-urile;
- [x] `PDP-105` emite event-uri redacted pentru decizia de politica;
- [x] `PDP-106` proiecteaza Provider Envelope v2 cu adapter/source version,
  job/run/correlation, freshness si provenance;
- [x] `PDP-107` pastreaza reader compatibil v1 si quarantine fail-closed pentru
  major versions necunoscute sau payload invalid.

Checkpoint 2026-08-02: urmatorul slice incremental din `PDP-104` este inchis.
Operatiile active legacy ale motorului de predictii `calculate_implied`,
`dixon_coles_weights` si `model_fit_predict` au mapping explicit si gate pe
identitatea `(penaltyblog, local-model, operation, production)` inainte de
subprocess. Gate-ul model-fit este run-wide, in afara exceptiilor per-target,
astfel incat refuzul de politica ramane sistemic. Verificare: **62** teste
provider/strategy si suita backend normala **898 passed / 46 skipped**, plus
Ruff complet. Task-ul ramane deschis pentru
deciziile separate OddsHarvester/browser si catalog/runtime; acestea nu sunt
declarate artificial complete si nu s-a executat trafic provider live.

Ownership initial:

- `backend/app/providers/`
- `backend/app/services/python_bridge.py`
- `backend/tests/test_provider_registry.py`
- `backend/tests/test_backend_owned_bridges.py`

Gate:

- comportamentul extern al apelului read-only ales ramane identic;
- production fail-closed, canary explicit si auditat;
- envelope v1 continua sa faca round-trip cu acelasi digest;
- envelope v2 face round-trip cu adapter/source, versions, correlation,
  freshness si provenance;
- payload invalid sau major version necunoscut produce quarantine cu motiv si
  digest, fara a ajunge la normalizare;
- nicio migrare, ruta noua sau modificare nested in primul slice.

Targeted verification:

```bash
cd backend
.venv/bin/pytest -q tests/test_provider_registry.py tests/test_backend_owned_bridges.py
.venv/bin/pytest -q tests/test_provider_envelope_versions.py tests/test_provider_canary.py
.venv/bin/ruff check app/providers app/services/python_bridge.py tests/test_provider_registry.py tests/test_backend_owned_bridges.py
```

Rollback: revert numai integrarea caller-ului; contractele v1 raman compatibile.

## P2 — Identitate multi-sursa si observatii

Precondition: ADR separat aprobat pentru schema si migration strategy, iar
contractul envelope v2/quarantine a trecut gate-ul P1.

Tasks:

- [x] `PDP-200` profileaza modelele `Match`, `MatchSource`, `MatchStat`,
  `OddsEntry`, `ScrapedDataset` si prediction lineage;
- [x] `PDP-201` defineste tabelele/provider mappings si cheile unice;
- [x] `PDP-202` defineste raw observation/envelope persistence si retention;
- [x] `PDP-203` implementeaza migration expand-only;
- [x] `PDP-204` implementeaza resolverul deterministic si review queue pentru
  mappings ambigue;
- [x] `PDP-205` implementeaza replay/idempotency si conflict handling;
- [ ] `PDP-206` backfill-uieste lineage-ul numai unde poate fi demonstrat.

Identity ADR acceptance:

- entitati canonice Team/Competition/Match;
- namespace `(adapter_key, source_key, source_id)`;
- mapping history temporal si audit/remap behavior;
- lifecycle pentru mapping ambiguu;
- FK/delete behavior si impact asupra dataset/prediction lineage.

Gate:

- upgrade pe DB noua si existenta;
- no drift;
- duplicate/replay/concurrency tests;
- mapping ambiguu nu este promovat automat;
- imaginea precedenta functioneaza pe schema expand-only in staging.

Planned evidence harness:

- `backend/tests/test_provider_identity.py`: source namespace, mapping history,
  ambiguous lifecycle, remap/replay si delete/FK behavior;
- `backend/tests/test_provider_observation_persistence.py`: v1/v2 ingest,
  quarantine isolation, digest/idempotency si concurrency;
- migration tests extinse in `backend/tests/test_db_foundation_migrations.py` si
  `backend/tests/test_orm_migration_alignment.py`;
- fresh temporary DB upgrade plus `alembic check`, cu manifestul exact al
  comenzilor si rezultatelor in checkpoint.

Rollback: codul poate reveni la schema veche; coloanele/tabelele adaugate nu se
sterg in release rollback.

## P2.5 — Minimum viable worker isolation

Precondition: identity ADR si queue payload contract aprobate; poate rula in
paralel cu implementarea P2, dar nu satisface singur preconditia P3/P5.

Tasks:

- [x] `PDP-250` defineste queue classes `provider-http`, `provider-browser`,
  `model-cpu` si `control/default`;
- [x] `PDP-251` aplica concurrency/resource caps si backpressure;
- [x] `PDP-252` defineste lease, retry si terminal-state taxonomy per lane;
- [x] `PDP-253` adauga metrici de baza pentru queue age, runtime, RSS,
  retry/fallback si freshness;
- [x] `PDP-254` separa gradual worker images/egress/secrets cand threat model-ul
  sau benchmark-ul justifica, fara a crea API/DB per provider.

Gate:

- browser si CPU work nu produc head-of-line blocking pe control jobs;
- restart/lease recovery nu dubleaza business state;
- fiecare lane are cap si observabilitate demonstrata;
- payload/queue contracts raman backend-owned.

Planned evidence harness:

- `backend/tests/test_provider_worker_isolation.py`: routing pe queue class,
  concurrency caps, backpressure si un control job care termina in timp ce un
  browser job este blocat controlat;
- `backend/tests/test_task_runs.py`: lease expiry/recovery, process kill si
  persistenta idempotenta fara dublare;
- integration harness cu Taskiq/Redis real: queue age, retry count, terminal
  state si recovery dupa restart;
- resource probe sub cgroup/container: peak RSS si PID count pentru fiecare
  lane, comparate cu limitele declarate;
- alert proof: injectare controlata a queue age/failure/RSS threshold si dovada
  ca alerta se activeaza si revine la normal.

Rollback: admission se inchide separat de consumer lifecycle; work-ul v1 se
dreneaza pe lane-ul si contractul original inainte ca acel consumer sau un
binary lane-unaware sa fie oprit. Nu exista repatriere in control si nu se
elimina limitele, istoricul sau lineage-ul.

## P3 — Ingestie soccerdata si cache stratificat

Precondition: gate-urile P1, P2 si P2.5 trecute.

Tasks:

- [x] `PDP-300` selecteaza operatiile primare: MatchHistory/ESPN pentru
  fixtures/results si FBref/Understat pentru stats/xG;
- [x] `PDP-301` dezactiveaza overlap-ul implicit cu scrapers penaltyblog;
- [x] `PDP-302` adauga job specs versionate pentru backfill si incremental;
- [x] `PDP-303` configureaza TTL/freshness per sursa si operatie;
- [x] `PDP-304` adauga checkpointing pe competitie/sezon/pagina;
- [x] `PDP-305` persista envelopes si dataset lineage;
- [x] `PDP-306` adauga rate limit, timeout, payload si resource bounds;
- [x] `PDP-307` verifica cold/warm cache cu fixture-uri/VCR, fara live implicit.

Gate:

- warm-cache valid nu acceseaza upstream;
- rerun identic nu dubleaza meciuri/observatii;
- partial failure este reluabil de la checkpoint;
- starea `no_data` nu este raportata ca succes cu date.

Rollback: oprire job type/provider capability; datele istorice raman auditate.

Evidenta G004: JobSpec/cursor imutabil, checkpoint si staging per pagina,
reluare dupa failure la pagina N, publicare terminala continua, limiter RPM
source-scoped cu cache-hit bypass, freshness/digest stabil si retry pentru
BridgeError sunt implementate. Generatia upstream este propagata de la pagina
zero, iar publicarea accepta exact paginile aceleiasi generatii, supersedeaza
atomic head-ul anterior si serializeaza inserturile concurente warm/refresh.
Apartenenta generation-page este separata de continutul deduplicat, astfel
incat continutul identic/revenit si generatiile goale autoritative sunt sigure.
Schema curata `001 -> 034`, `alembic check` si suita backend completa cu toate
gate-urile PostgreSQL au trecut: **787 tests**, inclusiv **6** gate-uri G004 PG.
Sursele live raman `APPROVAL_REQUIRED`; nu a fost efectuat niciun request live.

Handoff P3 -> P4 (2026-08-02): rezultatul terminal de ingestie expune
`provider_dataset_generation_ids` si scalarul exact `source_generation_id`
consumat de `TrainModelCommandV1`. Paginile cu cursor pastreaza lineage-ul
pentru observabilitate, dar nu se prezinta ca generatie antrenabila. Fluxul
operational este documentat in
`docs/runbooks/soccerdata-penaltyblog-pipeline.md`.

## P4 — Feature/model pipeline penaltyblog

Precondition: dataset canonic P3 disponibil; dezvoltarea harness-ului de model
poate incepe in paralel, dar promovarea depinde de P3.

Tasks:

- [x] `PDP-400` defineste feature-set schema si fingerprint;
- [x] `PDP-401` leaga inputul de dataset/observatii canonice;
- [x] `PDP-402` versioneaza model config si runtime dependency set;
- [x] `PDP-403` separa train/backtest/predict jobs;
- [x] `PDP-404` persista calibration, coverage si quality metrics;
- [x] `PDP-405` leaga fiecare output de odds snapshot-ul evaluat;
- [x] `PDP-406` adauga golden datasets si reproducibility tests;
- [x] `PDP-407` benchmark-uieste subprocess-per-call fata de un model
  serializat/preincarcat si adopta un worker long-lived numai daca gate-ul de
  performanta si izolare este demonstrat.

Gate:

- acelasi input + model version produce acelasi fingerprint;
- niciun model nu ruleaza pe dataset incomplet/fara freshness attestation;
- predictiile partiale nu alimenteaza tickets ca rezultat complet;
- backtest-ul nu foloseste date viitoare fata de observation time.

Rollback: dezactiveaza model version; pastreaza run history si outputs.

Evidenta G005: contractele stricte `penaltyblog-model-pipeline/v1`, feature
artifacts si model artifacts content-addressed, runtime attestation, joburile
durabile `train_model`/`backtest_model`/`predict_model`, cutoff-urile de
observation/forecast, legarea obligatorie la odds snapshot si blocarea P4
fail-closed in ticket governance sunt implementate. Pickle este incarcat numai
in subprocess-ul `model-cpu`, dupa verificarea root/digest/runtime; payload-urile
mari folosesc JSON canonic intr-un fisier privat, nu argv. Backtest-ul incarca
exact artefactul antrenat si feature matrix-ul verificat, foloseste rezultate si
metadata din observatiile generatiei pinned si persista Brier, log loss,
accuracy, ECE, quality rate si coverage. Benchmark-ul real offline, executat de
harness-ul versionat cu 80 randuri si patru tinte, a pastrat paritatea 1X2 si a
redus calea de predictie cu 74.7%; worker-ul rezident ramane dezactivat.
Migrarea curata `001 -> 038`, `038 (head)`, `alembic check`, suita backend cu
gate-uri PostgreSQL (**851 passed, 1 skipped**) si runtime-ul penaltyblog izolat
(**14 passed**) au trecut. Revizia `036` leaga PredictionRun de artefactul exact
si face terminal artifacts append-only in PostgreSQL. Reviziile `037`-`038`
blocheaza stergerea lineage-ului P4 folosit de ticket legs prin trigger si FK
`RESTRICT`, inclusiv cursa insert/delete; FK-ul ramane deliberat `NOT VALID`
pana cand singurul snapshot legacy orfan din baza locala este reconciliat, dar
protejeaza scrierile noi si stergerile parintelui. Expunerea activa revalideaza
o singura data per run fingerprint-ul complet inainte sa foloseasca fixture-ul
si liga pinned. API-ul monteaza volumul read-only, iar model-cpu ramane
writer-ul izolat. Sursele live nu au fost apelate.

## P5 — Odds lane si API-uri licentiate

Poate rula in paralel cu P3 dupa P1, P2 si P2.5, deoarece foloseste aceleasi
policy/identity/worker contracts, dar un source descriptor separat.

Tasks:

- [x] `PDP-500` defineste contractul comun events/bookmakers/markets/snapshots;
- [x] `PDP-501` evalueaza Sportmonks vs The Odds API pe coverage/cost/rights;
- [x] `PDP-502` implementeaza primul adaptor API read-only, secret-safe;
- [x] `PDP-503` pastreaza OddsHarvester fallback aprobat si limitat;
- [x] `PDP-504` implementeaza parity report intre API si OddsHarvester;
- [ ] `PDP-505` ruleaza canary 10/25/50/100, minimum 20 joburi per etapa ca
  smoke operational;
- [ ] `PDP-505A` calculeaza sample size si confidence interval pentru gate-ul
  formal de non-inferioritate si p95, stratificat pe workload;
- [x] `PDP-506` documenteaza rollback si quota exhaustion behavior.

Nota de checkpoint G006: contractele, jobul programat, cohortele deterministe,
quota ledger-ul durabil si harness-ul statistic offline sunt implementate.
`PDP-505` si `PDP-505A` raman deschise deoarece cer observatii live aprobate;
fixture-urile offline si cele 20 de joburi simulate/stage sunt smoke evidence,
nu dovada de promovare.

Gate:

- drepturile si costul au owner si aprobare;
- coverage si result parity >= 99% pentru campurile comparabile inainte de
  evaluarea vitezei;
- success delta nu scade cu >1pp numai dupa ce esantionul/CI poate sustine
  afirmatia; altfel ramane smoke evidence, nu promotion proof;
- p50 scade >=40% sau sec/result scade >=30%;
- RSS <=4 GiB/worker si fara egress credential leakage;
- rollback la providerul anterior este testat.

## P6 — Observabilitate avansata si operare

Tasks:

- [x] `PDP-600` dashboards/SLO-uri peste metricile minime din P2.5;
- [x] `PDP-601` limite per source/egress si quota-aware backpressure;
- [x] `PDP-602` retry taxonomy, circuit breaker si dead-letter/recovery;
- [ ] `PDP-603` metrics/logs/traces redacted si dashboards;
- [x] `PDP-604` alerts pentru queue age, freshness, failures, RSS si quota;
- [ ] `PDP-605` soak si worker restart/lease recovery;
- [x] `PDP-606` operator runbooks pentru provider disable/failover/replay.

`PDP-603` are agregate/redacted metrics, safe reason codes si dashboardul local
de operator; ramane deschis pentru exportul de traces si dashboard/retention
demonstrat in mediul protejat. `PDP-605` are dovada locala bounded de 10 repetari consecutive, 530/530
teste, inclusiv lease fencing/recovery si concurenta PostgreSQL. Ramane deschis
pentru un soak de durata cu restart real al workerului si timestamps/runtime
snapshots; dovada locala nu este promotion proof.

Gate:

- restart worker nu pierde business state;
- lease recovery nu dubleaza persistenta;
- browser fan-out ramane bounded;
- alertele sunt demonstrate, nu doar configurate.

## P7 — UI provider-agnostic si QA integrat

Tasks:

- [x] `PDP-700` expune coverage/freshness/lineage, nu detalii fragile de provider;
- [x] `PDP-701` diferentiaza cached/fresh/partial/no-data/failure;
- [x] `PDP-702` adauga progres pe fazele backfill/normalize/features/model;
- [x] `PDP-703` pastreaza retry-only-failed si idempotency;
- [x] `PDP-704` ruleaza contract/unit/hybrid/live-authorized E2E;
- [x] `PDP-705` verifica accessibility, responsive si PWA recovery.

Gate-ul local G007 a inchis 934 teste backend cu PostgreSQL, 125 unit frontend,
60/60 hybrid E2E si 3/3 PWA production. Live-authorized E2E ramane conditional:
nu a fost rulat deoarece nicio sursa/credentiala live nu a fost autorizata.

Gate:

```bash
cd frontend
pnpm check
pnpm test:unit
pnpm build
pnpm test:e2e
```

Live E2E ruleaza numai intr-un mediu si cu surse aprobate.

## P8 — Protected release

Acest plan nu inlocuieste gate-urile MVP existente. Raman obligatorii:

- `SEC-001` credential rotation;
- `QA-001` protected staging two-user lifecycle;
- `DB-003` off-host backup/restore rehearsal;
- `OPS-002` tag/publication proof;
- `OPS-003` production observability/on-call;
- `OPS-006` clean rebuilt-image scan/SBOM evidence;
- clean reviewed revision, protected CI, signed immutable images si explicit
  rollout authorization.

### P8 local implementation result — 2026-08-01

Arhitectura locala P0-P8 este implementata si verificata. Ultimul blocker de
review a fost limita tranzactionala soccerdata: replay miss inchide numai
tranzactia read-only pornita de propriul `SELECT`; o tranzactie deja detinuta de
caller esueaza inchis inainte de bridge, fara commit/rollback implicit, iar
fluxul compus foloseste fetch separat urmat de persistenta. Schedulerul confirma
fiecare pagina inainte de urmatorul cursor.

Replay-ul schedulerului foloseste o sesiune PostgreSQL dedicata si short-lived,
astfel incat rollback-ul probei nu expira identitatile ORM `run`/`job` ale
workerului. O regresie reala `execute_scheduled_job_run` acopera miss initial si
continuation si detecteaza revenirea `MissingGreenlet`.

Gate local final: 71 teste focalizate, backend PostgreSQL 938 passed/1 skipped,
Ruff/format, Alembic 043 head/check, 35 contracte root, frontend check 0/0,
125 unit si build. Baseline-ul browser imediat anterior ramane 60/60 hybrid si
3/3 PWA. Cleanup-ul obligatoriu a fost no-op justificat, iar review-urile
independente sunt pastrate in quality gate-ul G009.

Aceasta inchidere locala nu bifeaza gate-urile externe de mai sus. In special,
`PDP-603` si `PDP-605`, live-authorized E2E/canary/promotion, drepturile si
credentialele providerilor, staging/backup/observability/SBOM/publication si
autorizarea explicita de rollout raman HOLD.

## Benchmark design

Dataset controlat:

- aceleasi 3 tari si competitii acceptate;
- acelasi sezon istoric si aceeasi fereastra upcoming;
- aceleasi meciuri si campuri comparabile;
- run cold-cache si warm-cache separat;
- minimum 3 repetari per lane pentru smoke/variance discovery, apoi sample size
  justificat statistic pentru p95/non-inferiority;
- raw artifacts pastrate cu digest, fara secrete.

Protocolul formal este pre-inregistrat inainte de colectare:

- confidence level 95%;
- success-rate non-inferiority: test one-sided, marja 1 punct procentual,
  minimum 80% power; sample size calculat din baseline-ul stratului inainte de
  canary si salvat in manifest;
- p95: metoda nearest-rank plus bootstrap 95% CI pe fiecare strat; nicio
  afirmatie p95 cand sample size-ul nu sustine estimarea;
- straturi: adapter/source, transport, competitie, cache mode, market count si
  volum;
- coverage/parity gate ruleaza inaintea performantelor;
- excluderi permise numai pentru motive predefinite (`harness_failure`,
  `unauthorized_egress`, `invalid_fixture`) si sunt raportate, nu sterse;
- niciun threshold, strat sau outlier rule nu se schimba dupa observarea
  rezultatelor fara un nou benchmark run ID.

Artifact root propus, ignorat de Git:
`.provider-benchmark-artifacts/<run-id>/`. `manifest.json` contine commit SHA,
dirty fingerprint, versiuni, adapter/source, dataset digest, cache mode, seed,
start/end, sample-size calculation, request/success/error counts, raw latency
samples, CPU/peak RSS, cache/fallback metrics, coverage/parity, exclusions si
digests ale fisierelor. Secretele si URL-urile private sunt interzise.

Comparatii:

1. `soccerdata` MatchHistory/ESPN vs lane browser pentru fixtures/results;
2. `soccerdata` FBref/Understat vs orice overlap existent;
3. `penaltyblog` model throughput dupa cache stabil;
4. API odds vs OddsHarvester direct/XHR/browser;
5. pipeline end-to-end pana la dataset/prediction, nu numai fetch.

Failure injection obligatoriu: timeout, 403/429, soft-block HTTP 200, payload
malformat/schema drift, paginare duplicata sau trunchiata, proxy mort, cache
corupt si process kill. Niciun astfel de caz nu poate produce un dataset marcat
complet sau o predictie eligibila pentru tickets.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| upstream drift/anti-bot | API-first, fixture replay, fallback bounded, circuit breaker |
| cache stale | TTL per operation, freshness attestation, current-season refresh |
| identity collision | provider-scoped IDs, manual review for ambiguous mapping |
| leakage/secrets | env/secret manager, redaction, no auth state in artifacts |
| duplicate work | idempotency key, durable checkpoints, unique constraints |
| false performance claim | controlled cold/warm benchmark and raw evidence |
| premature microservices | modular monolith until measured isolation need |
| docs/memory drift | one checkpoint update at every phase gate |
| dirty checkout conflict | explicit file ownership, no resets, worktrees for risky lanes |

## First implementation slice

Primul slice exact este `PDP-100 + PDP-100A + PDP-101 + PDP-102`, limitat la:

- caller: `backend/app/diagnostics/provider_canary.py::verify_provider_runtime`;
- operation: `goal_expectancy`;
- identity: `(adapter_key="penaltyblog", source_key="local-model")`;
- capability: `predictions`;
- execution context: `canary`, cu politica locala `allowed`, fara bypass;
- unchanged behavior: payload-ul trimis la `run_penaltyblog` si verificarea
  `prediction["operation"] == "goal_expectancy"` raman identice;
- files: `backend/app/providers/*`, provider canary si testele dedicate;
- exclusions: nicio schimbare a bridge payload-ului, subprocess-ului,
  migrarilor, rutelor API sau proiectului nested.

Regresiile demonstreaza ca policy/capability este evaluata inainte de apel,
unknown source/capability esueaza, iar output-ul canary-ului ramane identic.
Envelope v2 (`PDP-106/107`) poate continua ca urmatorul slice P1, dar P2 nu
incepe pana cand gate-ul complet P1 este trecut.

Stop conditions:

- operation-to-capability mapping is ambiguous;
- policy context would require a hidden bypass;
- existing external behavior changes;
- nested project or migration changes become necessary.

In any stop condition, return to ADR/design review instead of expanding scope.

## Agent staffing

- `explore`/Bet explorer: file and symbol mapping, read-only;
- `architect`: identity/schema/orchestration boundaries;
- `bet-scrape-reviewer`: upstream brittleness, performance and rights risks;
- `bet-backend-executor`: scoped provider/backend implementation;
- `test-engineer`: contract, replay, migration and failure coverage;
- `bet-qa-verifier`/`verifier`: final evidence and claim validation;
- `code-reviewer`: independent review after implementation.

Parallel work is allowed only for non-overlapping ownership. Migration/schema,
provider caller and shared status files retain a single writer.

## Durable handoff

At each gate:

1. update this plan and `docs/status/current-platform-status.md`;
2. record material decisions as ADR, not duplicated prose;
3. update Serena memory with stable checkpoint/pointers;
4. request a Codex Memory extension note containing only stable facts;
5. reindex Codebase Memory only after structural code changes;
6. record exact Git dirty state, checks, blockers and one next action.
