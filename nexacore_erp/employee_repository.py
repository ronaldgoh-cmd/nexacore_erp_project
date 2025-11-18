"""
Employee repository – thin wrapper that lets the Qt UI call simple
functions while the real work is done via the HTTP backend.
"""

from typing import Any, Dict, List
import asyncio

from nexacore_erp.services.api_client import APIClient, AuthError, load_default_credentials
from nexacore_erp.services.employees_service import (
    fetch_all_employees,
    create_employee,
)


def _ensure_authenticated() -> None:
    """
    Make sure the shared API client has a token before the UI calls API helpers.

    Priority for credentials:
    1. Environment variables (NEXACORE_API_TOKEN or username/password/account_id)
    2. nexacore_erp/config.json values (api_access_token OR api_username/api_password/api_account_id)
    """

    client = APIClient.get()
    # Ensure we are pointing to the configured host (e.g., 34.87.155.9) instead
    # of the localhost fallback.
    client.refresh_base_url()
    if client.has_token():
        return

    creds = load_default_credentials()

    if creds.get("access_token"):
        client.set_token(creds["access_token"] or "", expires_at=creds.get("expires_at"))
        return

    # Fall back to performing a login using stored credentials
    missing = [k for k in ("username", "password", "account_id") if not creds.get(k)]
    if missing:
        raise AuthError(
            "Missing API credentials. Set environment variables (NEXACORE_API_USERNAME/"
            "PASSWORD/ACCOUNT_ID or NEXACORE_API_TOKEN), drop your /auth/login JSON into "
            "nexacore_erp/api_token.json, or fill api_username/api_password/api_account_id "
            "in nexacore_erp/config.json."
        )

    asyncio.run(
        client.login(
            username=creds["username"] or "",
            password=creds["password"] or "",
            account_id=creds["account_id"] or "",
        )
    )


def get_all_employees() -> List[Dict[str, Any]]:
    """
    Return a list of employees from the backend API.

    Qt code can call this synchronously.
    """
    _ensure_authenticated()
    return asyncio.run(fetch_all_employees())


def add_employee(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new employee via the backend API.

    'payload' must match the backend EmployeeCreate schema.
    """
    _ensure_authenticated()
    return asyncio.run(create_employee(payload))
