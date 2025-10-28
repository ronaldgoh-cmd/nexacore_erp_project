# leave_module.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Dict, List, Tuple, Set

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QLineEdit, QPushButton, QHeaderView, QMessageBox,
    QSpinBox, QFormLayout, QDoubleSpinBox, QAbstractItemView
)

# Project imports (keep these paths)
from ....core.database import get_employee_session as SessionLocal
from ....core.tenant import id as tenant_id
from ..models import Employee  # must exist
MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"]


# ----------------------------
# Internal DB helpers (safe)
# ----------------------------

def _safe_scalar(session, sql: str, params: dict = None, default=None):
    try:
        res = session.execute(sql, params or {})
        row = res.first()
        return row[0] if row and len(row) > 0 else default
    except Exception:
        return default


def _safe_rows(session, sql: str, params: dict = None) -> List[tuple]:
    try:
        res = session.execute(sql, params or {})
        return list(res.fetchall())
    except Exception:
        return []


def _table_exists(session, table_name: str) -> bool:
    sql = """
    SELECT COUNT(*) FROM sqlite_master
    WHERE type='table' AND name=:name
    """
    return bool(_safe_scalar(session, sql, {"name": table_name}, 0))


# --------------------------------------
# Business rules: workdays, holidays, use
# --------------------------------------

def _default_workdays() -> Set[int]:
    # Monday=0 ... Sunday=6
    return {0, 1, 2, 3, 4}


def _employee_workdays(session, emp_id: int) -> Set[int]:
    """
    Reads employee_workdays( employee_id, weekday INT 0-6, is_working INT/BOOL ).
    Falls back to Mon-Fri if table missing or empty.
    """
    if not _table_exists(session, "employee_workdays"):
        return _default_workdays()
    rows = _safe_rows(session, """
        SELECT weekday, COALESCE(is_working,1)
        FROM employee_workdays
        WHERE employee_id=:eid
    """, {"eid": emp_id})
    days = {wk for wk, isw in rows if (wk is not None and int(isw) == 1)}
    return days or _default_workdays()


def _holidays_between(session, d0: date, d1: date) -> Dict[date, float]:
    """
    Reads holidays(date TEXT 'YYYY-MM-DD', is_half_day INT) as generic/global.
    Returns map of date -> 1.0 (full) or 0.5 (half). Empty if table missing.
    """
    if not _table_exists(session, "holidays"):
        return {}
    rows = _safe_rows(session, """
        SELECT date, COALESCE(is_half_day,0)
        FROM holidays
        WHERE date BETWEEN :a AND :b
    """, {"a": d0.isoformat(), "b": d1.isoformat()})
    out: Dict[date, float] = {}
    for ds, half in rows:
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d").date()
            out[dt] = 0.5 if int(half) == 1 else 1.0
        except Exception:
            continue
    return out


def _daterange(d0: date, d1: date):
    cur = d0
    while cur <= d1:
        yield cur
        cur = cur + timedelta(days=1)


def _compute_used_days(
    session,
    emp_id: int,
    s_date: date,
    s_half: str,  # "AM" or "PM"
    e_date: date,
    e_half: str   # "AM" or "PM"
) -> float:
    """
    Rules:
    - Count only employee workdays.
    - Exclude full holidays (1.0). Half holidays reduce 0.5 if the half overlaps.
    - Same-day:
        AM..AM => 0.5
        PM..PM => 0.5
        AM..PM => 1.0
        PM..AM => 0.0
    - Multi-day:
        first day: 0.5 if start=PM else 1.0 (if working day)
        last day:  0.5 if end=AM   else 1.0 (if working day)
        full middle working days: 1.0 each
    - Never negative. Floor at 0.
    """
    if e_date < s_date:
        return 0.0

    workdays = _employee_workdays(session, emp_id)
    hols = _holidays_between(session, s_date, e_date)

    def is_workday(d: date) -> bool:
        return d.weekday() in workdays

    def holiday_weight(d: date, half: Optional[str] = None) -> float:
        w = hols.get(d, 0.0)
        if w >= 1.0:
            return 1.0
        if w == 0.5:
            if half in ("AM", "PM"):
                return 0.5
            return 0.5
        return 0.0

    # Same-day
    if s_date == e_date:
        if not is_workday(s_date):
            return 0.0
        if s_half == "AM" and e_half == "AM":
            gross = 0.5
            red = holiday_weight(s_date, "AM")
            return max(0.0, gross - min(red, gross))
        if s_half == "PM" and e_half == "PM":
            gross = 0.5
            red = holiday_weight(s_date, "PM")
            return max(0.0, gross - min(red, gross))
        if s_half == "AM" and e_half == "PM":
            gross = 1.0
            red = holiday_weight(s_date, None)
            return max(0.0, gross - min(red, gross))
        return 0.0

    # Multi-day
    total = 0.0
    for d in _daterange(s_date, e_date):
        if not is_workday(d):
            continue
        if d == s_date:
            day_take = 0.5 if s_half == "PM" else 1.0
            red = holiday_weight(d, s_half if day_take == 0.5 else None)
            total += max(0.0, day_take - min(red, day_take))
        elif d == e_date:
            day_take = 0.5 if e_half == "AM" else 1.0
            red = holiday_weight(d, e_half if day_take == 0.5 else None)
            total += max(0.0, day_take - min(red, day_take))
        else:
            day_take = 1.0
            red = holiday_weight(d, None)
            total += max(0.0, day_take - min(red, day_take))

    return round(total, 2)


