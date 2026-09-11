"""記録権世代と D3 の後退防止を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_recording_generations"
down_revision: str | Sequence[str] | None = "0007_idempotency_originals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGER_FUNCTION = "protect_recording_generations_updates"
_TRIGGER = "trg_recording_generations_update_guard"


def upgrade() -> None:
    """記録権世代表・イベントスロット FK・更新防止トリガを追加する。"""
    op.create_table(
        "recording_generations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column(
            "kind",
            sa.Text(),
            server_default=sa.text("'normal'"),
            nullable=False,
        ),
        sa.Column("issuance_order", sa.BigInteger(), nullable=False),
        sa.Column("holder_device", sa.Text(), nullable=True),
        sa.Column(
            "confirmed_watermark",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "applied_prefix",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('normal', 'migration')"),
        sa.CheckConstraint("confirmed_watermark >= 0"),
        sa.CheckConstraint("applied_prefix >= 0"),
        sa.CheckConstraint("kind <> 'migration' OR holder_device IS NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_recording_generations_game",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "generation",
            name="pk_recording_generations",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "game_id",
            "issuance_order",
            name="uq_recording_generations_issuance_order",
        ),
    )
    op.create_index(
        "uq_recording_generations_current",
        "recording_generations",
        ["tenant_id", "game_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'normal' AND revoked_at IS NULL"),
    )
    op.create_index(
        "uq_recording_generations_migration",
        "recording_generations",
        ["tenant_id", "game_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'migration' AND retired_at IS NULL"),
    )
    op.create_index(
        "ix_recording_generations_history",
        "recording_generations",
        ["tenant_id", "game_id", sa.text("issuance_order DESC")],
        unique=False,
    )
    op.create_foreign_key(
        "fk_event_slots_generation",
        "event_slots",
        "recording_generations",
        ["tenant_id", "game_id", "generation"],
        ["tenant_id", "game_id", "generation"],
        ondelete="NO ACTION",
        match="FULL",
    )
    op.execute(
        f"""
        CREATE FUNCTION {_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.generation,
                NEW.kind,
                NEW.issuance_order,
                NEW.holder_device,
                NEW.granted_at
            ) IS DISTINCT FROM ROW(
                OLD.generation,
                OLD.kind,
                OLD.issuance_order,
                OLD.holder_device,
                OLD.granted_at
            ) THEN
                RAISE EXCEPTION 'recording generation identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.confirmed_watermark < OLD.confirmed_watermark THEN
                RAISE EXCEPTION 'recording generation D3 cannot move backward'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
        BEFORE UPDATE OF generation, kind, issuance_order, holder_device,
            granted_at, confirmed_watermark
        ON recording_generations
        FOR EACH ROW
        EXECUTE FUNCTION {_TRIGGER_FUNCTION}()
        """
    )


def downgrade() -> None:
    """記録権世代表・イベントスロット FK・更新防止トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_TRIGGER} ON recording_generations")
    op.execute(f"DROP FUNCTION {_TRIGGER_FUNCTION}()")
    op.drop_constraint(
        "fk_event_slots_generation",
        "event_slots",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_recording_generations_history",
        table_name="recording_generations",
    )
    op.drop_index(
        "uq_recording_generations_migration",
        table_name="recording_generations",
    )
    op.drop_index(
        "uq_recording_generations_current",
        table_name="recording_generations",
    )
    op.drop_table("recording_generations")
