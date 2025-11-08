from PySide6.QtWidgets import (
    QMainWindow, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSizePolicy, QDialog, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QAbstractItemView, QDialogButtonBox, QDockWidget, QTabWidget, QStatusBar, QMenu,
    QMessageBox
)
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtCore import QTimer, Qt

from ..ui.login_dialog import LoginDialog
from ..ui.company_settings_dialog import CompanySettingsDialog
from ..ui.user_settings_dialog import UserSettingsDialog
from ..ui.about_dialog import AboutDialog
from ..core.database import SessionLocal
from ..core.models import User, UserSettings, ModuleState, CompanySettings
from ..core.plugins import discover_modules
from ..core import themes

from datetime import datetime
from zoneinfo import ZoneInfo
import re


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NexaCore ERP")
        self.resize(1366, 860)

        self.user = None
        self.user_settings = None

        # ---------- Fixed vertical header (always top) ----------
        header = self._build_header_widget()
        self.setMenuWidget(header)

        # ---------- Central tabs ----------
        self.content_tabs = QTabWidget(self)
        self.content_tabs.setTabsClosable(True)
        self.content_tabs.tabCloseRequested.connect(self.content_tabs.removeTab)
        self.setCentralWidget(self.content_tabs)

        # ---------- Navigation dock (left) ----------
        self.nav_dock = QDockWidget("Navigation", self)
        self.nav_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.nav_dock)

        nav_host = QWidget(self)
        nav_host.setObjectName("NavPanel")  # for themed background
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(6)

        self.nav = QTreeWidget(nav_host)
        self.nav.setHeaderHidden(True)
        self.nav.setIndentation(12)
        self.nav.itemClicked.connect(self._open_item)
        self.nav.setObjectName("NavTree")

        nav_layout.addWidget(self.nav, 1)
        self.nav_dock.setWidget(nav_host)

        # ---------- Status bar ----------
        sb = QStatusBar(self)
        self.clock_lbl = QLabel("")
        sb.addPermanentWidget(self.clock_lbl)
        self.setStatusBar(sb)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick_clock)
        self.timer.start(1000)

        # ---------- Flow ----------
        self._login_flow()
        self._rebuild_nav()
        self._refresh_identity()

    def toggle_nav(self):
        vis = self.nav_dock.isVisible()
        self.nav_dock.setVisible(not vis)

    # ===== Header =====
    def _build_header_widget(self) -> QWidget:
        host = QWidget(self)
        host.setObjectName("TopHeader")
        v = QVBoxLayout(host)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        # Section 1: centered fixed title
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        left_sp = QWidget(host); left_sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right_sp = QWidget(host); right_sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.fixed_title = QLabel("NexaCore Digital Solutions", host)
        self.fixed_title.setAlignment(Qt.AlignCenter)
        self.fixed_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        row1.addWidget(left_sp); row1.addWidget(self.fixed_title); row1.addWidget(right_sp)
        v.addLayout(row1)

        # Section 2: logo + company name + line1 + line2 (stacked)
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(10)

        # Centered logo inside its own fixed box
        self.header_logo = QLabel(host)
        self.header_logo.setFixedSize(56, 56)   # fixed box
        self.header_logo.setAlignment(Qt.AlignCenter)
        self.header_logo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.header_logo.setScaledContents(True)

        text_box = QWidget(host)
        tv = QVBoxLayout(text_box)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(0)
        self.header_company = QLabel("", host)
        self.header_company.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.header_detail1 = QLabel("", host)
        self.header_detail1.setStyleSheet("font-size: 12px;")
        self.header_detail2 = QLabel("", host)
        self.header_detail2.setStyleSheet("font-size: 12px;")
        tv.addWidget(self.header_company); tv.addWidget(self.header_detail1); tv.addWidget(self.header_detail2)

        row2.addWidget(self.header_logo, 0, Qt.AlignVCenter)
        row2.addWidget(text_box, 0, Qt.AlignVCenter)
        row2.addStretch(1)
        v.addLayout(row2)

        # Section 3: actions | search
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(12)

        self.company_act_btn = QPushButton("Company Settings", host)
        self.company_act_btn.clicked.connect(self.open_company_settings)
        self.modules_act_btn = QPushButton("Install/Enable Modules", host)
        self.modules_act_btn.clicked.connect(self.open_module_manager)
        self.about_act_btn = QPushButton("About", host)
        self.about_act_btn.clicked.connect(lambda: AboutDialog().exec())
        self.nav_toggle_btn = QPushButton("Toggle Navigation", host)
        self.nav_toggle_btn.clicked.connect(self.toggle_nav)
        row3.addWidget(self.nav_toggle_btn)
        row3.addWidget(self.company_act_btn)
        row3.addWidget(self.modules_act_btn)
        row3.addWidget(self.about_act_btn)

        row3.addSpacing(16)
        self.search_box = QLineEdit(host)
        self.search_box.setPlaceholderText("Search…")
        self.search_box.setFixedWidth(280)
        row3.addWidget(self.search_box)

        row3.addStretch(1)
        self.account_btn = QPushButton("Not logged in", host)
        self.account_menu = QMenu(self)
        self.account_menu.addAction("User Settings", self.open_user_settings)
        self.account_menu.addAction("Logout", self.do_logout)
        self.account_btn.setMenu(self.account_menu)
        row3.addWidget(self.account_btn)

        v.addLayout(row3)
        return host

    def _refresh_identity(self):
        with SessionLocal() as s:
            cs = s.query(CompanySettings).first()
        if not cs:
            self.header_company.setText("Company Name")
            self.header_detail1.setText("")
            self.header_detail2.setText("")
            self.header_logo.clear()
            return
        self.header_company.setText(cs.name or "Company Name")
        self.header_detail1.setText(cs.detail1 or "")
        self.header_detail2.setText(cs.detail2 or "")
        if cs.logo:
            pm = QPixmap()
            pm.loadFromData(cs.logo)
            pm_scaled = pm.scaled(self.header_logo.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.header_logo.setPixmap(pm_scaled)
        else:
            self.header_logo.clear()

    # ===== Helpers =====
    def _normalize_tz(self, key: str) -> str:
        """Invert sign for IANA Etc/GMT±X zones: Etc/GMT+8 means UTC-8."""
        if not key:
            return "Etc/UTC"
        m = re.fullmatch(r"Etc/GMT([+-])(\d+)", key, flags=re.IGNORECASE)
        if m:
            sign, num = m.groups()
            inv = "-" if sign == "+" else "+"
            return f"Etc/GMT{inv}{num}"
        return key

    def _login_flow(self):
        """Open login dialog, support hardcoded admin/admin123, and normal auth."""
        while True:
            dlg = LoginDialog()
            if dlg.exec() != QDialog.Accepted:
                self.close()
                return

            # pull credentials from the dialog
            try:
                if hasattr(dlg, "credentials"):
                    username, password = dlg.credentials()
                else:
                    username = dlg.ed_user.text().strip()
                    password = dlg.ed_pass.text()
            except Exception:
                username, password = "", ""

            username = (username or "").strip()
            password = password or ""

            # --- DEV BYPASS: admin / admin123 ---
            if username.lower() == "admin" and password == "admin123":
                with SessionLocal() as s:
                    user = s.query(User).filter(User.username == "admin").first()
                    if not user:
                        try:
                            from ..core.auth import hash_password as _hash
                        except Exception:
                            _hash = None
                        pwhash = _hash("admin123") if _hash else "admin123"
                        user = User(username="admin", password_hash=pwhash, role="superadmin", account_id="default")
                        s.add(user); s.commit(); s.refresh(user)
                    us = s.query(UserSettings).filter(UserSettings.user_id == user.id).first()
                    if not us:
                        us = UserSettings(user_id=user.id, account_id="default", timezone="Asia/Singapore", theme="light")
                        s.add(us); s.commit(); s.refresh(us)
                self.user = user
                self.user_settings = us
                self.account_btn.setText(user.username)
                self.company_act_btn.setEnabled(True)
                self.modules_act_btn.setEnabled(True)
                self._apply_theme()
                break

            # --- Normal auth path ---
            if not username:
                QMessageBox.warning(self, "Login failed", "Username is required.")
                continue

            with SessionLocal() as s:
                user = s.query(User).filter(User.username == username).first()

            ok = False
            if user:
                try:
                    from ..core.auth import verify_password as _verify_password
                except Exception:
                    _verify_password = None
                try:
                    if _verify_password:
                        ok = _verify_password(password, user.password_hash)
                    else:
                        ok = (password == user.password_hash)  # fallback if hashing unavailable
                except Exception:
                    ok = False

            if not ok:
                QMessageBox.warning(self, "Login failed", "Invalid username or password.")
                continue

            self.user = user
            with SessionLocal() as s:
                self.user_settings = s.query(UserSettings).filter(
                    UserSettings.user_id == user.id
                ).first()
                if not self.user_settings:
                    self.user_settings = UserSettings(user_id=user.id, account_id="default",
                                                      timezone="Asia/Singapore", theme="light")
                    s.add(self.user_settings); s.commit(); s.refresh(self.user_settings)

            self.account_btn.setText(user.username)
            self.company_act_btn.setEnabled(user.role in ("admin", "superadmin"))
            self.modules_act_btn.setEnabled(user.role == "superadmin")
            self._apply_theme()
            break

    def _apply_theme(self):
        if not self.user_settings:
            return
        self.setStyleSheet(themes.DARK if self.user_settings.theme == "dark" else themes.LIGHT)

    def _tick_clock(self):
        tz_key = (self.user_settings.timezone if self.user_settings else "Etc/UTC") or "Etc/UTC"
        tz_key = self._normalize_tz(tz_key)
        try:
            tz = ZoneInfo(tz_key)
        except Exception:
            try:
                tz = ZoneInfo("Asia/Singapore")
            except Exception:
                tz = ZoneInfo("Etc/UTC")
        now = datetime.now(tz)
        self.clock_lbl.setText(now.strftime("%Y-%m-%d %H:%M:%S %Z"))

    def _enabled_states(self):
        with SessionLocal() as s:
            return {m.name: m.enabled for m in s.query(ModuleState).all()}

    def _rebuild_nav(self):
        self.nav.clear()
        mods = discover_modules()
        enabled = self._enabled_states()
        for info, module in mods:
            mname = info["name"]
            if enabled.get(mname):
                mitem = QTreeWidgetItem([mname])
                mitem.setData(0, Qt.UserRole, ("module", mname))
                self.nav.addTopLevelItem(mitem)
                for sub in info.get("submodules", []):
                    full = f"{mname}/{sub}"
                    if enabled.get(full):
                        sitem = QTreeWidgetItem([sub])
                        sitem.setData(0, Qt.UserRole, ("submodule", mname, sub))
                        mitem.addChild(sitem)
                mitem.setExpanded(True)

    # ===== Open content =====
    def _open_item(self, item: QTreeWidgetItem):
        role = item.data(0, Qt.UserRole)
        if not role:
            return
        t = role[0]
        if t == "module":
            name = role[1]
            for info, module in discover_modules():
                if info["name"] == name:
                    self._open_in_tab(name, module.get_widget())
                    break
        else:
            mname, sub = role[1], role[2]
            title = f"{mname} — {sub}"
            for info, module in discover_modules():
                if info["name"] == mname:
                    try:
                        w = module.get_submodule_widget(sub)
                    except Exception as ex:
                        QMessageBox.critical(self, "Failed to open submodule", f"{sub} error:\n{ex}")
                        raise
                    self._open_in_tab(title, w)
                    break

    def _open_in_tab(self, title: str, widget: QWidget):
        for i in range(self.content_tabs.count()):
            if self.content_tabs.tabText(i) == title:
                self.content_tabs.setCurrentIndex(i)
                return
        self.content_tabs.addTab(widget, title)
        self.content_tabs.setCurrentIndex(self.content_tabs.count() - 1)

    # ===== Actions =====
    def open_company_settings(self):
        if self.user.role not in ("admin", "superadmin"):
            return
        CompanySettingsDialog(self).exec()
        self._refresh_identity()

    def open_user_settings(self):
        if not self.user_settings:
            return
        d = UserSettingsDialog(self.user_settings.timezone, self.user_settings.theme)
        if d.exec() == QDialog.Accepted:
            tz, theme = d.values()
            with SessionLocal() as s:
                us = s.query(UserSettings).get(self.user_settings.id)
                us.timezone = tz
                us.theme = theme
                s.commit()
                s.refresh(us)
                self.user_settings = us
            self._apply_theme()

    def do_logout(self):
        self.user = None
        self.user_settings = None
        self._login_flow()
        self._refresh_identity()

    def open_module_manager(self):
        if self.user.role != "superadmin":
            return

        mods = discover_modules()
        enabled = self._enabled_states()

        d = QDialog(self)
        d.setWindowTitle("Install / Enable Modules and Submodules")
        layout = QVBoxLayout(d)

        tree = QTreeWidget()
        tree.setHeaderLabels(["Name"])
        tree.setSelectionMode(QAbstractItemView.NoSelection)

        def _item(text, key, checked):
            it = QTreeWidgetItem([text])
            it.setData(0, Qt.UserRole, key)
            it.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
            return it

        for info, module in mods:
            mname = info["name"]
            m_it = _item(mname, mname, bool(enabled.get(mname)))
            for sub in info.get("submodules", []):
                skey = f"{mname}/{sub}"
                s_it = _item(sub, skey, bool(enabled.get(skey)))
                m_it.addChild(s_it)
            tree.addTopLevelItem(m_it)
            m_it.setExpanded(True)

        layout.addWidget(tree)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addWidget(bb)

        def save():
            checked = set()
            for i in range(tree.topLevelItemCount()):
                m_it = tree.topLevelItem(i)
                m_key = m_it.data(0, Qt.UserRole)
                if m_it.checkState(0) == Qt.Checked:
                    checked.add(m_key)
                for j in range(m_it.childCount()):
                    s_it = m_it.child(j)
                    s_key = s_it.data(0, Qt.UserRole)
                    if s_it.checkState(0) == Qt.Checked:
                        checked.add(s_key)
                        checked.add(m_key)

            with SessionLocal() as s:
                current = {m.name: m for m in s.query(ModuleState).all()}
                keys = set()
                for info, _ in mods:
                    mname = info["name"]
                    keys.add(mname)
                    for sub in info.get("submodules", []):
                        keys.add(f"{mname}/{sub}")
                for key in keys:
                    if key in current:
                        current[key].enabled = key in checked
                    else:
                        s.add(ModuleState(name=key, enabled=(key in checked)))
                s.commit()

            self._rebuild_nav()
            d.accept()

        bb.accepted.connect(save)
        bb.rejected.connect(d.reject)
        d.exec()
