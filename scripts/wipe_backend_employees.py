from __future__ import annotations

"""
Danger: this script deletes ALL employees for the current account
on the backend API.

Make sure:
  - NEXACORE_API_BASE is set, e.g. http://34.87.155.9:8000
  - NEXACORE_API_TOKEN is a valid Bearer token for the right account
"""

import os
import sys
from pathlib import Path

# --- ensure project root on sys.path ---
BASE_DIR = Path(__file__).resolve().parents[1]  # .../nexacore_erp_project
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from nexacore_erp.core import api_employees  # uses same base URL + token


def wipe_employees():
    # 1) List all employees visible for this token/account
    employees = api_employees.list_employees()
    print(f"Found {len(employees)} employees on backend for this account.")

    if not employees:
        print("Nothing to delete.")
        return

    # 2) Delete one by one
    for e in employees:
        emp_id = e.get("id")
        code = e.get("code")
        if emp_id is None:
            print(f"SKIP: employee without id (code={code!r})")
            continue

        try:
            api_employees.delete_employee(emp_id)
            print(f"Deleted employee id={emp_id}, code={code}")
        except Exception as ex:
            resp = getattr(ex, "response", None)
            print(f"\nFAILED to delete id={emp_id}, code={code}: {ex}")
            if resp is not None:
                try:
                    print("Status:", resp.status_code)
                    print("Response text:", resp.text)
                except Exception:
                    pass
            print("-" * 60)


if __name__ == "__main__":
    wipe_employees()
