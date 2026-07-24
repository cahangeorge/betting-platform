import asyncio
import json
import logging
import time

import pytest
from fastapi import WebSocketDisconnect
from starlette.routing import Match

from app.api.v1 import live as live_api
from app.config import get_settings
from app.main import app
from app.services.auth import create_access_token


class _FakeWebSocket:
    def __init__(self, messages: list[str], *, token: str | None = None):
        self._messages = list(messages)
        self.headers = {"origin": get_settings().cors_origin_list[0]} if token else {}
        self.cookies = {"access_token": token} if token else {}
        self.accepted = False
        self.closed: tuple[int, str] | None = None
        self.sent: list[dict] = []

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        if not self._messages:
            raise WebSocketDisconnect()
        return self._messages.pop(0)

    async def send_text(self, payload: str):
        self.sent.append(json.loads(payload))

    async def close(self, code: int, reason: str):
        self.closed = (code, reason)


class _FakeDb:
    def __init__(self, user=None):
        self.user = user

    async def get(self, _model, object_id):
        if self.user is not None and self.user.id == object_id:
            return self.user
        return None

    async def execute(self, _statement):
        return type("Result", (), {"scalar_one_or_none": lambda _self: self.user})()


def _reset_manager():
    live_api.manager.active_connections.clear()
    live_api.manager._subscriptions.clear()
    live_api.manager._user_ids.clear()


def test_app_exposes_live_websocket_route_at_public_path():
    scope = {
        "type": "websocket",
        "path": "/api/v1/live/ws",
        "root_path": "",
        "scheme": "ws",
        "query_string": b"",
        "headers": [],
        "client": None,
        "server": None,
        "subprotocols": [],
    }
    assert any(route.matches(scope)[0] is Match.FULL for route in app.routes)

    websocket_route = next(route for route in live_api.router.routes if getattr(route, "path", None) == "/ws")
    assert websocket_route.endpoint is live_api.live_websocket


@pytest.mark.asyncio
async def test_live_websocket_requires_authentication_before_accepting():
    _reset_manager()
    websocket = _FakeWebSocket([])

    await live_api.live_websocket(websocket, db=_FakeDb())

    assert websocket.accepted is False
    assert websocket.closed == (4401, "Not authenticated")
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_live_websocket_rejects_cookie_auth_from_untrusted_origin():
    _reset_manager()
    user = type("User", (), {"id": 7})()
    websocket = _FakeWebSocket([], token=create_access_token(user.id))
    websocket.headers["origin"] = "https://attacker.example"

    await live_api.live_websocket(websocket, db=_FakeDb(user))

    assert websocket.accepted is False
    assert websocket.closed == (4401, "Not authenticated")


@pytest.mark.asyncio
async def test_live_websocket_accepts_configured_loopback_origin():
    _reset_manager()
    user = type("User", (), {"id": 7})()
    websocket = _FakeWebSocket([], token=create_access_token(user.id))
    websocket.headers["origin"] = "http://127.0.0.1:5175"

    await live_api.live_websocket(websocket, db=_FakeDb(user))

    assert websocket.accepted is True
    assert websocket.closed is None


@pytest.mark.asyncio
async def test_live_websocket_rejects_unconfigured_tunnel_origin():
    _reset_manager()
    user = type("User", (), {"id": 7})()
    websocket = _FakeWebSocket([], token=create_access_token(user.id))
    websocket.headers["origin"] = "https://attacker.trycloudflare.com"

    await live_api.live_websocket(websocket, db=_FakeDb(user))

    assert websocket.accepted is False
    assert websocket.closed == (4401, "Not authenticated")


