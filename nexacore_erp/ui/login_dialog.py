# ui/login_dialog.py
from __future__ import annotations
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QDialogButtonBox, QWidget, QFormLayout
)
from PySide6.QtGui import QPixmap

class CreateAccountDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Create Account")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.ed_user = QLineEdit()
        self.ed_email = QLineEdit()
        self.ed_pass = QLineEdit(); self.ed_pass.setEchoMode(QLineEdit.Password)
        self.ed_pass2 = QLineEdit(); self.ed_pass2.setEchoMode(QLineEdit.Password)
        form.addRow("Username", self.ed_user)
        form.addRow("Email", self.ed_email)
        form.addRow("Password", self.ed_pass)
        form.addRow("Repeat Password", self.ed_pass2)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # Leave handlers empty for now
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

class LoginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, logo_pixmap: QPixmap | None = None):
        super().__init__(parent)
        self.setWindowTitle("NexaCore — Sign in")
        self.settings = QSettings("NexaCore", "ERP")

        root = QVBoxLayout(self)
        # Header with centered logo
        self.logo = QLabel()
        self.logo.setMinimumSize(72, 72)
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setScaledContents(True)
        if logo_pixmap:
            self.logo.setPixmap(logo_pixmap)
        root.addWidget(self.logo, alignment=Qt.AlignCenter)

        # Form
        form = QFormLayout()
        self.ed_user = QLineEdit(); self.ed_user.setPlaceholderText("Username")
        self.ed_pass = QLineEdit(); self.ed_pass.setEchoMode(QLineEdit.Password); self.ed_pass.setPlaceholderText("Password")
        form.addRow("Username", self.ed_user)
        form.addRow("Password", self.ed_pass)
        root.addLayout(form)

        # Remember on this PC
        chk_row = QHBoxLayout()
        self.cb_user = QCheckBox("Remember username on this PC")
        self.cb_pass = QCheckBox("Remember password on this PC")
        chk_row.addWidget(self.cb_user)
        chk_row.addWidget(self.cb_pass)
        chk_row.addStretch(1)
        root.addLayout(chk_row)

        # Footer buttons
        btn_row = QHBoxLayout()
        self.btn_create = QPushButton("Create Account")
        self.btn_create.clicked.connect(self._open_create_account)
        btn_row.addWidget(self.btn_create)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_login_clicked)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self._load_cached_fields()

    # Public API you likely already call:
    def credentials(self) -> tuple[str, str]:
        return self.ed_user.text().strip(), self.ed_pass.text()

    # ----- internals
    def _load_cached_fields(self) -> None:
        if self.settings.value("login/remember_user", False, bool):
            self.ed_user.setText(self.settings.value("login/username", "", str))
            self.cb_user.setChecked(True)
        if self.settings.value("login/remember_pass", False, bool):
            self.ed_pass.setText(self.settings.value("login/password", "", str))
            self.cb_pass.setChecked(True)

    def _cache_now(self) -> None:
        if self.cb_user.isChecked():
            self.settings.setValue("login/remember_user", True)
            self.settings.setValue("login/username", self.ed_user.text().strip())
        else:
            self.settings.setValue("login/remember_user", False)
            self.settings.remove("login/username")

        if self.cb_pass.isChecked():
            self.settings.setValue("login/remember_pass", True)
            self.settings.setValue("login/password", self.ed_pass.text())
        else:
            self.settings.setValue("login/remember_pass", False)
            self.settings.remove("login/password")

    def _on_login_clicked(self) -> None:
        # Do not change your existing auth flow; only cache decisions.
        self._cache_now()
        self.accept()

    def _open_create_account(self) -> None:
        dlg = CreateAccountDialog(self)
        dlg.exec()
