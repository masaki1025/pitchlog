"""イベントスロットと操作イベントを追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_sync_events"
down_revision: str | Sequence[str] | None = "0004_rule_sets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SLOT_TRIGGER_FUNCTION = "prevent_event_slots_key_update"
_SLOT_TRIGGER = "trg_event_slots_key_immutable"
_EVENT_TRIGGER_FUNCTION = "prevent_operation_events_content_update"
_EVENT_TRIGGER = "trg_operation_events_content_immutable"


def upgrade() -> None:
    """2表と確定内容を保護する不変性トリガを追加する。"""
    op.create_table(
        "event_slots",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("d1", sa.BigInteger(), nullable=False),
        sa.Column(
            "confirmed_version",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.CheckConstraint("d1 > 0"),
        sa.CheckConstraint("confirmed_version > 0"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_event_slots_game",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "generation",
            "d1",
            name="pk_event_slots",
        ),
    )
    op.create_table(
        "operation_events",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=True),
        sa.Column("d1", sa.BigInteger(), nullable=True),
        sa.Column("d2", sa.BigInteger(), nullable=True),
        sa.Column("d5", sa.Uuid(), nullable=False),
        sa.Column(
            "ledger_kind",
            sa.Text(),
            server_default=sa.text("'accepted'"),
            nullable=False,
        ),
        sa.Column("event_kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("state_diff", postgresql.JSONB(), nullable=True),
        sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_generation", sa.BigInteger(), nullable=True),
        sa.Column("target_d1", sa.BigInteger(), nullable=True),
        sa.Column("expected_version", sa.BigInteger(), nullable=True),
        sa.Column("change_order", sa.BigInteger(), nullable=True),
        sa.Column("legacy_row_identifier", sa.Text(), nullable=True),
        sa.Column(
            "migration_unverified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("ledger_kind = 'accepted'"),
        sa.CheckConstraint("(d1 IS NULL) = (generation IS NULL)"),
        sa.CheckConstraint(
            "event_kind NOT IN ('play_change', 'play_delete', "
            "'substitution_change') OR (d1 IS NULL AND d2 IS NULL AND "
            "generation IS NULL AND target_generation IS NOT NULL AND "
            "target_d1 IS NOT NULL AND expected_version IS NOT NULL)"
        ),
        sa.CheckConstraint(
            "event_kind IN ('play_change', 'play_delete', "
            "'substitution_change') OR d1 IS NOT NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_operation_events_game",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id", "generation", "d1"],
            [
                "event_slots.tenant_id",
                "event_slots.game_id",
                "event_slots.generation",
                "event_slots.d1",
            ],
            name="fk_operation_events_slot",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id", "target_generation", "target_d1"],
            [
                "event_slots.tenant_id",
                "event_slots.game_id",
                "event_slots.generation",
                "event_slots.d1",
            ],
            name="fk_operation_events_target",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_operation_events"),
        sa.UniqueConstraint(
            "tenant_id",
            "d5",
            name="uq_operation_events_d5",
        ),
    )
    op.create_index(
        "uq_operation_events_active_slot",
        "operation_events",
        ["tenant_id", "game_id", "generation", "d1"],
        unique=True,
        postgresql_where=sa.text("d1 IS NOT NULL AND replaced_at IS NULL"),
    )
    op.create_index(
        "uq_operation_events_active_d2",
        "operation_events",
        ["tenant_id", "game_id", "d2"],
        unique=True,
        postgresql_where=sa.text(
            "d2 IS NOT NULL AND replaced_at IS NULL AND retired_at IS NULL"
        ),
    )
    op.create_index(
        "ix_operation_events_replay",
        "operation_events",
        ["tenant_id", "game_id", "d2", "id"],
        unique=False,
        postgresql_where=sa.text("replaced_at IS NULL AND retired_at IS NULL"),
    )
    op.execute(
        f"""
        CREATE FUNCTION {_SLOT_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.tenant_id, NEW.game_id, NEW.generation, NEW.d1)
               IS DISTINCT FROM
               ROW(OLD.tenant_id, OLD.game_id, OLD.generation, OLD.d1) THEN
                RAISE EXCEPTION 'event_slots key columns are immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_SLOT_TRIGGER}
        BEFORE UPDATE OF tenant_id, game_id, generation, d1 ON event_slots
        FOR EACH ROW
        EXECUTE FUNCTION {_SLOT_TRIGGER_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_EVENT_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.tenant_id,
                NEW.id,
                NEW.game_id,
                NEW.generation,
                NEW.d1,
                NEW.d5,
                NEW.event_kind,
                NEW.payload,
                NEW.state_diff
            ) IS DISTINCT FROM ROW(
                OLD.tenant_id,
                OLD.id,
                OLD.game_id,
                OLD.generation,
                OLD.d1,
                OLD.d5,
                OLD.event_kind,
                OLD.payload,
                OLD.state_diff
            ) THEN
                RAISE EXCEPTION 'operation_events confirmed content is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_EVENT_TRIGGER}
        BEFORE UPDATE OF
            tenant_id,
            id,
            game_id,
            generation,
            d1,
            d5,
            event_kind,
            payload,
            state_diff
        ON operation_events
        FOR EACH ROW
        EXECUTE FUNCTION {_EVENT_TRIGGER_FUNCTION}()
        """
    )


def downgrade() -> None:
    """2表と確定内容の不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_EVENT_TRIGGER} ON operation_events")
    op.execute(f"DROP FUNCTION {_EVENT_TRIGGER_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_SLOT_TRIGGER} ON event_slots")
    op.execute(f"DROP FUNCTION {_SLOT_TRIGGER_FUNCTION}()")
    op.drop_index("ix_operation_events_replay", table_name="operation_events")
    op.drop_index("uq_operation_events_active_d2", table_name="operation_events")
    op.drop_index("uq_operation_events_active_slot", table_name="operation_events")
    op.drop_table("operation_events")
    op.drop_table("event_slots")
