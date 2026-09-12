"""移行結果・解決・警告レポートを追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_migration_reports"
down_revision: str | Sequence[str] | None = "0017_migrated_final_lineups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_FUNCTION_NAME = "prevent_migration_runs_source_update"
_RUN_TRIGGER_NAME = "trg_migration_runs_source_immutable"
_RESOLUTION_FUNCTION_NAME = "prevent_migration_resolution_reports_mutation"
_RESOLUTION_TRIGGER_NAME = "trg_migration_resolution_reports_append_only"
_WARNING_FUNCTION_NAME = "prevent_migration_warning_reports_mutation"
_WARNING_TRIGGER_NAME = "trg_migration_warning_reports_append_only"


def upgrade() -> None:
    """移行結果・レポート・既存取り込み識別子の FK を追加する。"""
    op.create_table(
        "migration_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_counts", postgresql.JSONB(), nullable=False),
        sa.Column("generated_copy_counts", postgresql.JSONB(), nullable=False),
        sa.Column("validation_results", postgresql.JSONB(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("completed_at IS NULL OR completed_at >= started_at"),
        sa.PrimaryKeyConstraint("id", name="pk_migration_runs"),
    )
    op.create_index(
        "ix_migration_runs_time",
        "migration_runs",
        [sa.text("started_at DESC"), sa.text("id DESC")],
        unique=False,
    )

    op.create_table(
        "migration_resolution_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("legacy_row_identifier", sa.Text(), nullable=False),
        sa.Column("issue", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["migration_runs.id"],
            name="fk_migration_resolution_reports_run",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_migration_resolution_reports"),
    )
    op.create_index(
        "ix_migration_resolution_reports_run",
        "migration_resolution_reports",
        ["import_batch_id", "source_kind", "id"],
        unique=False,
    )

    op.create_table(
        "migration_warning_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("legacy_row_identifier", sa.Text(), nullable=False),
        sa.Column("warning_kind", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["migration_runs.id"],
            name="fk_migration_warning_reports_run",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_migration_warning_reports"),
    )
    op.create_index(
        "ix_migration_warning_reports_run",
        "migration_warning_reports",
        ["import_batch_id", "warning_kind", "id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_tenants_import_batch",
        "tenants",
        "migration_runs",
        ["import_batch_id"],
        ["id"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_team_records_import_batch",
        "team_records",
        "migration_runs",
        ["import_batch_id"],
        ["id"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_migration_quarantine_run",
        "migration_quarantine",
        "migration_runs",
        ["import_batch_id"],
        ["id"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )

    op.execute(
        f"""
        CREATE FUNCTION {_RUN_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.id, NEW.started_at, NEW.source_counts)
               IS DISTINCT FROM
               ROW(OLD.id, OLD.started_at, OLD.source_counts) THEN
                RAISE EXCEPTION 'migration run source is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_RUN_TRIGGER_NAME}
        BEFORE UPDATE OF id, started_at, source_counts
        ON migration_runs
        FOR EACH ROW
        EXECUTE FUNCTION {_RUN_FUNCTION_NAME}()
        """
    )

    op.execute(
        f"""
        CREATE FUNCTION {_RESOLUTION_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'migration resolution report is append-only'
                USING ERRCODE = '23514';
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_RESOLUTION_TRIGGER_NAME}
        BEFORE UPDATE OR DELETE ON migration_resolution_reports
        FOR EACH ROW
        EXECUTE FUNCTION {_RESOLUTION_FUNCTION_NAME}()
        """
    )

    op.execute(
        f"""
        CREATE FUNCTION {_WARNING_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'migration warning report is append-only'
                USING ERRCODE = '23514';
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_WARNING_TRIGGER_NAME}
        BEFORE UPDATE OR DELETE ON migration_warning_reports
        FOR EACH ROW
        EXECUTE FUNCTION {_WARNING_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """移行結果・レポート・既存取り込み識別子の FK を除去する。"""
    op.drop_constraint(
        "fk_migration_quarantine_run",
        "migration_quarantine",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_team_records_import_batch",
        "team_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_tenants_import_batch",
        "tenants",
        type_="foreignkey",
    )

    op.execute(f"DROP TRIGGER {_WARNING_TRIGGER_NAME} ON migration_warning_reports")
    op.execute(f"DROP FUNCTION {_WARNING_FUNCTION_NAME}()")
    op.execute(
        f"DROP TRIGGER {_RESOLUTION_TRIGGER_NAME} ON migration_resolution_reports"
    )
    op.execute(f"DROP FUNCTION {_RESOLUTION_FUNCTION_NAME}()")
    op.execute(f"DROP TRIGGER {_RUN_TRIGGER_NAME} ON migration_runs")
    op.execute(f"DROP FUNCTION {_RUN_FUNCTION_NAME}()")

    op.drop_index(
        "ix_migration_warning_reports_run",
        table_name="migration_warning_reports",
    )
    op.drop_table("migration_warning_reports")
    op.drop_index(
        "ix_migration_resolution_reports_run",
        table_name="migration_resolution_reports",
    )
    op.drop_table("migration_resolution_reports")
    op.drop_index("ix_migration_runs_time", table_name="migration_runs")
    op.drop_table("migration_runs")
