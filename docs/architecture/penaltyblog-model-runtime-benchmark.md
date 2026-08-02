# Penaltyblog model-runtime benchmark contract

`backend/scripts/benchmark_penaltyblog_model_runtime.py` is the bounded, offline
G005 evidence harness. Its default deterministic mode is the stable CI contract.
Its explicit host mode invokes the real pinned penaltyblog bridge and compares
the old **per-target refit** shape against **one serialized-model load plus batch
prediction**. Neither mode makes network or provider calls.

Run it from `backend/`:

```bash
python scripts/benchmark_penaltyblog_model_runtime.py --target-count 100 --repetitions 5
```

Run measured host evidence with the isolated penaltyblog interpreter:

```bash
../penaltyblog/.venv/bin/python scripts/benchmark_penaltyblog_model_runtime.py \
  --host-python ../penaltyblog/.venv/bin/python \
  --penaltyblog-root ../penaltyblog \
  --target-count 4 --row-count 80
```

The JSON report records phase costs, exact output digest parity, runtime and
artifact fingerprints, and the resident-worker decision. The deterministic
cost clock is an anti-flake CI contract, not a production latency statement.
Only host mode is accepted as measured penaltyblog throughput evidence.

## Resident-worker promotion gate

The default is **disabled**. A future long-lived worker is only eligible for a
separate approval when all of these hold:

1. output parity is exact;
2. it is process-isolated from the API/default worker lanes;
3. its RSS bound is measured and passes;
4. it improves p50 by at least 40%, **or** seconds/result by at least 30%.

The one-load batch subprocess is the adopted G005 implementation. This harness
does not turn on a resident process, communicate with a live provider, or
authorize a ticket/prediction workflow.

## Local host smoke — 2026-08-01

The checked-in harness was executed offline using the pinned penaltyblog revision
`dd81473a40f29ddcf62a85c006cd28e6d83acd80`, 80 generated training rows and
four targets compared four `model_fit_predict` subprocesses with one
`model_train` plus one `model_predict_batch` subprocess:

- baseline refit total: `3.9994s`;
- serialized train: `1.0772s`;
- verified single-load batch predict: `1.0114s`;
- predict-path reduction versus four refits: `74.7%`;
- exact 1X2 output parity: passed;
- network calls: `0`;
- resident worker: disabled.

This is host smoke evidence, not a statistically powered production p95 claim.
It is sufficient to retain the isolated serialized-load subprocess design and
reject per-target refitting; it does not authorize a resident/preloaded worker.
