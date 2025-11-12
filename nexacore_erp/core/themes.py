# SAP-inspired Quartz themes with clear hierarchy and accessible contrast.

LIGHT = """
/* Base */
QWidget { font-family: Segoe UI, Arial; font-size: 13px; color: #1f2d3d; background: #f4f6fb; }
QMainWindow { background: #eef2f8; }

/* Fixed header (setMenuWidget) */
#TopHeader { background: #ffffff; border-bottom: 1px solid #cfd6e4; }
#TopHeader * { color: #1f2d3d; }

/* Dock title */
QDockWidget::title { background: #e8eef6; color: #1f2d3d; padding: 6px 8px; border: 1px solid #cfd6e4; }

/* Nav panel and tree */
#NavPanel { background: #ffffff; }
QTreeWidget#NavTree { background: #ffffff; color: #1f2d3d; border: 1px solid #cfd6e4; }
QTreeWidget#NavTree::item { height: 28px; padding: 4px 10px; }
QTreeWidget#NavTree::item:selected { background: #d9ecff; color: #0b4f94; }
QTreeWidget#NavTree::item:hover { background: #eef5ff; }

/* Tabs */
QTabBar::tab { background: #ffffff; color: #1f2d3d; border: 1px solid #cfd6e4; border-bottom: none; padding: 6px 12px; margin-right: 2px; }
QTabBar::tab:selected { background: #eef2f8; color: #0b4f94; border-color: #0d6efd; font-weight: 600; }
QTabWidget::pane { border: 1px solid #cfd6e4; top: -1px; }

/* Inputs */
QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit {
  background: #ffffff; color: #1f2d3d; border: 1px solid #b8c4d6; border-radius: 4px; padding: 4px 6px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus {
  border: 1px solid #0d6efd;
}
QComboBox QAbstractItemView { background: #ffffff; color: #1f2d3d; selection-background-color: #d9ecff; selection-color: #0b4f94; }

/* Buttons */
QPushButton { background: #0d6efd; color: #ffffff; border: 0; padding: 6px 12px; border-radius: 4px; }
QPushButton:hover { background: #0a5fcc; }
QPushButton:pressed { background: #084c9c; }
QPushButton:disabled { background: #c5d4e6; color: #7b899c; }

/* Tables and lists */
QTableView, QListView, QTreeView { background: #ffffff; color: #1f2d3d; border: 1px solid #cfd6e4; }
QHeaderView::section { background: #e8eef6; color: #1f2d3d; border: 1px solid #cfd6e4; padding: 4px 6px; font-weight: 600; }
QTableView::item:selected, QListView::item:selected, QTreeView::item:selected { background: #d9ecff; color: #0b4f94; }

/* Item-view checkbox indicators (tree/table check states) */
QTreeView::indicator, QTreeWidget::indicator, QTableView::indicator {
  width: 18px; height: 18px; margin-left: 6px; margin-right: 6px;
}
QTreeView::indicator:unchecked, QTreeWidget::indicator:unchecked, QTableView::indicator:unchecked {
  border: 1px solid #6e7d90; background: #ffffff; border-radius: 3px;
}
QTreeView::indicator:checked, QTreeWidget::indicator:checked, QTableView::indicator:checked {
  border: 1px solid #0d6efd; background: #0d6efd; border-radius: 3px;
}
QTreeView::indicator:indeterminate, QTreeWidget::indicator:indeterminate, QTableView::indicator:indeterminate {
  border: 1px solid #0d6efd; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #d9ecff, stop:1 #9dc5f6); border-radius: 3px;
}

/* Menus */
QMenu { background: #ffffff; color: #1f2d3d; border: 1px solid #cfd6e4; }
QMenu::item:selected { background: #d9ecff; color: #0b4f94; }

/* Status bar */
QStatusBar { background: #ffffff; color: #243345; border-top: 1px solid #cfd6e4; }

/* Standalone checkbox and radio indicators */
QCheckBox, QRadioButton { color: #1f2d3d; }
QCheckBox::indicator, QRadioButton::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked { border: 1px solid #6e7d90; background: #ffffff; border-radius: 3px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { border: 1px solid #0d6efd; background: #0d6efd; border-radius: 3px; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border: 1px solid #b8c4d6; background: #e8eef6; }
"""

