from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QPushButton
from ....core.database import SessionLocal
from ....core.tenant import id as tenant_id
from ..models import Employee

class SalaryModuleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget(self)
        v = QVBoxLayout(self); v.addWidget(self.tabs)

        self._build_summary_tab()
        self._build_salary_review_tab()
        self._build_vouchers_tab()
        self._build_settings_tab()

    def _build_summary_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        top = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText("Search by name")
        self.search.textChanged.connect(self._reload)
        top.addWidget(self.search); v.addLayout(top)

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Code", "Name", "Basic", "Incentive", "Allowance", "OT Rate"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl, 1)
        self.tabs.addTab(host, "Summary")
        self._reload()

    def _reload(self):
        q = (self.search.text() or "").lower()
        with SessionLocal() as s:
            rows = s.query(Employee).filter(Employee.account_id == tenant_id()).all()
        self.tbl.setRowCount(0)
        for e in rows:
            if q and q not in (e.full_name or "").lower():
                continue
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(e.code))
            self.tbl.setItem(r, 1, QTableWidgetItem(e.full_name))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{e.basic_salary:.2f}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(f"{e.incentives:.2f}"))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{e.allowance:.2f}"))
            self.tbl.setItem(r, 5, QTableWidgetItem(f"{e.overtime_rate:.2f}"))

    def _build_salary_review_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        v.addWidget(QLabel("Salary review workflow placeholder — create monthly runs, edit lines, submit lock"))
        v.addWidget(QPushButton("Create Month"))
        self.tabs.addTab(host, "Salary Review")

    def _build_vouchers_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        v.addWidget(QLabel("Salary vouchers placeholder — generate by month/year with company stamp"))
        self.tabs.addTab(host, "Salary Vouchers")

    def _build_settings_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        v.addWidget(QLabel("Settings placeholder — Voucher format, CPF/SHG/SDL tables"))
        self.tabs.addTab(host, "Settings")
