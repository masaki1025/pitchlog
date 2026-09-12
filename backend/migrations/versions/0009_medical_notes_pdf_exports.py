"""カルテ所見・変更履歴・PDF 出力実績を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_medical_notes_pdf_exports"
down_revision: str | Sequence[str] | None = "0008_recording_generations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MEDICAL_NOTE_FUNCTION = "prevent_medical_notes_identity_update"
_MEDICAL_NOTE_TRIGGER = "trg_medical_notes_identity_immutable"
_MEDICAL_VERSION_FUNCTION = "prevent_medical_note_versions_content_update"
_MEDICAL_VERSION_TRIGGER = "trg_medical_note_versions_content_immutable"
_PDF_EXPORT_FUNCTION = "prevent_pdf_export_records_mutation"
_PDF_EXPORT_TRIGGER = "trg_pdf_export_records_append_only"


def upgrade() -> None:
    """カルテ 2 表・PDF 実績表と不変性トリガを追加する。"""
    op.create_table(
        "medical_notes",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("note_kind", sa.Text(), nullable=False),
        sa.Column(
            "content",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("note_kind IN ('pitcher', 'batter')"),
        sa.CheckConstraint("version > 0"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_medical_notes_player",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_medical_notes",
        ),
    )
    op.create_index(
        "uq_medical_notes_active",
        "medical_notes",
        ["tenant_id", "player_id", "note_kind"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_table(
        "medical_note_versions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("medical_note_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "origin",
            sa.Text(),
            server_default=sa.text("'user_edit'"),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "retained_for_restore",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.CheckConstraint("origin IN ('user_edit', 'merge')"),
        sa.CheckConstraint("version > 0"),
        sa.CheckConstraint("origin <> 'merge' OR retained_for_restore"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "medical_note_id"],
            ["medical_notes.tenant_id", "medical_notes.id"],
            name="fk_medical_note_versions_note",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_medical_note_versions",
        ),
    )
    op.create_index(
        "ix_medical_note_versions_history",
        "medical_note_versions",
        ["tenant_id", "medical_note_id", sa.text("version DESC")],
        unique=False,
    )
    op.create_table(
        "pdf_export_records",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "exported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("team_record_id", sa.Uuid(), nullable=True),
        sa.Column("player_id", sa.Uuid(), nullable=True),
        sa.Column("applied_filters", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("team_record_id IS NOT NULL OR player_id IS NOT NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_pdf_export_records_team",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_pdf_export_records_player",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_pdf_export_records",
        ),
    )
    op.create_index(
        "ix_pdf_export_records_time",
        "pdf_export_records",
        ["tenant_id", sa.text("exported_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.execute(
        f"""
        CREATE FUNCTION {_MEDICAL_NOTE_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.player_id, NEW.note_kind)
               IS DISTINCT FROM ROW(OLD.player_id, OLD.note_kind) THEN
                RAISE EXCEPTION 'medical note identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_MEDICAL_NOTE_TRIGGER}
        BEFORE UPDATE OF player_id, note_kind ON medical_notes
        FOR EACH ROW
        EXECUTE FUNCTION {_MEDICAL_NOTE_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_MEDICAL_VERSION_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.medical_note_id,
                NEW.version,
                NEW.content,
                NEW.origin,
                NEW.recorded_at
            ) IS DISTINCT FROM ROW(
                OLD.medical_note_id,
                OLD.version,
                OLD.content,
                OLD.origin,
                OLD.recorded_at
            ) THEN
                RAISE EXCEPTION 'medical note version content is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_MEDICAL_VERSION_TRIGGER}
        BEFORE UPDATE OF medical_note_id, version, content, origin, recorded_at
        ON medical_note_versions
        FOR EACH ROW
        EXECUTE FUNCTION {_MEDICAL_VERSION_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_PDF_EXPORT_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'pdf export records are append-only'
                USING ERRCODE = '23514';
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_PDF_EXPORT_TRIGGER}
        BEFORE UPDATE OR DELETE ON pdf_export_records
        FOR EACH ROW
        EXECUTE FUNCTION {_PDF_EXPORT_FUNCTION}()
        """
    )


def downgrade() -> None:
    """カルテ 2 表・PDF 実績表と不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_PDF_EXPORT_TRIGGER} ON pdf_export_records")
    op.execute(f"DROP FUNCTION {_PDF_EXPORT_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_MEDICAL_VERSION_TRIGGER} ON medical_note_versions")
    op.execute(f"DROP FUNCTION {_MEDICAL_VERSION_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_MEDICAL_NOTE_TRIGGER} ON medical_notes")
    op.execute(f"DROP FUNCTION {_MEDICAL_NOTE_FUNCTION}()")
    op.drop_index("ix_pdf_export_records_time", table_name="pdf_export_records")
    op.drop_table("pdf_export_records")
    op.drop_index(
        "ix_medical_note_versions_history",
        table_name="medical_note_versions",
    )
    op.drop_table("medical_note_versions")
    op.drop_index("uq_medical_notes_active", table_name="medical_notes")
    op.drop_table("medical_notes")
