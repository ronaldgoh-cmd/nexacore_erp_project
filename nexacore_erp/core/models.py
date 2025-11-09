from sqlalchemy import String, Integer, LargeBinary, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")

    # identity
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    role: Mapped[str] = mapped_column(String, default="user")  # user|admin|superadmin

    # auth
    password_hash: Mapped[str] = mapped_column(String)
    # plaintext-for-display ONLY, encrypted or base64; may be NULL for legacy rows
    password_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # profile/state
    email: Mapped[str] = mapped_column(String, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    timezone: Mapped[str] = mapped_column(String, default="Etc/UTC")
    theme: Mapped[str] = mapped_column(String, default="light")


class CompanySettings(Base):
    __tablename__ = "company_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    name: Mapped[str] = mapped_column(String, default="")
    detail1: Mapped[str] = mapped_column(String, default="")
    detail2: Mapped[str] = mapped_column(String, default="")
    logo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    stamp: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    version: Mapped[str] = mapped_column(String, default="")
    about: Mapped[str] = mapped_column(String, default="")


class ModuleState(Base):
    __tablename__ = "module_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    name: Mapped[str] = mapped_column(String, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
