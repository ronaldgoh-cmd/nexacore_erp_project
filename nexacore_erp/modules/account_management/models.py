# keeps all new tables in MAIN DB, separate from other modules
from __future__ import annotations
from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, declarative_base

BaseAcc = declarative_base()

class Role(BaseAcc):
    __tablename__ = "am_roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    description: Mapped[str] = mapped_column(String, default="")

class Permission(BaseAcc):
    __tablename__ = "am_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)  # e.g. "accounts.manage_users"


class RolePermission(BaseAcc):
    __tablename__ = "am_role_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("am_roles.id", ondelete="CASCADE"), index=True)
    perm_id: Mapped[int] = mapped_column(Integer, ForeignKey("am_permissions.id", ondelete="CASCADE"), index=True)
    __table_args__ = (UniqueConstraint("role_id", "perm_id", name="uq_role_perm"),)
    role = relationship(Role)
    perm = relationship(Permission)


class UserRole(BaseAcc):
    __tablename__ = "am_user_roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)  # references core.users.id
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("am_roles.id", ondelete="CASCADE"), index=True)
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)
    role = relationship(Role)


class AccessRule(BaseAcc):
    __tablename__ = "am_access_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("am_roles.id", ondelete="CASCADE"), index=True)
    module_name: Mapped[str] = mapped_column(String, index=True)  # e.g. "Employee Management"
    submodule_name: Mapped[str] = mapped_column(String, default="")  # e.g. "Leave Management" or ""
    tab_name: Mapped[str] = mapped_column(String, default="")  # e.g. "Summary" or ""
    can_view: Mapped[bool] = mapped_column(Boolean, default=True)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("role_id", "module_name", "submodule_name", "tab_name", name="uq_access"),)
    role = relationship(Role)
