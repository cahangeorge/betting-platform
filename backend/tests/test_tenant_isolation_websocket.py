import json

import pytest

from app.api.v1 import live as live_api


class _WebSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def accept(self):
        return None

    async def send_text(self, payload: str):
        self.sent.append(json.loads(payload))


@pytest.mark.asyncio
async def test_prediction_update_is_not_sent_to_another_users_websocket(monkeypatch):
    async def current_session_versions(user_ids: set[int]) -> dict[int, int]:
        return {user_id: 0 for user_id in user_ids}

    monkeypatch.setattr(live_api, "_load_user_session_versions", current_session_versions)
    owner_socket = _WebSocket()
    other_socket = _WebSocket()
    manager = live_api.ConnectionManager()

    await manager.connect(owner_socket, user_id=101)
    await manager.connect(other_socket, user_id=202)

    await manager.broadcast(
        {"type": "prediction_update", "run_id": 77, "status": "completed"},
        channel="predictions",
        recipient_user_id=101,
    )

    assert owner_socket.sent == [{"type": "prediction_update", "run_id": 77, "status": "completed"}]
    assert other_socket.sent == []
