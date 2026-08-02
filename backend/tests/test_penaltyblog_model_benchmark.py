"""Deterministic evidence contracts for the penaltyblog runtime benchmark."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_penaltyblog_model_runtime.py"


def _benchmark_module():
    spec = importlib.util.spec_from_file_location("penaltyblog_model_benchmark_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_offline_benchmark_reports_phase_accounting_and_batch_output_parity():
    benchmark = _benchmark_module()

    report = benchmark.run_deterministic_benchmark(target_count=4, repetitions=3)

    assert report["mode"] == "offline_deterministic_golden_runtime"
    assert report["network_calls"] == 0
    assert report["output_parity"] is True
    assert report["measurements"]["per_target_refit"][0]["phase_seconds"]["fit"] == pytest.approx(0.02)
    assert report["measurements"]["single_load_batch_predict"][0]["phase_seconds"]["deserialize"] == pytest.approx(
        0.002
    )
    assert report["p50_seconds"]["single_load_batch_predict"] < report["p50_seconds"]["per_target_refit"]


def test_offline_benchmark_keeps_resident_worker_disabled_without_isolation_and_rss_gates():
    benchmark = _benchmark_module()

    decision = benchmark.run_deterministic_benchmark(target_count=10)["resident_worker_decision"]

    assert decision["throughput_gate_passed"] is True
    assert decision["resident_worker_candidate_eligible"] is False
    assert decision["resident_worker_status"] == "disabled"


def test_host_benchmark_uses_real_bridge_shapes_and_requires_exact_parity(monkeypatch, tmp_path):
    benchmark = _benchmark_module()
    calls = []

    def fake_invoke(_python, _bridge, request, **_kwargs):
        calls.append(request["operation"])
        if request["operation"] == "runtime_info":
            return {"runtime_fingerprint": "f" * 64}, 0.01
        if request["operation"] == "model_fit_predict":
            return {"prediction": {"homeWin": 0.5, "draw": 0.25, "awayWin": 0.25}}, 1.0
        if request["operation"] == "model_train":
            return {"artifact_digest": "a" * 64}, 1.0
        assert request["operation"] == "model_predict_batch"
        return {
            "predictions": [
                {"homeWin": 0.5, "draw": 0.25, "awayWin": 0.25},
                {"homeWin": 0.5, "draw": 0.25, "awayWin": 0.25},
            ]
        }, 0.5

    monkeypatch.setattr(benchmark, "_invoke_bridge", fake_invoke)
    report = benchmark.run_host_benchmark(
        python=tmp_path / "python",
        penaltyblog_root=tmp_path,
        bridge=tmp_path / "bridge.py",
        row_count=8,
        target_count=2,
    )

    assert calls == ["runtime_info", "model_fit_predict", "model_fit_predict", "model_train", "model_predict_batch"]
    assert report["mode"] == "offline_real_penaltyblog_subprocess"
    assert report["output_parity"] is True
    assert report["elapsed_seconds"]["per_target_refit_total"] == pytest.approx(2.0)
    assert report["resident_worker_decision"]["resident_worker_status"] == "disabled"


def test_resident_worker_requires_parity_and_either_preregistered_throughput_threshold():
    benchmark = _benchmark_module()

    decision = benchmark.resident_worker_decision(
        output_parity=True,
        baseline_p50_seconds=10.0,
        batch_p50_seconds=6.5,
        baseline_seconds_per_result=1.0,
        batch_seconds_per_result=0.7,
        isolation_gate_passed=True,
        rss_gate_passed=True,
    )

    assert decision["p50_improvement"] == pytest.approx(0.35)
    assert decision["seconds_per_result_improvement"] == pytest.approx(0.30)
    assert decision["resident_worker_candidate_eligible"] is True
    assert decision["resident_worker_status"] == "eligible_for_separate_approval"


def test_resident_worker_rejects_candidate_when_output_parity_fails_despite_speed_and_runtime_gates():
    benchmark = _benchmark_module()

    decision = benchmark.resident_worker_decision(
        output_parity=False,
        baseline_p50_seconds=10.0,
        batch_p50_seconds=5.0,
        baseline_seconds_per_result=1.0,
        batch_seconds_per_result=0.5,
        isolation_gate_passed=True,
        rss_gate_passed=True,
    )

    assert decision["throughput_gate_passed"] is True
    assert decision["resident_worker_candidate_eligible"] is False
    assert decision["resident_worker_status"] == "disabled"


@pytest.mark.parametrize("target_count,repetitions", [(0, 1), (1, 0)])
def test_offline_benchmark_rejects_empty_workloads_and_repetition_counts(target_count, repetitions):
    benchmark = _benchmark_module()

    with pytest.raises(ValueError):
        benchmark.run_deterministic_benchmark(target_count=target_count, repetitions=repetitions)
