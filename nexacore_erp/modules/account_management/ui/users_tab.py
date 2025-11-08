from __future__ import annotations
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox, QMessageBox,
    QCheckBox, QInputDialog, QAbstractItemView
)

# Absolute imports into core
from nexacore_erp.core.database import SessionLocal
from nexacore_erp.core.models import User

try:
    from nexacore_erp.core.auth import hash_password as _hash
except Exception:
    _hash = None


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
            self.ed_email.setText(getattr(user, "email", "") or "")
            idx = self.cb_role.findText(user.role or "user")
            if idx >= 0:
                self.cb_role.setCurrentIndex(idx)
            self.cb_active.setChecked(getattr(user, "is_active", True))
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


class UsersTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)

        actions = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_edit = QPushButton("Edit")
        self.btn_reset = QPushButton("Reset Password")
        self.btn_toggle = QPushButton("Toggle Active")
        actions.addWidget(self.btn_add)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_reset)
        actions.addWidget(self.btn_toggle)
        actions.addStretch(1)
        v.addLayout(actions)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["ID", "Username", "Email", "Role", "Active", "Created"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)          # FIX
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)           # FIX
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_reset.clicked.connect(self._reset)
        self.btn_toggle.clicked.connect(self._toggle_active)

        self.reload()

    def _selected_user_id(self) -> int | None:
        r = self.table.currentRow()
        if r < 0:
            return None
        return int(self.table.item(r, 0).text())

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
                self.table.setItem(r, 4, QTableWidgetItem("Yes" if getattr(u, "is_active", True) else "No"))
                created = getattr(u, "created_at", None)
                self.table.setItem(
                    r, 5,
                    QTableWidgetItem(created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else "")
                )

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
            setattr(u, "email", vals["email"])
            setattr(u, "is_active", vals["is_active"])
            if vals["password"]:
                u.password_hash = _hash(vals["password"]) if _hash else vals["password"]
            s.add(u)
            s.commit()
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
            setattr(u, "email", vals["email"])
            setattr(u, "is_active", vals["is_active"])
            if vals["password"]:
                u.password_hash = _hash(vals["password"]) if _hash else vals["password"]
            s.commit()
        self.reload()

    def _reset(self):
        uid = self._selected_user_id()
        if not uid:
            return
        pwd, ok = QInputDialog.getText(self, "New Password", "Enter new password:", QLineEdit.Password)
        if not ok or not pwd:
            return
        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            u.password_hash = _hash(pwd) if _hash else pwd
            s.commit()
        QMessageBox.information(self, "Done", "Password reset.")

    def _toggle_active(self):
        uid = self._selected_user_id()
        if not uid:
            return
        with SessionLocal() as s:
            u = s.query(User).get(uid)
            if not u:
                return
            setattr(u, "is_active", not getattr(u, "is_active", True))
            s.commit()
        self.reload()
