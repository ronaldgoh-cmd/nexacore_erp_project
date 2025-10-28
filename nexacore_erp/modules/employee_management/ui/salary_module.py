# salary_module.py
from __future__ import annotations

import base64
from calendar import month_name
from datetime import date
from typing import List, Tuple, Optional

from PySide6.QtCore import Qt, QMarginsF
from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout, QFont, QPixmap
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTableWidget,
    QTableWidgetItem, QPushButton, QComboBox, QFileDialog, QHeaderView, QGroupBox,
    QFormLayout, QTextBrowser, QTableWidgetSelectionRange, QSizePolicy, QScrollArea, QFrame
)

from ....core.database import get_employee_session as SessionLocal
from ....core.tenant import id as tenant_id
from ..models import Employee
from ....core.models import CompanySettings


# ---------- globals / helpers ----------
_VOUCHER_FMT = "SV-{YYYY}{MM}-{EMP}"           # editable from Settings
_STAMP_B64: Optional[str] = None               # set from Settings → Upload Company Stamp


def _format_voucher_code(emp: Employee | None, year: int, month_index_1: int) -> str:
    tpl = globals().get("_VOUCHER_FMT", "SV-{YYYY}{MM}-{EMP}") or "SV-{YYYY}{MM}-{EMP}"
    emp_code = (getattr(emp, "code", "") or "EMP001")
    mm = f"{month_index_1:02d}"
    return (tpl.replace("{YYYY}", str(year))
               .replace("{MM}", mm)
               .replace("{EMP}", emp_code))


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


