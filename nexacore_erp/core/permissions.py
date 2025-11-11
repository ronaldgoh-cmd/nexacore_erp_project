# nexacore_erp/core/permissions.py
from __future__ import annotations
import re
from sqlalchemy import func, or_
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
      - No explicit AccessRule deny exists for the location, and
      - Either an AccessRule allow exists or the role owns the matching permission.

    Names are normalized to avoid whitespace/case mismatches.
    """
    mkey = _norm(module_name)
    skey = _norm(submodule_name or "")
    tkey = _norm(tab_name or "")

    with SessionLocal() as s:
        rids = _user_role_ids(user_id, s)
        if not rids:
            return False

        # Compare case-insensitively with trimming
        def _exists(match_sub: str, match_tab: str, expect: bool) -> bool:
            q = (
                s.query(AccessRule)
                .filter(
                    AccessRule.role_id.in_(rids),
                    func.lower(func.trim(AccessRule.module_name)) == mkey,
                    func.lower(func.trim(AccessRule.submodule_name)) == match_sub,
                    func.lower(func.trim(AccessRule.tab_name)) == match_tab,
                    AccessRule.can_view == expect,
                )
            )
            return s.query(q.exists()).scalar()

        def _deny(match_sub: str, match_tab: str) -> bool:
            return _exists(match_sub, match_tab, False)

        def _allow(match_sub: str, match_tab: str) -> bool:
            return _exists(match_sub, match_tab, True)

        def _any_tab_allow(match_sub: str) -> bool:
            q = (
                s.query(AccessRule)
                .filter(
                    AccessRule.role_id.in_(rids),
                    func.lower(func.trim(AccessRule.module_name)) == mkey,
                    func.lower(func.trim(AccessRule.submodule_name)) == match_sub,
                    func.lower(func.trim(AccessRule.tab_name)) != "",
                    AccessRule.can_view == True,  # noqa: E712
                )
            )
            return s.query(q.exists()).scalar()

        def _any_child_allow() -> bool:
            q = (
                s.query(AccessRule)
                .filter(
                    AccessRule.role_id.in_(rids),
                    func.lower(func.trim(AccessRule.module_name)) == mkey,
                    AccessRule.can_view == True,  # noqa: E712
                )
                .filter(
                    or_(
                        func.lower(func.trim(AccessRule.submodule_name)) != "",
                        func.lower(func.trim(AccessRule.tab_name)) != "",
                    )
                )
            )
            return s.query(q.exists()).scalar()

        # explicit denies override everything
        if tkey:
            if _deny(skey, tkey) or _deny(skey, "") or _deny("", ""):
                return False
        elif skey:
            if _deny(skey, "") or _deny("", ""):
                return False
        else:
            if _deny("", ""):
                return False

        # explicit allows (or allowed children) grant access
        if tkey and _allow(skey, tkey):
            return True
        if skey:
            if _allow(skey, "") or _any_tab_allow(skey):
                return True
        else:
            if _allow("", "") or _any_tab_allow("") or _any_child_allow():
                return True

    # Permission keys fallback path (no relevant AccessRule state)
    if tkey:
        perm_sub = skey or "__module__"
        if has_permission(user_id, f"module:{mkey}/{perm_sub}/{tkey}.view"):
            return True
    if skey:
        if has_permission(user_id, f"module:{mkey}/{skey}.view"):
            return True
    if has_permission(user_id, f"module:{mkey}.view"):
        return True
    return False
