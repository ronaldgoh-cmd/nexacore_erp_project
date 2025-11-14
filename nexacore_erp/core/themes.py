# SAP-inspired Quartz themes with clear hierarchy and accessible contrast.

LIGHT = """
/* Base */
QWidget { font-family: Segoe UI, Arial; font-size: 13px; color: #1a2a3a; background: #f5f6f8; }
QMainWindow { background: #f0f3f7; }

/* Fixed header (setMenuWidget) */
#TopHeader { background: #ffffff; border-bottom: 1px solid #d5dbe3; }
#TopHeader * { color: #1a2a3a; }
#TopHeader QLabel,
#TopHeader QPushButton,
#TopHeader QToolButton { color: #ffffff; }

/* Dock title */
QDockWidget::title { background: #ecf1f6; color: #1a2a3a; padding: 6px 8px; border: 1px solid #d5dbe3; }

/* Nav panel and tree */
#NavPanel { background: #ffffff; }
QTreeWidget#NavTree { background: #ffffff; color: #1a2a3a; border: 1px solid #d5dbe3; }
QTreeWidget#NavTree::item { height: 28px; padding: 4px 10px; }
QTreeWidget#NavTree::item:selected { background: #d4e9ff; color: #0a5096; }
QTreeWidget#NavTree::item:hover { background: #edf5ff; }

/* Tabs */
QTabBar::tab { background: #ffffff; color: #1a2a3a; border: 1px solid #d5dbe3; border-bottom: none; padding: 6px 12px; margin-right: 2px; }
QTabBar::tab:selected { background: #f0f3f7; color: #0a5096; border-color: #0a6ed1; font-weight: 600; }
QTabWidget::pane { border: 1px solid #d5dbe3; top: -1px; }

/* Inputs */
QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit {
  background: #ffffff; color: #1a2a3a; border: 1px solid #c1c9d6; border-radius: 4px; padding: 4px 6px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus {
  border: 1px solid #0a6ed1;
}
QComboBox QAbstractItemView { background: #ffffff; color: #1a2a3a; selection-background-color: #d4e9ff; selection-color: #0a5096; }

/* Buttons */
QPushButton { background: #0a6ed1; color: #ffffff; border: 0; padding: 6px 12px; border-radius: 4px; }
QPushButton:hover { background: #085cad; }
QPushButton:pressed { background: #064b8d; }
QPushButton:disabled { background: #c5d8ea; color: #7a8ca4; }

/* Tables and lists */
QTableView, QListView, QTreeView { background: #ffffff; color: #1a2a3a; border: 1px solid #d5dbe3; }
QHeaderView::section { background: #ecf1f6; color: #1a2a3a; border: 1px solid #d5dbe3; padding: 4px 6px; font-weight: 600; }
QTableView::item:selected, QListView::item:selected, QTreeView::item:selected { background: #d4e9ff; color: #0a5096; }

/* Item-view checkbox indicators (tree/table check states) */
QTreeView::indicator, QTreeWidget::indicator, QTableView::indicator {
  width: 18px; height: 18px; margin-left: 6px; margin-right: 6px;
}
QTreeView::indicator:unchecked, QTreeWidget::indicator:unchecked, QTableView::indicator:unchecked {
  border: 1px solid #6c7d92; background: #ffffff; border-radius: 3px;
}
QTreeView::indicator:checked, QTreeWidget::indicator:checked, QTableView::indicator:checked {
  border: 1px solid #0a6ed1; background: #0a6ed1; border-radius: 3px;
}
QTreeView::indicator:indeterminate, QTreeWidget::indicator:indeterminate, QTableView::indicator:indeterminate {
  border: 1px solid #0a6ed1; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #d4e9ff, stop:1 #9cc8f2); border-radius: 3px;
}

/* Menus */
QMenu { background: #ffffff; color: #1a2a3a; border: 1px solid #d5dbe3; }
QMenu::item:selected { background: #d4e9ff; color: #0a5096; }

/* Status bar */
QStatusBar { background: #ffffff; color: #24344a; border-top: 1px solid #d5dbe3; }

/* Standalone checkbox and radio indicators */
QCheckBox, QRadioButton { color: #1a2a3a; }
QCheckBox::indicator, QRadioButton::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked { border: 1px solid #6c7d92; background: #ffffff; border-radius: 3px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { border: 1px solid #0a6ed1; background: #0a6ed1; border-radius: 3px; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border: 1px solid #c1c9d6; background: #ecf1f6; }
"""

