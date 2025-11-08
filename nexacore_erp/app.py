# nexacore_erp/app.py
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from .core.database import init_db
from .core.auth import ensure_bootstrap_superadmin
from .ui.main_window import MainWindow

def run_app():
    # DB and default admin
    init_db()
    ensure_bootstrap_superadmin()  # user=admin / pass=admin123

    # High-DPI normalization (must be set before creating QApplication)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QGuiApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Qt app
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NexaCore ERP")
    app.setOrganizationName("NexaCore Digital Solutions")
    app.setOrganizationDomain("nexacore.local")

    # Use a consistent cross-platform base style to avoid checkbox rendering differences
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())
