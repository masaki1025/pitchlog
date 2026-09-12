"""キャッシュ無効化意図表を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_invalidation_intents"
down_revision: str | Sequence[str] | None = "0014_analysis_groups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_NAME = "prevent_invalidation_intents_target_update"
_TRIGGER_NAME = "trg_invalidation_intents_target_immutable"


def upgrade() -> None:
    """無効化先・配信状態と不変性トリガを追加する。"""
    op.create_table(
        "invalidation_intents",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("intent_id", sa.Text(), nullable=False),
        sa.Column("scope_kind", sa.Text(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=True),
        sa.Column("player_id", sa.Uuid(), nullable=True),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("requesting_tenant_id", sa.Uuid(), nullable=True),
        sa.Column("target_tenant_id", sa.Uuid(), nullable=True),
        sa.Column("period", postgresql.JSONB(), nullable=True),
        sa.Column("chart_kind", sa.Text(), nullable=True),
        sa.Column(
            "delivery_status",
            sa.Text(),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scope_kind IN ('game', 'player_total', 'team_total', "
            "'shared_total', 'chart')"
        ),
        sa.CheckConstraint("delivery_status IN ('pending', 'delivered')"),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "intent_id",
            name="pk_invalidation_intents",
        ),
    )
    op.create_index(
        "ix_invalidation_intents_delivery",
        "invalidation_intents",
        ["tenant_id", "delivery_status"],
        unique=False,
    )

    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.tenant_id,
                NEW.intent_id,
                NEW.scope_kind,
                NEW.game_id,
                NEW.player_id,
                NEW.group_id,
                NEW.requesting_tenant_id,
                NEW.target_tenant_id,
                NEW.period,
                NEW.chart_kind
            ) IS DISTINCT FROM ROW(
                OLD.tenant_id,
                OLD.intent_id,
                OLD.scope_kind,
                OLD.game_id,
                OLD.player_id,
                OLD.group_id,
                OLD.requesting_tenant_id,
                OLD.target_tenant_id,
                OLD.period,
                OLD.chart_kind
            ) THEN
                RAISE EXCEPTION 'invalidation intent target is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE UPDATE OF
            tenant_id,
            intent_id,
            scope_kind,
            game_id,
            player_id,
            group_id,
            requesting_tenant_id,
            target_tenant_id,
            period,
            chart_kind
        ON invalidation_intents
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """無効化意図表と不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_TRIGGER_NAME} ON invalidation_intents")
    op.execute(f"DROP FUNCTION {_FUNCTION_NAME}()")
    op.drop_index(
        "ix_invalidation_intents_delivery",
        table_name="invalidation_intents",
    )
    op.drop_table("invalidation_intents")
