from __future__ import annotations
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox, QMessageBox,
    QCheckBox, QAbstractItemView, QToolButton, QHeaderView
)

# Absolute imports into core
from nexacore_erp.core.database import SessionLocal
from nexacore_erp.core.models import User

try:
    from nexacore_erp.core.auth import hash_password as _hash
except Exception:
    _hash = None


# ---------- table DDL helpers ----------
def _ensure_user_columns():
    """Make sure users table has email, is_active, password_hash columns."""
    with SessionLocal() as s:
        raw = s.connection().connection
        cur = raw.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {str(r[1]) for r in cur.fetchall()}

        if "email" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "is_active" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
        if "password_hash" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        raw.commit()


def _fetch_users_rows():
    """Read rows using SQL so we can access columns even if not mapped on the ORM model."""
    with SessionLocal() as s:
        raw = s.connection().connection
        cur = raw.cursor()
        cur.execute(
            """
            SELECT id,
                   COALESCE(username,''),
                   COALESCE(email,''),
                   COALESCE(role,'user'),
                   COALESCE(is_active,1),
                   created_at,
                   COALESCE(password_hash,'')
            FROM users
            ORDER BY id ASC
            """
        )
        out = []
        for rid, username, email, role, is_active, created_at, pwd_hash in cur.fetchall():
            out.append({
                "id": int(rid),
                "username": username,
                "email": email,
                "role": role,
                "is_active": bool(is_active),
                "created_at": created_at,
                "password_hash": pwd_hash,
            })
        return out


def _update_user_raw(uid: int, *, email: str | None = None, is_active: bool | None = None):
    with SessionLocal() as s:
        raw = s.connection().connection
        cur = raw.cursor()
        if email is not None:
            cur.execute("UPDATE users SET email=? WHERE id=?", (email, uid))
        if is_active is not None:
            cur.execute("UPDATE users SET is_active=? WHERE id=?", (1 if is_active else 0, uid))
        raw.commit()