def _stamp_img_html(cs: CompanySettings | None) -> str:
    # pick global in-memory stamp first; else CompanySettings.stamp if present
    b64 = _STAMP_B64
    if not b64:
        raw = getattr(cs, "stamp", None)
        if raw:
            b64 = base64.b64encode(raw).decode("ascii")
    if not b64:
        return ""
    # light opacity, auto-size within box
    return (
        "<img src=\"data:image/png;base64," + b64 +
        "\" style=\"max-height:120px;max-width:220px;opacity:0.75;object-fit:contain;\"/>"
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
    stamp_html = _stamp_img_html(cs)

    # --- employee snapshot ---
    emp_name = getattr(emp, "full_name", "") or "—"
    emp_code = getattr(emp, "code", "") or "—"
    id_no    = getattr(emp, "identification_number", "") or getattr(emp, "nric", "") or "—"
    bank     = getattr(emp, "bank", "") or "—"
    acct     = getattr(emp, "bank_account", "") or "—"

    # --- figures ---
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

    advance = float(getattr(emp, "advance", 0.0) or 0.0)
    shg     = float(getattr(emp, "shg", 0.0) or 0.0)

    cpf_emp = float(getattr(emp, "cpf_employee", 0.0) or 0.0)
    cpf_er  = float(getattr(emp, "cpf_employer", 0.0) or 0.0)
    cpf_total = cpf_emp + cpf_er

    sdl  = float(getattr(emp, "sdl", 0.0) or 0.0)
    levy = float(getattr(emp, "levy", 0.0) or 0.0)

    gross = basic + comm + incent + allow + pt_amt + ot_amt
    ded_only = advance + shg
    net_pay = gross - ded_only - cpf_emp

    ym = f"{month_name[month_index_1]} {year}"
    code = _format_voucher_code(emp, year, month_index_1)

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
  html, body {{ font-size: 13px; }}
  body {{ margin:0; background:#ffffff; color:#111827; font-family:Segoe UI, Arial, sans-serif; }}
  .page {{ width:794px; margin:0 auto; padding:24px 18px; }}   /* thinner padding to improve on-screen scroll */
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

    <!-- Header -->
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

    <!-- Employee box -->
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

    <!-- Signatures + Stamp -->
    <table cellpadding="0" cellspacing="0" width="100%" style="margin-top:22px">
      <tr>
        <td style="width:50%;vertical-align:bottom">
          <div style="font-weight:bold">Prepared by: {html.escape(company_name)}</div>
        </td>
        <td style="width:50%;text-align:right;vertical-align:bottom">
          {stamp_html}
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

        # in-memory stamp mirror for preview
        self._company_stamp_b64: Optional[str] = None

        self._build_summary_tab()
        self._build_salary_review_tab()
        self._build_vouchers_tab()
        self._build_settings_tab()

        # try preload stamp from CompanySettings
        cs = _company()
        raw = getattr(cs, "stamp", None)
        if raw and not self._company_stamp_b64:
            try:
                self._company_stamp_b64 = base64.b64encode(raw).decode("ascii")
                globals()["_STAMP_B64"] = self._company_stamp_b64
            except Exception:
                pass

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

    def _build_salary_review_tab(self):
        from datetime import date, datetime
        from calendar import monthrange
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
            QTableWidget, QTableWidgetItem, QDialog, QGridLayout, QLineEdit,
            QDialogButtonBox, QMessageBox
        )
        from sqlalchemy import text

        # ---------- helpers from Settings tab ----------
        def _rf(x):
            try:
                return float(str(x).replace(",", "").replace("%", "").strip())
            except Exception:
                return 0.0

        def _age(emp, on_date):
            dob = getattr(emp, "dob", None) or getattr(emp, "date_of_birth", None)
            if not dob:
                return 30
            try:
                if isinstance(dob, str):
                    p = [int(t) for t in dob.replace("/", "-").split("-")]
                    if p[0] > 1900:
                        y, m, d = (p + [1, 1])[0:3]
                    else:
                        d, m, y = (p + [1, 1])[0:3]
                    dob = date(y, m, d)
            except Exception:
                return 30
            return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))

        def _cpf_rows():
            rows = []
            tbl = getattr(self, "cpf_tbl", None)
            if not tbl:
                return rows
            for r in range(tbl.rowCount()):
                age_br = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
                resid = (tbl.item(r, 1).text().strip() if tbl.item(r, 1) else "")
                ee_pct = _rf(tbl.item(r, 2).text() if tbl.item(r, 2) else "0")
                er_pct = _rf(tbl.item(r, 3).text() if tbl.item(r, 3) else "0")
                ceil = _rf(tbl.item(r, 4).text() if tbl.item(r, 4) else "0")
                rows.append((age_br, resid, ee_pct, er_pct, ceil))
            return rows

        def _match_age(br, a):
            b = (br or "").replace(" ", "")
            try:
                if "-" in b:
                    lo, hi = b.split("-")
                    return int(lo) <= a <= int(hi)
                if b.startswith("<="): return a <= int(b[2:])
                if b.startswith("<"):  return a < int(b[1:])
                if b.startswith(">="): return a >= int(b[2:])
                if b.startswith(">"):  return a > int(b[1:])
                if b.isdigit():         return a >= int(b)
            except Exception:
                return True
            return True

        def _cpf_for(emp, gross, on_date):
            resid = (getattr(emp, "residency", "") or "").strip()
            a = _age(emp, on_date)
            for age_br, resid_row, ee_pct, er_pct, ceil in _cpf_rows():
                if resid_row.lower() == resid.lower() and _match_age(age_br, a):
                    base = min(gross, ceil) if ceil else gross
                    ee = round(base * (ee_pct / 100.0), 2)
                    er = round(base * (er_pct / 100.0), 2)
                    return ee, er, round(ee + er, 2)
            return 0.0, 0.0, 0.0

        def _shg_rows():
            rows = []
            tbl = getattr(self, "shg_tbl", None)
            if not tbl:
                return rows
            for r in range(tbl.rowCount()):
                race = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
                lo = _rf(tbl.item(r, 1).text() if tbl.item(r, 1) else "0")
                hi = _rf(tbl.item(r, 2).text() if tbl.item(r, 2) else "0")
                val = _rf(tbl.item(r, 3).text() if tbl.item(r, 3) else "0")
                rows.append((race.lower(), lo, hi, val))
            return rows

        def _shg_for(emp, total):
            race = (getattr(emp, "race", "") or "").lower()
            for rc, lo, hi, val in _shg_rows():
                if (rc == race or rc in ("any", "all", "")) and (lo <= total <= (hi or total)):
                    return float(val)
            return 0.0

        def _sdl_rows():
            rows = []
            tbl = getattr(self, "sdl_tbl", None)
            if not tbl:
                return rows
            for r in range(tbl.rowCount()):
                lo = _rf(tbl.item(r, 0).text() if tbl.item(r, 0) else "0")
                hi = _rf(tbl.item(r, 1).text() if tbl.item(r, 1) else "0")
                rule = (tbl.item(r, 2).text().strip() if tbl.item(r, 2) else "")
                rows.append((lo, hi, rule))
            return rows

        def _sdl_for(total):
            for lo, hi, rule in _sdl_rows():
                if lo <= total <= (hi or total):
                    r = rule.lower()
                    if r.startswith("flat:"):
                        try:
                            return float(r.split(":", 1)[1].strip())
                        except Exception:
                            return 0.0
                    pct = _rf(r)  # "0.25%" or "0.25"
                    return round(total * (pct / 100.0), 2)
            return 0.0

        # ---------- DB bootstrapping ----------
        def _ensure_tables():
            with SessionLocal() as s:
                s.execute(text("""
                CREATE TABLE IF NOT EXISTS payroll_batches(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  year INTEGER NOT NULL,
                  month INTEGER NOT NULL,
                  status TEXT NOT NULL DEFAULT 'Draft',
                  total_basic REAL DEFAULT 0,
                  total_er REAL DEFAULT 0,
                  grand_total REAL DEFAULT 0,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """))
                s.execute(text("""
                CREATE TABLE IF NOT EXISTS payroll_batch_lines(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  batch_id INTEGER NOT NULL,
                  employee_id INTEGER NOT NULL,
                  basic_salary REAL DEFAULT 0,
                  commission REAL DEFAULT 0,
                  incentives REAL DEFAULT 0,
                  allowance REAL DEFAULT 0,
                  overtime_rate REAL DEFAULT 0,
                  overtime_hours REAL DEFAULT 0,
                  part_time_rate REAL DEFAULT 0,
                  part_time_hours REAL DEFAULT 0,
                  levy REAL DEFAULT 0,
                  shg REAL DEFAULT 0,
                  sdl REAL DEFAULT 0,
                  cpf_emp REAL DEFAULT 0,
                  cpf_er REAL DEFAULT 0,
                  cpf_total REAL DEFAULT 0,
                  line_total REAL DEFAULT 0,         -- gross earnings
                  ee_contrib REAL DEFAULT 0,         -- ee cpf + shg
                  er_contrib REAL DEFAULT 0,         -- er cpf + sdl + levy
                  total_cash REAL DEFAULT 0          -- g - ee cpf - shg
                );
                """))
                s.commit()

        def _active_employees(y, m):
            som = date(y, m, 1)
            eom = date(y, m, monthrange(y, m)[1])
            rows = []
            with SessionLocal() as s:
                emps = s.query(Employee).filter(Employee.account_id == tenant_id()).all()

            def _parse(d):
                if not d: return None
                if isinstance(d, date): return d
                try:
                    p = [int(t) for t in str(d).replace("/", "-").split("-")]
                    if p[0] > 1900:
                        y0, m0, d0 = (p + [1, 1])[:3]
                    else:
                        d0, m0, y0 = (p + [1, 1])[:3]
                    return date(y0, m0, d0)
                except Exception:
                    return None

            for e in emps:
                jd = _parse(getattr(e, "date_employment", None) or getattr(e, "join_date", None))
                xd = _parse(getattr(e, "date_exit", None) or getattr(e, "exit_date", None))
                if jd and jd > eom:
                    continue
                if xd and xd < som:
                    continue
                rows.append(e)
            return rows

        # ---------- UI: batches list ----------
        host = QWidget()
        v = QVBoxLayout(host)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Month"))
        cb_month = QComboBox()
        cb_month.addItems(_month_names())
        cb_month.setCurrentIndex(date.today().month - 1)
        toolbar.addWidget(cb_month)
        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("Year"))
        cb_year = QComboBox()
        this_year = date.today().year
        cb_year.addItems([str(y) for y in range(this_year - 5, this_year + 6)])
        cb_year.setCurrentText(str(this_year))
        toolbar.addWidget(cb_year)
        toolbar.addStretch(1)

        btn_create = QPushButton("Create…")
        btn_edit = QPushButton("Edit…")
        btn_view = QPushButton("View…")
        btn_submit = QPushButton("Submit")
        btn_delete = QPushButton("Delete")
        btn_refresh = QPushButton("Refresh")
        for b in (btn_create, btn_edit, btn_view, btn_submit, btn_delete, btn_refresh):
            toolbar.addWidget(b)

        v.addLayout(toolbar)

        tbl = QTableWidget(0, 6)
        tbl.setHorizontalHeaderLabels(["Year", "Month", "Total Basic", "Total Employer", "Grand Total", "Status"])
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setSelectionMode(QTableWidget.SingleSelection)
        tbl.setSortingEnabled(True)
        v.addWidget(tbl, 1)

        self.tabs.addTab(host, "Salary Review")

        # ---------- data ops ----------
        _ensure_tables()

        def _load_batches():
            tbl.setRowCount(0)
            with SessionLocal() as s:
                rows = s.execute(text("""
                  SELECT id, year, month, total_basic, total_er, grand_total, status
                  FROM payroll_batches
                  ORDER BY year DESC, month DESC, id DESC
                """)).fetchall()
            for _id, y, m, tb, ter, gt, st in rows:
                r = tbl.rowCount()
                tbl.insertRow(r)

                def item(val):
                    it = QTableWidgetItem(f"{val}")
                    it.setData(Qt.UserRole, _id)
                    return it

                tbl.setItem(r, 0, item(y))
                tbl.setItem(r, 1, item(m))
                tbl.setItem(r, 2, QTableWidgetItem(f"{(tb or 0):,.2f}"))
                tbl.setItem(r, 3, QTableWidgetItem(f"{(ter or 0):,.2f}"))
                tbl.setItem(r, 4, QTableWidgetItem(f"{(gt or 0):,.2f}"))
                tbl.setItem(r, 5, QTableWidgetItem(st or "Draft"))

        _load_batches()

        def _selected_batch_id():
            r = tbl.currentRow()
            if r < 0: return None
            return tbl.item(r, 0).data(Qt.UserRole)

        # ---------- dialog builder ----------
        COLS = [
            "Name", "Basic", "Commission", "Incentives", "Allowance",
            "OT Rate", "OT Hours", "PT Rate", "PT Hours",
            "Total", "Levy", "SHG", "SDL",
            "CPF EE", "CPF ER", "CPF Total",
            "EE Contrib", "ER Contrib", "Cash Payout"
        ]
        EDITABLE = {1, 2, 3, 4, 5, 6, 7, 8, 10}  # editable column indexes

        def _recalc_row(t, row_idx, emp_obj, on_date):
            f = lambda c: _rf(t.item(row_idx, c).text()) if t.item(row_idx, c) else 0.0
            basic, com, inc, allw = f(1), f(2), f(3), f(4)
            ot_r, ot_h, pt_r, pt_h = f(5), f(6), f(7), f(8)
            levy = f(10)
            gross = basic + com + inc + allw + (ot_r * ot_h) + (pt_r * pt_h)
            shg = _shg_for(emp_obj, gross)
            sdl = _sdl_for(gross)
            ee, er, cpf_t = _cpf_for(emp_obj, gross, on_date)
            ee_c = ee + shg
            er_c = er + sdl + levy
            cash = gross - ee - shg

            def setv(c, val):
                it = QTableWidgetItem(f"{val:,.2f}")
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(row_idx, c, it)

            setv(9, gross)
            setv(11, shg)
            setv(12, sdl)
            setv(13, ee)
            setv(14, er)
            setv(15, cpf_t)
            setv(16, ee_c)
            setv(17, er_c)
            setv(18, cash)

        def _recalc_totals(t):
            sums = [0.0] * t.columnCount()
            for r in range(t.rowCount()):
                for c in range(t.columnCount()):
                    try:
                        sums[c] += float(str(t.item(r, c).text()).replace(",", ""))
                    except Exception:
                        pass
            return {
                "total_basic": sums[1],
                "total_er": sums[17],
                "grand_total": sums[18] + sums[17]  # payroll cost = cash + employer contrib
            }

        def _open_batch_dialog(batch_id=None, read_only=False, y=None, m=None):
            # load or start new
            if batch_id:
                with SessionLocal() as s:
                    b = s.execute(text("SELECT year, month, status FROM payroll_batches WHERE id=:i"),
                                  {"i": batch_id}).fetchone()
                    if not b:
                        QMessageBox.warning(host, "Salary Review", "Batch not found.")
                        return
                    y, m, status = int(b.year), int(b.month), b.status
                    if status == "Submitted" and not read_only:
                        QMessageBox.information(host, "Salary Review", "Batch is submitted. Opening in view mode.")
                        read_only = True

            dlg = QDialog(self)
            dlg.setWindowTitle("Salary Review")
            lay = QVBoxLayout(dlg)

            hdr = QHBoxLayout()
            hdr.addWidget(QLabel(f"Period: {month_name[m]} {y}"))
            hdr.addStretch(1)
            lay.addLayout(hdr)

            grid = QTableWidget(0, len(COLS))
            grid.setHorizontalHeaderLabels(COLS)
            lay.addWidget(grid, 1)

            som = date(y, m, 1)
            on_date = date(y, m, monthrange(y, m)[1])

            row_emps = []  # keep employee objects per row

            if batch_id:
                with SessionLocal() as s:
                    lines = s.execute(text("""
                      SELECT l.employee_id, e.full_name,
                             l.basic_salary, l.commission, l.incentives, l.allowance,
                             l.overtime_rate, l.overtime_hours, l.part_time_rate, l.part_time_hours,
                             l.levy, l.shg, l.sdl, l.cpf_emp, l.cpf_er, l.cpf_total,
                             l.ee_contrib, l.er_contrib, l.total_cash
                      FROM payroll_batch_lines l
                      JOIN employees e ON e.id = l.employee_id
                      WHERE l.batch_id=:b
                      ORDER BY e.full_name COLLATE NOCASE ASC
                    """), {"b": batch_id}).fetchall()
                for ln in lines:
                    r = grid.rowCount()
                    grid.insertRow(r)
                    vals = [
                        ln.full_name, ln.basic_salary, ln.commission, ln.incentives, ln.allowance,
                        ln.overtime_rate, ln.overtime_hours, ln.part_time_rate, ln.part_time_hours,
                        ln.basic_salary + ln.commission + ln.incentives + ln.allowance + (
                                ln.overtime_rate * ln.overtime_hours) + (ln.part_time_rate * ln.part_time_hours),
                        ln.levy, ln.shg, ln.sdl, ln.cpf_emp, ln.cpf_er, ln.cpf_total, ln.ee_contrib, ln.er_contrib,
                        ln.total_cash
                    ]
                    for c, v in enumerate(vals):
                        it = QTableWidgetItem(f"{v}" if c == 0 else f"{float(v):,.2f}")
                        if c != 0:
                            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        editable = (c in EDITABLE) and (not read_only)
                        it.setFlags((it.flags() | Qt.ItemIsEditable) if editable else (it.flags() & ~Qt.ItemIsEditable))
                        grid.setItem(r, c, it)
                    with SessionLocal() as s:
                        row_emps.append(s.get(Employee, int(ln.employee_id)))
            else:
                # new batch: all active employees
                emps = _active_employees(y, m)
                emps.sort(key=lambda e: (e.full_name or "").lower())
                for e in emps:
                    r = grid.rowCount()
                    grid.insertRow(r)

                    def num(x):
                        it = QTableWidgetItem(f"{float(x):,.2f}")
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        return it

                    name = QTableWidgetItem(e.full_name or "")
                    for c in range(len(COLS)):
                        grid.setItem(r, c, QTableWidgetItem(""))
                    grid.setItem(r, 0, name)
                    grid.setItem(r, 1, num(getattr(e, "basic_salary", 0.0)))
                    grid.setItem(r, 2, num(0.0))
                    grid.setItem(r, 3, num(getattr(e, "incentives", 0.0)))
                    grid.setItem(r, 4, num(getattr(e, "allowance", 0.0)))
                    grid.setItem(r, 5, num(getattr(e, "overtime_rate", 0.0)))
                    grid.setItem(r, 6, num(0.0))
                    grid.setItem(r, 7, num(getattr(e, "parttime_rate", 0.0)))
                    grid.setItem(r, 8, num(0.0))
                    grid.setItem(r, 10, num(getattr(e, "levy", 0.0)))
                    for c in range(len(COLS)):
                        if c in EDITABLE:
                            it = grid.item(r, c)
                            it.setFlags(it.flags() | Qt.ItemIsEditable)
                        else:
                            it = grid.item(r, c)
                            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    row_emps.append(e)

            # initial calc
            for r, e in enumerate(row_emps):
                _recalc_row(grid, r, e, on_date)

            if not read_only:
                def _cell_changed(r, c):
                    if c not in EDITABLE: return
                    _recalc_row(grid, r, row_emps[r], on_date)

                grid.cellChanged.connect(_cell_changed)

            # buttons
            btns = QDialogButtonBox(parent=dlg)
            if read_only:
                btns.addButton(QDialogButtonBox.Close)
            else:
                btn_save = btns.addButton("Save", QDialogButtonBox.AcceptRole)
                btn_submit = btns.addButton("Submit", QDialogButtonBox.ActionRole)
                btn_close = btns.addButton(QDialogButtonBox.Close)
                btn_submit.setToolTip("Lock this period. No further edits.")
            lay.addWidget(btns)

            def _persist(status=None):
                totals = _recalc_totals(grid)
                with SessionLocal() as s:
                    if batch_id is None:
                        r = s.execute(text(
                            "INSERT INTO payroll_batches(year,month,status,total_basic,total_er,grand_total) "
                            "VALUES(:y,:m,:st,:tb,:ter,:gt)"),
                            {"y": y, "m": m, "st": status or "Draft",
                             "tb": totals["total_basic"], "ter": totals["total_er"], "gt": totals["grand_total"]})
                        batch_id_local = r.lastrowid
                    else:
                        batch_id_local = batch_id
                        s.execute(text(
                            "UPDATE payroll_batches SET status=:st,total_basic=:tb,total_er=:ter,grand_total=:gt WHERE id=:i"),
                            {"st": status or "Draft", "tb": totals["total_basic"], "ter": totals["total_er"],
                             "gt": totals["grand_total"], "i": batch_id_local})
                        s.execute(text("DELETE FROM payroll_batch_lines WHERE batch_id=:i"), {"i": batch_id_local})

                    # insert lines
                    for r in range(grid.rowCount()):
                        emp = row_emps[r]
                        vals = [grid.item(r, c).text() if grid.item(r, c) else "0" for c in range(1, len(COLS))]
                        nums = [_rf(v) for v in vals]
                        (basic, comm, inc, allw, ot_r, ot_h, pt_r, pt_h, tot, levy, shg, sdl, cpf_ee, cpf_er, cpf_t,
                         ee_c, er_c, cash) = nums
                        s.execute(text("""
                          INSERT INTO payroll_batch_lines(
                            batch_id, employee_id, basic_salary, commission, incentives, allowance,
                            overtime_rate, overtime_hours, part_time_rate, part_time_hours,
                            levy, shg, sdl, cpf_emp, cpf_er, cpf_total,
                            line_total, ee_contrib, er_contrib, total_cash
                          ) VALUES(
                            :b,:e,:ba,:co,:in,:al,:otr,:oth,:ptr,:pth,:lev,:shg,:sdl,:ee,:er,:cpt,:lt,:eec,:erc,:cash
                          )
                        """), {
                            "b": batch_id_local, "e": int(emp.id),
                            "ba": basic, "co": comm, "in": inc, "al": allw,
                            "otr": ot_r, "oth": ot_h, "ptr": pt_r, "pth": pt_h,
                            "lev": levy, "shg": shg, "sdl": sdl,
                            "ee": cpf_ee, "er": cpf_er, "cpt": cpf_t,
                            "lt": tot, "eec": ee_c, "erc": er_c, "cash": cash
                        })
                    s.commit()
                return batch_id_local

            def _on_clicked(btn):
                role = btns.buttonRole(btn)
                text_btn = btn.text().lower()
                if "save" in text_btn:
                    _persist("Draft")
                    QMessageBox.information(dlg, "Salary Review", "Saved.")
                    _load_batches()
                elif "submit" in text_btn:
                    _persist("Submitted")
                    QMessageBox.information(dlg, "Salary Review", "Submitted and locked.")
                    _load_batches()
                    dlg.accept()
                else:
                    dlg.reject()

            if not read_only:
                btns.clicked.connect(_on_clicked)

            dlg.resize(1200, 620)
            dlg.exec()

        # ---------- toolbar actions ----------
        def _create():
            y = int(cb_year.currentText())
            m = cb_month.currentIndex() + 1
            _open_batch_dialog(None, False, y, m)

        def _edit():
            bid = _selected_batch_id()
            if not bid:
                QMessageBox.information(host, "Salary Review", "Select a batch.")
                return
            _open_batch_dialog(bid, False)

        def _view():
            bid = _selected_batch_id()
            if not bid:
                QMessageBox.information(host, "Salary Review", "Select a batch.")
                return
            _open_batch_dialog(bid, True)

        def _submit():
            bid = _selected_batch_id()
            if not bid:
                QMessageBox.information(host, "Salary Review", "Select a batch.")
                return
            with SessionLocal() as s:
                s.execute(text("UPDATE payroll_batches SET status='Submitted' WHERE id=:i"), {"i": bid})
                s.commit()
            _load_batches()

        def _delete():
            bid = _selected_batch_id()
            if not bid:
                QMessageBox.information(host, "Salary Review", "Select a batch.")
                return
            if QMessageBox.question(host, "Delete",
                                    "Delete selected batch? This removes all lines.") == QMessageBox.Yes:
                with SessionLocal() as s:
                    s.execute(text("DELETE FROM payroll_batch_lines WHERE batch_id=:i"), {"i": bid})
                    s.execute(text("DELETE FROM payroll_batches WHERE id=:i"), {"i": bid})
                    s.commit()
                _load_batches()

        btn_create.clicked.connect(_create)
        btn_edit.clicked.connect(_edit)
        btn_view.clicked.connect(_view)
        btn_submit.clicked.connect(_submit)
        btn_delete.clicked.connect(_delete)
        btn_refresh.clicked.connect(_load_batches)

    # -- Vouchers
    def _build_vouchers_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        ctrl = QHBoxLayout()
        self.v_emp = QComboBox()
        for emp_id, name, code in _employees():
            self.v_emp.addItem(f"{name} ({code})", emp_id)
        self.v_month = QComboBox()
        self.v_month.addItems(_month_names())
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

        # centered, thin-border, scrollable preview
        wrap = QHBoxLayout()
        wrap.addStretch(1)

        self.v_preview = QTextBrowser()
        self.v_preview.setOpenExternalLinks(True)
        self.v_preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.v_preview.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.v_preview.setFrameShape(QFrame.NoFrame)
        self.v_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.v_preview.setMinimumWidth(780)
        self.v_preview.setMinimumHeight(700)

        wrap.addWidget(self.v_preview, 1)
        wrap.addStretch(1)
        v.addLayout(wrap)

        self.tabs.addTab(host, "Salary Vouchers")

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

        # upscale readability
        html = self.v_preview.toHtml().replace(
            "<head>",
            "<head><style>@page{size:A4;margin:12mm 10mm;} html,body{font-size:12pt;}</style>"
        )

        doc = QTextDocument()
        doc.setDefaultFont(QFont("Arial", 12))
        doc.setHtml(html)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setResolution(150)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4),
                                          QPageLayout.Portrait,
                                          QMarginsF(10, 12, 10, 12),
                                          QPageLayout.Millimeter))
        printer.setOutputFileName(path)
        doc.print_(printer)

    # -- Settings
    def _build_settings_tab(self):
        from sqlalchemy import text
        import csv, re

        # ---------- ensure DB rule tables ----------
        def _ensure_settings_tables():
            with SessionLocal() as s:
                s.execute(text("""
                CREATE TABLE IF NOT EXISTS cpf_rules(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  age_bracket TEXT NOT NULL,
                  residency   TEXT NOT NULL,
                  ee_pct      REAL NOT NULL DEFAULT 0,
                  er_pct      REAL NOT NULL DEFAULT 0,
                  wage_ceiling REAL NOT NULL DEFAULT 0
                )"""))
                s.execute(text("""
                CREATE TABLE IF NOT EXISTS shg_rules(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  race TEXT NOT NULL,
                  income_from REAL NOT NULL,
                  income_to   REAL NOT NULL,
                  contribution REAL NOT NULL
                )"""))
                s.execute(text("""
                CREATE TABLE IF NOT EXISTS sdl_rules(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  salary_from REAL NOT NULL,
                  salary_to   REAL NOT NULL,
                  rule TEXT NOT NULL
                )"""))
                s.commit()
        _ensure_settings_tables()

        # ---------- helpers ----------
        def _mk_table(headers):
            t = QTableWidget(0, len(headers))
            t.setHorizontalHeaderLabels(headers)
            t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            t.verticalHeader().setVisible(False)
            t.setAlternatingRowColors(True)
            return t

        def _rf(x):
            try:
                return float(str(x).replace(",", "").replace("%", "").strip())
            except:
                return 0.0

        def _csv_export(tbl, headers, title):
            path, _ = QFileDialog.getSaveFileName(self, f"Export {title}", f"{title}.csv", "CSV Files (*.csv)")
            if not path: return
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for r in range(tbl.rowCount()):
                    w.writerow([(tbl.item(r, c).text() if tbl.item(r, c) else "") for c in range(tbl.columnCount())])

        def _csv_import(tbl, headers, title):
            path, _ = QFileDialog.getOpenFileName(self, f"Import {title}", "", "CSV Files (*.csv)")
            if not path: return
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            if not rows: return
            hdr = [h.strip() for h in rows[0]]
            if [h.lower() for h in hdr] != [h.lower() for h in headers]:
                QMessageBox.warning(self, "Import", f"Header mismatch.\nExpected: {headers}\nGot: {hdr}")
                return
            tbl.setRowCount(0)
            for data in rows[1:]:
                r = tbl.rowCount()
                tbl.insertRow(r)
                for c, val in enumerate(data[:len(headers)]):
                    tbl.setItem(r, c, QTableWidgetItem(val))

        def _csv_template(headers, title):
            path, _ = QFileDialog.getSaveFileName(self, f"{title} CSV Template", f"{title}_template.csv", "CSV Files (*.csv)")
            if not path: return
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(headers)
            QMessageBox.information(self, "Template", f"Created: {path}")

        # ---------- SCROLL AREA AS TAB ----------
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sa.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        v = QVBoxLayout(inner)
        v.setSpacing(12)
        inner.setContentsMargins(12, 12, 12, 12)

        # ---------- Voucher Settings (format + company stamp) ----------
        voucher_box = QGroupBox("Voucher Settings")
        f_v = QFormLayout(voucher_box)

        # voucher code format
        self.voucher_format = QLineEdit(globals().get("_VOUCHER_FMT", "SV-{YYYY}{MM}-{EMP}"))
        self.voucher_format.setMaximumWidth(340)
        self.voucher_preview = QLabel("")
        btn_preview = QPushButton("Preview"); btn_preview.setMaximumWidth(120)
        btn_apply   = QPushButton("Apply");   btn_apply.setMaximumWidth(120)

        def _preview_code():
            sample = (self.voucher_format.text() or "SV-{YYYY}{MM}-{EMP}")
            code = (sample.replace("{YYYY}", "2025")
                          .replace("{MM}", "01")
                          .replace("{EMP}", "EMP001"))
            self.voucher_preview.setText(f"Preview: {code}")

        def _apply_format():
            fmt = (self.voucher_format.text().strip() or "SV-{YYYY}{MM}-{EMP}")
            globals()["_VOUCHER_FMT"] = fmt
            _preview_code()
            try:
                self._refresh_voucher_preview()
            except Exception:
                pass

        btn_preview.clicked.connect(_preview_code)
        btn_apply.clicked.connect(_apply_format)

        row_fmt = QHBoxLayout()
        row_fmt.addWidget(btn_preview)
        row_fmt.addWidget(btn_apply)
        row_fmt.addStretch(1)
        f_v.addRow("Format", self.voucher_format)
        f_v.addRow("", row_fmt)
        f_v.addRow("", self.voucher_preview)

        # company stamp upload
        stamp_row = QHBoxLayout()
        self.stamp_preview = QLabel("No stamp")
        self.stamp_preview.setMinimumSize(120, 60)
        self.stamp_preview.setStyleSheet("border:1px solid #ddd; padding:4px;")
        btn_up = QPushButton("Upload Stamp")
        btn_cl = QPushButton("Clear")
        btn_up.setMaximumWidth(140)
        btn_cl.setMaximumWidth(120)

        def _refresh_stamp_preview_from_b64(b64: Optional[str]):
            if not b64:
                self.stamp_preview.setText("No stamp")
                self.stamp_preview.setPixmap(QPixmap())
                return
            pix = QPixmap()
            pix.loadFromData(base64.b64decode(b64))
            self.stamp_preview.setPixmap(pix.scaled(140, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.stamp_preview.setText("")

        def _upload_stamp():
            path, _ = QFileDialog.getOpenFileName(self, "Select Company Stamp", "", "Images (*.png *.jpg *.jpeg)")
            if not path:
                return
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                b64 = base64.b64encode(raw).decode("ascii")
                self._company_stamp_b64 = b64
                globals()["_STAMP_B64"] = b64
                # try persist if CompanySettings.stamp exists
                try:
                    with SessionLocal() as s:
                        cs = s.query(CompanySettings).first()
                        if cs is not None and hasattr(cs, "stamp"):
                            setattr(cs, "stamp", raw)
                            s.commit()
                except Exception:
                    pass
                _refresh_stamp_preview_from_b64(b64)
                try:
                    self._refresh_voucher_preview()
                except Exception:
                    pass
            except Exception:
                pass

        def _clear_stamp():
            self._company_stamp_b64 = None
            globals()["_STAMP_B64"] = None
            # try clear in DB if field exists
            try:
                with SessionLocal() as s:
                    cs = s.query(CompanySettings).first()
                    if cs is not None and hasattr(cs, "stamp"):
                        setattr(cs, "stamp", None)
                        s.commit()
            except Exception:
                pass
            _refresh_stamp_preview_from_b64(None)
            try:
                self._refresh_voucher_preview()
            except Exception:
                pass

        btn_up.clicked.connect(_upload_stamp)
        btn_cl.clicked.connect(_clear_stamp)

        stamp_row.addWidget(self.stamp_preview)
        stamp_row.addSpacing(10)
        stamp_row.addWidget(btn_up)
        stamp_row.addWidget(btn_cl)
        stamp_row.addStretch(1)
        f_v.addRow("Company Stamp", stamp_row)

        v.addWidget(voucher_box)
        _preview_code()
        _refresh_stamp_preview_from_b64(self._company_stamp_b64)

        # ---------- CPF ----------
        cpf_headers = ["Age Bracket", "Residency", "Employee %", "Employer %", "Wage Ceiling"]
        cpf_box = QGroupBox("CPF Rules")
        cpf_v = QVBoxLayout(cpf_box)
        cpf_hint = QLabel("Age: <=55, >55-60, >=65 etc. Residency: Citizen/SPR 3+ yr, PR Y1 G/G, PR Y2 G/G, PR Y1 F/G, PR Y2 F/G.")
        cpf_hint.setStyleSheet("color:#6b7280;")
        cpf_v.addWidget(cpf_hint)
        self.cpf_tbl = _mk_table(cpf_headers)
        cpf_v.addWidget(self.cpf_tbl)
        row = QHBoxLayout()
        b_add = QPushButton("Add"); b_del = QPushButton("Delete")
        b_imp = QPushButton("Import CSV"); b_exp = QPushButton("Export CSV")
        b_tpl = QPushButton("CSV Template"); b_val = QPushButton("Validate")
        for b in (b_add, b_del): row.addWidget(b)
        row.addStretch(1)
        for b in (b_imp, b_exp, b_tpl, b_val): row.addWidget(b)
        cpf_v.addLayout(row)
        b_add.clicked.connect(lambda: self.cpf_tbl.insertRow(self.cpf_tbl.rowCount()))
        b_del.clicked.connect(lambda: [self.cpf_tbl.removeRow(r) for r in sorted({ix.row() for ix in self.cpf_tbl.selectedIndexes()}, reverse=True)])
        b_imp.clicked.connect(lambda: _csv_import(self.cpf_tbl, cpf_headers, "CPF"))
        b_exp.clicked.connect(lambda: _csv_export(self.cpf_tbl, cpf_headers, "CPF"))
        b_tpl.clicked.connect(lambda: _csv_template(cpf_headers, "CPF"))
        b_val.clicked.connect(lambda: QMessageBox.information(self, "CPF Validate",
                        "OK" if not _validate_cpf(self.cpf_tbl) else "\n".join(_validate_cpf(self.cpf_tbl))))
        v.addWidget(cpf_box)

        # ---------- SHG ----------
        shg_headers = ["Race", "Income From", "Income To", "Contribution"]
        shg_box = QGroupBox("SHG Rules")
        shg_v = QVBoxLayout(shg_box)
        shg_hint = QLabel("Race: chinese|indian|eurasian|muslim (or 'any'). Contribution is flat amount.")
        shg_hint.setStyleSheet("color:#6b7280;")
        shg_v.addWidget(shg_hint)
        self.shg_tbl = _mk_table(shg_headers)
        shg_v.addWidget(self.shg_tbl)
        row2 = QHBoxLayout()
        s_add = QPushButton("Add"); s_del = QPushButton("Delete")
        s_imp = QPushButton("Import CSV"); s_exp = QPushButton("Export CSV")
        s_tpl = QPushButton("CSV Template"); s_val = QPushButton("Validate")
        for b in (s_add, s_del): row2.addWidget(b)
        row2.addStretch(1)
        for b in (s_imp, s_exp, s_tpl, s_val): row2.addWidget(b)
        shg_v.addLayout(row2)
        s_add.clicked.connect(lambda: self.shg_tbl.insertRow(self.shg_tbl.rowCount()))
        s_del.clicked.connect(lambda: [self.shg_tbl.removeRow(r) for r in sorted({ix.row() for ix in self.shg_tbl.selectedIndexes()}, reverse=True)])
        s_imp.clicked.connect(lambda: _csv_import(self.shg_tbl, shg_headers, "SHG"))
        s_exp.clicked.connect(lambda: _csv_export(self.shg_tbl, shg_headers, "SHG"))
        s_tpl.clicked.connect(lambda: _csv_template(shg_headers, "SHG"))
        s_val.clicked.connect(lambda: QMessageBox.information(self, "SHG Validate",
                        "OK" if not _validate_shg(self.shg_tbl) else "\n".join(_validate_shg(self.shg_tbl))))
        v.addWidget(shg_box)

        # ---------- SDL ----------
        sdl_headers = ["Salary From", "Salary To", "Rate / Formula"]
        sdl_box = QGroupBox("SDL Rules")
        sdl_v = QVBoxLayout(sdl_box)
        sdl_hint = QLabel("Use percent like 0.25% or 0.25. Or flat like 'flat: 11.25'.")
        sdl_hint.setStyleSheet("color:#6b7280;")
        sdl_v.addWidget(sdl_hint)
        self.sdl_tbl = _mk_table(sdl_headers)
        sdl_v.addWidget(self.sdl_tbl)
        row3 = QHBoxLayout()
        d_add = QPushButton("Add"); d_del = QPushButton("Delete")
        d_imp = QPushButton("Import CSV"); d_exp = QPushButton("Export CSV")
        d_tpl = QPushButton("CSV Template"); d_val = QPushButton("Validate")
        for b in (d_add, d_del): row3.addWidget(b)
        row3.addStretch(1)
        for b in (d_imp, d_exp, d_tpl, d_val): row3.addWidget(b)
        sdl_v.addLayout(row3)
        d_add.clicked.connect(lambda: self.sdl_tbl.insertRow(self.sdl_tbl.rowCount()))
        d_del.clicked.connect(lambda: [self.sdl_tbl.removeRow(r) for r in sorted({ix.row() for ix in self.sdl_tbl.selectedIndexes()}, reverse=True)])
        d_imp.clicked.connect(lambda: _csv_import(self.sdl_tbl, sdl_headers, "SDL"))
        d_exp.clicked.connect(lambda: _csv_export(self.sdl_tbl, sdl_headers, "SDL"))
        d_tpl.clicked.connect(lambda: _csv_template(sdl_headers, "SDL"))
        d_val.clicked.connect(lambda: QMessageBox.information(self, "SDL Validate",
                        "OK" if not _validate_sdl(self.sdl_tbl) else "\n".join(_validate_sdl(self.sdl_tbl))))
        v.addWidget(sdl_box)

        # ---------- mount scroll area ----------
        sa.setWidget(inner)
        self.tabs.addTab(sa, "Settings")

        # initial preview
        try:
            _preview_code()
        except Exception:
            pass


# ---- validators used in Settings (defined at end for clarity) ----
from PySide6.QtWidgets import QMessageBox  # local import used above


def _validate_cpf(tbl):
    import re
    errs = []
    for r in range(tbl.rowCount()):
        age = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
        resid = (tbl.item(r, 1).text().strip() if tbl.item(r, 1) else "")
        try:
            ee = float(str(tbl.item(r, 2).text() if tbl.item(r, 2) else "0").replace(",", "").replace("%", "").strip())
            er = float(str(tbl.item(r, 3).text() if tbl.item(r, 3) else "0").replace(",", "").replace("%", "").strip())
            cap = float(str(tbl.item(r, 4).text() if tbl.item(r, 4) else "0").replace(",", "").strip())
        except Exception:
            ee = er = cap = 0.0
        if not age or not resid: errs.append(f"Row {r + 1}: missing Age/Residency")
        if ee < 0 or er < 0: errs.append(f"Row {r + 1}: negative %")
        if cap < 0: errs.append(f"Row {r + 1}: negative ceiling")
        if age and not re.match(r"^(<=?\d+|>=?\d+|\d+\-\d+|>\d+)$", age.replace(" ", "")):
            errs.append(f"Row {r + 1}: age bracket format")
    return errs


def _validate_shg(tbl):
    errs = []
    def rf(x):
        try:
            return float(str(x).replace(",", "").strip())
        except Exception:
            return 0.0
    for r in range(tbl.rowCount()):
        race = (tbl.item(r, 0).text().strip().lower() if tbl.item(r, 0) else "")
        lo = rf(tbl.item(r, 1).text() if tbl.item(r, 1) else "0")
        hi = rf(tbl.item(r, 2).text() if tbl.item(r, 2) else "0")
        val = rf(tbl.item(r, 3).text() if tbl.item(r, 3) else "0")
        if not race: errs.append(f"Row {r + 1}: missing race")
        if lo < 0 or hi < 0 or val < 0: errs.append(f"Row {r + 1}: negative number")
        if hi and hi < lo: errs.append(f"Row {r + 1}: income_to < income_from")
    return errs


def _validate_sdl(tbl):
    errs = []
    def rf(x):
        try:
            return float(str(x).replace(",", "").replace("%", "").strip())
        except Exception:
            return 0.0
    for r in range(tbl.rowCount()):
        lo = rf(tbl.item(r, 0).text() if tbl.item(r, 0) else "0")
        hi = rf(tbl.item(r, 1).text() if tbl.item(r, 1) else "0")
        rule = (tbl.item(r, 2).text().strip().lower() if tbl.item(r, 2) else "")
        if hi and hi < lo: errs.append(f"Row {r + 1}: salary_to < salary_from")
        if not rule:
            errs.append(f"Row {r + 1}: missing rule")
            continue
        if rule.startswith("flat:"):
            try:
                float(rule.split(":", 1)[1].strip())
            except Exception:
                errs.append(f"Row {r + 1}: flat format")
        else:
            try:
                _ = rf(rule)
            except Exception:
                errs.append(f"Row {r + 1}: percent format")
    return errs
