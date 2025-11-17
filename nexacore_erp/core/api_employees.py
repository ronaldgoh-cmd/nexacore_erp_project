from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


class EmployeeAPIError(Exception):
    """Raised for employee API problems (4xx/5xx, bad payloads, etc.)."""


def _get_base() -> str:
    """
    Base URL for the backend.

    Read from NEXACORE_API_BASE, defaulting to local dev.
    Examples:
      - http://34.87.155.9:8000
      - http://127.0.0.1:8000
    """
    base = os.getenv("NEXACORE_API_BASE", "http://127.0.0.1:8000")
    return base.rstrip("/")  # avoid double slashes


def _get_token() -> Optional[str]:
    """
    Access token for Authorization header.

    Read from NEXACORE_API_TOKEN and used as:
      Authorization: Bearer <token>
    """
    return os.getenv("NEXACORE_API_TOKEN")


def _headers() -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    token = _get_token()
    if token:
        # IMPORTANT: backend expects the 'Bearer ' prefix
        headers["Authorization"] = f"Bearer {token}"
    return headers


_session = requests.Session()


def _request(method: str, path: str, **kwargs) -> requests.Response:
    """
    Internal helper to send a request and handle common errors.
    """
    url = f"{_get_base()}{path}"
    user_headers = kwargs.pop("headers", {})
    merged_headers = {**_headers(), **user_headers}

    resp = _session.request(
        method,
        url,
        headers=merged_headers,
        timeout=30,
        **kwargs,
    )

    # Give a very explicit message for auth failures
    if resp.status_code == 401:
        raise EmployeeAPIError(
            f"401 Unauthorized calling {url}.\n\n"
            "The backend rejected our credentials.\n"
            "- Make sure NEXACORE_API_TOKEN is set to the 'access_token' "
            "you got from /auth/login in Swagger (WITHOUT the word 'Bearer').\n"
            "- Also confirm that the token hasn't expired and that the user "
            "has permission to access /employees/."
        )

    resp.raise_for_status()
    return resp


# ---------- Public functions used by the UI & migration script ----------


def list_employees() -> List[Dict[str, Any]]:
    """
    GET /employees/

    Returns a list of employees as plain dicts.
    Works whether the backend returns:
      - a plain list: [ {...}, {...} ]
      - a paginated object: { "items": [ {...}, ... ], ... }
    """
    resp = _request("GET", "/employees/")
    data = resp.json()
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, list):
        return data
    raise EmployeeAPIError(f"Unexpected employees payload: {data!r}")


def create_employee(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /employees/
    """
    resp = _request("POST", "/employees/", json=payload)
    return resp.json()


def update_employee(emp_id: int | str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /employees/{id}
    """
    resp = _request("PUT", f"/employees/{emp_id}", json=payload)
    return resp.json()


def delete_employee(emp_id: int | str) -> None:
    """
    DELETE /employees/{id}
    """
    _request("DELETE", f"/employees/{emp_id}")
