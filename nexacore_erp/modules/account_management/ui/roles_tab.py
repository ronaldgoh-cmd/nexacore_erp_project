from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLineEdit,
    QGroupBox, QGridLayout, QCheckBox, QMessageBox, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QSplitter, QInputDialog
)

# FIXED: absolute imports to core
from nexacore_erp.core.database import SessionLocal
from nexacore_erp.core.plugins import discover_modules

from ..models import BaseAcc, Role, Permission, RolePermission, UserRole, AccessRule

_BASE_PERMS = [
    "accounts.manage_users",
    "accounts.manage_roles",
    "modules.install",
]

class RolesAccessTab(QWidget):
    def __init__(self):
        super().__init__()
        split = QSplitter(Qt.Horizontal, self)

        # left: roles list + actions
        left = QWidget()
        lv = QVBoxLayout(left)
        self.list_roles = QListWidget()
        row = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_rename = QPushButton("Rename")
        self.btn_delete = QPushButton("Delete")
        row.addWidget(self.btn_add); row.addWidget(self.btn_rename); row.addWidget(self.btn_delete)
        lv.addWidget(self.list_roles); lv.addLayout(row)

        # right: permissions + module access
        right = QWidget()
        rv = QVBoxLayout(right)

        # permissions group
        grp_perm = QGroupBox("Permissions")
        grid = QGridLayout(grp_perm)
        self.perm_checks: dict[str, QCheckBox] = {}
        col = 0; rowi = 0

        keys = list(_BASE_PERMS)
        for info, _ in discover_modules():
            m = info["name"]
            keys.append(f"module:{m}.view")
            for sub in info.get("submodules", []):
                keys.append(f"module:{m}/{sub}.view")

        keys = sorted(set(keys))
        for i, k in enumerate(keys):
            cb = QCheckBox(k)
            self.perm_checks[k] = cb
            grid.addWidget(cb, rowi, col)
            rowi += 1
            if rowi > 12:
                rowi = 0; col += 1

        # module access tree
        grp_access = QGroupBox("Module Access")
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Module / Submodule", "View"])
        self.tree.setColumnWidth(0, 300)
        rv2 = QVBoxLayout(grp_access); rv2.addWidget(self.tree)

        rv.addWidget(grp_perm); rv.addWidget(grp_access)

        split.addWidget(left); split.addWidget(right)
        lay = QVBoxLayout(self); lay.addWidget(split)

        self.btn_add.clicked.connect(self._add_role)
        self.btn_rename.clicked.connect(self._rename_role)
        self.btn_delete.clicked.connect(self._delete_role)
        self.list_roles.currentItemChanged.connect(lambda *_: self._load_role_detail())

        self._reload_roles()
        self._reload_access_tree()

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

    def _reload_access_tree(self):
        self.tree.clear()
        with SessionLocal() as s:
            role = self._selected_role()
            role_id = role.id if role else None
            rules = { (ar.module_name, ar.submodule_name): ar
                      for ar in s.query(AccessRule).filter(AccessRule.role_id == role_id).all() } if role_id else {}

        for info, _ in discover_modules():
            mname = info["name"]
            mitem = QTreeWidgetItem([mname, ""])
            mitem.setData(0, Qt.UserRole, (mname, ""))
            mitem.setCheckState(1, Qt.Checked if rules.get((mname, "")) and rules[(mname, "")].can_view else Qt.Unchecked)
            self.tree.addTopLevelItem(mitem)
            for sub in info.get("submodules", []):
                subitem = QTreeWidgetItem([sub, ""])
                subitem.setData(0, Qt.UserRole, (mname, sub))
                subitem.setCheckState(1, Qt.Checked if rules.get((mname, sub)) and rules[(mname, sub)].can_view else Qt.Unchecked)
                mitem.addChild(subitem)
        self.tree.expandAll()

    def _add_role(self):
        name, ok = QInputDialog.getText(self, "Add Role", "Role name:")
        if not ok or not name.strip():
            return
        with SessionLocal() as s:
            if s.query(Role).filter(Role.name == name.strip()).first():
                QMessageBox.warning(self, "Error", "Role already exists."); return
            s.add(Role(name=name.strip())); s.commit()
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
            obj.name = name.strip()
            s.commit()
        self._reload_roles()

    def _delete_role(self):
        r = self._selected_role()
        if not r:
            return
        with SessionLocal() as s:
            obj = s.query(Role).get(r.id)
            s.delete(obj)
            s.commit()
        self._reload_roles()

    def _load_role_detail(self):
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

        for k, cb in self.perm_checks.items():
            cb.stateChanged.connect(self._save_perms)
        self.tree.itemChanged.connect(self._save_access)

    def _save_perms(self):
        r = self._selected_role()
        if not r:
            return
        desired = {k for k, cb in self.perm_checks.items() if cb.isChecked()}
        with SessionLocal() as s:
            perm_map = {p.key: p for p in s.query(Permission).all()}
            for k in desired:
                if k not in perm_map:
                    p = Permission(key=k); s.add(p); s.flush(); perm_map[k] = p
            cur = s.query(RolePermission).filter(RolePermission.role_id == r.id).all()
            cur_keys = {c.perm.key for c in cur}
            for addk in desired - cur_keys:
                s.add(RolePermission(role_id=r.id, perm_id=perm_map[addk].id))
            for rm in cur:
                if rm.perm.key not in desired:
                    s.delete(rm)
            s.commit()

    def _save_access(self, it: QTreeWidgetItem, column: int):
        if column != 1:
            return
        r = self._selected_role()
        if not r:
            return
        mname, sub = it.data(0, Qt.UserRole)
        want = it.checkState(1) == Qt.Checked
        with SessionLocal() as s:
            rule = s.query(AccessRule).filter(
                AccessRule.role_id == r.id,
                AccessRule.module_name == mname,
                AccessRule.submodule_name == (sub or "")
            ).first()
            if not rule and want:
                s.add(AccessRule(role_id=r.id, module_name=mname, submodule_name=(sub or ""), can_view=True))
            elif rule:
                if want:
                    rule.can_view = True
                else:
                    s.delete(rule)
            s.commit()
