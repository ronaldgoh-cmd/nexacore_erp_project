# salary_module.py
from __future__ import annotations

import base64
from calendar import month_name
from datetime import date
from typing import List, Tuple

from PySide6.QtCore import Qt, QMarginsF
from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTableWidget,
    QTableWidgetItem, QPushButton, QComboBox, QFileDialog, QHeaderView, QGroupBox,
    QFormLayout, QTextEdit, QTableWidgetSelectionRange, QSizePolicy
)

from ....core.database import SessionLocal
from ....core.tenant import id as tenant_id
from ..models import Employee
from ....core.models import CompanySettings


# ---------- helpers ----------
def _img_data_uri(png_bytes: bytes | None, fallback_label: str = "Logo") -> str:
    if png_bytes:
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return (
            "<img src=\"data:image/png;base64,"
            f"{b64}\" style=\"max-height:64px;max-width:160px;object-fit:contain;\"/>"
        )
    return (
        "<div style=\"height:64px;width:160px;border:1px solid #cfcfcf;border-radius:6px;"
        "display:flex;align-items:center;justify-content:center;color:#9aa0a6;font-size:12px;\">"
        f"{fallback_label}</div>"
    )


def _month_names() -> List[str]:
    return [month_name[i] for i in range(1, 13)]


def _employees() -> List[Tuple[int, str, str]]:
    with SessionLocal() as s:
        rows = (
            s.query(Employee)
            .filter(Employee.account_id == tenant_id())
            .order_by(Employee.full_name)
            .all()
        )
        return [(r.id, r.full_name or "", r.code or "") for r in rows]


def _company() -> CompanySettings | None:
    with SessionLocal() as s:
        return s.query(CompanySettings).first()


def _voucher_html(cs: CompanySettings | None, emp: Employee | None, year: int, month_index_1: int) -> str:
    import html
    # --- company ---
    company_name = (cs.name if cs else "") or "Company Name"
    detail1 = (cs.detail1 if cs else "") or "Company details line 1"
    detail2 = (cs.detail2 if cs else "") or "Company details line 2"
    logo_html = _img_data_uri(getattr(cs, "logo", None), "Logo")

    # --- employee snapshot ---
    emp_name = getattr(emp, "full_name", "") or "—"
    emp_code = getattr(emp, "code", "") or "—"
    id_no    = getattr(emp, "identification_number", "") or getattr(emp, "nric", "") or "—"
    bank     = getattr(emp, "bank", "") or "—"
    acct     = getattr(emp, "bank_account", "") or "—"

    # --- figures (use your stored fields; labels show Rate * Hr as requested) ---
    basic   = float(getattr(emp, "basic_salary", 0.0) or 0.0)
    comm    = float(getattr(emp, "commission", 0.0) or 0.0)
    incent  = float(getattr(emp, "incentives", 0.0) or 0.0)
    allow   = float(getattr(emp, "allowance", 0.0) or 0.0)

    pt_rate = float(getattr(emp, "parttime_rate", 0.0) or 0.0)
    pt_hrs  = float(getattr(emp, "part_time_hours", 0.0) or 0.0)
    pt_amt  = pt_rate * pt_hrs

    ot_rate = float(getattr(emp, "overtime_rate", 0.0) or 0.0)
    ot_hrs  = float(getattr(emp, "overtime_hours", 0.0) or 0.0)
    ot_amt  = ot_rate * ot_hrs

    # deductions panel = Advanced + SHG only
    advance = float(getattr(emp, "advance", 0.0) or 0.0)
    shg     = float(getattr(emp, "shg", 0.0) or 0.0)

    # CPF block
    cpf_emp = float(getattr(emp, "cpf_employee", 0.0) or 0.0)
    cpf_er  = float(getattr(emp, "cpf_employer", 0.0) or 0.0)
    cpf_total = cpf_emp + cpf_er

    # Others block
    sdl  = float(getattr(emp, "sdl", 0.0) or 0.0)
    levy = float(getattr(emp, "levy", 0.0) or 0.0)

    gross = basic + comm + incent + allow + pt_amt + ot_amt
    ded_only = advance + shg
    # Net pay excludes employer CPF, SDL, Levy. Employee CPF reduces net.
    net_pay = gross - ded_only - cpf_emp

    ym = f"{month_name[month_index_1]} {year}"
    code = f"SV-{year}{month_index_1:02d}-{(getattr(emp, 'code', '') or 'EMP001')}"

    def money(x: float) -> str:
        try:
            return f"{float(x):,.2f}"
        except Exception:
            return "0.00"

    no_data = (gross == 0 and ded_only == 0 and cpf_emp == 0 and cpf_er == 0 and sdl == 0 and levy == 0)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Salary Voucher</title>
