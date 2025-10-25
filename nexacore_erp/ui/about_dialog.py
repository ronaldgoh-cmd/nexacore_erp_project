from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from ..core.database import SessionLocal
from ..core.models import CompanySettings
class AboutDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("About")
        layout = QVBoxLayout(self)
        with SessionLocal() as s:
            cs = s.query(CompanySettings).first()
        layout.addWidget(QLabel(f"<b>{cs.name}</b>"))
        layout.addWidget(QLabel(cs.detail1 or ""))
        layout.addWidget(QLabel(cs.detail2 or ""))
        layout.addWidget(QLabel(f"Version: {cs.version}"))
        layout.addWidget(QLabel(cs.about or ""))
