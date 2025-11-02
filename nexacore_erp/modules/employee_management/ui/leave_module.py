# leave_module.py — NexaCore ERP (Employee Management > Leave)
# Amended to implement EOL-based entitlement with prorate/reset/bring-forward-limit
# and robust used-days counting with work schedules and holidays.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import traceback
import json

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QLineEdit, QPushButton, QHeaderView, QMessageBox,
    QFormLayout, QAbstractItemView
)

# Project imports
from ....core.database import get_employee_session as SessionLocal
from ....core.tenant import id as tenant_id
from ..models import Employee, LeaveDefault, WorkScheduleDay, Holiday, LeaveEntitlement  # [NC PATCH] add LeaveEntitlement

# ---------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------

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
    """Return dict from JSON string or dict, else {}."""
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


# ---------------------------------------------------------------
# Service-year helpers for entitlement math
# ---------------------------------------------------------------

def _months_between(d0: date, d1: date) -> Tuple[int, int]:
    """Return completed (years, months remainder) between d0 and d1. If d1 <= d0 -> (0,0)."""
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
    """Service year k (1-based) as inclusive window [start, end]."""
    start = _add_years(join_dt, k - 1)
    end = _add_years(join_dt, k) - timedelta(days=1)
    return start, end


# ---------------------------------------------------------------
# EOL sources and policy
# ---------------------------------------------------------------

