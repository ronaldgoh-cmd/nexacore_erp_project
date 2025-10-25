from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QLineEdit, QPushButton
from ....core.database import SessionLocal
from ....core.tenant import id as tenant_id
from ..models import Employee

class LeaveModuleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget(self)
        v = QVBoxLayout(self); v.addWidget(self.tabs)

        self._build_calendar_tab()
        self._build_details_tab()
        self._build_summary_tab()
        self._build_application_tab()
        self._build_adjustments_tab()

    def _build_calendar_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        h = QHBoxLayout()
        self.month = QComboBox(); self.month.addItems([str(i) for i in range(1, 13)])
        self.year = QComboBox(); self.year.addItems([str(y) for y in range(2024, 2036)])
        h.addWidget(QLabel("Month")); h.addWidget(self.month); h.addWidget(QLabel("Year")); h.addWidget(self.year); h.addStretch(1)
        v.addLayout(h)
        v.addWidget(QLabel("Calendar view placeholder – to be implemented"))
        self.tabs.addTab(host, "Calendar View")

    def _build_details_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Start Date", "Start AM/PM", "End Date", "End AM/PM", "Name", "Remarks"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl, 1)
        self.tabs.addTab(host, "Details")

    def _build_summary_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        v.addWidget(QLabel("Summary placeholder – compute balances from defaults + adjustments"))
        self.tabs.addTab(host, "Summary")

    def _build_application_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        h = QHBoxLayout()
        self.emp = QComboBox(); self._load_employees()
        self.type = QLineEdit(); self.type.setPlaceholderText("Leave type")
        self.s_date = QDateEdit(); self.s_date.setCalendarPopup(True); self.s_date.setDate(QDate.currentDate())
        self.s_ampm = QComboBox(); self.s_ampm.addItems(["AM", "PM"])
        self.e_date = QDateEdit(); self.e_date.setCalendarPopup(True); self.e_date.setDate(QDate.currentDate())
        self.e_ampm = QComboBox(); self.e_ampm.addItems(["AM", "PM"])
        self.remarks = QLineEdit(); self.remarks.setPlaceholderText("Remarks")
        h_widgets = [QLabel("Name"), self.emp, QLabel("Type"), self.type, QLabel("Start"), self.s_date, self.s_ampm, QLabel("End"), self.e_date, self.e_ampm, self.remarks]
        for w in h_widgets: h.addWidget(w)
        v.addLayout(h)
        v.addWidget(QLabel("Current balance and total used calculation placeholder"))
        v.addWidget(QPushButton("Submit Application"))
        self.tabs.addTab(host, "Application")

    def _build_adjustments_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        v.addWidget(QLabel("Adjustments placeholder – add manual adjustments here"))
        self.tabs.addTab(host, "Adjustments")

    def _load_employees(self):
        self.emp.clear()
        with SessionLocal() as s:
            rows = s.query(Employee).filter(Employee.account_id == tenant_id()).order_by(Employee.full_name).all()
        for r in rows:
            self.emp.addItem(f"{r.full_name} ({r.code})", r.id)
