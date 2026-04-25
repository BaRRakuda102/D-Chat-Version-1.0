from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, set[WebSocket]] = defaultdict(set)
        self.connection_info: dict[WebSocket, dict[str, int]] = {}
        self.user_connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, *, room_id: int, user_id: int) -> None:
        await websocket.accept()
        self.active_connections[room_id].add(websocket)
        self.connection_info[websocket] = {"room_id": room_id, "user_id": user_id}
        self.user_connections[user_id].add(websocket)

    async def connect_user(self, websocket: WebSocket, *, user_id: int) -> None:
        await websocket.accept()
        self.user_connections[user_id].add(websocket)
        self.connection_info[websocket] = {"room_id": 0, "user_id": user_id}

    def disconnect(self, websocket: WebSocket) -> None:
        info = self.connection_info.pop(websocket, None)
        if not info:
            return
        room_id = info["room_id"]
        user_id = info["user_id"]
        self.active_connections[room_id].discard(websocket)
        if room_id in self.active_connections and not self.active_connections[room_id]:
            del self.active_connections[room_id]
        self.user_connections[user_id].discard(websocket)
        if user_id in self.user_connections and not self.user_connections[user_id]:
            del self.user_connections[user_id]

    async def broadcast(self, room_id: int, payload: dict[str, Any], *, exclude: WebSocket | None = None) -> None:
        dead_connections: list[WebSocket] = []
        for websocket in self.active_connections.get(room_id, set()):
            if websocket == exclude:
                continue
            try:
                await websocket.send_json(payload)
            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.disconnect(websocket)

    async def broadcast_to_user(
        self,
        user_id: int,
        payload: dict[str, Any],
        *,
        exclude: WebSocket | None = None,
    ) -> None:
        dead_connections: list[WebSocket] = []
        for websocket in self.user_connections.get(user_id, set()):
            if websocket == exclude:
                continue
            try:
                await websocket.send_json(payload)
            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.disconnect(websocket)

    def disconnect_user_from_room(self, *, user_id: int, room_id: int) -> None:
        for websocket, info in list(self.connection_info.items()):
            if info["user_id"] == user_id and info["room_id"] == room_id:
                self.disconnect(websocket)

    def has_user_connections(self, user_id: int) -> bool:
        return bool(self.user_connections.get(user_id))

    def get_room_connections(self, room_id: int) -> list[tuple[WebSocket, int]]:
        return [
            (websocket, self.connection_info[websocket]["user_id"])
            for websocket in self.active_connections.get(room_id, set())
            if websocket in self.connection_info
        ]


manager = ConnectionManager()
