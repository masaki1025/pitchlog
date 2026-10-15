"""試合状態変更の無効化意図へ明示的な選択子判別を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_intent_selectors"
down_revision: str | Sequence[str] | None = "0030_seed_game_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "invalidation_intents"
_TRIGGER = "trg_invalidation_intents_target_immutable"
_FUNCTION = "prevent_invalidation_intents_target_update"
_PREFIX = "game_delete_restore_or_resume:"
_UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_SELECTOR_VALUES = (
    "target_selector_kind IS NULL OR target_selector_kind IN "
    "('concrete_game', 'tenant_scope', 'shared_target_tenant')"
)
_IDENTITY = (
    "CASE WHEN target_selector_kind IS NULL THEN "
    f"left(intent_id, length('{_PREFIX}')) <> '{_PREFIX}' "
    "ELSE "
    f"left(intent_id, length('{_PREFIX}')) = '{_PREFIX}' "
    f"AND intent_id ~ '^{_PREFIX}{_UUID_PATTERN}:{_UUID_PATTERN}:"
    "(match|player_career|team_aggregate|shared_aggregate|analytics_chart)$' "
    "END"
)
_SHAPE = (
    "target_selector_kind IS NULL OR CASE split_part(intent_id, ':', 4) "
    "WHEN 'match' THEN scope_kind = 'game' "
    "AND target_selector_kind = 'concrete_game' "
    "AND game_id IS NOT NULL AND game_id::text = split_part(intent_id, ':', 3) "
    "AND player_id IS NULL AND group_id IS NULL "
    "AND requesting_tenant_id IS NULL AND target_tenant_id IS NULL "
    "AND period IS NULL AND chart_kind IS NULL "
    "WHEN 'player_career' THEN scope_kind = 'player_total' "
    "AND target_selector_kind = 'tenant_scope' "
    "AND game_id IS NULL AND player_id IS NULL AND group_id IS NULL "
    "AND requesting_tenant_id IS NULL AND target_tenant_id IS NULL "
    "AND period IS NULL AND chart_kind IS NULL "
    "WHEN 'team_aggregate' THEN scope_kind = 'team_total' "
    "AND target_selector_kind = 'tenant_scope' "
    "AND game_id IS NULL AND player_id IS NULL AND group_id IS NULL "
    "AND requesting_tenant_id IS NULL AND target_tenant_id IS NULL "
    "AND period IS NULL AND chart_kind IS NULL "
    "WHEN 'shared_aggregate' THEN scope_kind = 'shared_total' "
    "AND target_selector_kind = 'shared_target_tenant' "
    "AND target_tenant_id IS NOT NULL "
    "AND target_tenant_id IS NOT DISTINCT FROM tenant_id "
    "AND game_id IS NULL AND player_id IS NULL AND group_id IS NULL "
    "AND requesting_tenant_id IS NULL AND period IS NULL "
    "AND chart_kind IS NULL "
    "WHEN 'analytics_chart' THEN scope_kind = 'chart' "
    "AND target_selector_kind = 'tenant_scope' "
    "AND game_id IS NULL AND player_id IS NULL AND group_id IS NULL "
    "AND requesting_tenant_id IS NULL AND target_tenant_id IS NULL "
    "AND period IS NULL AND chart_kind IS NULL "
    "ELSE FALSE END"
)


def _replace_immutability_trigger(*, with_selector: bool) -> None:
    """対象列集合を列追加前後の形へ更新する。"""
    new_selector = ", NEW.target_selector_kind" if with_selector else ""
    old_selector = ", OLD.target_selector_kind" if with_selector else ""
    selector_column = ", target_selector_kind" if with_selector else ""
    op.execute(f"DROP TRIGGER {_TRIGGER} ON {_TABLE}")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.tenant_id, NEW.intent_id, NEW.scope_kind,
                NEW.game_id, NEW.player_id, NEW.group_id,
                NEW.requesting_tenant_id, NEW.target_tenant_id,
                NEW.period, NEW.chart_kind{new_selector}
            ) IS DISTINCT FROM ROW(
                OLD.tenant_id, OLD.intent_id, OLD.scope_kind,
                OLD.game_id, OLD.player_id, OLD.group_id,
                OLD.requesting_tenant_id, OLD.target_tenant_id,
                OLD.period, OLD.chart_kind{old_selector}
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
        CREATE TRIGGER {_TRIGGER}
        BEFORE UPDATE OF
            tenant_id, intent_id, scope_kind, game_id, player_id,
            group_id, requesting_tenant_id, target_tenant_id,
            period, chart_kind{selector_column}
        ON {_TABLE}
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION}()
        """
    )


def upgrade() -> None:
    """旧行を更新せず、新意図だけに明示的な保存形を強制する。"""
    op.add_column(_TABLE, sa.Column("target_selector_kind", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_invalidation_intents_selector_values", _TABLE, _SELECTOR_VALUES
    )
    op.create_check_constraint(
        "ck_invalidation_intents_selector_identity", _TABLE, _IDENTITY
    )
    op.create_check_constraint("ck_invalidation_intents_selector_shape", _TABLE, _SHAPE)
    _replace_immutability_trigger(with_selector=True)


def downgrade() -> None:
    """新形式行が残る場合は情報を捨てずに拒否する。"""
    op.execute(
        "ALTER TABLE invalidation_intents ADD CONSTRAINT "
        "ck_invalidation_intents_downgrade_guard "
        "CHECK (target_selector_kind IS NULL) NOT VALID"
    )
    op.execute(
        "ALTER TABLE invalidation_intents VALIDATE CONSTRAINT "
        "ck_invalidation_intents_downgrade_guard"
    )
    op.drop_constraint("ck_invalidation_intents_downgrade_guard", _TABLE, type_="check")
    _replace_immutability_trigger(with_selector=False)
    op.drop_constraint("ck_invalidation_intents_selector_shape", _TABLE, type_="check")
    op.drop_constraint(
        "ck_invalidation_intents_selector_identity", _TABLE, type_="check"
    )
    op.drop_constraint("ck_invalidation_intents_selector_values", _TABLE, type_="check")
    op.drop_column(_TABLE, "target_selector_kind")
