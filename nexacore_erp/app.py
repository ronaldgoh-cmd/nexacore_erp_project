# nexacore_erp/app.py
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from .core.database import init_db
from .core.auth import authenticate, set_current_user, get_current_user
from .ui.login_dialog import LoginDialog
from .ui.main_window import MainWindow

def _login_or_quit(app: QApplication):
    while True:
        dlg = LoginDialog()
        if dlg.exec() != QDialog.Accepted:
            sys.exit(0)

        # Read credentials
        try:
            username, password = dlg.credentials()
        except Exception:
            username = dlg.ed_user.text().strip()
            password = dlg.ed_pass.text()

        username = (username or "").strip()
        password = password or ""
        if not username:
            QMessageBox.warning(None, "Login failed", "Username is required.")
            continue

        u = authenticate(username, password)
        if not u:
            QMessageBox.warning(None, "Login failed", "Invalid username or password, or account is inactive.")
            continue

        set_current_user(u)
        return u

def run_app():
    init_db()  # schema only; does NOT create any 'admin' user

    # High-DPI setup before QApplication
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QGuiApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NexaCore ERP")
    app.setOrganizationName("NexaCore Digital Solutions")
    app.setOrganizationDomain("nexacore.local")
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    _login_or_quit(app)  # sets current user once

    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())
