from __future__ import annotations
from datetime import date, timedelta
from calendar import monthrange

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QLineEdit, QPushButton, QFormLayout, QMessageBox,
    QSpinBox, QAbstractItemView
)

from ....core.database import SessionLocal
from ....core.tenant import id as tenant_id
from ..models import Employee, Holiday, WorkScheduleDay, LeaveDefault
# optional leave tables (use if present)
try:
    from ..models import LeaveApplication, LeaveAdjustment  # type: ignore
    _HAS_LEAVE_TABLES = True
except Exception:
    LeaveApplication = None  # type: ignore
    LeaveAdjustment = None   # type: ignore
    _HAS_LEAVE_TABLES = False


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

        self._reload_calendar()
        self._reload_details()
        self._reload_summary()

    # ---------- Calendar ----------
    def _build_calendar_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        ctrl = QHBoxLayout()
        self.cal_month = QComboBox(); self.cal_month.addItems([str(i) for i in range(1, 13)])
        self.cal_year = QComboBox(); self.cal_year.addItems([str(y) for y in range(2020, 2041)])
        self.cal_month.setCurrentText(str(date.today().month))
        self.cal_year.setCurrentText(str(date.today().year))
        ctrl.addWidget(QLabel("Month")); ctrl.addWidget(self.cal_month)
        ctrl.addWidget(QLabel("Year"));  ctrl.addWidget(self.cal_year)
        ctrl.addStretch(1)
        v.addLayout(ctrl)

        self.cal_tbl = QTableWidget(6, 7)
        self.cal_tbl.setHorizontalHeaderLabels(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])
        self.cal_tbl.verticalHeader().setVisible(False)
        self.cal_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.addWidget(self.cal_tbl, 1)

        self.cal_month.currentTextChanged.connect(self._reload_calendar)
        self.cal_year.currentTextChanged.connect(self._reload_calendar)

        self.tabs.addTab(host, "Calendar View")

    def _reload_calendar(self):
        m = int(self.cal_month.currentText()); y = int(self.cal_year.currentText())
        first = date(y, m, 1)
        _, ndays = monthrange(y, m)
        start_col = first.weekday()  # Mon=0..Sun=6

        self.cal_tbl.clearContents()
        for i in range(6):
            for j in range(7):
                self.cal_tbl.setItem(i, j, QTableWidgetItem(""))

        leave_by_day = {}
        if _HAS_LEAVE_TABLES:
            with SessionLocal() as s:
                apps = s.query(LeaveApplication).filter(LeaveApplication.account_id == tenant_id()).all()
                emap = {e.id: f"{e.full_name} ({e.code})" for e in s.query(Employee).all()}
            for a in apps:
                cur = a.start_date
                while cur <= a.end_date:
                    leave_by_day.setdefault(cur, []).append(emap.get(a.employee_id, f"ID {a.employee_id}"))
                    cur += timedelta(days=1)

        day = 1
        for cell in range(start_col, start_col + ndays):
            r = cell // 7; c = cell % 7
            d = date(y, m, day)
            names = "\n".join(sorted(set(leave_by_day.get(d, []))))
            txt = f"{day}\n{names}" if names else f"{day}"
            self.cal_tbl.setItem(r, c, QTableWidgetItem(txt))
            day += 1

    # ---------- Details ----------
    def _build_details_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        self.det_tbl = QTableWidget(0, 6)
        self.det_tbl.setHorizontalHeaderLabels(["Start Date","Start AM/PM","End Date","End AM/PM","Name","Remarks"])
        self.det_tbl.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.det_tbl, 1)
        self.tabs.addTab(host, "Details")

    def _reload_details(self):
        self.det_tbl.setRowCount(0)
        if not _HAS_LEAVE_TABLES:
            return
        with SessionLocal() as s:
            rows = (
                s.query(LeaveApplication)
                .filter(LeaveApplication.account_id == tenant_id())
                .order_by(LeaveApplication.start_date.asc())
                .all()
            )
            emap = {e.id: f"{e.full_name} ({e.code})" for e in s.query(Employee).all()}
        for a in rows:
            r = self.det_tbl.rowCount(); self.det_tbl.insertRow(r)
            vals = [
                a.start_date.strftime("%Y-%m-%d"),
                a.start_half or "AM",
                a.end_date.strftime("%Y-%m-%d"),
                a.end_half or "PM",
                emap.get(a.employee_id, str(a.employee_id)),
                a.remarks or ""
            ]
            for i, v in enumerate(vals):
                self.det_tbl.setItem(r, i, QTableWidgetItem(v))

    # ---------- Summary ----------
    def _build_summary_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        self.sum_tbl = QTableWidget(0, 4)
        self.sum_tbl.setHorizontalHeaderLabels(["Employee","Leave Type","Entitled","Balance"])
        self.sum_tbl.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.sum_tbl, 1)
        if not _HAS_LEAVE_TABLES:
            v.addWidget(QLabel("Note: leave tables not detected. Summary excludes applications/adjustments."))
        self.tabs.addTab(host, "Summary")

    def _reload_summary(self):
        self.sum_tbl.setRowCount(0)
        with SessionLocal() as s:
            emps = s.query(Employee).filter(Employee.account_id == tenant_id()).all()
            today = date.today()
            yos = {}
            for e in emps:
                if e.join_date:
                    years = max(1, min(50, int((today - e.join_date).days // 365.25) + 1))
                else:
                    years = 1
                yos[e.id] = years

            from ..models import LeaveEntitlement
            ent_map = {}
            ents = s.query(LeaveEntitlement).filter(LeaveEntitlement.account_id == tenant_id()).all()
            for ent in ents:
                if ent.year_of_service == yos.get(ent.employee_id, 1):
                    ent_map[(ent.employee_id, ent.leave_type)] = float(ent.days)

            used = {}
            adj = {}
            if _HAS_LEAVE_TABLES:
                apps = s.query(LeaveApplication).filter(LeaveApplication.account_id == tenant_id()).all()
                for a in apps:
                    used[(a.employee_id, a.leave_type)] = used.get((a.employee_id, a.leave_type), 0.0) + float(a.days_used or 0.0)
                adjs = s.query(LeaveAdjustment).filter(LeaveAdjustment.account_id == tenant_id()).all()
                for x in adjs:
                    adj[(x.employee_id, x.leave_type)] = adj.get((x.employee_id, x.leave_type), 0.0) + float(x.delta_days or 0.0)

        def ename(e: Employee): return f"{e.full_name} ({e.code})"
        for e in emps:
            for (emp_id, ltype), entitled in ent_map.items():
                if emp_id != e.id: continue
                u = used.get((emp_id, ltype), 0.0)
                a = adj.get((emp_id, ltype), 0.0)
                bal = entitled - u + a
                r = self.sum_tbl.rowCount(); self.sum_tbl.insertRow(r)
                for i, v in enumerate([ename(e), ltype, f"{entitled:.1f}", f"{bal:.1f}"]):
                    self.sum_tbl.setItem(r, i, QTableWidgetItem(v))

    # ---------- Application ----------
    def _build_application_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        frm = QFormLayout()
        self.app_emp = QComboBox(); self._load_employees(self.app_emp)
        self.app_type = QComboBox(); self._load_leave_types(self.app_type)
        self.app_s = QDateEdit(); self.app_s.setCalendarPopup(True); self.app_s.setDate(QDate.currentDate())
        self.app_s_half = QComboBox(); self.app_s_half.addItems(["AM","PM"])
        self.app_e = QDateEdit(); self.app_e.setCalendarPopup(True); self.app_e.setDate(QDate.currentDate())
        self.app_e_half = QComboBox(); self.app_e_half.addItems(["AM","PM"])
        self.app_remarks = QLineEdit()

        frm.addRow("Name", self.app_emp)
        frm.addRow("Type", self.app_type)
        row = QHBoxLayout(); row.addWidget(self.app_s); row.addWidget(self.app_s_half); row.addStretch(1)
        frm.addRow("Start", row)
        row2 = QHBoxLayout(); row2.addWidget(self.app_e); row2.addWidget(self.app_e_half); row2.addStretch(1)
        frm.addRow("End", row2)
        frm.addRow("Remarks", self.app_remarks)
        v.addLayout(frm)

        self.lbl_used = QLabel("Total used: 0.0 day")
        v.addWidget(self.lbl_used)

        btn = QPushButton("Submit"); btn.clicked.connect(self._submit_application)
        if not _HAS_LEAVE_TABLES:
            btn.setEnabled(False)
            v.addWidget(QLabel("Note: add LeaveApplication model to enable submission."))
        v.addWidget(btn)

        # live preview
        self.app_s.dateChanged.connect(self._update_used_preview)
        self.app_e.dateChanged.connect(self._update_used_preview)
        self.app_s_half.currentTextChanged.connect(self._update_used_preview)
        self.app_e_half.currentTextChanged.connect(self._update_used_preview)

        self.tabs.addTab(host, "Application")

    def _submit_application(self):
        if not _HAS_LEAVE_TABLES:
            return
        emp_id = self.app_emp.currentData()
        ltype = self.app_type.currentText().strip()
        d0 = self.app_s.date().toPython()
        d1 = self.app_e.date().toPython()
        if d1 < d0:
            QMessageBox.warning(self, "Leave", "End date earlier than start date.")
            return
        days = self._calc_working_days(emp_id, d0, self.app_s_half.currentText(), d1, self.app_e_half.currentText())
        with SessionLocal() as s:
            s.add(LeaveApplication(
                account_id=tenant_id(), employee_id=emp_id, leave_type=ltype,
                start_date=d0, start_half=self.app_s_half.currentText(),
                end_date=d1, end_half=self.app_e_half.currentText(),
                remarks=self.app_remarks.text().strip(), days_used=days, approved=True
            ))
            s.commit()
        self._reload_details(); self._reload_calendar(); self._reload_summary()
        QMessageBox.information(self, "Leave", "Application saved.")

    def _update_used_preview(self):
        emp_id = self.app_emp.currentData()
        d0 = self.app_s.date().toPython()
        d1 = self.app_e.date().toPython()
        used = self._calc_working_days(emp_id, d0, self.app_s_half.currentText(), d1, self.app_e_half.currentText())
        self.lbl_used.setText(f"Total used: {used:.1f} day")

    def _calc_working_days(self, employee_id: int, start: date, s_half: str, end: date, e_half: str) -> float:
        if end < start:
            return 0.0
        with SessionLocal() as s:
            sched = {w.weekday: (w.working, w.day_type) for w in s.query(WorkScheduleDay).filter(WorkScheduleDay.employee_id == employee_id).all()}
            emp = s.get(Employee, employee_id)
            hols = set(h.date for h in s.query(Holiday).filter(Holiday.group_code == (emp.holiday_group or "")).all())
        total = 0.0
        cur = start
        while cur <= end:
            wk = cur.weekday()
            working, day_type = sched.get(wk, (wk < 5, "Full"))  # default Mon-Fri
            if working and cur not in hols:
                add = 1.0 if day_type == "Full" else 0.5
                if cur == start and s_half == "PM":
                    add -= 0.5
                if cur == end and e_half == "AM":
                    add -= 0.5
                total += max(0.0, add)
            cur += timedelta(days=1)
        return total

    # ---------- Adjustments ----------
    def _build_adjustments_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        frm = QFormLayout()
        self.adj_emp = QComboBox(); self._load_employees(self.adj_emp)
        self.adj_type = QComboBox(); self._load_leave_types(self.adj_type)
        self.adj_delta = QSpinBox(); self.adj_delta.setRange(-365, 365); self.adj_delta.setValue(0)
        self.adj_date = QDateEdit(); self.adj_date.setCalendarPopup(True); self.adj_date.setDate(QDate.currentDate())
        frm.addRow("Name", self.adj_emp)
        frm.addRow("Type", self.adj_type)
        frm.addRow("± Days", self.adj_delta)
        frm.addRow("Date", self.adj_date)
        v.addLayout(frm)
        btn = QPushButton("Add Adjustment"); btn.clicked.connect(self._save_adjustment)
        if not _HAS_LEAVE_TABLES:
            btn.setEnabled(False)
            v.addWidget(QLabel("Note: add LeaveAdjustment model to enable adjustments."))
        v.addWidget(btn)
        self.tabs.addTab(host, "Adjustments")

    def _save_adjustment(self):
        if not _HAS_LEAVE_TABLES:
            return
        with SessionLocal() as s:
            s.add(LeaveAdjustment(
                account_id=tenant_id(),
                employee_id=self.adj_emp.currentData(),
                leave_type=self.adj_type.currentText().strip(),
                delta_days=float(self.adj_delta.value()),
                note="",
                date=self.adj_date.date().toPython()
            ))
            s.commit()
        self._reload_summary()
        QMessageBox.information(self, "Leave", "Adjustment saved.")

    # ---------- helpers ----------
    def _load_employees(self, combo: QComboBox):
        combo.clear()
        with SessionLocal() as s:
            rows = s.query(Employee).filter(Employee.account_id == tenant_id()).order_by(Employee.full_name).all()
        for r in rows:
            combo.addItem(f"{r.full_name} ({r.code})", r.id)

    def _load_leave_types(self, combo: QComboBox):
        combo.clear()
        with SessionLocal() as s:
            rows = s.query(LeaveDefault.leave_type).distinct().all()
        vals = [r[0] for r in rows] or ["Annual Leave"]
        for v in vals:
            combo.addItem(v)
