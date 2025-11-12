from sqlalchemy import String, Integer, LargeBinary, Boolean, DateTime, Text, UniqueConstraint
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


class DashboardPreference(Base):
    __tablename__ = "dashboard_preferences"
    __table_args__ = (UniqueConstraint("account_id", "user_id", name="uq_dashboard_pref_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    widgets_json: Mapped[str] = mapped_column(Text, default="[]")


class CloudSettings(Base):
    __tablename__ = "cloud_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    provider: Mapped[str] = mapped_column(String, default="digitalocean")
    region: Mapped[str] = mapped_column(String, default="")
    spaces_region: Mapped[str] = mapped_column(String, default="")
    spaces_bucket: Mapped[str] = mapped_column(String, default="")
    control_panel_url: Mapped[str] = mapped_column(String, default="https://cloud.digitalocean.com")
    api_endpoint: Mapped[str] = mapped_column(String, default="")
    api_token: Mapped[str] = mapped_column(String, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
