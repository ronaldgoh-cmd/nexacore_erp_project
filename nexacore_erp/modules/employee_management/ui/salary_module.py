# salary_module.py
from __future__ import annotations

import base64
from calendar import month_name
from datetime import date
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
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
            f"{b64}\" style=\"max-height:48px;max-width:120px;object-fit:contain;\"/>"
        )
    return (
        "<div style=\"height:48px;width:120px;border:1px solid #cfcfcf;border-radius:6px;"
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
    from calendar import month_name
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

    # amounts (placeholders until review is wired)
    basic   = float(getattr(emp, "basic_salary", 0.0) or 0.0)
    comm    = 0.0
    incent  = float(getattr(emp, "incentives", 0.0) or 0.0)
    allow   = float(getattr(emp, "allowance", 0.0) or 0.0)
    ot_rate = float(getattr(emp, "overtime_rate", 0.0) or 0.0); ot_hrs = 0.0; ot_amt = ot_rate * ot_hrs
    pt_rate = float(getattr(emp, "parttime_rate", 0.0) or 0.0); pt_hrs = 0.0; pt_amt = pt_rate * pt_hrs
    levy    = float(getattr(emp, "levy", 0.0) or 0.0)

    gross = basic + comm + incent + allow + ot_amt + pt_amt
    emp_cpf = 0.0; shg = 0.0; sdl = 0.0
    deductions = emp_cpf + shg + sdl + levy
    net_pay = max(0.0, gross - deductions)

    ym   = f"{month_name[month_index_1]} {year}"
    code = f"SV-{year}{month_index_1:02d}-{(emp.code or 'TST-0001') if emp else 'TST-0001'}"

    # A4 portrait look: width ≈ 794px @96 dpi. Keep inside border so it prints as a full page.
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  :root {{
    --sheet-w: 794px;          /* ~A4 width @96dpi */
    --sheet-pad: 18px;         /* ~7mm */
    --gap: 16px;
    --border: #e5e7eb;
    --muted: #6b7280;
  }}
  body {{ background:#fff; font-family:'Segoe UI', Arial, sans-serif; color:#111827; }}
  .sheet {{
    width: var(--sheet-w);
    margin: 0 auto;
    border: 1px solid var(--border);
    box-sizing: border-box;
    padding: var(--sheet-pad);
  }}

  .hdr {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }}
  .brand {{ display:flex; gap:12px; align-items:center; }}
  .cname {{ font-size:18px; font-weight:800; }}
  .cline {{ font-size:12px; color:var(--muted); line-height:1.2; }}
  .hrule {{ height:1px; background:var(--border); margin:10px 0 12px; }}

  .title {{ font-size:26px; font-weight:800; color:#2563eb; margin:8px 0; }}
  .rmeta {{ text-align:right; font-size:13px; color:#334155; }}

  .panel {{ border:1px solid var(--border); border-radius:6px; padding:12px; }}
  .kv {{ display:grid; grid-template-columns: 170px 1fr 150px 1fr; gap:8px 14px; }}
  .kv .k {{ font-weight:700; color:#374151; }}

  .cols {{ display:grid; grid-template-columns: 1fr 1fr; gap: var(--gap); margin-top:12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ padding:8px 10px; }}
  .sec {{ border:1px solid var(--border); border-radius:6px; overflow:hidden; }}
  .sec .cap {{ padding:10px; font-weight:700; background:#f8fafc; border-bottom:1px solid var(--border); }}
  .sec tbody tr td {{ border-top:1px solid #f1f5f9; }}
  .right {{ text-align:right; }}

  .notice {{ margin:12px 0; background:#fffbeb; border:1px solid #f59e0b; color:#92400e;
            border-radius:6px; padding:8px 10px; font-size:13px; }}
  .net {{ margin-top:10px; background:#e6f0ff; border:1px solid #bfdbfe; border-radius:6px;
         padding:12px 14px; display:flex; justify-content:space-between; font-weight:800; }}

  .notes {{ margin-top:10px; font-size:12px; color:#475569; }}
  .foot {{ display:flex; justify-content:space-between; align-items:flex-end; margin-top:28px; font-size:12px; color:#6b7280; }}
  .sig {{ width:44%; text-align:center; }}
  .sig hr {{ border:none; border-top:1px solid #cbd5e1; margin:28px 0 6px; }}
</style>
</head>
<body>
  <div class="sheet">
    <div class="hdr">
      <div class="brand">
        {logo_html}
        <div>
          <div class="cname">{html.escape(company_name)}</div>
          <div class="cline">{html.escape(detail1)}</div>
          <div class="cline">{html.escape(detail2)}</div>
        </div>
      </div>
      <div class="rmeta">
        <div>{ym}</div>
        <div>Code: <b>{code}</b></div>
      </div>
    </div>

    <div class="title">Salary Voucher</div>
    <div class="hrule"></div>

    <div class="panel">
      <div class="kv">
        <div class="k">Employee</div><div>{emp_name}</div>
        <div class="k">Employee Code</div><div>{emp_code}</div>
        <div class="k">Department</div><div>{dept}</div>
        <div class="k">Position</div><div>{pos}</div>
        <div class="k">Bank</div><div>{bank}</div>
        <div class="k">Account No.</div><div>{acct}</div>
      </div>
    </div>

    <div class="cols">
      <div class="sec">
        <div class="cap">Earnings</div>
        <table>
          <tbody>
            <tr><td>Basic Salary</td><td class="right">{basic:.2f}</td></tr>
            <tr><td>Commission</td><td class="right">{comm:.2f}</td></tr>
            <tr><td>Incentives</td><td class="right">{incent:.2f}</td></tr>
            <tr><td>Allowance</td><td class="right">{allow:.2f}</td></tr>
            <tr><td>Overtime</td><td class="right">{ot_amt:.2f}</td></tr>
            <tr><td>Part-time</td><td class="right">{pt_amt:.2f}</td></tr>
            <tr><td><b>Gross Pay</b></td><td class="right"><b>{gross:.2f}</b></td></tr>
          </tbody>
        </table>
      </div>

      <div class="sec">
        <div class="cap">Deductions</div>
        <table>
          <tbody>
            <tr><td>Employee CPF</td><td class="right">{emp_cpf:.2f}</td></tr>
            <tr><td>SHG</td><td class="right">{shg:.2f}</td></tr>
            <tr><td>SDL</td><td class="right">{sdl:.2f}</td></tr>
            <tr><td>Levy</td><td class="right">{levy:.2f}</td></tr>
            <tr><td><b>Total Deductions</b></td><td class="right"><b>{deductions:.2f}</b></td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="notice">No Salary Review entry found for <b>{emp_name}</b> in <b>{ym}</b>.</div>

    <div class="net"><div>Net Pay</div><div>{net_pay:.2f}</div></div>

    <div class="notes">
      Figures reflect the Salary Review for the selected period. If none exists, this preview shows zeros and a notice.
      CPF and statutory values will be populated from tables once configured.
    </div>

    <div class="foot">
      <div class="sig"><hr/>Prepared by: {html.escape(company_name)}</div>
      <div class="sig"><hr/>Employee Acknowledgement</div>
    </div>
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
        printer.setPageSize(QPrinter.A4)  # force A4
        printer.setOutputFileName(path)
        printer.setPageMargins(10, 10, 10, 10, QPrinter.Millimeter)  # ~10mm margins

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
