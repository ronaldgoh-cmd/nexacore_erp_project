from zoneinfo import available_timezones

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class ToggleSwitch(QCheckBox):
    """A check box rendered as a modern toggle switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(54, 30)
        # Hide the default indicator so we can draw the control ourselves.
        self.setStyleSheet("QCheckBox::indicator { width: 0px; height: 0px; }")

        # Ensure we repaint whenever the underlying state changes so the
        # thumb position updates immediately.
        self.stateChanged.connect(self.update)

        # Palette tuned for accessibility across both light and dark themes.
        self._on_color = QColor("#2dc76d")
        self._off_color = QColor("#b6c5d6")
        self._disabled_color = QColor("#d6dde6")
        self._thumb_color = QColor("#ffffff")
        self._thumb_disabled_color = QColor("#f5f7f9")

    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        return self.size()

    def hitButton(self, pos):
        """Make the entire control clickable, not just the hidden indicator."""
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        margin = 3
        track_height = self.height() - 2 * margin
        track_rect = QRectF(margin, margin, self.width() - 2 * margin, track_height)
        track_radius = track_height / 2

        if not self.isEnabled():
            track_color = self._disabled_color
        else:
            track_color = self._on_color if self.isChecked() else self._off_color

        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, track_radius, track_radius)

        thumb_diameter = track_height
        thumb_x = track_rect.right() - thumb_diameter if self.isChecked() else track_rect.left()
        thumb_rect = QRectF(thumb_x, margin, thumb_diameter, thumb_diameter)
        thumb_color = self._thumb_disabled_color if not self.isEnabled() else self._thumb_color

        painter.setBrush(thumb_color)
        painter.drawEllipse(thumb_rect)

        if self.hasFocus():
            focus_pen = QPen(QColor("#0a6ed1"))
            focus_pen.setWidthF(2.0)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(focus_pen)
            focus_rect = track_rect.adjusted(-1.5, -1.5, 1.5, 1.5)
            painter.drawRoundedRect(focus_rect, track_radius + 1.5, track_radius + 1.5)

        painter.end()


class UserSettingsDialog(QDialog):
    def __init__(self, current_tz: str, current_theme: str):
        super().__init__()
        self.setWindowTitle("User Settings")

        layout = QVBoxLayout(self)

        self.tz = QComboBox()
        tzs = sorted(t for t in available_timezones() if "/" in t)
        self.tz.addItems(tzs)
        idx = self.tz.findText(current_tz)
        if idx >= 0:
            self.tz.setCurrentIndex(idx)

        self.theme_toggle = ToggleSwitch()
        self.theme_toggle.setChecked(current_theme == "dark")
        self.theme_toggle.setToolTip("Toggle dark theme")

        self.save_btn = QPushButton("Save")

        layout.addWidget(QLabel("Timezone"))
        layout.addWidget(self.tz)

        theme_row = QHBoxLayout()
        theme_label = QLabel("Dark Theme")
        theme_row.addWidget(theme_label)
        theme_row.addStretch()
        theme_row.addWidget(self.theme_toggle)
        layout.addLayout(theme_row)

        layout.addWidget(self.save_btn)

        self.save_btn.clicked.connect(self.accept)

    def values(self):
        return self.tz.currentText(), ("dark" if self.theme_toggle.isChecked() else "light")