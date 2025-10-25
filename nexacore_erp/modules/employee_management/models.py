from datetime import date
from sqlalchemy import String, Integer, Float, Date, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ...core.database import Base
from ...core.tenant import id as tenant_id

# -------- Employees --------
class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")

    # identity
    code: Mapped[str] = mapped_column(String, index=True)
    full_name: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, default="")
    contact_number: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(String, default="")
    id_type: Mapped[str] = mapped_column(String, default="")
    id_number: Mapped[str] = mapped_column(String, default="")
    gender: Mapped[str] = mapped_column(String, default="")
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    race: Mapped[str] = mapped_column(String, default="")
    country: Mapped[str] = mapped_column(String, default="")
    residency: Mapped[str] = mapped_column(String, default="")
    pr_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # employment
    employment_status: Mapped[str] = mapped_column(String, default="Active")  # Active / Non-Active
    employment_pass: Mapped[str] = mapped_column(String, default="")
    work_permit_number: Mapped[str] = mapped_column(String, default="")
    department: Mapped[str] = mapped_column(String, default="")
    position: Mapped[str] = mapped_column(String, default="")
    employment_type: Mapped[str] = mapped_column(String, default="")
    join_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    holiday_group: Mapped[str] = mapped_column(String, default="")

    # bank
    bank: Mapped[str] = mapped_column(String, default="")
    bank_account: Mapped[str] = mapped_column(String, default="")

    # remuneration snapshot (latest)
    basic_salary: Mapped[float] = mapped_column(Float, default=0.0)
    incentives: Mapped[float] = mapped_column(Float, default=0.0)
    allowance: Mapped[float] = mapped_column(Float, default=0.0)
    overtime_rate: Mapped[float] = mapped_column(Float, default=0.0)
    parttime_rate: Mapped[float] = mapped_column(Float, default=0.0)
    levy: Mapped[float] = mapped_column(Float, default=0.0)

    salary_history: Mapped[list["SalaryHistory"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    work_schedule: Mapped[list["WorkScheduleDay"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    entitlements: Mapped[list["LeaveEntitlement"]] = relationship(back_populates="employee", cascade="all, delete-orphan")

class SalaryHistory(Base):
    __tablename__ = "employee_salary_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    employee: Mapped[Employee] = relationship(back_populates="salary_history")

class WorkScheduleDay(Base):
    __tablename__ = "employee_work_schedule"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Mon .. 6=Sun
    working: Mapped[bool] = mapped_column(Boolean, default=True)
    day_type: Mapped[str] = mapped_column(String, default="Full")  # Full | Half
    __table_args__ = (UniqueConstraint("employee_id", "weekday", name="uq_emp_weekday"),)
    employee: Mapped[Employee] = relationship(back_populates="work_schedule")

class LeaveEntitlement(Base):
    __tablename__ = "employee_leave_entitlements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    year_of_service: Mapped[int] = mapped_column(Integer)  # 1..50
    leave_type: Mapped[str] = mapped_column(String, index=True)
    days: Mapped[float] = mapped_column(Float, default=0.0)
    __table_args__ = (UniqueConstraint("employee_id", "year_of_service", "leave_type", name="uq_emp_yos_type"),)
    employee: Mapped[Employee] = relationship(back_populates="entitlements")

# -------- Holidays and Options / Defaults --------
class Holiday(Base):
    __tablename__ = "holidays"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    group_code: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    date: Mapped[date] = mapped_column(Date, index=True)
    __table_args__ = (UniqueConstraint("account_id", "group_code", "date", name="uq_holiday"),)

class DropdownOption(Base):
    __tablename__ = "dropdown_options"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    category: Mapped[str] = mapped_column(String, index=True)  # e.g. "ID Type", "Position", "Bank", "Country", "Race"
    value: Mapped[str] = mapped_column(String, index=True)

class LeaveDefault(Base):
    __tablename__ = "leave_defaults"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="default")
    leave_type: Mapped[str] = mapped_column(String, index=True)   # "Annual", "Sick", etc.
    prorated: Mapped[bool] = mapped_column(Boolean, default=False)
    yearly_reset: Mapped[bool] = mapped_column(Boolean, default=True)
    table_json: Mapped[str] = mapped_column(Text, default="{}")   # {"1":14,...,"50":14}