def _eol_map_for_emp(session, emp: Employee, leave_type: str) -> Dict[int, float]:
    """Return per-service-year entitlement for this employee and leave_type.
    Priority:
      1) Per-employee overrides in LeaveEntitlement (employee_id, leave_type, year_of_service)
      2) LeaveDefault.table_json['years'] for this leave_type (scoped to tenant)
    """
    eol_map: Dict[int, float] = {}

    # 1) Per-employee overrides (override first)
    rows = (
        session.query(LeaveEntitlement.year_of_service, LeaveEntitlement.days)
        .filter(
            LeaveEntitlement.employee_id == emp.id,
            LeaveEntitlement.leave_type == leave_type,
        )
        .all()
    )
    for yos, days in rows:
        try:
            eol_map[int(yos)] = float(days or 0.0)
        except Exception:
            pass

    if eol_map:
        return eol_map

    # 2) Fallback: LeaveDefault
    ld = (
        session.query(LeaveDefault)
        .filter(
            LeaveDefault.account_id == tenant_id(),  # [NC PATCH] scope to tenant
            LeaveDefault.leave_type == leave_type,
        )
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
    """Read policy flags for a leave_type.
    Expected fields from LeaveDefault:
      - prorated: bool or text
      - table_json._meta.carry_policy: "bring" or "reset"
      - table_json._meta.carry_limit_enabled: bool or text
      - table_json._meta.carry_limit: float or text
    Safe defaults if missing.
    """
    pol = {
        "prorated": False,
        "carry_policy": "bring",
        "carry_limit_enabled": False,
        "carry_limit": 0.0,
    }
    ld = (
        session.query(LeaveDefault)
        .filter(
            LeaveDefault.account_id == tenant_id(),  # [NC PATCH] scope to tenant
            LeaveDefault.leave_type == leave_type
        )
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
    mk = max(eol_map.keys())
    return float(eol_map[mk])


# ---------------------------------------------------------------
# Work schedule and holiday weights
# ---------------------------------------------------------------

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
    """Weight for a given date by employee work schedule: 1.0 work, 0.5 half, 0.0 off.
    Defaults to Mon-Fri=1.0, Sat/Sun=0.0 if no rows.
    """
    rows = session.query(WorkScheduleDay).filter(WorkScheduleDay.employee_id == emp_id).all()
    if not rows:
        return 1.0 if d.weekday() < 5 else 0.0

    # build map
    mp: Dict[int, float] = {}
    for r in rows:
        idx = _weekday_field(r)
        if idx is None:
            continue
        # [NC PATCH] respect 'working' flag and "Full/Half"
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
            # unknown label → treat as working full if 'working' True, otherwise off
            mp[idx] = 1.0
    return mp.get(d.weekday(), 0.0)


def _holiday_weight_for_date(h: Holiday) -> float:
    # Support either full-day only or optional half-day if column exists
    try:
        is_half = bool(getattr(h, "is_half_day"))
        return 0.5 if is_half else 1.0
    except Exception:
        return 1.0


def _holiday_dates_weight(session, emp: Employee, d0: date, d1: date) -> Dict[date, float]:
    """Return {date: weight} for holidays in [d0..d1] that apply to emp's holiday_group.
    Weight 1.0 = full-day holiday, 0.5 = half-day.
    """
    group_val = getattr(emp, "holiday_group", None)
    q = session.query(Holiday).filter(Holiday.account_id == tenant_id())  # [NC PATCH] scope to tenant
    if group_val:
        # [NC PATCH] correct column is group_code
        q = q.filter(Holiday.group_code == group_val)
    # [NC PATCH] only pull holidays in range
    try:
        q = q.filter(Holiday.date >= d0, Holiday.date <= d1)
    except Exception:
        pass

    rows = q.all()

    out: Dict[date, float] = {}
    for h in rows:
        hd = _safe_date(h, "date", "holiday_date", "dt")
        if not hd:
            continue
        if d0 <= hd <= d1:
            out[hd] = _holiday_weight_for_date(h)
    return out


# ---------------------------------------------------------------
# Used-days calculator for a single application window
# ---------------------------------------------------------------

def _compute_used_days(session, emp_id: int, s: date, s_half: str, e: date, e_half: str) -> float:
    """Count used days between s and e inclusive using work schedule and holidays.
    s_half/e_half in {"AM","PM"} determine half-day at endpoints.
    Holidays subtract weight from that day up to the workday weight floor of 0.
    """
    if e < s:
        return 0.0

    emp = session.query(Employee).get(emp_id)
    if not emp:
        return 0.0

    holidays = _holiday_dates_weight(session, emp, s, e)

    def day_portion(d: date) -> float:
        base = _employee_weekday_weight(session, emp_id, d)
        if base <= 0.0:
            return 0.0
        h_w = holidays.get(d, 0.0)
        eff = max(0.0, base - h_w)
        return eff

    total = 0.0
    cur = s
    one = timedelta(days=1)
    while cur <= e:
        eff = day_portion(cur)
        if eff <= 0.0:
            cur += one
            continue

        if s == e:
            # same day
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


# ---------------------------------------------------------------
# Usage aggregation over windows and years
# ---------------------------------------------------------------

def _used_days_in_window(session, emp_id: int, leave_type: str, w0: date, w1: date) -> float:
    """Sum approved leave usage inside [w0..w1], clipped to the window.
    Uses _compute_used_days for accurate work/holiday logic.
    """
    from sqlite3 import OperationalError
    acc = tenant_id()

    q = (
        """
        SELECT start_date, start_half, end_date, end_half
        FROM leave_applications
        WHERE account_id = ?
          AND employee_id = ?
          AND leave_type = ?
          AND status = 'Approved'
          AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
        """
    )

    try:
        raw_conn = session.connection().connection  # SQLAlchemy -> sqlite3
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
    """Sum of leave_adjustments.days for a given year. Positive adds entitlement, negative reduces."""
    from sqlite3 import OperationalError
    acc = tenant_id()

    q = (
        """
        SELECT COALESCE(SUM(days), 0.0)
        FROM leave_adjustments
        WHERE account_id = ? AND employee_id = ? AND leave_type = ? AND year = ?
        """
    )
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
    y0 = date(year, 1, 1)
    y1 = date(year, 12, 31)
    used = _used_days_in_window(session, emp_id, leave_type, y0, y1)
    if include_adjustments:
        used += _adjustments_sum_for_year(session, emp_id, leave_type, year)
    return round(float(used), 3)


# ---------------------------------------------------------------
# Entitlement engine combining all scenarios
# ---------------------------------------------------------------

def _entitlement_asof(session, emp: Employee, leave_type: str, as_of: date) -> float:
    """Implements 6 scenarios from user spec.

    carry_policy='bring', limit off:
        prorated=False -> sum(full years) + full(current)
        prorated=True  -> sum(full years) + (months/12)*current

    carry_policy='reset':
        prorated=False -> full(current only)
        prorated=True  -> (months/12)*current only

    carry_policy='bring', limit on (limit = L):
        Walk service years, carry leftover across boundaries with cap L.
        Current year portion is full(current) if prorated=False else (months/12)*current.
    """
    jd = _safe_date(emp, "join_date", "date_joined", "start_date")
    if not jd:
        return 0.0
    if as_of < jd:
        return 0.0

    eol_map = _eol_map_for_emp(session, emp, leave_type)
    pol = _policy_for_leave_type(session, leave_type)

    full_years, months_in_cur = _months_between(jd, as_of)
    cur_idx = max(1, full_years + 1)

    def current_year_entitlement(prorated: bool) -> float:
        base = _eol_amount(eol_map, cur_idx)
        if prorated:
            return (months_in_cur / 12.0) * base
        return base

    # Reset policy
    if pol["carry_policy"] == "reset":
        return round(current_year_entitlement(pol["prorated"]), 2)

    # Bring policy, no limit
    if not pol["carry_limit_enabled"]:
        total = 0.0
        for k in range(1, full_years + 1):
            total += _eol_amount(eol_map, k)
        total += current_year_entitlement(pol["prorated"])
        return round(total, 2)

    # Bring policy, limit on
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


# ---------------------------------------------------------------
# DDL bootstrap for leave tables in Employee DB
# ---------------------------------------------------------------

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
            status     TEXT NOT NULL DEFAULT 'Approved',
            remarks    TEXT,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_la_emp ON leave_applications(employee_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_la_type ON leave_applications(leave_type);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_la_start ON leave_applications(start_date);
        """,
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
        """
        CREATE INDEX IF NOT EXISTS idx_ladj_emp ON leave_adjustments(employee_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ladj_year ON leave_adjustments(year);
        """,
    ]
    try:
        raw_conn = session.connection().connection
        cur = raw_conn.cursor()
        for stmt in ddl:
            cur.execute(stmt)
        raw_conn.commit()
    except Exception:
        # silent; do not break UI just because tables are missing
        pass


# ---------------------------------------------------------------
# UI: Leave module widget
# ---------------------------------------------------------------

@dataclass
class _AppState:
    emp_id: Optional[int] = None
    leave_type: str = "Annual"


class LeaveModuleWidget(QWidget):
    """Minimal but functional UI wired to the entitlement and used-days logic."""

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

        self._init_summary_tab()
        self._init_application_tab()
        self._init_details_tab()
        self._init_adjustments_tab()

        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)

        self.tabs.addTab(self._summary_tab, "Summary")
        self.tabs.addTab(self._application_tab, "Application")
        self.tabs.addTab(self._details_tab, "Details")
        self.tabs.addTab(self._adjustments_tab, "Adjustments")

    # ---------------- Summary ----------------
    def _init_summary_tab(self):
        w = self._summary_tab
        layout = QVBoxLayout(w)

        top = QHBoxLayout()
        layout.addLayout(top)

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

        self.tbl_summary = QTableWidget(0, 5)
        self.tbl_summary.setHorizontalHeaderLabels(["Emp ID", "Employee", "Entitlement", "Used", "Balance"])
        self.tbl_summary.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_summary.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_summary.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tbl_summary)

        self._refresh_summary()

    def _refresh_summary(self):
        session = self.session
        y = int(self.cmb_year.currentText())
        lt = self.cmb_leave_type_sum.currentText() or "Annual"

        # [NC PATCH] scope employees to tenant
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

            r = self.tbl_summary.rowCount()
            self.tbl_summary.insertRow(r)
            self.tbl_summary.setItem(r, 0, QTableWidgetItem(str(emp.id)))
            name_txt = str(getattr(emp, "full_name", getattr(emp, "name", emp.id)))
            self.tbl_summary.setItem(r, 1, QTableWidgetItem(name_txt))
            self.tbl_summary.setItem(r, 2, QTableWidgetItem(f"{ent:.2f}"))
            self.tbl_summary.setItem(r, 3, QTableWidgetItem(f"{used:.2f}"))
            self.tbl_summary.setItem(r, 4, QTableWidgetItem(f"{bal:.2f}"))

    def _populate_leave_types(self, combo: QComboBox):
        # [NC PATCH] Prefer union of defaults and employee overrides so all types appear
        s = self.session
        types = set(
            t for (t,) in s.query(LeaveDefault.leave_type)
                          .filter(LeaveDefault.account_id == tenant_id())
                          .distinct().all()
        )
        try:
            types |= set(
                t for (t,) in s.query(LeaveEntitlement.leave_type)
                               .distinct().all()
            )
        except Exception:
            pass
        if not types:
            types = {"Annual", "Sick"}
        combo.clear()
        combo.addItems(sorted(types))

    # ---------------- Application ----------------
    def _init_application_tab(self):
        w = self._application_tab
        form = QFormLayout(w)

        # employee
        self.cmb_emp = QComboBox()
        self._populate_employees(self.cmb_emp)
        form.addRow("Employee", self.cmb_emp)

        # leave type
        self.cmb_leave_type = QComboBox()
        self._populate_leave_types(self.cmb_leave_type)
        form.addRow("Leave type", self.cmb_leave_type)

        # dates and halves
        self.de_start = QDateEdit()
        self.de_start.setCalendarPopup(True)
        self.de_start.setDate(QDate.currentDate())
        self.cmb_start_half = QComboBox(); self.cmb_start_half.addItems(["AM", "PM"])
        hl1 = QHBoxLayout(); hl1.addWidget(self.de_start); hl1.addWidget(self.cmb_start_half)
        form.addRow("Start", self._wrap(hl1))

        self.de_end = QDateEdit()
        self.de_end.setCalendarPopup(True)
        self.de_end.setDate(QDate.currentDate())
        self.cmb_end_half = QComboBox(); self.cmb_end_half.addItems(["AM", "PM"])
        hl2 = QHBoxLayout(); hl2.addWidget(self.de_end); hl2.addWidget(self.cmb_end_half)
        form.addRow("End", self._wrap(hl2))

        # remarks
        self.txt_remarks = QLineEdit()
        form.addRow("Remarks", self.txt_remarks)

        # computed used
        self.ed_used = QLineEdit(); self.ed_used.setReadOnly(True)
        form.addRow("Total Used", self.ed_used)

        # actions
        self.btn_calc = QPushButton("Recalculate")
        self.btn_submit = QPushButton("Submit")
        hl3 = QHBoxLayout(); hl3.addWidget(self.btn_calc); hl3.addWidget(self.btn_submit); hl3.addStretch(1)
        form.addRow(self._wrap(hl3))

        # signals
        self.cmb_emp.currentIndexChanged.connect(self._recalculate_used)
        self.cmb_leave_type.currentIndexChanged.connect(self._recalculate_used)
        self.de_start.dateChanged.connect(self._recalculate_used)
        self.de_end.dateChanged.connect(self._recalculate_used)
        self.cmb_start_half.currentIndexChanged.connect(self._recalculate_used)
        self.cmb_end_half.currentIndexChanged.connect(self._recalculate_used)
        self.btn_calc.clicked.connect(self._recalculate_used)
        self.btn_submit.clicked.connect(self._submit_application)

        self._recalculate_used()

    def _wrap(self, layout: QHBoxLayout):
        host = QWidget(); host.setLayout(layout); return host

    def _populate_employees(self, combo: QComboBox):
        combo.clear()
        rows = (
            self.session.query(Employee)
            .filter(Employee.account_id == tenant_id())  # [NC PATCH] scope to tenant
            .order_by(Employee.id.asc())
            .all()
        )
        for emp in rows:
            combo.addItem(str(getattr(emp, "full_name", getattr(emp, "name", emp.id))), emp.id)

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
            cur.execute(
                """
                INSERT INTO leave_applications(account_id, employee_id, leave_type, start_date, start_half, end_date, end_half, used_days, status, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Approved', ?)
                """,
                (acc, int(emp_id), leave_type, s.isoformat(), sh, e.isoformat(), eh, float(used), self.txt_remarks.text().strip())
            )
            raw.commit()
            QMessageBox.information(self, "Saved", "Leave application recorded.")
            self._recalculate_used()
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to save.\n{ex}")

    # ---------------- Details ----------------
    def _init_details_tab(self):
        w = self._details_tab
        layout = QVBoxLayout(w)

        top = QHBoxLayout(); layout.addLayout(top)
        top.addWidget(QLabel("Year:"))
        self.cmb_year_d = QComboBox()
        cur_year = _today().year
        self.cmb_year_d.addItems([str(cur_year - 1), str(cur_year), str(cur_year + 1)])
        self.cmb_year_d.setCurrentText(str(cur_year))
        top.addWidget(self.cmb_year_d)

        top.addWidget(QLabel("Leave type:"))
        self.cmb_leave_type_d = QComboBox(); self._populate_leave_types(self.cmb_leave_type_d)
        top.addWidget(self.cmb_leave_type_d)

        self.btn_refresh_d = QPushButton("Refresh")
        self.btn_refresh_d.clicked.connect(self._refresh_details)
        top.addWidget(self.btn_refresh_d)
        top.addStretch(1)

        self.tbl_details = QTableWidget(0, 8)
        self.tbl_details.setHorizontalHeaderLabels([
            "ID", "Emp ID", "Type", "Start", "Start Half", "End", "End Half", "Used"
        ])
        self.tbl_details.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_details.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_details.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tbl_details)

        self._refresh_details()

    def _refresh_details(self):
        session = self.session
        y = int(self.cmb_year_d.currentText())
        lt = self.cmb_leave_type_d.currentText() or "Annual"
        y0, y1 = date(y, 1, 1), date(y, 12, 31)

        self.tbl_details.setRowCount(0)
        try:
            acc = tenant_id()
            raw = session.connection().connection
            cur = raw.cursor()
            cur.execute(
                """
                SELECT id, employee_id, leave_type, start_date, start_half, end_date, end_half, used_days
                FROM leave_applications
                WHERE account_id = ? AND leave_type = ?
                  AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
                ORDER BY date(start_date) ASC
                """,
                (acc, lt, y0.isoformat(), y1.isoformat())
            )
            for row in cur.fetchall():
                r = self.tbl_details.rowCount(); self.tbl_details.insertRow(r)
                for c, val in enumerate(row):
                    self.tbl_details.setItem(r, c, QTableWidgetItem(str(val)))
        except Exception:
            # no table yet
            pass

    # ---------------- Adjustments ----------------
    def _init_adjustments_tab(self):
        w = self._adjustments_tab
        form = QFormLayout(w)

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

        self.btn_add_adj = QPushButton("Add Adjustment")
        self.btn_add_adj.clicked.connect(self._save_adjustment)
        form.addRow(self.btn_add_adj)

    def _save_adjustment(self):
        session = self.session
        try:
            emp_id = self.cmb_emp_adj.currentData()
            lt = self.cmb_leave_type_adj.currentText() or "Annual"
            y = int(self.cmb_year_adj.currentText())
            d = self.de_adj.date().toPython()
            days = float(self.ed_days_adj.text().strip())
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
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to save.\n{ex}")


# ---------------------------------------------------------------
# Public helpers you may want to import elsewhere
# ---------------------------------------------------------------

def entitlement_for_year_end(session, emp: Employee, leave_type: str, year: int) -> float:
    return _entitlement_asof(session, emp, leave_type, date(year, 12, 31))


def used_for_year(session, emp_id: int, leave_type: str, year: int, include_adjustments: bool = True) -> float:
    return _used_days_total_year(session, emp_id, leave_type, year, include_adjustments)
