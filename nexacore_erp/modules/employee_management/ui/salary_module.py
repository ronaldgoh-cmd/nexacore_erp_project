# salary_module.py
from __future__ import annotations

import base64
import csv
import math
from calendar import month_name
from datetime import date, datetime
from typing import List, Tuple, Optional

from PySide6.QtCore import Qt, QMarginsF
from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout, QFont, QPixmap
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTableWidget,
    QTableWidgetItem, QPushButton, QComboBox, QFileDialog, QHeaderView, QGroupBox,
    QFormLayout, QTextBrowser, QSizePolicy, QScrollArea, QFrame, QDialog,
    QDialogButtonBox, QAbstractItemView  # added
)

from ....core.database import get_employee_session as SessionLocal, get_main_session as MainSession
from ....core.tenant import id as tenant_id
from ....core.events import employee_events
from ..models import Employee, DropdownOption
from ....core.models import CompanySettings

# -------- Roles & Access manifest --------
MODULE_KEY = "salary_management"
MODULE_NAME = "Salary Management"
SUBMODULES = [
    ("summary",  "Summary"),
    ("review",   "Salary Review"),
    ("vouchers", "Salary Vouchers"),
    ("settings", "Settings"),
]

def module_manifest() -> dict:
    return {
        "key": MODULE_KEY,
        "name": MODULE_NAME,
        "submodules": [{"key": k, "name": n} for k, n in SUBMODULES],
    }

# ---------- globals / helpers ----------
_VOUCHER_FMT = "SV-{YYYY}{MM}-{EMP}"  # default; load/persist via payroll_settings table
_STAMP_B64: Optional[str] = None  # set from Settings → Upload Company Stamp

# CPF two-term offset constant requested: TW minus 500
# Keep this constant unless future policy changes.
_CPF_TW_MINUS_OFFSET = 500.0


