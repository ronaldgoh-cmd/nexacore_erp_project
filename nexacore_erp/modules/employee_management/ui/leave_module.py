# leave_module.py — NexaCore ERP (Employee Management > Leave)
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple, List

import traceback
import json

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QLineEdit, QPushButton, QHeaderView, QMessageBox,
    QFormLayout, QAbstractItemView, QDialog, QDialogButtonBox
)

from ....core.database import get_employee_session as SessionLocal
from ....core.tenant import id as tenant_id
from ....core.events import employee_events
from ..models import Employee, LeaveDefault, WorkScheduleDay, Holiday, LeaveEntitlement, SalaryHistory

# expose key for main_window
MODULE_KEY = "salary_management"

def filter_tabs_by_access(self, allowed_keys: list[str] | set[str]):
    allowed = set(allowed_keys or [])
    if not allowed:
        return  # empty = show all
    label_by_key = {
        "summary":  "Summary",
        "review":   "Salary Review",
        "vouchers": "Salary Vouchers",
        "settings": "Settings",
    }
    allowed_labels = {label_by_key[k] for k in allowed if k in label_by_key}
    for i in range(self.tabs.count() - 1, -1, -1):
        if self.tabs.tabText(i) not in allowed_labels:
            self.tabs.removeTab(i)

# =================== ACL helpers and module meta ===================

ROOT_MODULE_NAME = "Employee Management"
MODULE_NAME = "Leave Management"
SUBMODULES = ["Summary", "Application", "All Details", "Adjustments", "Calendar", "User Application History"]

# try to import your real auth/permission functions; fall back to permissive no-ops
try:
    from ....core.auth import get_current_user  # type: ignore
except Exception:
    def get_current_user():
        class _U:  # minimal shape
            id = None
            role = "superadmin"
        return _U()

try:
    from ....core.permissions import can_view  # type: ignore
except Exception:
    def can_view(_user_id, _module, _submodule=None, _tab=None) -> bool:
        return True

def _gate_subtabs(root: QWidget, module_name: str, submodule_name: str | None, submodules: List[str]) -> None:
    """Hide tabs that current user cannot view. Safe no-op on failure."""
    try:
        u = get_current_user()
        if not u or getattr(u, "role", "") == "superadmin":
            return
        allowed = {
            s
            for s in submodules
            if can_view(getattr(u, "id", None), module_name, submodule_name, s)
        }
        for tw in root.findChildren(QTabWidget):
            titles = [tw.tabText(i) for i in range(tw.count())]
            if not any(t in submodules for t in titles):
                continue
            for i in reversed(range(tw.count())):
                if tw.tabText(i) not in allowed:
                    tw.removeTab(i)
    except Exception:
        # never block UI due to ACL errors
        return

def _select_tab(root: QWidget, name: str) -> None:
    """Focus the first QTabWidget tab whose title matches name."""
    try:
        for tw in root.findChildren(QTabWidget):
            for i in range(tw.count()):
                if tw.tabText(i) == name:
                    tw.setCurrentIndex(i)
                    return
    except Exception:
        return

# =================== utils ===================

def _safe_date(obj, *field_names: str) -> Optional[date]:
    for fn in field_names:
        try:
            v = getattr(obj, fn)
            if isinstance(v, date):
                return v
            if isinstance(v, (str, bytes)):
                s = v.decode() if isinstance(v, bytes) else v
                if s:
                    return date.fromisoformat(s)
        except Exception:
            pass
    return None

def _today() -> date:
    return date.today()

def _jdict(x) -> dict:
    if isinstance(x, dict):
        return x
    if isinstance(x, (str, bytes)):
        try:
            s = x.decode() if isinstance(x, bytes) else x
            v = json.loads(s)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}

def _as_bool(x) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, (str, bytes)):
        s = x.decode() if isinstance(x, bytes) else x
        s = s.strip().lower()
        return s in {"1", "true", "t", "yes", "y"}
    return False

def _current_user() -> str:
    """Replace with your actual auth/user provider later."""
    try:
        u = get_current_user()
        # prefer username if present, else id, else placeholder
        return getattr(u, "username", None) or str(getattr(u, "id", "") or "user")
    except Exception:
        return "user"

# ---- sqlite helpers ----
def _has_column(raw_conn, table: str, column: str) -> bool:
    try:
        cur = raw_conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        for row in cur.fetchall():
            if len(row) >= 2 and str(row[1]) == column:
                return True
    except Exception:
        pass
    return False

# ---------------- service-year helpers ----------------

def _months_between(d0: date, d1: date) -> Tuple[int, int]:
    if d1 <= d0:
        return 0, 0
    months = (d1.year - d0.year) * 12 + (d1.month - d0.month)
    if d1.day < d0.day:
        months -= 1
    years = months // 12
    rem = months % 12
    return years, rem

def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + years)

def _service_year_period(join_dt: date, k: int) -> Tuple[date, date]:
    start = _add_years(join_dt, k - 1)
    end = _add_years(join_dt, k) - timedelta(days=1)
    return start, end

# ---------------- entitlement sources/policy ----------------

def _eol_map_for_emp(session, emp: Employee, leave_type: str) -> Dict[int, float]:
    eol_map: Dict[int, float] = {}

    rows = (
        session.query(LeaveEntitlement.year_of_service, LeaveEntitlement.days)
        .filter(LeaveEntitlement.employee_id == emp.id,
                LeaveEntitlement.leave_type == leave_type)
        .all()
    )
    for yos, days in rows:
        try:
            eol_map[int(yos)] = float(days or 0.0)
        except Exception:
            pass
    if eol_map:
        return eol_map

    ld = (
        session.query(LeaveDefault)
        .filter(LeaveDefault.account_id == tenant_id(),
                LeaveDefault.leave_type == leave_type)
        .first()
    )
    if ld:
        tj = _jdict(getattr(ld, "table_json", {}))
        years_blob = tj.get("years", {}) or {}
        if isinstance(years_blob, dict):
            for k, v in years_blob.items():
                try:
                    eol_map[int(k)] = float(v)
                except Exception:
                    pass
    return eol_map

def _policy_for_leave_type(session, leave_type: str) -> Dict:
    pol = {"prorated": False, "carry_policy": "bring",
           "carry_limit_enabled": False, "carry_limit": 0.0}
    ld = (
        session.query(LeaveDefault)
        .filter(LeaveDefault.account_id == tenant_id(),
                LeaveDefault.leave_type == leave_type)
        .first()
    )
    if ld:
        pol["prorated"] = _as_bool(getattr(ld, "prorated", False))
        tj = _jdict(getattr(ld, "table_json", {}))
        meta = _jdict(tj.get("_meta", {}))
        cp = str(meta.get("carry_policy", pol["carry_policy"]))
        pol["carry_policy"] = cp if cp in {"bring", "reset"} else pol["carry_policy"]
        pol["carry_limit_enabled"] = _as_bool(meta.get("carry_limit_enabled", pol["carry_limit_enabled"]))
        try:
            pol["carry_limit"] = float(meta.get("carry_limit", pol["carry_limit"]))
        except Exception:
            pass
    return pol

