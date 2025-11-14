"""create users and employees tables"""
from alembic import op
import sqlalchemy as sa

revision = "0001_create_base_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("password_enc", sa.LargeBinary(), nullable=True),
        sa.Column("email", sa.String(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_account_id", "users", ["account_id"])

    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False, server_default=""),
        sa.Column("contact_number", sa.String(), nullable=False, server_default=""),
        sa.Column("position", sa.String(), nullable=False, server_default=""),
        sa.Column("department", sa.String(), nullable=False, server_default=""),
        sa.Column("join_date", sa.Date(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("basic_salary", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_emp_account_code", "employees", ["account_id", "code"])
    op.create_index("ix_emp_account_fullname", "employees", ["account_id", "full_name"])


def downgrade() -> None:
    op.drop_index("ix_emp_account_fullname", table_name="employees")
    op.drop_index("ix_emp_account_code", table_name="employees")
    op.drop_table("employees")
    op.drop_index("ix_users_account_id", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