def _table_exists(cur, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


# ---------- password display cell (read-only with eye) ----------
class PasswordDisplayCell(QWidget):
    """Shows stored password string masked. Read-only. Eye toggles visibility."""
    def __init__(self, text_value: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(self)
        self.edit.setReadOnly(True)
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setText(text_value or "")
        self.btn = QToolButton(self)
        self.btn.setCheckable(True)
        self.btn.setText("👁")
        self.btn.setToolTip("Show/Hide")
        self.btn.toggled.connect(self._toggle)
        h.addWidget(self.edit, 1)
        h.addWidget(self.btn, 0)

    def _toggle(self, on: bool):
        self.edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)


# ---------- user create/edit dialog ----------
class _UserDialog(QDialog):
    def __init__(self, parent=None, user: User | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit User" if user else "Create User")
        self.user = user
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.ed_username = QLineEdit()
        self.ed_email = QLineEdit()
        self.cb_role = QComboBox()
        self.cb_role.addItems(["user", "admin", "superadmin"])
        self.cb_active = QCheckBox("Active")

        if user:
            self.ed_username.setText(user.username or "")
            self.cb_role.setCurrentText(user.role or "user")
            self.cb_active.setChecked(getattr(user, "is_active", True))
            with SessionLocal() as s:
                raw = s.connection().connection
                cur = raw.cursor()
                cur.execute("SELECT COALESCE(email,''), COALESCE(is_active,1) FROM users WHERE id=?", (user.id,))
                row = cur.fetchone()
                if row:
                    self.ed_email.setText(row[0] or "")
                    self.cb_active.setChecked(bool(row[1]))
        else:
            self.cb_active.setChecked(True)

        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.Password)
        self.ed_password.setPlaceholderText("Set password (leave blank to keep current)")

        form.addRow("Username", self.ed_username)
        form.addRow("Email", self.ed_email)
        form.addRow("Role", self.cb_role)
        form.addRow("Password", self.ed_password)
        form.addRow("", self.cb_active)

        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def values(self):
        return {
            "username": self.ed_username.text().strip(),
            "email": self.ed_email.text().strip(),
            "role": self.cb_role.currentText(),
            "password": self.ed_password.text(),
            "is_active": self.cb_active.isChecked(),
        }


# ---------- Users tab ----------
class UsersTab(QWidget):
    def __init__(self):
        super().__init__()

        _ensure_user_columns()

        root = QHBoxLayout(self)
        left = QWidget(self)
        v = QVBoxLayout(left)

        actions = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_edit = QPushButton("Edit")
        self.btn_toggle = QPushButton("Toggle Active")
        self.btn_delete = QPushButton("Delete")
        actions.addWidget(self.btn_add)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_toggle)
        actions.addWidget(self.btn_delete)
        actions.addStretch(1)
        v.addLayout(actions)

        # Columns: ID(hidden), Username, Password(display), Email, Role, Active, Created
        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Username", "Password", "Email", "Role", "Active", "Created"]
        )
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(False)
        v.addWidget(self.table)

        # panel ~2x wider
        root.addWidget(left, 2)
        root.addStretch(1)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_toggle.clicked.connect(self._toggle_active)
        self.btn_delete.clicked.connect(self._delete)

        self.reload()

    def _selected_row(self) -> int:
        return self.table.currentRow()

    def _selected_user_id(self) -> int | None:
        r = self._selected_row()
        if r < 0:
            return None
        it = self.table.item(r, 0)
        return int(it.text()) if it else None

    def reload(self):
        self.table.setRowCount(0)
        rows = _fetch_users_rows()
        for u in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)

            id_it = QTableWidgetItem(str(u["id"]))
            id_it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, id_it)

            un_it = QTableWidgetItem(u["username"])
            un_it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 1, un_it)

            pwd_cell = PasswordDisplayCell(u["password_hash"])
            self.table.setCellWidget(r, 2, pwd_cell)

            em_it = QTableWidgetItem(u["email"])
            em_it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 3, em_it)

            role_it = QTableWidgetItem(u["role"])
            role_it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 4, role_it)

            act_it = QTableWidgetItem("Yes" if u["is_active"] else "No")
            act_it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 5, act_it)

            cval = u["created_at"]
            if isinstance(cval, datetime):
                c_txt = cval.strftime("%Y-%m-%d %H:%M")
            else:
                try:
                    c_txt = str(cval or "")
                except Exception:
                    c_txt = ""
            cr_it = QTableWidgetItem(c_txt)
            cr_it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 6, cr_it)

        self.table.resizeColumnsToContents()

    # ---------- CRUD ----------
    def _add(self):
        dlg = _UserDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        if not vals["username"]:
            QMessageBox.warning(self, "Error", "Username is required.")
            return

        with SessionLocal() as s:
            if s.query(User).filter(User.username == vals["username"]).first():
                QMessageBox.warning(self, "Error", "Username already exists.")
                return

            u = User(username=vals["username"], role=vals["role"])
            setattr(u, "is_active", vals["is_active"])
            if vals["password"]:
                u.password_hash = _hash(vals["password"]) if _hash else vals["password"]

            s.add(u)
            s.commit()
            uid = u.id

        _update_user_raw(uid, email=vals["email"], is_active=vals["is_active"])
        self.reload()

    def _edit(self):
        uid = self._selected_user_id()
        if not uid:
            return

        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            dlg = _UserDialog(self, u)
            if dlg.exec() != QDialog.Accepted:
                return
            vals = dlg.values()
            if not vals["username"]:
                QMessageBox.warning(self, "Error", "Username is required.")
                return

            u.username = vals["username"]
            u.role = vals["role"]
            setattr(u, "is_active", vals["is_active"])
            if vals["password"]:
                u.password_hash = _hash(vals["password"]) if _hash else vals["password"]
            s.commit()

        _update_user_raw(uid, email=vals["email"], is_active=vals["is_active"])
        self.reload()

    def _toggle_active(self):
        uid = self._selected_user_id()
        if not uid:
            return

        r = self._selected_row()
        cur_txt = self.table.item(r, 5).text() if r >= 0 else "Yes"
        new_state = not (cur_txt.strip().lower() == "yes")

        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            setattr(u, "is_active", new_state)
            s.commit()

        _update_user_raw(uid, is_active=new_state)
        self.reload()

    def _delete(self):
        uid = self._selected_user_id()
        if not uid:
            return

        resp = QMessageBox.question(
            self,
            "Confirm Deletion",
            "This will permanently delete this user and all account information. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        with SessionLocal() as s:
            raw = s.connection().connection
            cur = raw.cursor()

            # Best-effort cleanup of related tables if present
            related = [
                ("user_settings", "user_id"),
                ("user_roles", "user_id"),
                ("user_role_mappings", "user_id"),
                ("api_tokens", "user_id"),
                ("audit_logs", "user_id"),
                ("sessions", "user_id"),
            ]
            for tbl, col in related:
                if _table_exists(cur, tbl):
                    cur.execute(f"DELETE FROM {tbl} WHERE {col}=?", (uid,))

            # Finally delete the user
            cur.execute("DELETE FROM users WHERE id=?", (uid,))
            raw.commit()

        self.reload()
