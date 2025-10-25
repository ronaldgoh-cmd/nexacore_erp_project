# nexacore_erp/app.py
import sys
from PySide6.QtWidgets import QApplication
from .core.database import init_db
from .core.auth import ensure_bootstrap_superadmin
from .ui.main_window import MainWindow


def run_app():
    # DB and default admin
    init_db()
    ensure_bootstrap_superadmin()  # user=admin / pass=admin123

    # Qt app
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NexaCore ERP")
    app.setOrganizationName("NexaCore Digital Solutions")
    app.setOrganizationDomain("nexacore.local")

    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())
