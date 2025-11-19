"""Reusable FastAPI dependencies."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Dict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_session
from .models import User
from .schemas import TokenData

# Load settings once
settings = get_settings()

# Use simple Bearer auth instead of OAuth2 password flow
bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an AsyncSession."""
    async for session in get_session():
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Return the authenticated user from a JWT access token
    taken from the Authorization: Bearer <token> header.
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = credentials.credentials

    try:
        token_data = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc

    result = await session.execute(
        select(User).where(
            User.username == token_data.username,
            User.account_id == token_data.account_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive or missing user",
        )

    return user


def require_same_tenant(user: User, account_id: str) -> None:
    """Raise if the requested tenant does not match the authenticated user."""
    if user.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )


def require_admin(user: User) -> None:
    """Ensure the current user has the admin role."""

    if getattr(user, "role", "user") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )


def decode_access_token(token: str) -> TokenData:
    """Decode a JWT access token and return its payload."""

    payload: Dict[str, Any] = jwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
    )
    return TokenData(**payload)


def token_payload(user: User) -> dict[str, Any]:
    """
    Generate the JWT payload for a given user.

    auth.login() will add "exp" on top of this.
    """
    return {
        "username": user.username,
        "account_id": user.account_id,
        "iat": int(datetime.utcnow().timestamp()),
    }
