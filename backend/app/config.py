"""Application settings and configuration helpers."""
from functools import lru_cache
import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    """Runtime configuration loaded from environment variables."""

    database_url: str = Field(
        default="sqlite+aiosqlite:///./nexacore.db", alias="DATABASE_URL"
    )
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    access_token_expires_minutes: int = Field(default=60 * 24)

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings.model_fields["database_url"].default),
        secret_key=os.getenv("SECRET_KEY", Settings.model_fields["secret_key"].default),
    )
