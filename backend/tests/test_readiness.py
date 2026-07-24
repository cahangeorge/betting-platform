import json

import pytest
from sqlalchemy.exc import OperationalError

from app import main


class _Connection:
    def __init__(self, error_at: int | None = None, error: Exception | None = None):
        self.statements: list[str] = []
        self.error_at = error_at
        self.error = error

    async def execute(self, statement):
        self.statements.append(str(statement))
        if self.error_at == len(self.statements) and self.error is not None:
            raise self.error


class _ConnectionContext:
    def __init__(self, connection: _Connection | None = None, error: Exception | None = None):
        self.connection = connection
        self.error = error

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self.connection

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


class _Engine:
    def __init__(self, context: _ConnectionContext):
        self.context = context

    def connect(self):
        return self.context


@pytest.mark.asyncio
async def test_readiness_returns_ready_after_database_probe(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(main, "engine", _Engine(_ConnectionContext(connection=connection)))

    response = await main.readiness()

    assert response == {"status": "ready", "database": "ready", "schema": "ready"}
    assert connection.statements[0] == "SELECT 1"
    assert "SELECT users.id" in connection.statements[1]
    assert "FROM users" in connection.statements[1]


@pytest.mark.asyncio
async def test_readiness_returns_503_when_essential_schema_is_unavailable(monkeypatch):
    schema_error = OperationalError("SELECT users.id", {}, OSError("missing table"))
    connection = _Connection(error_at=2, error=schema_error)
    monkeypatch.setattr(main, "engine", _Engine(_ConnectionContext(connection=connection)))

    response = await main.readiness()

    assert response.status_code == 503
    assert json.loads(response.body) == {"status": "unavailable", "database": "ready", "schema": "unavailable"}
    assert connection.statements[0] == "SELECT 1"
    assert "FROM users" in connection.statements[1]


@pytest.mark.asyncio
async def test_readiness_returns_non_secret_503_when_database_is_unavailable(monkeypatch):
    database_error = OperationalError("postgresql://secret-user:secret-password@db", {}, OSError("refused"))
    monkeypatch.setattr(main, "engine", _Engine(_ConnectionContext(error=database_error)))

    response = await main.readiness()

    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload == {"status": "unavailable", "database": "unavailable"}
    assert "secret-user" not in response.body.decode()
    assert "secret-password" not in response.body.decode()


@pytest.mark.asyncio
async def test_taskiq_readiness_requires_fresh_worker_and_scheduler_heartbeats(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(main, "engine", _Engine(_ConnectionContext(connection=connection)))
    monkeypatch.setattr(main.settings, "task_queue_backend", "taskiq")
    from app.tasks import runtime

    async def ready_queue(*_args):
        return None

    checked_roles: list[str] = []

    async def ready_role(role):
        checked_roles.append(role)

    monkeypatch.setattr(runtime, "task_queue_probe", ready_queue)
    monkeypatch.setattr(runtime, "verify_any_runtime_role", ready_role)

    response = await main.readiness()

    assert response["task_runtime"] == "ready"
    assert checked_roles == ["worker", "scheduler"]


def test_readiness_is_available_at_root_and_api_alias():
    readiness_paths = {route.path for route in main.app.routes if getattr(route, "endpoint", None) is main.readiness}

    assert readiness_paths == {"/ready", "/api/v1/ready"}
