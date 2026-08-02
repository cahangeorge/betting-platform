#!/usr/bin/env python3
"""Offline, deterministic evidence for the penaltyblog model-runtime rollout.

The default deterministic mode is deliberately *not* a live performance claim.
An explicit ``--host-python`` mode invokes the real pinned penaltyblog bridge
offline and measures the two execution shapes:

* baseline: refit once for every target;
* candidate: deserialize once, then predict the complete target batch.

The resulting JSON is safe for CI and records output parity, phase accounting,
and the guard used before a future resident model worker can be enabled.  A
real host benchmark may replace the deterministic clock, but must retain the
same report schema and promotion guard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

BENCHMARK_CONTRACT_VERSION = "penaltyblog-model-runtime-benchmark/v1"
P50_IMPROVEMENT_THRESHOLD = 0.40
SECONDS_PER_RESULT_IMPROVEMENT_THRESHOLD = 0.30


@dataclass(frozen=True)
class Measurement:
    """One deterministic strategy execution used in a benchmark report."""

    strategy: str
    target_count: int
    elapsed_seconds: float
    phase_seconds: dict[str, float]
    output_digest: str


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class _GoldenModel:
    """Model whose output depends only on a target, not process timing."""

    def predict(self, target: dict[str, str]) -> dict[str, float | str]:
        seed = int(_digest(target)[:8], 16)
        home = 0.35 + (seed % 30) / 100
        draw = 0.20 + ((seed // 31) % 10) / 100
        away = round(1.0 - home - draw, 6)
        return {
            "away_team": target["away_team"],
            "away_win": away,
            "draw": round(draw, 6),
            "home_team": target["home_team"],
            "home_win": round(home, 6),
        }


def _golden_targets(target_count: int) -> list[dict[str, str]]:
    if target_count < 1:
        raise ValueError("target_count must be positive")
    return [
        {"home_team": f"Home {index:03d}", "away_team": f"Away {index:03d}"} for index in range(1, target_count + 1)
    ]


def _baseline_per_target_refit(targets: Iterable[dict[str, str]]) -> Measurement:
    targets = list(targets)
    outputs: list[dict[str, float | str]] = []
    phases = {"deserialize": 0.0, "fit": 0.0, "predict": 0.0}
    for target in targets:
        # Fixed logical costs make CI evidence stable and prevent timing flakes.
        phases["deserialize"] += 0.002
        phases["fit"] += 0.005
        phases["predict"] += 0.001
        outputs.append(_GoldenModel().predict(target))
    return Measurement(
        strategy="per_target_refit",
        target_count=len(targets),
        elapsed_seconds=round(sum(phases.values()), 9),
        phase_seconds=phases,
        output_digest=_digest(outputs),
    )


def _single_load_batch_predict(targets: Iterable[dict[str, str]]) -> Measurement:
    targets = list(targets)
    # One serialized-artifact load is followed by one batched prediction call.
    phases = {"deserialize": 0.002, "fit": 0.0, "predict_batch": 0.0005 * len(targets)}
    model = _GoldenModel()
    outputs = [model.predict(target) for target in targets]
    return Measurement(
        strategy="single_load_batch_predict",
        target_count=len(targets),
        elapsed_seconds=round(sum(phases.values()), 9),
        phase_seconds=phases,
        output_digest=_digest(outputs),
    )


def _percent_improvement(baseline: float, candidate: float) -> float:
    if baseline <= 0:
        raise ValueError("baseline measurement must be positive")
    return round((baseline - candidate) / baseline, 9)


def _p50(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        raise ValueError("cannot calculate p50 for no measurements")
    return float(median(values))


def resident_worker_decision(
    *,
    output_parity: bool,
    baseline_p50_seconds: float,
    batch_p50_seconds: float,
    baseline_seconds_per_result: float,
    batch_seconds_per_result: float,
    isolation_gate_passed: bool,
    rss_gate_passed: bool,
) -> dict[str, Any]:
    """Apply the pre-registered resident-worker promotion rule.

    A resident worker is never promoted merely for being faster: exact output
    parity, process isolation, and a bounded RSS measurement are all required.
    """

    p50_improvement = _percent_improvement(baseline_p50_seconds, batch_p50_seconds)
    seconds_per_result_improvement = _percent_improvement(baseline_seconds_per_result, batch_seconds_per_result)
    throughput_gate_passed = (
        p50_improvement >= P50_IMPROVEMENT_THRESHOLD
        or seconds_per_result_improvement >= SECONDS_PER_RESULT_IMPROVEMENT_THRESHOLD
    )
    eligible = output_parity and isolation_gate_passed and rss_gate_passed and throughput_gate_passed
    return {
        "p50_improvement": p50_improvement,
        "seconds_per_result_improvement": seconds_per_result_improvement,
        "thresholds": {
            "p50": P50_IMPROVEMENT_THRESHOLD,
            "seconds_per_result": SECONDS_PER_RESULT_IMPROVEMENT_THRESHOLD,
        },
        "output_parity": output_parity,
        "isolation_gate_passed": isolation_gate_passed,
        "rss_gate_passed": rss_gate_passed,
        "throughput_gate_passed": throughput_gate_passed,
        "resident_worker_candidate_eligible": eligible,
        "resident_worker_status": "eligible_for_separate_approval" if eligible else "disabled",
    }


def run_deterministic_benchmark(
    *, target_count: int = 100, repetitions: int = 5, isolation_gate_passed: bool = False, rss_gate_passed: bool = False
) -> dict[str, Any]:
    """Return reproducible benchmark evidence without importing penaltyblog."""

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    targets = _golden_targets(target_count)
    baseline = [_baseline_per_target_refit(targets) for _ in range(repetitions)]
    batch = [_single_load_batch_predict(targets) for _ in range(repetitions)]
    output_parity = {item.output_digest for item in baseline} == {item.output_digest for item in batch}
    baseline_p50 = _p50(item.elapsed_seconds for item in baseline)
    batch_p50 = _p50(item.elapsed_seconds for item in batch)
    decision = resident_worker_decision(
        output_parity=output_parity,
        baseline_p50_seconds=baseline_p50,
        batch_p50_seconds=batch_p50,
        baseline_seconds_per_result=baseline_p50 / target_count,
        batch_seconds_per_result=batch_p50 / target_count,
        isolation_gate_passed=isolation_gate_passed,
        rss_gate_passed=rss_gate_passed,
    )
    return {
        "contract_version": BENCHMARK_CONTRACT_VERSION,
        "mode": "offline_deterministic_golden_runtime",
        "network_calls": 0,
        "target_count": target_count,
        "repetitions": repetitions,
        "measurements": {
            "per_target_refit": [asdict(item) for item in baseline],
            "single_load_batch_predict": [asdict(item) for item in batch],
        },
        "p50_seconds": {"per_target_refit": baseline_p50, "single_load_batch_predict": batch_p50},
        "output_parity": output_parity,
        "resident_worker_decision": decision,
    }


def _invoke_bridge(
    python: Path,
    bridge: Path,
    request: dict[str, Any],
    *,
    penaltyblog_root: Path,
    artifact_root: Path,
) -> tuple[dict[str, Any], float]:
    """Invoke the production bridge contract and return its result and wall time."""

    with tempfile.TemporaryDirectory(prefix="bet-model-benchmark-") as directory:
        work = Path(directory)
        payload_path = work / "request.json"
        output_path = work / "response.json"
        payload_path.write_text(_canonical_json(request), encoding="utf-8")
        environment = os.environ.copy()
        environment.update(
            {
                "BET_PENALTYBLOG_ROOT": str(penaltyblog_root.resolve()),
                "BET_MODEL_ARTIFACT_ROOT": str(artifact_root.resolve()),
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            }
        )
        started = time.perf_counter()
        subprocess.run(
            [str(python), str(bridge), "--payload-file", str(payload_path), "--output", str(output_path)],
            check=True,
            env=environment,
            capture_output=True,
            text=True,
        )
        elapsed = time.perf_counter() - started
        response = json.loads(output_path.read_text(encoding="utf-8"))
    if response.get("ok") is not True:
        raise RuntimeError(response.get("error", "penaltyblog bridge failed"))
    return response["result"]["result"], elapsed


def _host_rows(row_count: int) -> list[dict[str, Any]]:
    if row_count < 8:
        raise ValueError("row_count must be at least 8")
    teams = ("Alpha", "Bravo", "Charlie", "Delta")
    rows = []
    for index in range(row_count):
        home = teams[index % len(teams)]
        away = teams[(index + 1 + (index // len(teams))) % len(teams)]
        if home == away:
            away = teams[(teams.index(away) + 1) % len(teams)]
        rows.append(
            {
                "source_id": f"benchmark-{index:04d}",
                "observed_at": f"2025-{1 + (index // 28):02d}-{1 + (index % 28):02d}T14:00:00Z",
                "date": f"2025-{1 + (index // 28):02d}-{1 + (index % 28):02d}T12:00:00+00:00",
                "team_home": home,
                "team_away": away,
                "goals_home": index % 4,
                "goals_away": (index * 3) % 3,
            }
        )
    return rows


def _training_wire_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected = [
        {
            "date": str(row["date"]).replace("+00:00", "Z"),
            "team_home": str(row["team_home"]),
            "team_away": str(row["team_away"]),
            "goals_home": int(row["goals_home"]),
            "goals_away": int(row["goals_away"]),
            "_source_id": str(row["source_id"]),
            "_observed_at": str(row["observed_at"]).replace("+00:00", "Z"),
        }
        for row in rows
    ]
    projected.sort(key=lambda row: (row["date"], row["_source_id"], row["_observed_at"]))
    for row in projected:
        row.pop("_source_id")
        row.pop("_observed_at")
    return projected


def run_host_benchmark(
    *,
    python: Path,
    penaltyblog_root: Path,
    bridge: Path,
    row_count: int = 80,
    target_count: int = 4,
) -> dict[str, Any]:
    """Measure the real offline subprocess contract; never performs network I/O."""

    targets = _golden_targets(target_count)
    # Use teams present in the fitted model rather than the golden labels.
    teams = ("Alpha", "Bravo", "Charlie", "Delta")
    targets = [{"home_team": teams[index % 4], "away_team": teams[(index + 1) % 4]} for index in range(target_count)]
    rows = _host_rows(row_count)
    legacy_payload = {
        "model": "PoissonGoalsModel",
        "goals_home": [row["goals_home"] for row in rows],
        "goals_away": [row["goals_away"] for row in rows],
        "teams_home": [row["team_home"] for row in rows],
        "teams_away": [row["team_away"] for row in rows],
    }
    artifact_root = Path(tempfile.mkdtemp(prefix="bet-model-artifacts-"))
    try:
        runtime, _ = _invoke_bridge(
            python,
            bridge,
            {"operation": "runtime_info", "payload": {}},
            penaltyblog_root=penaltyblog_root,
            artifact_root=artifact_root,
        )
        baseline_outputs = []
        baseline_seconds = 0.0
        for target in targets:
            result, elapsed = _invoke_bridge(
                python,
                bridge,
                {"operation": "model_fit_predict", "payload": {**legacy_payload, "prediction": target}},
                penaltyblog_root=penaltyblog_root,
                artifact_root=artifact_root,
            )
            baseline_seconds += elapsed
            prediction = result["prediction"]
            baseline_outputs.append({key: prediction[key] for key in ("homeWin", "draw", "awayWin")})
        trained, train_seconds = _invoke_bridge(
            python,
            bridge,
            {
                "operation": "model_train",
                "payload": {
                    "artifact_path": "benchmark/model.pkl",
                    "matches": rows,
                    "model_config": {"model_class": "PoissonGoalsModel"},
                    "expected_model_config_digest": _digest(
                        {
                            "model_class": "PoissonGoalsModel",
                            "model_kwargs": {},
                            "fit_kwargs": {},
                            "use_time_decay": False,
                            "xi": None,
                            "base_date": None,
                        }
                    ),
                    "expected_training_data_digest": _digest(_training_wire_rows(rows)),
                },
            },
            penaltyblog_root=penaltyblog_root,
            artifact_root=artifact_root,
        )
        predicted, batch_seconds = _invoke_bridge(
            python,
            bridge,
            {
                "operation": "model_predict_batch",
                "payload": {
                    "artifact_path": "benchmark/model.pkl",
                    "expected_artifact_digest": trained["artifact_digest"],
                    "expected_runtime_fingerprint": runtime["runtime_fingerprint"],
                    "targets": targets,
                },
            },
            penaltyblog_root=penaltyblog_root,
            artifact_root=artifact_root,
        )
        batch_outputs = [
            {key: prediction[key] for key in ("homeWin", "draw", "awayWin")} for prediction in predicted["predictions"]
        ]
        parity = _canonical_json(baseline_outputs) == _canonical_json(batch_outputs)
        decision = resident_worker_decision(
            output_parity=parity,
            baseline_p50_seconds=baseline_seconds,
            batch_p50_seconds=batch_seconds,
            baseline_seconds_per_result=baseline_seconds / target_count,
            batch_seconds_per_result=batch_seconds / target_count,
            isolation_gate_passed=False,
            rss_gate_passed=False,
        )
        return {
            "contract_version": BENCHMARK_CONTRACT_VERSION,
            "mode": "offline_real_penaltyblog_subprocess",
            "network_calls": 0,
            "row_count": row_count,
            "target_count": target_count,
            "runtime_fingerprint": runtime["runtime_fingerprint"],
            "artifact_digest": trained["artifact_digest"],
            "elapsed_seconds": {
                "per_target_refit_total": baseline_seconds,
                "serialized_train": train_seconds,
                "single_load_batch_predict": batch_seconds,
            },
            "output_parity": parity,
            "output_digest": _digest(batch_outputs),
            "resident_worker_decision": decision,
        }
    finally:
        import shutil

        shutil.rmtree(artifact_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-count", type=int, default=100)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--isolation-gate-passed", action="store_true")
    parser.add_argument("--rss-gate-passed", action="store_true")
    parser.add_argument("--host-python", type=Path)
    parser.add_argument("--penaltyblog-root", type=Path, default=Path("../penaltyblog"))
    parser.add_argument("--bridge", type=Path, default=Path("app/bridges/penaltyblog_bridge.py"))
    parser.add_argument("--row-count", type=int, default=80)
    args = parser.parse_args()
    if args.host_python:
        report = run_host_benchmark(
            python=args.host_python,
            penaltyblog_root=args.penaltyblog_root,
            bridge=args.bridge,
            row_count=args.row_count,
            target_count=args.target_count,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(
        json.dumps(
            run_deterministic_benchmark(
                target_count=args.target_count,
                repetitions=args.repetitions,
                isolation_gate_passed=args.isolation_gate_passed,
                rss_gate_passed=args.rss_gate_passed,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
