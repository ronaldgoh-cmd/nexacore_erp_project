"""Utility helpers for FastAPI WebSocket broadcasting."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import WebSocket


class WebSocketManager:
    """Tracks open tenant-specific WebSocket connections."""

    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, tenant_id: str, websocket: WebSocket) -> None:
        """Register a websocket connection under a tenant scope."""

        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(tenant_id, []).append(websocket)

    async def disconnect(self, tenant_id: str, websocket: WebSocket) -> None:
        """Remove a websocket connection if it still exists."""

        async with self._lock:
            if tenant_id not in self._connections:
                return
            if websocket in self._connections[tenant_id]:
                self._connections[tenant_id].remove(websocket)
            if not self._connections[tenant_id]:
                del self._connections[tenant_id]

    async def broadcast(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Send a payload to every websocket registered for a tenant."""

        async with self._lock:
            targets = list(self._connections.get(tenant_id, []))

        stale_connections: list[WebSocket] = []
        for connection in targets:
            try:
                await connection.send_json(payload)
            except Exception:  # pragma: no cover - defensive cleanup
                stale_connections.append(connection)

        for websocket in stale_connections:
            await self.disconnect(tenant_id, websocket)


ws_manager = WebSocketManager()


async def broadcast_event(
    tenant_id: str,
    channel: str,
    action: str,
    data: Dict[str, Any],
) -> None:
    """Helper to send a normalized event payload to subscribers."""

    await ws_manager.broadcast(
        tenant_id,
        {
            "channel": channel,
            "action": action,
            "data": data,
        },
    )
