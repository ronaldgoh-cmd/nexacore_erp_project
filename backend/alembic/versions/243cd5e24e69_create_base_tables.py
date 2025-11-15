"""create base tables

Revision ID: 243cd5e24e69
Revises: 
Create Date: 2025-11-15 20:26:51.626731

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '243cd5e24e69'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users table ---------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # indexes for users (idempotent)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_account_id ON users (account_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"
    )

    # --- employees table -----------------------------------------------------
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("contact_number", sa.String(), nullable=False),
        sa.Column("position", sa.String(), nullable=False),
        sa.Column("department", sa.String(), nullable=False),
        sa.Column("join_date", sa.Date(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("basic_salary", sa.Float(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
    )

    # indexes for employees (idempotent)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employees_account_id "
        "ON employees (account_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employees_code "
        "ON employees (code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employees_full_name "
        "ON employees (full_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_emp_account_code "
        "ON employees (account_id, code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_emp_account_fullname "
        "ON employees (account_id, full_name)"
    )


def downgrade() -> None:
    # drop indexes + tables in reverse order

    # employees
    op.execute("DROP INDEX IF EXISTS ix_emp_account_fullname")
    op.execute("DROP INDEX IF EXISTS ix_emp_account_code")
    op.execute("DROP INDEX IF EXISTS ix_employees_full_name")
    op.execute("DROP INDEX IF EXISTS ix_employees_code")
    op.execute("DROP INDEX IF EXISTS ix_employees_account_id")
    op.drop_table("employees")

    # users
    op.execute("DROP INDEX IF EXISTS ix_users_username")
    op.execute("DROP INDEX IF EXISTS ix_users_account_id")
    op.drop_table("users")
