from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QPushButton, QLabel
from zoneinfo import available_timezones
class UserSettingsDialog(QDialog):
    def __init__(self, current_tz: str, current_theme: str):
        super().__init__()
        self.setWindowTitle("User Settings")
        layout = QVBoxLayout(self)
        self.tz = QComboBox(); tzs = sorted(t for t in available_timezones() if "/" in t)
        self.tz.addItems(tzs); 
        idx = self.tz.findText(current_tz)
        if idx >= 0: self.tz.setCurrentIndex(idx)
        self.theme = QComboBox(); self.theme.addItems(["light", "dark"])
        self.theme.setCurrentText(current_theme)
        self.save_btn = QPushButton("Save")
        layout.addWidget(QLabel("Timezone")); layout.addWidget(self.tz)
        layout.addWidget(QLabel("Theme")); layout.addWidget(self.theme)
        layout.addWidget(self.save_btn)
        self.save_btn.clicked.connect(self.accept)
    def values(self):
        return self.tz.currentText(), self.theme.currentText()
