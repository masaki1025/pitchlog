"""D5 台帳と拒否・退避原本を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_idempotency_originals"
down_revision: str | Sequence[str] | None = "0006_play_projections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEDGER_TRIGGER_FUNCTION = "prevent_idempotency_ledger_result_update"
_LEDGER_TRIGGER = "trg_idempotency_ledger_result_immutable"
_REJECTED_TRIGGER_FUNCTION = "prevent_rejected_event_originals_content_update"
_REJECTED_TRIGGER = "trg_rejected_event_originals_content_immutable"
_EVACUATED_TRIGGER_FUNCTION = "prevent_evacuated_event_originals_identity_update"
_EVACUATED_TRIGGER = "trg_evacuated_event_originals_identity_immutable"


def upgrade() -> None:
    """D5 台帳・原本 2 表・参照元 3 表の複合 FK を追加する。"""
    op.create_table(
        "idempotency_ledger",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("d5", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source_fingerprint", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('accepted', 'rejected', 'evacuated')"),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "d5",
            name="pk_idempotency_ledger",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "d5",
            "kind",
            name="uq_idempotency_ledger_kind",
        ),
    )
    op.create_table(
        "rejected_event_originals",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("d5", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Text(),
            server_default=sa.text("'rejected'"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("kind = 'rejected'"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "d5", "kind"],
            [
                "idempotency_ledger.tenant_id",
                "idempotency_ledger.d5",
                "idempotency_ledger.kind",
            ],
            name="fk_rejected_event_originals_ledger",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_rejected_event_originals",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "d5",
            name="uq_rejected_event_originals_d5",
        ),
    )
    op.create_foreign_key(
        "fk_operation_events_ledger",
        "operation_events",
        "idempotency_ledger",
        ["tenant_id", "d5", "ledger_kind"],
        ["tenant_id", "d5", "kind"],
        ondelete="NO ACTION",
        match="FULL",
    )
    op.create_table(
        "evacuated_event_originals",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("old_generation", sa.BigInteger(), nullable=False),
        sa.Column("original_d1", sa.BigInteger(), nullable=False),
        sa.Column("d5", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Text(),
            server_default=sa.text("'evacuated'"),
            nullable=False,
        ),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("recovered_device", sa.Text(), nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("imported_event_id", sa.Uuid(), nullable=True),
        sa.Column("retention_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("kind = 'evacuated'"),
        sa.CheckConstraint("origin IN ('authority_mismatch', 'restore_collection')"),
        sa.CheckConstraint(
            "status IN ('pending', 'imported', 'not_imported', 'discarded')"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_evacuated_event_originals_game",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "d5", "kind"],
            [
                "idempotency_ledger.tenant_id",
                "idempotency_ledger.d5",
                "idempotency_ledger.kind",
            ],
            name="fk_evacuated_event_originals_ledger",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "imported_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_evacuated_event_originals_imported_event",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_evacuated_event_originals",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "game_id",
            "old_generation",
            "original_d1",
            name="uq_evacuated_event_originals_source",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "d5",
            name="uq_evacuated_event_originals_d5",
        ),
    )
    op.create_index(
        "ix_evacuated_event_originals_retention",
        "evacuated_event_originals",
        ["tenant_id", "retention_deadline"],
        unique=False,
        postgresql_where=sa.text(
            "retention_deadline IS NOT NULL AND discarded_at IS NULL"
        ),
    )
    op.execute(
        f"""
        CREATE FUNCTION {_LEDGER_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.kind, NEW.source_fingerprint, NEW.result, NEW.reason)
               IS DISTINCT FROM
               ROW(OLD.kind, OLD.source_fingerprint, OLD.result, OLD.reason) THEN
                RAISE EXCEPTION 'idempotency ledger result is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_LEDGER_TRIGGER}
        BEFORE UPDATE OF kind, source_fingerprint, result, reason
        ON idempotency_ledger
        FOR EACH ROW
        EXECUTE FUNCTION {_LEDGER_TRIGGER_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_REJECTED_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.d5, NEW.kind, NEW.payload)
               IS DISTINCT FROM ROW(OLD.d5, OLD.kind, OLD.payload) THEN
                RAISE EXCEPTION 'rejected event original is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_REJECTED_TRIGGER}
        BEFORE UPDATE OF d5, kind, payload ON rejected_event_originals
        FOR EACH ROW
        EXECUTE FUNCTION {_REJECTED_TRIGGER_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_EVACUATED_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.game_id,
                NEW.old_generation,
                NEW.original_d1,
                NEW.d5,
                NEW.kind,
                NEW.origin
            ) IS DISTINCT FROM ROW(
                OLD.game_id,
                OLD.old_generation,
                OLD.original_d1,
                OLD.d5,
                OLD.kind,
                OLD.origin
            ) THEN
                RAISE EXCEPTION 'evacuated event original identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_EVACUATED_TRIGGER}
        BEFORE UPDATE OF game_id, old_generation, original_d1, d5, kind, origin
        ON evacuated_event_originals
        FOR EACH ROW
        EXECUTE FUNCTION {_EVACUATED_TRIGGER_FUNCTION}()
        """
    )


def downgrade() -> None:
    """D5 台帳・原本 2 表・参照元 3 表の複合 FK を除去する。"""
    op.execute(f"DROP TRIGGER {_EVACUATED_TRIGGER} ON evacuated_event_originals")
    op.execute(f"DROP FUNCTION {_EVACUATED_TRIGGER_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_REJECTED_TRIGGER} ON rejected_event_originals")
    op.execute(f"DROP FUNCTION {_REJECTED_TRIGGER_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_LEDGER_TRIGGER} ON idempotency_ledger")
    op.execute(f"DROP FUNCTION {_LEDGER_TRIGGER_FUNCTION}()")
    op.drop_index(
        "ix_evacuated_event_originals_retention",
        table_name="evacuated_event_originals",
    )
    op.drop_table("evacuated_event_originals")
    op.drop_constraint(
        "fk_operation_events_ledger",
        "operation_events",
        type_="foreignkey",
    )
    op.drop_table("rejected_event_originals")
    op.drop_table("idempotency_ledger")
