# High-contrast NAV/SAP-like themes with explicit backgrounds and visible indicators.

LIGHT = """
/* Base */
QWidget { font-family: Segoe UI, Arial; font-size: 13px; color: #18202a; background: #ffffff; }
QMainWindow { background: #f3f5f7; }

/* Fixed header (setMenuWidget) */
#TopHeader { background: #ffffff; border-bottom: 1px solid #d6dbe3; }
#TopHeader * { color: #18202a; }

/* Dock title */
QDockWidget::title { background: #eef2f6; color: #18202a; padding: 6px 8px; border: 1px solid #d6dbe3; }

/* Nav panel and tree */
#NavPanel { background: #ffffff; }
QTreeWidget#NavTree { background: #ffffff; color: #18202a; border: 1px solid #d6dbe3; }
QTreeWidget#NavTree::item { height: 28px; padding: 4px 10px; }
QTreeWidget#NavTree::item:selected { background: #e7f0fe; color: #0a6ed1; }
QTreeWidget#NavTree::item:hover { background: #f3f8ff; }

/* Tabs */
QTabBar::tab { background: #ffffff; color: #18202a; border: 1px solid #d6dbe3; border-bottom: none; padding: 6px 12px; margin-right: 2px; }
QTabBar::tab:selected { background: #f3f5f7; color: #0a6ed1; border-color: #0a6ed1; font-weight: 600; }
QTabWidget::pane { border: 1px solid #d6dbe3; top: -1px; }

/* Inputs */
QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit {
  background: #ffffff; color: #18202a; border: 1px solid #c8ced6; border-radius: 4px; padding: 4px 6px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus {
  border: 1px solid #0a6ed1;
}
QComboBox QAbstractItemView { background: #ffffff; color: #18202a; selection-background-color: #e7f0fe; selection-color: #0a6ed1; }

/* Buttons */
QPushButton { background: #0a6ed1; color: #ffffff; border: 0; padding: 6px 12px; border-radius: 4px; }
QPushButton:hover { background: #095fb5; }
QPushButton:pressed { background: #084f97; }
QPushButton:disabled { background: #c2d4ef; color: #ffffff; }

/* Tables and lists */
QTableView, QListView, QTreeView { background: #ffffff; color: #18202a; border: 1px solid #d6dbe3; }
QHeaderView::section { background: #eef2f6; color: #18202a; border: 1px solid #d6dbe3; padding: 4px 6px; font-weight: 600; }
QTableView::item:selected, QListView::item:selected, QTreeView::item:selected { background: #e7f0fe; color: #0a6ed1; }

/* Item-view checkbox indicators (tree/table check states) */
QTreeView::indicator, QTreeWidget::indicator, QTableView::indicator {
  width: 18px; height: 18px; margin-left: 6px; margin-right: 6px;
}
QTreeView::indicator:unchecked, QTreeWidget::indicator:unchecked, QTableView::indicator:unchecked {
  border: 1px solid #586170; background: #ffffff; border-radius: 3px;
}
QTreeView::indicator:checked, QTreeWidget::indicator:checked, QTableView::indicator:checked {
  border: 1px solid #0a6ed1; background: #0a6ed1; border-radius: 3px;
}
QTreeView::indicator:indeterminate, QTreeWidget::indicator:indeterminate, QTableView::indicator:indeterminate {
  border: 1px solid #0a6ed1; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #e7f0fe, stop:1 #bcd7ff); border-radius: 3px;
}

/* Menus */
QMenu { background: #ffffff; color: #18202a; border: 1px solid #d6dbe3; }
QMenu::item:selected { background: #e7f0fe; color: #0a6ed1; }

/* Status bar */
QStatusBar { background: #ffffff; color: #2a3b4f; border-top: 1px solid #d6dbe3; }

/* Standalone checkbox and radio indicators */
QCheckBox, QRadioButton { color: #18202a; }
QCheckBox::indicator, QRadioButton::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked { border: 1px solid #586170; background: #ffffff; border-radius: 3px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { border: 1px solid #0a6ed1; background: #0a6ed1; border-radius: 3px; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border: 1px solid #c8ced6; background: #eef2f6; }
"""

