"""
Employee repository – thin wrapper that lets the Qt UI call simple
functions while the real work is done via the HTTP backend.
"""

from typing import Any, Dict, List
import asyncio

from nexacore_erp.services.employees_service import (
    fetch_all_employees,
    create_employee,
)


def get_all_employees() -> List[Dict[str, Any]]:
    """
    Return a list of employees from the backend API.

    Qt code can call this synchronously.
    """
    return asyncio.run(fetch_all_employees())


def add_employee(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new employee via the backend API.

    'payload' must match the backend EmployeeCreate schema.
    """
    return asyncio.run(create_employee(payload))
