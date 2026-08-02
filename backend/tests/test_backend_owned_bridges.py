import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.services import python_bridge

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_ROOT = BACKEND_ROOT / "app" / "bridges"


def _run_bridge(script: Path, payload: dict, output: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), "--payload", json.dumps(payload), "--output", str(output)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )


def test_bridge_defaults_are_backend_owned_and_dependency_roots_are_explicit():
    settings = Settings(_env_file=None)

    assert settings.resolved_penaltyblog_bridge == str(BRIDGE_ROOT / "penaltyblog_bridge.py")
    assert settings.resolved_soccerdata_bridge == str(BRIDGE_ROOT / "soccerdata_bridge.py")
    assert settings.resolved_penaltyblog_root == str(BACKEND_ROOT.parent / "penaltyblog")
    assert settings.resolved_soccerdata_root == str(BACKEND_ROOT.parent / "soccerdata")
    assert "betfront" not in settings.resolved_penaltyblog_bridge
    assert "betfront" not in settings.resolved_soccerdata_bridge


def test_provider_validation_is_scoped(tmp_path):
    existing = tmp_path / "runtime"
    existing.mkdir()
    settings = Settings(
        _env_file=None,
        penaltyblog_python=str(tmp_path / "missing-penalty-python"),
        penaltyblog_bridge=str(tmp_path / "missing-penalty-bridge"),
        penaltyblog_root=str(tmp_path / "missing-penalty-root"),
        soccerdata_python=str(tmp_path / "missing-soccer-python"),
        soccerdata_bridge=str(tmp_path / "missing-soccer-bridge"),
        soccerdata_root=str(tmp_path / "missing-soccer-root"),
        oddsharvester_python=str(existing),
    )

    assert settings.provider_validation_issues("oddsharvester") == []
    assert len(settings.provider_validation_issues("penaltyblog")) == 3
    assert len(settings.provider_validation_issues("soccerdata")) == 3


def test_soccerdata_bridge_preserves_output_protocol_on_failure(tmp_path):
    output = tmp_path / "soccerdata-output.json"
    result = _run_bridge(
        BRIDGE_ROOT / "soccerdata_bridge.py",
        {"operation": "deterministic_unknown_operation"},
        output,
        {"BET_SOCCERDATA_ROOT": str(tmp_path)},
    )

    response = json.loads(output.read_text())
    assert result.returncode != 0
    assert response["ok"] is False
    assert response["error"] == "Unsupported operation: deterministic_unknown_operation"
    assert "traceback" in response


def test_penaltyblog_catalog_preserves_legacy_envelope(tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "numpy.py").write_text("class generic: pass\nclass ndarray: pass\n", encoding="utf-8")
    (stubs / "pandas.py").write_text("class DataFrame: pass\nclass Series: pass\n", encoding="utf-8")
    output = tmp_path / "penaltyblog-output.json"

    result = _run_bridge(
        BRIDGE_ROOT / "penaltyblog_bridge.py",
        {"operation": "catalog", "payload": {}},
        output,
        {
            "BET_PENALTYBLOG_ROOT": str(tmp_path),
            "PYTHONPATH": str(stubs),
        },
    )

    response = json.loads(output.read_text())
    assert result.returncode == 0, result.stderr
    assert response["ok"] is True
    assert response["result"]["operation"] == "catalog"
    groups = response["result"]["result"]["groups"]
    assert {group["id"] for group in groups} >= {"models", "betting", "ratings"}


