"""Reusable FastAPI dependencies."""
from collections.abc import AsyncGenerator
from datetime import datetime

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_session
from .models import User
from .schemas import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an AsyncSession."""

    async for session in get_session():
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_db_session)
) -> User:
    """Return the authenticated user from a JWT access token."""

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        token_data = TokenData(**payload)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc

    result = await session.execute(
        select(User).where(User.username == token_data.username, User.account_id == token_data.account_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")

    return user


def require_same_tenant(user: User, account_id: str) -> None:
    """Raise if the requested tenant does not match the authenticated user."""

    if user.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )


def token_payload(user: User) -> dict[str, str]:
    """Generate the JWT payload for a given user."""

    return {"username": user.username, "account_id": user.account_id, "iat": int(datetime.utcnow().timestamp())}
