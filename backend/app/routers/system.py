"""System-level endpoints such as maintenance mode toggles."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_user, get_db_session, require_admin
from ..models import SystemStatus, User
from ..schemas import SystemStatusRead, SystemStatusUpdate

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusRead)
async def get_status(session: AsyncSession = Depends(get_db_session)) -> SystemStatus:
    """Return the current maintenance toggle."""

    result = await session.execute(select(SystemStatus).limit(1))
    status_row = result.scalar_one_or_none()
    if status_row is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System status missing")
    return status_row


@router.put("/maintenance", response_model=SystemStatusRead)
async def update_maintenance(
    payload: SystemStatusUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SystemStatus:
    """Enable or disable maintenance mode (admin only)."""

    require_admin(current_user)

    result = await session.execute(select(SystemStatus).limit(1))
    status_row = result.scalar_one_or_none()
    if status_row is None:
        status_row = SystemStatus()
        session.add(status_row)
        await session.flush()

    status_row.maintenance_mode = payload.maintenance_mode
    if payload.message is not None:
        status_row.message = payload.message

    await session.commit()
    await session.refresh(status_row)
    return status_row
