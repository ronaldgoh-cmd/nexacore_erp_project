from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import shutil
from sqlalchemy import create_engine, text, MetaData
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------- paths ----------
PKG_DIR = Path(__file__).resolve().parents[1]          # .../nexacore_erp
DATA_DIR = PKG_DIR / "database"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

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

def get_main_session():
    return SessionMain()

def init_db() -> None:
    """Create core tables on the main database. Import inside to avoid circulars."""
    from . import models as core_models  # noqa: F401
    Base.metadata.create_all(bind=MAIN_ENGINE)
    # Enable FKs and run lightweight migrations
    with MAIN_ENGINE.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        # add 'stamp' column if missing
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(company_settings)")).fetchall()}
        if "stamp" not in cols:
            conn.execute(text("ALTER TABLE company_settings ADD COLUMN stamp BLOB"))

# ---------- Module databases (separate .db per module) ----------
MODULE_DB_FILES = {
    "employee_management": "nexacore_employeemanagement.db",
    # add future modules here as needed
}

_module_engines: dict[str, any] = {}
_module_sessions: dict[str, sessionmaker] = {}
_module_metadata: dict[str, MetaData] = {}

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
            poolclass=NullPool,
        )
        _module_engines[module_key] = eng
        with eng.connect() as c:
            c.execute(text("PRAGMA foreign_keys = ON"))
        metadata = _module_metadata.get(module_key)
        if metadata is not None:
            metadata.create_all(bind=eng)
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
    _module_metadata[module_key] = base_metadata
    eng = get_module_engine(module_key)
    base_metadata.create_all(bind=eng)

# Convenience for Employee Management
def get_employee_session():
    return get_module_sessionmaker("employee_management")()


def get_module_db_path(module_key: str) -> Path:
    """Return the filesystem path for a module's standalone database."""
    return _module_db_path(module_key)


def wipe_module_database(module_key: str) -> None:
    """Dispose cached connections and delete a module's database file if present."""
    eng = _module_engines.pop(module_key, None)
    if eng is not None:
        try:
            eng.dispose()
        except Exception:
            pass
    _module_sessions.pop(module_key, None)

    path = _module_db_path(module_key)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def iter_database_files() -> list[Path]:
    """Return a list of all database files managed by the application."""
    files: list[Path] = []
    if MAIN_DB_PATH.exists():
        files.append(MAIN_DB_PATH)
    existing = {p.resolve() for p in files}
    for path in DATA_DIR.glob("*.db"):
        if path.resolve() not in existing:
            files.append(path)
    return sorted(files)


def _ensure_engines_disposed() -> None:
    """Dispose of cached engines and sessions so files can be copied."""
    try:
        MAIN_ENGINE.dispose()
    except Exception:
        pass
    for eng in list(_module_engines.values()):
        try:
            eng.dispose()
        except Exception:
            pass
    _module_engines.clear()
    _module_sessions.clear()


def create_backup(progress_callback=None) -> dict:
    """Copy all database files to a timestamped backup folder."""

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now()
    backup_id = timestamp.strftime("%Y%m%d-%H%M%S")
    backup_dir = BACKUP_DIR / backup_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_files = iter_database_files()
    total = len(db_files)

    for idx, path in enumerate(db_files, start=1):
        if progress_callback:
            progress_callback(idx - 1, total, f"Copying {path.name}…")
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)

    metadata = {
        "id": backup_id,
        "created_at": timestamp.isoformat(),
        "files": [p.name for p in db_files],
    }

    with (backup_dir / "metadata.json").open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    if progress_callback:
        progress_callback(total, total, "Backup complete.")

    return metadata


def list_backups() -> list[dict]:
    """Return metadata for available backups sorted newest first."""

    if not BACKUP_DIR.exists():
        return []

    backups: list[dict] = []
    for candidate in BACKUP_DIR.iterdir():
        if not candidate.is_dir():
            continue
        meta_path = candidate / "metadata.json"
        metadata: dict | None = None
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = None
        if not metadata:
            metadata = {
                "id": candidate.name,
                "created_at": None,
                "files": [p.name for p in candidate.glob("*.db")],
            }
        metadata["path"] = candidate
        backups.append(metadata)

    def _sort_key(item: dict):
        created = item.get("created_at")
        try:
            return datetime.fromisoformat(created)  # type: ignore[arg-type]
        except Exception:
            return datetime.min

    backups.sort(key=_sort_key, reverse=True)
    return backups


def restore_backup(backup_id: str, progress_callback=None) -> None:
    """Restore databases from the specified backup id."""

    backup_dir = BACKUP_DIR / backup_id
    if not backup_dir.exists() or not backup_dir.is_dir():
        raise FileNotFoundError(f"Backup '{backup_id}' not found")

    _ensure_engines_disposed()

    backup_files = sorted(backup_dir.glob("*.db"))
    total = len(backup_files)

    existing_files = iter_database_files()
    for path in existing_files:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    for idx, path in enumerate(backup_files, start=1):
        if progress_callback:
            progress_callback(idx - 1, total, f"Restoring {path.name}…")
        shutil.copy2(path, DATA_DIR / path.name)

    if progress_callback:
        progress_callback(total, total, "Restore complete.")
