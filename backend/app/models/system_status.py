"""System status flag for maintenance windows."""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SystemStatus(Base):
    """Represents the global maintenance toggle for the platform."""

    __tablename__ = "system_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str] = mapped_column(
        String,
        default="NexaCore ERP is updating. Please try again shortly.",
    )