def _eol_amount(eol_map: Dict[int, float], k: int) -> float:
    if not eol_map:
        return 0.0
    if k in eol_map:
        return float(eol_map[k])
    return float(eol_map[max(eol_map.keys())])

# ---------------- work schedule / holidays ----------------

def _weekday_field(ws_row: WorkScheduleDay) -> Optional[int]:
    for name in ("weekday", "day_of_week", "dow", "dayindex"):
        try:
            v = getattr(ws_row, name)
            if isinstance(v, int):
                return v
        except Exception:
            pass
    return None

def _employee_weekday_weight(session, emp_id: int, d: date) -> float:
    rows = session.query(WorkScheduleDay).filter(WorkScheduleDay.employee_id == emp_id).all()
    if not rows:
        return 1.0 if d.weekday() < 5 else 0.0
    mp: Dict[int, float] = {}
    for r in rows:
        idx = _weekday_field(r)
        if idx is None:
            continue
        try:
            if hasattr(r, "working") and not bool(getattr(r, "working")):
                mp[idx] = 0.0
                continue
        except Exception:
            pass
        day_type = str(getattr(r, "day_type", "Full") or "Full").strip().lower()
        if day_type in ("full", "work", "working", "full day", "fullday"):
            mp[idx] = 1.0
        elif day_type in ("half", "half day", "halfday"):
            mp[idx] = 0.5
        else:
            mp[idx] = 1.0
    return mp.get(d.weekday(), 0.0)

def _holiday_weight_for_date(h: Holiday) -> float:
    try:
        return 0.5 if bool(getattr(h, "is_half_day")) else 1.0
    except Exception:
        return 1.0

def _holiday_dates_weight(session, emp: Employee, d0: date, d1: date) -> Dict[date, float]:
    group_val = getattr(emp, "holiday_group", None)
    q = session.query(Holiday).filter(Holiday.account_id == tenant_id())
    if group_val:
        q = q.filter(Holiday.group_code == group_val)
    try:
        q = q.filter(Holiday.date >= d0, Holiday.date <= d1)
    except Exception:
        pass
    rows = q.all()

    out: Dict[date, float] = {}
    for h in rows:
        hd = _safe_date(h, "date", "holiday_date", "dt")
        if hd and d0 <= hd <= d1:
            out[hd] = _holiday_weight_for_date(h)
    return out

# ---------------- used-days ----------------

def _compute_used_days(session, emp_id: int, s: date, s_half: str, e: date, e_half: str) -> float:
    if e < s:
        return 0.0
    emp = session.get(Employee, emp_id)
    if not emp:
        return 0.0
    holidays = _holiday_dates_weight(session, emp, s, e)

    def day_portion(d: date) -> float:
        base = _employee_weekday_weight(session, emp_id, d)
        if base <= 0.0:
            return 0.0
        h_w = holidays.get(d, 0.0)
        return max(0.0, base - h_w)

    total = 0.0
    cur = s
    one = timedelta(days=1)
    while cur <= e:
        eff = day_portion(cur)
        if eff > 0.0:
            if s == e:
                if s_half == "AM" and e_half == "AM":
                    total += min(eff, 0.5)
                elif s_half == "PM" and e_half == "PM":
                    total += min(eff, 0.5)
                else:
                    total += eff
            elif cur == s:
                total += min(eff, 0.5) if s_half == "PM" else eff
            elif cur == e:
                total += min(eff, 0.5) if e_half == "AM" else eff
            else:
                total += eff
        cur += one
    return round(float(total), 3)

def _used_days_in_window(session, emp_id: int, leave_type: str, w0: date, w1: date) -> float:
    from sqlite3 import OperationalError
    acc = tenant_id()
    q = """
        SELECT start_date, start_half, end_date, end_half
        FROM leave_applications
        WHERE account_id = ?
          AND employee_id = ?
          AND leave_type = ?
          AND status = 'Approved'
          AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
        """
    try:
        raw_conn = session.connection().connection
        cur = raw_conn.cursor()
        cur.execute(q, (acc, emp_id, leave_type, w0.isoformat(), w1.isoformat()))
        rows = cur.fetchall()
    except OperationalError:
        return 0.0
    except Exception:
        return 0.0

    total = 0.0
    for sd_s, sh, ed_s, eh in rows:
        try:
            s_all = date.fromisoformat(sd_s)
            e_all = date.fromisoformat(ed_s)
        except Exception:
            continue
        s = max(s_all, w0)
        e = min(e_all, w1)
        if s > e:
            continue
        s_half = sh if s_all >= w0 else "AM"
        e_half = eh if e_all <= w1 else "PM"
        total += _compute_used_days(session, emp_id, s, s_half, e, e_half)
    return float(total)

def _adjustments_sum_for_year(session, emp_id: int, leave_type: str, year: int) -> float:
    from sqlite3 import OperationalError
    acc = tenant_id()
    q = """
        SELECT COALESCE(SUM(days), 0.0)
        FROM leave_adjustments
        WHERE account_id = ? AND employee_id = ? AND leave_type = ? AND year = ?
        """
    try:
        raw_conn = session.connection().connection
        cur = raw_conn.cursor()
        cur.execute(q, (acc, emp_id, leave_type, int(year)))
        row = cur.fetchone()
        return float(row[0] or 0.0)
    except OperationalError:
        return 0.0
    except Exception:
        return 0.0

def _used_days_total_year(session, emp_id: int, leave_type: str, year: int, include_adjustments: bool = True) -> float:
    """Approved leave used within the calendar year.
    If include_adjustments is True, subtract adjustments (so +2 entitlement lowers 'Used' by 2)."""
    y0 = date(year, 1, 1)
    y1 = date(year, 12, 31)
    used = _used_days_in_window(session, emp_id, leave_type, y0, y1)
    if include_adjustments:
        adj = _adjustments_sum_for_year(session, emp_id, leave_type, year)
        used = used - adj
    return round(float(used), 3)

# ---------------- entitlement engine ----------------

def _entitlement_asof(session, emp: Employee, leave_type: str, as_of: date) -> float:
    jd = _safe_date(emp, "join_date", "date_joined", "start_date")
    if not jd or as_of < jd:
        return 0.0

    eol_map = _eol_map_for_emp(session, emp, leave_type)
    pol = _policy_for_leave_type(session, leave_type)

    full_years, months_in_cur = _months_between(jd, as_of)
    cur_idx = max(1, full_years + 1)

    def cur_ent(prorated: bool) -> float:
        base = _eol_amount(eol_map, cur_idx)
        return (months_in_cur / 12.0) * base if prorated else base

    if pol["carry_policy"] == "reset":
        return round(cur_ent(pol["prorated"]), 2)

    if not pol["carry_limit_enabled"]:
        total = 0.0
        for k in range(1, full_years + 1):
            total += _eol_amount(eol_map, k)
        total += cur_ent(pol["prorated"])
        return round(total, 2)

    L = max(0.0, float(pol["carry_limit"] or 0.0))
    carry_in = 0.0
    for k in range(1, full_years + 1):
        A_k = _eol_amount(eol_map, k)
        sy_start, sy_end = _service_year_period(jd, k)
        used_k = _used_days_in_window(session, emp.id, leave_type, sy_start, sy_end)
        opening = A_k + carry_in
        leftover = max(0.0, opening - used_k)
        carry_in = leftover if L <= 0 else min(L, leftover)

    A_cur = _eol_amount(eol_map, cur_idx)
    cur_part = (months_in_cur / 12.0) * A_cur if pol["prorated"] else A_cur
    total = carry_in + cur_part
    return round(total, 2)

