"""Static contracts for the isolated durable penaltyblog model runtime."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _service_block(compose: str, service: str) -> str:
    match = re.search(rf"^  {re.escape(service)}:\n", compose, re.MULTILINE)
    assert match is not None, service
    start = match.start()
    next_service = re.search(r"^  [A-Za-z][A-Za-z0-9_-]*:", compose[match.end() :], re.MULTILINE)
    end = len(compose) if next_service is None else match.end() + next_service.start()
    return compose[start:end]


def test_development_compose_shares_durable_model_artifact_volume_with_api_and_model_cpu():
    for compose_path in (ROOT / "docker-compose.yml", ROOT / "docker-compose.podman.yml"):
        compose = compose_path.read_text(encoding="utf-8")
        assert "model_artifacts:" in compose
        for service in ("backend", "model-cpu-worker"):
            block = _service_block(compose, service)
            assert "BET_MODEL_ARTIFACT_ROOT: /model-artifacts" in block
            assert "model_artifacts:/model-artifacts" in block


def test_development_model_cpu_uses_image_installed_penaltyblog_and_initializes_volume_ownership():
    for compose_path in (ROOT / "docker-compose.yml", ROOT / "docker-compose.podman.yml"):
        compose = compose_path.read_text(encoding="utf-8")
        model_cpu = _service_block(compose, "model-cpu-worker")
        init = _service_block(compose, "model-artifacts-init")

        assert "context: ." in model_cpu
        assert "dockerfile: backend/Dockerfile.production" in model_cpu
        assert "BET_PENALTYBLOG_PYTHON: /usr/local/bin/python" in model_cpu
        assert "BET_PENALTYBLOG_BRIDGE: /app/backend/app/bridges/penaltyblog_bridge.py" in model_cpu
        assert "BET_PENALTYBLOG_ROOT: /app/penaltyblog" in model_cpu
        assert "/workspace/penaltyblog/.venv/bin/python" not in model_cpu
        assert "./penaltyblog:/app/penaltyblog:ro" in model_cpu
        assert "model-artifacts-init:" in model_cpu
        assert "condition: service_completed_successfully" in model_cpu

        assert 'user: "0:0"' in init
        assert "model_artifacts:/model-artifacts" in init
        assert "chown -R 1001:1001 /model-artifacts" in init


def test_production_model_cpu_uses_durable_artifact_volume_not_tmpfs_only():
    compose = (ROOT / "deploy" / "production" / "compose.yml").read_text(encoding="utf-8")
    assert "BET_MODEL_ARTIFACT_ROOT: /model-artifacts" in compose
    assert "model-artifacts:" in compose
    assert "volumes: [model-artifacts:/model-artifacts:ro]" in _service_block(compose, "api")
    assert "volumes: [model-artifacts:/model-artifacts]" in _service_block(compose, "model-cpu-worker")

    init = _service_block(compose, "model-artifacts-init")
    assert 'user: "0:0"' in init
    assert "volumes: [model-artifacts:/model-artifacts]" in init
    assert "chown -R 1001:1001 /model-artifacts" in init
    for service in ("api", "model-cpu-worker"):
        assert "model-artifacts-init: {condition: service_completed_successfully}" in _service_block(compose, service)


def test_production_image_prepares_the_unmounted_artifact_root_for_appuser():
    dockerfile = (ROOT / "backend" / "Dockerfile.production").read_text(encoding="utf-8")
    assert 'mkdir -p "$HOME" /model-artifacts' in dockerfile
    assert 'chown -R appuser:appuser /app "$PLAYWRIGHT_BROWSERS_PATH" "$HOME" /model-artifacts' in dockerfile
