# Soccerdata to Penaltyblog Pipeline

This runbook covers the governed non-odds path used before the final odds
acquisition stage:

```text
soccerdata acquisition
  -> provider observations and canonical dataset pages
  -> published ProviderDatasetGeneration
  -> penaltyblog feature artifact
  -> trained model artifact
  -> backtest
```

It does not authorize provider traffic, credentials, production rollout, or
public release. Use only a source and execution context already approved by the
provider registry and operations owner.

For Understat, the backend adapter owns two compatibility guarantees which
must remain covered by regression tests: naive upstream fixture datetimes are
serialized as explicit UTC, and the reader's direct JSON API path is included
in cache, TTL, quota, and upstream-request telemetry. A valid warm direct-API
cache must perform neither cookie initialization nor upstream I/O; a stale
entry must be forced through the refresh path.

## 1. Select the soccerdata operation

The supported non-odds operations are versioned in
`backend/app/providers/soccerdata.py`:

- historical results: `matchhistory_results_backfill`;
- incremental fixtures: `espn_schedule_incremental`;
- Understat fixtures/statistics: `understat_schedule_backfill` and
  `understat_team_stats_backfill`;
- FBref fixtures/statistics: `fbref_schedule_backfill` and
  `fbref_team_stats_backfill`.

Create the scheduled job with task type `soccerdata_http_ingest` or
`soccerdata_browser_ingest` exactly as derived by the selected operation. A
public job starts at page zero. The scheduler derives and persists continuation
cursors; operators must not manufacture a later page or generation key.

## 2. Require terminal generation evidence

Do not train from an individual dataset page. A usable terminal ingestion run
must have:

- run status `completed`;
- `ingestion_state=completed`;
- no `next_cursor`;
- `provider_dataset_generation_ids=[N]`;
- scalar `source_generation_id=N`.

The scalar is emitted only after terminal publication proves the complete,
continuous page membership. Partial pages expose their generation for
observability but deliberately omit `source_generation_id`. If a terminal
continuation page is empty after earlier pages contained records, the aggregate
run remains `completed` and exposes the single verified generation. A wholly
empty run is `skipped`/`no_data` and must not be trained.

## 3. Train the penaltyblog goal model

Create a `train_model` scheduled job using the exact scalar from the terminal
ingestion run:

```json
{
  "contract_version": "penaltyblog-model-pipeline/v1",
  "source_generation_id": 41,
  "model_spec": {"model_class": "PoissonGoalsModel"},
  "model_version": "goals-v1",
  "training_cutoff_at": "2026-01-01T00:00:00Z"
}
```

The accepted model classes and strict command fields are defined in
`backend/app/schemas/model_pipeline.py`. A successful run emits
`model_artifact_ids` and retains the exact source generation, feature, runtime,
configuration, and training-data fingerprints.

## 4. Backtest before prediction

Run `backtest_model` with the exact `model_artifact_id`, the same pinned
`source_generation_id`, chronological cutoffs, and targets inside the declared
test window. Promotion remains fail-closed if freshness, completeness,
artifact integrity, chronology, or quality gates fail.

The current `football-goals-features/v1` model uses match date, teams, and
home/away goals. Understat/FBref statistics, including xG when supplied by the
bridge, remain preserved in canonical provider observations. They are not
silently presented as active inputs to the v1 penaltyblog goal model; adding an
xG feature schema/model is a separate versioned change with its own leakage and
reproducibility gates.

## 5. Odds is the final prerequisite for forecasts

`predict_model` targets require exact `odds_snapshot_id` and `odds_entry_id`
lineage. Therefore the data extraction, canonical generation, training, and
backtest stages can be completed first, but production-shaped predictions wait
for the separately authorized odds acquisition/scraping stage. Do not invent
odds identifiers or bypass this contract.

## Verification

From `backend/`:

```bash
.venv/bin/pytest tests/test_model_pipeline_contract.py \
  tests/test_soccerdata_ingestion.py tests/test_scheduled_jobs.py \
  -k 'understat_statistics or soccerdata'
.venv/bin/pytest
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
```

Run the isolated PostgreSQL gates with `BET_TEST_POSTGRES_URL` only against a
throwaway database migrated to the current Alembic head. Provider bridge smoke
tests are a distinct authorized operation and are not implied by these offline
checks.
