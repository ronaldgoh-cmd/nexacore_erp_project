# nexacore_erp/core/permissions.py
from __future__ import annotations
import re
from sqlalchemy import func
from .database import SessionLocal

# Models: User is in core, the rest are in account_management
from nexacore_erp.core.models import User
from nexacore_erp.modules.account_management.models import (
    Role, Permission, RolePermission, UserRole, AccessRule
)

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _user_role_ids(user_id: int, s) -> set[int]:
    """Resolve effective role IDs for a user from users.role and mapping table."""
    ids: set[int] = set()
    u = s.query(User).get(user_id)
    if u and (u.role or "").strip():
        r = s.query(Role).filter(func.lower(Role.name) == _norm(u.role)).first()
        if r:
            ids.add(r.id)
    for ur in s.query(UserRole).filter(UserRole.user_id == user_id):
        ids.add(ur.role_id)
    return ids

def has_permission(user_id: int, perm_key: str) -> bool:
    with SessionLocal() as s:
        rids = _user_role_ids(user_id, s)
        if not rids:
            return False
        q = (
            s.query(RolePermission)
            .join(Permission, Permission.id == RolePermission.perm_id)
            .filter(RolePermission.role_id.in_(rids), Permission.key == perm_key)
        )
        return s.query(q.exists()).scalar()

def can_view(
    user_id: int,
    module_name: str,
    submodule_name: str | None = None,
    tab_name: str | None = None,
) -> bool:
    """
    Grants view if:
      1) Role has perm 'module:{module}.view' (module level),
         'module:{module}/{sub}.view' (submodule), or
         'module:{module}/{sub}/{tab}.view' (tab), OR
      2) An AccessRule exists for the role on that module/sub/tab with can_view=1.

    Names are normalized to avoid whitespace/case mismatches.
    """
    mkey = _norm(module_name)
    skey = _norm(submodule_name or "")
    tkey = _norm(tab_name or "")

    # Permission keys fallback path
    if tkey:
        perm_sub = skey or "__module__"
        if has_permission(user_id, f"module:{mkey}/{perm_sub}/{tkey}.view"):
            return True
    if skey:
        if has_permission(user_id, f"module:{mkey}/{skey}.view"):
            return True
    if has_permission(user_id, f"module:{mkey}.view"):
        return True

    # AccessRule path
    with SessionLocal() as s:
        rids = _user_role_ids(user_id, s)
        if not rids:
            return False

        # Compare case-insensitively with trimming
        def _exists(match_sub: str, match_tab: str) -> bool:
            q = (
                s.query(AccessRule)
                .filter(
                    AccessRule.role_id.in_(rids),
                    func.lower(func.trim(AccessRule.module_name)) == mkey,
                    func.lower(func.trim(AccessRule.submodule_name)) == match_sub,
                    func.lower(func.trim(AccessRule.tab_name)) == match_tab,
                    AccessRule.can_view == True,  # noqa: E712
                )
            )
            return s.query(q.exists()).scalar()

        if _exists(skey, tkey):
            return True
        if tkey and _exists(skey, ""):
            return True
        if _exists("", ""):
            return True
        return False