def _ensure_payroll_settings_table():
    from sqlalchemy import text
    with MainSession() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS payroll_settings (
                account_id     TEXT PRIMARY KEY NOT NULL,
                voucher_format TEXT
            );
        """))
        s.commit()


def _load_voucher_format_from_db() -> None:
    """Load persisted voucher format into global _VOUCHER_FMT."""
    from sqlalchemy import text
    global _VOUCHER_FMT
    try:
        _ensure_payroll_settings_table()
        with MainSession() as s:
            row = s.execute(
                text("SELECT voucher_format FROM payroll_settings WHERE account_id=:a"),
                {"a": str(tenant_id())}
            ).fetchone()
            if row and (row.voucher_format or "").strip():
                _VOUCHER_FMT = row.voucher_format.strip()
    except Exception:
        # keep default if anything fails
        pass


def _save_voucher_format_to_db(fmt: str) -> None:
    from sqlalchemy import text
    try:
        _ensure_payroll_settings_table()
        with MainSession() as s:
            s.execute(
                text("""
                    INSERT INTO payroll_settings(account_id, voucher_format)
                    VALUES (:a, :f)
                    ON CONFLICT(account_id) DO UPDATE SET voucher_format=excluded.voucher_format
                """),
                {"a": str(tenant_id()), "f": fmt}
            )
            s.commit()
    except Exception:
        pass


def _dropdown_values(category: str) -> list[str]:
    """Return dropdown values (trimmed) for a category from Employee settings."""
    try:
        with SessionLocal() as s:
            rows = (s.query(DropdownOption.value)
                    .filter(DropdownOption.account_id == tenant_id(),
                            DropdownOption.category == category)
                    .order_by(DropdownOption.value)
                    .all())
        return [str(r[0]).strip() for r in rows if (r[0] or "").strip()]
    except Exception:
        return []


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


def _detect_mime(data: bytes | None) -> str:
    if not data:
        return "image/png"
    b0 = data[:8]
    if b0.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if b0.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if b0.startswith(b"GIF8"):
        return "image/gif"
    return "application/octet-stream"


def _stamp_img_html(cs: CompanySettings | None) -> str:
    raw = getattr(cs, "stamp", None) if cs else None
    if not raw and _STAMP_B64:
        raw = base64.b64decode(_STAMP_B64)
    if not raw:
        return ""
    mime = _detect_mime(raw)
    b64 = base64.b64encode(raw).decode("ascii")
    return (
        f'<img src="data:{mime};base64,{b64}" '
        'width="128" height="128" '
        'style="display:inline-block;width:128px;height:128px;object-fit:contain;opacity:0.85;vertical-align:bottom;"/>'
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
    with MainSession() as s:
        row = s.query(CompanySettings).filter(CompanySettings.account_id == str(tenant_id())).first()
        if not row:
            row = CompanySettings(account_id=str(tenant_id()))
            s.add(row)
            s.commit()
            s.refresh(row)
        return row


def _voucher_html(
        cs: CompanySettings | None,
        emp: Employee | None,
        year: int,
        month_index_1: int,
        line: Optional[dict] = None,
) -> str:
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
    id_no = getattr(emp, "identification_number", "") or getattr(emp, "nric", "") or "—"
    bank = getattr(emp, "bank", "") or "—"
    acct = getattr(emp, "bank_account", "") or "—"

    # --- figures (defaults from employee fields) ---
    basic = float(getattr(emp, "basic_salary", 0.0) or 0.0)
    comm = float(getattr(emp, "commission", 0.0) or 0.0)
    incent = float(getattr(emp, "incentives", 0.0) or 0.0)
    allow = float(getattr(emp, "allowance", 0.0) or 0.0)

    pt_rate = float(getattr(emp, "parttime_rate", getattr(emp, "part_time_rate", 0.0)) or 0.0)
    pt_hrs = float(getattr(emp, "part_time_hours", 0.0) or 0.0)

    ot_rate = float(getattr(emp, "overtime_rate", 0.0) or 0.0)
    ot_hrs = float(getattr(emp, "overtime_hours", 0.0) or 0.0)

    advance = float(getattr(emp, "advance", 0.0) or 0.0)
    shg = float(getattr(emp, "shg", 0.0) or 0.0)
    adjustment = 0.0

    cpf_emp = float(getattr(emp, "cpf_employee", 0.0) or 0.0)
    cpf_er = float(getattr(emp, "cpf_employer", 0.0) or 0.0)

    sdl = float(getattr(emp, "sdl", 0.0) or 0.0)
    levy = float(getattr(emp, "levy", 0.0) or 0.0)

    # --- override from batch line if available ---
    if line:
        basic = float(line.get("basic_salary", basic) or 0.0)
        comm = float(line.get("commission", comm) or 0.0)
        incent = float(line.get("incentives", incent) or 0.0)
        allow = float(line.get("allowance", allow) or 0.0)
        ot_rate = float(line.get("overtime_rate", ot_rate) or 0.0)
        ot_hrs = float(line.get("overtime_hours", ot_hrs) or 0.0)
        pt_rate = float(line.get("part_time_rate", pt_rate) or 0.0)
        pt_hrs = float(line.get("part_time_hours", pt_hrs) or 0.0)
        levy = float(line.get("levy", levy) or 0.0)
        advance = float(line.get("advance", advance) or 0.0)
        shg = float(line.get("shg", shg) or 0.0)
        sdl = float(line.get("sdl", sdl) or 0.0)
        cpf_emp = float(line.get("cpf_emp", cpf_emp) or 0.0)
        cpf_er = float(line.get("cpf_er", cpf_er) or 0.0)
        adjustment = float(line.get("adjustment", adjustment) or 0.0)

    pt_amt = pt_rate * pt_hrs
    ot_amt = ot_rate * ot_hrs
    cpf_total = cpf_emp + cpf_er

    gross_base = basic + comm + incent + allow + pt_amt + ot_amt
    gross = gross_base + adjustment
    ded_only = advance + shg
    net_pay = gross - ded_only - cpf_emp

    ym = f"{month_name[month_index_1]} {year}"
    code = _format_voucher_code(emp, year, month_index_1)

    def money(x: float) -> str:
        try:
            return f"{float(x):,.2f}"
        except Exception:
            return "0.00"

    show_warn = (line is None) and (
                gross == 0 and adjustment == 0 and ded_only == 0 and cpf_emp == 0 and cpf_er == 0 and sdl == 0 and levy == 0)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Salary Voucher</title>
<style>
  html, body {{ font-size: 13px; }}
  body {{ margin:0; background:#ffffff; color:#111827; font-family:Segoe UI, Arial, sans-serif; }}
  .page {{ width:794px; margin:0 auto; padding:24px 18px; }}
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
                <tr><td class="cell" style="color:#374151">Adjustment (+/-)</td><td class="cell" style="text-align:right">{money(adjustment)}</td></tr>
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
                <tr><td class="cell" style="color:#374151">Advance</td><td class="cell" style="text-align:right">{money(advance)}</td></tr>
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

    {'' if not show_warn else f'''
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
        <!-- Left: stamp above Prepared by -->
        <td style="width:50%;vertical-align:bottom">
          <div style="margin-bottom:6px">{stamp_html}</div>
          <div style="font-weight:bold">Prepared by: {html.escape(company_name)}</div>
        </td>

        <!-- Right: signature line then label -->
        <td style="width:50%;vertical-align:bottom;text-align:right">
          <div style="display:inline-block;width:70%;text-align:center">
            <hr style="width:60%;margin:0 auto 6px auto;height:1px;border:none;background:#111;">
            <div>Employee Acknowledgement</div>
          </div>
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

        # Load persisted voucher format once per widget init
        _load_voucher_format_from_db()

        self._company_stamp_b64: Optional[str] = None

        self._build_summary_tab()
        self._build_salary_review_tab()
        self._build_vouchers_tab()
        self._build_settings_tab()

        cs = _company()
        raw = getattr(cs, "stamp", None)
        if raw and not self._company_stamp_b64:
            try:
                self._company_stamp_b64 = base64.b64encode(raw).decode("ascii")
                globals()["_STAMP_B64"] = self._company_stamp_b64
            except Exception:
                pass

        employee_events.employees_changed.connect(self._handle_employees_changed)

    # expose key for main_window
    MODULE_KEY = "salary_management"

    def filter_tabs_by_access(self, allowed_keys: list[str] | set[str]):
        allowed = set(allowed_keys or [])
        if not allowed:
            return  # empty = show all
        label_by_key = {
            "summary": "Summary",
            "review": "Salary Review",
            "vouchers": "Salary Vouchers",
            "settings": "Settings",
        }
        allowed_labels = {label_by_key[k] for k in allowed if k in label_by_key}
        for i in range(self.tabs.count() - 1, -1, -1):
            if self.tabs.tabText(i) not in allowed_labels:
                self.tabs.removeTab(i)

    # -- Summary
    def _build_summary_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        # Top filters: Name + Department
        top = QHBoxLayout()
        top.addWidget(QLabel("Name"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name")
        top.addWidget(self.search, 1)

        top.addWidget(QLabel("Department"))
        self.cmb_dept = QComboBox()
        top.addWidget(self.cmb_dept, 1)
        top.addStretch(1)
        v.addLayout(top)

        # Table: add Department after Name; make non-editable; center headers and cells
        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(
            ["Code", "Name", "Department", "Basic", "Incentive", "Allowance", "Overtime Rate", "Part-Time Rate"]
        )
        hdr = self.tbl.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)  # non editable
        v.addWidget(self.tbl, 1)

        # Wire signals
        self.search.textChanged.connect(self._reload_summary)
        self.cmb_dept.currentIndexChanged.connect(self._reload_summary)

        # Init dropdowns + data
        self._load_departments_for_summary()
        self.tabs.addTab(host, "Summary")
        self._reload_summary()

    def _handle_employees_changed(self):
        self._load_departments_for_summary()
        self._reload_summary()

    def _load_departments_for_summary(self):
        with SessionLocal() as s:
            vals = s.query(Employee.department).filter(Employee.account_id == tenant_id()).distinct().all()
        depts = sorted({(v[0] or "").strip() for v in vals if (v[0] or "").strip()}, key=str.lower)
        self.cmb_dept.blockSignals(True)
        self.cmb_dept.clear()
        self.cmb_dept.addItem("All")
        self.cmb_dept.addItems(depts)
        self.cmb_dept.blockSignals(False)

    def _reload_summary(self):
        # helpers
        def _money(x) -> str:
            try:
                return f"$ {float(x or 0):,.2f}"
            except Exception:
                return "$ 0.00"

        def _center(text: str) -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            return it

        name_q = (self.search.text() or "").strip().lower()
        dept_q = self.cmb_dept.currentText() if getattr(self, "cmb_dept", None) and self.cmb_dept.count() else "All"

        with SessionLocal() as s:
            q = s.query(Employee).filter(Employee.account_id == tenant_id())
            if dept_q and dept_q != "All":
                q = q.filter(Employee.department == dept_q)
            rows = q.all()

        self.tbl.setRowCount(0)
        for e in rows:
            if name_q and name_q not in (e.full_name or "").lower():
                continue
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            code = e.code or ""
            name = e.full_name or ""
            dept = e.department or ""

            basic = _money(getattr(e, "basic_salary", 0.0))
            incent = _money(getattr(e, "incentives", getattr(e, "incentive", 0.0)))
            allow = _money(getattr(e, "allowance", 0.0))
            ot_rate = _money(getattr(e, "overtime_rate", 0.0))
            pt_rate = _money(getattr(e, "parttime_rate", getattr(e, "part_time_rate", 0.0)))

            vals = [code, name, dept, basic, incent, allow, ot_rate, pt_rate]
            for c, v in enumerate(vals):
                self.tbl.setItem(r, c, _center(str(v)))

    def _build_salary_review_tab(self):
        from calendar import monthrange, month_name
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
            QTableWidget, QTableWidgetItem, QDialog, QListWidget, QListWidgetItem,
            QDialogButtonBox, QMessageBox, QHeaderView
        )
        from PySide6.QtCore import Qt, QRect
        from PySide6.QtGui import QPainter, QColor, QPen, QBrush
        from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
        from sqlalchemy import text
        import re

        # ----------------
        # helpers
        # ----------------
        def _month_names():
            return [month_name[i] for i in range(1, 13)]

        def _rf(x):
            # robust number parse; strips $, commas, text, % etc
            s = str(x or "")
            s = s.replace("S$", "").replace("$", "")
            s = s.replace(",", "")
            m = re.findall(r"-?\d+(?:\.\d+)?", s)
            return float(m[0]) if m else 0.0

        def _ri(x):
            xs = str(x or "").strip()
            return int(xs) if xs else None

        # Date parser: prefer DD/MM/YYYY, also accept DD-MM-YYYY, YYYY-MM-DD, YYYY/MM/DD
        def _rd(x) -> Optional[date]:
            s = (str(x or "").strip())
            if not s:
                return None
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    return datetime.strptime(s, fmt).date()
                except Exception:
                    pass
            return None

        def _age(emp, on_date):
            dob = getattr(emp, "dob", None) or getattr(emp, "date_of_birth", None)
            if not dob:
                return 30, False
            try:
                if isinstance(dob, str):
                    p = [int(t) for t in dob.replace("/", "-").split("-")]
                    if p[0] > 1900:
                        y, m, d = (p + [1, 1])[0:3]
                    else:
                        d, m, y = (p + [1, 1])[0:3]
                    from datetime import date as _date
                    dob = _date(y, m, d)
            except Exception:
                return 30, False

            years = on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))
            try:
                anniv = dob.replace(year=dob.year + years)
            except ValueError:
                if dob.month == 2 and dob.day == 29:
                    anniv = date(dob.year + years, 2, 28)
                else:
                    anniv = date(dob.year + years, dob.month, dob.day)
            has_fraction = on_date > anniv
            return years, has_fraction

        # ----- rounding rules for CPF -----
        from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
        def _round_dollar_half_up(x: float) -> float:
            return float(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

        def _floor_dollar(x: float) -> float:
            return float(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_DOWN))

        # ---------- CPF rules read + compute (v2) ----------
        def _cpf_rows():
            rows = []
            tbl = getattr(self, "cpf_tbl", None)
            if not tbl:
                return rows

            def _rf2(x):
                try:
                    return float(str(x).replace(",", "").replace("%", "").strip())
                except Exception:
                    return 0.0

            def _ri2(x):
                xs = str(x or "").strip()
                return int(xs) if xs else None

            def _rd2(x) -> Optional[date]:
                s = (str(x or "").strip())
                if not s:
                    return None
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
                    try:
                        return datetime.strptime(s, fmt).date()
                    except Exception:
                        pass
                return None

            for r in range(tbl.rowCount()):
                age_br = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
                resid = (tbl.item(r, 1).text().strip() if tbl.item(r, 1) else "")
                pr_year = _ri2(tbl.item(r, 2).text() if tbl.item(r, 2) else "")
                sal_from = _rf2(tbl.item(r, 3).text() if tbl.item(r, 3) else "0")
                sal_to = _rf2(tbl.item(r, 4).text() if tbl.item(r, 4) else "0")

                tot_pct_tw = _rf2(tbl.item(r, 5).text() if tbl.item(r, 5) else "0")
                tot_pct_tw_m = _rf2(tbl.item(r, 6).text() if tbl.item(r, 6) else "0")
                ee_pct_tw = _rf2(tbl.item(r, 7).text() if tbl.item(r, 7) else "0")
                ee_pct_tw_m = _rf2(tbl.item(r, 8).text() if tbl.item(r, 8) else "0")

                cap_total = _rf2(tbl.item(r, 9).text() if tbl.item(r, 9) else "0")
                cap_ee = _rf2(tbl.item(r, 10).text() if tbl.item(r, 10) else "0")
                eff_from = _rd2(tbl.item(r, 11).text() if tbl.item(r, 11) else "")
                rows.append((
                    age_br, resid, pr_year, sal_from, sal_to,
                    tot_pct_tw, tot_pct_tw_m, ee_pct_tw, ee_pct_tw_m,
                    cap_total, cap_ee, eff_from
                ))
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

        def _employee_pr_year(emp, on_date: date) -> Optional[int]:
            val = getattr(emp, "pr_year", None)
            if isinstance(val, int):
                return val
            pr_date = getattr(emp, "pr_date", None)
            if isinstance(pr_date, str):
                pr_date = _rd(pr_date)
            elif isinstance(pr_date, datetime):
                pr_date = pr_date.date()
            if isinstance(pr_date, date):
                if pr_date > on_date:
                    return None
                elapsed_days = (on_date - pr_date).days
                years = elapsed_days / 365.0
                return max(1, math.ceil(years))
            resid = (getattr(emp, "residency", "") or "")
            m = re.search(r"[Yy]\s*(\d+)", resid)
            try:
                return int(m.group(1)) if m else None
            except Exception:
                return None

        def _is_casual(emp) -> bool:
            return ((getattr(emp, "employment_type", "") or "").strip().lower() == "casual")

        def _cpf_for(emp, tw, on_date):
            if _is_casual(emp):
                return 0.0, 0.0, 0.0
            resid_emp = (getattr(emp, "residency", "") or "").strip().lower()
            age_years, has_fraction = _age(emp, on_date)
            pry = _employee_pr_year(emp, on_date)

            age_candidates = []
            if has_fraction and age_years >= 60:
                age_candidates.append(age_years + 1)
            age_candidates.append(age_years)

            rows = _cpf_rows()
            for age_value in age_candidates:
                for (
                        age_br, resid_row, pr_year, sal_lo, sal_hi,
                        tot_pct_tw, tot_pct_tw_m, ee_pct_tw, ee_pct_tw_m,
                        cap_total, cap_ee, eff_from
                ) in rows:

                    if resid_row.strip().lower() != resid_emp:
                        continue
                    if eff_from and eff_from > on_date:
                        continue
                    if not _match_age(age_br, age_value):
                        continue
                    if sal_lo and tw < sal_lo:
                        continue
                    if sal_hi and tw > sal_hi:
                        continue
                    if pr_year is not None:
                        if pry is None or pry != pr_year:
                            continue

                    off = _CPF_TW_MINUS_OFFSET

                    total_term1 = tw * (tot_pct_tw / 100.0)
                    total_term2 = max(tw - off, 0.0) * (tot_pct_tw_m / 100.0)
                    ee_term1 = tw * (ee_pct_tw / 100.0)
                    ee_term2 = max(tw - off, 0.0) * (ee_pct_tw_m / 100.0)

                    total_val_calc = _round_dollar_half_up(total_term1 + total_term2)
                    ee_val_calc = _floor_dollar(ee_term1 + ee_term2)

                    total_val = float(min(total_val_calc, cap_total)) if cap_total else float(total_val_calc)
                    ee_val = float(min(ee_val_calc, cap_ee)) if cap_ee else float(ee_val_calc)
                    if ee_val > total_val:
                        ee_val = total_val
                    er_val = float(max(total_val - ee_val, 0.0))
                    return ee_val, er_val, float(ee_val + er_val)

            return 0.0, 0.0, 0.0

        # ---------- SHG ----------
        def _load_shg_race_map() -> dict:
            try:
                with SessionLocal() as s:
                    from sqlalchemy import text as _t
                    s.execute(_t("""
                                   CREATE TABLE IF NOT EXISTS shg_race_map
                                   (
                                       account_id TEXT NOT NULL,
                                       race       TEXT NOT NULL,
                                       shg        TEXT NOT NULL,
                                       PRIMARY KEY (account_id, race)
                                   );
                                   """))
                    s.commit()
                    rows = s.execute(_t("SELECT race, shg FROM shg_race_map WHERE account_id=:a"),
                                     {"a": str(tenant_id())}).fetchall()
                return {(r.race or "").strip().lower(): (r.shg or "").strip().upper() for r in rows}
            except Exception:
                return {}

        def _shg_rows():
            rows = []
            tbl = getattr(self, "shg_tbl", None)
            if not tbl:
                return rows
            for r in range(tbl.rowCount()):
                shg = (tbl.item(r, 0).text().strip().upper() if tbl.item(r, 0) else "")
                lo = _rf(tbl.item(r, 1).text() if tbl.item(r, 1) else "0")
                hi = _rf(tbl.item(r, 2).text() if tbl.item(r, 2) else "0")
                ctyp = (tbl.item(r, 3).text().strip().lower() if tbl.item(r, 3) else "")
                cval = _rf(tbl.item(r, 4).text() if tbl.item(r, 4) else "0")
                eff = _rd(tbl.item(r, 5).text() if tbl.item(r, 5) else "")
                rows.append((shg, lo, hi, ctyp, cval, eff))
            return rows

        def _map_race_to_shg(race_str: str) -> str:
            m = _load_shg_race_map()
            key = (race_str or "").strip().lower()
            if key in m:
                return m[key]
            r = key
            if r.startswith("malay") or "muslim" in r:
                return "MBMF"
            if r.startswith("chin"):
                return "CDAC"
            if r.startswith("ind"):
                return "SINDA"
            if r.startswith("eurasian"):
                return "ECF"
            return "CDAC"

        def _shg_for(emp, tw, on_date):
            shg_name = _map_race_to_shg(getattr(emp, "race", "") or "")
            for shg, lo, hi, ctyp, cval, eff in _shg_rows():
                if shg != shg_name:
                    continue
                if eff and eff > on_date:
                    continue
                if not (lo <= tw <= (hi or tw)):
                    continue
                if ctyp == "percent":
                    return round(tw * (cval / 100.0), 2)
                return float(cval)
            return 0.0

        # ---------- SDL ----------
        def _sdl_rows():
            rows = []
            tbl = getattr(self, "sdl_tbl", None)
            if not tbl:
                return rows
            for r in range(tbl.rowCount()):
                lo = _rf(tbl.item(r, 0).text() if tbl.item(r, 0) else "0")
                hi = _rf(tbl.item(r, 1).text() if tbl.item(r, 1) else "0")
                rtyp = (tbl.item(r, 2).text().strip().lower() if tbl.item(r, 2) else "")
                rval = _rf(tbl.item(r, 3).text() if tbl.item(r, 3) else "0")
                eff = _rd(tbl.item(r, 4).text() if tbl.item(r, 4) else "")
                rows.append((lo, hi, rtyp, rval, eff))
            return rows

        def _sdl_for(tw, on_date):
            for lo, hi, rtyp, rval, eff in _sdl_rows():
                if eff and eff > on_date:
                    continue
                if lo <= tw <= (hi or tw):
                    if rtyp == "flat":
                        try:
                            return float(rval)
                        except Exception:
                            return 0.0
                    return round(tw * (float(rval) / 100.0), 2)
            return 0.0

        # ---------- DB bootstrapping ----------
        def _ensure_tables():
            with SessionLocal() as s:
                from sqlalchemy import text as _t
                s.execute(_t("""
                               CREATE TABLE IF NOT EXISTS payroll_batches
                               (
                                   id           INTEGER PRIMARY KEY AUTOINCREMENT,
                                   year         INTEGER NOT NULL,
                                   month        INTEGER NOT NULL,
                                   status       TEXT    NOT NULL DEFAULT 'Draft',
                                   total_basic  REAL    DEFAULT 0,
                                   total_er     REAL    DEFAULT 0,
                                   grand_total  REAL    DEFAULT 0,
                                   created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
                               );
                               """))
                s.execute(_t("""
                               CREATE TABLE IF NOT EXISTS payroll_batch_lines
                               (
                                   id              INTEGER PRIMARY KEY AUTOINCREMENT,
                                   batch_id        INTEGER NOT NULL,
                                   employee_id     INTEGER NOT NULL,
                                   basic_salary    REAL    DEFAULT 0,
                                   commission      REAL    DEFAULT 0,
                                   incentives      REAL    DEFAULT 0,
                                   allowance       REAL    DEFAULT 0,
                                   overtime_rate   REAL    DEFAULT 0,
                                   overtime_hours  REAL    DEFAULT 0,
                                   part_time_rate  REAL    DEFAULT 0,
                                   part_time_hours REAL    DEFAULT 0,
                                   adjustment      REAL    DEFAULT 0,
                                   levy            REAL    DEFAULT 0,
                                   advance         REAL    DEFAULT 0,
                                   shg             REAL    DEFAULT 0,
                                   sdl             REAL    DEFAULT 0,
                                   cpf_emp         REAL    DEFAULT 0,
                                   cpf_er          REAL    DEFAULT 0,
                                   cpf_total       REAL    DEFAULT 0,
                                   line_total      REAL    DEFAULT 0,
                                   ee_contrib      REAL    DEFAULT 0,
                                   er_contrib      REAL    DEFAULT 0,
                                   total_cash      REAL    DEFAULT 0,
                                   remarks         TEXT    DEFAULT ''
                               );
                               """))
                try:
                    cols = s.execute(_t("PRAGMA table_info(payroll_batch_lines)")).fetchall()
                    have = {c.name for c in cols}
                    if "adjustment" not in have:
                        s.execute(_t("ALTER TABLE payroll_batch_lines ADD COLUMN adjustment REAL DEFAULT 0;"))
                    if "advance" not in have:
                        s.execute(_t("ALTER TABLE payroll_batch_lines ADD COLUMN advance REAL DEFAULT 0;"))
                    if "remarks" not in have:
                        s.execute(_t("ALTER TABLE payroll_batch_lines ADD COLUMN remarks TEXT DEFAULT '';"))
                except Exception:
                    pass
                s.execute(_t("""
                               CREATE TABLE IF NOT EXISTS shg_race_map
                               (
                                   account_id TEXT NOT NULL,
                                   race       TEXT NOT NULL,
                                   shg        TEXT NOT NULL,
                                   PRIMARY KEY (account_id, race)
                               );
                               """))
                s.commit()

        # ---------- format + delegates ----------
        HOURS_COLS = {6, 8}  # OT Hours, PT Hours

        def _fmt_cell(col, val_float):
            if col in TEXT_COLS:
                return str(val_float)
            if col in HOURS_COLS:
                return f"{val_float:,.2f}"
            return f"${val_float:,.2f}"

        from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
        header_rows: set[int] = set()

        def _is_header_row(row_idx: int) -> bool:
            return row_idx in header_rows

        class _NoBorderCenterDelegate(QStyledItemDelegate):
            def paint(self, painter, option, index):
                opt = QStyleOptionViewItem(option)
                opt.displayAlignment = Qt.AlignCenter | Qt.AlignVCenter
                opt.state &= ~QStyle.State_HasFocus
                super().paint(painter, opt, index)

        class _BorderedCenterDelegate(QStyledItemDelegate):
            def __init__(self, header_checker, parent=None):
                super().__init__(parent)
                self._header_checker = header_checker

            def paint(self, painter, option, index):
                from PySide6.QtGui import QColor, QPen, QBrush
                opt = QStyleOptionViewItem(option)
                opt.displayAlignment = Qt.AlignCenter | Qt.AlignVCenter
                opt.state &= ~QStyle.State_HasFocus
                if self._header_checker(index.row()):
                    opt.state &= ~QStyle.State_Selected
                    opt.state &= ~QStyle.State_MouseOver
                    painter.save()
                    brush = index.data(Qt.BackgroundRole)
                    if isinstance(brush, QBrush):
                        painter.fillRect(opt.rect, brush)
                    elif brush:
                        painter.fillRect(opt.rect, QBrush(brush))
                    else:
                        painter.fillRect(opt.rect, opt.palette.base())
                    text = index.data(Qt.DisplayRole)
                    if text:
                        text_color = opt.palette.text().color()
                        painter.setPen(text_color)
                        header_font = QFont(opt.font)
                        header_font.setBold(True)
                        painter.setFont(header_font)
                        margin = 12 + int(index.data(Qt.UserRole) or 0) * 16
                        text_rect = opt.rect.adjusted(margin, 0, -12, 0)
                        alignment = index.data(Qt.TextAlignmentRole)
                        if alignment is None:
                            alignment = Qt.AlignLeft | Qt.AlignVCenter
                        painter.drawText(text_rect, alignment, text)
                    painter.restore()
                    return

                super().paint(painter, opt, index)
                r = option.rect
                pen = QPen(QColor("#e5e7eb"))
                pen.setWidth(1)
                painter.save()
                painter.setPen(pen)
                painter.drawRect(r.adjusted(0, 0, -1, -1))
                painter.restore()

        class _GroupHeaderDelegate(QStyledItemDelegate):
            def paint(self, painter, option, index):
                opt = QStyleOptionViewItem(option)
                opt.state &= ~QStyle.State_HasFocus
                opt.state &= ~QStyle.State_Selected
                painter.save()
                brush = index.data(Qt.BackgroundRole)
                if isinstance(brush, QBrush):
                    painter.fillRect(opt.rect, brush)
                elif brush:
                    painter.fillRect(opt.rect, QBrush(brush))
                else:
                    painter.fillRect(opt.rect, opt.palette.base())
                text = index.data(Qt.DisplayRole)
                if text:
                    text_color = opt.palette.text().color()
                    painter.setPen(text_color)
                    header_font = QFont(opt.font)
                    header_font.setBold(True)
                    painter.setFont(header_font)
                    margin = 12 + int(index.data(Qt.UserRole) or 0) * 16
                    text_rect = opt.rect.adjusted(margin, 0, -12, 0)
                    alignment = index.data(Qt.TextAlignmentRole)
                    if alignment is None:
                        alignment = Qt.AlignLeft | Qt.AlignVCenter
                    painter.drawText(text_rect, alignment, text)
                painter.restore()

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

        # Columns per request: Month first, then Year, requested totals, then Status
        batch_headers = [
            "Month", "Year",
            "Total", "Advance", "Employer SHG", "SDL",
            "CPF EE", "CPF ER", "CPF Total",
            "Levy", "EE Contribution", "ER Contribution", "Cash Payout",
            "Status"
        ]
        tbl = QTableWidget(0, len(batch_headers))
        tbl.setHorizontalHeaderLabels(batch_headers)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setSelectionMode(QTableWidget.SingleSelection)
        tbl.setSortingEnabled(True)

        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)  # auto-size to contents
        hdr.setStretchLastSection(False)
        hdr.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)  # center header text
        v.addWidget(tbl, 1)

        self.tabs.addTab(host, "Salary Review")

        # ---------- data ops ----------
        _ensure_tables()

        def _money(x) -> str:
            try:
                return f"${float(x or 0):,.2f}"
            except Exception:
                return "$0.00"

        def _add_centered(r, c, text, batch_id=None):
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if batch_id is not None:
                it.setData(Qt.UserRole, int(batch_id))
            tbl.setItem(r, c, it)

        def _load_batches():
            from sqlalchemy import text
            tbl.setRowCount(0)
            with SessionLocal() as s:
                rows = s.execute(text("""
                    SELECT id, year, month, status
                    FROM payroll_batches
                    ORDER BY year DESC, month DESC, id DESC
                """)).fetchall()

                for b in rows:
                    sums = s.execute(text("""
                        SELECT
                            SUM(line_total)  AS t_total,
                            SUM(advance)     AS t_advance,
                            SUM(shg)         AS t_shg,        -- Employer SHG
                            SUM(sdl)         AS t_sdl,
                            SUM(cpf_emp)     AS t_cpf_ee,
                            SUM(cpf_er)      AS t_cpf_er,
                            SUM(cpf_total)   AS t_cpf_total,
                            SUM(levy)        AS t_levy,
                            SUM(ee_contrib)  AS t_ee_contrib,
                            SUM(er_contrib)  AS t_er_contrib,
                            SUM(total_cash)  AS t_cash
                        FROM payroll_batch_lines
                        WHERE batch_id = :bid
                    """), {"bid": int(b.id)}).fetchone()

                    r = tbl.rowCount()
                    tbl.insertRow(r)

                    # Month name first, then Year
                    m_name = month_name[int(b.month)] if 1 <= int(b.month) <= 12 else str(b.month)
                    _add_centered(r, 0, m_name, batch_id=b.id)
                    _add_centered(r, 1, str(b.year))

                    # Totals in requested order
                    _add_centered(r, 2, _money(getattr(sums, "t_total", 0)))
                    _add_centered(r, 3, _money(getattr(sums, "t_advance", 0)))
                    _add_centered(r, 4, _money(getattr(sums, "t_shg", 0)))  # Employer SHG
                    _add_centered(r, 5, _money(getattr(sums, "t_sdl", 0)))
                    _add_centered(r, 6, _money(getattr(sums, "t_cpf_ee", 0)))
                    _add_centered(r, 7, _money(getattr(sums, "t_cpf_er", 0)))
                    _add_centered(r, 8, _money(getattr(sums, "t_cpf_total", 0)))
                    _add_centered(r, 9, _money(getattr(sums, "t_levy", 0)))
                    _add_centered(r, 10, _money(getattr(sums, "t_ee_contrib", 0)))
                    _add_centered(r, 11, _money(getattr(sums, "t_er_contrib", 0)))
                    _add_centered(r, 12, _money(getattr(sums, "t_cash", 0)))

                    _add_centered(r, 13, b.status or "Draft")

        _load_batches()

        def _selected_batch_id():
            r = tbl.currentRow()
            if r < 0:
                return None
            it = tbl.item(r, 0)
            return it.data(Qt.UserRole) if it else None

        # ---- grid columns ----
        COLS = [
            "Name", "Basic", "Commission", "Incentives", "Allowance",
            "OT Rate", "OT Hours", "PT Rate", "PT Hours",
            "Adjustment (+/-)", "Total", "Levy", "Advance", "SHG", "SDL",
            "CPF EE", "CPF ER", "CPF Total",
            "EE Contrib", "ER Contrib", "Cash Payout", "Remarks"
        ]
        REMARKS_COL = COLS.index("Remarks")
        # Editable only these
        EDITABLE = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, REMARKS_COL}
        from PySide6.QtGui import QColor, QBrush
        TEXT_COLS = {REMARKS_COL}
        DERIVED = set(range(len(COLS))) - (EDITABLE | {0})
        DERIVED_COLOR = QColor("#7a1f1f")  # dark red for uneditable fields

        def _recalc_row(t, row_idx, emp_obj, on_date, name_list=None):
            if emp_obj is None:
                return
            f = lambda c: _rf(t.item(row_idx, c).text()) if t.item(row_idx, c) else 0.0
            basic, com, inc, allw = f(1), f(2), f(3), f(4)
            ot_r, ot_h, pt_r, pt_h = f(5), f(6), f(7), f(8)
            adj = f(9)
            levy = f(11)
            adv = f(12)

            gross = basic + com + inc + allw + (ot_r * ot_h) + (pt_r * pt_h)
            total = gross + adj
            # rules at last day of period
            from datetime import date as _date
            from calendar import monthrange
            y = int(cb_year.currentText())
            m = cb_month.currentIndex() + 1
            on_date = _date(y, m, monthrange(y, m)[1])

            if gross <= 0.0 or _is_casual(emp_obj):
                shg = 0.0
                sdl = 0.0
                ee = 0.0
                er = 0.0
                cpf_t = 0.0
            else:
                shg = _shg_for(emp_obj, gross, on_date)
                sdl = _sdl_for(gross, on_date)
                ee, er, cpf_t = _cpf_for(emp_obj, gross, on_date)
            ee_c = ee + shg
            er_c = er + sdl + levy
            cash = total - ee - shg - adv

            def setv(c, val):
                it = QTableWidgetItem(_fmt_cell(c, float(val)))
                it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c in DERIVED:
                    it.setForeground(QBrush(DERIVED_COLOR))
                t.setItem(row_idx, c, it)

            setv(10, total)
            setv(13, shg)
            setv(14, sdl)
            setv(15, ee)
            setv(16, er)
            setv(17, cpf_t)
            setv(18, ee_c)
            setv(19, er_c)
            setv(20, cash)

        def _recalc_totals(t, row_emps_list):
            sums = [0.0] * t.columnCount()
            for r in range(t.rowCount()):
                if r >= len(row_emps_list) or row_emps_list[r] is None:
                    continue
                for c in range(t.columnCount()):
                    if c in TEXT_COLS:
                        continue
                    try:
                        sums[c] += _rf(t.item(r, c).text())
                    except Exception:
                        pass
            return {
                "total_basic": sums[1],
                "total_er": sums[19],
                "grand_total": sums[20] + sums[19]
            }

        def _open_batch_dialog(batch_id=None, read_only=False, y=None, m=None):
            from sqlalchemy import text
            from calendar import monthrange

            dlg = QDialog(self)

            if batch_id:
                with SessionLocal() as s:
                    b = s.execute(text("SELECT year, month, status FROM payroll_batches WHERE id=:i"),
                                  {"i": batch_id}).fetchone()
                    if not b:
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, "Salary Review", "Batch not found.")
                        return
                    y, m, status = int(b.year), int(b.month), b.status
                    if status == "Submitted" and not read_only:
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.information(self, "Salary Review", "Batch is submitted. Opening in view mode.")
                        read_only = True

            dlg.setWindowTitle("Salary Review")
            lay = QVBoxLayout(dlg)

            hdr = QHBoxLayout()
            hdr.addWidget(QLabel(f"Period: {month_name[m]} {y}"))
            hdr.addStretch(1)
            lay.addLayout(hdr)

            # Single grid. Column 0 (Name) is hidden; names shown in frozen row header.
            grid = QTableWidget(0, len(COLS))
            grid.setHorizontalHeaderLabels(COLS)
            grid.setShowGrid(False)
            grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            grid.setColumnHidden(0, True)
            vh = grid.verticalHeader()
            vh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            vh.setFixedWidth(220)
            vh.setSectionsClickable(False)
            lay.addWidget(grid, 1)

            # Delegates
            nb = _NoBorderCenterDelegate(grid)
            bd = _BorderedCenterDelegate(_is_header_row, grid)
            header_delegate = _GroupHeaderDelegate(grid)
            for c in range(len(COLS)):
                grid.setItemDelegateForColumn(c, bd if c in EDITABLE else nb)

            from datetime import date as _date
            on_date = _date(y, m, monthrange(y, m)[1])
            row_emps = []

            def _set_row_header(r, name, *, level: int = 0, bold: bool = False):
                text = f"{'    ' * level}{(name or '').strip()}"
                hi = QTableWidgetItem(text)
                hi.setToolTip((name or "").strip())
                if bold:
                    font = hi.font()
                    font.setBold(True)
                    hi.setFont(font)
                grid.setVerticalHeaderItem(r, hi)

            def _add_group_header(label: str, level: int):
                r = grid.rowCount()
                grid.insertRow(r)
                row_emps.append(None)
                header_rows.add(r)
                _set_row_header(r, label, level=level, bold=True)
                shade = "#f3f4f6" if level == 0 else "#f9fafb"
                brush = QBrush(QColor(shade))
                for c in range(grid.columnCount()):
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemIsEnabled)
                    item.setBackground(brush)
                    if c == 0:
                        item.setData(Qt.UserRole, level)
                    grid.setItem(r, c, item)
                grid.setItemDelegateForRow(r, header_delegate)

            def _add_employee_row(emp: Employee, line_data=None):
                r = grid.rowCount()
                grid.insertRow(r)

                it_name = QTableWidgetItem(emp.full_name or "")
                it_name.setFlags(it_name.flags() & ~Qt.ItemIsEditable)
                grid.setItem(r, 0, it_name)
                _set_row_header(r, emp.full_name or "", level=2)

                def putnum(c, v, editable):
                    txt = _fmt_cell(c, float(v)) if v is not None else ""
                    it = QTableWidgetItem(txt)
                    if c != 0:
                        it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    flags = it.flags()
                    if editable and (not read_only):
                        it.setFlags(flags | Qt.ItemIsEditable)
                    else:
                        it.setFlags(flags & ~Qt.ItemIsEditable)
                        if c in DERIVED:
                            it.setForeground(QBrush(DERIVED_COLOR))
                    grid.setItem(r, c, it)

                def puttext(c, v, editable):
                    it = QTableWidgetItem(str(v or ""))
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    flags = it.flags()
                    if editable and (not read_only):
                        it.setFlags(flags | Qt.ItemIsEditable)
                    else:
                        it.setFlags(flags & ~Qt.ItemIsEditable)
                    grid.setItem(r, c, it)

                if line_data is not None:
                    putnum(1, line_data.basic_salary, True)
                    putnum(2, line_data.commission, True)
                    putnum(3, line_data.incentives, True)
                    putnum(4, line_data.allowance, True)
                    putnum(5, line_data.overtime_rate, True)
                    putnum(6, line_data.overtime_hours, True)
                    putnum(7, line_data.part_time_rate, True)
                    putnum(8, line_data.part_time_hours, True)

                    gross = (line_data.basic_salary + line_data.commission + line_data.incentives + line_data.allowance +
                             (line_data.overtime_rate * line_data.overtime_hours) +
                             (line_data.part_time_rate * line_data.part_time_hours))
                    adj_val = getattr(line_data, "adjustment", 0.0)
                    line_total = getattr(line_data, "line_total", None)
                    if line_total is None:
                        line_total = gross + adj_val
                    putnum(9, adj_val, True)
                    putnum(10, line_total, False)
                    putnum(11, line_data.levy, True)
                    putnum(12, line_data.advance, True)
                    putnum(13, line_data.shg, False)
                    putnum(14, line_data.sdl, False)
                    putnum(15, line_data.cpf_emp, False)
                    putnum(16, line_data.cpf_er, False)
                    putnum(17, line_data.cpf_total, False)
                    putnum(18, line_data.ee_contrib, False)
                    putnum(19, line_data.er_contrib, False)
                    putnum(20, line_data.total_cash, False)
                    puttext(REMARKS_COL, getattr(line_data, "remarks", ""), True)
                else:
                    putnum(1, getattr(emp, "basic_salary", 0.0), True)
                    putnum(2, 0.0, True)
                    putnum(3, getattr(emp, "incentives", 0.0), True)
                    putnum(4, getattr(emp, "allowance", 0.0), True)
                    putnum(5, getattr(emp, "overtime_rate", 0.0), True)
                    putnum(6, 0.0, True)
                    putnum(7, getattr(emp, "parttime_rate", getattr(emp, "part_time_rate", 0.0)), True)
                    putnum(8, 0.0, True)
                    putnum(9, 0.0, True)
                    putnum(10, 0.0, False)
                    putnum(11, getattr(emp, "levy", 0.0), True)
                    putnum(12, getattr(emp, "advance", 0.0), True)
                    putnum(13, 0.0, False)
                    putnum(14, 0.0, False)
                    putnum(15, 0.0, False)
                    putnum(16, 0.0, False)
                    putnum(17, 0.0, False)
                    putnum(18, 0.0, False)
                    putnum(19, 0.0, False)
                    putnum(20, 0.0, False)

                    remark_it = QTableWidgetItem("")
                    remark_it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    if not read_only:
                        remark_it.setFlags(remark_it.flags() | Qt.ItemIsEditable)
                    else:
                        remark_it.setFlags(remark_it.flags() & ~Qt.ItemIsEditable)
                    grid.setItem(r, REMARKS_COL, remark_it)

                row_emps.append(emp)

            type_options = _dropdown_values("Employment Type")
            dept_options = _dropdown_values("Department")
            type_index_map = {opt.casefold(): idx for idx, opt in enumerate(type_options) if opt.strip()}
            type_label_map = {opt.casefold(): opt.strip() for opt in type_options if opt.strip()}
            dept_index_map = {opt.casefold(): idx for idx, opt in enumerate(dept_options) if opt.strip()}
            dept_label_map = {opt.casefold(): opt.strip() for opt in dept_options if opt.strip()}

            UNASSIGNED_TYPE = "Unassigned Employment Type"
            UNASSIGNED_DEPT = "Unassigned Department"

            def _classify(emp: Employee):
                raw_type = (getattr(emp, "employment_type", "") or "").strip()
                if raw_type:
                    key = raw_type.casefold()
                    if key in type_index_map:
                        type_order = (0, type_index_map[key])
                        type_label = type_label_map[key]
                    else:
                        type_order = (1, raw_type.lower())
                        type_label = raw_type
                else:
                    type_order = (2, "")
                    type_label = UNASSIGNED_TYPE

                raw_dept = (getattr(emp, "department", "") or "").strip()
                if raw_dept:
                    dkey = raw_dept.casefold()
                    if dkey in dept_index_map:
                        dept_order = (0, dept_index_map[dkey])
                        dept_label = dept_label_map[dkey]
                    else:
                        dept_order = (1, raw_dept.lower())
                        dept_label = raw_dept
                else:
                    dept_order = (2, "")
                    dept_label = UNASSIGNED_DEPT

                return type_order, type_label, dept_order, dept_label

            entries = []

            if batch_id:
                with SessionLocal() as s:
                    lines = s.execute(text("""
                                           SELECT l.employee_id,
                                                  e.full_name,
                                                  l.basic_salary,
                                                  l.commission,
                                                  l.incentives,
                                                  l.allowance,
                                                  l.overtime_rate,
                                                  l.overtime_hours,
                                                  l.part_time_rate,
                                                  l.part_time_hours,
                                                  l.adjustment,
                                                  l.line_total,
                                                  l.levy,
                                                  l.advance,
                                                  l.shg,
                                                  l.sdl,
                                                  l.cpf_emp,
                                                  l.cpf_er,
                                                  l.cpf_total,
                                                  l.ee_contrib,
                                                  l.er_contrib,
                                                  l.total_cash,
                                                  l.remarks
                                           FROM payroll_batch_lines l
                                                    JOIN employees e ON e.id = l.employee_id
                                           WHERE l.batch_id = :b
                                           """), {"b": batch_id}).fetchall()
                    for ln in lines:
                        emp_obj = s.get(Employee, int(ln.employee_id))
                        if not emp_obj:
                            continue
                        type_order, type_label, dept_order, dept_label = _classify(emp_obj)
                        entries.append({
                            "emp": emp_obj,
                            "line": ln,
                            "type_order": type_order,
                            "type_label": type_label,
                            "dept_order": dept_order,
                            "dept_label": dept_label,
                            "name_key": ((emp_obj.full_name or "").strip().lower())
                        })
            else:
                def _active_employees(y, m):
                    from calendar import monthrange
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

                emps = _active_employees(y, m)
                for e in emps:
                    type_order, type_label, dept_order, dept_label = _classify(e)
                    entries.append({
                        "emp": e,
                        "line": None,
                        "type_order": type_order,
                        "type_label": type_label,
                        "dept_order": dept_order,
                        "dept_label": dept_label,
                        "name_key": ((e.full_name or "").strip().lower())
                    })

            entries.sort(key=lambda row: (row["type_order"], row["dept_order"], row["name_key"]))

            current_type = current_dept = None
            for entry in entries:
                if entry["type_label"] != current_type:
                    _add_group_header(entry["type_label"], level=0)
                    current_type = entry["type_label"]
                    current_dept = None
                if entry["dept_label"] != current_dept:
                    _add_group_header(entry["dept_label"], level=1)
                    current_dept = entry["dept_label"]
                _add_employee_row(entry["emp"], entry["line"])

            # initial compute
            for r, e in enumerate(row_emps):
                _recalc_row(grid, r, e, on_date)

            if not read_only:
                def _cell_changed(r, c):
                    if r >= len(row_emps) or row_emps[r] is None:
                        return
                    if c not in EDITABLE or c in TEXT_COLS:
                        return
                    _recalc_row(grid, r, row_emps[r], on_date)

                grid.cellChanged.connect(_cell_changed)

            btns = QDialogButtonBox(parent=dlg)
            if read_only:
                btns.addButton(QDialogButtonBox.Close)
            else:
                btns.addButton("Save", QDialogButtonBox.AcceptRole)
                btns.addButton("Submit", QDialogButtonBox.ActionRole)
                btns.addButton(QDialogButtonBox.Close)
            export_btn = btns.addButton("Export CSV", QDialogButtonBox.ActionRole)
            lay.addWidget(btns)

            btns.rejected.connect(dlg.reject)

            def _export_csv():
                default_name = f"Salary_Review_{month_name[m]}_{y}.csv"
                path, _ = QFileDialog.getSaveFileName(dlg, "Export Salary Review", default_name, "CSV Files (*.csv)")
                if not path:
                    return
                try:
                    with open(path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(COLS)
                        for r, emp_obj in enumerate(row_emps):
                            if emp_obj is None:
                                continue
                            writer.writerow([
                                (grid.item(r, c).text() if grid.item(r, c) else "")
                                for c in range(grid.columnCount())
                            ])
                    QMessageBox.information(dlg, "Export", f"Exported to {path}")
                except Exception as exc:
                    QMessageBox.warning(dlg, "Export", f"Failed to export.\n{exc}")

            export_btn.clicked.connect(_export_csv)

            def _persist(status=None):
                totals = _recalc_totals(grid, row_emps)
                from sqlalchemy import text
                with SessionLocal() as s:
                    if batch_id is None:
                        r = s.execute(text(
                            "INSERT INTO payroll_batches(year,month,status,total_basic,total_er,grand_total) "
                            "VALUES(:y,:m,:st,:tb,:ter,:gt)"),
                            {"y": y, "m": m, "st": status or "Draft",
                             "tb": totals['total_basic'], "ter": totals['total_er'], "gt": totals['grand_total']})
                        batch_id_local = r.lastrowid
                    else:
                        batch_id_local = batch_id
                        s.execute(text(
                            "UPDATE payroll_batches SET status=:st,total_basic=:tb,total_er=:ter,grand_total=:gt WHERE id=:i"),
                            {"st": status or "Draft", "tb": totals['total_basic'], "ter": totals['total_er'],
                             "gt": totals['grand_total'], "i": batch_id_local})
                        s.execute(text("DELETE FROM payroll_batch_lines WHERE batch_id=:i"), {"i": batch_id_local})

                    for r in range(grid.rowCount()):
                        if r >= len(row_emps):
                            continue
                        emp = row_emps[r]
                        if emp is None:
                            continue
                        def _txt(col):
                            it = grid.item(r, col)
                            return it.text() if it else ""

                        basic = _rf(_txt(1))
                        comm = _rf(_txt(2))
                        inc = _rf(_txt(3))
                        allw = _rf(_txt(4))
                        ot_r = _rf(_txt(5))
                        ot_h = _rf(_txt(6))
                        pt_r = _rf(_txt(7))
                        pt_h = _rf(_txt(8))
                        adj = _rf(_txt(9))
                        tot = _rf(_txt(10))
                        levy = _rf(_txt(11))
                        adv = _rf(_txt(12))
                        shg = _rf(_txt(13))
                        sdl = _rf(_txt(14))
                        cpf_ee = _rf(_txt(15))
                        cpf_er = _rf(_txt(16))
                        cpf_t = _rf(_txt(17))
                        ee_c = _rf(_txt(18))
                        er_c = _rf(_txt(19))
                        cash = _rf(_txt(20))
                        remarks_val = _txt(REMARKS_COL).strip()
                        s.execute(text("""
                                       INSERT INTO payroll_batch_lines(batch_id, employee_id, basic_salary, commission,
                                                                       incentives, allowance,
                                                                       overtime_rate, overtime_hours, part_time_rate,
                                                                       part_time_hours, adjustment,
                                                                       levy, advance, shg, sdl, cpf_emp, cpf_er,
                                                                       cpf_total,
                                                                       line_total, ee_contrib, er_contrib, total_cash,
                                                                       remarks)
                                       VALUES (:b, :e, :ba, :co, :in, :al, :otr, :oth, :ptr, :pth, :adj, :lev, :adv, :shg,
                                               :sdl, :ee, :er, :cpt, :lt, :eec, :erc, :cash, :rmk)
                                       """), {
                            "b": batch_id_local, "e": int(emp.id),
                            "ba": basic, "co": comm, "in": inc, "al": allw,
                            "otr": ot_r, "oth": ot_h, "ptr": pt_r, "pth": pt_h,
                            "adj": adj,
                            "lev": levy, "adv": adv, "shg": shg, "sdl": sdl,
                            "ee": cpf_ee, "er": cpf_er, "cpt": cpf_t,
                            "lt": tot, "eec": ee_c, "erc": er_c, "cash": cash,
                            "rmk": remarks_val
                        })
                    s.commit()
                return batch_id_local

            def _on_clicked(btn):
                t = btn.text().lower()
                from PySide6.QtWidgets import QMessageBox
                if "save" in t:
                    _persist("Draft")
                    QMessageBox.information(dlg, "Salary Review", "Saved.")
                    _load_batches()
                elif "submit" in t:
                    _persist("Submitted")
                    QMessageBox.information(dlg, "Salary Review", "Submitted and locked.")
                    _load_batches()
                    dlg.accept()
                else:
                    dlg.reject()

            if not read_only:
                btns.clicked.connect(_on_clicked)

            dlg.resize(1260, 640)
            dlg.exec()

        def _create():
            y = int(cb_year.currentText())
            m = cb_month.currentIndex() + 1
            _open_batch_dialog(None, False, y, m)

        def _edit():
            bid = _selected_batch_id()
            from PySide6.QtWidgets import QMessageBox
            if not bid:
                QMessageBox.information(host, "Salary Review", "Select a batch.")
                return
            _open_batch_dialog(bid, False)

        def _view():
            bid = _selected_batch_id()
            from PySide6.QtWidgets import QMessageBox
            if not bid:
                QMessageBox.information(host, "Salary Review", "Select a batch.")
                return
            _open_batch_dialog(bid, True)

        def _submit():
            bid = _selected_batch_id()
            from PySide6.QtWidgets import QMessageBox
            if not bid:
                QMessageBox.information(host, "Salary Review", "Select a batch.")
                return
            from sqlalchemy import text
            with SessionLocal() as s:
                s.execute(text("UPDATE payroll_batches SET status='Submitted' WHERE id=:i"), {"i": bid})
                s.commit()
            _load_batches()

        def _delete():
            bid = _selected_batch_id()
            from PySide6.QtWidgets import QMessageBox
            if not bid:
                QMessageBox.information(host, "Salary Review", "Select a batch.")
                return
            if QMessageBox.question(host, "Delete",
                                    "Delete selected batch? This removes all lines.") == QMessageBox.Yes:
                from sqlalchemy import text
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
        self.v_month.setCurrentIndex(date.today().month - 1)
        self.v_year = QComboBox()
        this_year = date.today().year
        self.v_year.addItems([str(y) for y in range(this_year - 5, this_year + 6)])
        self.v_year.setCurrentText(str(this_year))

        ctrl.addWidget(QLabel("Employee"))
        ctrl.addWidget(self.v_emp)
        ctrl.addSpacing(12)
        ctrl.addWidget(QLabel("Month"))
        ctrl.addWidget(self.v_month)
        ctrl.addSpacing(12)
        ctrl.addWidget(QLabel("Year"))
        ctrl.addWidget(self.v_year)
        ctrl.addStretch(1)

        self.btn_pdf = QPushButton("Export PDF")
        self.btn_pdf.clicked.connect(self._export_voucher_pdf)
        ctrl.addWidget(self.btn_pdf)
        v.addLayout(ctrl)

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
        from sqlalchemy import text
        emp_id = self.v_emp.currentData()
        m1 = (self.v_month.currentIndex() + 1) or 1
        y = int(self.v_year.currentText())

        emp = None
        line = None
        with SessionLocal() as s:
            emp = s.get(Employee, emp_id) if emp_id else None
            try:
                batch = s.execute(text("""
                                       SELECT id, status
                                       FROM payroll_batches
                                       WHERE year =:y AND month =:m
                                       ORDER BY CASE status WHEN 'Submitted' THEN 1 ELSE 2
                                       END, id DESC
                    LIMIT 1
                                       """), {"y": y, "m": m1}).fetchone()
                if batch and emp_id:
                    ln = s.execute(text("""
                                        SELECT basic_salary,
                                               commission,
                                               incentives,
                                               allowance,
                                               overtime_rate,
                                               overtime_hours,
                                               part_time_rate,
                                               part_time_hours,
                                               adjustment,
                                               levy,
                                               advance,
                                               shg,
                                               sdl,
                                               cpf_emp,
                                               cpf_er,
                                               cpf_total,
                                               ee_contrib,
                                               er_contrib,
                                               total_cash
                                        FROM payroll_batch_lines
                                        WHERE batch_id = :b
                                          AND employee_id = :e LIMIT 1
                                        """), {"b": int(batch.id), "e": int(emp_id)}).fetchone()
                    if ln:
                        line = {
                            "basic_salary": float(ln.basic_salary or 0.0),
                            "commission": float(ln.commission or 0.0),
                            "incentives": float(ln.incentives or 0.0),
                            "allowance": float(ln.allowance or 0.0),
                            "overtime_rate": float(ln.overtime_rate or 0.0),
                            "overtime_hours": float(ln.overtime_hours or 0.0),
                            "part_time_rate": float(ln.part_time_rate or 0.0),
                            "part_time_hours": float(ln.part_time_hours or 0.0),
                            "adjustment": float(ln.adjustment or 0.0),
                            "levy": float(ln.levy or 0.0),
                            "advance": float(ln.advance or 0.0),
                            "shg": float(ln.shg or 0.0),
                            "sdl": float(ln.sdl or 0.0),
                            "cpf_emp": float(ln.cpf_emp or 0.0),
                            "cpf_er": float(ln.cpf_er or 0.0),
                            "cpf_total": float(ln.cpf_total or 0.0)
                        }
            except Exception:
                pass

        html = _voucher_html(_company(), emp, y, m1, line=line)
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
        import csv
        from PySide6.QtWidgets import QMessageBox

        # ---------- durable schema for rules (v2) ----------
        def _ensure_settings_tables():
            with SessionLocal() as s:
                # Legacy shells remain; v2 tables hold what the UI edits.
                s.execute(text("""
                               CREATE TABLE IF NOT EXISTS cpf_rules_v2
                               (
                                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                                   account_id TEXT NOT NULL,
                                   age_bracket TEXT NOT NULL,
                                   residency TEXT NOT NULL,
                                   pr_year INTEGER,
                                   salary_from REAL,
                                   salary_to REAL,
                                   total_pct_tw REAL,
                                   total_pct_tw_minus REAL,
                                   ee_pct_tw REAL,
                                   ee_pct_tw_minus REAL,
                                   cpf_total_cap REAL,
                                   cpf_employee_cap REAL,
                                   effective_from TEXT,
                                   notes TEXT
                               )"""))
                s.execute(text("""
                               CREATE TABLE IF NOT EXISTS shg_rules_v2
                               (
                                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                                   account_id TEXT NOT NULL,
                                   shg TEXT NOT NULL,
                                   income_from REAL,
                                   income_to REAL,
                                   contribution_type TEXT,
                                   contribution_value REAL,
                                   effective_from TEXT,
                                   notes TEXT
                               )"""))
                s.execute(text("""
                               CREATE TABLE IF NOT EXISTS sdl_rules_v2
                               (
                                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                                   account_id TEXT NOT NULL,
                                   salary_from REAL,
                                   salary_to REAL,
                                   rate_type TEXT,
                                   rate_value REAL,
                                   effective_from TEXT,
                                   notes TEXT
                               )"""))
                # Race map table used elsewhere
                s.execute(text("""
                               CREATE TABLE IF NOT EXISTS shg_race_map
                               (
                                   account_id TEXT NOT NULL,
                                   race TEXT NOT NULL,
                                   shg TEXT NOT NULL,
                                   PRIMARY KEY (account_id, race)
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

        def _ri(x):
            try:
                xs = str(x).strip()
                return int(xs) if xs else None
            except:
                return None

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
            path, _ = QFileDialog.getSaveFileName(self, f"{title} CSV Template", f"{title}_template.csv",
                                                  "CSV Files (*.csv)")
            if not path: return
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(headers)
            QMessageBox.information(self, "Template", f"Created: {path}")

        def _list_defined_races():
            races = set()
            try:
                with SessionLocal() as s:
                    tbls = s.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
                    names = [t.name for t in tbls]

                    def columns_of(table):
                        try:
                            cols = s.execute(text(f"PRAGMA table_info({table})")).fetchall()
                            return [c.name for c in cols]
                        except Exception:
                            return []

                    preferred = [
                        "employee_dropdowns", "dropdown_values", "dropdowns",
                        "settings_dropdowns", "hr_dropdowns", "lookup_values",
                        "meta_choices", "choices", "employee_meta",
                        "employee_settings", "hr_options", "hr_option_values"
                    ]
                    ordered = [t for t in preferred if t in names] + [t for t in names if t not in preferred]

                    for tbl in ordered:
                        cols = [c.lower() for c in columns_of(tbl)]
                        if not cols:
                            continue

                        direct_cols = [c for c in cols if "race" in c]
                        for rc in direct_cols:
                            try:
                                rows = s.execute(
                                    text(f"SELECT DISTINCT {rc} AS v FROM {tbl} WHERE {rc} IS NOT NULL")).fetchall()
                                for r in rows:
                                    v = getattr(r, "v", None)
                                    if v and str(v).strip():
                                        races.add(str(v).strip())
                            except Exception:
                                pass

                        group_cols = [c for c in cols if
                                      c in ("category", "group", "group_name", "type", "key", "field", "option_group")]
                        value_cols = [c for c in cols if c in ("value", "label", "name", "option", "text")]
                        for gc in group_cols:
                            for vc in value_cols:
                                try:
                                    rows = s.execute(text(
                                        f"SELECT DISTINCT {vc} AS v FROM {tbl} "
                                        f"WHERE lower({gc}) IN ('race','races') AND {vc} IS NOT NULL"
                                    )).fetchall()
                                    for r in rows:
                                        v = getattr(r, "v", None)
                                        if v and str(v).strip():
                                            races.add(str(v).strip())
                                except Exception:
                                    pass

                    if not races:
                        vals = s.query(Employee.race).filter(Employee.account_id == tenant_id()).all()
                        for (rv,) in vals:
                            if rv and str(rv).strip():
                                races.add(str(rv).strip())
            except Exception:
                try:
                    with SessionLocal() as s:
                        vals = s.query(Employee.race).filter(Employee.account_id == tenant_id()).all()
                        for (rv,) in vals:
                            if rv and str(rv).strip():
                                races.add(str(rv).strip())
                except Exception:
                    pass

            return sorted(races, key=lambda x: x.lower())

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

        # ---------- Voucher box ----------
        voucher_box = QGroupBox("Voucher Settings")
        f_v = QFormLayout(voucher_box)

        self.voucher_format = QLineEdit(globals().get("_VOUCHER_FMT", "SV-{YYYY}{MM}-{EMP}"))
        self.voucher_format.setMaximumWidth(340)
        self.voucher_preview = QLabel("")
        btn_preview = QPushButton("Preview")
        btn_preview.setMaximumWidth(120)
        btn_apply = QPushButton("Apply")
        btn_apply.setMaximumWidth(120)

        def _preview_code():
            sample = (self.voucher_format.text() or "SV-{YYYY}{MM}-{EMP}")
            code = (sample.replace("{YYYY}", "2025")
                    .replace("{MM}", "01")
                    .replace("{EMP}", "EMP001"))
            self.voucher_preview.setText(f"Preview: {code}")

        def _apply_format():
            fmt = (self.voucher_format.text().strip() or "SV-{YYYY}{MM}-{EMP}")
            globals()["_VOUCHER_FMT"] = fmt
            _save_voucher_format_to_db(fmt)
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
            path, _ = QFileDialog.getOpenFileName(self, "Select Company Stamp", "", "Images (*.png *.jpg *.jpeg *.gif)")
            if not path:
                return
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                # persist into MAIN DB under current tenant
                with MainSession() as s:
                    row = s.query(CompanySettings).filter(CompanySettings.account_id == str(tenant_id())).first()
                    if not row:
                        row = CompanySettings(account_id=str(tenant_id()))
                        s.add(row)
                        s.flush()
                    row.stamp = raw
                    s.commit()

                # live preview
                b64 = base64.b64encode(raw).decode("ascii")
                self._company_stamp_b64 = b64
                globals()["_STAMP_B64"] = b64
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
            try:
                with MainSession() as s:
                    row = s.query(CompanySettings).filter(CompanySettings.account_id == str(tenant_id())).first()
                    if row:
                        row.stamp = None
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

        # ---------- CPF (v2 two-term structure) ----------
        cpf_headers = [
            "Age Bracket", "Residency", "Year (PR)",
            "Salary From", "Salary To",
            "Total % TW", "Total % (TW-500)", "EE % TW", "EE % (TW-500)",
            "CPF Total Cap", "CPF Employee Cap", "Effective From", "Notes"
        ]
        cpf_box = QGroupBox("CPF Rules")
        cpf_v = QVBoxLayout(cpf_box)
        cpf_hint = QLabel(
            "Two-term: X%×TW + Y%×max(TW-500,0). Enter X and Y. Caps optional. Effective From in DD/MM/YYYY.")
        cpf_hint.setStyleSheet("color:#6b7280;")
        cpf_v.addWidget(cpf_hint)
        self.cpf_tbl = _mk_table(cpf_headers)
        cpf_v.addWidget(self.cpf_tbl)
        row = QHBoxLayout()
        b_add = QPushButton("Add")
        b_del = QPushButton("Delete")
        b_imp = QPushButton("Import CSV")
        b_exp = QPushButton("Export CSV")
        b_tpl = QPushButton("CSV Template")
        b_val = QPushButton("Validate")
        b_del_all = QPushButton("Delete all")
        for b in (b_add, b_del): row.addWidget(b)
        row.addStretch(1)
        for b in (b_imp, b_exp, b_tpl, b_val, b_del_all): row.addWidget(b)
        cpf_v.addLayout(row)
        v.addWidget(cpf_box)

        # ---------- SHG (v2) ----------
        shg_headers = ["SHG", "Income From", "Income To", "Contribution Type", "Contribution Value", "Effective From",
                       "Notes"]
        shg_box = QGroupBox("SHG Rules")
        shg_v = QVBoxLayout(shg_box)
        shg_hint = QLabel(
            "Type: flat or percent. Value is number only. Effective From in DD/MM/YYYY. Race→SHG map controls which table applies.")
        shg_hint.setStyleSheet("color:#6b7280;")
        shg_v.addWidget(shg_hint)
        self.shg_tbl = _mk_table(shg_headers)
        shg_v.addWidget(self.shg_tbl)
        row2 = QHBoxLayout()
        s_add = QPushButton("Add")
        s_del = QPushButton("Delete")
        s_imp = QPushButton("Import CSV")
        s_exp = QPushButton("Export CSV")
        s_tpl = QPushButton("CSV Template")
        s_val = QPushButton("Validate")
        s_map = QPushButton("Manage Race→SHG")
        s_del_all = QPushButton("Delete all")
        for b in (s_add, s_del): row2.addWidget(b)
        row2.addStretch(1)
        for b in (s_imp, s_exp, s_tpl, s_val, s_map, s_del_all): row2.addWidget(b)
        shg_v.addLayout(row2)
        v.addWidget(shg_box)

        # ---------- SDL (v2) ----------
        sdl_headers = ["Salary From", "Salary To", "Rate Type", "Rate Value", "Effective From", "Notes"]
        sdl_box = QGroupBox("SDL Rules")
        sdl_v = QVBoxLayout(sdl_box)
        sdl_hint = QLabel(
            "Rate Type: percent or flat. If percent, enter 0.25 for 0.25%. Blank 'To' = no upper limit. Effective From in DD/MM/YYYY.")
        sdl_hint.setStyleSheet("color:#6b7280;")
        sdl_v.addWidget(sdl_hint)
        self.sdl_tbl = _mk_table(sdl_headers)
        sdl_v.addWidget(self.sdl_tbl)
        row3 = QHBoxLayout()
        d_add = QPushButton("Add")
        d_del = QPushButton("Delete")
        d_imp = QPushButton("Import CSV")
        d_exp = QPushButton("Export CSV")
        d_tpl = QPushButton("CSV Template")
        d_val = QPushButton("Validate")
        d_del_all = QPushButton("Delete all")
        for b in (d_add, d_del): row3.addWidget(b)
        row3.addStretch(1)
        for b in (d_imp, d_exp, d_tpl, d_val, d_del_all): row3.addWidget(b)
        sdl_v.addLayout(row3)
        v.addWidget(sdl_box)

        # ---------- persistence: save / load / delete-all ----------
        acct = lambda: str(tenant_id())

        def _save_cpf_rules():
            with SessionLocal() as s:
                s.execute(text("DELETE FROM cpf_rules_v2 WHERE account_id=:a"), {"a": acct()})
                for r in range(self.cpf_tbl.rowCount()):
                    g = lambda c: (self.cpf_tbl.item(r, c).text().strip() if self.cpf_tbl.item(r, c) else "")
                    s.execute(text("""
                                   INSERT INTO cpf_rules_v2(account_id, age_bracket, residency, pr_year, salary_from,
                                                            salary_to,
                                                            total_pct_tw, total_pct_tw_minus, ee_pct_tw,
                                                            ee_pct_tw_minus,
                                                            cpf_total_cap, cpf_employee_cap, effective_from, notes)
                                   VALUES (:a, :age, :res, :yr, :sf, :st, :ttw, :ttwm, :eetw, :eetwm, :ct, :ce, :eff,
                                           :notes)"""), {
                                  "a": acct(),
                                  "age": g(0), "res": g(1), "yr": _ri(g(2)),
                                  "sf": _rf(g(3)), "st": _rf(g(4)),
                                  "ttw": _rf(g(5)), "ttwm": _rf(g(6)),
                                  "eetw": _rf(g(7)), "eetwm": _rf(g(8)),
                                  "ct": _rf(g(9)), "ce": _rf(g(10)),
                                  "eff": g(11), "notes": g(12)
                              })
                s.commit()

        def _load_cpf_rules():
            self.cpf_tbl.setRowCount(0)
            with SessionLocal() as s:
                rows = s.execute(text("""
                                      SELECT age_bracket,
                                             residency,
                                             pr_year,
                                             salary_from,
                                             salary_to,
                                             total_pct_tw,
                                             total_pct_tw_minus,
                                             ee_pct_tw,
                                             ee_pct_tw_minus,
                                             cpf_total_cap,
                                             cpf_employee_cap,
                                             effective_from,
                                             notes
                                      FROM cpf_rules_v2
                                      WHERE account_id = :a
                                      ORDER BY id ASC
                                      """), {"a": acct()}).fetchall()
            for row in rows:
                r = self.cpf_tbl.rowCount()
                self.cpf_tbl.insertRow(r)
                vals = [
                    row.age_bracket or "", row.residency or "",
                    "" if row.pr_year is None else str(row.pr_year),
                    f"{(row.salary_from or 0):g}", f"{(row.salary_to or 0):g}",
                    f"{(row.total_pct_tw or 0):g}", f"{(row.total_pct_tw_minus or 0):g}",
                    f"{(row.ee_pct_tw or 0):g}", f"{(row.ee_pct_tw_minus or 0):g}",
                    f"{(row.cpf_total_cap or 0):g}", f"{(row.cpf_employee_cap or 0):g}",
                    row.effective_from or "", row.notes or ""
                ]
                for c, v in enumerate(vals):
                    self.cpf_tbl.setItem(r, c, QTableWidgetItem(v))

        def _save_shg_rules():
            with SessionLocal() as s:
                s.execute(text("DELETE FROM shg_rules_v2 WHERE account_id=:a"), {"a": acct()})
                for r in range(self.shg_tbl.rowCount()):
                    g = lambda c: (self.shg_tbl.item(r, c).text().strip() if self.shg_tbl.item(r, c) else "")
                    s.execute(text("""
                                   INSERT INTO shg_rules_v2(account_id, shg, income_from, income_to,
                                                            contribution_type, contribution_value, effective_from,
                                                            notes)
                                   VALUES (:a, :shg, :f, :t, :typ, :val, :eff, :notes)"""), {
                                  "a": acct(),
                                  "shg": g(0).upper(),
                                  "f": _rf(g(1)), "t": _rf(g(2)),
                                  "typ": g(3).lower(), "val": _rf(g(4)),
                                  "eff": g(5), "notes": g(6)
                              })
                s.commit()

        def _load_shg_rules():
            self.shg_tbl.setRowCount(0)
            with SessionLocal() as s:
                rows = s.execute(text("""
                                      SELECT shg,
                                             income_from,
                                             income_to,
                                             contribution_type,
                                             contribution_value,
                                             effective_from,
                                             notes
                                      FROM shg_rules_v2
                                      WHERE account_id = :a
                                      ORDER BY id ASC
                                      """), {"a": acct()}).fetchall()
            for row in rows:
                r = self.shg_tbl.rowCount()
                self.shg_tbl.insertRow(r)
                vals = [
                    row.shg or "", f"{(row.income_from or 0):g}", f"{(row.income_to or 0):g}",
                    row.contribution_type or "", f"{(row.contribution_value or 0):g}",
                    row.effective_from or "", row.notes or ""
                ]
                for c, v in enumerate(vals):
                    self.shg_tbl.setItem(r, c, QTableWidgetItem(v))

        def _save_sdl_rules():
            with SessionLocal() as s:
                s.execute(text("DELETE FROM sdl_rules_v2 WHERE account_id=:a"), {"a": acct()})
                for r in range(self.sdl_tbl.rowCount()):
                    g = lambda c: (self.sdl_tbl.item(r, c).text().strip() if self.sdl_tbl.item(r, c) else "")
                    s.execute(text("""
                                   INSERT INTO sdl_rules_v2(account_id, salary_from, salary_to, rate_type, rate_value,
                                                            effective_from, notes)
                                   VALUES (:a, :f, :t, :typ, :val, :eff, :notes)"""), {
                                  "a": acct(),
                                  "f": _rf(g(0)), "t": _rf(g(1)),
                                  "typ": g(2).lower(), "val": _rf(g(3)),
                                  "eff": g(4), "notes": g(5)
                              })
                s.commit()

        def _load_sdl_rules():
            self.sdl_tbl.setRowCount(0)
            with SessionLocal() as s:
                rows = s.execute(text("""
                                      SELECT salary_from, salary_to, rate_type, rate_value, effective_from, notes
                                      FROM sdl_rules_v2
                                      WHERE account_id = :a
                                      ORDER BY id ASC
                                      """), {"a": acct()}).fetchall()
            for row in rows:
                r = self.sdl_tbl.rowCount()
                self.sdl_tbl.insertRow(r)
                vals = [
                    f"{(row.salary_from or 0):g}", f"{(row.salary_to or 0):g}",
                    row.rate_type or "", f"{(row.rate_value or 0):g}",
                    row.effective_from or "", row.notes or ""
                ]
                for c, v in enumerate(vals):
                    self.sdl_tbl.setItem(r, c, QTableWidgetItem(v))

        def _delete_all_cpf():
            if QMessageBox.question(self, "Delete all", "Delete all CPF rules?") == QMessageBox.Yes:
                with SessionLocal() as s:
                    s.execute(text("DELETE FROM cpf_rules_v2 WHERE account_id=:a"), {"a": acct()})
                    s.commit()
                self.cpf_tbl.setRowCount(0)

        def _delete_all_shg():
            if QMessageBox.question(self, "Delete all", "Delete all SHG rules?") == QMessageBox.Yes:
                with SessionLocal() as s:
                    s.execute(text("DELETE FROM shg_rules_v2 WHERE account_id=:a"), {"a": acct()})
                    s.commit()
                self.shg_tbl.setRowCount(0)

        def _delete_all_sdl():
            if QMessageBox.question(self, "Delete all", "Delete all SDL rules?") == QMessageBox.Yes:
                with SessionLocal() as s:
                    s.execute(text("DELETE FROM sdl_rules_v2 WHERE account_id=:a"), {"a": acct()})
                    s.commit()
                self.sdl_tbl.setRowCount(0)

        # ---------- wire buttons ----------
        b_add.clicked.connect(lambda: self.cpf_tbl.insertRow(self.cpf_tbl.rowCount()))
        b_del.clicked.connect(lambda: [self.cpf_tbl.removeRow(r) for r in
                                       sorted({ix.row() for ix in self.cpf_tbl.selectedIndexes()}, reverse=True)])
        b_imp.clicked.connect(lambda: _csv_import(self.cpf_tbl, cpf_headers, "CPF"))
        b_exp.clicked.connect(lambda: _csv_export(self.cpf_tbl, cpf_headers, "CPF"))
        b_tpl.clicked.connect(lambda: _csv_template(cpf_headers, "CPF"))

        def _on_validate_cpf():
            errs = _validate_cpf(self.cpf_tbl)
            if errs:
                QMessageBox.information(self, "CPF Validate", "\n".join(errs))
            else:
                _save_cpf_rules()
                QMessageBox.information(self, "CPF Validate", "OK. Saved.")

        b_val.clicked.connect(_on_validate_cpf)
        b_del_all.clicked.connect(_delete_all_cpf)

        s_add.clicked.connect(lambda: self.shg_tbl.insertRow(self.shg_tbl.rowCount()))
        s_del.clicked.connect(lambda: [self.shg_tbl.removeRow(r) for r in
                                       sorted({ix.row() for ix in self.shg_tbl.selectedIndexes()}, reverse=True)])
        s_imp.clicked.connect(lambda: _csv_import(self.shg_tbl, shg_headers, "SHG"))
        s_exp.clicked.connect(lambda: _csv_export(self.shg_tbl, shg_headers, "SHG"))
        s_tpl.clicked.connect(lambda: _csv_template(shg_headers, "SHG"))

        def _on_validate_shg():
            errs = _validate_shg(self.shg_tbl)
            if errs:
                QMessageBox.information(self, "SHG Validate", "\n".join(errs))
            else:
                _save_shg_rules()
                QMessageBox.information(self, "SHG Validate", "OK. Saved.")

        s_val.clicked.connect(_on_validate_shg)
        s_del_all.clicked.connect(_delete_all_shg)

        def _open_race_shg_map():
            dlg = QDialog(self)
            dlg.setWindowTitle("Race → SHG Mapping")
            lay = QVBoxLayout(dlg)
            info = QLabel("Map each Race to an SHG. Races are pulled from Employee dropdown settings.")
            info.setStyleSheet("color:#6b7280;")
            lay.addWidget(info)

            tbl = QTableWidget(0, 2)
            tbl.setHorizontalHeaderLabels(["Race", "SHG"])
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            lay.addWidget(tbl, 1)

            races = _list_defined_races()
            if not races:
                with SessionLocal() as s:
                    races = sorted({(e.race or "").strip() for e in
                                    s.query(Employee).filter(Employee.account_id == tenant_id()).all()
                                    if (e.race or "").strip()}, key=lambda x: x.lower())

            with SessionLocal() as s:
                rows = s.execute(text("SELECT race, shg FROM shg_race_map WHERE account_id=:a"),
                                 {"a": str(tenant_id())}).fetchall()
                existing = {(r.race or "").strip().lower(): (r.shg or "").strip().upper() for r in rows}

            options = ["MBMF", "CDAC", "SINDA", "ECF", "OTHERS"]  # added OTHERS
            for rname in races:
                r = tbl.rowCount()
                tbl.insertRow(r)
                it = QTableWidgetItem(rname)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                tbl.setItem(r, 0, it)
                combo = QComboBox()
                combo.addItems(options)
                pre = existing.get(rname.strip().lower(), "")
                if pre in options:
                    combo.setCurrentText(pre)
                tbl.setCellWidget(r, 1, combo)

            btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
            lay.addWidget(btns)

            def _save_map():
                with SessionLocal() as s:
                    s.execute(text("DELETE FROM shg_race_map WHERE account_id=:a"), {"a": str(tenant_id())})
                    for r in range(tbl.rowCount()):
                        race = (tbl.item(r, 0).text() if tbl.item(r, 0) else "").strip()
                        shg = (tbl.cellWidget(r, 1).currentText() if tbl.cellWidget(r, 1) else "").strip().upper()
                        if not race or not shg:
                            continue
                        s.execute(text("""
                                       INSERT INTO shg_race_map(account_id, race, shg)
                                       VALUES (:a, :r, :s) ON CONFLICT(account_id, race) DO
                                       UPDATE SET shg=excluded.shg
                                       """), {"a": str(tenant_id()), "r": race, "s": shg})
                    s.commit()
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(dlg, "Race→SHG", "Saved.")
                dlg.accept()

            btns.accepted.connect(_save_map)
            btns.rejected.connect(dlg.reject)
            dlg.resize(560, 440)
            dlg.exec()

        s_map.clicked.connect(_open_race_shg_map)

        d_add.clicked.connect(lambda: self.sdl_tbl.insertRow(self.sdl_tbl.rowCount()))
        d_del.clicked.connect(lambda: [self.sdl_tbl.removeRow(r) for r in
                                       sorted({ix.row() for ix in self.sdl_tbl.selectedIndexes()}, reverse=True)])
        d_imp.clicked.connect(lambda: _csv_import(self.sdl_tbl, sdl_headers, "SDL"))
        d_exp.clicked.connect(lambda: _csv_export(self.sdl_tbl, sdl_headers, "SDL"))
        d_tpl.clicked.connect(lambda: _csv_template(sdl_headers, "SDL"))

        def _on_validate_sdl():
            errs = _validate_sdl(self.sdl_tbl)
            if errs:
                QMessageBox.information(self, "SDL Validate", "\n".join(errs))
            else:
                _save_sdl_rules()
                QMessageBox.information(self, "SDL Validate", "OK. Saved.")

        d_val.clicked.connect(_on_validate_sdl)
        d_del_all.clicked.connect(_delete_all_sdl)

        # ---------- initial load from DB ----------
        _load_cpf_rules()
        _load_shg_rules()
        _load_sdl_rules()

        sa.setWidget(inner)
        self.tabs.addTab(sa, "Settings")

        try:
            _preview_code()
        except Exception:
            pass


from PySide6.QtWidgets import QMessageBox


def _validate_cpf(tbl):
    import re
    errs = []

    def rf(x):
        try:
            return float(str(x).replace(",", "").replace("%", "").strip())
        except:
            return 0.0

    def ri(x):
        try:
            xs = str(x).strip()
            return int(xs) if xs else None
        except:
            return None

    # Date validator: prefer DD/MM/YYYY, also accept DD-MM-YYYY, YYYY-MM-DD, YYYY/MM/DD
    def rd(x):
        s = (str(x or "").strip())
        if not s:
            return None
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                datetime.strptime(s, fmt)
                return True
            except Exception:
                pass
        return False

    for r in range(tbl.rowCount()):
        age = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
        resid = (tbl.item(r, 1).text().strip() if tbl.item(r, 1) else "")
        yr = (tbl.item(r, 2).text().strip() if tbl.item(r, 2) else "")
        sal_from = (tbl.item(r, 3).text().strip() if tbl.item(r, 3) else "0")
        sal_to = (tbl.item(r, 4).text().strip() if tbl.item(r, 4) else "0")

        t_tw = (tbl.item(r, 5).text().strip() if tbl.item(r, 5) else "0")
        t_m = (tbl.item(r, 6).text().strip() if tbl.item(r, 6) else "0")
        ee_tw = (tbl.item(r, 7).text().strip() if tbl.item(r, 7) else "0")
        ee_m = (tbl.item(r, 8).text().strip() if tbl.item(r, 8) else "0")

        cap_total = (tbl.item(r, 9).text().strip() if tbl.item(r, 9) else "0")
        cap_ee = (tbl.item(r, 10).text().strip() if tbl.item(r, 10) else "0")
        eff_from = (tbl.item(r, 11).text().strip() if tbl.item(r, 11) else "")

        s_from = rf(sal_from); s_to = rf(sal_to)
        y = ri(yr)

        if not age or not resid: errs.append(f"Row {r + 1}: missing Age/Residency")
        if age and not re.match(r"^(<=?\d+|>=?\d+|\d+\-\d+|>\d+)$", age.replace(" ", "")):
            errs.append(f"Row {r + 1}: age bracket format")
        if s_from < 0 or s_to < 0: errs.append(f"Row {r + 1}: negative salary range")
        if s_to and s_to < s_from: errs.append(f"Row {r + 1}: Salary To < Salary From")

        for lab, val in (("Total % TW", t_tw), ("Total % (TW-500)", t_m), ("EE % TW", ee_tw), ("EE % (TW-500)", ee_m)):
            try:
                _ = rf(val)
                if rf(val) < 0: errs.append(f"Row {r + 1}: {lab} negative")
            except Exception:
                errs.append(f"Row {r + 1}: {lab} invalid")

        ct = rf(cap_total); ce = rf(cap_ee)
        if y is not None and y < 0: errs.append(f"Row {r + 1}: Year(PR) invalid")
        if ct < 0: errs.append(f"Row {r + 1}: CPF Total Cap cannot be negative")
        if ce < 0: errs.append(f"Row {r + 1}: CPF Employee Cap cannot be negative")
        if eff_from and not rd(eff_from): errs.append(f"Row {r + 1}: Effective From date must be DD/MM/YYYY")
    return errs


def _validate_shg(tbl):
    errs = []

    def rf(x):
        try:
            return float(str(x).replace(",", "").strip())
        except Exception:
            return 0.0

    def rd(x):
        s = (str(x or "").strip())
        if not s:
            return None
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                datetime.strptime(s, fmt)
                return True
            except Exception:
                pass
        return False

    valid_shg = {"MBMF", "CDAC", "SINDA", "ECF", "OTHERS"}  # OTHERS added
    valid_typ = {"flat", "percent"}

    for r in range(tbl.rowCount()):
        shg = (tbl.item(r, 0).text().strip().upper() if tbl.item(r, 0) else "")
        lo = rf(tbl.item(r, 1).text() if tbl.item(r, 1) else "0")
        hi = rf(tbl.item(r, 2).text() if tbl.item(r, 2) else "0")
        ctyp = (tbl.item(r, 3).text().strip().lower() if tbl.item(r, 3) else "")
        cval = rf(tbl.item(r, 4).text() if tbl.item(r, 4) else "0")
        eff  = (tbl.item(r, 5).text().strip() if tbl.item(r, 5) else "")

        if shg not in valid_shg: errs.append(f"Row {r + 1}: SHG must be one of {sorted(valid_shg)}")
        if lo < 0 or hi < 0 or cval < 0: errs.append(f"Row {r + 1}: negative number")
        if hi and hi < lo: errs.append(f"Row {r + 1}: Income To < Income From")
        if ctyp not in valid_typ: errs.append(f"Row {r + 1}: Contribution Type must be flat or percent")
        if eff and not rd(eff): errs.append(f"Row {r + 1}: Effective From date must be DD/MM/YYYY")
    return errs


def _validate_sdl(tbl):
    errs = []
    def rf(x):
        try:
            return float(str(x).replace(",", "").replace("%", "").strip())
        except Exception:
            return 0.0

    def rd(x):
        s = (str(x or "").strip())
        if not s:
            return None
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                datetime.strptime(s, fmt)
                return True
            except Exception:
                pass
        return False

    valid_typ = {"flat", "percent"}

    for r in range(tbl.rowCount()):
        lo = rf(tbl.item(r, 0).text() if tbl.item(r, 0) else "0")
        hi = rf(tbl.item(r, 1).text() if tbl.item(r, 1) else "0")
        rtyp = (tbl.item(r, 2).text().strip().lower() if tbl.item(r, 2) else "")
        rval = rf(tbl.item(r, 3).text() if tbl.item(r, 3) else "0")
        eff  = (tbl.item(r, 4).text().strip() if tbl.item(r, 4) else "")

        if hi and hi < lo: errs.append(f"Row {r + 1}: Salary To < Salary From")
        if rtyp not in valid_typ: errs.append(f"Row {r + 1}: Rate Type must be flat or percent")
        if rval < 0: errs.append(f"Row {r + 1}: Rate Value cannot be negative")
        if eff and not rd(eff): errs.append(f"Row {r + 1}: Effective From date must be DD/MM/YYYY")
    return errs
