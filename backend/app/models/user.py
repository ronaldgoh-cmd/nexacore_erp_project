"""User model mirroring the desktop application's schema."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class User(TenantMixin, Base):
    """Application user with tenant scoping."""

    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint("account_id", "username", name="uq_users_account_username"),
        Index("ix_users_account_id", "account_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String, default="user")
    password_hash: Mapped[str] = mapped_column(String)
    password_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    email: Mapped[str] = mapped_column(String, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
