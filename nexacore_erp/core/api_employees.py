from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests
from nexacore_erp.services.api_client import load_default_credentials


class EmployeeAPIError(Exception):
    """Raised for employee API problems (4xx/5xx, bad payloads, etc.)."""


def _get_base() -> str:
    """
    Base URL for the backend.

    Priority (matches services.api_client):
      1) NEXACORE_API_BASE_URL env var
      2) legacy NEXACORE_API_BASE env var
      3) nexacore_erp/config.json -> {"api_base_url": "..."}
      4) fallback to http://127.0.0.1:8000
    """
    env_url = os.getenv("NEXACORE_API_BASE_URL") or os.getenv("NEXACORE_API_BASE")
    if env_url:
        return env_url.rstrip("/")

    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            import json

            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg_url = data.get("api_base_url")
            if cfg_url:
                return str(cfg_url).rstrip("/")
        except Exception:
            # Fall back to localhost if config is malformed
            pass

    return "http://127.0.0.1:8000"


_token_cache: Optional[str] = None


def _get_token() -> Optional[str]:
    """
    Access token for Authorization header.

    Priority:
      1) NEXACORE_API_TOKEN env var
      2) token cached from an earlier login in this process
      3) api_access_token in config.json
      4) If username/password/account_id are configured, perform /auth/login to
         fetch a token and cache it.
    """
    global _token_cache

    token = os.getenv("NEXACORE_API_TOKEN")
    if token:
        _token_cache = token
        return token

    if _token_cache:
        return _token_cache

    # Allow dropping the /auth/login response into api_token.json to avoid
    # editing config.json for secrets. Structure:
    # {
    #   "access_token": "...",
    #   "token_type": "bearer",
    #   "expires_at": "2025-11-19T13:15:24.193355"
    # }
    token_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api_token.json")
    if os.path.exists(token_path):
        try:
            import json

            with open(token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("access_token"):
                _token_cache = str(data.get("access_token"))
                return _token_cache
        except Exception:
            # Ignore malformed token file and continue
            pass

    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            import json

            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg_token = data.get("api_access_token")
            if cfg_token:
                _token_cache = str(cfg_token)
                return _token_cache
        except Exception:
            pass

    # As a convenience, fall back to logging in with stored credentials.
    creds = load_default_credentials()
    if creds.get("username") and creds.get("password") and creds.get("account_id"):
        try:
            resp = _session.post(
                f"{_get_base()}/auth/login",
                json={
                    "username": creds.get("username"),
                    "password": creds.get("password"),
                    "account_id": creds.get("account_id"),
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            _token_cache = data.get("access_token") or None
            if _token_cache:
                return _token_cache
        except requests.HTTPError as exc:  # pragma: no cover - defensive
            raise EmployeeAPIError(
                f"Login failed against {_get_base()}/auth/login: {exc.response.text}"
            ) from exc
        except requests.RequestException as exc:  # pragma: no cover - network issue
            raise EmployeeAPIError(f"Unable to reach backend for login: {exc}") from exc

    return None


def _headers() -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    token = _get_token()
    if token:
        # IMPORTANT: backend expects the 'Bearer ' prefix
        headers["Authorization"] = f"Bearer {token}"
    else:
        raise EmployeeAPIError(
            "No API token configured. Add NEXACORE_API_TOKEN to your env, "
            "drop the /auth/login response into nexacore_erp/api_token.json, "
            "or fill api_access_token/api_username/api_password/api_account_id "
            "in nexacore_erp/config.json so we can authenticate."
        )
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


# ---------- Thin OO wrapper expected by the Qt UI ----------


class APIEmployees:
    """
    Qt UI expects an `api_employees` object with methods.

    This wraps the stateless helper functions above so the existing UI import
    (``from ....core.api_employees import api_employees``) keeps working.
    """

    def list_employees(self) -> List[Dict[str, Any]]:
        return list_employees()

    def get_employee(self, emp_id: int | str) -> Dict[str, Any]:
        resp = _request("GET", f"/employees/{emp_id}")
        return resp.json()

    def create_employee(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return create_employee(payload)

    def update_employee(self, emp_id: int | str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return update_employee(emp_id, payload)

    def delete_employee(self, emp_id: int | str) -> None:
        delete_employee(emp_id)

    # The desktop UI exposes import/export buttons; the FastAPI backend does not
    # yet provide endpoints. Provide clear guidance rather than crashing.
    def export_employees_xlsx(self, path: str) -> None:  # pragma: no cover - UI hook
        raise EmployeeAPIError(
            "Export to Excel is not available via the cloud API yet."
        )

    def import_employees_xlsx(self, path: str) -> Dict[str, Any]:  # pragma: no cover - UI hook
        raise EmployeeAPIError(
            "Import from Excel is not available via the cloud API yet."
        )


# Keep the name that the Qt module imports
api_employees = APIEmployees()
