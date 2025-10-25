from datetime import datetime, date
import re
import json
import os


from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QComboBox, QFormLayout, QDateEdit, QFileDialog,
    QDialog, QDialogButtonBox, QMessageBox, QSpinBox, QCheckBox, QGroupBox, QGridLayout,
    QScrollArea, QListWidgetItem, QHeaderView, QAbstractItemView, QSizePolicy, QListWidget,
    QInputDialog
)

# optional XLSX support
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter
except Exception:
    Workbook = None
    load_workbook = None
    DataValidation = None
    get_column_letter = None

from ....core.database import SessionLocal
from ....core.tenant import id as tenant_id
from ..models import (
    Employee, SalaryHistory, Holiday, DropdownOption, LeaveDefault,
    WorkScheduleDay, LeaveEntitlement
)

# ---------------- Employee code settings (session-scope) ----------------
EMP_CODE_PREFIX = "EM-"
EMP_CODE_ZPAD = 4

# Valid dropdown categories managed in UI
MANAGED_CATEGORIES = [
    "ID Type", "Gender", "Race", "Country", "Residency",
    "Employment Pass", "Department", "Position", "Employment Type", "Bank"
]
# persist employee code format to a small json file next to this module
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "employee_settings.json")

def _load_code_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            p = str(d.get("prefix", "EM-") or "EM-")
            z = int(d.get("zpad", 4) or 4)
            return p, z
    except Exception:
        return "EM-", 4

def _save_code_settings(prefix: str, zpad: int):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"prefix": prefix, "zpad": int(zpad)}, f)
    except Exception:
        pass

# Columns for Employee List table (order matters)
COLS = [
    ("employment_status", "Status"),
    ("code", "Employee Code"),
    ("full_name", "Employee Name"),
    ("department", "Department"),
    ("position", "Position"),
    ("employment_type", "Employment Type"),
    ("dob", "Date of Birth"),
    ("age", "Age"),
    ("id_type", "Identification Type"),
    ("id_number", "Identification Number"),
    ("country", "Country"),
    ("residency", "Residency"),
    ("join_date", "Join Date"),
    ("exit_date", "Exit Date"),
]


class EmployeeMainWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("EmployeeMainWidget")
        # load persisted code format into globals
        global EMP_CODE_PREFIX, EMP_CODE_ZPAD
        EMP_CODE_PREFIX, EMP_CODE_ZPAD = _load_code_settings()

        self.tabs = QTabWidget(self)
        v = QVBoxLayout(self)
        v.addWidget(self.tabs)


        self._build_employee_list_tab()
        self._build_holidays_tab()
        self._build_settings_tab()

    # ---------------- Employee List ----------------
    def _build_employee_list_tab(self):
        host = QWidget()
        h = QHBoxLayout(host)
        splitter = QSplitter(Qt.Horizontal, host)

        # left: table + filters + actions
        left = QWidget(splitter)
        lv = QVBoxLayout(left)

        # actions row
        actions = QHBoxLayout()
        # filters toggle
        self.filter_toggle = QPushButton("Filters ▾")
        self.filter_toggle.setCheckable(True)
        self.filter_toggle.setChecked(True)
        self.filter_toggle.toggled.connect(self._toggle_filters)
        actions.addWidget(self.filter_toggle)

        self.quick_search = QLineEdit()
        self.quick_search.setPlaceholderText("Quick search (any column)…")
        self.quick_search.textChanged.connect(self._apply_filters)
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._add_employee)
        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._edit_employee)
        btn_del = QPushButton("Delete")
        btn_del.clicked.connect(self._delete_employee)
        for w in (self.quick_search, btn_add, btn_edit, btn_del):
            actions.addWidget(w)
        lv.addLayout(actions)

        # per-column filters
        self.filter_box = QGroupBox("Filters")
        fbv = QVBoxLayout(self.filter_box)
        grid = QGridLayout()
        self.filters: dict[str, QWidget] = {}

        def add_filter(row, label, key, widget_factory):
            grid.addWidget(QLabel(label), row, 0)
            w = widget_factory()
            self.filters[key] = w
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self._apply_filters)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(self._apply_filters)
            grid.addWidget(w, row, 1)

        r = 0
        add_filter(r, "Status", "employment_status",
                   lambda: self._combo_with(["", "Active", "Non-Active"])); r += 1
        add_filter(r, "Employee Code", "code", QLineEdit); r += 1
        add_filter(r, "Employee Name", "full_name", QLineEdit); r += 1
        add_filter(r, "Department", "department", QLineEdit); r += 1
        add_filter(r, "Position", "position", QLineEdit); r += 1
        add_filter(r, "Employment Type", "employment_type",
                   lambda: self._combo_with(["", "Full-Time", "Part-Time", "Contract"])); r += 1
        add_filter(r, "ID Type", "id_type", QLineEdit); r += 1
        add_filter(r, "ID Number", "id_number", QLineEdit); r += 1
        add_filter(r, "Country", "country", QLineEdit); r += 1
        add_filter(r, "Residency", "residency",
                   lambda: self._combo_with(["", "Citizen", "Permanent Resident", "Work Pass"])); r += 1
        add_filter(r, "Age ≥", "age_min", QLineEdit); r += 1
        add_filter(r, "Age ≤", "age_max", QLineEdit); r += 1
        fbv.addLayout(grid)

        # make filters scrollable to keep compact
        self.filter_area = QScrollArea()
        self.filter_area.setWidget(self.filter_box)
        self.filter_area.setWidgetResizable(True)
        self.filter_area.setFixedHeight(160)
        lv.addWidget(self.filter_area)

        # table
        self.emp_table = QTableWidget(0, len(COLS))
        self.emp_table.setHorizontalHeaderLabels([c[1] for c in COLS])
        self.emp_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.emp_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.emp_table.setSortingEnabled(True)
        self.emp_table.itemSelectionChanged.connect(self._show_preview)
        hdr = self.emp_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)  # auto-fit to header/contents
        hdr.setStretchLastSection(False)
        lv.addWidget(self.emp_table, 1)

        # right: read-only detail form
        right = QWidget(splitter)
        rv = QVBoxLayout(right)
        self.detail_form = self._build_readonly_form()
        rv.addWidget(self.detail_form["host"], 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        h.addWidget(splitter)
        self.tabs.addTab(host, "Employee List")
        self._reload_employees()

    def _toggle_filters(self, checked: bool):
        self.filter_area.setVisible(checked)
        self.filter_toggle.setText("Filters ▾" if checked else "Filters ▸")

    def _combo_with(self, items: list[str]) -> QComboBox:
        c = QComboBox()
        c.addItems(items)
        return c

    def _reload_employees(self):
        with SessionLocal() as s:
            rows = s.query(Employee).filter(Employee.account_id == tenant_id()).all()
        self._all_rows = rows
        self._apply_filters()

    def _apply_filters(self):
        txt = (self.quick_search.text() or "").lower().strip()

        def f_get(k):
            w = self.filters.get(k)
            if isinstance(w, QComboBox):
                return w.currentText().strip().lower()
            if isinstance(w, QLineEdit):
                return w.text().strip().lower()
            return ""

        def to_int(val):
            try:
                return int(val) if val else None
            except Exception:
                return None

        age_min = to_int(f_get("age_min"))
        age_max = to_int(f_get("age_max"))

        def keep(e: Employee) -> bool:
            # must have at least a name or a code to show
            if not ((e.code or "").strip() or (e.full_name or "").strip()):
                return False

            # quick search
            if txt:
                hay = " ".join([
                    str(e.employment_status or ""), str(e.code or ""), str(e.full_name or ""),
                    str(getattr(e, "department", "") or ""), str(e.position or ""),
                    str(e.employment_type or ""), str(e.id_type or ""), str(e.id_number or ""),
                    str(e.country or ""), str(e.residency or "")
                ]).lower()
                if txt not in hay:
                    return False

            # column filters
            for key in ["employment_status", "code", "full_name", "department", "position",
                        "employment_type", "id_type", "id_number", "country", "residency"]:
                val = f_get(key)
                if val and val not in str(getattr(e, key, "") or "").lower():
                    return False

            # age filters
            age = None
            if e.dob:
                try:
                    age = int((datetime.utcnow().date() - e.dob).days // 365.25)
                except Exception:
                    age = None
            if age_min is not None and (age is None or age < age_min):
                return False
            if age_max is not None and (age is None or age > age_max):
                return False
            return True

        rows = [e for e in getattr(self, "_all_rows", []) if keep(e)]

        # render
        self.emp_table.setSortingEnabled(False)
        self.emp_table.setRowCount(len(rows))
        for r, e in enumerate(rows):
            def put(col, val):
                self.emp_table.setItem(r, col, QTableWidgetItem(val))

            employment_status = e.employment_status or ""
            code = e.code or ""
            full_name = e.full_name or ""
            department = getattr(e, "department", "") or ""
            position = e.position or ""
            employment_type = e.employment_type or ""
            dob_txt = e.dob.strftime("%Y-%m-%d") if e.dob else ""
            age_txt = ""
            if e.dob:
                try:
                    age_txt = str(int((datetime.utcnow().date() - e.dob).days // 365.25))
                except Exception:
                    age_txt = ""
            id_type = e.id_type or ""
            id_number = e.id_number or ""
            country = e.country or ""
            residency = e.residency or ""
            join_date = e.join_date.strftime("%Y-%m-%d") if e.join_date else ""
            exit_date = e.exit_date.strftime("%Y-%m-%d") if e.exit_date else ""

            values = [employment_status, code, full_name, department, position, employment_type,
                      dob_txt, age_txt, id_type, id_number, country, residency, join_date, exit_date]
            for c, v in enumerate(values):
                put(c, v)

            # keep id for selection in vertical header
            self.emp_table.setVerticalHeaderItem(r, QTableWidgetItem(str(e.id)))

        self.emp_table.setSortingEnabled(True)

        if self.emp_table.rowCount() > 0:
            self.emp_table.selectRow(0)
        else:
            self._clear_preview()

    # read-only detail form
    def _build_readonly_form(self):
        host = QWidget()
        v = QVBoxLayout(host)
        frm = QFormLayout()
        fields = [
            "Employee Code", "Full Name", "Email", "Contact Number", "Address",
            "ID Type", "ID Number", "Gender", "Date of Birth", "Age", "Race",
            "Country", "Residency", "PR Date",
            "Employment Status", "Employment Pass", "Work Permit Number",
            "Department", "Position", "Employment Type",
            "Join Date", "Exit Date", "Holiday Group",
            "Bank", "Account Number",
            "Basic Salary", "Incentives", "Allowance", "Overtime Rate", "Part Time Rate", "Levy"
        ]
        labels = {}
        for f in fields:
            lbl = QLabel("")
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            frm.addRow(f, lbl)
            labels[f] = lbl
        v.addLayout(frm)
        v.addStretch(1)
        return {"host": host, "labels": labels}

    def _clear_preview(self):
        for lbl in self.detail_form["labels"].values():
            lbl.setText("")

    def _show_preview(self):
        sel = self.emp_table.selectedItems()
        if not sel:
            self._clear_preview()
            return
        r = self.emp_table.currentRow()
        id_item = self.emp_table.verticalHeaderItem(r)
        emp_id = int(id_item.text()) if id_item else None
        if not emp_id:
            self._clear_preview()
            return
        with SessionLocal() as s:
            e = s.get(Employee, emp_id)
        if not e:
            self._clear_preview()
            return

        L = self.detail_form["labels"]
        fmt = lambda d: d.strftime("%Y-%m-%d") if d else ""
        age_txt = ""
        if e.dob:
            try:
                age_txt = str(int((datetime.utcnow().date() - e.dob).days // 365.25))
            except Exception:
                age_txt = ""

        def put(k, v):
            if isinstance(v, str):
                L[k].setText(v)
            elif isinstance(v, float):
                L[k].setText(f"{v:.2f}")
            else:
                L[k].setText("" if v is None else str(v))

        put("Employee Code", e.code or "")
        put("Full Name", e.full_name or "")
        put("Email", e.email or "")
        put("Contact Number", e.contact_number or "")
        put("Address", e.address or "")
        put("ID Type", e.id_type or "")
        put("ID Number", e.id_number or "")
        put("Gender", e.gender or "")
        put("Date of Birth", fmt(e.dob))
        put("Age", age_txt)
        put("Race", e.race or "")
        put("Country", e.country or "")
        put("Residency", e.residency or "")
        put("PR Date", fmt(e.pr_date))
        put("Employment Status", e.employment_status or "")
        put("Employment Pass", e.employment_pass or "")
        put("Work Permit Number", e.work_permit_number or "")
        put("Department", getattr(e, "department", "") or "")
        put("Position", e.position or "")
        put("Employment Type", e.employment_type or "")
        put("Join Date", fmt(e.join_date))
        put("Exit Date", fmt(e.exit_date))
        put("Holiday Group", e.holiday_group or "")
        put("Bank", e.bank or "")
        put("Account Number", e.bank_account or "")
        put("Basic Salary", e.basic_salary or 0.0)
        put("Incentives", e.incentives or 0.0)
        put("Allowance", e.allowance or 0.0)
        put("Overtime Rate", e.overtime_rate or 0.0)
        put("Part Time Rate", e.parttime_rate or 0.0)
        put("Levy", e.levy or 0.0)

    # --- list actions ---
    def _add_employee(self):
        d = EmployeeEditor(parent=self)
        if d.exec() == QDialog.Accepted:
            self._reload_employees()

    def _edit_employee(self):
        r = self.emp_table.currentRow()
        if r < 0:
            return
        id_item = self.emp_table.verticalHeaderItem(r)
        emp_id = int(id_item.text()) if id_item else None
        if not emp_id:
            return
        d = EmployeeEditor(emp_id, parent=self)
        if d.exec() == QDialog.Accepted:
            self._reload_employees()
            for i in range(self.emp_table.rowCount()):
                ii = self.emp_table.verticalHeaderItem(i)
                if ii and ii.text() == str(emp_id):
                    self.emp_table.selectRow(i)
                    break

    def _delete_employee(self):
        r = self.emp_table.currentRow()
        if r < 0:
            return
        id_item = self.emp_table.verticalHeaderItem(r)
        emp_id = int(id_item.text()) if id_item else None
        if not emp_id:
            return
        if QMessageBox.question(self, "Delete", "Delete selected employee?") != QMessageBox.Yes:
            return
        with SessionLocal() as s:
            e = s.get(Employee, emp_id)
            if e:
                s.delete(e)
                s.commit()
        self._reload_employees()

    # ---------------- Holidays ----------------
    def _build_holidays_tab(self):
        host = QWidget(); v = QVBoxLayout(host)
        top = QHBoxLayout()
        self.h_group = QLineEdit(); self.h_group.setPlaceholderText("Holiday Group e.g. A or B")
        self.h_name = QLineEdit(); self.h_name.setPlaceholderText("Holiday Name")
        self.h_date = QLineEdit(); self.h_date.setPlaceholderText("Date DD-MM-YYYY")
        btn_add = QPushButton("Add"); btn_add.clicked.connect(self._holiday_add)
        btn_del = QPushButton("Delete Selected"); btn_del.clicked.connect(self._holiday_del)
        btn_imp = QPushButton("Import CSV"); btn_imp.clicked.connect(self._holiday_import_csv)
        btn_tpl = QPushButton("Download Template"); btn_tpl.clicked.connect(self._holiday_template)
        for w in (self.h_group, self.h_name, self.h_date, btn_add, btn_del, btn_imp, btn_tpl):
            top.addWidget(w)
        v.addLayout(top)

        self.h_table = QTableWidget(0, 3)
        self.h_table.setHorizontalHeaderLabels(["Group", "Name", "Date"])
        hdr = self.h_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(False)
        self.h_table.verticalHeader().setVisible(False)

        v.addWidget(self.h_table, 1)

        self.tabs.addTab(host, "Holidays")
        self._holiday_reload()

    def _holiday_reload(self):
        with SessionLocal() as s:
            rows = (
                s.query(Holiday)
                .filter(Holiday.account_id == tenant_id())
                .order_by(Holiday.group_code, Holiday.date)
                .all()
            )

        self.h_table.setRowCount(0)
        for r in rows:
            row = self.h_table.rowCount()
            self.h_table.insertRow(row)
            self.h_table.setItem(row, 0, QTableWidgetItem(r.group_code))
            self.h_table.setItem(row, 1, QTableWidgetItem(r.name))
            self.h_table.setItem(row, 2, QTableWidgetItem(r.date.strftime("%d-%m-%Y")))

        self.h_table.resizeColumnsToContents()

    def _holiday_add(self):
        g = self.h_group.text().strip(); n = self.h_name.text().strip(); d = self.h_date.text().strip()
        if not (g and n and d):
            QMessageBox.warning(self, "Holiday", "Fill group, name, date (DD-MM-YYYY)"); return
        try:
            day, month, year = map(int, d.split("-")); dt = date(year, month, day)
        except Exception:
            QMessageBox.warning(self, "Holiday", "Date format must be DD-MM-YYYY"); return
        with SessionLocal() as s:
            s.add(Holiday(account_id=tenant_id(), group_code=g, name=n, date=dt))
            try: s.commit()
            except Exception as ex:
                s.rollback(); QMessageBox.warning(self, "Holiday", f"Duplicate or invalid: {ex}")
        self._holiday_reload()

    def _holiday_del(self):
        rows = sorted({r.row() for r in self.h_table.selectedIndexes()}, reverse=True)
        if not rows: return
        items = []
        for r in rows:
            items.append((self.h_table.item(r, 0).text(), self.h_table.item(r, 1).text(), self.h_table.item(r, 2).text()))
        with SessionLocal() as s:
            for g, n, d in items:
                day, month, year = map(int, d.split("-")); dt = date(year, month, day)
                q = s.query(Holiday).filter(Holiday.account_id == tenant_id(), Holiday.group_code == g, Holiday.name == n, Holiday.date == dt)
                for h in q.all(): s.delete(h)
            s.commit()
        self._holiday_reload()

    def _holiday_import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Holidays CSV", "", "CSV Files (*.csv)")
        if not path: return
        imported = 0
        with open(path, newline="", encoding="utf-8-sig") as f, SessionLocal() as s:
            import csv
            rd = csv.DictReader(f)
            for r in rd:
                g = (r.get("group") or r.get("Group") or "").strip()
                n = (r.get("name") or r.get("Name") or "").strip()
                d = (r.get("date") or r.get("Date") or "").strip()
                if not (g and n and d): continue
                try:
                    day, month, year = map(int, d.split("-")); dt = date(year, month, day)
                    s.add(Holiday(account_id=tenant_id(), group_code=g, name=n, date=dt))
                    s.flush(); imported += 1
                except Exception:
                    s.rollback()
            s.commit()
        QMessageBox.information(self, "Holidays", f"Imported {imported} rows")
        self._holiday_reload()

    def _holiday_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV Template", "holiday_template.csv", "CSV Files (*.csv)")
        if not path: return
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f); wr.writerow(["group", "name", "date"]); wr.writerow(["A", "New Year", "01-01-2025"])
        QMessageBox.information(self, "Template", "Template saved.")

    # ---------------- Settings ----------------
    def _build_settings_tab(self):
        host = QWidget()
        host.setMaximumWidth(520)  # slimmer panel
        v = QVBoxLayout(host)

        # Employee ID format
        frm = QFormLayout()
        self.id_prefix = QLineEdit()
        self.zero_pad = QSpinBox()
        self.zero_pad.setRange(2, 8)
        self.zero_pad.setValue(EMP_CODE_ZPAD)
        self.id_prefix.setText(EMP_CODE_PREFIX)

        frm.addRow("Employee ID Prefix", self.id_prefix)
        frm.addRow("Zero Padding", self.zero_pad)
        self.id_preview = QLabel(f"Preview: {EMP_CODE_PREFIX}{1:0{EMP_CODE_ZPAD}d}")
        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self._apply_id_format)
        v.addLayout(frm)
        v.addWidget(self.id_preview)
        v.addWidget(btn_apply)

        v.addSpacing(8)

        # Dropdowns and leave defaults
        row1 = QHBoxLayout()
        btn_opts = QPushButton("Manage Dropdown Options")
        btn_opts.clicked.connect(lambda: DropdownOptionsDialog(self).exec())
        btn_leave = QPushButton("Manage Leave Defaults")
        btn_leave.clicked.connect(lambda: LeaveDefaultsDialog(self).exec())
        row1.addWidget(btn_opts)
        row1.addWidget(btn_leave)
        row1.addStretch(1)
        v.addLayout(row1)

        v.addSpacing(8)

        # Data Management: export/import XLSX with dropdowns
        row2 = QHBoxLayout()
        exp_btn = QPushButton("Export XLSX")
        exp_btn.clicked.connect(self._export_xlsx)
        imp_btn = QPushButton("Import XLSX")
        imp_btn.clicked.connect(self._import_xlsx)
        tmpl_btn = QPushButton("Download Template")
        tmpl_btn.clicked.connect(self._export_employees_template)  # template with dropdowns
        row2.addWidget(exp_btn)
        row2.addWidget(imp_btn)
        row2.addWidget(tmpl_btn)
        row2.addStretch(1)
        v.addLayout(row2)

        v.addStretch(1)
        self.tabs.addTab(host, "Employee Settings")

    def _export_xlsx(self):
        try:
            from openpyxl import Workbook
            from openpyxl.worksheet.datavalidation import DataValidation
            from openpyxl.utils import get_column_letter
        except Exception:
            QMessageBox.warning(self, "Export", "openpyxl not installed")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export Employees", "employees.xlsx", "Excel (*.xlsx)")
        if not path: return

        # collect dropdowns and employees
        with SessionLocal() as s:
            drop = {}
            for r in s.query(DropdownOption).all():
                drop.setdefault(r.category, []).append(r.value)
            emps = s.query(Employee).filter(Employee.account_id == tenant_id()).all()
            # add Holiday Group and Employment Status fixed lists
            groups = [g[0] for g in s.query(Holiday.group_code).distinct().all()]
        drop.setdefault("Holiday Group", groups)
        drop.setdefault("Employment Status", ["Active", "Non-Active"])

        wb = Workbook()
        ws = wb.active
        ws.title = "Employees"
        ws2 = wb.create_sheet("Dropdowns")

        # write dropdowns in rows (category in col A, values from col B rightwards)
        drow = 1
        for cat, vals in sorted(drop.items()):
            ws2.cell(drow, 1, cat)
            for i, v in enumerate(sorted(vals), start=2):
                ws2.cell(drow, i, v)
            drow += 1

        headers = [
            "Employee Code", "Full Name", "Email", "Contact Number", "Address",
            "ID Type", "ID Number", "Gender", "Date of Birth", "Race", "Country", "Residency", "PR Date",
            "Employment Status", "Employment Pass", "Work Permit Number",
            "Department", "Position", "Employment Type",
            "Join Date", "Exit Date", "Holiday Group",
            "Bank", "Account Number",
            "Incentives", "Allowance", "Overtime Rate", "Part Time Rate", "Levy", "Basic Salary"
        ]
        ws.append(headers)

        fmt = lambda d: d.strftime("%Y-%m-%d") if d else ""
        for e in emps:
            ws.append([
                e.code or "", e.full_name or "", e.email or "", e.contact_number or "", e.address or "",
                e.id_type or "", e.id_number or "", e.gender or "", fmt(e.dob), e.race or "", e.country or "",
                e.residency or "", fmt(e.pr_date),
                e.employment_status or "", e.employment_pass or "", e.work_permit_number or "",
                getattr(e, "department", "") or "", e.position or "", e.employment_type or "",
                fmt(e.join_date), fmt(e.exit_date), e.holiday_group or "",
                e.bank or "", e.bank_account or "",
                e.incentives or 0.0, e.allowance or 0.0, e.overtime_rate or 0.0, e.parttime_rate or 0.0, e.levy or 0.0,
                e.basic_salary or 0.0
            ])

        # data validations
        col_index = {h: i + 1 for i, h in enumerate(headers)}
        dv_map = {
            "ID Type": "ID Type", "Gender": "Gender", "Race": "Race", "Country": "Country",
            "Residency": "Residency", "Employment Status": "Employment Status",
            "Employment Pass": "Employment Pass", "Department": "Department",
            "Position": "Position", "Employment Type": "Employment Type",
            "Bank": "Bank", "Holiday Group": "Holiday Group",
        }
        cat_formula = {}
        for r in range(1, ws2.max_row + 1):
            cat = ws2.cell(r, 1).value
            if not cat: continue
            # dynamic width to the right based on COUNTA
            cat_formula[cat] = f'=OFFSET(Dropdowns!$B${r},0,0,1,COUNTA(Dropdowns!$B${r}:$ZZ${r}))'

        max_rows = max(1000, ws.max_row + 100)
        for header, cat in dv_map.items():
            if cat not in cat_formula or header not in col_index: continue
            c = col_index[header]
            dv = DataValidation(type="list", formula1=cat_formula[cat], allow_blank=True, showDropDown=True)
            ws.add_data_validation(dv)
            dv.ranges.add(f"{ws.cell(2, c).coordinate}:{ws.cell(max_rows, c).coordinate}")

        ws.freeze_panes = "A2"
        try:
            wb.save(path)
            QMessageBox.information(self, "Export", "Export complete.")
        except Exception as ex:
            QMessageBox.warning(self, "Export", f"Failed to save: {ex}")

    def _import_xlsx(self):
        try:
            from openpyxl import load_workbook
        except Exception:
            QMessageBox.warning(self, "Import", "openpyxl not installed")
            return

        path, _ = QFileDialog.getOpenFileName(self, "Import Employees", "", "Excel (*.xlsx)")
        if not path:
            return

        try:
            wb = load_workbook(path, data_only=True)
            ws = wb["Employees"]
        except Exception as ex:
            QMessageBox.warning(self, "Import", f"Cannot open workbook: {ex}")
            return

        # case-insensitive header map
        headers = {}
        for c in range(1, ws.max_column + 1):
            h = ws.cell(1, c).value
            if isinstance(h, str) and h.strip():
                headers[h.strip().lower()] = c
        if "full name" not in headers and "employee code" not in headers:
            QMessageBox.warning(self, "Import", "Sheet needs 'Full Name' or 'Employee Code'.")
            return

        def gv(row, name):
            c = headers.get(name.lower())
            return ws.cell(row, c).value if c else None

        def to_date(x):
            try:
                if isinstance(x, str):
                    return datetime.strptime(x.strip(), "%Y-%m-%d").date()
                if isinstance(x, date):
                    return x
            except Exception:
                return None
            return None

        def to_float(x):
            try:
                return float(x)
            except Exception:
                return 0.0

        created = updated = 0
        with SessionLocal() as s:
            # ----- allocate a monotonic "next code" cursor for this import run -----
            prefix, z = EMP_CODE_PREFIX, EMP_CODE_ZPAD
            existing_codes = [
                c for (c,) in s.query(Employee.code)
                .filter(Employee.account_id == tenant_id(),
                        Employee.code.isnot(None),
                        Employee.code.like(f"{prefix}%"))
                .all()
            ]

            def _num_tail(c):
                if not c: return None
                m = re.search(r"(\d+)$", c)
                return int(m.group(1)) if m else None

            used_nums = {n for n in (_num_tail(c) for c in existing_codes) if n is not None}
            cursor = max(used_nums) if used_nums else 0

            def next_code():
                nonlocal cursor
                cursor += 1
                # no need to loop since we only ever increment
                code = f"{prefix}{cursor:0{z}d}"
                used_nums.add(cursor)
                return code

            # ----------------------------------------------------------------------

            for r in range(2, ws.max_row + 1):
                # skip empty rows
                if not any((ws.cell(r, c).value not in (None, "", " ")) for c in range(1, ws.max_column + 1)):
                    continue

                code_raw = gv(r, "Employee Code") or gv(r, "code")
                name_raw = gv(r, "Full Name") or gv(r, "full_name")

                code = (str(code_raw).strip() if code_raw is not None else "")
                full_name = (str(name_raw).strip() if name_raw is not None else "")

                if not code and not full_name:
                    continue

                q = s.query(Employee).filter(Employee.account_id == tenant_id())
                e = None
                if code:
                    e = q.filter(Employee.code == code).first()
                if e is None and full_name:
                    e = q.filter(Employee.full_name == full_name).first()

                is_new = e is None
                if is_new:
                    if not code:
                        code = next_code()  # allocate unique code for this row
                    e = Employee(account_id=tenant_id(), code=code, full_name=full_name)
                    s.add(e)
                else:
                    if code and not (e.code or "").strip():
                        e.code = code
                    if full_name:
                        e.full_name = full_name

                e.email = str(gv(r, "Email") or gv(r, "email") or "")
                e.contact_number = str(gv(r, "Contact Number") or gv(r, "contact_number") or "")
                e.address = str(gv(r, "Address") or gv(r, "address") or "")
                e.id_type = str(gv(r, "ID Type") or gv(r, "id_type") or "")
                e.id_number = str(gv(r, "ID Number") or gv(r, "id_number") or "")
                e.gender = str(gv(r, "Gender") or gv(r, "gender") or "")
                e.dob = to_date(gv(r, "Date of Birth") or gv(r, "dob"))
                e.race = str(gv(r, "Race") or gv(r, "race") or "")
                e.country = str(gv(r, "Country") or gv(r, "country") or "")
                e.residency = str(gv(r, "Residency") or gv(r, "residency") or "")
                e.pr_date = to_date(gv(r, "PR Date") or gv(r, "pr_date"))
                e.employment_status = str(gv(r, "Employment Status") or gv(r, "employment_status") or "")
                e.employment_pass = str(gv(r, "Employment Pass") or gv(r, "employment_pass") or "")
                e.work_permit_number = str(gv(r, "Work Permit Number") or gv(r, "work_permit_number") or "")
                e.department = str(gv(r, "Department") or gv(r, "department") or "")
                e.position = str(gv(r, "Position") or gv(r, "position") or "")
                e.employment_type = str(gv(r, "Employment Type") or gv(r, "employment_type") or "")
                e.join_date = to_date(gv(r, "Join Date") or gv(r, "join_date"))
                e.exit_date = to_date(gv(r, "Exit Date") or gv(r, "exit_date"))
                e.holiday_group = str(gv(r, "Holiday Group") or gv(r, "holiday_group") or "")
                e.bank = str(gv(r, "Bank") or gv(r, "bank") or "")
                e.bank_account = str(gv(r, "Account Number") or gv(r, "bank_account") or "")

                e.incentives = to_float(gv(r, "Incentives") or gv(r, "incentives"))
                e.allowance = to_float(gv(r, "Allowance") or gv(r, "allowance"))
                e.overtime_rate = to_float(gv(r, "Overtime Rate") or gv(r, "overtime_rate"))
                e.parttime_rate = to_float(gv(r, "Part Time Rate") or gv(r, "parttime_rate"))
                e.levy = to_float(gv(r, "Levy") or gv(r, "levy"))
                b = gv(r, "Basic Salary") or gv(r, "basic_salary")
                if b is not None:
                    try:
                        e.basic_salary = float(b)
                    except Exception:
                        pass

                if is_new:
                    created += 1
                else:
                    updated += 1

            s.commit()

        try:
            self._reload_employees()
        except Exception:
            pass
        QMessageBox.information(self, "Import", f"Import complete. Created {created}, Updated {updated}.")

    def _export_employees_template(self):
        # blank template with dropdown validations derived from DropdownOption
        if Workbook is None or DataValidation is None or get_column_letter is None:
            QMessageBox.warning(self, "Template", "openpyxl is required. Install 'openpyxl'.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Employee Template", "employee_template.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "Employees"

        headers = [
            "Employee Code", "Full Name", "Email", "Contact Number", "Address",
            "ID Type", "ID Number", "Gender", "Date of Birth", "Race", "Country", "Residency", "PR Date",
            "Employment Status", "Employment Pass", "Work Permit Number",
            "Department", "Position", "Employment Type",
            "Join Date", "Exit Date", "Holiday Group",
            "Bank", "Account Number",
            "Incentives", "Allowance", "Overtime Rate", "Part Time Rate", "Levy", "Basic Salary"
        ]
        ws.append(headers)  # only header row

        # build dropdown sources
        with SessionLocal() as s:
            dropdowns = {c: [r.value for r in s.query(DropdownOption)
                             .filter(DropdownOption.category == c)
                             .order_by(DropdownOption.value).all()]
                         for c in MANAGED_CATEGORIES}
            groups = [g[0] for g in s.query(Holiday.group_code).distinct().all()]
        dropdowns["Employment Status"] = ["Active", "Non-Active"]
        dropdowns["Holiday Group"] = groups

        # write lists on sheet "Dropdowns" in columns
        lists = wb.create_sheet("Dropdowns")
        list_col_map = {}
        col_idx = 1
        for cat, vals in sorted(dropdowns.items()):
            list_col_map[cat] = col_idx
            lists.cell(row=1, column=col_idx, value=cat)
            for i, v in enumerate(vals, start=2):
                lists.cell(row=i, column=col_idx, value=v)
            col_idx += 1

        # map header names to column letters
        header_to_letter = {h: get_column_letter(i+1) for i, h in enumerate(headers)}

        # add validations
        def add_validation(header_name: str, category: str):
            if category not in list_col_map:
                return
            col = list_col_map[category]
            rng = f"Dropdowns!${get_column_letter(col)}$2:${get_column_letter(col)}$2000"
            dv = DataValidation(type="list", formula1=rng, allow_blank=True)
            ws.add_data_validation(dv)
            col_letter = header_to_letter[header_name]
            dv.add(f"{col_letter}2:{col_letter}2000")

        mapping = {
            "ID Type": "ID Type",
            "Gender": "Gender",
            "Race": "Race",
            "Country": "Country",
            "Residency": "Residency",
            "Employment Status": "Employment Status",
            "Employment Pass": "Employment Pass",
            "Department": "Department",
            "Position": "Position",
            "Employment Type": "Employment Type",
            "Bank": "Bank",
            "Holiday Group": "Holiday Group",
        }
        for hdr, cat in mapping.items():
            add_validation(hdr, cat)

        ws.freeze_panes = "A2"
        try:
            wb.save(path)
            QMessageBox.information(self, "Template", "Template saved.")
        except Exception as ex:
            QMessageBox.warning(self, "Template", f"Failed to create template: {ex}")

    def _apply_id_format(self):
        global EMP_CODE_PREFIX, EMP_CODE_ZPAD
        p = self.id_prefix.text().strip() or "EM-"
        z = int(self.zero_pad.value())
        self.id_preview.setText(f"Preview: {p}{1:0{z}d}")

        # Reformat existing employee codes for this tenant
        def extract_num(code: str):
            if not code: return None
            m = re.search(r"(\d+)$", code)
            return int(m.group(1)) if m else None

        with SessionLocal() as s:
            rows = s.query(Employee).filter(Employee.account_id == tenant_id()).order_by(Employee.id.asc()).all()
            used = set()
            next_seq = 1
            for e in rows:
                n = extract_num(e.code or "")
                if n is None or n in used:
                    while next_seq in used:
                        next_seq += 1
                    n = next_seq
                    next_seq += 1
                used.add(n)
                e.code = f"{p}{n:0{z}d}"
            s.commit()

        # update globals and persist
        EMP_CODE_PREFIX, EMP_CODE_ZPAD = p, z
        _save_code_settings(p, z)

        # refresh list immediately
        try:
            self._reload_employees()
        except Exception:
            pass

        QMessageBox.information(self, "Employee Codes", "Codes updated.")

    # ----- XLSX helpers -----
    def _need_openpyxl(self) -> bool:
        if Workbook is None or load_workbook is None or DataValidation is None:
            QMessageBox.warning(self, "XLSX", "openpyxl is required for XLSX. Install 'openpyxl' and retry.")
            return True
        return False

    def _gather_dropdowns(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        with SessionLocal() as s:
            for cat in MANAGED_CATEGORIES:
                vals = [r.value for r in s.query(DropdownOption).filter(DropdownOption.category == cat).order_by(DropdownOption.value).all()]
                out[cat] = vals or [""]
        return out

    def _next_employee_code(self, s) -> str:
        prefix, z = EMP_CODE_PREFIX, EMP_CODE_ZPAD
        existing = [r.code for r in s.query(Employee).filter(Employee.account_id == tenant_id()).all() if r.code and r.code.startswith(prefix)]
        nums = []
        for c in existing:
            m = re.search(r"(\d+)$", c)
            if m:
                try: nums.append(int(m.group(1)))
                except: pass
        nxt = (max(nums) + 1) if nums else 1
        return f"{prefix}{nxt:0{z}d}"


# ---------- Employee Editor ----------
class EmployeeEditor(QDialog):
    def __init__(self, emp_id: int | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Employee")
        self._emp_id = emp_id

        v = QVBoxLayout(self)
        self.tabs = QTabWidget(self); v.addWidget(self.tabs)

        self._build_personal_tab()
        self._build_employment_tab()
        self._build_payment_tab()
        self._build_remuneration_tab()
        self._build_schedule_tab()
        self._build_entitlement_tab()

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        v.addWidget(bb)

        if emp_id:
            self._load(emp_id)

    # --- helpers ---
    def _opts(self, category: str) -> list[str]:
        with SessionLocal() as s:
            rows = s.query(DropdownOption).filter(DropdownOption.category == category).order_by(DropdownOption.value).all()
        return [r.value for r in rows]

    def _holiday_groups(self) -> list[str]:
        with SessionLocal() as s:
            rows = s.query(Holiday.group_code).distinct().all()
        return [r[0] for r in rows]

    # --- Personal ---
    def _build_personal_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.full_name = QLineEdit()
        self.email = QLineEdit()
        self.contact = QLineEdit()
        self.address = QLineEdit()
        self.id_type = QComboBox(); self.id_type.addItems(self._opts("ID Type"))
        self.id_number = QLineEdit()
        self.gender = QComboBox(); self.gender.addItems(self._opts("Gender") or ["Male", "Female"])
        self.dob = QDateEdit(); self.dob.setCalendarPopup(True); self.dob.setDate(QDate.currentDate()); self.dob.dateChanged.connect(self._update_age)
        self.age_lbl = QLabel("-")
        self.race = QComboBox(); self.race.addItems(self._opts("Race"))
        self.country = QComboBox(); self.country.addItems(self._opts("Country"))
        self.residency = QComboBox(); self.residency.addItems(self._opts("Residency") or ["Citizen", "Permanent Resident", "Work Pass"])
        self.residency.currentTextChanged.connect(self._toggle_pr_date)
        self.pr_date = QDateEdit(); self.pr_date.setCalendarPopup(True); self.pr_date.setEnabled(False)

        f.addRow("Full Name", self.full_name)
        f.addRow("Email", self.email)
        f.addRow("Contact Number", self.contact)
        f.addRow("Address", self.address)
        f.addRow("ID Type", self.id_type)
        f.addRow("ID Number", self.id_number)
        f.addRow("Gender", self.gender)
        f.addRow("Date of Birth", self.dob)
        f.addRow("Age", self.age_lbl)
        f.addRow("Race", self.race)
        f.addRow("Country", self.country)
        f.addRow("Residency", self.residency)
        f.addRow("PR Date", self.pr_date)

        self.tabs.addTab(w, "Personal")

    def _update_age(self):
        try:
            dob = self.dob.date().toPython()
            yrs = int((date.today() - dob).days // 365.25)
            self.age_lbl.setText(str(yrs))
        except Exception:
            self.age_lbl.setText("-")

    def _toggle_pr_date(self, txt: str):
        self.pr_date.setEnabled(txt == "Permanent Resident")

    # --- Employment ---
    def _build_employment_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.employment_status = QComboBox(); self.employment_status.addItems(["Active", "Non-Active"])
        self.employment_pass = QComboBox(); self.employment_pass.addItems(self._opts("Employment Pass") or ["None", "S Pass", "Work Permit"])
        self.employment_pass.currentTextChanged.connect(self._toggle_wp)
        self.work_permit_number = QLineEdit(); self.work_permit_number.setEnabled(False)
        self.department = QComboBox(); self.department.addItems(self._opts("Department"))
        self.position = QComboBox(); self.position.addItems(self._opts("Position"))
        self.employment_type = QComboBox(); self.employment_type.addItems(self._opts("Employment Type") or ["Full-Time", "Part-Time", "Contract"])
        self.join_date = QDateEdit(); self.join_date.setCalendarPopup(True)
        self.exit_date = QDateEdit(); self.exit_date.setCalendarPopup(True); self.exit_date.setSpecialValueText("—"); self.exit_date.setDate(QDate.currentDate())
        self.exit_date.setDisplayFormat("yyyy-MM-dd")
        self.holiday_group = QComboBox(); self.holiday_group.addItems(self._holiday_groups())

        f.addRow("Employment Status", self.employment_status)
        f.addRow("Employment Pass", self.employment_pass)
        f.addRow("Work Permit Number", self.work_permit_number)
        f.addRow("Department", self.department)
        f.addRow("Position", self.position)
        f.addRow("Employment Type", self.employment_type)
        f.addRow("Join Date", self.join_date)
        f.addRow("Exit Date", self.exit_date)
        f.addRow("Holiday Group", self.holiday_group)
        self.tabs.addTab(w, "Employment")

    def _toggle_wp(self, txt: str):
        self.work_permit_number.setEnabled(txt in ("Work Permit", "S Pass"))

    # --- Payment ---
    def _build_payment_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.bank = QComboBox(); self.bank.addItems(self._opts("Bank"))
        self.bank_account = QLineEdit()
        f.addRow("Bank", self.bank)
        f.addRow("Account Number", self.bank_account)
        self.tabs.addTab(w, "Payment")

    # --- Remuneration ---
    def _build_remuneration_tab(self):
        w = QWidget(); v = QVBoxLayout(w)

        # quick fields
        grid = QGridLayout()
        self.incentives = QLineEdit("0")
        self.allowance = QLineEdit("0")
        self.ot_rate = QLineEdit("0")
        self.pt_rate = QLineEdit("0")
        self.levy = QLineEdit("0")
        self.basic_salary_lbl = QLabel("0.00")
        grid.addWidget(QLabel("Basic Salary (auto)"), 0, 0); grid.addWidget(self.basic_salary_lbl, 0, 1)
        grid.addWidget(QLabel("Incentives"), 1, 0); grid.addWidget(self.incentives, 1, 1)
        grid.addWidget(QLabel("Allowance"), 2, 0); grid.addWidget(self.allowance, 2, 1)
        grid.addWidget(QLabel("Overtime Rate"), 3, 0); grid.addWidget(self.ot_rate, 3, 1)
        grid.addWidget(QLabel("Part Time Rate"), 4, 0); grid.addWidget(self.pt_rate, 4, 1)
        grid.addWidget(QLabel("Levy"), 5, 0); grid.addWidget(self.levy, 5, 1)
        v.addLayout(grid)

        # salary history table
        self.salary_tbl = QTableWidget(0, 3)
        self.salary_tbl.setHorizontalHeaderLabels(["Amount", "Start Date", "End Date"])
        self.salary_tbl.horizontalHeader().setStretchLastSection(True)

        btn_row = QHBoxLayout()
        add = QPushButton("Add Row"); add.clicked.connect(lambda: self._row_add(self.salary_tbl, ["0.00", date.today().strftime("%Y-%m-%d"), ""]))
        rm = QPushButton("Delete Row"); rm.clicked.connect(lambda: self._row_del(self.salary_tbl))
        btn_row.addWidget(add); btn_row.addWidget(rm); btn_row.addStretch(1)

        v.addWidget(QLabel("Salary History"))
        v.addLayout(btn_row)
        v.addWidget(self.salary_tbl, 1)

        self.tabs.addTab(w, "Remuneration")

    # --- Work schedule ---
    def _build_schedule_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.ws_tbl = QTableWidget(7, 3)
        self.ws_tbl.setHorizontalHeaderLabels(["Day", "Working", "Day Type"])
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for i, d in enumerate(days):
            self.ws_tbl.setItem(i, 0, QTableWidgetItem(d))
            chk = QCheckBox(); chk.setChecked(True); self.ws_tbl.setCellWidget(i, 1, chk)
            typ = QComboBox(); typ.addItems(["Full", "Half"]); self.ws_tbl.setCellWidget(i, 2, typ)
        self.ws_tbl.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.ws_tbl)
        self.tabs.addTab(w, "Work Schedule")

    # --- Leave entitlement ---
    def _build_entitlement_tab(self):
        w = QWidget(); v = QVBoxLayout(w)

        top = QHBoxLayout()
        self.ent_leave_types = self._load_leave_types()
        self.ent_tbl = QTableWidget(50, max(1, len(self.ent_leave_types)))
        # headers
        headers = [f"Year {i}" for i in range(1, 51)]
        self.ent_tbl.setVerticalHeaderLabels(headers)
        self.ent_tbl.setHorizontalHeaderLabels(self.ent_leave_types or ["Leave"])
        for r in range(50):
            for c in range(max(1, len(self.ent_leave_types))):
                self.ent_tbl.setItem(r, c, QTableWidgetItem("0"))

        load_def = QPushButton("Load Default Leave Values"); load_def.clicked.connect(self._load_defaults_into_entitlements)
        top.addWidget(load_def); top.addStretch(1)
        v.addLayout(top)
        v.addWidget(self.ent_tbl, 1)
        self.tabs.addTab(w, "Leave Entitlement")

    def _load(self, emp_id: int):
        with SessionLocal() as s:
            e = s.get(Employee, emp_id)
            if not e:
                return
            # Personal
            self.full_name.setText(e.full_name or "")
            self.email.setText(e.email or "")
            self.contact.setText(e.contact_number or "")
            self.address.setText(e.address or "")
            self.id_type.setCurrentText(e.id_type or "")
            self.id_number.setText(e.id_number or "")
            self.gender.setCurrentText(e.gender or "")
            if e.dob:
                self.dob.setDate(QDate(e.dob.year, e.dob.month, e.dob.day))
                self._update_age()
            self.race.setCurrentText(e.race or "")
            self.country.setCurrentText(e.country or "")
            self.residency.setCurrentText(e.residency or "")
            self._toggle_pr_date(self.residency.currentText())
            if e.pr_date:
                self.pr_date.setDate(QDate(e.pr_date.year, e.pr_date.month, e.pr_date.day))

            # Employment
            self.employment_status.setCurrentText(e.employment_status or "")
            self.employment_pass.setCurrentText(e.employment_pass or "")
            self._toggle_wp(self.employment_pass.currentText())
            self.work_permit_number.setText(e.work_permit_number or "")
            self.department.setCurrentText(getattr(e, "department", "") or "")
            self.position.setCurrentText(e.position or "")
            self.employment_type.setCurrentText(e.employment_type or "")
            if e.join_date:
                self.join_date.setDate(QDate(e.join_date.year, e.join_date.month, e.join_date.day))
            if e.exit_date:
                self.exit_date.setDate(QDate(e.exit_date.year, e.exit_date.month, e.exit_date.day))
            self.holiday_group.setCurrentText(e.holiday_group or "")

            # Payment
            self.bank.setCurrentText(e.bank or "")
            self.bank_account.setText(e.bank_account or "")

            # Remuneration
            self.incentives.setText(str(e.incentives or 0))
            self.allowance.setText(str(e.allowance or 0))
            self.ot_rate.setText(str(e.overtime_rate or 0))
            self.pt_rate.setText(str(e.parttime_rate or 0))
            self.levy.setText(str(e.levy or 0))
            self.basic_salary_lbl.setText(f"{(e.basic_salary or 0.0):.2f}")

            # Salary history
            self.salary_tbl.setRowCount(0)
            sh = (
                s.query(SalaryHistory)
                .filter(SalaryHistory.employee_id == emp_id)
                .order_by(SalaryHistory.start_date.desc())
                .all()
            )
            for row in sh:
                r = self.salary_tbl.rowCount()
                self.salary_tbl.insertRow(r)
                self.salary_tbl.setItem(r, 0, QTableWidgetItem(f"{(row.amount or 0.0):.2f}"))
                self.salary_tbl.setItem(r, 1, QTableWidgetItem(row.start_date.strftime("%Y-%m-%d") if row.start_date else ""))
                self.salary_tbl.setItem(r, 2, QTableWidgetItem(row.end_date.strftime("%Y-%m-%d") if row.end_date else ""))

            # Work schedule
            ws = {d.weekday: d for d in s.query(WorkScheduleDay).filter(WorkScheduleDay.employee_id == emp_id).all()}
            for i in range(7):
                chk: QCheckBox = self.ws_tbl.cellWidget(i, 1)
                cmb: QComboBox = self.ws_tbl.cellWidget(i, 2)
                if i in ws:
                    chk.setChecked(ws[i].working)
                    cmb.setCurrentText(ws[i].day_type or "Full")
                else:
                    chk.setChecked(True)
                    cmb.setCurrentText("Full")

            # Entitlements
            ents = s.query(LeaveEntitlement).filter(LeaveEntitlement.employee_id == emp_id).all()
            types = sorted({row.leave_type for row in ents}) or getattr(self, "ent_leave_types", [])
            self.ent_leave_types = list(types) if types else ["Leave"]
            self.ent_tbl.setColumnCount(len(self.ent_leave_types))
            self.ent_tbl.setHorizontalHeaderLabels(self.ent_leave_types)
            grid = {(r.year_of_service, r.leave_type): r.days for r in ents}
            for r in range(50):
                for c, t in enumerate(self.ent_leave_types):
                    val = grid.get((r + 1, t), 0)
                    self.ent_tbl.setItem(r, c, QTableWidgetItem(str(val)))

    def _load_leave_types(self) -> list[str]:
        with SessionLocal() as s:
            rows = s.query(LeaveDefault.leave_type).distinct().all()
        return [r[0] for r in rows]

    def _load_defaults_into_entitlements(self):
        with SessionLocal() as s:
            defs = {d.leave_type: json.loads(d.table_json or "{}") for d in s.query(LeaveDefault).all()}
        if not defs:
            QMessageBox.information(self, "Leave Defaults", "No defaults defined."); return
        # ensure columns match current types
        self.ent_leave_types = list(defs.keys())
        self.ent_tbl.setColumnCount(len(self.ent_leave_types))
        self.ent_tbl.setHorizontalHeaderLabels(self.ent_leave_types)
        for r in range(50):
            for c, t in enumerate(self.ent_leave_types):
                val = defs.get(t, {}).get(str(r + 1), 0)
                self.ent_tbl.setItem(r, c, QTableWidgetItem(str(val)))

    # --- utils ---
    def _row_add(self, tbl: QTableWidget, values: list[str] | None = None):
        r = tbl.rowCount(); tbl.insertRow(r)
        vals = values or ["", "", ""]
        for c, v in enumerate(vals):
            tbl.setItem(r, c, QTableWidgetItem(v))

    def _row_del(self, tbl: QTableWidget):
        rows = sorted({i.row() for i in tbl.selectedIndexes()}, reverse=True)
        for r in rows: tbl.removeRow(r)


# ---- Dropdown Options dialog ----
class DropdownOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dropdown Options")
        v = QVBoxLayout(self)

        # category selector
        top = QHBoxLayout()
        self.cat = QComboBox(); self.cat.addItems(MANAGED_CATEGORIES)
        self.cat.currentTextChanged.connect(self._reload_values)
        btn_add_val = QPushButton("Add"); btn_add_val.clicked.connect(self._add_value)
        btn_rename_val = QPushButton("Rename"); btn_rename_val.clicked.connect(self._rename_value)
        btn_del_val = QPushButton("Delete"); btn_del_val.clicked.connect(self._delete_values)
        for w in (QLabel("Category"), self.cat, btn_add_val, btn_rename_val, btn_del_val):
            top.addWidget(w)
        v.addLayout(top)

        # values list
        self.val_list = QListWidget()
        v.addWidget(self.val_list, 1)

        self._reload_values(self.cat.currentText())

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject); bb.accepted.connect(self.accept)
        v.addWidget(bb)

    def _reload_values(self, category: str):
        self.val_list.clear()
        with SessionLocal() as s:
            rows = s.query(DropdownOption).filter(DropdownOption.category == category).order_by(DropdownOption.value).all()
        for r in rows:
            QListWidgetItem(r.value, self.val_list)

    def _add_value(self):
        cat = self.cat.currentText()
        txt, ok = self._prompt("Add value", "Value")
        if not ok or not txt.strip(): return
        with SessionLocal() as s:
            exists = s.query(DropdownOption).filter(DropdownOption.category == cat, DropdownOption.value == txt.strip()).first()
            if exists:
                QMessageBox.information(self, "Dropdown", "Value already exists."); return
            s.add(DropdownOption(account_id=tenant_id(), category=cat, value=txt.strip()))
            s.commit()
        self._reload_values(cat)

    def _rename_value(self):
        cat = self.cat.currentText()
        it = self.val_list.currentItem()
        if not it: return
        old = it.text()
        new, ok = self._prompt("Rename value", "New value", old)
        if not ok or not new.strip() or new.strip() == old: return
        with SessionLocal() as s:
            row = s.query(DropdownOption).filter(DropdownOption.category == cat, DropdownOption.value == old).first()
            if not row: return
            exists = s.query(DropdownOption).filter(DropdownOption.category == cat, DropdownOption.value == new.strip()).first()
            if exists:
                QMessageBox.information(self, "Dropdown", "Target value already exists."); return
            row.value = new.strip()
            s.commit()
        self._reload_values(cat)

    def _delete_values(self):
        cat = self.cat.currentText()
        items = self.val_list.selectedItems()
        if not items: return
        if QMessageBox.question(self, "Dropdown", f"Delete {len(items)} selected value(s)?") != QMessageBox.Yes:
            return
        vals = [i.text() for i in items]
        with SessionLocal() as s:
            for v in vals:
                q = s.query(DropdownOption).filter(DropdownOption.category == cat, DropdownOption.value == v)
                for d in q.all(): s.delete(d)
            s.commit()
        self._reload_values(cat)

    def _prompt(self, title: str, label: str, value: str = ""):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        inp = QLineEdit(value)
        fl = QFormLayout(); fl.addRow(label, inp); lay.addLayout(fl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.Accepted:
            return inp.text(), True
        return "", False


# ---- Leave Defaults dialog ----
class LeaveDefaultsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Leave Defaults")
        self.resize(720, 480)

        root = QHBoxLayout(self)

        # left: types list
        left = QVBoxLayout()
        self.type_list = QListWidget()
        self.type_list.currentItemChanged.connect(self._on_type_changed)
        left.addWidget(QLabel("Leave types"))
        left.addWidget(self.type_list, 1)

        btns = QHBoxLayout()
        add = QPushButton("Add Type"); add.clicked.connect(self._add_type)
        ren = QPushButton("Rename"); ren.clicked.connect(self._rename_type)
        rm  = QPushButton("Delete"); rm.clicked.connect(self._delete_type)
        for b in (add, ren, rm): b.setMaximumWidth(120)
        btns.addWidget(add); btns.addWidget(ren); btns.addWidget(rm); btns.addStretch(1)
        left.addLayout(btns)

        # right: config for selected type
        right = QVBoxLayout()
        top = QHBoxLayout()
        self.lbl_curr = QLabel("—")
        top.addWidget(QLabel("Selected:")); top.addWidget(self.lbl_curr); top.addStretch(1)
        right.addLayout(top)

        meta = QHBoxLayout()
        self.prorated = QComboBox(); self.prorated.addItems(["False", "True"])
        self.reset = QComboBox(); self.reset.addItems(["True", "False"])
        meta.addWidget(QLabel("Prorated?")); meta.addWidget(self.prorated)
        meta.addSpacing(16)
        meta.addWidget(QLabel("Annual reset?")); meta.addWidget(self.reset)
        meta.addStretch(1)
        right.addLayout(meta)

        self.tbl = QTableWidget(50, 2)
        self.tbl.setHorizontalHeaderLabels(["Year", "Days"])
        for i in range(50):
            self.tbl.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.tbl.setItem(i, 1, QTableWidgetItem("14"))
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        right.addWidget(self.tbl, 1)

        save_row = QHBoxLayout()
        save = QPushButton("Save"); save.clicked.connect(self._save_current)
        save.setMaximumWidth(120)
        save_row.addWidget(save); save_row.addStretch(1)
        right.addLayout(save_row)

        root.addLayout(left, 1)
        root.addLayout(right, 2)

        self._load_types()

    # --- data I/O ---
    def _load_types(self):
        self.type_list.clear()
        with SessionLocal() as s:
            rows = s.query(LeaveDefault.leave_type).distinct().order_by(LeaveDefault.leave_type).all()
        for (t,) in rows:
            self.type_list.addItem(t)
        if self.type_list.count() == 0:
            self.type_list.addItem("Annual Leave")
            self._ensure_row("Annual Leave")  # create default row
        self.type_list.setCurrentRow(0)

    def _ensure_row(self, leave_type: str):
        with SessionLocal() as s:
            row = s.query(LeaveDefault).filter(LeaveDefault.leave_type == leave_type).first()
            if not row:
                table = {str(i + 1): 14 for i in range(50)}
                s.add(LeaveDefault(
                    account_id=tenant_id(), leave_type=leave_type,
                    prorated=False, yearly_reset=True,
                    table_json=json.dumps(table)
                ))
                s.commit()

    def _on_type_changed(self, curr, prev):
        if not curr:
            return
        typ = curr.text()
        self.lbl_curr.setText(typ)
        with SessionLocal() as s:
            row = s.query(LeaveDefault).filter(LeaveDefault.leave_type == typ).first()
        if not row:
            self._ensure_row(typ)
            with SessionLocal() as s:
                row = s.query(LeaveDefault).filter(LeaveDefault.leave_type == typ).first()

        self.prorated.setCurrentText("True" if row.prorated else "False")
        self.reset.setCurrentText("True" if row.yearly_reset else "False")

        # load table_json
        try:
            data = json.loads(row.table_json or "{}")
        except Exception:
            data = {}
        for i in range(50):
            self.tbl.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.tbl.setItem(i, 1, QTableWidgetItem(str(data.get(str(i + 1), 14))))

    def _save_current(self):
        itm = self.type_list.currentItem()
        if not itm: return
        typ = itm.text()
        table = {str(i + 1): self._int_or_zero(self.tbl.item(i, 1)) for i in range(50)}
        with SessionLocal() as s:
            row = s.query(LeaveDefault).filter(LeaveDefault.leave_type == typ).first()
            if not row:
                row = LeaveDefault(account_id=tenant_id(), leave_type=typ)
                s.add(row)
            row.prorated = (self.prorated.currentText() == "True")
            row.yearly_reset = (self.reset.currentText() == "True")
            row.table_json = json.dumps(table)
            s.commit()
        QMessageBox.information(self, "Leave Defaults", f"Saved '{typ}'")

    # --- CRUD for types ---
    def _add_type(self):
        name, ok = QInputDialog.getText(self, "Add Leave Type", "Name:")
        if not ok or not name.strip(): return
        name = name.strip()
        self._ensure_row(name)
        self._load_types()
        items = self.type_list.findItems(name, Qt.MatchExactly)
        if items: self.type_list.setCurrentItem(items[0])

    def _rename_type(self):
        itm = self.type_list.currentItem()
        if not itm: return
        old = itm.text()
        new, ok = QInputDialog.getText(self, "Rename Leave Type", "New name:", text=old)
        if not ok or not new.strip() or new == old: return
        new = new.strip()
        with SessionLocal() as s:
            row = s.query(LeaveDefault).filter(LeaveDefault.leave_type == old).first()
            if row:
                row.leave_type = new
                s.commit()
        self._load_types()
        items = self.type_list.findItems(new, Qt.MatchExactly)
        if items: self.type_list.setCurrentItem(items[0])

    def _delete_type(self):
        itm = self.type_list.currentItem()
        if not itm: return
        typ = itm.text()
        if QMessageBox.question(self, "Delete", f"Delete leave type '{typ}'?") != QMessageBox.Yes:
            return
        with SessionLocal() as s:
            rows = s.query(LeaveDefault).filter(LeaveDefault.leave_type == typ).all()
            for r in rows: s.delete(r)
            s.commit()
        self._load_types()

    @staticmethod
    def _int_or_zero(item: QTableWidgetItem | None) -> int:
        try:
            return int((item.text() if item else "0").strip() or "0")
        except Exception:
            return 0


# ---------------- EmployeeEditor save/load (at end to keep file compact) ----------------
def _extract_trailing_int(txt: str | None):
    if not txt:
        return None
    m = re.search(r"(\d+)$", txt)
    return int(m.group(1)) if m else None


def _employeeeditor_save(self: EmployeeEditor):
    def f2(x):
        try: return float(x)
        except: return 0.0

    def dget(qd: QDateEdit) -> date | None:
        try: return qd.date().toPython()
        except: return None

    with SessionLocal() as s:
        if self._emp_id:
            e = s.get(Employee, self._emp_id)
        else:
            code = None
            e = Employee(account_id=tenant_id(), code=code or "")
            s.add(e)
            s.flush()
            if not code:
                e.code = EmployeeMainWidget._next_employee_code(EmployeeMainWidget, s)
            self._emp_id = e.id

        # personal
        e.full_name = self.full_name.text().strip()
        e.email = self.email.text().strip()
        e.contact_number = self.contact.text().strip()
        e.address = self.address.text().strip()
        e.id_type = self.id_type.currentText()
        e.id_number = self.id_number.text().strip()
        e.gender = self.gender.currentText()
        e.dob = dget(self.dob)
        e.race = self.race.currentText()
        e.country = self.country.currentText()
        e.residency = self.residency.currentText()
        e.pr_date = dget(self.pr_date) if self.pr_date.isEnabled() else None

        # employment
        e.employment_status = self.employment_status.currentText()
        e.employment_pass = self.employment_pass.currentText()
        e.work_permit_number = self.work_permit_number.text().strip() if self.work_permit_number.isEnabled() else ""
        e.department = self.department.currentText()
        e.position = self.position.currentText()
        e.employment_type = self.employment_type.currentText()
        e.join_date = dget(self.join_date)
        e.exit_date = dget(self.exit_date)
        e.holiday_group = self.holiday_group.currentText()

        # payment
        e.bank = self.bank.currentText()
        e.bank_account = self.bank_account.text().strip()

        # remuneration snapshot
        e.incentives = f2(self.incentives.text())
        e.allowance = f2(self.allowance.text())
        e.overtime_rate = f2(self.ot_rate.text())
        e.parttime_rate = f2(self.pt_rate.text())
        e.levy = f2(self.levy.text())

        # salary history -> compute basic from latest start_date
        s.query(SalaryHistory).filter(SalaryHistory.employee_id == e.id).delete()
        latest_amt, latest_start = 0.0, date(1900, 1, 1)
        for r in range(self.salary_tbl.rowCount()):
            try:
                amt = f2(self.salary_tbl.item(r, 0).text())
                sd_txt = (self.salary_tbl.item(r, 1).text() or "").strip()
                ed_txt = (self.salary_tbl.item(r, 2).text() or "").strip()
                sd = datetime.strptime(sd_txt, "%Y-%m-%d").date() if sd_txt else None
                ed = datetime.strptime(ed_txt, "%Y-%m-%d").date() if ed_txt else None
            except Exception:
                continue
            row = SalaryHistory(account_id=tenant_id(), employee_id=e.id, amount=amt, start_date=sd, end_date=ed)
            s.add(row)
            if sd and sd >= latest_start:
                latest_start = sd; latest_amt = amt
        e.basic_salary = latest_amt

        # work schedule
        s.query(WorkScheduleDay).filter(WorkScheduleDay.employee_id == e.id).delete()
        for i in range(7):
            chk: QCheckBox = self.ws_tbl.cellWidget(i, 1)
            cmb: QComboBox = self.ws_tbl.cellWidget(i, 2)
            s.add(WorkScheduleDay(
                account_id=tenant_id(), employee_id=e.id,
                weekday=i, working=chk.isChecked(), day_type=cmb.currentText()
            ))

        # entitlements
        s.query(LeaveEntitlement).filter(LeaveEntitlement.employee_id == e.id).delete()
        for r in range(50):
            for c in range(self.ent_tbl.columnCount()):
                hdr = self.ent_tbl.horizontalHeaderItem(c)
                t = hdr.text() if hdr else "Leave"
                val_txt = self.ent_tbl.item(r, c).text() if self.ent_tbl.item(r, c) else "0"
                try:
                    days = float(val_txt)
                except Exception:
                    days = 0.0
                s.add(LeaveEntitlement(
                    account_id=tenant_id(), employee_id=e.id,
                    year_of_service=r + 1, leave_type=t, days=days
                ))

        s.commit()
    self.accept()


# bind the save override
EmployeeEditor._save = _employeeeditor_save