@pytest.mark.asyncio
async def test_penaltyblog_wrapper_checks_only_its_provider_at_use_site(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(python_bridge.settings, "penaltyblog_python", str(runtime))
    monkeypatch.setattr(python_bridge.settings, "penaltyblog_bridge", str(runtime))
    monkeypatch.setattr(python_bridge.settings, "penaltyblog_root", str(tmp_path))
    monkeypatch.setattr(python_bridge.settings, "soccerdata_python", str(tmp_path / "missing"))
    captured: dict[str, object] = {}

    async def fake_run_bridge(payload, python_bin, bridge_script, **kwargs):
        captured.update(payload=payload, python_bin=python_bin, bridge_script=bridge_script, kwargs=kwargs)
        return {"operation": "catalog", "result": {}}

    monkeypatch.setattr(python_bridge, "run_bridge", fake_run_bridge)

    response = await python_bridge.run_penaltyblog({"operation": "catalog", "payload": {}})

    assert response["operation"] == "catalog"
    assert captured["kwargs"]["extra_env"] == {
        "BET_PENALTYBLOG_ROOT": str(tmp_path),
        "BET_MODEL_ARTIFACT_ROOT": python_bridge.settings.resolved_model_artifact_root,
    }
    assert captured["kwargs"]["payload_file"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("model_train", "model_backtest_fold"))
async def test_penaltyblog_model_payload_file_serializes_canonical_datetime_rows(monkeypatch, tmp_path, operation):
    """Model train/backtest payloads must cross the subprocess JSON boundary."""
    bridge = tmp_path / "bridge.py"
    bridge.write_text(
        "import argparse, json\n"
        "parser = argparse.ArgumentParser(); parser.add_argument('--payload-file'); parser.add_argument('--output')\n"
        "args = parser.parse_args()\n"
        "with open(args.payload_file, encoding='utf-8') as source: payload = json.load(source)\n"
        "with open(args.output, 'w', encoding='utf-8') as target: json.dump({'ok': True, 'result': payload}, target)\n",
        encoding="utf-8",
    )
    root = tmp_path / "penaltyblog"
    root.mkdir()
    monkeypatch.setattr(python_bridge.settings, "penaltyblog_python", sys.executable)
    monkeypatch.setattr(python_bridge.settings, "penaltyblog_bridge", str(bridge))
    monkeypatch.setattr(python_bridge.settings, "penaltyblog_root", str(root))
    monkeypatch.setattr(python_bridge, "TEMP_DIR", tmp_path / "bridge-temp")
    python_bridge.TEMP_DIR.mkdir()

    result = await python_bridge.run_penaltyblog(
        {
            "operation": operation,
            "payload": {
                "training_matches": [
                    {"date": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC), "team_home": "A", "team_away": "B"}
                ]
            },
        }
    )

    assert result["operation"] == operation
    assert result["payload"]["training_matches"][0]["date"] == "2026-01-02T03:04:05Z"


@pytest.mark.asyncio
async def test_soccerdata_wrapper_uses_a_writable_default_cache(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(python_bridge.settings, "soccerdata_python", str(runtime))
    monkeypatch.setattr(python_bridge.settings, "soccerdata_bridge", str(runtime))
    monkeypatch.setattr(python_bridge.settings, "soccerdata_root", str(tmp_path))
    monkeypatch.setattr(python_bridge, "TEMP_DIR", tmp_path / "bridge-temp")
    monkeypatch.delenv("SOCCERDATA_DIR", raising=False)
    captured: dict[str, object] = {}

    async def fake_run_bridge(payload, python_bin, bridge_script, **kwargs):
        captured.update(payload=payload, python_bin=python_bin, bridge_script=bridge_script, kwargs=kwargs)
        return {"operation": "catalog", "result": {}}

    monkeypatch.setattr(python_bridge, "run_bridge", fake_run_bridge)

    response = await python_bridge.run_soccerdata({"operation": "catalog"})

    expected_cache = tmp_path / "bridge-temp" / "soccerdata"
    assert response["operation"] == "catalog"
    assert expected_cache.is_dir()
    assert captured["kwargs"]["extra_env"] == {
        "BET_SOCCERDATA_ROOT": str(tmp_path),
        "SOCCERDATA_DIR": str(expected_cache),
    }


def test_penaltyblog_bridge_accepts_private_payload_file_transport(tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "numpy.py").write_text("class generic: pass\nclass ndarray: pass\n", encoding="utf-8")
    (stubs / "pandas.py").write_text("class DataFrame: pass\nclass Series: pass\n", encoding="utf-8")
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps({"operation": "catalog", "payload": {}}), encoding="utf-8")
    output = tmp_path / "output.json"

    result = subprocess.run(
        [
            sys.executable,
            str(BRIDGE_ROOT / "penaltyblog_bridge.py"),
            "--payload-file",
            str(payload_file),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "BET_PENALTYBLOG_ROOT": str(tmp_path), "PYTHONPATH": str(stubs)},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())["ok"] is True