@pytest.mark.asyncio
async def test_live_websocket_closes_when_access_token_expires(monkeypatch):
    _reset_manager()
    user = type("User", (), {"id": 7})()

    class _SlowWebSocket(_FakeWebSocket):
        async def receive_text(self):
            await asyncio.sleep(1)
            return ""

    websocket = _SlowWebSocket([])

    async def expiring_authentication(_websocket, _db):
        return user, time.time() + 0.01, 0

    monkeypatch.setattr(live_api, "_authenticate_live_websocket", expiring_authentication)

    await live_api.live_websocket(websocket, db=_FakeDb(user))

    assert websocket.accepted is True
    assert websocket.closed == (4401, "Access token expired")
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_live_websocket_accepts_authenticated_subscribe_ping_and_invalid_json():
    _reset_manager()
    user = type("User", (), {"id": 7})()
    websocket = _FakeWebSocket(
        [
            json.dumps({"action": "subscribe", "channel": "odds"}),
            json.dumps({"action": "ping"}),
            "not-json",
        ],
        token=create_access_token(user.id),
    )

    await live_api.live_websocket(websocket, db=_FakeDb(user))

    assert websocket.accepted is True
    assert websocket.sent == [
        {"type": "subscribed", "channels": ["odds"]},
        {"type": "pong"},
        {"type": "error", "message": "Invalid JSON"},
    ]
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_live_websocket_rejects_invalid_subscription_payload():
    _reset_manager()
    user = type("User", (), {"id": 7})()
    websocket = _FakeWebSocket(
        [json.dumps({"action": "subscribe", "channels": ["odds", 7]})],
        token=create_access_token(user.id),
    )

    await live_api.live_websocket(websocket, db=_FakeDb(user))

    assert websocket.sent == [{"type": "error", "message": "Channels must only contain strings"}]
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_manager_broadcast_filters_by_channel_and_match_subscription(monkeypatch):
    _reset_manager()

    async def current_versions(user_ids):
        return {user_id: 0 for user_id in user_ids}

    monkeypatch.setattr(live_api, "_load_user_session_versions", current_versions)

    odds_socket = _FakeWebSocket([])
    match_socket = _FakeWebSocket([])
    all_socket = _FakeWebSocket([])

    await live_api.manager.connect(odds_socket, user_id=7)
    await live_api.manager.connect(match_socket, user_id=7)
    await live_api.manager.connect(all_socket, user_id=8)

    await live_api.manager.set_subscriptions(odds_socket, "odds")
    await live_api.manager.set_subscriptions(match_socket, "match:42")

    await live_api.broadcast_odds_update(42, {"home": 1.9})
    await live_api.broadcast_prediction_update(9, "running", 0.5, user_id=7)
    await live_api.broadcast_match_update(99, "goal", {"team": "home"})

    assert [message["type"] for message in odds_socket.sent] == ["odds_update"]
    assert [message["type"] for message in match_socket.sent] == ["odds_update"]
    assert [message["type"] for message in all_socket.sent] == ["odds_update", "match_event"]

    await live_api.manager.disconnect(odds_socket)
    await live_api.manager.disconnect(match_socket)
    await live_api.manager.disconnect(all_socket)
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_live_websocket_rejects_global_and_per_user_capacity(monkeypatch):
    _reset_manager()
    monkeypatch.setattr(
        live_api,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "websocket_max_connections": 2,
                "websocket_max_connections_per_user": 1,
                "websocket_send_timeout_seconds": 1,
                "websocket_receive_timeout_seconds": 60,
                "websocket_max_message_bytes": 1024,
                "cors_origin_list": ["http://localhost:5173"],
            },
        )(),
    )
    first, same_user, other_user, overflow = (_FakeWebSocket([]) for _ in range(4))

    assert await live_api.manager.connect(first, user_id=7) is None
    assert await live_api.manager.connect(same_user, user_id=7) == "user_capacity"
    assert await live_api.manager.connect(other_user, user_id=8) is None
    assert await live_api.manager.connect(overflow, user_id=9) == "global_capacity"
    assert same_user.accepted is False
    assert overflow.accepted is False
    await live_api.manager.disconnect(first)
    await live_api.manager.disconnect(other_user)


