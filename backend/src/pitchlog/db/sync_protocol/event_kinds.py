"""正本の参加区分と操作イベント種別リテラルの対応を定義する。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class ParticipationBinding(StrEnum):
    """参加区分が操作イベント行のどの要素へ写るか。"""

    EVENT_KIND = "V5"
    CONDITIONAL_EVENT_KIND = "V5(採用時)"
    TOMBSTONE_STATE = "V9(墓標)"
    REVISION_STATE = "V9(改訂)"


@dataclass(frozen=True)
class OperationEventParticipation:
    """参加区分 1 件に対応する V5 または V9 の表現。"""

    participation_number: int
    canonical_name: str
    binding: ParticipationBinding
    event_kind_literal: str | None


OPERATION_EVENT_PARTICIPATIONS = (
    OperationEventParticipation(
        1, "毎球入力", ParticipationBinding.EVENT_KIND, "play_input"
    ),
    OperationEventParticipation(2, "undo", ParticipationBinding.EVENT_KIND, "undo"),
    OperationEventParticipation(
        3, "選手交代", ParticipationBinding.EVENT_KIND, "substitution"
    ),
    OperationEventParticipation(
        4, "タイブレーク開始", ParticipationBinding.EVENT_KIND, "tiebreak_start"
    ),
    OperationEventParticipation(
        5,
        "試合終了宣言",
        ParticipationBinding.EVENT_KIND,
        "game_end_declaration",
    ),
    OperationEventParticipation(
        6, "選手のその場登録", ParticipationBinding.EVENT_KIND, "player_registration"
    ),
    OperationEventParticipation(
        7,
        "状態補正",
        ParticipationBinding.CONDITIONAL_EVENT_KIND,
        "state_correction",
    ),
    OperationEventParticipation(8, "墓標", ParticipationBinding.TOMBSTONE_STATE, None),
    OperationEventParticipation(9, "改訂版", ParticipationBinding.REVISION_STATE, None),
    OperationEventParticipation(
        10, "プレイの修正", ParticipationBinding.EVENT_KIND, "play_change"
    ),
    OperationEventParticipation(
        11, "プレイ行の論理削除", ParticipationBinding.EVENT_KIND, "play_delete"
    ),
    OperationEventParticipation(
        12,
        "交代イベントの修正",
        ParticipationBinding.EVENT_KIND,
        "substitution_change",
    ),
)
EVENT_KIND_BY_CANONICAL_NAME = MappingProxyType(
    {
        participation.canonical_name: participation.event_kind_literal
        for participation in OPERATION_EVENT_PARTICIPATIONS
        if participation.event_kind_literal is not None
    }
)
EVENT_KIND_LITERALS = tuple(
    participation.event_kind_literal
    for participation in OPERATION_EVENT_PARTICIPATIONS
    if participation.binding is ParticipationBinding.EVENT_KIND
    and participation.event_kind_literal is not None
)
CONDITIONAL_EVENT_KIND_LITERALS = tuple(
    participation.event_kind_literal
    for participation in OPERATION_EVENT_PARTICIPATIONS
    if participation.binding is ParticipationBinding.CONDITIONAL_EVENT_KIND
    and participation.event_kind_literal is not None
)
CHANGE_EVENT_KIND_LITERALS = tuple(
    EVENT_KIND_BY_CANONICAL_NAME[name]
    for name in ("プレイの修正", "プレイ行の論理削除", "交代イベントの修正")
)
PLAY_INPUT_EVENT_KIND = EVENT_KIND_BY_CANONICAL_NAME["毎球入力"]
STATE_CORRECTION_EVENT_KIND = EVENT_KIND_BY_CANONICAL_NAME["状態補正"]


def _sql_literal_list(literals: tuple[str, ...]) -> str:
    """信頼済みの種別リテラルを CHECK 用の SQL リストへ整形する。"""
    return ", ".join(f"'{literal}'" for literal in literals)


EVENT_KIND_CHECK_EXPRESSION = (
    f"event_kind IN ({_sql_literal_list(EVENT_KIND_LITERALS)})"
)
STATE_DIFF_BY_EVENT_KIND_CHECK_EXPRESSION = (
    f"(event_kind <> '{PLAY_INPUT_EVENT_KIND}' OR state_diff IS NOT NULL) AND "
    f"(event_kind NOT IN ({_sql_literal_list(CHANGE_EVENT_KIND_LITERALS)}) "
    "OR state_diff IS NULL)"
)
TOMBSTONE_CHECK_EXPRESSION = (
    "(NOT is_tombstone OR "
    "(d1 IS NOT NULL AND d2 IS NULL AND state_diff IS NULL)) AND "
    f"(NOT is_tombstone OR event_kind NOT IN "
    f"({_sql_literal_list(CHANGE_EVENT_KIND_LITERALS)})) AND "
    "(NOT is_tombstone OR payload = '{}'::jsonb)"
)
