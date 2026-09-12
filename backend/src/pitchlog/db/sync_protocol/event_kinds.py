"""正本の参加区分と操作イベント種別リテラルの対応を定義する。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import product
from types import MappingProxyType

from pitchlog.db.model_metadata import is_task_handoff_id


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


class C12Value(StrEnum):
    """C12 が種別条件付きで扱うイベント値。"""

    V2 = "V2"
    V3 = "V3"
    V6 = "V6"
    V8 = "V8"
    V9 = "V9"
    V10 = "V10"
    V11 = "V11"


class C12Requirement(StrEnum):
    """参加区分ごとの値の要求区分。"""

    REQUIRED = "必須"
    FORBIDDEN = "禁止"
    OPTIONAL = "任意"
    UNREPRESENTABLE = "表現不能"


@dataclass(frozen=True)
class C12Cell:
    """参加区分 1 件と C12 値 1 件の契約。"""

    participation: OperationEventParticipation
    value: C12Value
    requirement: C12Requirement
    row_predicate: str
    carrier_columns: tuple[str, ...]
    source: str
    unrepresentable_reason: str | None = None
    unrepresentable_handoff: str | None = None

    def __post_init__(self) -> None:
        """表現不能セルの理由と受け取り先を完全な組として強制する。"""
        if self.requirement is C12Requirement.UNREPRESENTABLE:
            if not self.unrepresentable_reason:
                raise ValueError("表現不能セルには理由が必要です")
            if not self.unrepresentable_handoff:
                raise ValueError("表現不能セルには受け取り先 ID が必要です")
            if not is_task_handoff_id(self.unrepresentable_handoff):
                raise ValueError(
                    "表現不能セルの受け取り先 ID は TSK-<数字> 形式で指定してください"
                )
        elif (
            self.unrepresentable_reason is not None
            or self.unrepresentable_handoff is not None
        ):
            raise ValueError("表現不能でないセルに理由・受け取り先は指定できません")
        if not self.row_predicate:
            raise ValueError("C12 セルには行述語が必要です")
        if len(self.carrier_columns) != len(set(self.carrier_columns)):
            raise ValueError("C12 セルの担い手列は重複できません")
        if ":" not in self.source:
            raise ValueError("C12 セルの典拠はファイル:節の形式で指定してください")


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
UNDO_EVENT_KIND = EVENT_KIND_BY_CANONICAL_NAME["undo"]

C12_VALUES = tuple(C12Value)
_LOGICAL_POSITION_EVENT_KINDS = frozenset(
    EVENT_KIND_BY_CANONICAL_NAME[name]
    for name in ("毎球入力", "選手交代", "タイブレーク開始", "試合終了宣言")
)
_C12_CARRIER_COLUMNS = MappingProxyType(
    {
        C12Value.V2: ("d1",),
        C12Value.V3: ("generation",),
        C12Value.V6: ("d2",),
        C12Value.V8: ("state_diff",),
        C12Value.V10: ("target_generation", "target_d1"),
        C12Value.V11: ("expected_version",),
    }
)
_C12_SOURCE_BY_VALUE = MappingProxyType(
    {
        C12Value.V2: "sync-protocol.md:4-3",
        C12Value.V3: "sync-protocol.md:4-3",
        C12Value.V6: "data-model.md:5-3",
        C12Value.V8: "sync-protocol.md:4-3",
        C12Value.V9: "sync-protocol.md:4-3",
        C12Value.V10: "sync-protocol.md:4-3",
        C12Value.V11: "sync-protocol.md:4-3",
    }
)
_FOLLOW_UP_B = "TSK-373"
_P58_HANDOFF = "TSK-375"
_REVISION_ROW_AMBIGUITY_REASON = (
    "改訂版を名指す列が無く、replaced_at は置換された旧版側に立つため "
    "event_kind だけでは通常版と区別できない"
)
_V10_TOMBSTONE_REASON = "墓標の V10 の物理表現を正本が定めていない"
_STATE_CORRECTION_REASON = (
    "P-58 が状態補正(#7)の採否を Must 前提として組み込むことを禁じている"
)
_UNREPRESENTABLE_ROW_PREDICATE = "FALSE"


def _is_change_event(participation: OperationEventParticipation) -> bool:
    """参加区分が D1 を持たない変更イベントなら真を返す。"""
    return participation.event_kind_literal in CHANGE_EVENT_KIND_LITERALS


def _c12_row_predicate(participation: OperationEventParticipation) -> str:
    """D-1 を反映した参加区分の物理行述語を返す。"""
    if participation.binding is ParticipationBinding.TOMBSTONE_STATE:
        return "is_tombstone"
    if participation.binding is ParticipationBinding.REVISION_STATE:
        # 改訂版を名指す物理列はない。FALSE は式へ接続しない表現不能セルの明示値。
        return _UNREPRESENTABLE_ROW_PREDICATE
    literal = participation.event_kind_literal
    if literal is None:
        raise ValueError(f"参加区分 #{participation.participation_number} に表現がない")
    predicate = f"event_kind = '{literal}'"
    if not _is_change_event(participation):
        return f"{predicate} AND NOT is_tombstone"
    return predicate


def _c12_requirement(
    participation: OperationEventParticipation, value: C12Value
) -> tuple[C12Requirement, str | None, str | None]:
    """正本の意味規則から要求区分・未表現理由・受け取り先を導く。"""
    is_change = _is_change_event(participation)
    is_tombstone = participation.binding is ParticipationBinding.TOMBSTONE_STATE
    is_revision = participation.binding is ParticipationBinding.REVISION_STATE
    literal = participation.event_kind_literal

    if is_revision:
        return (
            C12Requirement.UNREPRESENTABLE,
            _REVISION_ROW_AMBIGUITY_REASON,
            _FOLLOW_UP_B,
        )
    if value in {C12Value.V2, C12Value.V3}:
        requirement = C12Requirement.FORBIDDEN if is_change else C12Requirement.REQUIRED
        return requirement, None, None
    if value is C12Value.V6:
        if participation.binding is ParticipationBinding.CONDITIONAL_EVENT_KIND:
            return (
                C12Requirement.UNREPRESENTABLE,
                _STATE_CORRECTION_REASON,
                _P58_HANDOFF,
            )
        requirement = (
            C12Requirement.REQUIRED
            if literal in _LOGICAL_POSITION_EVENT_KINDS
            else C12Requirement.FORBIDDEN
        )
        return requirement, None, None
    if value is C12Value.V8:
        # sync-protocol.md:4-6 は、採用状態を種別集合で表し、採用された
        # 状態補正イベント自身には V8 を必須としている。
        requirement = (
            C12Requirement.REQUIRED
            if literal in {PLAY_INPUT_EVENT_KIND, STATE_CORRECTION_EVENT_KIND}
            else C12Requirement.FORBIDDEN
        )
        return requirement, None, None
    if value is C12Value.V9:
        requirement = (
            C12Requirement.REQUIRED if is_tombstone else C12Requirement.FORBIDDEN
        )
        return requirement, None, None
    if value is C12Value.V10:
        if is_tombstone:
            return (
                C12Requirement.UNREPRESENTABLE,
                _V10_TOMBSTONE_REASON,
                _FOLLOW_UP_B,
            )
        if is_change or literal == UNDO_EVENT_KIND:
            return C12Requirement.REQUIRED, None, None
        return (
            C12Requirement.UNREPRESENTABLE,
            _REVISION_ROW_AMBIGUITY_REASON,
            _FOLLOW_UP_B,
        )
    requirement = C12Requirement.REQUIRED if is_change else C12Requirement.FORBIDDEN
    return requirement, None, None


def _c12_carrier_columns(
    participation: OperationEventParticipation, value: C12Value
) -> tuple[str, ...]:
    """参加区分と値に対応する物理列を返す。"""
    if value is C12Value.V9:
        if participation.binding is ParticipationBinding.REVISION_STATE:
            return ()
        return ("is_tombstone",)
    if (
        value is C12Value.V10
        and participation.binding is ParticipationBinding.TOMBSTONE_STATE
    ):
        return ()
    return _C12_CARRIER_COLUMNS[value]


def _build_c12_cell(
    participation: OperationEventParticipation, value: C12Value
) -> C12Cell:
    """参加区分と値から C12 セルを 1 件構築する。"""
    requirement, reason, handoff = _c12_requirement(participation, value)
    return C12Cell(
        participation=participation,
        value=value,
        requirement=requirement,
        row_predicate=_c12_row_predicate(participation),
        carrier_columns=_c12_carrier_columns(participation, value),
        source=(
            "sync-protocol.md:4-6"
            if value is C12Value.V8
            and participation.binding is ParticipationBinding.CONDITIONAL_EVENT_KIND
            else _C12_SOURCE_BY_VALUE[value]
        ),
        unrepresentable_reason=reason,
        unrepresentable_handoff=handoff,
    )


C12_REQUIREMENT_MATRIX = MappingProxyType(
    {
        (participation.participation_number, value): _build_c12_cell(
            participation, value
        )
        for participation, value in product(OPERATION_EVENT_PARTICIPATIONS, C12_VALUES)
    }
)


def validate_c12_requirement_matrix(
    matrix: Mapping[tuple[int, C12Value], C12Cell],
) -> None:
    """マトリクスが参加区分と値の直積を過不足なく覆うことを検査する。"""
    expected_keys = {
        (participation.participation_number, value)
        for participation, value in product(OPERATION_EVENT_PARTICIPATIONS, C12_VALUES)
    }
    actual_keys = set(matrix)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise ValueError(f"C12 セルの母集団が不一致: missing={missing}, extra={extra}")
    for key, cell in matrix.items():
        if key != (cell.participation.participation_number, cell.value):
            raise ValueError(f"C12 セルのキーと内容が不一致: {key}")


def c12_cell_check_expression(cell: C12Cell) -> str | None:
    """強制可能なセルを行述語から CHECK の含意式へ変換する。"""
    if cell.requirement in {
        C12Requirement.OPTIONAL,
        C12Requirement.UNREPRESENTABLE,
    }:
        return None
    if not cell.carrier_columns:
        raise ValueError("必須・禁止セルには担い手列が必要です")
    if cell.value is C12Value.V9 and cell.carrier_columns == ("is_tombstone",):
        # D-1 の通常行述語は既に NOT is_tombstone を含むため、V9 禁止を
        # 重ねた項と、墓標述語へ is_tombstone 必須を重ねた項は恒真になる。
        # 真理値表を読みやすく保つため、どちらも生成しない。
        if (
            cell.requirement is C12Requirement.FORBIDDEN
            and cell.row_predicate.endswith("AND NOT is_tombstone")
        ) or (
            cell.requirement is C12Requirement.REQUIRED
            and cell.row_predicate == "is_tombstone"
        ):
            return None
        carrier_condition = (
            "is_tombstone"
            if cell.requirement is C12Requirement.REQUIRED
            else "NOT is_tombstone"
        )
    else:
        null_test = (
            "IS NOT NULL" if cell.requirement is C12Requirement.REQUIRED else "IS NULL"
        )
        carrier_condition = " AND ".join(
            f"{column} {null_test}" for column in cell.carrier_columns
        )
    return f"(NOT ({cell.row_predicate}) OR ({carrier_condition}))"


def generate_c12_check_expressions(
    matrix: Mapping[tuple[int, C12Value], C12Cell] = C12_REQUIREMENT_MATRIX,
) -> Mapping[C12Value, str]:
    """C12 マトリクスから値ごとの CHECK 式を生成する。"""
    validate_c12_requirement_matrix(matrix)
    expressions: dict[C12Value, str] = {}
    for value in C12_VALUES:
        cell_expressions = tuple(
            expression
            for participation in OPERATION_EVENT_PARTICIPATIONS
            if (
                expression := c12_cell_check_expression(
                    matrix[(participation.participation_number, value)]
                )
            )
            is not None
        )
        expressions[value] = " AND ".join(cell_expressions) or "TRUE"
    return MappingProxyType(expressions)


C12_CHECK_EXPRESSIONS = generate_c12_check_expressions()

# V9 は墓標であること自体の種別条件だけを表す。墓標 payload の空 object 要件は
# C12 の 7 値に含まれないため、既存要件を残して同じ名前の CHECK へ合成する。
C12_TOMBSTONE_CHECK_EXPRESSION = (
    f"({C12_CHECK_EXPRESSIONS[C12Value.V9]}) AND "
    "(NOT is_tombstone OR payload = '{}'::jsonb)"
)


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