@pytest.mark.asyncio
async def test_live_websocket_bounds_oversized_messages(monkeypatch):
    _reset_manager()
    monkeypatch.setattr(
        live_api,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "websocket_max_connections": 10,
                "websocket_max_connections_per_user": 2,
                "websocket_send_timeout_seconds": 1,
                "websocket_receive_timeout_seconds": 60,
                "websocket_max_message_bytes": 4,
                "cors_origin_list": ["http://localhost:5173"],
            },
        )(),
    )
    user = type("User", (), {"id": 7})()
    websocket = _FakeWebSocket(["12345"], token=create_access_token(user.id))

    await live_api.live_websocket(websocket, db=_FakeDb(user))

    assert websocket.closed == (1009, "Message too large")
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_manager_disconnects_slow_broadcast_consumers(monkeypatch):
    _reset_manager()

    async def current_versions(user_ids):
        return {user_id: 0 for user_id in user_ids}

    monkeypatch.setattr(live_api, "_load_user_session_versions", current_versions)
    monkeypatch.setattr(
        live_api,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "websocket_max_connections": 10,
                "websocket_max_connections_per_user": 2,
                "websocket_send_timeout_seconds": 0.01,
                "websocket_receive_timeout_seconds": 60,
                "websocket_max_message_bytes": 1024,
                "cors_origin_list": ["http://localhost:5173"],
            },
        )(),
    )

    class _SlowSendSocket(_FakeWebSocket):
        async def send_text(self, payload: str):
            await asyncio.sleep(1)

    websocket = _SlowSendSocket([])
    assert await live_api.manager.connect(websocket, user_id=7) is None
    await live_api.manager.broadcast({"type": "event"})

    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_live_websocket_slow_control_response_times_out_and_releases_slot(monkeypatch):
    _reset_manager()
    monkeypatch.setattr(
        live_api,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "websocket_max_connections": 10,
                "websocket_max_connections_per_user": 2,
                "websocket_send_timeout_seconds": 0.01,
                "websocket_receive_timeout_seconds": 60,
                "websocket_max_message_bytes": 1024,
                "cors_origin_list": ["http://localhost:5173"],
            },
        )(),
    )
    user = type("User", (), {"id": 7})()

    async def authenticate(_websocket, _db):
        return user, time.time() + 60, 0

    class SlowControlSocket(_FakeWebSocket):
        async def send_text(self, _payload: str):
            await asyncio.sleep(1)

    monkeypatch.setattr(live_api, "_authenticate_live_websocket", authenticate)
    websocket = SlowControlSocket([json.dumps({"action": "ping"})])

    await live_api.live_websocket(websocket, db=_FakeDb(user))

    assert websocket.closed == (1013, "Slow consumer")
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_revoked_user_socket_is_closed_and_removed_before_broadcast():
    _reset_manager()
    websocket = _FakeWebSocket([])
    await live_api.manager.connect(websocket, user_id=7)

    await live_api.manager.revoke_user(7)
    await live_api.manager.broadcast({"type": "event"})

    assert websocket.closed == (4401, "Session revoked")
    assert live_api.manager.active_connections == []
    assert websocket.sent == []


@pytest.mark.asyncio
async def test_manager_broadcast_revalidates_old_session_version_from_another_worker(monkeypatch):
    manager = live_api.ConnectionManager()
    websocket = _FakeWebSocket([])
    await manager.connect(websocket, user_id=7, session_version=0)

    async def bumped_version(_user_ids):
        return {7: 1}

    monkeypatch.setattr(live_api, "_load_user_session_versions", bumped_version)
    await manager.broadcast({"type": "event"})

    assert websocket.closed == (4401, "Session revoked")
    assert websocket.sent == []
    assert manager.active_connections == []


@pytest.mark.asyncio
async def test_live_websocket_rejects_stale_identity_map_user_during_handshake():
    """Handshake must bypass an AsyncSession's cached User when checking revocation."""
    from sqlalchemy.ext.asyncio import AsyncSession

    class StaleIdentityMapSession(AsyncSession):
        def __init__(self):
            super().__init__()
            self.cached_user = type("User", (), {"id": 7, "session_version": 0})()
            self.database_user = type("User", (), {"id": 7, "session_version": 1})()
            self.get_options: list[dict] = []

        async def execute(self, statement):
            self.get_options.append(statement.get_execution_options())
            return type("Result", (), {"scalar_one_or_none": lambda _self: self.database_user})()

    _reset_manager()
    db = StaleIdentityMapSession()
    websocket = _FakeWebSocket([], token=create_access_token(7, session_version=0))
    try:
        await asyncio.wait_for(live_api.live_websocket(websocket, db=db), timeout=1)
    finally:
        await db.close()

    assert db.get_options == [{"populate_existing": True}]
    assert websocket.accepted is False
    assert websocket.closed == (4401, "Not authenticated")


