import json

import pytest
from fastapi import WebSocketDisconnect

from app.api.v1 import live as live_api
from app.api.v1.router import v1_router


class _FakeWebSocket:
    def __init__(self, messages: list[str]):
        self._messages = list(messages)
        self.accepted = False
        self.sent: list[dict] = []

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        if not self._messages:
            raise WebSocketDisconnect()
        return self._messages.pop(0)

    async def send_text(self, payload: str):
        self.sent.append(json.loads(payload))


def test_v1_router_exposes_live_websocket_route():
    route_paths = {getattr(route, "path", None) for route in v1_router.routes}

    assert "/api/v1/live/ws" in route_paths


@pytest.mark.asyncio
async def test_live_websocket_accepts_subscribe_ping_and_invalid_json():
    live_api.manager.active_connections.clear()
    live_api.manager._subscriptions.clear()
    websocket = _FakeWebSocket(
        [
            json.dumps({"action": "subscribe", "channel": "odds"}),
            json.dumps({"action": "ping"}),
            "not-json",
        ]
    )

    await live_api.live_websocket(websocket)

    assert websocket.accepted is True
    assert websocket.sent == [
        {"type": "subscribed", "channels": ["odds"]},
        {"type": "pong"},
        {"type": "error", "message": "Invalid JSON"},
    ]
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_live_websocket_rejects_invalid_subscription_payload():
    live_api.manager.active_connections.clear()
    live_api.manager._subscriptions.clear()
    websocket = _FakeWebSocket([json.dumps({"action": "subscribe", "channels": ["odds", 7]})])

    await live_api.live_websocket(websocket)

    assert websocket.sent == [
        {"type": "error", "message": "Channels must only contain strings"}
    ]
    assert live_api.manager.active_connections == []


@pytest.mark.asyncio
async def test_manager_broadcast_filters_by_channel_and_match_subscription():
    live_api.manager.active_connections.clear()
    live_api.manager._subscriptions.clear()

    odds_socket = _FakeWebSocket([])
    match_socket = _FakeWebSocket([])
    all_socket = _FakeWebSocket([])

    await live_api.manager.connect(odds_socket)
    await live_api.manager.connect(match_socket)
    await live_api.manager.connect(all_socket)

    await live_api.manager.set_subscriptions(odds_socket, "odds")
    await live_api.manager.set_subscriptions(match_socket, "match:42")

    await live_api.broadcast_odds_update(42, {"home": 1.9})
    await live_api.broadcast_prediction_update(9, "running", 0.5)
    await live_api.broadcast_match_update(99, "goal", {"team": "home"})

    assert [message["type"] for message in odds_socket.sent] == ["odds_update"]
    assert [message["type"] for message in match_socket.sent] == ["odds_update"]
    assert [message["type"] for message in all_socket.sent] == ["odds_update", "prediction_update", "match_event"]

    await live_api.manager.disconnect(odds_socket)
    await live_api.manager.disconnect(match_socket)
    await live_api.manager.disconnect(all_socket)
    assert live_api.manager.active_connections == []
