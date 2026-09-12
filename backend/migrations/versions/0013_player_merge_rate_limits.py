"""選手統合イベント・移動記録・レート制限表を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_player_merge_rate_limits"
down_revision: str | Sequence[str] | None = "0012_admin_operation_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLAYER_MERGE_FUNCTION = "prevent_player_merge_events_content_update"
_PLAYER_MERGE_TRIGGER = "trg_player_merge_events_content_immutable"
_PLAYER_MOVE_FUNCTION = "prevent_player_move_records_mutation"
_PLAYER_MOVE_TRIGGER = "trg_player_move_records_append_only"
_RATE_LIMIT_FUNCTION = "prevent_rate_limit_counters_identity_update"
_RATE_LIMIT_TRIGGER = "trg_rate_limit_counters_identity_immutable"


def upgrade() -> None:
    """選手統合・移動・レート制限の3表と不変性トリガを追加する。"""
    op.create_table(
        "player_merge_events",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_player_id", sa.Uuid(), nullable=False),
        sa.Column("target_player_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("executor", sa.Text(), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("source_player_id <> target_player_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_player_merge_events_source",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_player_merge_events_target",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_player_merge_events",
        ),
    )
    op.create_index(
        "ix_player_merge_events_time",
        "player_merge_events",
        ["tenant_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_table(
        "player_move_records",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("merge_event_id", sa.Uuid(), nullable=False),
        sa.Column("resource_kind", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("original_player_id", sa.Uuid(), nullable=False),
        sa.Column("moved_player_id", sa.Uuid(), nullable=False),
        sa.Column("medical_note_version_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "merge_event_id"],
            ["player_merge_events.tenant_id", "player_merge_events.id"],
            name="fk_player_move_records_merge",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "original_player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_player_move_records_original_player",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "moved_player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_player_move_records_moved_player",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_player_move_records",
        ),
    )
    op.create_index(
        "ix_player_move_records_merge",
        "player_move_records",
        ["tenant_id", "merge_event_id", "id"],
        unique=False,
    )
    op.create_table(
        "rate_limit_counters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempt_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_count >= 0"),
        sa.PrimaryKeyConstraint("id", name="pk_rate_limit_counters"),
    )
    op.create_index(
        "ix_rate_limit_counters_window",
        "rate_limit_counters",
        ["scope_key", sa.text("window_start DESC"), "id"],
        unique=False,
    )

    op.execute(
        f"""
        CREATE FUNCTION {_PLAYER_MERGE_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.source_player_id,
                NEW.target_player_id,
                NEW.occurred_at,
                NEW.executor
            ) IS DISTINCT FROM ROW(
                OLD.source_player_id,
                OLD.target_player_id,
                OLD.occurred_at,
                OLD.executor
            ) THEN
                RAISE EXCEPTION 'player merge event content is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_PLAYER_MERGE_TRIGGER}
        BEFORE UPDATE OF source_player_id, target_player_id, occurred_at, executor
        ON player_merge_events
        FOR EACH ROW
        EXECUTE FUNCTION {_PLAYER_MERGE_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_PLAYER_MOVE_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'player move records are append-only'
                USING ERRCODE = '23514';
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_PLAYER_MOVE_TRIGGER}
        BEFORE UPDATE OR DELETE ON player_move_records
        FOR EACH ROW
        EXECUTE FUNCTION {_PLAYER_MOVE_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_RATE_LIMIT_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.id, NEW.scope_key, NEW.window_start)
               IS DISTINCT FROM ROW(OLD.id, OLD.scope_key, OLD.window_start) THEN
                RAISE EXCEPTION 'rate limit counter identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_RATE_LIMIT_TRIGGER}
        BEFORE UPDATE OF id, scope_key, window_start ON rate_limit_counters
        FOR EACH ROW
        EXECUTE FUNCTION {_RATE_LIMIT_FUNCTION}()
        """
    )


def downgrade() -> None:
    """選手統合・移動・レート制限の3表と不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_RATE_LIMIT_TRIGGER} ON rate_limit_counters")
    op.execute(f"DROP FUNCTION {_RATE_LIMIT_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_PLAYER_MOVE_TRIGGER} ON player_move_records")
    op.execute(f"DROP FUNCTION {_PLAYER_MOVE_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_PLAYER_MERGE_TRIGGER} ON player_merge_events")
    op.execute(f"DROP FUNCTION {_PLAYER_MERGE_FUNCTION}()")

    op.drop_index(
        "ix_rate_limit_counters_window",
        table_name="rate_limit_counters",
    )
    op.drop_table("rate_limit_counters")
    op.drop_index(
        "ix_player_move_records_merge",
        table_name="player_move_records",
    )
    op.drop_table("player_move_records")
    op.drop_index(
        "ix_player_merge_events_time",
        table_name="player_merge_events",
    )
    op.drop_table("player_merge_events")
