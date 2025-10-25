from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QCheckBox
from PySide6.QtCore import QSettings

from ..core.auth import authenticate


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NexaCore ERP — Login")

        self.user = QLineEdit(self); self.user.setPlaceholderText("Username")
        self.pw = QLineEdit(self); self.pw.setPlaceholderText("Password"); self.pw.setEchoMode(QLineEdit.Password)

        self.chk_user = QCheckBox("Save user id", self)
        self.chk_pass = QCheckBox("Save password", self)

        self.msg = QLabel("")
        self.btn = QPushButton("Login", self)

        layout = QVBoxLayout(self)
        layout.addWidget(self.user)
        layout.addWidget(self.pw)
        layout.addWidget(self.chk_user)
        layout.addWidget(self.chk_pass)
        layout.addWidget(self.btn)
        layout.addWidget(self.msg)

        self.btn.clicked.connect(self.try_login)

        self.result_user = None
        self._load_saved()

    # settings helpers
    def _settings(self) -> QSettings:
        return QSettings("NexaCore", "ERP")

    def _load_saved(self):
        s = self._settings()
        u = s.value("auth/user", "", type=str)
        p = s.value("auth/pass", "", type=str)
        self.user.setText(u)
        self.pw.setText(p)
        self.chk_user.setChecked(bool(u))
        self.chk_pass.setChecked(bool(p))

    def _persist_selection(self):
        s = self._settings()
        if self.chk_user.isChecked():
            s.setValue("auth/user", self.user.text().strip())
        else:
            s.remove("auth/user")
        if self.chk_pass.isChecked():
            s.setValue("auth/pass", self.pw.text())
        else:
            s.remove("auth/pass")

    def try_login(self):
        u = authenticate(self.user.text(), self.pw.text())
        if u:
            self._persist_selection()
            self.result_user = u
            self.accept()
        else:
            self.msg.setText("Invalid credentials")