<style>
  body {{ margin:0; background:#ffffff; color:#111827; font-family:Segoe UI, Arial, sans-serif; }}
  .page {{ width:794px; margin:0 auto; padding:36px 28px; }}
  .muted {{ color:#6b7280; }}
  .rule  {{ height:1px; background:#e5e7eb; }}
  .panel {{ border:1px solid #e5e7eb; border-radius:6px; }}
  .cap   {{ background:#f9fafb; border-bottom:1px solid #e5e7eb; font-weight:bold; padding:6px 8px; }}
  .cell  {{ padding:6px 8px; }}
  .title {{ color:#1f4e79; font-weight:bold; font-size:22px; padding:8px 0 6px 0; font-family:Helvetica, Arial, sans-serif; }}
  .stripe{{ background:#e8f1fb; border:1px solid #cfe0f6; border-radius:4px; padding:10px 12px; }}
</style>
</head>
<body>
  <div class="page">

    <!-- Header: company text aligned left beside logo -->
    <table cellpadding="0" cellspacing="0" width="100%">
      <tr>
        <td style="width:170px;vertical-align:top">{logo_html}</td>
        <td style="vertical-align:top;text-align:left">
          <div style="font-size:18px;font-weight:800">{html.escape(company_name)}</div>
          <div class="muted">{html.escape(detail1)}</div>
          <div class="muted">{html.escape(detail2)}</div>
        </td>
        <td style="width:220px;vertical-align:top;text-align:right">
          <div style="font-size:13px">{html.escape(ym)}</div>
          <div style="font-size:12px;font-weight:bold">Code: {html.escape(code)}</div>
        </td>
      </tr>
    </table>

    <div class="rule" style="margin:8px 0 12px 0"></div>
    <div class="title">Salary Voucher</div>

    <!-- Employee box: swap Employee Code above Employee, remove Position, change Department->Identification Number -->
    <table cellpadding="0" cellspacing="0" width="100%" class="panel" style="margin:8px 0 10px 0">
      <tr><td class="cap">Employee</td></tr>
      <tr>
        <td class="cell">
          <table cellpadding="0" cellspacing="0" width="100%">
            <tr>
              <td style="width:50%;vertical-align:top">
                <table cellpadding="0" cellspacing="0" width="100%">
                  <tr><td class="cell" style="width:160px;color:#374151;font-weight:bold">Employee Code</td><td class="cell">{html.escape(emp_code)}</td></tr>
                  <tr><td class="cell" style="color:#374151;font-weight:bold">Employee</td><td class="cell">{html.escape(emp_name)}</td></tr>
                  <tr><td class="cell" style="color:#374151;font-weight:bold">Identification Number</td><td class="cell">{html.escape(id_no)}</td></tr>
                </table>
              </td>
              <td style="width:50%;vertical-align:top">
                <table cellpadding="0" cellspacing="0" width="100%">
                  <tr><td class="cell" style="width:160px;color:#374151;font-weight:bold">Bank</td><td class="cell">{html.escape(bank)}</td></tr>
                  <tr><td class="cell" style="color:#374151;font-weight:bold">Account No.</td><td class="cell">{html.escape(acct)}</td></tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>

    <!-- Earnings / Deductions -->
    <table cellpadding="0" cellspacing="0" width="100%">
      <tr>
        <!-- Earnings -->
        <td style="width:50%;vertical-align:top">
          <table cellpadding="0" cellspacing="0" width="100%" class="panel">
            <tr><td class="cap">Earnings</td></tr>
            <tr><td>
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr><td class="cell" style="color:#374151">Basic Salary</td><td class="cell" style="text-align:right">{money(basic)}</td></tr>
                <tr><td class="cell" style="color:#374151">Commission</td><td class="cell" style="text-align:right">{money(comm)}</td></tr>
                <tr><td class="cell" style="color:#374151">Incentives</td><td class="cell" style="text-align:right">{money(incent)}</td></tr>
                <tr><td class="cell" style="color:#374151">Allowance</td><td class="cell" style="text-align:right">{money(allow)}</td></tr>
                <tr><td class="cell" style="color:#374151">Part time (Rate × Hr)</td><td class="cell" style="text-align:right">{money(pt_amt)}</td></tr>
                <tr><td class="cell" style="color:#374151">Overtime (Rate × Hr)</td><td class="cell" style="text-align:right">{money(ot_amt)}</td></tr>
                <tr><td class="cell" style="font-weight:bold">Gross Pay</td><td class="cell" style="text-align:right;font-weight:bold">{money(gross)}</td></tr>
              </table>
            </td></tr>
          </table>
        </td>

        <td style="width:12px"></td>

        <!-- Deductions -->
        <td style="width:50%;vertical-align:top">
          <table cellpadding="0" cellspacing="0" width="100%" class="panel">
            <tr><td class="cap">Deductions</td></tr>
            <tr><td>
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr><td class="cell" style="color:#374151">Advanced</td><td class="cell" style="text-align:right">{money(advance)}</td></tr>
                <tr><td class="cell" style="color:#374151">SHG</td><td class="cell" style="text-align:right">{money(shg)}</td></tr>
                <tr><td class="cell" style="font-weight:bold">Total Deductions</td><td class="cell" style="text-align:right;font-weight:bold">{money(ded_only)}</td></tr>
              </table>
            </td></tr>
          </table>
        </td>
      </tr>
    </table>

    <!-- CPF block -->
    <table cellpadding="0" cellspacing="0" width="100%" class="panel" style="margin-top:10px">
      <tr><td class="cap">CPF</td></tr>
      <tr><td>
        <table cellpadding="0" cellspacing="0" width="100%">
          <tr><td class="cell" style="color:#374151">Employee</td><td class="cell" style="text-align:right">{money(cpf_emp)}</td></tr>
          <tr><td class="cell" style="color:#374151">Employer</td><td class="cell" style="text-align:right">{money(cpf_er)}</td></tr>
          <tr><td class="cell" style="font-weight:bold">Total</td><td class="cell" style="text-align:right;font-weight:bold">{money(cpf_total)}</td></tr>
        </table>
      </td></tr>
    </table>

    <!-- Others block -->
    <table cellpadding="0" cellspacing="0" width="100%" class="panel" style="margin-top:10px">
      <tr><td class="cap">Others</td></tr>
      <tr><td>
        <table cellpadding="0" cellspacing="0" width="100%">
          <tr><td class="cell" style="color:#374151">SDL</td><td class="cell" style="text-align:right">{money(sdl)}</td></tr>
          <tr><td class="cell" style="color:#374151">Levy</td><td class="cell" style="text-align:right">{money(levy)}</td></tr>
        </table>
      </td></tr>
    </table>

    {'' if not no_data else f'''
    <table cellpadding="0" cellspacing="0" width="100%" style="margin-top:10px">
      <tr><td>
        <table cellpadding="0" cellspacing="0" width="100%" style="border:1px solid #fdba74;background:#fff7ed;border-radius:4px">
          <tr><td style="padding:8px 10px;color:#9a3412;font-weight:bold">
            No Salary Review entry found for {html.escape(emp_name if emp_name != "—" else "selected employee")} in {html.escape(ym)}.
          </td></tr>
        </table>
      </td></tr>
    </table>
    '''}

    <!-- Net Pay stripe -->
    <table cellpadding="0" cellspacing="0" width="100%" style="margin-top:12px">
      <tr>
        <td class="stripe" style="font-weight:bold">Net Pay</td>
        <td class="stripe" style="text-align:right;font-weight:bold">{money(net_pay)}</td>
      </tr>
    </table>

    <!-- Notes -->
    <div style="margin-top:12px;font-weight:bold">Notes</div>
    <div class="muted" style="font-size:13px">
      Figures reflect the 'Salary Review' records for the selected period. If no record exists, this preview
      shows zeros and a not-found notice. CPF and statutory amounts shown are those stored in the review.
    </div>

    <!-- Signatures -->
    <table cellpadding="0" cellspacing="0" width="100%" style="margin-top:22px">
      <tr>
        <td style="width:50%;vertical-align:bottom">
          <div style="font-weight:bold">Prepared by: {html.escape(company_name)}</div>
        </td>
        <td style="width:50%;text-align:right;vertical-align:bottom">
          <div>Employee Acknowledgement</div>
          <div style="height:1px;background:#e5e7eb;margin-top:18px"></div>
        </td>
      </tr>
    </table>

  </div>
</body>
</html>"""


# ---------- widget ----------
class SalaryModuleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget(self)
        v = QVBoxLayout(self)
        v.addWidget(self.tabs)

        self._build_summary_tab()
        self._build_salary_review_tab()
        self._build_vouchers_tab()
        self._build_settings_tab()

    # -- Summary
    def _build_summary_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name")
        self.search.textChanged.connect(self._reload_summary)
        top.addWidget(self.search)
        top.addStretch(1)
        v.addLayout(top)

        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(
            ["Code", "Name", "Basic", "Incentive", "Allowance", "Overtime Rate", "Part-Time Rate"]
        )
        hdr = self.tbl.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        v.addWidget(self.tbl, 1)

        self.tabs.addTab(host, "Summary")
        self._reload_summary()

    def _reload_summary(self):
        q = (self.search.text() or "").lower()
        with SessionLocal() as s:
            rows = s.query(Employee).filter(Employee.account_id == tenant_id()).all()
        self.tbl.setRowCount(0)
        for e in rows:
            if q and q not in (e.full_name or "").lower():
                continue
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(e.code or ""))
            self.tbl.setItem(r, 1, QTableWidgetItem(e.full_name or ""))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{(e.basic_salary or 0.0):.2f}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(f"{(e.incentives or 0.0):.2f}"))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{(e.allowance or 0.0):.2f}"))
            self.tbl.setItem(r, 5, QTableWidgetItem(f"{(e.overtime_rate or 0.0):.2f}"))
            self.tbl.setItem(r, 6, QTableWidgetItem(f"{(e.parttime_rate or 0.0):.2f}"))

    # -- Salary Review (placeholder)
    def _build_salary_review_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)
        v.addWidget(QLabel("Salary review workflow placeholder — create monthly runs, edit lines, submit lock"))
        v.addWidget(QPushButton("Create Month"))
        self.tabs.addTab(host, "Salary Review")

    # -- Vouchers
    def _build_vouchers_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        ctrl = QHBoxLayout()
        self.v_emp = QComboBox()
        for emp_id, name, code in _employees():
            self.v_emp.addItem(f"{name} ({code})", emp_id)
        self.v_month = QComboBox(); self.v_month.addItems(_month_names())
        self.v_year = QComboBox()
        this_year = date.today().year
        self.v_year.addItems([str(y) for y in range(this_year - 5, this_year + 6)])
        self.v_year.setCurrentText(str(this_year))

        ctrl.addWidget(QLabel("Employee")); ctrl.addWidget(self.v_emp)
        ctrl.addSpacing(12)
        ctrl.addWidget(QLabel("Month")); ctrl.addWidget(self.v_month)
        ctrl.addSpacing(12)
        ctrl.addWidget(QLabel("Year")); ctrl.addWidget(self.v_year)
        ctrl.addStretch(1)

        self.btn_pdf = QPushButton("Export PDF")
        self.btn_pdf.clicked.connect(self._export_voucher_pdf)
        ctrl.addWidget(self.btn_pdf)
        v.addLayout(ctrl)

        # centered, non-stretch preview
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        self.v_preview = QTextEdit()
        self.v_preview.setReadOnly(True)
        self.v_preview.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.v_preview.setMinimumWidth(820)
        self.v_preview.setMaximumWidth(820)
        self.v_preview.setMinimumHeight(900)
        wrap.addWidget(self.v_preview)
        wrap.addStretch(1)
        v.addLayout(wrap)

        self.tabs.addTab(host, "Salary Vouchers")

        # react
        self.v_emp.currentIndexChanged.connect(self._refresh_voucher_preview)
        self.v_month.currentIndexChanged.connect(self._refresh_voucher_preview)
        self.v_year.currentIndexChanged.connect(self._refresh_voucher_preview)
        self._refresh_voucher_preview()

    def _refresh_voucher_preview(self):
        emp_id = self.v_emp.currentData()
        m1 = (self.v_month.currentIndex() + 1) or 1
        y = int(self.v_year.currentText())
        with SessionLocal() as s:
            emp = s.get(Employee, emp_id) if emp_id else None
        html = _voucher_html(_company(), emp, y, m1)
        self.v_preview.setHtml(html)

    def _export_voucher_pdf(self):
        emp_label = self.v_emp.currentText() or "employee"
        m1 = self.v_month.currentIndex() + 1
        y = int(self.v_year.currentText())
        mn = _month_names()[m1 - 1]
        default_name = f"SalaryVoucher_{emp_label.replace(' ', '_')}_{y}_{mn}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Export Voucher PDF", default_name, "PDF Files (*.pdf)")
        if not path:
            return

        doc = QTextDocument()
        doc.setHtml(self.v_preview.toHtml())

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        # Qt6 page setup
        printer.setPageSize(QPageSize(QPageSize.A4))
        layout = printer.pageLayout()
        layout.setOrientation(QPageLayout.Portrait)
        layout.setMargins(QMarginsF(10, 12, 10, 12))  # mm
        printer.setPageLayout(layout)

        printer.setOutputFileName(path)
        doc.print_(printer)

    # -- Settings
    def _build_settings_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        voucher_box = QGroupBox("Voucher Settings")
        f = QFormLayout(voucher_box)
        self.voucher_format = QLineEdit("SV-{YYYY}{MM}-{EMP}")
        self.voucher_format.setMaximumWidth(320)
        self.voucher_preview = QLabel("Preview: SV-202501-EMP001")
        btn_preview = QPushButton("Preview Code"); btn_preview.setMaximumWidth(140)

        def _preview_code():
            sample = (self.voucher_format.text() or "SV-{YYYY}{MM}-{EMP}")
            code = sample.replace("{YYYY}", "2025").replace("{MM}", "01").replace("{EMP}", "EMP001")
            self.voucher_preview.setText(f"Preview: {code}")

        btn_preview.clicked.connect(_preview_code)
        f.addRow("Format", self.voucher_format)
        f.addRow("", btn_preview)
        f.addRow("", self.voucher_preview)

        cpf_box = QGroupBox("CPF Table")
        shg_box = QGroupBox("SHG Table")
        sdl_box = QGroupBox("SDL Table")

        def _grid(box: QGroupBox, headers: List[str]) -> QTableWidget:
            lay = QVBoxLayout(box)
            tbl = QTableWidget(0, len(headers))
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            tbl.setEditTriggers(QTableWidget.AllEditTriggers)
            btns = QHBoxLayout()
            btn_add = QPushButton("Add Row"); btn_del = QPushButton("Delete Row"); btn_imp = QPushButton("Import CSV")
            btn_add.setMaximumWidth(120); btn_del.setMaximumWidth(120); btn_imp.setMaximumWidth(120)

            def add_row():
                tbl.insertRow(tbl.rowCount())

            def del_row():
                rngs = tbl.selectedRanges()
                if not rngs:
                    return
                rng: QTableWidgetSelectionRange = rngs[0]
                for r in range(rng.bottomRow(), rng.topRow() - 1, -1):
                    tbl.removeRow(r)

            def import_csv():
                QFileDialog.getOpenFileName(box, "Import CSV", "", "CSV Files (*.csv)")

            btn_add.clicked.connect(add_row)
            btn_del.clicked.connect(del_row)
            btn_imp.clicked.connect(import_csv)
            btns.addWidget(btn_add); btns.addWidget(btn_del); btns.addWidget(btn_imp); btns.addStretch(1)
            lay.addWidget(tbl); lay.addLayout(btns)
            return tbl

        self.cpf_tbl = _grid(cpf_box, ["Age Bracket", "Residency", "Employee %", "Employer %", "Wage Ceiling"])
        self.shg_tbl = _grid(shg_box, ["Race", "Income From", "Income To", "Contribution"])
        self.sdl_tbl = _grid(sdl_box, ["Salary From", "Salary To", "Rate / Formula"])

        v.addWidget(voucher_box)
        v.addWidget(cpf_box)
        v.addWidget(shg_box)
        v.addWidget(sdl_box)
        v.addStretch(1)

        self.tabs.addTab(host, "Settings")
