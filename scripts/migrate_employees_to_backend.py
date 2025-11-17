from __future__ import annotations

"""
One-off migration: read employees from OLD local DB and push them
into the backend via api_employees.

Current strategy:
- Migrate "flat" employee fields + basic_salary.
- DO NOT rely on backend list_employees() (GET /employees/ is 500).
- We assume backend currently has no employees; if you rerun this
  later, duplicates will fail on the backend side, but the script
  will keep going.
"""

from datetime import date
from typing import List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1) OLD DB URL (change this if needed)
OLD_DB_URL = "sqlite:///C:/Users/rev-e/Desktop/nexacore_erp_project/nexacore_erp/database/nexacore_employeemanagement.db"

engine_old = create_engine(OLD_DB_URL, future=True)
SessionOld = sessionmaker(bind=engine_old, autoflush=False, autocommit=False)

import os
import sys
from pathlib import Path

# --- make sure project root is on sys.path ---
BASE_DIR = Path(__file__).resolve().parents[1]  # C:/Users/.../nexacore_erp_project
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from nexacore_erp.modules.employee_management.models import (
    Employee,
    SalaryHistory,
    Holiday,
    DropdownOption,
    LeaveDefault,
    WorkScheduleDay,
    LeaveEntitlement,
)

from nexacore_erp.core import api_employees


def migrate():
    # IMPORTANT: we do NOT call api_employees.list_employees() here,
    # because GET /employees/ is currently returning 500 from backend.
    # We just try to create everything. If backend has unique constraints
    # and you re-run this script, duplicates will fail per-employee but
    # the loop continues.

    with SessionOld() as s:
        employees: List[Employee] = s.query(Employee).all()
        print(f"Found {len(employees)} employees in OLD DB")

        for e in employees:
            code = (e.code or "").strip()
            if not code:
                # You can choose to generate a code instead of skipping.
                print("Skipping employee with empty code (id=%r)" % (e.id,))
                continue

            # ----- basic helpers -----
            def _d(d: date | None):
                return d.isoformat() if d and d > date(1900, 1, 1) else None

            # ----- base payload (flat fields only for now) -----
            payload = {
                "code": code,
                "full_name": e.full_name or "",
                # email handled separately below
                "contact_number": e.contact_number or "",
                "address": e.address or "",
                "id_type": e.id_type or "",
                "id_number": e.id_number or "",
                "gender": e.gender or "",
                "dob": _d(e.dob),
                "race": e.race or "",
                "country": e.country or "",
                "residency": e.residency or "",
                "pr_date": _d(e.pr_date),
                "employment_status": e.employment_status or "",
                "employment_pass": e.employment_pass or "",
                "work_permit_number": e.work_permit_number or "",
                "department": getattr(e, "department", "") or "",
                "position": e.position or "",
                "employment_type": e.employment_type or "",
                "join_date": _d(e.join_date),
                "exit_date": _d(e.exit_date),
                "holiday_group": e.holiday_group or "",
                "bank": e.bank or "",
                "bank_account": e.bank_account or "",
                "incentives": float(e.incentives or 0.0),
                "allowance": float(e.allowance or 0.0),
                "overtime_rate": float(e.overtime_rate or 0.0),
                "parttime_rate": float(e.parttime_rate or 0.0),
                "levy": float(e.levy or 0.0),
            }

            # ----- handle email safely: only send if it looks valid -----
            raw_email = (e.email or "").strip() if hasattr(e, "email") else ""
            if raw_email and "@" in raw_email:
                payload["email"] = raw_email
            # otherwise omit email field from payload entirely

            # ----- compute basic_salary from salary history -----
            sh_rows = (
                s.query(SalaryHistory)
                .filter(SalaryHistory.employee_id == e.id)
                .order_by(SalaryHistory.start_date.asc())
                .all()
            )
            latest_amt, latest_start = 0.0, date(1900, 1, 1)
            for row in sh_rows:
                sd = row.start_date
                if sd and sd >= latest_start:
                    latest_start = sd
                    latest_amt = float(row.amount or 0.0)

            payload["basic_salary"] = latest_amt

            # NOTE: We intentionally DO NOT send:
            #   - salary_history
            #   - work_schedule
            #   - entitlements
            # to avoid backend 500s from nested structures.
            # We can migrate them later with a second script if needed.

            # ----- create on backend -----
            try:
                api_employees.create_employee(payload)
                print(f"OK: {code}")
            except Exception as ex:
                resp = getattr(ex, "response", None)
                print(f"\nFAILED to migrate {code}: {ex}")
                if resp is not None:
                    try:
                        print("Status:", resp.status_code)
                        print("Response text:", resp.text)
                    except Exception:
                        pass
                print("-" * 60)


if __name__ == "__main__":
    migrate()