DARK = """
/* Base */
QWidget { font-family: Segoe UI, Arial; font-size: 13px; color: #e6edf3; background: #0f1216; }
QMainWindow { background: #0f1216; }

/* Fixed header (setMenuWidget) */
#TopHeader { background: #111723; border-bottom: 1px solid #2a3446; }
#TopHeader * { color: #e6edf3; }

/* Dock title */
QDockWidget::title { background: #151c2a; color: #e6edf3; padding: 6px 8px; border: 1px solid #2a3446; }

/* Nav panel and tree */
#NavPanel { background: #10151c; }
QTreeWidget#NavTree { background: #10151c; color: #e6edf3; border: 1px solid #2a3446; }
QTreeWidget#NavTree::item { height: 28px; padding: 4px 10px; }
QTreeWidget#NavTree::item:selected { background: #243551; color: #9fc2ff; }
QTreeWidget#NavTree::item:hover { background: #172232; }

/* Tabs */
QTabBar::tab { background: #121826; color: #d9e3ee; border: 1px solid #2a3446; border-bottom: none; padding: 6px 12px; margin-right: 2px; }
QTabBar::tab:selected { background: #0f1216; color: #9fc2ff; border-color: #3a5d8a; font-weight: 600; }
QTabWidget::pane { border: 1px solid #2a3446; top: -1px; }

/* Inputs */
QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit {
  background: #0b0f15; color: #e6edf3; border: 1px solid #2a3446; border-radius: 4px; padding: 4px 6px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus {
  border: 1px solid #3b6fbf;
}
QComboBox QAbstractItemView { background: #0f1520; color: #e6edf3; selection-background-color: #243551; selection-color: #9fc2ff; }

/* Buttons */
QPushButton { background: #2b5fad; color: #ffffff; border: 0; padding: 6px 12px; border-radius: 4px; }
QPushButton:hover { background: #2a5aa3; }
QPushButton:pressed { background: #264f8f; }
QPushButton:disabled { background: #2a3b57; color: #8da2c0; }

/* Tables and lists */
QTableView, QListView, QTreeView { background: #0f1216; color: #e6edf3; border: 1px solid #2a3446; }
QHeaderView::section { background: #151c2a; color: #e6edf3; border: 1px solid #2a3446; padding: 4px 6px; font-weight: 600; }
QTableView::item:selected, QListView::item:selected, QTreeView::item:selected { background: #243551; color: #9fc2ff; }

/* Item-view checkbox indicators (tree/table check states) */
QTreeView::indicator, QTreeWidget::indicator, QTableView::indicator {
  width: 18px; height: 18px; margin-left: 6px; margin-right: 6px;
}
QTreeView::indicator:unchecked, QTreeWidget::indicator:unchecked, QTableView::indicator:unchecked {
  border: 1px solid #8a8f98; background: #0f1216; border-radius: 3px;
}
QTreeView::indicator:checked, QTreeWidget::indicator:checked, QTableView::indicator:checked {
  border: 1px solid #2f8bff; background: #2f8bff; border-radius: 3px;
}
QTreeView::indicator:indeterminate, QTreeWidget::indicator:indeterminate, QTableView::indicator:indeterminate {
  border: 1px solid #2f8bff; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #243551, stop:1 #3a5d8a); border-radius: 3px;
}

/* Menus */
QMenu { background: #0f1216; color: #e6edf3; border: 1px solid #2a3446; }
QMenu::item:selected { background: #243551; color: #9fc2ff; }

/* Status bar */
QStatusBar { background: #101521; color: #cdd7e5; border-top: 1px solid #2a3446; }

/* Standalone checkbox and radio indicators */
QCheckBox, QRadioButton { color: #e6edf3; }
QCheckBox::indicator, QRadioButton::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked { border: 1px solid #8a8f98; background: #1e1f22; border-radius: 3px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { border: 1px solid #2f8bff; background: #2f8bff; border-radius: 3px; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border: 1px solid #2a3446; background: #151c2a; }
"""
