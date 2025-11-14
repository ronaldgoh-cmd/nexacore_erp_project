"""Declarative base for ORM models."""
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String


class Base(DeclarativeBase):
    """Base class that includes a tenant-aware account identifier."""

    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