# ---------------- DDL bootstrap ----------------

def _ensure_leave_tables(session) -> None:
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS leave_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            employee_id INTEGER NOT NULL,
            leave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            start_half TEXT NOT NULL CHECK (start_half IN ('AM','PM')),
            end_date   TEXT NOT NULL,
            end_half   TEXT NOT NULL CHECK (end_half IN ('AM','PM')),
            used_days  REAL NOT NULL,
            status     TEXT NOT NULL DEFAULT 'Pending',
            remarks    TEXT,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_la_emp ON leave_applications(employee_id);",
        "CREATE INDEX IF NOT EXISTS idx_la_type ON leave_applications(leave_type);",
        "CREATE INDEX IF NOT EXISTS idx_la_start ON leave_applications(start_date);",
        "CREATE INDEX IF NOT EXISTS idx_la_status ON leave_applications(status);",
        """
        CREATE TABLE IF NOT EXISTS leave_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            employee_id INTEGER NOT NULL,
            leave_type TEXT NOT NULL,
            year INTEGER NOT NULL,
            date TEXT NOT NULL,
            days REAL NOT NULL,
            remarks TEXT,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_ladj_emp ON leave_adjustments(employee_id);",
        "CREATE INDEX IF NOT EXISTS idx_ladj_year ON leave_adjustments(year);",
    ]
    try:
        raw_conn = session.connection().connection
        cur = raw_conn.cursor()
        for stmt in ddl:
            cur.execute(stmt)
        # Add audit columns if missing
        try:
            cur.execute("ALTER TABLE leave_applications ADD COLUMN action_user TEXT")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE leave_applications ADD COLUMN created_by TEXT")
        except Exception:
            pass
        raw_conn.commit()
    except Exception:
        pass

# ---------------- UI ----------------

@dataclass
class _AppState:
    emp_id: Optional[int] = None
    leave_type: str = "Annual"

class LeaveModuleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        _ensure_leave_tables(self.session)
        self.state = _AppState()

        self.tabs = QTabWidget()
        self._summary_tab = QWidget()
        self._application_tab = QWidget()
        self._details_tab = QWidget()
        self._adjustments_tab = QWidget()
        self._calendar_tab = QWidget()
        self._user_history_tab = QWidget()

        self._init_summary_tab()
        self._init_application_tab()
        self._init_details_tab()
        self._init_adjustments_tab()
        self._init_calendar_tab()
        self._init_user_history_tab()

        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)

        self.tabs.addTab(self._summary_tab, "Summary")
        self.tabs.addTab(self._application_tab, "Application")
        self.tabs.addTab(self._details_tab, "All Details")
        self.tabs.addTab(self._adjustments_tab, "Adjustments")
        self.tabs.addTab(self._calendar_tab, "Calendar")
        self.tabs.addTab(self._user_history_tab, "User Application History")

        # Gate sub-tabs based on permissions. Safe no-op if permissions not wired.
        _gate_subtabs(self, ROOT_MODULE_NAME, MODULE_NAME, SUBMODULES)

        employee_events.employees_changed.connect(self._handle_employees_changed)

    MODULE_KEY = "leave_management"

    def filter_tabs_by_access(self, allowed_keys: list[str] | set[str]):
        allowed = set(allowed_keys or [])
        if not allowed:
            return
        label_by_key = {
            "summary": "Summary",
            "all_details": "All Details",
            "calendar": "Calendar",
        }
        allowed_labels = {label_by_key[k] for k in allowed if k in label_by_key}
        for i in range(self.tabs.count() - 1, -1, -1):
            if self.tabs.tabText(i) not in allowed_labels:
                self.tabs.removeTab(i)


    # ----- Summary -----
    def _init_summary_tab(self):
        w = self._summary_tab
        layout = QVBoxLayout(w)

        top = QHBoxLayout(); layout.addLayout(top)

        top.addWidget(QLabel("Year:"))
        self.cmb_year = QComboBox()
        cur_year = _today().year
        years = [str(y) for y in range(cur_year - 3, cur_year + 3)]
        self.cmb_year.addItems(years)
        self.cmb_year.setCurrentText(str(cur_year))
        top.addWidget(self.cmb_year)

        top.addWidget(QLabel("Leave type:"))
        self.cmb_leave_type_sum = QComboBox()
        self._populate_leave_types(self.cmb_leave_type_sum)
        top.addWidget(self.cmb_leave_type_sum)

        self.btn_refresh_sum = QPushButton("Refresh")
        self.btn_refresh_sum.clicked.connect(self._refresh_summary)
        top.addWidget(self.btn_refresh_sum)
        top.addStretch(1)

        # Headers: Employee Code, Employee, Entitlement, Used, Balance
        self.tbl_summary = QTableWidget(0, 5)
        self.tbl_summary.setHorizontalHeaderLabels(["Employee Code", "Employee", "Entitlement", "Used", "Balance"])
        hdr = self.tbl_summary.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(False)
        hdr.setDefaultAlignment(Qt.AlignCenter)
        self.tbl_summary.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_summary.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tbl_summary)

        self.cmb_year.currentTextChanged.connect(self._refresh_summary)
        self.cmb_leave_type_sum.currentTextChanged.connect(self._refresh_summary)

        self._refresh_summary()

    def _refresh_summary(self):
        session = self.session
        try:
            session.expire_all()
        except Exception:
            pass
        y = int(self.cmb_year.currentText())
        lt = self.cmb_leave_type_sum.currentText() or "Annual"

        rows = (
            session.query(Employee)
            .filter(Employee.account_id == tenant_id())
            .order_by(Employee.id.asc())
            .all()
        )
        self.tbl_summary.setRowCount(0)

        for emp in rows:
            asof = date(y, 12, 31)
            ent = _entitlement_asof(session, emp, lt, asof)
            used = _used_days_total_year(session, emp.id, lt, y, include_adjustments=True)
            bal = round(ent - used, 2)

            code = (getattr(emp, "code", None) or "").strip() or str(emp.id)
            name_txt = str(getattr(emp, "full_name", getattr(emp, "name", emp.id)))

            r = self.tbl_summary.rowCount()
            self.tbl_summary.insertRow(r)

            vals = [code, name_txt, f"{ent:.2f}", f"{used:.2f}", f"{bal:.2f}"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                self.tbl_summary.setItem(r, c, it)

        self.tbl_summary.resizeColumnsToContents()

    def _handle_employees_changed(self):
        try:
            self.session.expire_all()
        except Exception:
            pass
        self._populate_leave_types(self.cmb_leave_type_sum)
        self._refresh_summary()

    def _populate_leave_types(self, combo: QComboBox):
        s = self.session
        types = set(
            t for (t,) in s.query(LeaveDefault.leave_type)
                           .filter(LeaveDefault.account_id == tenant_id())
                           .distinct().all()
        )
        try:
            types |= set(t for (t,) in s.query(LeaveEntitlement.leave_type).distinct().all())
        except Exception:
            pass
        if not types:
            types = {"Annual", "Sick"}
        combo.clear()
        combo.addItems(sorted(types))

    # ----- Application -----
    def _init_application_tab(self):
        w = self._application_tab
        form = QFormLayout(w)

        self.cmb_emp = QComboBox()
        self._populate_employees(self.cmb_emp)
        form.addRow("Employee", self.cmb_emp)

        self.cmb_leave_type = QComboBox()
        self._populate_leave_types(self.cmb_leave_type)
        form.addRow("Leave type", self.cmb_leave_type)

        self.de_start = QDateEdit(); self.de_start.setCalendarPopup(True); self.de_start.setDate(QDate.currentDate())
        self.cmb_start_half = QComboBox(); self.cmb_start_half.addItems(["AM", "PM"])
        hl1 = QHBoxLayout(); hl1.addWidget(self.de_start); hl1.addWidget(self.cmb_start_half)
        form.addRow("Start", self._wrap(hl1))

        self.de_end = QDateEdit(); self.de_end.setCalendarPopup(True); self.de_end.setDate(QDate.currentDate())
        self.cmb_end_half = QComboBox(); self.cmb_end_half.addItems(["AM", "PM"])
        hl2 = QHBoxLayout(); hl2.addWidget(self.de_end); hl2.addWidget(self.cmb_end_half)
        form.addRow("End", self._wrap(hl2))

        self.txt_remarks = QLineEdit()
        form.addRow("Remarks", self.txt_remarks)

        self.lbl_available = QLabel("0.00 day(s)")
        form.addRow("Available", self.lbl_available)

        self.ed_used = QLineEdit(); self.ed_used.setReadOnly(True)
        form.addRow("Total Used", self.ed_used)

        self.btn_calc = QPushButton("Recalculate")
        self.btn_submit = QPushButton("Submit")
        hl3 = QHBoxLayout(); hl3.addWidget(self.btn_calc); hl3.addWidget(self.btn_submit); hl3.addStretch(1)
        form.addRow(self._wrap(hl3))

        # auto recalc + available live
        self.cmb_emp.currentIndexChanged.connect(self._recalculate_used)
        self.cmb_leave_type.currentIndexChanged.connect(self._recalculate_used)
        self.de_start.dateChanged.connect(self._recalculate_used)
        self.de_end.dateChanged.connect(self._recalculate_used)
        self.cmb_start_half.currentIndexChanged.connect(self._recalculate_used)
        self.cmb_end_half.currentIndexChanged.connect(self._recalculate_used)
        self.btn_calc.clicked.connect(self._recalculate_used)
        self.btn_submit.clicked.connect(self._submit_application)

        self.cmb_emp.currentIndexChanged.connect(self._update_available)
        self.cmb_leave_type.currentIndexChanged.connect(self._update_available)
        self.de_start.dateChanged.connect(self._update_available)

        self._recalculate_used()
        self._update_available()

    def _wrap(self, layout: QHBoxLayout):
        host = QWidget(); host.setLayout(layout); return host

    def _populate_employees(self, combo: QComboBox):
        combo.clear()
        rows = (
            self.session.query(Employee)
            .filter(Employee.account_id == tenant_id())
            .order_by(Employee.id.asc())
            .all()
        )
        for emp in rows:
            combo.addItem(str(getattr(emp, "full_name", getattr(emp, "name", emp.id))), emp.id)

    def _update_available(self):
        try:
            emp_id = self.cmb_emp.currentData()
            if emp_id is None:
                self.lbl_available.setText("0.00 day(s)")
                return
            year = self.de_start.date().toPython().year
            lt = self.cmb_leave_type.currentText() or "Annual"
            emp = self.session.get(Employee, int(emp_id))
            if not emp:
                self.lbl_available.setText("0.00 day(s)")
                return
            ent = _entitlement_asof(self.session, emp, lt, date(year, 12, 31))
            used = _used_days_total_year(self.session, int(emp_id), lt, year, True)
            avail = round(ent - used, 2)
            self.lbl_available.setText(f"{avail:.2f} day(s) in {year}")
        except Exception:
            self.lbl_available.setText("0.00 day(s)")

    def _recalculate_used(self):
        try:
            emp_id = self.cmb_emp.currentData()
            if emp_id is None:
                self.ed_used.setText("0")
                return
            s = self.de_start.date().toPython()
            e = self.de_end.date().toPython()
            sh = self.cmb_start_half.currentText() or "AM"
            eh = self.cmb_end_half.currentText() or "PM"
            used = _compute_used_days(self.session, int(emp_id), s, sh, e, eh)
            self.ed_used.setText(f"{used:.2f}")
        except Exception:
            self.ed_used.setText("0")

    def _submit_application(self):
        session = self.session
        try:
            emp_id = self.cmb_emp.currentData()
            if emp_id is None:
                QMessageBox.warning(self, "Missing", "Select employee.")
                return
            leave_type = self.cmb_leave_type.currentText() or "Annual"
            s = self.de_start.date().toPython()
            e = self.de_end.date().toPython()
            if e < s:
                QMessageBox.warning(self, "Invalid", "End date before start date.")
                return
            sh = self.cmb_start_half.currentText() or "AM"
            eh = self.cmb_end_half.currentText() or "PM"
            used = _compute_used_days(session, int(emp_id), s, sh, e, eh)

            _ensure_leave_tables(session)
            acc = tenant_id()
            raw = session.connection().connection
            cur = raw.cursor()

            # Choose column set based on availability
            has_created = _has_column(raw, "leave_applications", "created_by")
            has_action = _has_column(raw, "leave_applications", "action_user")

            if has_created or has_action:
                cols = ["account_id","employee_id","leave_type","start_date","start_half",
                        "end_date","end_half","used_days","status","remarks"]
                vals = [acc, int(emp_id), leave_type, s.isoformat(), sh, e.isoformat(), eh, float(used), "Pending", self.txt_remarks.text().strip()]
                if has_created:
                    cols.append("created_by");  vals.append(_current_user())
                sql = f"INSERT INTO leave_applications({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})"
                cur.execute(sql, tuple(vals))
            else:
                cur.execute(
                    """
                    INSERT INTO leave_applications(account_id, employee_id, leave_type, start_date, start_half, end_date, end_half, used_days, status, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
                    """,
                    (acc, int(emp_id), leave_type, s.isoformat(), sh, e.isoformat(), eh, float(used), self.txt_remarks.text().strip())
                )

            raw.commit()
            QMessageBox.information(self, "Saved", "Leave application recorded as Pending.")
            self._refresh_details()
            self._refresh_user_history()
            self._refresh_summary()
            self._refresh_calendar()
            self._recalculate_used()
            self._update_available()
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to save.\n{ex}")

    # ----- All Details -----
    def _init_details_tab(self):
        w = self._details_tab
        layout = QVBoxLayout(w)

        top = QHBoxLayout()
        layout.addLayout(top)
        top.addWidget(QLabel("Year:"))
        self.cmb_year_d = QComboBox()
        cur_year = _today().year
        self.cmb_year_d.addItems([str(cur_year - 1), str(cur_year), str(cur_year + 1)])
        self.cmb_year_d.setCurrentText(str(cur_year))
        top.addWidget(self.cmb_year_d)

        top.addWidget(QLabel("Leave type:"))
        self.cmb_leave_type_d = QComboBox()
        self._populate_leave_types(self.cmb_leave_type_d)
        top.addWidget(self.cmb_leave_type_d)

        self.btn_refresh_d = QPushButton("Refresh")
        self.btn_refresh_d.clicked.connect(self._refresh_details)
        top.addWidget(self.btn_refresh_d)

        # right-side action buttons
        top.addStretch(1)
        self.btn_approve = QPushButton("Approve")
        self.btn_reject = QPushButton("Reject")
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_approve.clicked.connect(self._approve_selected)
        self.btn_reject.clicked.connect(self._reject_selected)
        self.btn_delete.clicked.connect(self._delete_selected_details)
        top.addWidget(self.btn_approve)
        top.addWidget(self.btn_reject)
        top.addWidget(self.btn_delete)

        # Columns: (hidden ID) | Employee Code | Employee | Type | Start | Start Half | End | End Half | Used | Status | User
        self.tbl_details = QTableWidget(0, 11)
        self.tbl_details.setHorizontalHeaderLabels([
            "ID", "Employee Code", "Employee", "Type", "Start", "Start Half", "End", "End Half", "Used", "Status", "User"
        ])
        self.tbl_details.setColumnHidden(0, True)
        hdr = self.tbl_details.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setDefaultAlignment(Qt.AlignCenter)
        self.tbl_details.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_details.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tbl_details)

        self.cmb_year_d.currentIndexChanged.connect(self._refresh_details)
        self.cmb_leave_type_d.currentIndexChanged.connect(self._refresh_details)

        self._refresh_details()

    def _refresh_details(self):
        session = self.session
        y = int(self.cmb_year_d.currentText())
        lt = self.cmb_leave_type_d.currentText() or "Annual"
        y0, y1 = date(y, 1, 1), date(y, 12, 31)

        # Build id -> name/code maps once
        emp_name_map: Dict[int, str] = {}
        emp_code_map: Dict[int, str] = {}
        for e in session.query(Employee).filter(Employee.account_id == tenant_id()).all():
            emp_name_map[e.id] = (e.full_name or f"Emp {e.id}")
            emp_code_map[e.id] = (getattr(e, "code", None) or "").strip() or str(e.id)

        self.tbl_details.setRowCount(0)
        try:
            acc = tenant_id()
            raw = session.connection().connection
            cur = raw.cursor()
            has_action = _has_column(raw, "leave_applications", "action_user")

            cur.execute(
                f"""
                SELECT id, employee_id, leave_type, start_date, start_half, end_date, end_half, used_days, status
                       {", action_user" if has_action else ""}
                FROM leave_applications
                WHERE account_id = ? AND leave_type = ?
                  AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
                ORDER BY date(start_date) ASC
                """,
                (acc, lt, y0.isoformat(), y1.isoformat())
            )
            for row in cur.fetchall():
                if has_action:
                    _id, emp_id, leave_type, sd, sh, ed, eh, used, status, action_user = row
                else:
                    _id, emp_id, leave_type, sd, sh, ed, eh, used, status = row
                    action_user = ""
                r = self.tbl_details.rowCount()
                self.tbl_details.insertRow(r)
                name = emp_name_map.get(int(emp_id), f"Emp {emp_id}")
                code = emp_code_map.get(int(emp_id), str(emp_id))
                vals = [
                    str(_id), code, name, str(leave_type),
                    str(sd), str(sh), str(ed), str(eh),
                    f"{float(used):.2f}" if used is not None else "0.00",
                    str(status or ""), str(action_user or "")
                ]
                for c, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setTextAlignment(Qt.AlignCenter)
                    self.tbl_details.setItem(r, c, it)
        except Exception:
            pass

    def _selected_ids_from(self, table: QTableWidget) -> List[int]:
        ids: List[int] = []
        for idx in table.selectionModel().selectedRows():
            try:
                row = idx.row()
                it = table.item(row, 0)  # hidden ID col
                if it:
                    ids.append(int(it.text()))
            except Exception:
                pass
        return ids

    def _approve_selected(self):
        try:
            raw = self.session.connection().connection
            cur = raw.cursor()
            ids = self._selected_ids_from(self.tbl_details)
            if not ids:
                QMessageBox.information(self, "No selection", "Select one or more rows to approve.")
                return
            has_action = _has_column(raw, "leave_applications", "action_user")
            for _id in ids:
                if has_action:
                    cur.execute("UPDATE leave_applications SET status='Approved', action_user=? WHERE id=?", (_current_user(), _id))
                else:
                    cur.execute("UPDATE leave_applications SET status='Approved' WHERE id=?", (_id,))
            raw.commit()
            self._refresh_details()
            self._refresh_user_history()
            self._refresh_summary()
            self._refresh_calendar()
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Approve failed.\n{ex}")

    def _reject_selected(self):
        try:
            raw = self.session.connection().connection
            cur = raw.cursor()
            ids = self._selected_ids_from(self.tbl_details)
            if not ids:
                QMessageBox.information(self, "No selection", "Select one or more rows to reject.")
                return
            has_action = _has_column(raw, "leave_applications", "action_user")
            for _id in ids:
                if has_action:
                    cur.execute("UPDATE leave_applications SET status='Rejected', action_user=? WHERE id=?", (_current_user(), _id))
                else:
                    cur.execute("UPDATE leave_applications SET status='Rejected' WHERE id=?", (_id,))
            raw.commit()
            self._refresh_details()
            self._refresh_user_history()
            self._refresh_summary()
            self._refresh_calendar()
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Reject failed.\n{ex}")

    def _delete_selected_details(self):
        try:
            raw = self.session.connection().connection
            cur = raw.cursor()
            ids = self._selected_ids_from(self.tbl_details)
            if not ids:
                QMessageBox.information(self, "No selection", "Select one or more rows to delete.")
                return
            for _id in ids:
                cur.execute("DELETE FROM leave_applications WHERE id=?", (_id,))
            raw.commit()
            self._refresh_details()
            self._refresh_user_history()
            self._refresh_summary()
            self._refresh_calendar()
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Delete failed.\n{ex}")

    # ----- Adjustments -----
    def _init_adjustments_tab(self):
        w = self._adjustments_tab
        root = QVBoxLayout(w)

        # Form row
        form = QFormLayout()
        self.cmb_emp_adj = QComboBox(); self._populate_employees(self.cmb_emp_adj)
        form.addRow("Employee", self.cmb_emp_adj)

        self.cmb_leave_type_adj = QComboBox(); self._populate_leave_types(self.cmb_leave_type_adj)
        form.addRow("Leave type", self.cmb_leave_type_adj)

        self.cmb_year_adj = QComboBox()
        cur_year = _today().year
        self.cmb_year_adj.addItems([str(cur_year - 1), str(cur_year), str(cur_year + 1)])
        self.cmb_year_adj.setCurrentText(str(cur_year))
        form.addRow("Year", self.cmb_year_adj)

        self.de_adj = QDateEdit(); self.de_adj.setCalendarPopup(True); self.de_adj.setDate(QDate.currentDate())
        form.addRow("Date", self.de_adj)

        self.ed_days_adj = QLineEdit(); self.ed_days_adj.setPlaceholderText("e.g. +2 or -1.5")
        form.addRow("Days", self.ed_days_adj)

        self.ed_remarks_adj = QLineEdit()
        form.addRow("Remarks", self.ed_remarks_adj)

        btn_row = QHBoxLayout()
        self.btn_add_adj = QPushButton("Add Adjustment")
        self.btn_add_adj.clicked.connect(self._save_adjustment)
        self.btn_clear_adj = QPushButton("Clear")
        self.btn_clear_adj.clicked.connect(self._clear_adj_form)
        self.btn_edit_adj = QPushButton("Edit Selected")
        self.btn_edit_adj.clicked.connect(self._edit_adjustment)
        self.btn_del_adj = QPushButton("Delete Selected")
        self.btn_del_adj.clicked.connect(self._delete_adjustment)
        btn_row.addWidget(self.btn_add_adj)
        btn_row.addWidget(self.btn_clear_adj)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_edit_adj)
        btn_row.addWidget(self.btn_del_adj)

        root.addLayout(form)
        root.addLayout(btn_row)

        # Table: ID(hidden), Emp Code, Employee, Type, Year, Date, Days, Remarks, Created
        self.tbl_adj = QTableWidget(0, 9)
        self.tbl_adj.setHorizontalHeaderLabels([
            "ID", "Employee Code", "Employee", "Type", "Year", "Date", "Days", "Remarks", "Created"
        ])
        self.tbl_adj.setColumnHidden(0, True)
        hdr = self.tbl_adj.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(False)
        hdr.setDefaultAlignment(Qt.AlignCenter)
        self.tbl_adj.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_adj.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self.tbl_adj, 1)

        # Hooks to refresh table when filters change
        self.cmb_emp_adj.currentIndexChanged.connect(self._refresh_adjustments_table)
        self.cmb_leave_type_adj.currentIndexChanged.connect(self._refresh_adjustments_table)
        self.cmb_year_adj.currentIndexChanged.connect(self._refresh_adjustments_table)
        self.tbl_adj.cellDoubleClicked.connect(lambda _r, _c: self._edit_adjustment())

        # initial load
        self._refresh_adjustments_table()

    def _clear_adj_form(self):
        self.de_adj.setDate(QDate.currentDate())
        self.ed_days_adj.clear()
        self.ed_remarks_adj.clear()

    def _save_adjustment(self):
        session = self.session
        try:
            emp_id = self.cmb_emp_adj.currentData()
            if emp_id is None:
                QMessageBox.warning(self, "Missing", "Select employee."); return
            lt = self.cmb_leave_type_adj.currentText() or "Annual"
            y = int(self.cmb_year_adj.currentText())
            d = self.de_adj.date().toPython()
            try:
                days = float((self.ed_days_adj.text() or "0").strip())
            except Exception:
                QMessageBox.warning(self, "Invalid", "Days must be a number."); return
            remarks = self.ed_remarks_adj.text().strip()

            _ensure_leave_tables(session)
            acc = tenant_id()
            raw = session.connection().connection
            cur = raw.cursor()
            cur.execute(
                """
                INSERT INTO leave_adjustments(account_id, employee_id, leave_type, year, date, days, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (acc, int(emp_id), lt, y, d.isoformat(), days, remarks)
            )
            raw.commit()
            QMessageBox.information(self, "Saved", "Adjustment recorded.")
            self._refresh_adjustments_table()
            self._refresh_summary()
            self._refresh_calendar()
            self._refresh_details()
            self._refresh_user_history()
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to save.\n{ex}")

    def _refresh_adjustments_table(self):
        session = self.session
        emp_id = self.cmb_emp_adj.currentData()
        lt = self.cmb_leave_type_adj.currentText() or ""
        try:
            y = int(self.cmb_year_adj.currentText())
        except Exception:
            y = _today().year

        # maps for code and name
        emp_name_map: Dict[int, str] = {}
        emp_code_map: Dict[int, str] = {}
        for e in session.query(Employee).filter(Employee.account_id == tenant_id()).all():
            emp_name_map[e.id] = (e.full_name or f"Emp {e.id}")
            emp_code_map[e.id] = (getattr(e, "code", None) or "").strip() or str(e.id)

        self.tbl_adj.setRowCount(0)
        try:
            acc = tenant_id()
            raw = session.connection().connection
            cur = raw.cursor()

            base = "SELECT id, employee_id, leave_type, year, date, days, remarks, created_at FROM leave_adjustments WHERE account_id = ?"
            args: List[object] = [acc]
            if emp_id is not None:
                base += " AND employee_id = ?"; args.append(int(emp_id))
            if lt:
                base += " AND leave_type = ?"; args.append(lt)
            base += " AND year = ?"; args.append(int(y))
            base += " ORDER BY date(date) ASC, id ASC"

            cur.execute(base, tuple(args))
            rows = cur.fetchall()

            for row in rows:
                _id, e_id, ltyp, yy, dt_s, days, rm, created = row
                name = emp_name_map.get(int(e_id), f"Emp {e_id}")
                code = emp_code_map.get(int(e_id), str(e_id))
                try:
                    dshow = date.fromisoformat(str(dt_s)).strftime("%d/%m/%Y")
                except Exception:
                    dshow = str(dt_s)
                vals = [
                    str(_id), code, name, str(ltyp), str(yy),
                    dshow, f"{float(days):.2f}", str(rm or ""), str(created or "")
                ]
                r = self.tbl_adj.rowCount()
                self.tbl_adj.insertRow(r)
                for c, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setTextAlignment(Qt.AlignCenter)
                    self.tbl_adj.setItem(r, c, it)
        except Exception:
            pass

    def _current_adj_id(self) -> Optional[int]:
        idxs = self.tbl_adj.selectionModel().selectedRows()
        if not idxs:
            return None
        r = idxs[0].row()
        it = self.tbl_adj.item(r, 0)
        try:
            return int(it.text()) if it else None
        except Exception:
            return None

    def _edit_adjustment(self):
        adj_id = self._current_adj_id()
        if adj_id is None:
            QMessageBox.information(self, "Edit", "Select a row to edit.")
            return

        # pull current values from table
        r = self.tbl_adj.currentRow()
        cur_emp_name = self.tbl_adj.item(r, 2).text() if self.tbl_adj.item(r, 2) else ""
        cur_type = self.tbl_adj.item(r, 3).text() if self.tbl_adj.item(r, 3) else ""
        cur_year = self.tbl_adj.item(r, 4).text() if self.tbl_adj.item(r, 4) else ""
        cur_date = self.tbl_adj.item(r, 5).text() if self.tbl_adj.item(r, 5) else ""
        cur_days = self.tbl_adj.item(r, 6).text() if self.tbl_adj.item(r, 6) else ""
        cur_rm = self.tbl_adj.item(r, 7).text() if self.tbl_adj.item(r, 7) else ""

        # dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Adjustment")
        fl = QFormLayout(dlg)

        lbl_emp = QLabel(cur_emp_name)
        lbl_type = QLabel(cur_type)
        lbl_year = QLabel(cur_year)
        fl.addRow("Employee", lbl_emp)
        fl.addRow("Leave type", lbl_type)
        fl.addRow("Year", lbl_year)

        de = QDateEdit(); de.setCalendarPopup(True)
        try:
            d = datetime.strptime(cur_date, "%d/%m/%Y").date()
            de.setDate(QDate(d.year, d.month, d.day))
        except Exception:
            de.setDate(QDate.currentDate())

        ed_days = QLineEdit(cur_days)
        ed_rm = QLineEdit(cur_rm)
        fl.addRow("Date", de)
        fl.addRow("Days", ed_days)
        fl.addRow("Remarks", ed_rm)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        fl.addRow(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.Accepted:
            return

        try:
            dq = de.date()
            d_iso = f"{dq.year():04d}-{dq.month():02d}-{dq.day():02d}"
            days_val = float((ed_days.text() or "0").strip())
        except Exception:
            QMessageBox.warning(self, "Edit", "Invalid inputs.")
            return

        raw = self.session.connection().connection
        cur = raw.cursor()
        try:
            cur.execute(
                "UPDATE leave_adjustments SET date=?, days=?, remarks=? WHERE id=? AND account_id=?",
                (d_iso, days_val, ed_rm.text().strip(), int(adj_id), tenant_id())
            )
            raw.commit()
        except Exception as ex:
            QMessageBox.warning(self, "Edit", f"Failed: {ex}")
            return

        self._refresh_adjustments_table()
        self._refresh_summary()
        self._refresh_calendar()
        self._refresh_details()
        self._refresh_user_history()

    def _delete_adjustment(self):
        adj_id = self._current_adj_id()
        if adj_id is None:
            QMessageBox.information(self, "Delete", "Select a row to delete.")
            return
        if QMessageBox.question(self, "Delete", "Delete selected adjustment?") != QMessageBox.Yes:
            return

        raw = self.session.connection().connection
        cur = raw.cursor()
        try:
            cur.execute("DELETE FROM leave_adjustments WHERE id=? AND account_id=?", (int(adj_id), tenant_id()))
            raw.commit()
        except Exception as ex:
            QMessageBox.warning(self, "Delete", f"Failed: {ex}")
            return

        self._refresh_adjustments_table()
        self._refresh_summary()
        self._refresh_calendar()
        self._refresh_details()
        self._refresh_user_history()

    # ----- Calendar -----
    def _init_calendar_tab(self):
        w = self._calendar_tab
        v = QVBoxLayout(w)

        top = QHBoxLayout()
        v.addLayout(top)

        top.addWidget(QLabel("Year:"))
        self.cmb_cal_year = QComboBox()
        cur_year = _today().year
        self.cmb_cal_year.addItems([str(y) for y in range(cur_year - 3, cur_year + 4)])
        self.cmb_cal_year.setCurrentText(str(cur_year))
        top.addWidget(self.cmb_cal_year)

        top.addWidget(QLabel("Month:"))
        self.cmb_cal_month = QComboBox()
        self.cmb_cal_month.addItems(
            ["01 Jan","02 Feb","03 Mar","04 Apr","05 May","06 Jun",
             "07 Jul","08 Aug","09 Sep","10 Oct","11 Nov","12 Dec"]
        )
        self.cmb_cal_month.setCurrentIndex(_today().month - 1)
        top.addWidget(self.cmb_cal_month)

        btn_today = QPushButton("Today")
        btn_today.clicked.connect(self._goto_today)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_calendar)
        top.addWidget(btn_today)
        top.addWidget(btn_refresh)
        top.addStretch(1)

        self.tbl_cal = QTableWidget(6, 7)
        self.tbl_cal.setHorizontalHeaderLabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.tbl_cal.verticalHeader().setVisible(False)
        self.tbl_cal.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_cal.setSelectionMode(QAbstractItemView.NoSelection)
        self.tbl_cal.setWordWrap(True)
        self.tbl_cal.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.tbl_cal, 1)

        self.cmb_cal_year.currentTextChanged.connect(self._refresh_calendar)
        self.cmb_cal_month.currentIndexChanged.connect(self._refresh_calendar)

        self._refresh_calendar()

    def _goto_today(self):
        t = _today()
        self.cmb_cal_year.setCurrentText(str(t.year))
        self.cmb_cal_month.setCurrentIndex(t.month - 1)

    def _month_bounds(self, y: int, m: int) -> Tuple[date, date]:
        start = date(y, m, 1)
        if m == 12:
            end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(y, m + 1, 1) - timedelta(days=1)
        return start, end

    def _refresh_calendar(self):
        y = int(self.cmb_cal_year.currentText())
        m = self.cmb_cal_month.currentIndex() + 1
        m_start, m_end = self._month_bounds(y, m)

        # clear grid
        for r in range(6):
            for c in range(7):
                it = QTableWidgetItem("")
                it.setFlags(Qt.ItemIsEnabled)
                self.tbl_cal.setItem(r, c, it)

        # employees
        emp_map: Dict[int, str] = {
            e.id: (e.full_name or f"Emp {e.id}")
            for e in self.session.query(Employee)
            .filter(Employee.account_id == tenant_id())
            .all()
        }

        # leave applications intersecting month — ONLY Approved
        acc = tenant_id()
        raw = self.session.connection().connection
        cur = raw.cursor()
        cur.execute(
            """
            SELECT employee_id, leave_type, start_date, start_half, end_date, end_half
            FROM leave_applications
            WHERE account_id = ?
              AND status = 'Approved'
              AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
            """,
            (acc, m_start.isoformat(), m_end.isoformat())
        )
        rows = cur.fetchall()

        # day -> [labels]
        day_map: Dict[date, List[str]] = {}
        for emp_id, lt, s_s, sh, e_s, eh in rows:
            try:
                s_all = date.fromisoformat(s_s)
                e_all = date.fromisoformat(e_s)
            except Exception:
                continue
            s = max(s_all, m_start)
            e = min(e_all, m_end)
            if s > e:
                continue

            name = emp_map.get(int(emp_id), f"Emp {emp_id}")
            type_tag = f"[{lt}]"

            cur_d = s
            one = timedelta(days=1)
            while cur_d <= e:
                tag = f"{name} {type_tag}"
                if s == e:
                    if sh == "AM" and eh == "AM":
                        tag = f"{name} {type_tag} (AM)"
                    elif sh == "PM" and eh == "PM":
                        tag = f"{name} {type_tag} (PM)"
                elif cur_d == s and sh == "PM":
                    tag = f"{name} {type_tag} (PM)"
                elif cur_d == e and eh == "AM":
                    tag = f"{name} {type_tag} (AM)"

                day_map.setdefault(cur_d, []).append(tag)
                cur_d += one

        # fill grid Monday=0
        first_wd = m_start.weekday()  # Mon=0..Sun=6
        day = 1
        total_days = m_end.day

        for r in range(6):
            self.tbl_cal.setRowHeight(r, 110)

        for slot in range(first_wd, first_wd + total_days):
            r = slot // 7
            c = slot % 7
            d = date(y, m, day)
            labels = sorted(day_map.get(d, []))
            lines = [str(day)] + labels
            txt = "\n".join(lines)
            it = QTableWidgetItem(txt)
            it.setFlags(Qt.ItemIsEnabled)
            it.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
            if labels:
                it.setBackground(QColor("#FFF4C2"))
                it.setToolTip("\n".join(labels))
            self.tbl_cal.setItem(r, c, it)
            day += 1

    # ----- User Application History -----
    def _init_user_history_tab(self):
        w = self._user_history_tab
        layout = QVBoxLayout(w)

        top = QHBoxLayout()
        layout.addLayout(top)
        top.addWidget(QLabel("Year:"))
        self.cmb_year_uh = QComboBox()
        cur_year = _today().year
        self.cmb_year_uh.addItems([str(cur_year - 1), str(cur_year), str(cur_year + 1)])
        self.cmb_year_uh.setCurrentText(str(cur_year))
        top.addWidget(self.cmb_year_uh)

        self.btn_refresh_uh = QPushButton("Refresh")
        self.btn_refresh_uh.clicked.connect(self._refresh_user_history)
        top.addWidget(self.btn_refresh_uh)

        top.addStretch(1)
        self.btn_delete_uh = QPushButton("Delete Selected")
        self.btn_delete_uh.clicked.connect(self._delete_selected_user_history)
        top.addWidget(self.btn_delete_uh)

        # Match All Details columns for consistency
        self.tbl_user_hist = QTableWidget(0, 11)
        self.tbl_user_hist.setHorizontalHeaderLabels([
            "ID", "Employee Code", "Employee", "Type", "Start", "Start Half", "End", "End Half", "Used", "Status", "User"
        ])
        self.tbl_user_hist.setColumnHidden(0, True)
        hdr = self.tbl_user_hist.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setDefaultAlignment(Qt.AlignCenter)
        self.tbl_user_hist.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_user_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tbl_user_hist)

        self.cmb_year_uh.currentIndexChanged.connect(self._refresh_user_history)

        self._refresh_user_history()

    def _refresh_user_history(self):
        session = self.session
        y = int(self.cmb_year_uh.currentText())
        y0, y1 = date(y, 1, 1), date(y, 12, 31)
        me = _current_user()

        emp_name_map: Dict[int, str] = {}
        emp_code_map: Dict[int, str] = {}
        for e in session.query(Employee).filter(Employee.account_id == tenant_id()).all():
            emp_name_map[e.id] = (e.full_name or f"Emp {e.id}")
            emp_code_map[e.id] = (getattr(e, "code", None) or "").strip() or str(e.id)

        self.tbl_user_hist.setRowCount(0)
        try:
            acc = tenant_id()
            raw = session.connection().connection
            cur = raw.cursor()
            has_created = _has_column(raw, "leave_applications", "created_by")
            has_action = _has_column(raw, "leave_applications", "action_user")

            if has_created:
                cur.execute(
                    f"""
                    SELECT id, employee_id, leave_type, start_date, start_half, end_date, end_half, used_days, status
                           {", action_user" if has_action else ""}
                    FROM leave_applications
                    WHERE account_id = ?
                      AND created_by = ?
                      AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
                    ORDER BY date(start_date) ASC
                    """,
                    (acc, me, y0.isoformat(), y1.isoformat())
                )
            elif has_action:
                cur.execute(
                    f"""
                    SELECT id, employee_id, leave_type, start_date, start_half, end_date, end_half, used_days, status, action_user
                    FROM leave_applications
                    WHERE account_id = ?
                      AND action_user = ?
                      AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
                    ORDER BY date(start_date) ASC
                    """,
                    (acc, me, y0.isoformat(), y1.isoformat())
                )
            else:
                cur.execute(
                    """
                    SELECT id, employee_id, leave_type, start_date, start_half, end_date, end_half, used_days, status
                    FROM leave_applications
                    WHERE account_id = ?
                      AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
                    ORDER BY date(start_date) ASC
                    """,
                    (acc, y0.isoformat(), y1.isoformat())
                )

            for row in cur.fetchall():
                if has_action and len(row) == 10:
                    _id, emp_id, leave_type, sd, sh, ed, eh, used, status, action_user = row
                else:
                    _id, emp_id, leave_type, sd, sh, ed, eh, used, status = row[:9]
                    action_user = row[9] if (len(row) > 9) else ""
                r = self.tbl_user_hist.rowCount()
                self.tbl_user_hist.insertRow(r)
                name = emp_name_map.get(int(emp_id), f"Emp {emp_id}")
                code = emp_code_map.get(int(emp_id), str(emp_id))
                vals = [
                    str(_id), code, name, str(leave_type),
                    str(sd), str(sh), str(ed), str(eh),
                    f"{float(used):.2f}" if used is not None else "0.00",
                    str(status or ""), str(action_user or "")
                ]
                for c, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setTextAlignment(Qt.AlignCenter)
                    self.tbl_user_hist.setItem(r, c, it)
        except Exception:
            pass

    def _delete_selected_user_history(self):
        try:
            raw = self.session.connection().connection
            cur = raw.cursor()
            ids = self._selected_ids_from(self.tbl_user_hist)
            if not ids:
                QMessageBox.information(self, "No selection", "Select one or more of your applications to delete.")
                return
            for _id in ids:
                cur.execute("DELETE FROM leave_applications WHERE id=?", (_id,))
            raw.commit()
            self._refresh_user_history()
            self._refresh_details()
            self._refresh_summary()
            self._refresh_calendar()
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Delete failed.\n{ex}")

# ---------------- public helpers ----------------

def entitlement_for_year_end(session, emp: Employee, leave_type: str, year: int) -> float:
    return _entitlement_asof(session, emp, leave_type, date(year, 12, 31))

def used_for_year(session, emp_id: int, leave_type: str, year: int, include_adjustments: bool = True) -> float:
    return _used_days_total_year(session, emp_id, leave_type, year, include_adjustments)

# ---------------- module entrypoints (for main_window) ----------------

def get_widget() -> QWidget:
    """Return the Leave module root widget with tabs already gated."""
    w = LeaveModuleWidget()
    # gating already applied in __init__, but call again safely if needed
    _gate_subtabs(w, ROOT_MODULE_NAME, MODULE_NAME, SUBMODULES)
    return w

def get_submodule_widget(sub: str) -> QWidget:
    """Return widget focused on a specific submodule tab title."""
    w = get_widget()
    _select_tab(w, sub)
    return w
