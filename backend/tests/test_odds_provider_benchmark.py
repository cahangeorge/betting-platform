import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_odds_provider_contracts.py"


def _benchmark_module():
    spec = importlib.util.spec_from_file_location("odds_provider_benchmark_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_offline_provider_benchmark_is_honest_and_deterministically_equivalent():
    report = _benchmark_module().run_benchmark(iterations=100)

    assert report["network_requests"] == report["browser_requests"] == 0
    assert report["live_provider_evidence"] is report["promotion_proof"] is False
    assert report["parity"]["point_estimate"] == 1.0
    assert report["parity"]["formal_gate_passed"] is False
    assert report["parity"]["max_absolute_price_difference"] == "0.0"
    assert all(stage["smoke_ready"] for stage in report["canary_contract"].values())
    assert report["formal_success_required_per_arm_at_99_percent_baseline"] > 100
