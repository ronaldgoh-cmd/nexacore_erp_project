# nexacore_erp/modules/account_management/ui/roles_tab.py
from __future__ import annotations
from typing import Iterable, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QGroupBox, QGridLayout, QCheckBox, QMessageBox, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem, QSplitter, QInputDialog, QDialogButtonBox
)

from nexacore_erp.core.database import SessionLocal
from nexacore_erp.core.plugins import discover_modules
from ..models import Role, Permission, RolePermission, UserRole, AccessRule  # noqa: F401

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

        # right: permissions + module access + footer
        right = QWidget()
        rv = QVBoxLayout(right)

        grp_perm = QGroupBox("Permissions")
        self.perm_grid = QGridLayout(grp_perm)
        self.perm_checks: dict[str, QCheckBox] = {}

        grp_access = QGroupBox("Module & Sub-tab Access")
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Module / Submodule", "View"])
        self.tree.setColumnWidth(0, 320)
        lay_access = QVBoxLayout(grp_access); lay_access.addWidget(self.tree)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Reset)
        self.btn_save = bb.button(QDialogButtonBox.Save)
        self.btn_reset = bb.button(QDialogButtonBox.Reset)

        rv.addWidget(grp_perm)
        rv.addWidget(grp_access)
        rv.addWidget(bb)

        split.addWidget(left); split.addWidget(right)
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1)
        lay = QVBoxLayout(self); lay.addWidget(split)

        # wire
        self.btn_add.clicked.connect(self._add_role)
        self.btn_rename.clicked.connect(self._rename_role)
        self.btn_delete.clicked.connect(self._delete_role)
        self.list_roles.currentItemChanged.connect(lambda *_: self._load_role_detail())
        self.btn_save.clicked.connect(self._save_all)
        self.btn_reset.clicked.connect(self._load_role_detail)

        self._build_permissions_ui()
        self._reload_roles()
        self._reload_access_tree()

    # roles
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

    def _add_role(self):
        name, ok = QInputDialog.getText(self, "Add Role", "Role name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        with SessionLocal() as s:
            if s.query(Role).filter(Role.name == name).first():
                QMessageBox.warning(self, "Error", "Role already exists.")
                return
            s.add(Role(name=name)); s.commit()
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
        if QMessageBox.question(self, "Confirm", f"Delete role '{r.name}'?") != QMessageBox.Yes:
            return
        with SessionLocal() as s:
            obj = s.query(Role).get(r.id)
            if not obj:
                return
            s.query(RolePermission).filter(RolePermission.role_id == r.id).delete()
            s.query(AccessRule).filter(AccessRule.role_id == r.id).delete()
            s.query(UserRole).filter(UserRole.role_id == r.id).delete()
            s.delete(obj); s.commit()
        self._reload_roles()

    # permissions UI
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
        return sorted(set(keys))

    def _build_permissions_ui(self):
        # clear
        for i in reversed(range(self.perm_grid.count())):
            w = self.perm_grid.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.perm_checks.clear()

        keys = self._discover_permission_keys()
        col = 0; rowi = 0
        for k in keys:
            cb = QCheckBox(k)
            self.perm_checks[k] = cb
            self.perm_grid.addWidget(cb, rowi, col)
            rowi += 1
            if rowi > 12:
                rowi = 0; col += 1

    # module access tree
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

    def _load_role_detail(self):
        # reset checks
        for cb in self.perm_checks.values():
            cb.setChecked(False)
        self._reload_access_tree()

        r = self._selected_role()
        if not r:
            return

        with SessionLocal() as s:
            # role permissions -> keys
            rp = s.query(RolePermission).filter(RolePermission.role_id == r.id).all()
            if rp:
                # robust map id->key avoids relying on a relationship property
                perm_ids = [x.perm_id for x in rp]
                pkeys = {p.id: p.key for p in s.query(Permission).filter(Permission.id.in_(perm_ids)).all()}
                for x in rp:
                    key = pkeys.get(x.perm_id)
                    if key and key in self.perm_checks:
                        self.perm_checks[key].setChecked(True)

    # collect
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

    # save all
    def _save_all(self):
        r = self._selected_role()
        if not r:
            return

        desired_perm = self._collect_perm_state()
        desired_rules = self._collect_access_state()

        with SessionLocal() as s:
            # ensure permissions
            perm_map = {p.key: p for p in s.query(Permission).all()}
            for k in desired_perm:
                if k not in perm_map:
                    p = Permission(key=k); s.add(p); s.flush(); perm_map[k] = p

            # current role-permission links
            cur_links = s.query(RolePermission).filter(RolePermission.role_id == r.id).all()
            id2key = {p.id: p.key for p in s.query(Permission).all()}
            cur_keys = {id2key.get(lnk.perm_id) for lnk in cur_links}
            cur_keys.discard(None)

            # add missing
            for k in desired_perm - cur_keys:
                s.add(RolePermission(role_id=r.id, perm_id=perm_map[k].id))
            # remove extra
            for lnk in cur_links:
                k = id2key.get(lnk.perm_id)
                if k and k not in desired_perm:
                    s.delete(lnk)

            # access rules
            cur_rules = {(ar.module_name, ar.submodule_name or ""): ar
                         for ar in s.query(AccessRule).filter(AccessRule.role_id == r.id).all()}
            # set desired
            want_set = {(m, sname) for (m, sname, want) in desired_rules if want}
            for key in want_set:
                if key in cur_rules:
                    cur_rules[key].can_view = True
                else:
                    m, sub = key
                    s.add(AccessRule(role_id=r.id, module_name=m, submodule_name=sub, can_view=True))
            # remove undesired
            for key, ar in list(cur_rules.items()):
                if key not in want_set:
                    s.delete(ar)

            s.commit()

        QMessageBox.information(self, "Saved", "Permissions and access saved.")
