from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QFileDialog,
    QTextEdit,
    QHBoxLayout,
    QMessageBox,
    QAbstractItemView,
)
from PySide6.QtGui import QPixmap
from ..core.database import SessionLocal, get_module_db_path, wipe_module_database
from ..core.models import CompanySettings
from ..core.plugins import discover_modules
class CompanySettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Company Settings")
        layout = QVBoxLayout(self)
        self.name = QLineEdit(); self.name.setPlaceholderText("Company Name")
        self.detail1 = QLineEdit(); self.detail1.setPlaceholderText("Details Line 1")
        self.detail2 = QLineEdit(); self.detail2.setPlaceholderText("Details Line 2")
        self.version = QLineEdit(); self.version.setPlaceholderText("Version")
        self.about = QTextEdit(); self.about.setPlaceholderText("About text")
        self.logo_path = ""
        self.logo_btn = QPushButton("Upload Logo")
        self.logo_lbl = QLabel("")
        self.update_btn = QPushButton("Update Version")
        self.save_btn = QPushButton("Save")
        self.factory_btn = QPushButton("Factory Reset…")
        layout.addWidget(self.name); layout.addWidget(self.detail1); layout.addWidget(self.detail2)
        layout.addWidget(self.version); layout.addWidget(self.about)
        layout.addWidget(self.logo_btn); layout.addWidget(self.logo_lbl)
        hl = QHBoxLayout(); hl.addWidget(self.update_btn); hl.addWidget(self.factory_btn); layout.addLayout(hl)
        layout.addWidget(self.save_btn)
        self.logo_btn.clicked.connect(self.pick_logo)
        self.update_btn.clicked.connect(self.bump_version)
        self.save_btn.clicked.connect(self.save)
        self.factory_btn.clicked.connect(self.factory_reset)
        with SessionLocal() as s:
            cs = s.query(CompanySettings).first()
            if not cs:
                cs = CompanySettings(); s.add(cs); s.commit()
            self.name.setText(cs.name); self.detail1.setText(cs.detail1); self.detail2.setText(cs.detail2)
            self.version.setText(cs.version); self.about.setPlainText(cs.about)
            if cs.logo:
                pm = QPixmap(); pm.loadFromData(cs.logo); self.logo_lbl.setPixmap(pm.scaledToHeight(64))
    def pick_logo(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select Logo", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if p: self.logo_path = p; self.logo_lbl.setText(p)
    def bump_version(self):
        parts = self.version.text().split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1); self.version.setText(".".join(parts))
        except Exception:
            pass
    def save(self):
        from PIL import Image
        from io import BytesIO
        logo_bytes = None
        if self.logo_path:
            img = Image.open(self.logo_path).convert("RGBA")
            buf = BytesIO(); img.save(buf, format="PNG"); logo_bytes = buf.getvalue()
        with SessionLocal() as s:
            cs = s.query(CompanySettings).first()
            cs.name = self.name.text(); cs.detail1 = self.detail1.text(); cs.detail2 = self.detail2.text()
            cs.version = self.version.text(); cs.about = self.about.toPlainText()
            if logo_bytes: cs.logo = logo_bytes
            s.commit()
        self.accept()
    def factory_reset(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        module_entries: list[tuple[str, str, str]] = []
        for info, module in discover_modules():
            module_path = getattr(module.__class__, "__module__", "")
            parts = module_path.split(".")
            key = ""
            if "modules" in parts:
                idx = parts.index("modules")
                if idx + 1 < len(parts):
                    key = parts[idx + 1]
            if not key or key == "account_management":
                continue
            path = get_module_db_path(key)
            name = info.get("name") or key.replace("_", " ").title()
            suffix = "" if path.exists() else " — no data file found"
            module_entries.append((f"{name} ({path.name}){suffix}", key, str(path)))

        if not module_entries:
            QMessageBox.information(self, "Factory Reset", "No module databases are available to wipe.")
            return

        d = QDialog(self)
        d.setWindowTitle("Factory Reset")
        v = QVBoxLayout(d)

        info_lbl = QLabel("Select the module databases to delete. Account data is preserved.")
        info_lbl.setWordWrap(True)
        v.addWidget(info_lbl)

        lw = QListWidget()
        lw.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for label, key, path in module_entries:
            item = QListWidgetItem(label, lw)
            item.setData(Qt.UserRole, {"key": key, "path": path})
        v.addWidget(lw)

        run = QPushButton("Wipe Selected")
        v.addWidget(run)

        def wipe():
            items = lw.selectedItems()
            if not items:
                QMessageBox.information(d, "Factory Reset", "Select at least one module database to wipe.")
                return
            summary = "\n".join(it.text() for it in items)
            if QMessageBox.question(
                d,
                "Confirm Wipe",
                f"Delete the following module database(s)?\n\n{summary}",
            ) != QMessageBox.Yes:
                return
            for it in items:
                data = it.data(Qt.UserRole) or {}
                key = data.get("key")
                if key:
                    wipe_module_database(key)
            QMessageBox.information(d, "Factory Reset", "Selected module databases have been wiped.")
            d.accept()

        run.clicked.connect(wipe)
        d.exec()
