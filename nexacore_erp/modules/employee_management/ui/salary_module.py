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
    # company
    company_name = (cs.name if cs else "") or "Company Name"
    detail1 = (cs.detail1 if cs else "") or "Company details line 1"
    detail2 = (cs.detail2 if cs else "") or "Company details line 2"
    logo_html = _img_data_uri(getattr(cs, "logo", None), "Logo")

    # employee snapshot
    emp_name = getattr(emp, "full_name", "") or "—"
    emp_code = getattr(emp, "code", "") or "—"
    dept     = getattr(emp, "department", "") or "—"
    pos      = getattr(emp, "position", "") or "—"
    bank     = getattr(emp, "bank", "") or "—"
    acct     = getattr(emp, "bank_account", "") or "—"

    # figures (placeholders until wired)
    basic   = float(getattr(emp, "basic_salary", 0.0) or 0.0)
    comm    = float(getattr(emp, "commission", 0.0) or 0.0)
    incent  = float(getattr(emp, "incentives", 0.0) or 0.0)
    allow   = float(getattr(emp, "allowance", 0.0) or 0.0)

    ot_rate = float(getattr(emp, "overtime_rate", 0.0) or 0.0)
    ot_hrs  = float(getattr(emp, "overtime_hours", 0.0) or 0.0); ot_amt = ot_rate * ot_hrs
    pt_rate = float(getattr(emp, "parttime_rate", 0.0) or 0.0)
    pt_hrs  = float(getattr(emp, "part_time_hours", 0.0) or 0.0); pt_amt = pt_rate * pt_hrs

    cpf_er  = float(getattr(emp, "cpf_employer", 0.0) or 0.0)   # income
    sdl     = float(getattr(emp, "sdl", 0.0) or 0.0)            # income
    cpf_emp = float(getattr(emp, "cpf_employee", 0.0) or 0.0)   # deduction
    shg     = float(getattr(emp, "shg", 0.0) or 0.0)            # deduction
    adv     = float(getattr(emp, "advance", 0.0) or 0.0)        # deduction

    total_income     = basic + comm + incent + allow + ot_amt + pt_amt + cpf_er + sdl
    total_deductions = cpf_emp + shg + adv
    total_net        = total_income - total_deductions
    total_cpf        = cpf_er + cpf_emp

    from calendar import month_name as _mn
    ym   = f"{_mn[month_index_1]} {year}"
    code = f"SV-{year}{month_index_1:02d}-{(getattr(emp, 'code', '') or 'EMP001')}"

    def money(x: float) -> str:
        try:
            return f"{float(x):,.2f}"
        except Exception:
            return "0.00"

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  /* Compact, gridless, print-safe */
  html,body{{margin:0;padding:0;background:#fff;color:#0f172a;font-family:Arial,Helvetica,sans-serif;font-size:10.5pt}}
  .page{{width:190mm;margin:0 auto;padding:12mm 10mm}}

  /* palette */
  .muted{{color:#5b6776}}
  .b0{{border:1px solid #d6d9df}}
  .b1{{border-top:1px solid #e6e9ef}}
  .cap{{background:#f6f8fb;border-bottom:1px solid #e6e9ef;font-weight:700;letter-spacing:.2px;padding:6px 8px}}

  table{{border-collapse:collapse;width:100%}}
  td,th{{padding:6px 8px;vertical-align:top}}
  .kv td.lbl{{width:32%;color:#394555}}
  .kv td.val{{width:68%;font-variant-numeric:tabular-nums}}

  .tbl td.lbl{{width:65%;color:#394555;border-top:1px solid #eef1f4}}
  .tbl td.val{{width:35%;text-align:right;font-variant-numeric:tabular-nums;border-top:1px solid #eef1f4}}

  .section-grid{{width:100%;border-collapse:separate;border-spacing:10px 0}}
  .tight{{margin:6px 0}}
  .title{{font-size:18pt;font-weight:800;color:#143d8c;margin:6px 0 8px}}

  .totals .lbl{{width:70%}}
  .totals .val{{width:30%;text-align:right;font-weight:700}}

  .bar{{background:#eaf0ff;border:1px solid #c8d6ff;border-radius:4px;padding:8px 10px;
        display:flex;justify-content:space-between;font-weight:800}}
</style>
</head>
<body>
  <div class="page">

    <!-- Header -->
    <table>
      <tr>
        <td style="width:110px;vertical-align:top">{logo_html}</td>
        <td style="vertical-align:top">
          <div style="font-size:15pt;font-weight:800">{html.escape(company_name)}</div>
          <div class="muted">{html.escape(detail1)}</div>
          <div class="muted">{html.escape(detail2)}</div>
        </td>
        <td style="width:210px;vertical-align:top;text-align:right">
          <div class="muted">{html.escape(ym)}</div>
          <div style="color:#143d8c">Code: <b>{html.escape(code)}</b></div>
        </td>
      </tr>
    </table>

    <div class="b1 tight"></div>
    <div class="title">Salary Voucher</div>

    <!-- Employee panel -->
    <div class="b0" style="border-radius:6px;overflow:hidden;margin-bottom:8px">
      <div class="cap">Employee</div>
      <table class="kv">
        <tr><td class="lbl">Employee</td><td class="val">{html.escape(emp_name)}</td></tr>
        <tr><td class="lbl">Employee Code</td><td class="val">{html.escape(emp_code)}</td></tr>
        <tr><td class="lbl">Department</td><td class="val">{html.escape(dept)}</td></tr>
        <tr><td class="lbl">Position</td><td class="val">{html.escape(pos)}</td></tr>
        <tr><td class="lbl">Bank</td><td class="val">{html.escape(bank)}</td></tr>
        <tr><td class="lbl">Account No.</td><td class="val">{html.escape(acct)}</td></tr>
      </table>
    </div>

    <!-- Earnings / Deductions -->
    <table class="section-grid">
      <tr>
        <td style="width:50%;vertical-align:top">
          <div class="b0" style="border-radius:6px;overflow:hidden">
            <div class="cap">Earnings</div>
            <table class="tbl">
              <tr><td class="lbl">Basic Salary</td><td class="val">{money(basic)}</td></tr>
              <tr><td class="lbl">Commission</td><td class="val">{money(comm)}</td></tr>
              <tr><td class="lbl">Incentives</td><td class="val">{money(incent)}</td></tr>
              <tr><td class="lbl">Allowance</td><td class="val">{money(allow)}</td></tr>
              <tr><td class="lbl">Overtime</td><td class="val">{money(ot_amt)}</td></tr>
              <tr><td class="lbl">Part-time</td><td class="val">{money(pt_amt)}</td></tr>
              <tr><td class="lbl">Employer CPF Contribution</td><td class="val">{money(cpf_er)}</td></tr>
              <tr><td class="lbl">SDL</td><td class="val">{money(sdl)}</td></tr>
            </table>
          </div>
        </td>
        <td style="width:50%;vertical-align:top">
          <div class="b0" style="border-radius:6px;overflow:hidden">
            <div class="cap">Deductions</div>
            <table class="tbl">
              <tr><td class="lbl">Employee CPF</td><td class="val">{money(cpf_emp)}</td></tr>
              <tr><td class="lbl">SHG</td><td class="val">{money(shg)}</td></tr>
              <tr><td class="lbl">Advance</td><td class="val">{money(adv)}</td></tr>
            </table>
          </div>
        </td>
      </tr>
    </table>

    <!-- Totals -->
    <div class="b0" style="border-radius:6px;overflow:hidden;margin-top:8px">
      <div class="cap">Totals</div>
      <table class="totals" style="width:100%">
        <tr><td class="lbl">Total Gross Salary</td><td class="val">{money(total_income)}</td></tr>
        <tr><td class="lbl">Total Deductions</td><td class="val">{money(total_deductions)}</td></tr>
        <tr><td class="lbl">Total CPF (ER + EE)</td><td class="val">{money(total_cpf)}</td></tr>
      </table>
    </div>

    <!-- Net Pay -->
    <div class="bar" style="margin-top:8px">
      <div>Net Pay</div>
      <div>{money(total_net)}</div>
    </div>

    <!-- Footer -->
    <table style="width:100%;margin-top:12px">
      <tr>
        <td style="width:50%">
          <div class="muted" style="font-weight:700">Prepared by</div>
          <div>{html.escape(company_name)}</div>
        </td>
        <td style="width:50%;text-align:right" class="muted">
          Employee Acknowledgement
        </td>
      </tr>
    </table>

  </div>
</body>
</html>
"""


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
