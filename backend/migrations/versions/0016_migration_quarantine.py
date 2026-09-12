"""正規化しない移行隔離領域を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_migration_quarantine"
down_revision: str | Sequence[str] | None = "0015_invalidation_intents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_NAME = "prevent_migration_quarantine_mutation"
_TRIGGER_NAME = "trg_migration_quarantine_append_only"


def upgrade() -> None:
    """隔離表と追記専用トリガを追加する。"""
    op.create_table(
        "migration_quarantine",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("source_read_order", sa.BigInteger(), nullable=False),
        sa.Column("raw_payload", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_migration_quarantine"),
    )
    op.create_index(
        "ix_migration_quarantine_source",
        "migration_quarantine",
        ["import_batch_id", "source_read_order"],
        unique=False,
    )

    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'migration quarantine is append-only'
                USING ERRCODE = '23514';
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE UPDATE OR DELETE ON migration_quarantine
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """隔離表と追記専用トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_TRIGGER_NAME} ON migration_quarantine")
    op.execute(f"DROP FUNCTION {_FUNCTION_NAME}()")
    op.drop_index(
        "ix_migration_quarantine_source",
        table_name="migration_quarantine",
    )
    op.drop_table("migration_quarantine")
