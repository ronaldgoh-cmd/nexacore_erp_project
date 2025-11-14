"""Employee endpoints for the FastAPI backend."""
from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_user, get_db_session, require_same_tenant
from ..models import Employee, User
from ..schemas import EmployeeCreate, EmployeeRead

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/", response_model=list[EmployeeRead])
async def list_employees(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Sequence[Employee]:
    """Return all employees for the authenticated tenant."""

    result = await session.execute(
        select(Employee).where(Employee.account_id == current_user.account_id).order_by(Employee.full_name)
    )
    return list(result.scalars().all())


@router.post("/", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Employee:
    """Create an employee scoped to the authenticated tenant."""

    require_same_tenant(current_user, current_user.account_id)
    duplicate = await session.execute(
        select(Employee).where(
            Employee.account_id == current_user.account_id,
            Employee.code == payload.code,
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee code already exists")

    employee = Employee(
        account_id=current_user.account_id,
        code=payload.code,
        full_name=payload.full_name,
        email=payload.email or "",
        contact_number=payload.contact_number or "",
        position=payload.position or "",
        department=payload.department or "",
        join_date=payload.join_date,
        exit_date=payload.exit_date,
        basic_salary=payload.basic_salary or 0.0,
    )
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee
