"""Pydantic schemas used across the backend API."""
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, EmailStr


class Token(BaseModel):
    """JWT response payload."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class TokenData(BaseModel):
    """Information encoded into JWTs."""

    username: str
    account_id: str


class UserLogin(BaseModel):
    """Credentials supplied during login."""

    username: str
    password: str
    account_id: str


class UserCreate(UserLogin):
    """Payload for user registration."""

    email: EmailStr | None = None


class UserRead(BaseModel):
    """Public representation of a user."""

    id: int
    username: str
    account_id: str
    email: EmailStr | None = Field(default=None)

    class Config:
        from_attributes = True


class EmployeeBase(BaseModel):
    """Shared properties for employee operations."""

    code: str
    full_name: str
    email: EmailStr | None = None
    contact_number: str | None = None
    position: str | None = None
    department: str | None = None
    join_date: date | None = None
    exit_date: date | None = None
    basic_salary: float | None = None


class EmployeeCreate(EmployeeBase):
    """Employee payload for creation."""


class EmployeeRead(EmployeeBase):
    """Employee representation returned by the API."""

    id: int

    class Config:
        from_attributes = True


def compute_expiry(minutes: int) -> datetime:
    """Return an absolute expiration timestamp for tokens."""

    return datetime.utcnow() + timedelta(minutes=minutes)
