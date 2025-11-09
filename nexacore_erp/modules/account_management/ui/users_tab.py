from __future__ import annotations
from datetime import datetime
import base64
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox, QMessageBox,
    QAbstractItemView, QToolButton, QStyle, QCheckBox, QLabel, QFrame, QHeaderView
)

# Absolute imports into core
from nexacore_erp.core.database import SessionLocal
from nexacore_erp.core.models import User

try:
    from nexacore_erp.core.auth import hash_password as _hash
except Exception:
    _hash = None

# ---------- optional encryption for reveal ----------
def _key_dir() -> Path:
    return Path.home() / ".nexacore_erp"
def _key_path() -> Path:
    return _key_dir() / "secret.key"

def _load_or_create_key() -> Optional[bytes]:
    try:
        from cryptography.fernet import Fernet  # noqa
    except Exception:
        return None
    _key_dir().mkdir(parents=True, exist_ok=True)
    p = _key_path()
    if p.exists():
        return p.read_bytes()
    from cryptography.fernet import Fernet  # type: ignore
    k = Fernet.generate_key()
    p.write_bytes(k)
    return k

_ENC_KEY = _load_or_create_key()

def _encrypt_for_view(plain: str) -> bytes:
    if not plain:
        return b""
    if _ENC_KEY:
        from cryptography.fernet import Fernet  # type: ignore
        return Fernet(_ENC_KEY).encrypt(plain.encode("utf-8"))
    return base64.b64encode(plain.encode("utf-8"))

def _decrypt_for_view(blob: bytes | str) -> str:
    if not blob:
        return ""
    data = blob if isinstance(blob, (bytes, bytearray)) else blob.encode("utf-8")
    if _ENC_KEY:
        try:
            from cryptography.fernet import Fernet  # type: ignore
            return Fernet(_ENC_KEY).decrypt(data).decode("utf-8")
        except Exception:
            return ""
    try:
        return base64.b64decode(data).decode("utf-8")
    except Exception:
        return ""

# ---------- small widgets ----------
class _PasswordCell(QWidget):
    def __init__(self, get_plain_callable):
        super().__init__()
        self._getter = get_plain_callable
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.ed = QLineEdit(self)
        self.ed.setReadOnly(True)
        self.ed.setEchoMode(QLineEdit.Password)
        self.ed.setText(self._getter() or "")
        self.btn = QToolButton(self)
        self._icon_eye = self.style().standardIcon(QStyle.SP_DesktopIcon)
        self._icon_eye_off = self.style().standardIcon(QStyle.SP_DialogNoButton)
        self.btn.setIcon(self._icon_eye)
        self.btn.setToolTip("Show/Hide")
        self.btn.clicked.connect(self._toggle)
        lay.addWidget(self.ed)
        lay.addWidget(self.btn)

    def _toggle(self):
        if self.ed.echoMode() == QLineEdit.Password:
            self.ed.setText(self._getter() or "")
            self.ed.setEchoMode(QLineEdit.Normal)
            self.btn.setIcon(self._icon_eye_off)
        else:
            self.ed.setEchoMode(QLineEdit.Password)
            self.btn.setIcon(self._icon_eye)

# ---------- dialogs ----------
class _UserDialog(QDialog):
    """Create or edit user metadata. Edit mode does not touch password."""
    def __init__(self, parent=None, user: User | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit User" if user else "Create User")
        self.user = user
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.ed_username = QLineEdit()
        self.ed_email = QLineEdit()
        self.cb_role = QComboBox(); self.cb_role.addItems(["user", "admin", "superadmin"])
        self.cb_active = QCheckBox("Active")
        self.cb_verified = QCheckBox("Verified")

        if user:
            self.ed_username.setText(user.username or "")
            self.ed_email.setText(getattr(user, "email", "") or "")
            idx = self.cb_role.findText(user.role or "user")
            if idx >= 0:
                self.cb_role.setCurrentIndex(idx)
            self.cb_active.setChecked(getattr(user, "is_active", True))
            self.cb_verified.setChecked(getattr(user, "is_verified", False))
        else:
            self.cb_active.setChecked(True)
            self.cb_verified.setChecked(False)

        form.addRow("Username", self.ed_username)
        form.addRow("Email", self.ed_email)
        form.addRow("Role", self.cb_role)
        form.addRow("", self.cb_active)
        form.addRow("", self.cb_verified)

        if not user:
            self.ed_password = QLineEdit(); self.ed_password.setEchoMode(QLineEdit.Password)
            self.ed_password2 = QLineEdit(); self.ed_password2.setEchoMode(QLineEdit.Password)
            form.addRow("Password", self.ed_password)
            form.addRow("Repeat Password", self.ed_password2)

        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def values(self):
        out = {
            "username": self.ed_username.text().strip(),
            "email": self.ed_email.text().strip(),
            "role": self.cb_role.currentText(),
            "is_active": self.cb_active.isChecked(),
            "is_verified": self.cb_verified.isChecked(),
        }
        if hasattr(self, "ed_password"):
            out["password"] = self.ed_password.text()
            out["password2"] = self.ed_password2.text()
        return out

class _ResetPasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reset Password")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.p1 = QLineEdit(); self.p1.setEchoMode(QLineEdit.Password)
        self.p2 = QLineEdit(); self.p2.setEchoMode(QLineEdit.Password)
        form.addRow("New password", self.p1)
        form.addRow("Repeat password", self.p2)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._check); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _check(self):
        a, b = self.p1.text(), self.p2.text()
        if not a:
            QMessageBox.warning(self, "Error", "Password cannot be empty."); return
        if a != b:
            QMessageBox.warning(self, "Error", "Passwords do not match."); return
        self.accept()

    def value(self) -> str:
        return self.p1.text()

