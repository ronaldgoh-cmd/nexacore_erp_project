# nexacore_erp/modules/account_management/module.py
from __future__ import annotations
import json, os
from sqlalchemy import text
from PySide6.QtWidgets import QWidget
from ...core.database import MAIN_ENGINE, SessionLocal
from ...core.plugins import BaseModule
from ...core.models import User  # existing core table
from .models import BaseAcc, Role, Permission, RolePermission, UserRole, AccessRule
from .ui.account_main import AccountMainWidget
from .ui.users_tab import UsersTab
from .ui.roles_tab import RolesAccessTab

_MANIFEST = os.path.join(os.path.dirname(__file__), "manifest.json")

def _ensure_core_user_columns():
    # add email, is_active columns to users if missing
    with MAIN_ENGINE.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info('users')")).fetchall()}
        if "email" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR"))
        if "is_active" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))

def _ensure_acc_tables():
    # create account-management tables in MAIN DB only
    BaseAcc.metadata.create_all(bind=MAIN_ENGINE)
    # upgrade am_access_rules with tab_name + new unique constraint if needed
    with MAIN_ENGINE.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info('am_access_rules')")).fetchall()}
        if "tab_name" not in cols:
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS am_access_rules__new (
                    id INTEGER PRIMARY KEY,
                    role_id INTEGER NOT NULL REFERENCES am_roles(id) ON DELETE CASCADE,
                    module_name VARCHAR,
                    submodule_name VARCHAR DEFAULT '',
                    tab_name VARCHAR DEFAULT '',
                    can_view BOOLEAN DEFAULT 1,
                    can_edit BOOLEAN DEFAULT 0,
                    UNIQUE(role_id, module_name, submodule_name, tab_name)
                );
                """
            ))
            conn.execute(text(
                """
                INSERT INTO am_access_rules__new (id, role_id, module_name, submodule_name, tab_name, can_view, can_edit)
                SELECT id, role_id, module_name, submodule_name, '' AS tab_name, can_view, can_edit
                FROM am_access_rules;
                """
            ))
            conn.execute(text("DROP TABLE am_access_rules"))
            conn.execute(text("ALTER TABLE am_access_rules__new RENAME TO am_access_rules"))
        conn.execute(text("PRAGMA foreign_keys = ON"))
    # seed a default "Admin" role with baseline powers if empty
    with SessionLocal() as s:
        if not s.query(Role).first():
            admin = Role(name="Admin", description="Administrators")
            s.add(admin); s.flush()
            for key in ["accounts.manage_users", "accounts.manage_roles", "modules.install"]:
                p = s.query(Permission).filter(Permission.key == key).first()
                if not p:
                    p = Permission(key=key); s.add(p); s.flush()
                s.add(RolePermission(role_id=admin.id, perm_id=p.id))
            s.commit()

class Module(BaseModule):
    name = "Account Management"
    submodules = ["Users", "Roles & Access"]

    def __init__(self) -> None:
        _ensure_core_user_columns()
        _ensure_acc_tables()

    def get_info(self) -> dict:
        with open(_MANIFEST, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_widget(self) -> QWidget:
        return AccountMainWidget()

    def get_submodule_widget(self, name: str) -> QWidget:
        if name == "Users":
            return UsersTab()
        if name == "Roles & Access":
            return RolesAccessTab()
        return AccountMainWidget()

    def get_models(self):
        return [Role, Permission, RolePermission, UserRole, AccessRule]

    def factory_reset(self) -> None:
        with MAIN_ENGINE.begin() as conn:
            for tbl in ["am_access_rules", "am_user_roles", "am_role_permissions", "am_permissions", "am_roles"]:
                conn.execute(text(f"DELETE FROM {tbl}"))
