"""管理者操作ログを追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_admin_operation_logs"
down_revision: str | Sequence[str] | None = "0011_authentication_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADMIN_OPERATION_LOG_FUNCTION = "prevent_admin_operation_logs_mutation"
_ADMIN_OPERATION_LOG_TRIGGER = "trg_admin_operation_logs_append_only"


def upgrade() -> None:
    """管理者操作ログ表と追記専用トリガを追加する。"""
    op.create_table(
        "admin_operation_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("operation_kind", sa.Text(), nullable=False),
        sa.Column("target", postgresql.JSONB(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_admin_operation_logs_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_operation_logs"),
    )
    op.create_index(
        "ix_admin_operation_logs_time",
        "admin_operation_logs",
        [sa.text("occurred_at DESC"), sa.text("id DESC")],
        unique=False,
    )

    op.execute(
        f"""
        CREATE FUNCTION {_ADMIN_OPERATION_LOG_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'admin operation logs are append-only'
                USING ERRCODE = '23514';
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_ADMIN_OPERATION_LOG_TRIGGER}
        BEFORE UPDATE OR DELETE ON admin_operation_logs
        FOR EACH ROW
        EXECUTE FUNCTION {_ADMIN_OPERATION_LOG_FUNCTION}()
        """
    )


def downgrade() -> None:
    """管理者操作ログ表と追記専用トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_ADMIN_OPERATION_LOG_TRIGGER} ON admin_operation_logs")
    op.execute(f"DROP FUNCTION {_ADMIN_OPERATION_LOG_FUNCTION}()")
    op.drop_index(
        "ix_admin_operation_logs_time",
        table_name="admin_operation_logs",
    )
    op.drop_table("admin_operation_logs")
