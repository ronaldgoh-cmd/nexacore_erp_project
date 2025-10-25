import os
import pkgutil
import importlib
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_URL = os.getenv("NEXACORE_DB_URL", "sqlite:///./nexacore.db")


class Base(DeclarativeBase):
    pass


engine = create_engine(DB_URL, pool_pre_ping=True, future=True)

# SQLite: enforce FKs
if DB_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_con, _):
        cur = dbapi_con.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _sqlite_add_missing_columns():
    """One-time patch for existing SQLite DBs."""
    if not DB_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        # company_settings columns
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='company_settings'"
        ).fetchone()
        if exists:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(company_settings)")]
            if "version" not in cols:
                conn.execute(text("ALTER TABLE company_settings ADD COLUMN version TEXT DEFAULT ''"))
            if "about" not in cols:
                conn.execute(text("ALTER TABLE company_settings ADD COLUMN about TEXT DEFAULT ''"))

        # employees.department column
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='employees'"
        ).fetchone()
        if exists:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(employees)")]
            if "department" not in cols:
                conn.execute(text("ALTER TABLE employees ADD COLUMN department VARCHAR(255) DEFAULT ''"))


def _import_module_models():
    """Import nexacore_erp.modules.*.models so plugin tables are registered."""
    try:
        from nexacore_erp import modules as modules_pkg
    except Exception:
        return
    prefix = modules_pkg.__name__ + "."
    for _, modname, ispkg in pkgutil.walk_packages(modules_pkg.__path__, prefix):
        if modname.endswith(".models"):
            try:
                importlib.import_module(modname)
            except Exception:
                # Ignore broken plugin models during startup
                pass


def init_db():
    from . import models  # register core tables
    _import_module_models()  # register plugin tables
    Base.metadata.create_all(bind=engine)
    _sqlite_add_missing_columns()
