"""
HTTP API client for talking to the NexaCore backend.

Usage pattern (later you will call this from your Qt code):

    from nexacore_erp.services.api_client import get_api_client

    client = get_api_client()

    # login
    await client.login(username="admin1", password="yourpass", account_id="default")

    # list employees
    employees = await client.list_employees()
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


# -----------------------------
# Configuration helpers
# -----------------------------


def _load_base_url() -> str:
    """
    Determine the backend base URL.

    Priority:
    1. Environment variable NEXACORE_API_BASE_URL
    2. nexacore_erp/config.json -> {"api_base_url": "..."}
    3. Default: http://127.0.0.1:8000
    """
    env_url = os.getenv("NEXACORE_API_BASE_URL")
    if env_url:
        return env_url.rstrip("/")

    # config.json lives one level above this file (inside nexacore_erp)
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            cfg_url = data.get("api_base_url")
            if cfg_url:
                return cfg_url.rstrip("/")
        except Exception:
            # If config is broken, just fall back
            pass

    # Fallback to local dev
    return "http://127.0.0.1:8000"


def _load_default_credentials() -> Dict[str, Optional[str]]:
    """
    Load default credentials from environment or config.json.

    Environment variables win over config.json so you can override without
    editing files:
      - NEXACORE_API_USERNAME
      - NEXACORE_API_PASSWORD
      - NEXACORE_API_ACCOUNT_ID
      - NEXACORE_API_TOKEN (optional shortcut to skip login)
      - NEXACORE_API_TOKEN_EXPIRES_AT (optional metadata when providing a token)
    """

    env_credentials = {
        "username": os.getenv("NEXACORE_API_USERNAME"),
        "password": os.getenv("NEXACORE_API_PASSWORD"),
        "account_id": os.getenv("NEXACORE_API_ACCOUNT_ID"),
        "access_token": os.getenv("NEXACORE_API_TOKEN"),
        "expires_at": os.getenv("NEXACORE_API_TOKEN_EXPIRES_AT"),
    }

    if any(env_credentials.values()):
        return env_credentials

    config_path = Path(__file__).resolve().parent.parent / "config.json"
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "username": data.get("api_username"),
                "password": data.get("api_password"),
                "account_id": data.get("api_account_id"),
                "access_token": data.get("api_access_token"),
                "expires_at": data.get("api_token_expires_at"),
            }
        except Exception:
            pass

    return {"username": None, "password": None, "account_id": None, "access_token": None, "expires_at": None}


def load_default_credentials() -> Dict[str, Optional[str]]:
    """
    Public wrapper so other modules (e.g., employee_repository) can read
    defaults without importing the private helper directly.
    """

    return _load_default_credentials()


# -----------------------------
# Error types
# -----------------------------


class APIError(Exception):
    """Generic API error."""


class AuthError(APIError):
    """Authentication / authorization error."""


@dataclass
class TokenInfo:
    access_token: str
    expires_at: Optional[str] = None  # ISO8601 string from backend


# -----------------------------
# Main API client
# -----------------------------


class APIClient:
    """
    Reusable HTTP client for the NexaCore backend.

    Use APIClient.get() to obtain a singleton instance.
    """

    _instance: Optional["APIClient"] = None

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url: str = (base_url or _load_base_url()).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[TokenInfo] = None

    def refresh_base_url(self) -> None:
        """
        Re-read the configured base URL and rebuild the HTTP client if it
        changes. This prevents accidentally calling http://127.0.0.1 when the
        production IP is set in config.json or env vars.
        """

        new_base = _load_base_url().rstrip("/")
        if new_base == self.base_url:
            return

        self.base_url = new_base

        # If the HTTP client was already created with the old base URL, close
        # it so the next request uses the correct host.
        if self._client is not None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule close without blocking if we're inside the Qt
                    # event loop.
                    loop.create_task(self._client.aclose())
                else:
                    loop.run_until_complete(self._client.aclose())
            except RuntimeError:
                # No running loop; fall back to a new event loop.
                asyncio.run(self._client.aclose())
            finally:
                self._client = None

    # ---------- Singleton helper ----------

    @classmethod
    def get(cls) -> "APIClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------- Internal helpers ----------

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=10.0,  # seconds
            )
        return self._client

    def _get_auth_header(self) -> Dict[str, str]:
        """
        Return Authorization header; raise if not logged in.
        """
        if not self._token or not self._token.access_token:
            raise AuthError("Not logged in - call login() first")

        return {"Authorization": f"Bearer {self._token.access_token}"}

    def has_token(self) -> bool:
        return bool(self._token and self._token.access_token)

    def set_token(self, access_token: str, expires_at: Optional[str] = None) -> None:
        """
        Manually set a token (useful when you already have a JWT issued by the backend).
        """

        if not access_token:
            raise ValueError("access_token cannot be empty")

        self._token = TokenInfo(access_token=access_token, expires_at=expires_at)

    # ---------- Public methods ----------

    async def close(self) -> None:
        """
        Close underlying HTTP connection pool.

        Call this once on app shutdown (optional but recommended).
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---- Health check ----

    async def health(self) -> Dict[str, Any]:
        """
        Call /health on the backend.
        """
        client = await self._ensure_client()
        resp = await client.get("/health")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise APIError(f"/health failed: {exc}") from exc
        return resp.json()

    # ---- Authentication ----

    async def login(self, username: str, password: str, account_id: str) -> TokenInfo:
        """
        Call /auth/login and store the JWT for subsequent requests.

        NOTE: backend expects the same payload as UserCreate:
            { "username": "...", "password": "...", "account_id": "..." }
        """
        client = await self._ensure_client()
        payload = {
            "username": username,
            "password": password,
            "account_id": account_id,
            # email is optional in backend's UserCreate; not needed for login
        }

        resp = await client.post("/auth/login", json=payload)
        if resp.status_code == 401:
            raise AuthError("Invalid username, password, or account")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise APIError(f"/auth/login failed: {exc.response.text}") from exc

        data = resp.json()
        token = TokenInfo(
            access_token=data.get("access_token", ""),
            expires_at=data.get("expires_at"),
        )
        if not token.access_token:
            raise APIError("Login did not return access_token")

        self._token = token
        return token

    async def register_user(
        self,
        username: str,
        password: str,
        account_id: str,
        email: str = "",
    ) -> Dict[str, Any]:
        """
        Call /auth/register to create a user.

        This is mainly for testing; in production you might have a separate admin flow.
        """
        client = await self._ensure_client()
        payload = {
            "username": username,
            "password": password,
            "account_id": account_id,
            "email": email,
        }

        resp = await client.post("/auth/register", json=payload)
        if resp.status_code == 400:
            # Backend sends e.g. {"detail": "Username already exists"}
            detail = resp.json().get("detail", "Bad request")
            raise APIError(f"/auth/register failed: {detail}")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise APIError(f"/auth/register failed: {exc.response.text}") from exc

        return resp.json()

    # ---- Employees ----

    async def list_employees(self) -> List[Dict[str, Any]]:
        """
        GET /employees/ using the stored JWT.

        Returns: list of employee dicts from the backend.
        """
        client = await self._ensure_client()
        headers = self._get_auth_header()

        resp = await client.get("/employees/", headers=headers)
        if resp.status_code == 401:
            raise AuthError("Unauthorized when listing employees (token missing/expired)")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise APIError(f"/employees/ failed: {exc.response.text}") from exc

        data = resp.json()
        if not isinstance(data, list):
            raise APIError("Expected a list of employees from /employees/")
        return data

    async def create_employee(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /employees/ to create a new employee.

        employee_data should match the EmployeeCreate schema on the backend.
        """
        client = await self._ensure_client()
        headers = self._get_auth_header()

        resp = await client.post("/employees/", json=employee_data, headers=headers)
        if resp.status_code == 401:
            raise AuthError("Unauthorized when creating employee")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise APIError(f"POST /employees/ failed: {exc.response.text}") from exc

        return resp.json()


# -----------------------------
# Convenience wrapper for Qt UI
# -----------------------------


def get_api_client() -> APIClient:
    """
    Helper used by the Qt UI:

        from nexacore_erp.services.api_client import get_api_client

        client = get_api_client()
        await client.login(...)

    Returns the process-wide singleton APIClient.
    """
    return APIClient.get()


# -----------------------------
# Simple CLI test hook
# -----------------------------


async def _demo() -> None:
    """
    Quick manual test:
    - checks /health
    - (optionally) logs in and lists employees

    Run from project root:
        python -m nexacore_erp.services.api_client
    """
    client = APIClient.get()

    print(f"Base URL: {client.base_url}")
    print("Checking /health ...")
    print(await client.health())

    # Uncomment and adjust these lines once you have a real user created
    # token = await client.login(username="admin1", password="yourpass", account_id="default")
    # print("Logged in, token starts with:", token.access_token[:16])
    # employees = await client.list_employees()
    # print("Employees:", employees)

    await client.close()


if __name__ == "__main__":
    asyncio.run(_demo())
