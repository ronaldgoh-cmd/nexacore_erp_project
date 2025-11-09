# nexacore_erp/core/auth.py
from __future__ import annotations
from typing import Optional
from types import SimpleNamespace

from werkzeug.security import generate_password_hash, check_password_hash

from .database import SessionLocal, init_db
from .models import User, UserSettings  # only for types

# ---------- runtime current user ----------
_CURRENT_USER: Optional[User] = None
def set_current_user(u: Optional[User]) -> None:
    global _CURRENT_USER
    _CURRENT_USER = u
def get_current_user() -> Optional[User]:
    return _CURRENT_USER

# ---------- superadministrator (ephemeral, DB-less) ----------
SUPERADMIN_USER = "superadministrator"
SUPERADMIN_PASS = "superadministrator123!"

def _make_ephemeral_superadmin() -> User:
    u = SimpleNamespace(
        id=-1,
        username=SUPERADMIN_USER,
        role="superadmin",
        is_active=True,
        account_id="root",
        email="",
        created_at=None,
    )
    setattr(u, "_ephemeral_super", True)
    return u  # type: ignore[return-value]

def is_ephemeral_user(u: object) -> bool:
    return bool(getattr(u, "_ephemeral_super", False))

# ---------- password helpers ----------
def hash_password(p: str) -> str:
    return generate_password_hash(p)

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return check_password_hash(hashed, plain)
    except Exception:
        return False

# ---------- authenticate ----------
def authenticate(username: str, password: str) -> Optional[User]:
    # 1) Ephemeral superadmin shortcut
    if username == SUPERADMIN_USER and password == SUPERADMIN_PASS:
        return _make_ephemeral_superadmin()

    # 2) Normal DB user (must be active)
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == username).first()
        if not u:
            return None
        if hasattr(u, "is_active") and not bool(getattr(u, "is_active", True)):
            return None
        return u if verify_password(password, getattr(u, "password_hash", "") or "") else None

# ---------- bootstrap ----------
def ensure_bootstrap_superadmin() -> None:
    """
    Only ensures DB/tables exist. Does NOT auto-create any admin user.
    """
    init_db()