# --------------------------------------
# Optional leave tables (names assumed)
# --------------------------------------

def _ensure_leave_tables(session):
    return


def _fetch_leave_types(session) -> List[str]:
    if _table_exists(session, "leave_types"):
        rows = _safe_rows(session, "SELECT name FROM leave_types WHERE COALESCE(active,1)=1 ORDER BY name")
        vals = [r[0] for r in rows if r and r[0]]
        return vals or []
    return []


def _entitlement_for(session, emp_id: int, leave_type: str, year: int) -> float:
    if _table_exists(session, "leave_entitlements"):
        v = _safe_scalar(session, """
            SELECT days FROM leave_entitlements
            WHERE employee_id=:e AND leave_type=:t AND year=:y
        """, {"e": emp_id, "t": leave_type, "y": year}, None)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 14.0


def _adjustments_total(session, emp_id: int, leave_type: str, year: int) -> float:
    if _table_exists(session, "leave_adjustments"):
        v = _safe_scalar(session, """
            SELECT COALESCE(SUM(days),0) FROM leave_adjustments
            WHERE employee_id=:e AND leave_type=:t AND year=:y
        """, {"e": emp_id, "t": leave_type, "y": year}, 0.0)
        try:
            return float(v or 0.0)
        except Exception:
            return 0.0
    return 0.0


def _used_days_total(session, emp_id: int, leave_type: str, year: int) -> float:
    if _table_exists(session, "leave_applications"):
        v = _safe_scalar(session, """
            SELECT COALESCE(SUM(used_days),0) FROM leave_applications
            WHERE employee_id=:e AND leave_type=:t AND strftime('%Y', start_date)=:y
              AND COALESCE(status,'Approved')='Approved'
        """, {"e": emp_id, "t": leave_type, "y": str(year)}, 0.0)
        try:
            return float(v or 0.0)
        except Exception:
            return 0.0
    return 0.0


def _insert_application(session,
                        emp_id: int,
                        leave_type: str,
                        start_date: date,
                        start_half: str,
                        end_date: date,
                        end_half: str,
                        used_days: float,
                        remarks: str) -> bool:
    if not _table_exists(session, "leave_applications"):
        return False
    try:
        session.execute("""
            INSERT INTO leave_applications
            (account_id, employee_id, leave_type, start_date, start_half,
             end_date, end_half, used_days, status, remarks, created_at)
            VALUES
            (:acc, :eid, :typ, :sd, :sh, :ed, :eh, :used, 'Approved', :rem, CURRENT_TIMESTAMP)
        """, {
            "acc": tenant_id(),
            "eid": emp_id,
            "typ": leave_type,
            "sd": start_date.isoformat(),
            "sh": start_half,
            "ed": end_date.isoformat(),
            "eh": end_half,
            "used": used_days,
            "rem": remarks or ""
        })
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False


def _list_applications(session, year: int) -> List[Tuple]:
    if not _table_exists(session, "leave_applications"):
        return []
    return _safe_rows(session, """
        SELECT la.id, e.full_name, COALESCE(e.code,''), la.leave_type,
               la.start_date, la.start_half, la.end_date, la.end_half,
               COALESCE(la.used_days,0), COALESCE(la.status,'Approved'), COALESCE(la.remarks,'')
        FROM leave_applications la
        LEFT JOIN employees e ON e.id = la.employee_id
        WHERE strftime('%Y', la.start_date)=:y AND la.account_id=:acc
        ORDER BY la.start_date DESC, la.id DESC
    """, {"y": str(year), "acc": tenant_id()})


