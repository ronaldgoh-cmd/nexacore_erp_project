"""Test fixtures for the backend."""
import os
from pathlib import Path

import pytest_asyncio
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_backend.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app import models  # noqa: E402
from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402


test_db_path = Path("test_backend.db")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database() -> None:
    """Create the database schema before tests and drop afterwards."""

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)
    if test_db_path.exists():
        test_db_path.unlink()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Provide an HTTP client for integration tests."""

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client
