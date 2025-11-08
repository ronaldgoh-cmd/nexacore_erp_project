from __future__ import annotations
from typing import Iterable
from sqlalchemy import text
from .database import SessionLocal

def _user_role_ids(user_id: int) -> list[int]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT role_id FROM am_user_roles WHERE user_id=:uid"), {"uid": user_id}).fetchall()
        return [r[0] for r in rows]

def has_permission(user_id: int, perm_key: str) -> bool:
    with SessionLocal() as s:
        sql = """
            SELECT 1
            FROM am_user_roles ur
            JOIN am_role_permissions rp ON rp.role_id = ur.role_id
            JOIN am_permissions p ON p.id = rp.perm_id
            WHERE ur.user_id=:uid AND p.key=:k
            LIMIT 1
        """
        return bool(s.execute(text(sql), {"uid": user_id, "k": perm_key}).fetchone())

def can_view(user_id: int, module_name: str, submodule_name: str | None = None) -> bool:
    sub = submodule_name or ""
    with SessionLocal() as s:
        sql = """
            SELECT 1
              FROM am_user_roles ur
              JOIN am_access_rules ar ON ar.role_id = ur.role_id
             WHERE ur.user_id=:uid AND ar.module_name=:m AND ar.submodule_name=:s AND ar.can_view=1
             LIMIT 1
        """
        return bool(s.execute(text(sql), {"uid": user_id, "m": module_name, "s": sub}).fetchone())