DARK = """
/* Base */
QWidget { font-family: Segoe UI, Arial; font-size: 13px; color: #e4eaf3; background: #121d2a; }
QMainWindow { background: #121d2a; }

/* Fixed header (setMenuWidget) */
#TopHeader { background: #182636; border-bottom: 1px solid #233345; }
#TopHeader * { color: #e4eaf3; }

/* Dock title */
QDockWidget::title { background: #1a2a3a; color: #e4eaf3; padding: 6px 8px; border: 1px solid #233345; }

/* Nav panel and tree */
#NavPanel { background: #152330; }
QTreeWidget#NavTree { background: #152330; color: #e4eaf3; border: 1px solid #233345; }
QTreeWidget#NavTree::item { height: 28px; padding: 4px 10px; }
QTreeWidget#NavTree::item:selected { background: #22486d; color: #bfe0ff; }
QTreeWidget#NavTree::item:hover { background: #1d3750; }

/* Tabs */
QTabBar::tab { background: #1a2a3a; color: #d0dceb; border: 1px solid #233345; border-bottom: none; padding: 6px 12px; margin-right: 2px; }
QTabBar::tab:selected { background: #121d2a; color: #bfe0ff; border-color: #3c8dd9; font-weight: 600; }
QTabWidget::pane { border: 1px solid #233345; top: -1px; }

/* Inputs */
QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit {
  background: #152434; color: #e4eaf3; border: 1px solid #23374c; border-radius: 4px; padding: 4px 6px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus {
  border: 1px solid #3c8dd9;
}
QComboBox QAbstractItemView { background: #16283b; color: #e4eaf3; selection-background-color: #22486d; selection-color: #bfe0ff; }

/* Buttons */
QPushButton { background: #2b7cd8; color: #ffffff; border: 0; padding: 6px 12px; border-radius: 4px; }
QPushButton:hover { background: #2367b6; }
QPushButton:pressed { background: #1b5192; }
QPushButton:disabled { background: #1e2d3f; color: #7f92ab; }

/* Tables and lists */
QTableView, QListView, QTreeView { background: #121d2a; color: #e4eaf3; border: 1px solid #233345; }
QHeaderView::section { background: #1a2a3a; color: #e4eaf3; border: 1px solid #233345; padding: 4px 6px; font-weight: 600; }
QTableView::item:selected, QListView::item:selected, QTreeView::item:selected { background: #22486d; color: #bfe0ff; }

/* Item-view checkbox indicators (tree/table check states) */
QTreeView::indicator, QTreeWidget::indicator, QTableView::indicator {
  width: 18px; height: 18px; margin-left: 6px; margin-right: 6px;
}
QTreeView::indicator:unchecked, QTreeWidget::indicator:unchecked, QTableView::indicator:unchecked {
  border: 1px solid #40556e; background: #121d2a; border-radius: 3px;
}
QTreeView::indicator:checked, QTreeWidget::indicator:checked, QTableView::indicator:checked {
  border: 1px solid #2b7cd8; background: #2b7cd8; border-radius: 3px;
}
QTreeView::indicator:indeterminate, QTreeWidget::indicator:indeterminate, QTableView::indicator:indeterminate {
  border: 1px solid #2b7cd8; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #22486d, stop:1 #3f6fa0); border-radius: 3px;
}

/* Menus */
QMenu { background: #121d2a; color: #e4eaf3; border: 1px solid #233345; }
QMenu::item:selected { background: #22486d; color: #bfe0ff; }

/* Status bar */
QStatusBar { background: #152330; color: #cad6e6; border-top: 1px solid #233345; }

/* Standalone checkbox and radio indicators */
QCheckBox, QRadioButton { color: #e4eaf3; }
QCheckBox::indicator, QRadioButton::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked { border: 1px solid #40556e; background: #182636; border-radius: 3px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { border: 1px solid #2b7cd8; background: #2b7cd8; border-radius: 3px; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border: 1px solid #233345; background: #1c2b3b; }
"""