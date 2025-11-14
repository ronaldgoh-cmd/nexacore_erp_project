"""FastAPI application entry point."""
from fastapi import FastAPI

from . import models
from .database import engine
from .routers.employees import router as employees_router
from .auth import router as auth_router

app = FastAPI(title="NexaCore ERP Backend", version="0.1.0")
app.include_router(auth_router)
app.include_router(employees_router)


@app.on_event("startup")
async def on_startup() -> None:
    """Ensure database tables exist when the app boots."""

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


@app.get("/health", tags=["system"])
async def healthcheck() -> dict[str, str]:
    """Simple readiness probe for uptime checks."""

    return {"status": "ok"}
