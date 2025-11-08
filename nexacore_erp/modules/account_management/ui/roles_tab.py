# nexacore_erp/modules/account_management/ui/roles_tab.py
from __future__ import annotations
from typing import Iterable, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLineEdit,
    QGroupBox, QGridLayout, QCheckBox, QMessageBox, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QSplitter, QInputDialog
)

# DB + models
from nexacore_erp.core.database import SessionLocal
from nexacore_erp.core.plugins import discover_modules
from ..models import BaseAcc, Role, Permission, RolePermission, UserRole, AccessRule  # noqa: F401

# Seed permissions. Add more as you add enforcement points.
_BASE_PERMS = [
    "accounts.manage_users",
    "accounts.manage_roles",
    "modules.install",
]


class RolesAccessTab(QWidget):
    def __init__(self):
        super().__init__()
        split = QSplitter(Qt.Horizontal, self)

        # ---------- left: roles list + actions ----------
        left = QWidget()
        lv = QVBoxLayout(left)
        self.list_roles = QListWidget()
        row = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_rename = QPushButton("Rename")
        self.btn_delete = QPushButton("Delete")
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_rename)
        row.addWidget(self.btn_delete)
        lv.addWidget(self.list_roles)
        lv.addLayout(row)

        # ---------- right: permissions + module access ----------
        right = QWidget()
        rv = QVBoxLayout(right)

        # permissions group
        grp_perm = QGroupBox("Permissions")
        self.perm_grid = QGridLayout(grp_perm)
        self.perm_checks: dict[str, QCheckBox] = {}

        # save buttons row
        actions_row = QHBoxLayout()
        self.btn_save_perms = QPushButton("Save Permissions")
        self.btn_save_access = QPushButton("Save Module Access")
        actions_row.addStretch(1)
        actions_row.addWidget(self.btn_save_perms)
        actions_row.addWidget(self.btn_save_access)

        # module access tree
        grp_access = QGroupBox("Module Access")
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Module / Submodule", "View"])
        self.tree.setColumnWidth(0, 320)
        lay_access = QVBoxLayout(grp_access)
        lay_access.addWidget(self.tree)

        rv.addWidget(grp_perm)
        rv.addWidget(grp_access)
        rv.addLayout(actions_row)

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(split)

        # wire buttons
        self.btn_add.clicked.connect(self._add_role)
        self.btn_rename.clicked.connect(self._rename_role)
        self.btn_delete.clicked.connect(self._delete_role)
        self.list_roles.currentItemChanged.connect(lambda *_: self._load_role_detail())
        self.btn_save_perms.clicked.connect(self._save_perms_clicked)
        self.btn_save_access.clicked.connect(self._save_access_clicked)

        # build static UI
        self._build_permissions_ui()
        self._reload_roles()
        self._reload_access_tree()

    # ---------------- roles helpers ----------------
    def _selected_role(self) -> Role | None:
        it = self.list_roles.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _reload_roles(self):
        self.list_roles.clear()
        with SessionLocal() as s:
            roles = s.query(Role).order_by(Role.name.asc()).all()
            for r in roles:
                it = QListWidgetItem(r.name)
                it.setData(Qt.UserRole, r)
                self.list_roles.addItem(it)
        if self.list_roles.count() > 0:
            self.list_roles.setCurrentRow(0)

    # ---------------- permissions UI ----------------
    def _discover_permission_keys(self) -> list[str]:
        keys = list(_BASE_PERMS)
        try:
            for info, _ in discover_modules():
                m = info.get("name", "")
                if not m:
                    continue
                keys.append(f"module:{m}.view")
                for sub in info.get("submodules", []):
                    keys.append(f"module:{m}/{sub}.view")
        except Exception:
            pass
        keys = sorted(set(keys))
        return keys

    def _build_permissions_ui(self):
        # clear old
        for i in reversed(range(self.perm_grid.count())):
            w = self.perm_grid.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.perm_checks.clear()

        keys = self._discover_permission_keys()
        col = 0
        rowi = 0
        for i, k in enumerate(keys):
            cb = QCheckBox(k)
            self.perm_checks[k] = cb
            self.perm_grid.addWidget(cb, rowi, col)
            rowi += 1
            if rowi > 12:
                rowi = 0
                col += 1

    # ---------------- module access UI ----------------
    def _reload_access_tree(self):
        self.tree.clear()
        role = self._selected_role()
        role_id = role.id if role else None
        rules_map: dict[tuple[str, str], bool] = {}
        if role_id:
            with SessionLocal() as s:
                for ar in s.query(AccessRule).filter(AccessRule.role_id == role_id).all():
                    rules_map[(ar.module_name, ar.submodule_name or "")] = bool(ar.can_view)

        try:
            modules: Iterable[Tuple[dict, object]] = discover_modules()
        except Exception:
            modules = []

        for info, _ in modules:
            mname = info.get("name", "")
            if not mname:
                continue
            mitem = QTreeWidgetItem([mname, ""])
            # make column 1 checkable
            mitem.setFlags(mitem.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            mitem.setData(0, Qt.UserRole, (mname, ""))
            mitem.setCheckState(1, Qt.Checked if rules_map.get((mname, ""), False) else Qt.Unchecked)
            self.tree.addTopLevelItem(mitem)

            for sub in info.get("submodules", []):
                subitem = QTreeWidgetItem([sub, ""])
                subitem.setFlags(subitem.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                subitem.setData(0, Qt.UserRole, (mname, sub))
                subitem.setCheckState(1, Qt.Checked if rules_map.get((mname, sub), False) else Qt.Unchecked)
                mitem.addChild(subitem)

        self.tree.expandAll()

    # ---------------- role CRUD ----------------
    def _add_role(self):
        name, ok = QInputDialog.getText(self, "Add Role", "Role name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        with SessionLocal() as s:
            if s.query(Role).filter(Role.name == name).first():
                QMessageBox.warning(self, "Error", "Role already exists.")
                return
            s.add(Role(name=name))
            s.commit()
        self._reload_roles()

    def _rename_role(self):
        r = self._selected_role()
        if not r:
            return
        name, ok = QInputDialog.getText(self, "Rename Role", "New name:", text=r.name)
        if not ok or not name.strip():
            return
        with SessionLocal() as s:
            obj = s.query(Role).get(r.id)
            if not obj:
                return
            obj.name = name.strip()
            s.commit()
        self._reload_roles()

    def _delete_role(self):
        r = self._selected_role()
        if not r:
            return
        with SessionLocal() as s:
            obj = s.query(Role).get(r.id)
            if not obj:
                return
            s.delete(obj)
            s.commit()
        self._reload_roles()

    # ---------------- load role state ----------------
    def _load_role_detail(self):
        # reset checks
        for cb in self.perm_checks.values():
            cb.setChecked(False)
        self._reload_access_tree()

        r = self._selected_role()
        if not r:
            return

        with SessionLocal() as s:
            rp = s.query(RolePermission).filter(RolePermission.role_id == r.id).all()
            keys = {p.perm.key for p in rp}
            for k, cb in self.perm_checks.items():
                cb.setChecked(k in keys)

    # ---------------- collect + save ----------------
    def _collect_perm_state(self) -> set[str]:
        return {k for k, cb in self.perm_checks.items() if cb.isChecked()}

    def _iterate_tree_items(self):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            yield top
            for j in range(top.childCount()):
                yield top.child(j)

    def _collect_access_state(self) -> list[tuple[str, str, bool]]:
        out: list[tuple[str, str, bool]] = []
        for it in self._iterate_tree_items():
            mname, sub = it.data(0, Qt.UserRole)
            want = it.checkState(1) == Qt.Checked
            out.append((mname, sub or "", want))
        return out

    def _save_perms_clicked(self):
        r = self._selected_role()
        if not r:
            return
        desired = self._collect_perm_state()

        with SessionLocal() as s:
            # ensure Permission rows exist
            perm_map = {p.key: p for p in s.query(Permission).all()}
            for k in desired:
                if k not in perm_map:
                    p = Permission(key=k)
                    s.add(p)
                    s.flush()
                    perm_map[k] = p

            # current links
            cur_links = s.query(RolePermission).filter(RolePermission.role_id == r.id).all()
            cur_keys = {lnk.perm.key for lnk in cur_links}

            # add
            for addk in desired - cur_keys:
                s.add(RolePermission(role_id=r.id, perm_id=perm_map[addk].id))
            # remove
            for lnk in cur_links:
                if lnk.perm.key not in desired:
                    s.delete(lnk)

            s.commit()

        QMessageBox.information(self, "Saved", "Permissions saved.")

    def _save_access_clicked(self):
        r = self._selected_role()
        if not r:
            return
        states = self._collect_access_state()

        with SessionLocal() as s:
            for mname, sub, want in states:
                rule = s.query(AccessRule).filter(
                    AccessRule.role_id == r.id,
                    AccessRule.module_name == mname,
                    AccessRule.submodule_name == (sub or "")
                ).first()
                if want and not rule:
                    s.add(AccessRule(role_id=r.id, module_name=mname, submodule_name=(sub or ""), can_view=True))
                elif want and rule:
                    rule.can_view = True
                elif not want and rule:
                    s.delete(rule)
            s.commit()

        QMessageBox.information(self, "Saved", "Module access saved.")
