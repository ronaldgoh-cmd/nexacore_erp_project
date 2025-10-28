# nexacore_erp/core/database.py
from __future__ import annotations

from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------- paths ----------
PKG_DIR = Path(__file__).resolve().parents[1]          # .../nexacore_erp
DATA_DIR = PKG_DIR / "database"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def _sqlite_url(p: Path) -> str:
    return "sqlite:///" + p.as_posix()

# ---------- ORM Base for CORE models ----------
# core/models.py does: from .database import Base
Base = declarative_base()

# ---------- MAIN framework DB (users, settings, modules) ----------
MAIN_DB_PATH = DATA_DIR / "nexacore_main.db"
MAIN_ENGINE = create_engine(
    _sqlite_url(MAIN_DB_PATH),
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    future=True,
)
SessionMain = sessionmaker(bind=MAIN_ENGINE, autocommit=False, autoflush=False, future=True)
# Back-compat alias
SessionLocal = SessionMain

def init_db() -> None:
    """Create core tables on the main database. Import inside to avoid circulars."""
    from . import models as core_models  # noqa: F401
    Base.metadata.create_all(bind=MAIN_ENGINE)
    with MAIN_ENGINE.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))

# ---------- Module databases (separate .db per module) ----------
MODULE_DB_FILES = {
    "employee_management": "nexacore_employeemanagement.db",
    # add future modules here as needed
}

_module_engines: dict[str, any] = {}
_module_sessions: dict[str, sessionmaker] = {}

def _module_db_path(module_key: str) -> Path:
    filename = MODULE_DB_FILES.get(module_key)
    if not filename:
        safe = "".join(ch for ch in module_key if ch.isalnum()).lower()
        filename = f"nexacore_{safe}.db"
        MODULE_DB_FILES[module_key] = filename
    return DATA_DIR / filename

def get_module_engine(module_key: str):
    eng = _module_engines.get(module_key)
    if eng is None:
        p = _module_db_path(module_key)
        eng = create_engine(
            _sqlite_url(p),
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
            future=True,
        )
        _module_engines[module_key] = eng
        with eng.connect() as c:
            c.execute(text("PRAGMA foreign_keys = ON"))
    return eng

def get_module_sessionmaker(module_key: str) -> sessionmaker:
    sm = _module_sessions.get(module_key)
    if sm is None:
        eng = get_module_engine(module_key)
        sm = sessionmaker(bind=eng, autocommit=False, autoflush=False, future=True)
        _module_sessions[module_key] = sm
    return sm

def init_module_db(module_key: str, base_metadata) -> None:
    """Create tables for a module's SQLAlchemy Base on its own DB."""
    eng = get_module_engine(module_key)
    base_metadata.create_all(bind=eng)

# Convenience for Employee Management
def get_employee_session():
    return get_module_sessionmaker("employee_management")()
