"""Declarative base classes for ORM models."""

from __future__ import annotations

from sqlalchemy import MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarative class that centralises metadata."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantMixin:
    """Mixin that adds the `account_id` column to tenant-scoped tables."""

    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