# ---------- migrations ----------
def _ensure_user_columns():
    with SessionLocal() as s:
        raw = s.connection().connection
        cur = raw.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}
        def _add(col, ddl):
            if col not in cols:
                try:
                    cur.execute(f"ALTER TABLE users ADD COLUMN {ddl}")
                except Exception:
                    pass
        _add("email", "email TEXT")
        _add("is_active", "is_active INTEGER DEFAULT 1")
        _add("is_verified", "is_verified INTEGER DEFAULT 0")
        _add("password_enc", "password_enc BLOB")
        raw.commit()

# ---------- main widget ----------
class UsersTab(QWidget):
    def __init__(self):
        super().__init__()
        _ensure_user_columns()

        v = QVBoxLayout(self)

        actions = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_edit = QPushButton("Edit")
        self.btn_reset = QPushButton("Reset Password")
        self.btn_delete = QPushButton("Delete")
        actions.addWidget(self.btn_add)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_reset)
        actions.addWidget(self.btn_delete)
        actions.addStretch(1)
        v.addLayout(actions)

        # ID | Username | Email | Role | Active | Verified | Password | Created
        self.table = QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Username", "Email", "Role", "Active", "Verified", "Password", "Created"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        hdr = self.table.horizontalHeader()
        for i in range(8):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(False)
        v.addWidget(self.table)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_reset.clicked.connect(self._reset)
        self.btn_delete.clicked.connect(self._delete)

        self.reload()

    # ---- utils ----
    def _selected_user_id(self) -> int | None:
        r = self.table.currentRow()
        if r < 0:
            return None
        it = self.table.item(r, 0)
        return int(it.text()) if it else None

    def _get_password_plain_for(self, uid: int) -> str:
        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return ""
            blob = getattr(u, "password_enc", None) or b""
            return _decrypt_for_view(blob)

    # ---- core ----
    def reload(self):
        self.table.setRowCount(0)
        with SessionLocal() as s:
            rows = s.query(User).order_by(User.id.asc()).all()
            for u in rows:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(str(u.id)))
                self.table.setItem(r, 1, QTableWidgetItem(u.username or ""))
                self.table.setItem(r, 2, QTableWidgetItem(getattr(u, "email", "") or ""))
                self.table.setItem(r, 3, QTableWidgetItem(u.role or "user"))

                active_cb = QCheckBox(); active_cb.setChecked(getattr(u, "is_active", True))
                active_cb.stateChanged.connect(lambda _=None, uid=u.id, cb=active_cb: self._toggle_active(uid, cb.isChecked()))
                self.table.setCellWidget(r, 4, active_cb)

                verified_cb = QCheckBox(); verified_cb.setChecked(getattr(u, "is_verified", False))
                verified_cb.stateChanged.connect(lambda _=None, uid=u.id, cb=verified_cb: self._toggle_verified(uid, cb.isChecked()))
                self.table.setCellWidget(r, 5, verified_cb)

                cell = _PasswordCell(lambda uid=u.id: self._get_password_plain_for(uid))
                self.table.setCellWidget(r, 6, cell)

                created = getattr(u, "created_at", None)
                self.table.setItem(
                    r, 7,
                    QTableWidgetItem(created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else "")
                )

    # ---- actions ----
    def _add(self):
        dlg = _UserDialog(self, None)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        if not vals["username"]:
            QMessageBox.warning(self, "Error", "Username is required."); return
        if not vals.get("password"):
            QMessageBox.warning(self, "Error", "Password is required."); return
        if vals["password"] != vals.get("password2", ""):
            QMessageBox.warning(self, "Error", "Passwords do not match."); return

        with SessionLocal() as s:
            if s.query(User).filter(User.username == vals["username"]).first():
                QMessageBox.warning(self, "Error", "Username already exists."); return
            u = User(username=vals["username"], role=vals["role"])
            setattr(u, "email", vals["email"])
            setattr(u, "is_active", vals["is_active"])
            setattr(u, "is_verified", vals["is_verified"])
            phash = _hash(vals["password"]) if _hash else vals["password"]
            setattr(u, "password_hash", phash)
            setattr(u, "password_enc", _encrypt_for_view(vals["password"]))
            s.add(u); s.commit()
        self.reload()

    def _edit(self):
        uid = self._selected_user_id()
        if not uid:
            return
        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            dlg = _UserDialog(self, u)  # no password fields in edit
            if dlg.exec() != QDialog.Accepted:
                return
            vals = dlg.values()
            if not vals["username"]:
                QMessageBox.warning(self, "Error", "Username is required."); return
            u.username = vals["username"]
            u.role = vals["role"]
            setattr(u, "email", vals["email"])
            setattr(u, "is_active", vals["is_active"])
            setattr(u, "is_verified", vals["is_verified"])
            s.commit()
        self.reload()

    def _reset(self):
        uid = self._selected_user_id()
        if not uid:
            return
        dlg = _ResetPasswordDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        newpwd = dlg.value()
        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            phash = _hash(newpwd) if _hash else newpwd
            setattr(u, "password_hash", phash)
            setattr(u, "password_enc", _encrypt_for_view(newpwd))
            s.commit()
        QMessageBox.information(self, "Done", "Password reset.")
        self.reload()

    def _delete(self):
        uid = self._selected_user_id()
        if not uid:
            return
        resp = QMessageBox.question(
            self, "Confirm delete",
            "Delete this user and all related account information?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return
        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            s.delete(u); s.commit()
        self.reload()

    def _toggle_active(self, uid: int, flag: bool):
        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            setattr(u, "is_active", bool(flag))
            s.commit()

    def _toggle_verified(self, uid: int, flag: bool):
        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            setattr(u, "is_verified", bool(flag))
            s.commit()
