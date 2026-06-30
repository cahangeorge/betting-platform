import pytest

from app.services import python_bridge


class _FakeProc:
    def __init__(self, stdout: bytes = b"[]", stderr: bytes = b"") -> None:
        self.returncode = 0
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self) -> None:
        return None


@pytest.mark.asyncio
async def test_run_oddsharvester_uses_dedicated_timeout(monkeypatch):
    fake_proc = _FakeProc()
    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return fake_proc

    async def fake_wait_for(awaitable, timeout):
        captured["timeout"] = timeout
        return await awaitable

    monkeypatch.setattr(python_bridge.settings, "oddsharvester_python", "/tmp/fake-oddsharvester-python")
    monkeypatch.setattr(python_bridge.Path, "exists", lambda self: True)
    monkeypatch.setattr(python_bridge.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(python_bridge.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(python_bridge, "ODDSHARVESTER_TIMEOUT", 321)

    result = await python_bridge.run_oddsharvester(["upcoming", "--sport", "football"])

    assert result == "[]"
    assert captured["timeout"] == 321
    assert captured["cmd"] == (
        "/tmp/fake-oddsharvester-python",
        "-m",
        "oddsharvester",
        "upcoming",
        "--sport",
        "football",
    )


@pytest.mark.asyncio
async def test_run_oddsharvester_allows_per_call_timeout(monkeypatch):
    fake_proc = _FakeProc()
    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        return fake_proc

    async def fake_wait_for(awaitable, timeout):
        captured["timeout"] = timeout
        return await awaitable

    monkeypatch.setattr(python_bridge.settings, "oddsharvester_python", "/tmp/fake-oddsharvester-python")
    monkeypatch.setattr(python_bridge.Path, "exists", lambda self: True)
    monkeypatch.setattr(python_bridge.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(python_bridge.asyncio, "wait_for", fake_wait_for)

    result = await python_bridge.run_oddsharvester(["historic", "--sport", "football"], timeout=2400)

    assert result == "[]"
    assert captured["timeout"] == 2400
