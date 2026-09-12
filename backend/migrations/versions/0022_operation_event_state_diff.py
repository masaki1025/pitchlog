"""操作イベントの種別条件と NULL 可な複合 FK の MATCH 方式を是正する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_operation_event_state_diff"
down_revision: str | Sequence[str] | None = "0021_medical_note_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT_KIND_CHECK = (
    "event_kind IN ('play_input', 'undo', 'substitution', 'tiebreak_start', "
    "'game_end_declaration', 'player_registration', 'play_change', "
    "'play_delete', 'substitution_change')"
)
_STATE_DIFF_BY_EVENT_KIND_CHECK = (
    "(event_kind <> 'play_input' OR state_diff IS NOT NULL) AND "
    "(event_kind NOT IN ('play_change', 'play_delete', "
    "'substitution_change') OR state_diff IS NULL)"
)
_TOMBSTONE_CHECK = (
    "(NOT is_tombstone OR "
    "(d1 IS NOT NULL AND d2 IS NULL AND state_diff IS NULL)) AND "
    "(NOT is_tombstone OR event_kind NOT IN "
    "('play_change', 'play_delete', 'substitution_change')) AND "
    "(NOT is_tombstone OR payload = '{}'::jsonb)"
)
_TARGET_PAIR_CHECK = "(target_generation IS NULL) = (target_d1 IS NULL)"
_OPTIONAL_TENANT_FOREIGN_KEYS = (
    (
        "fk_players_roster_label",
        "players",
        "tenant_vocabularies",
        "roster_label_key",
        "key",
    ),
    (
        "fk_evacuated_event_originals_imported_event",
        "evacuated_event_originals",
        "operation_events",
        "imported_event_id",
        "id",
    ),
    (
        "fk_pdf_export_records_team",
        "pdf_export_records",
        "team_records",
        "team_record_id",
        "id",
    ),
    (
        "fk_pdf_export_records_player",
        "pdf_export_records",
        "players",
        "player_id",
        "id",
    ),
)


def _drop_optional_tenant_foreign_keys() -> None:
    """テナント列と任意列を組み合わせた FK 4 本を削除する。"""
    for name, source_table, _, _, _ in _OPTIONAL_TENANT_FOREIGN_KEYS:
        op.drop_constraint(name, source_table, type_="foreignkey")


def _create_optional_tenant_foreign_keys(*, match: str) -> None:
    """テナント列と任意列を組み合わせた FK 4 本を作る。"""
    for (
        name,
        source_table,
        target_table,
        source_column,
        target_column,
    ) in _OPTIONAL_TENANT_FOREIGN_KEYS:
        op.create_foreign_key(
            name,
            source_table,
            target_table,
            ["tenant_id", source_column],
            ["tenant_id", target_column],
            ondelete="NO ACTION",
            match=match,
        )


def _create_nullable_slot_foreign_keys(*, match: str) -> None:
    """NULL 可のスロット参照 2 本を指定した MATCH 方式で作る。"""
    op.create_foreign_key(
        "fk_operation_events_slot",
        "operation_events",
        "event_slots",
        ["tenant_id", "game_id", "generation", "d1"],
        ["tenant_id", "game_id", "generation", "d1"],
        ondelete="NO ACTION",
        match=match,
    )
    op.create_foreign_key(
        "fk_operation_events_target",
        "operation_events",
        "event_slots",
        ["tenant_id", "game_id", "target_generation", "target_d1"],
        ["tenant_id", "game_id", "generation", "d1"],
        ondelete="NO ACTION",
        match=match,
    )


def upgrade() -> None:
    """任意参照を SIMPLE にし、V5・V8・V9 の種別条件を強制する。"""
    _drop_optional_tenant_foreign_keys()
    _create_optional_tenant_foreign_keys(match="SIMPLE")
    op.drop_constraint(
        "fk_operation_events_target",
        "operation_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_operation_events_slot",
        "operation_events",
        type_="foreignkey",
    )
    op.create_check_constraint(
        "ck_operation_events_target_pair",
        "operation_events",
        _TARGET_PAIR_CHECK,
    )
    _create_nullable_slot_foreign_keys(match="SIMPLE")
    op.add_column(
        "operation_events",
        sa.Column(
            "is_tombstone",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "ck_operation_events_event_kind",
        "operation_events",
        _EVENT_KIND_CHECK,
    )
    op.create_check_constraint(
        "ck_operation_events_state_diff_by_kind",
        "operation_events",
        _STATE_DIFF_BY_EVENT_KIND_CHECK,
    )
    op.create_check_constraint(
        "ck_operation_events_tombstone",
        "operation_events",
        _TOMBSTONE_CHECK,
    )


def downgrade() -> None:
    """種別条件と墓標列を撤去し、任意参照を FULL に戻す。"""
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
    op.drop_constraint(
        "ck_operation_events_event_kind",
        "operation_events",
        type_="check",
    )
    op.drop_column("operation_events", "is_tombstone")
    op.drop_constraint(
        "fk_operation_events_target",
        "operation_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_operation_events_slot",
        "operation_events",
        type_="foreignkey",
    )
    _create_nullable_slot_foreign_keys(match="FULL")
    op.drop_constraint(
        "ck_operation_events_target_pair",
        "operation_events",
        type_="check",
    )
    _drop_optional_tenant_foreign_keys()
    _create_optional_tenant_foreign_keys(match="FULL")