# --- adjustments helpers ---

def _insert_adjustment(session,
                       emp_id: int,
                       leave_type: str,
                       when: date,
                       days: float,
                       remarks: str) -> bool:
    if not _table_exists(session, "leave_adjustments"):
        return False
    try:
        session.execute("""
            INSERT INTO leave_adjustments
            (account_id, employee_id, leave_type, year, date, days, remarks, created_at)
            VALUES
            (:acc, :eid, :typ, :yr, :d, :days, :rem, CURRENT_TIMESTAMP)
        """, {
            "acc": tenant_id(),
            "eid": emp_id,
            "typ": leave_type,
            "yr": when.year,
            "d": when.isoformat(),
            "days": float(days),
            "rem": remarks or ""
        })
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False


def _list_adjustments(session, limit: int = 200) -> List[Tuple]:
    if not _table_exists(session, "leave_adjustments"):
        return []
    return _safe_rows(session, f"""
        SELECT la.date, e.full_name, COALESCE(e.code,''), la.leave_type, la.days, COALESCE(la.remarks,'')
        FROM leave_adjustments la
        LEFT JOIN employees e ON e.id = la.employee_id
        WHERE la.account_id = :acc
        ORDER BY la.date DESC, la.rowid DESC
        LIMIT {int(limit)}
    """, {"acc": tenant_id()})


# ----------------------------
# UI
# ----------------------------

class LeaveModuleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget(self)
        v = QVBoxLayout(self)
        v.addWidget(self.tabs)

        self._build_calendar_tab()
        self._build_details_tab()
        self._build_summary_tab()
        self._build_application_tab()
        self._build_adjustments_tab()

        self._refresh_all()

    # -------- Calendar --------

    def _build_calendar_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        top = QHBoxLayout()
        self.month = QComboBox()
        self.month.addItems(MONTHS)
        self.year = QComboBox()
        self.year.addItems([str(y) for y in range(2024, 2036)])
        today = date.today()
        self.month.setCurrentIndex(today.month - 1)
        self.year.setCurrentText(str(today.year))

        # live refresh on change
        self.month.currentTextChanged.connect(lambda _=None: self._reload_calendar())
        self.month.currentIndexChanged.connect(lambda _=None: self._reload_calendar())
        self.year.currentTextChanged.connect(lambda _=None: self._reload_calendar())
        self.year.currentIndexChanged.connect(lambda _=None: self._reload_calendar())

        top.addWidget(QLabel("Month"))
        top.addWidget(self.month)
        top.addWidget(QLabel("Year"))
        top.addWidget(self.year)
        top.addStretch(1)
        v.addLayout(top)

        self.cal = QTableWidget(6, 7)
        self.cal.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cal.setSelectionMode(QTableWidget.NoSelection)
        self.cal.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cal.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cal.setHorizontalHeaderLabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        v.addWidget(self.cal, 1)

        self.tabs.addTab(host, "Calendar View")

    def _reload_calendar(self):
        self._populate_calendar()

    def _populate_calendar(self):
        for r in range(6):
            for c in range(7):
                self.cal.setItem(r, c, QTableWidgetItem(""))

        try:
            m = self.month.currentIndex() + 1
            y = int(self.year.currentText())
        except Exception:
            return

        first = date(y, m, 1)
        # Python weekday: Mon=0..Sun=6 aligns with our headers
        start_col = first.weekday()

        r, c = 0, start_col
        d = first
        while d.month == m:
            item = QTableWidgetItem(str(d.day))
            item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.cal.setItem(r, c, item)
            c += 1
            if c >= 7:
                c = 0
                r += 1
                if r >= 6:
                    break
            d = d + timedelta(days=1)

    # -------- Details --------

    def _build_details_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        top = QHBoxLayout()
        top.addWidget(QLabel("Year"))
        self.det_year = QSpinBox()
        self.det_year.setRange(2000, 2100)
        self.det_year.setValue(date.today().year)
        btn = QPushButton("Reload")
        btn.clicked.connect(self._populate_details)
        top.addWidget(self.det_year)
        top.addStretch(1)
        top.addWidget(btn)
        v.addLayout(top)

        self.tbl = QTableWidget(0, 10)
        self.tbl.setHorizontalHeaderLabels([
            "ID", "Name", "Code", "Type", "Start", "End", "Used", "Status", "Remarks", " "
        ])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.tbl, 1)

        self.tabs.addTab(host, "Details")

    def _populate_details(self):
        yr = int(self.det_year.value())
        self.tbl.setRowCount(0)
        with SessionLocal() as s:
            rows = _list_applications(s, yr)
        for row in rows:
            rid, name, code, ltype, sd, sh, ed, eh, used, status, rem = row
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(rid)))
            self.tbl.setItem(r, 1, QTableWidgetItem(name or ""))
            self.tbl.setItem(r, 2, QTableWidgetItem(code or ""))
            self.tbl.setItem(r, 3, QTableWidgetItem(ltype or ""))
            sdisp = f"{sd or ''} {sh or ''}"
            edisp = f"{ed or ''} {eh or ''}"
            self.tbl.setItem(r, 4, QTableWidgetItem(sdisp.strip()))
            self.tbl.setItem(r, 5, QTableWidgetItem(edisp.strip()))
            self.tbl.setItem(r, 6, QTableWidgetItem(f"{used:.2f}"))
            self.tbl.setItem(r, 7, QTableWidgetItem(status or ""))
            self.tbl.setItem(r, 8, QTableWidgetItem(rem or ""))
            self.tbl.setItem(r, 9, QTableWidgetItem(""))

    # -------- Summary --------

    def _build_summary_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        top = QHBoxLayout()
        top.addWidget(QLabel("Year"))
        self.sum_year = QSpinBox()
        self.sum_year.setRange(2000, 2100)
        self.sum_year.setValue(date.today().year)
        self.sum_type = QComboBox()
        self.sum_type.setEditable(True)
        self.sum_reload = QPushButton("Reload")
        self.sum_reload.clicked.connect(self._populate_summary)
        top.addWidget(self.sum_year)
        top.addWidget(QLabel("Leave Type"))
        top.addWidget(self.sum_type)
        top.addStretch(1)
        top.addWidget(self.sum_reload)
        v.addLayout(top)

        self.sum_tbl = QTableWidget(0, 6)
        self.sum_tbl.setHorizontalHeaderLabels(
            ["Employee", "Code", "Entitlement", "Adjustments", "Used", "Balance"]
        )
        self.sum_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sum_tbl.verticalHeader().setVisible(False)
        v.addWidget(self.sum_tbl, 1)

        self.tabs.addTab(host, "Summary")

    def _populate_summary(self):
        yr = int(self.sum_year.value())
        ltype = self.sum_type.currentText().strip() or "Annual Leave"

        with SessionLocal() as s:
            emps = s.query(Employee).filter(Employee.account_id == tenant_id()).order_by(Employee.full_name).all()
            self.sum_tbl.setRowCount(0)
            for e in emps:
                ent = _entitlement_for(s, e.id, ltype, yr)
                adj = _adjustments_total(s, e.id, ltype, yr)
                used = _used_days_total(s, e.id, ltype, yr)
                bal = round(ent + adj - used, 2)
                r = self.sum_tbl.rowCount()
                self.sum_tbl.insertRow(r)
                self.sum_tbl.setItem(r, 0, QTableWidgetItem(e.full_name or ""))
                self.sum_tbl.setItem(r, 1, QTableWidgetItem(e.code or ""))
                self.sum_tbl.setItem(r, 2, QTableWidgetItem(f"{ent:.2f}"))
                self.sum_tbl.setItem(r, 3, QTableWidgetItem(f"{adj:.2f}"))
                self.sum_tbl.setItem(r, 4, QTableWidgetItem(f"{used:.2f}"))
                self.sum_tbl.setItem(r, 5, QTableWidgetItem(f"{bal:.2f}"))

    # -------- Application --------

    def _build_application_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        h = QHBoxLayout()
        self.emp = QComboBox()
        self._load_employees()

        self.type = QComboBox()
        self.type.setEditable(True)
        self._load_leave_types()

        self.s_date = QDateEdit()
        self.s_date.setCalendarPopup(True)
        self.s_date.setDate(QDate.currentDate())

        self.s_ampm = QComboBox()
        self.s_ampm.addItems(["AM", "PM"])

        self.e_date = QDateEdit()
        self.e_date.setCalendarPopup(True)
        self.e_date.setDate(QDate.currentDate())

        self.e_ampm = QComboBox()
        self.e_ampm.addItems(["AM", "PM"])

        self.remarks = QLineEdit()
        self.remarks.setPlaceholderText("Remarks")

        widgets = [
            QLabel("Name"), self.emp,
            QLabel("Type"), self.type,
            QLabel("Start"), self.s_date, self.s_ampm,
            QLabel("End"), self.e_date, self.e_ampm,
            self.remarks
        ]
        for w in widgets:
            h.addWidget(w)
        h.addStretch(1)
        v.addLayout(h)

        info = QHBoxLayout()
        self.lbl_used = QLabel("Total Used: 0.00")
        self.lbl_balance = QLabel("Balance: –")
        info.addWidget(self.lbl_used)
        info.addSpacing(20)
        info.addWidget(self.lbl_balance)
        info.addStretch(1)
        v.addLayout(info)

        act = QHBoxLayout()
        btn_calc = QPushButton("Recalculate")
        btn_save = QPushButton("Submit Application")
        btn_calc.clicked.connect(self._recalculate_used)
        btn_save.clicked.connect(self._submit_application)
        act.addStretch(1)
        act.addWidget(btn_calc)
        act.addWidget(btn_save)
        v.addLayout(act)

        self.emp.currentIndexChanged.connect(self._recalculate_used)
        self.type.currentIndexChanged.connect(self._recalculate_used)
        self.s_date.dateChanged.connect(self._recalculate_used)
        self.e_date.dateChanged.connect(self._recalculate_used)
        self.s_ampm.currentIndexChanged.connect(self._recalculate_used)
        self.e_ampm.currentIndexChanged.connect(self._recalculate_used)

        self.tabs.addTab(host, "Application")

    def _recalculate_used(self):
        emp_id = self.emp.currentData()
        if not emp_id:
            self.lbl_used.setText("Total Used: 0.00")
            self.lbl_balance.setText("Balance: –")
            return

        s_qd: QDate = self.s_date.date()
        e_qd: QDate = self.e_date.date()
        s_dt = date(s_qd.year(), s_qd.month(), s_qd.day())
        e_dt = date(e_qd.year(), e_qd.month(), e_qd.day())
        s_half = self.s_ampm.currentText()
        e_half = self.e_ampm.currentText()
        ltype = self.type.currentText().strip() or "Annual Leave"
        yr = s_dt.year

        with SessionLocal() as s:
            used = _compute_used_days(s, emp_id, s_dt, s_half, e_dt, e_half)
            ent = _entitlement_for(s, emp_id, ltype, yr)
            adj = _adjustments_total(s, emp_id, ltype, yr)
            used_ytd = _used_days_total(s, emp_id, ltype, yr)
            balance = round(ent + adj - used_ytd, 2)

        self.lbl_used.setText(f"Total Used: {used:.2f}")
        self.lbl_balance.setText(f"Balance: {balance:.2f}")

    def _submit_application(self):
        emp_id = self.emp.currentData()
        if not emp_id:
            QMessageBox.warning(self, "Missing", "Select an employee.")
            return

        ltype = self.type.currentText().strip() or "Annual Leave"
        s_qd: QDate = self.s_date.date()
        e_qd: QDate = self.e_date.date()
        s_dt = date(s_qd.year(), s_qd.month(), s_qd.day())
        e_dt = date(e_qd.year(), e_qd.month(), e_qd.day())
        s_half = self.s_ampm.currentText()
        e_half = self.e_ampm.currentText()
        remarks = self.remarks.text().strip()

        with SessionLocal() as s:
            used = _compute_used_days(s, emp_id, s_dt, s_half, e_dt, e_half)
            ok = _insert_application(
                s, emp_id, ltype, s_dt, s_half, e_dt, e_half, used, remarks
            )

        if ok:
            QMessageBox.information(self, "Saved", "Application saved.")
            self._refresh_all()
        else:
            QMessageBox.information(
                self, "Note",
                "Application not written because table 'leave_applications' was not found.\n"
                "Create the table to persist."
            )

    # -------- Adjustments --------

    def _build_adjustments_tab(self):
        host = QWidget()
        v = QVBoxLayout(host)

        form = QFormLayout()
        self.adj_emp = QComboBox(); self._load_employees_into(self.adj_emp)
        self.adj_date = QDateEdit(); self.adj_date.setCalendarPopup(True); self.adj_date.setDate(QDate.currentDate())
        self.adj_type = QComboBox(); self._load_leave_types_into(self.adj_type)
        self.adj_days = QDoubleSpinBox(); self.adj_days.setRange(-365.0, 365.0); self.adj_days.setSingleStep(0.5); self.adj_days.setDecimals(1)
        self.adj_rem = QLineEdit(); self.adj_rem.setPlaceholderText("Remarks (optional)")

        form.addRow("Employee", self.adj_emp)
        form.addRow("Date", self.adj_date)
        form.addRow("Leave Type", self.adj_type)
        form.addRow("± Days", self.adj_days)
        form.addRow("Remarks", self.adj_rem)
        v.addLayout(form)

        actions = QHBoxLayout()
        btn_add = QPushButton("Add Adjustment")
        btn_add.clicked.connect(self._save_adjustment)
        actions.addStretch(1)
        actions.addWidget(btn_add)
        v.addLayout(actions)

        self.adj_tbl = QTableWidget(0, 5)
        self.adj_tbl.setHorizontalHeaderLabels(["Date", "Employee", "Code", "Type", "± Days"])
        self.adj_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.adj_tbl.horizontalHeader().setStretchLastSection(True)
        self.adj_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.addWidget(self.adj_tbl, 1)

        self.tabs.addTab(host, "Adjustments")

    def _reload_adjustments(self):
        if not hasattr(self, "adj_tbl"):
            return
        self.adj_tbl.setRowCount(0)
        with SessionLocal() as s:
            rows = _list_adjustments(s, limit=200)
        for d, name, code, ltype, days, _rem in rows:
            r = self.adj_tbl.rowCount(); self.adj_tbl.insertRow(r)
            self.adj_tbl.setItem(r, 0, QTableWidgetItem(str(d or "")))
            self.adj_tbl.setItem(r, 1, QTableWidgetItem(name or ""))
            self.adj_tbl.setItem(r, 2, QTableWidgetItem(code or ""))
            self.adj_tbl.setItem(r, 3, QTableWidgetItem(ltype or ""))
            self.adj_tbl.setItem(r, 4, QTableWidgetItem(f"{float(days):.1f}"))

    def _save_adjustment(self):
        emp_id = self.adj_emp.currentData()
        if not emp_id:
            QMessageBox.warning(self, "Missing", "Select an employee.")
            return
        when = self.adj_date.date().toPython()
        ltype = self.adj_type.currentText().strip() or "Annual Leave"
        days = float(self.adj_days.value())
        remarks = self.adj_rem.text().strip()

        with SessionLocal() as s:
            ok = _insert_adjustment(s, emp_id, ltype, when, days, remarks)

        if ok:
            QMessageBox.information(self, "Saved", "Adjustment saved.")
            self._populate_summary()
            self._reload_adjustments()
        else:
            QMessageBox.information(
                self, "Note",
                "Adjustment not written because table 'leave_adjustments' was not found.\n"
                "Create the table to persist."
            )

    # -------- Data loads --------

    def _load_employees(self):
        self.emp.clear()
        with SessionLocal() as s:
            rows = s.query(Employee).filter(Employee.account_id == tenant_id()).order_by(Employee.full_name).all()
        for r in rows:
            self.emp.addItem(f"{r.full_name} ({r.code})", r.id)

    def _load_employees_into(self, combo: QComboBox):
        combo.clear()
        with SessionLocal() as s:
            rows = s.query(Employee).filter(Employee.account_id == tenant_id()).order_by(Employee.full_name).all()
        for r in rows:
            combo.addItem(f"{r.full_name} ({r.code})", r.id)

    def _load_leave_types(self):
        with SessionLocal() as s:
            types = _fetch_leave_types(s)
        if types:
            self.type.clear()
            self.type.addItems(types)

        self.sum_type.clear()
        if types:
            self.sum_type.addItems(types)
        else:
            self.sum_type.addItem("Annual Leave")

    def _load_leave_types_into(self, combo: QComboBox):
        combo.clear()
        with SessionLocal() as s:
            types = _fetch_leave_types(s)
        combo.addItems(types or ["Annual Leave"])

    # -------- Full refresh --------

    def _refresh_all(self):
        with SessionLocal() as s:
            _ensure_leave_tables(s)

        self._populate_calendar()
        self._populate_details()
        self._populate_summary()
        self._recalculate_used()
        self._reload_adjustments()
