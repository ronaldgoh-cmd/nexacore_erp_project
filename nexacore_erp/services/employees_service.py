"""
Employee service that talks to the NexaCore backend via HTTP,
instead of using the local SQLite database.

Later, your Qt UI code will import and call these functions instead
of opening a SQLAlchemy SessionLocal().
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .api_client import APIClient, APIError, AuthError


# -----------------------------
# High-level helpers
# -----------------------------


async def ensure_logged_in(
    username: str,
    password: str,
    account_id: str,
) -> None:
    """
    Make sure APIClient has a valid JWT token.

    Typical use:
        await ensure_logged_in("admin1", "yourpass", "default")
    """
    client = APIClient.get()

    # If you later add proper token expiry handling, you can add checks here.
    # For now, we simply call login() and let the backend validate credentials.
    try:
        await client.login(username=username, password=password, account_id=account_id)
    except AuthError as exc:
        # You can catch this in the UI and show a message box.
        raise
    except APIError as exc:
        # Any other backend issue.
        raise


async def fetch_all_employees() -> List[Dict[str, Any]]:
    """
    Get all employees for the current tenant from the backend.

    NOTE: Assumes ensure_logged_in() was called earlier in the app lifecycle.
    """
    client = APIClient.get()
    return await client.list_employees()


async def create_employee(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new employee via the backend.

    'payload' should match your EmployeeCreate schema on the backend.
    For example:
        {
            "employee_code": "E001",
            "full_name": "John Doe",
            "department": "Kitchen",
            ...
        }
    """
    client = APIClient.get()
    return await client.create_employee(payload)