@pytest.mark.asyncio
async def test_live_websocket_rechecks_session_version_before_processing_command():
    """A revocation between handshake and the next command must close before replying."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

    class RevokedAfterHandshakeSession(AsyncSession):
        def __init__(self):
            super().__init__()
            self.user = User(id=7, email="revoked-command@example.test", session_version=0)
            self.execution_options: list[dict] = []

        async def execute(self, statement):
            options = statement.get_execution_options()
            self.execution_options.append(options)
            # Simulate an ORM identity-map refresh: the same object becomes revoked
            # only when the second SELECT explicitly asks to replace cached fields.
            if len(self.execution_options) == 2 and options.get("populate_existing"):
                self.user.session_version = 1
            return type("Result", (), {"scalar_one_or_none": lambda _self: self.user})()

    _reset_manager()
    db = RevokedAfterHandshakeSession()
    websocket = _FakeWebSocket([json.dumps({"action": "ping"})], token=create_access_token(7, session_version=0))
    try:
        await asyncio.wait_for(live_api.live_websocket(websocket, db=db), timeout=1)
    finally:
        await db.close()

    assert websocket.accepted is True
    assert websocket.closed == (4401, "Session revoked")
    assert websocket.sent == []
    assert db.execution_options == [{"populate_existing": True}, {"populate_existing": True}]


@pytest.mark.asyncio
async def test_manager_does_not_send_after_disconnect_while_broadcast_version_lookup_is_blocked(monkeypatch):
    manager = live_api.ConnectionManager()
    websocket = _FakeWebSocket([])
    entered_lookup = asyncio.Event()
    allow_lookup = asyncio.Event()

    async def blocked_versions(_user_ids):
        entered_lookup.set()
        await allow_lookup.wait()
        return {7: 0}

    monkeypatch.setattr(live_api, "_load_user_session_versions", blocked_versions)
    assert await manager.connect(websocket, user_id=7) is None

    broadcast = asyncio.create_task(manager.broadcast({"type": "event"}))
    await entered_lookup.wait()
    await manager.disconnect(websocket)
    allow_lookup.set()
    await broadcast

    assert websocket.sent == []
    assert manager.active_connections == []


@pytest.mark.asyncio
async def test_manager_releases_pending_reservation_when_accept_raises():
    manager = live_api.ConnectionManager()

    class ExplodingAcceptSocket(_FakeWebSocket):
        async def accept(self):
            raise RuntimeError("accept exploded")

    websocket = ExplodingAcceptSocket([])
    with pytest.raises(RuntimeError, match="accept exploded"):
        await manager.connect(websocket, user_id=7)

    assert manager._pending_connections == {}
    assert manager.active_connections == []


@pytest.mark.asyncio
async def test_manager_releases_pending_reservation_when_cancelled_after_accept_before_promotion():
    manager = live_api.ConnectionManager()
    accept_started = asyncio.Event()
    release_accept = asyncio.Event()

    class GatedAcceptSocket(_FakeWebSocket):
        async def accept(self):
            self.accepted = True
            accept_started.set()
            await release_accept.wait()

    websocket = GatedAcceptSocket([])
    task = asyncio.create_task(manager.connect(websocket, user_id=7))
    await accept_started.wait()
    await manager._lock.acquire()
    try:
        release_accept.set()
        await asyncio.sleep(0)
        task.cancel()
    finally:
        manager._lock.release()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert manager._pending_connections == {}
    assert manager.active_connections == []


@pytest.mark.asyncio
async def test_close_websocket_logs_timeout_without_reason(monkeypatch, caplog):
    class NeverClosingSocket(_FakeWebSocket):
        async def close(self, code: int, reason: str):
            await asyncio.Event().wait()

    monkeypatch.setattr(
        live_api,
        "get_settings",
        lambda: type("Settings", (), {"websocket_send_timeout_seconds": 0.01})(),
    )
    caplog.set_level(logging.WARNING, logger=live_api.__name__)

    await live_api._close_websocket(NeverClosingSocket([]), code=1013, reason="sensitive detail")

    record = next(record for record in caplog.records if record.message == "websocket_close_timeout")
    assert record.websocket_close_code == 1013
    assert "sensitive detail" not in record.getMessage()


@pytest.mark.asyncio
async def test_close_websocket_logs_failure_without_reason(monkeypatch, caplog):
    class FailingCloseSocket(_FakeWebSocket):
        async def close(self, code: int, reason: str):
            raise RuntimeError("close exploded")

    monkeypatch.setattr(
        live_api,
        "get_settings",
        lambda: type("Settings", (), {"websocket_send_timeout_seconds": 0.01})(),
    )
    caplog.set_level(logging.WARNING, logger=live_api.__name__)

    await live_api._close_websocket(FailingCloseSocket([]), code=4401, reason="sensitive detail")

    record = next(record for record in caplog.records if record.message == "websocket_close_failed")
    assert record.websocket_close_code == 4401
    assert "sensitive detail" not in record.getMessage()
