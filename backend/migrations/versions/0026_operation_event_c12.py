"""C12 の生成式を操作イベントの種別条件 CHECK へ反映する。

既存 ``ck_operation_events_state_diff_by_kind`` は V8 の生成式へ、既存
``ck_operation_events_tombstone`` は V9 の生成式と C12 外の墓標 payload 要件へ
置き換える。V6・V10・V11 はそれぞれ d2・対象参照・expected_version の新しい
CHECK とする。V2・V3 を担う 0005 由来の無名 CHECK 4 本は変更しない。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_operation_event_c12"
down_revision: str | Sequence[str] | None = "0025_operation_event_immutable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_D2_CHECK = (
    "(NOT (event_kind = 'play_input' AND NOT is_tombstone) OR (d2 IS NOT NULL)) "
    "AND (NOT (event_kind = 'undo' AND NOT is_tombstone) OR (d2 IS NULL)) AND "
    "(NOT (event_kind = 'substitution' AND NOT is_tombstone) OR (d2 IS NOT NULL)) "
    "AND (NOT (event_kind = 'tiebreak_start' AND NOT is_tombstone) OR "
    "(d2 IS NOT NULL)) AND (NOT (event_kind = 'game_end_declaration' AND NOT "
    "is_tombstone) OR (d2 IS NOT NULL)) AND (NOT (event_kind = "
    "'player_registration' AND NOT is_tombstone) OR (d2 IS NULL)) AND "
    "(NOT (is_tombstone) OR (d2 IS NULL)) AND (NOT (event_kind = 'play_change') "
    "OR (d2 IS NULL)) AND (NOT (event_kind = 'play_delete') OR (d2 IS NULL)) "
    "AND (NOT (event_kind = 'substitution_change') OR (d2 IS NULL))"
)
_STATE_DIFF_CHECK = (
    "(NOT (event_kind = 'play_input' AND NOT is_tombstone) OR (state_diff IS NOT "
    "NULL)) AND (NOT (event_kind = 'undo' AND NOT is_tombstone) OR (state_diff "
    "IS NULL)) AND (NOT (event_kind = 'substitution' AND NOT is_tombstone) OR "
    "(state_diff IS NULL)) AND (NOT (event_kind = 'tiebreak_start' AND NOT "
    "is_tombstone) OR (state_diff IS NULL)) AND (NOT (event_kind = "
    "'game_end_declaration' AND NOT is_tombstone) OR (state_diff IS NULL)) AND "
    "(NOT (event_kind = 'player_registration' AND NOT is_tombstone) OR "
    "(state_diff IS NULL)) AND (NOT (event_kind = 'state_correction' AND NOT "
    "is_tombstone) OR (state_diff IS NOT NULL)) AND (NOT (is_tombstone) OR "
    "(state_diff IS NULL)) AND (NOT (event_kind = 'play_change') OR (state_diff "
    "IS NULL)) AND (NOT (event_kind = 'play_delete') OR (state_diff IS NULL)) "
    "AND (NOT (event_kind = 'substitution_change') OR (state_diff IS NULL))"
)
_V9_CHECK = (
    "(NOT (event_kind = 'play_change') OR (NOT is_tombstone)) AND "
    "(NOT (event_kind = 'play_delete') OR (NOT is_tombstone)) AND "
    "(NOT (event_kind = 'substitution_change') OR (NOT is_tombstone))"
)
_TOMBSTONE_CHECK = f"({_V9_CHECK}) AND (NOT is_tombstone OR payload = '{{}}'::jsonb)"
_TARGET_CHECK = (
    "(NOT (event_kind = 'undo' AND NOT is_tombstone) OR (target_generation IS "
    "NOT NULL AND target_d1 IS NOT NULL)) AND (NOT (event_kind = 'play_change') "
    "OR (target_generation IS NOT NULL AND target_d1 IS NOT NULL)) AND "
    "(NOT (event_kind = 'play_delete') OR (target_generation IS NOT NULL AND "
    "target_d1 IS NOT NULL)) AND (NOT (event_kind = 'substitution_change') OR "
    "(target_generation IS NOT NULL AND target_d1 IS NOT NULL))"
)
_EXPECTED_VERSION_CHECK = (
    "(NOT (event_kind = 'play_input' AND NOT is_tombstone) OR (expected_version "
    "IS NULL)) AND (NOT (event_kind = 'undo' AND NOT is_tombstone) OR "
    "(expected_version IS NULL)) AND (NOT (event_kind = 'substitution' AND NOT "
    "is_tombstone) OR (expected_version IS NULL)) AND (NOT (event_kind = "
    "'tiebreak_start' AND NOT is_tombstone) OR (expected_version IS NULL)) AND "
    "(NOT (event_kind = 'game_end_declaration' AND NOT is_tombstone) OR "
    "(expected_version IS NULL)) AND (NOT (event_kind = 'player_registration' "
    "AND NOT is_tombstone) OR (expected_version IS NULL)) AND (NOT (event_kind "
    "= 'state_correction' AND NOT is_tombstone) OR (expected_version IS NULL)) "
    "AND (NOT (is_tombstone) OR (expected_version IS NULL)) AND (NOT "
    "(event_kind = 'play_change') OR (expected_version IS NOT NULL)) AND "
    "(NOT (event_kind = 'play_delete') OR (expected_version IS NOT NULL)) AND "
    "(NOT (event_kind = 'substitution_change') OR (expected_version IS NOT NULL))"
)

_LEGACY_STATE_DIFF_CHECK = (
    "(event_kind <> 'play_input' OR state_diff IS NOT NULL) AND "
    "(event_kind NOT IN ('play_change', 'play_delete', "
    "'substitution_change') OR state_diff IS NULL)"
)
_LEGACY_TOMBSTONE_CHECK = (
    "(NOT is_tombstone OR "
    "(d1 IS NOT NULL AND d2 IS NULL AND state_diff IS NULL)) AND "
    "(NOT is_tombstone OR event_kind NOT IN "
    "('play_change', 'play_delete', 'substitution_change')) AND "
    "(NOT is_tombstone OR payload = '{}'::jsonb)"
)


def upgrade() -> None:
    """既存 2 本を C12 生成式へ置換し、V6・V10・V11 の 3 本を足す。"""
    op.drop_constraint(
        "ck_operation_events_state_diff_by_kind",
        "operation_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_operation_events_tombstone",
        "operation_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operation_events_state_diff_by_kind",
        "operation_events",
        _STATE_DIFF_CHECK,
    )
    op.create_check_constraint(
        "ck_operation_events_tombstone",
        "operation_events",
        _TOMBSTONE_CHECK,
    )
    op.create_check_constraint(
        "ck_operation_events_d2_by_kind",
        "operation_events",
        _D2_CHECK,
    )
    op.create_check_constraint(
        "ck_operation_events_target_by_kind",
        "operation_events",
        _TARGET_CHECK,
    )
    op.create_check_constraint(
        "ck_operation_events_expected_version_by_kind",
        "operation_events",
        _EXPECTED_VERSION_CHECK,
    )


def downgrade() -> None:
    """C12 の 5 本を外し、既存 2 本を 0025 時点の式へ正確に戻す。"""
    op.drop_constraint(
        "ck_operation_events_expected_version_by_kind",
        "operation_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_operation_events_target_by_kind",
        "operation_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_operation_events_d2_by_kind",
        "operation_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_operation_events_tombstone",
        "operation_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_operation_events_state_diff_by_kind",
        "operation_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operation_events_state_diff_by_kind",
        "operation_events",
        _LEGACY_STATE_DIFF_CHECK,
    )
    op.create_check_constraint(
        "ck_operation_events_tombstone",
        "operation_events",
        _LEGACY_TOMBSTONE_CHECK,
    )