DARK = """
/* Base */
QWidget { font-family: Segoe UI, Arial; font-size: 13px; color: #f4f7fb; background: #1f2a36; }
QMainWindow { background: #1f2a36; }

/* Fixed header (setMenuWidget) */
#TopHeader { background: #253341; border-bottom: 1px solid #32465a; }
#TopHeader * { color: #f4f7fb; }
#TopHeader QLabel,
#TopHeader QPushButton,
#TopHeader QToolButton { color: #ffffff; }

/* Dock title */
QDockWidget::title { background: #293b4b; color: #f4f7fb; padding: 6px 8px; border: 1px solid #32465a; }

/* Nav panel and tree */
#NavPanel { background: #223140; }
QTreeWidget#NavTree { background: #223140; color: #f4f7fb; border: 1px solid #32465a; }
QTreeWidget#NavTree::item { height: 28px; padding: 4px 10px; }
QTreeWidget#NavTree::item:selected { background: #2f4d6b; color: #a5d7ff; }
QTreeWidget#NavTree::item:hover { background: #2a3f58; }

/* Tabs */
QTabBar::tab { background: #283848; color: #d6e2f0; border: 1px solid #32465a; border-bottom: none; padding: 6px 12px; margin-right: 2px; }
QTabBar::tab:selected { background: #1f2a36; color: #a5d7ff; border-color: #3b8fdc; font-weight: 600; }
QTabWidget::pane { border: 1px solid #32465a; top: -1px; }

/* Inputs */
QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit {
  background: #233345; color: #f4f7fb; border: 1px solid #32465a; border-radius: 4px; padding: 4px 6px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus {
  border: 1px solid #3b8fdc;
}
QComboBox QAbstractItemView { background: #24364a; color: #f4f7fb; selection-background-color: #2f4d6b; selection-color: #a5d7ff; }

/* Buttons */
QPushButton { background: #1e76d2; color: #ffffff; border: 0; padding: 6px 12px; border-radius: 4px; }
QPushButton:hover { background: #1863b2; }
QPushButton:pressed { background: #124f90; }
QPushButton:disabled { background: #2b3d53; color: #8396af; }

/* Tables and lists */
QTableView, QListView, QTreeView { background: #1f2a36; color: #f4f7fb; border: 1px solid #32465a; }
QHeaderView::section { background: #293b4b; color: #f4f7fb; border: 1px solid #32465a; padding: 4px 6px; font-weight: 600; }
QTableView::item:selected, QListView::item:selected, QTreeView::item:selected { background: #2f4d6b; color: #a5d7ff; }

/* Item-view checkbox indicators (tree/table check states) */
QTreeView::indicator, QTreeWidget::indicator, QTableView::indicator {
  width: 18px; height: 18px; margin-left: 6px; margin-right: 6px;
}
QTreeView::indicator:unchecked, QTreeWidget::indicator:unchecked, QTableView::indicator:unchecked {
  border: 1px solid #4a5f77; background: #1f2a36; border-radius: 3px;
}
QTreeView::indicator:checked, QTreeWidget::indicator:checked, QTableView::indicator:checked {
  border: 1px solid #1e76d2; background: #1e76d2; border-radius: 3px;
}
QTreeView::indicator:indeterminate, QTreeWidget::indicator:indeterminate, QTableView::indicator:indeterminate {
  border: 1px solid #1e76d2; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #2f4d6b, stop:1 #4076a6); border-radius: 3px;
}

/* Menus */
QMenu { background: #1f2a36; color: #f4f7fb; border: 1px solid #32465a; }
QMenu::item:selected { background: #2f4d6b; color: #a5d7ff; }

/* Status bar */
QStatusBar { background: #223140; color: #d0dbea; border-top: 1px solid #32465a; }

/* Standalone checkbox and radio indicators */
QCheckBox, QRadioButton { color: #f4f7fb; }
QCheckBox::indicator, QRadioButton::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked { border: 1px solid #4a5f77; background: #253341; border-radius: 3px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { border: 1px solid #1e76d2; background: #1e76d2; border-radius: 3px; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border: 1px solid #32465a; background: #2a3d4f; }
"""