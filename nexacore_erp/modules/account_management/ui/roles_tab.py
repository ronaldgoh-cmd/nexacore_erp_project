# --- DROP-IN REPLACEMENT: class RolesAccessTab ---
from __future__ import annotations
import re
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

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    return re.sub(r"\s+", " ", s)

def _perm_key(module_name: str, submodule_name: str | None = None, tab_name: str | None = None) -> str:
    m = _norm(module_name)
    s = _norm(submodule_name or "")
    t = _norm(tab_name or "")
    if t:
        sub_part = s or "__module__"
        return f"module:{m}/{sub_part}/{t}.view"
    if s:
        return f"module:{m}/{s}.view"
    return f"module:{m}.view"

def _manifest_submodules(info: dict) -> list[str]:
    out: list[str] = []
    for entry in info.get("submodules", []) or []:
        name = ""
        if isinstance(entry, str):
            name = entry
        elif isinstance(entry, dict):
            name = entry.get("name") or entry.get("label") or entry.get("title") or ""
        if isinstance(name, str):
            name = name.strip()
        else:
            name = str(name).strip()
        if name:
            out.append(name)
    return out


def _manifest_tab_map(info: dict) -> dict[str, list[str]]:
    raw = info.get("tab_manifest") or {}
    out: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return out
    for key, tabs in raw.items():
        if isinstance(key, str):
            skey = key.strip()
        else:
            skey = str(key).strip()
        if not skey:
            continue
        if isinstance(tabs, (list, tuple)):
            cleaned = []
            for tab in tabs:
                if isinstance(tab, str):
                    t = tab.strip()
                else:
                    t = str(tab).strip()
                if t:
                    cleaned.append(t)
            if cleaned:
                out[skey] = cleaned
    return out


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

        # right: permissions + access tree + footer
        right = QWidget()
        rv = QVBoxLayout(right)

        grp_perm = QGroupBox("Permissions")
        self.perm_grid = QGridLayout(grp_perm)
        self.perm_checks: dict[str, QCheckBox] = {}

        grp_access = QGroupBox("Module, Submodule & Tab Access")
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Module / Submodule / Tab", "View"])
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 80)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.itemChanged.connect(self._on_tree_item_changed)
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

    # ---------------- Roles ----------------
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

    # --------------- Permissions UI ---------------
    def _discover_permission_keys(self) -> list[str]:
        keys = list(_BASE_PERMS)
        try:
            for info, _ in discover_modules():
                m = info.get("name", "")
                if not m:
                    continue
                keys.append(_perm_key(m))  # normalized module-level view
                tab_map = _manifest_tab_map(info)
                for tab in tab_map.get("__module__", []):
                    keys.append(_perm_key(m, None, tab))
                for sub in _manifest_submodules(info):
                    keys.append(_perm_key(m, sub))
                    for tab in tab_map.get(sub, []):
                        keys.append(_perm_key(m, sub, tab))
        except Exception:
            pass
        # Keep only unique
        out = sorted(set(keys))
        return out

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

    # --------------- Access tree ---------------
    def _reload_access_tree(self):
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            role = self._selected_role()
            role_id = role.id if role else None
            rules_map: dict[tuple[str, str, str], bool] = {}
            if role_id:
                with SessionLocal() as s:
                    for ar in s.query(AccessRule).filter(AccessRule.role_id == role_id).all():
                        key = (
                            (ar.module_name or "").strip(),
                            (ar.submodule_name or "").strip(),
                            (ar.tab_name or "").strip(),
                        )
                        rules_map[key] = bool(ar.can_view)

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
                mitem.setData(0, Qt.UserRole, (mname, "", ""))

                # children first
                any_child = False
                tab_map = _manifest_tab_map(info)

                # module-level tabs (no submodule)
                for tab in tab_map.get("__module__", []):
                    tabitem = QTreeWidgetItem([tab, ""])
                    tabitem.setFlags(tabitem.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    tabitem.setData(0, Qt.UserRole, (mname, "", tab))
                    tab_state = Qt.Checked if rules_map.get((mname, "", tab), False) else Qt.Unchecked
                    tabitem.setCheckState(1, tab_state)
                    mitem.addChild(tabitem)
                    any_child = True

                for sub in _manifest_submodules(info):
                    subitem = QTreeWidgetItem([sub, ""])
                    subitem.setFlags(subitem.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    subitem.setData(0, Qt.UserRole, (mname, sub, ""))

                    # add tabs under this submodule
                    for tab in tab_map.get(sub, []):
                        tabitem = QTreeWidgetItem([tab, ""])
                        tabitem.setFlags(tabitem.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                        tabitem.setData(0, Qt.UserRole, (mname, sub, tab))
                        tab_state = Qt.Checked if rules_map.get((mname, sub, tab), False) else Qt.Unchecked
                        tabitem.setCheckState(1, tab_state)
                        subitem.addChild(tabitem)

                    # submodule state: explicit rule wins; otherwise derive from children
                    if rules_map.get((mname, sub, ""), False):
                        sub_state = Qt.Checked
                    elif subitem.childCount():
                        child_states = [subitem.child(i).checkState(1) for i in range(subitem.childCount())]
                        if child_states and all(st == Qt.Checked for st in child_states):
                            sub_state = Qt.Checked
                        elif any(st == Qt.Checked for st in child_states):
                            sub_state = Qt.PartiallyChecked
                        else:
                            sub_state = Qt.Unchecked
                    else:
                        sub_state = Qt.Unchecked
                    subitem.setCheckState(1, sub_state)
                    mitem.addChild(subitem)
                    any_child = True

                # parent state: explicit rule wins, else reflect children
                if rules_map.get((mname, "", ""), False):
                    mstate = Qt.Checked
                elif any_child:
                    states = [mitem.child(i).checkState(1) for i in range(mitem.childCount())]
                    if states and all(st == Qt.Checked for st in states):
                        mstate = Qt.Checked
                    elif any(st == Qt.Checked for st in states):
                        mstate = Qt.PartiallyChecked
                    else:
                        mstate = Qt.Unchecked
                else:
                    mstate = Qt.Unchecked
                mitem.setCheckState(1, mstate)

                self.tree.addTopLevelItem(mitem)

            self.tree.expandAll()
        finally:
            self.tree.blockSignals(False)

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 1:
            return
        self.tree.blockSignals(True)
        try:
            state = item.checkState(1)
            # cascade to children
            for i in range(item.childCount()):
                item.child(i).setCheckState(1, state)
            # roll up to parents (tri-state)
            self._update_parent_state(item)
        finally:
            self.tree.blockSignals(False)

    def _update_parent_state(self, item: QTreeWidgetItem):
        parent = item.parent()
        while parent:
            checked = 0
            unchecked = 0
            for i in range(parent.childCount()):
                st = parent.child(i).checkState(1)
                if st == Qt.Checked:
                    checked += 1
                elif st == Qt.Unchecked:
                    unchecked += 1
            if checked and unchecked:
                parent.setCheckState(1, Qt.PartiallyChecked)
            elif checked and not unchecked:
                parent.setCheckState(1, Qt.Checked)
            else:
                parent.setCheckState(1, Qt.Unchecked)
            item = parent
            parent = parent.parent()

    # --------------- Load role detail ---------------
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
            if not rp:
                return
            perm_ids = [x.perm_id for x in rp]
            pkeys = {p.id: p.key for p in s.query(Permission).filter(Permission.id.in_(perm_ids)).all()}
            for x in rp:
                raw = pkeys.get(x.perm_id)
                if not raw:
                    continue
                # accept exact or normalized
                key = raw
                if key not in self.perm_checks:
                    # normalize legacy keys to new normalized form
                    # e.g. "module:Salary Management/Salary Review.view" -> "module:salary management/salary review.view"
                    m = re.match(r"^module:(.+?)(?:/(.+?))?(?:/(.+?))?\.view$", raw.strip(), flags=re.IGNORECASE)
                    if m:
                        key = _perm_key(m.group(1), m.group(2), m.group(3))
                if key in self.perm_checks:
                    self.perm_checks[key].setChecked(True)

    # --------------- Collect + Save ---------------
    def _collect_perm_state(self) -> set[str]:
        return {k for k, cb in self.perm_checks.items() if cb.isChecked()}

    def _iterate_tree_items(self):
        def walk(item: QTreeWidgetItem):
            yield item
            for idx in range(item.childCount()):
                yield from walk(item.child(idx))

        for i in range(self.tree.topLevelItemCount()):
            yield from walk(self.tree.topLevelItem(i))

    def _collect_access_state(self) -> list[tuple[str, str, str, bool | None]]:
        out: list[tuple[str, str, str, bool | None]] = []
        for it in self._iterate_tree_items():
            data = it.data(0, Qt.UserRole)
            if not data:
                continue
            if isinstance(data, tuple) and len(data) == 3:
                mname, sub, tab = data
            else:
                continue
            st = it.checkState(1)
            if st == Qt.Checked:
                want: bool | None = True
            elif st == Qt.Unchecked:
                want = False
            else:
                want = None
            out.append(((mname or ""), (sub or ""), (tab or ""), want))
        return out

    def _save_all(self):
        r = self._selected_role()
        if not r:
            return

        desired_perm = self._collect_perm_state()
        desired_rules = self._collect_access_state()

        with SessionLocal() as s:
            # ensure Permission rows exist
            perm_map = {p.key: p for p in s.query(Permission).all()}
            for k in desired_perm:
                if k not in perm_map:
                    p = Permission(key=k); s.add(p); s.flush(); perm_map[k] = p

            # current links
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
            cur_rules = {
                (
                    (ar.module_name or "").strip(),
                    (ar.submodule_name or "").strip(),
                    (ar.tab_name or "").strip(),
                ): ar
                for ar in s.query(AccessRule).filter(AccessRule.role_id == r.id).all()
            }

            normalized_rules: dict[tuple[str, str, str], bool] = {}
            for m, sub, tab, want in desired_rules:
                nm = (m or "").strip()
                ns = (sub or "").strip()
                nt = (tab or "").strip()
                if not nm or want is None:
                    continue
                normalized_rules[(nm, ns, nt)] = bool(want)

            # upsert desired states (True and False)
            for key, want in normalized_rules.items():
                if key in cur_rules:
                    cur_rules[key].can_view = want
                else:
                    m, sub, tab = key
                    s.add(
                        AccessRule(
                            role_id=r.id,
                            module_name=m,
                            submodule_name=sub,
                            tab_name=tab,
                            can_view=want,
                        )
                    )

            # delete stale rules (e.g. when state becomes indeterminate/partial)
            for key, ar in list(cur_rules.items()):
                if key not in normalized_rules:
                    s.delete(ar)

            s.commit()

        QMessageBox.information(self, "Saved", "Permissions and access saved.")
# --- END DROP-IN REPLACEMENT ---
