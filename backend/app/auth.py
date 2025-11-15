"""Authentication routes and helpers."""
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_session
from .dependencies import token_payload
from .models import User
from .schemas import Token, UserCreate, UserRead, compute_expiry

router = APIRouter(prefix="/auth", tags=["auth"])

# Use PBKDF2-SHA256 instead of bcrypt to avoid bcrypt backend issues
password_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plain password against the stored hash."""
    return password_context.verify(password, password_hash)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate, session: AsyncSession = Depends(get_session)
) -> User:
    """Create a tenant-scoped user account."""

    # Ensure username is unique within the whole system
    existing = await session.execute(
        select(User).where(User.username == payload.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    user = User(
        username=payload.username,
        account_id=payload.account_id,
        email=payload.email or "",
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    payload: UserCreate, session: AsyncSession = Depends(get_session)
) -> Token:
    """Authenticate a user and return a JWT access token."""

    settings = get_settings()
    result = await session.execute(
        select(User).where(
            User.username == payload.username,
            User.account_id == payload.account_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    expires_at = compute_expiry(settings.access_token_expires_minutes)
    encoded = jwt.encode(
        {**token_payload(user), "exp": int(expires_at.timestamp())},
        settings.secret_key,
        algorithm="HS256",
    )
    return Token(access_token=encoded, expires_at=expires_at)
