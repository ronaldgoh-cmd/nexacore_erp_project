"""FastAPI application entry point."""
import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from . import models
from .auth import router as auth_router
from .database import AsyncSessionLocal, engine
from .dependencies import decode_access_token
from .models import SystemStatus
from .routers.employees import router as employees_router
from .routers.system import router as system_router
from .websocket_manager import ws_manager

app = FastAPI(title="NexaCore ERP Backend", version="0.1.0")
app.include_router(auth_router)
app.include_router(employees_router)
app.include_router(system_router)


@app.on_event("startup")
async def on_startup() -> None:
    """Ensure database tables exist and baseline data is present."""

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SystemStatus).limit(1))
        status_row = result.scalar_one_or_none()
        if status_row is None:
            session.add(SystemStatus())
            await session.commit()


@app.get("/health", tags=["system"])
async def healthcheck() -> dict[str, str]:
    """Simple readiness probe for uptime checks."""

    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str) -> None:
    """Authenticate clients and keep a tenant-scoped connection open."""

    try:
        token_data = decode_access_token(token)
    except jwt.PyJWTError:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid or expired token",
        )
        return

    tenant_id = token_data.account_id
    await ws_manager.connect(tenant_id, websocket)
    try:
        while True:
            # Keep the connection alive and listen for optional client pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(tenant_id, websocket)
