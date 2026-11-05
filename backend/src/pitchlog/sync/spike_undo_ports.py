"""取消の接続spike専用ポート。

製品ポートではない。実writer・実記録権・同期核の同一取引の中で、取消の
内容を正式 artifact（``applyUndo``）で再計算し、保存された結果と照合する。
投影は監査行を消さず、挿入済み取消行と対象行の存在だけを確認する。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    OperationEventReadToken,
    RecordingGenerationReadToken,
    _SyncToken,
)

# operation_events の読取列順。モデル import はポート実装の静的検査で禁止されるため、
# 正本モデルの列順を値として固定する（一致は backend 試験で照合する）。
EVENT_COLUMNS = (
    "id",
    "game_id",
    "generation",
    "d1",
    "d2",
    "d5",
    "ledger_kind",
    "event_kind",
    "payload",
    "state_diff",
    "is_tombstone",
    "replaced_at",
    "target_generation",
    "target_d1",
    "expected_version",
    "change_order",
    "legacy_row_identifier",
    "migration_unverified",
    "tenant_id",
    "import_batch_id",
    "retired_at",
)
_EVENT_COLUMNS = EVENT_COLUMNS

_UNDO_FORMAT = "undo-connection-spike-v1"
_ERROR = "取消の接続spikeを確認できません"


def _cell(row: tuple[object, ...], columns: tuple[str, ...], name: str) -> object:
    """同期核と同じ列順規約で 1 値を読む。"""
    if len(row) != len(columns):
        raise RuntimeError("取消spikeの読み取り列数が正本と異なる")
    return row[columns.index(name)]


def _one(result: TenantOperationResult) -> tuple[object, ...]:
    """一意であるべき行の欠落・重複を拒否する。"""
    if type(result) is not TenantOperationResult or len(result.rows) != 1:
        raise RuntimeError(_ERROR)
    return result.rows[0]


def _event_row(
    writer: PortWriter, game_id: UUID, generation: int, d1: int
) -> dict[str, object] | None:
    """現行世代の D1 行を 1 件だけ読む。"""
    rows = writer.run(OperationEventReadToken(game_id, generation, d1)).rows
    if len(rows) != 1:
        return None
    row = rows[0]
    return {name: _cell(row, _EVENT_COLUMNS, name) for name in _EVENT_COLUMNS}


def _generation(writer: PortWriter, game_id: UUID) -> tuple[int, int]:
    """現行世代番号と確定水位を返す。"""
    row = _one(writer.run(RecordingGenerationReadToken(game_id)))
    generation = _cell(row, RECORDING_GENERATION_READ_COLUMNS, "generation")
    watermark = _cell(row, RECORDING_GENERATION_READ_COLUMNS, "confirmed_watermark")
    if type(generation) is not int or type(watermark) is not int:
        raise RuntimeError(_ERROR)
    return generation, watermark


def _same(left: object, right: object) -> bool:
    """JSON 値の同一性を再帰的に比較する（json import を使わない）。"""
    if left is None or right is None:
        return left is None and right is None
    if type(left) is bool or type(right) is bool:
        return type(left) is bool and type(right) is bool and left == right
    if type(left) in (int, str) or type(right) in (int, str):
        return type(left) is type(right) and left == right
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return False
        return all(_same(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    return False


def _snapshot(payload: object) -> dict[str, object] | None:
    """保存済み V7 から before/after/履歴行を取り出す。

    保存時に正式 artifact で検証済みの応答をそのまま読み、第二実装で
    計算し直さない。差分・履歴行の形は保存時の形式ごとに固定する。
    """
    if not isinstance(payload, Mapping):
        return None
    format_version = payload.get("formatVersion")
    calculation = payload.get("calculation")
    if not isinstance(calculation, Mapping):
        return None
    request = calculation.get("request")
    response = calculation.get("response")
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        return None
    t1_request = request.get("t1")
    if not isinstance(t1_request, Mapping):
        return None
    before = t1_request.get("before")
    value = response.get("value")
    if not isinstance(value, Mapping):
        return None
    if format_version == "first-ball-play-v1":
        after = value.get("after")
        history = value.get("historyContext")
        if not isinstance(after, Mapping) or not isinstance(history, list):
            return None
        if len(history) != 1 or not isinstance(history[0], Mapping):
            return None
        return {"before": before, "after": after, "entry": history[0]}
    if format_version in {
        "ordinary-pitch-play-v1",
        "play-prefix-play-v2",
        "play-prefix-play-v3",
    }:
        t1 = value.get("t1")
        after = t1.get("after") if isinstance(t1, Mapping) else None
        entry = value.get("newHistoryEntry")
        if not isinstance(after, Mapping) or not isinstance(entry, Mapping):
            return None
        return {"before": before, "after": after, "entry": entry}
    return None


type UndoInvoker = Callable[
    [Mapping[str, object], list[object]], Mapping[str, object] | None
]


def _mapping(value: object) -> Mapping[str, object] | None:
    """JSON object だけを返す。"""
    return value if isinstance(value, Mapping) else None


def _payload_result(event: SyncEvent) -> Mapping[str, object] | None:
    """V7 の取消spike封筒と対象参照を読む。"""
    payload = _mapping(event.v7)
    target = _mapping(event.v10)
    if payload is None or target is None:
        return None
    if payload.get("formatVersion") != _UNDO_FORMAT:
        return None
    if not _same(payload.get("target"), dict(target)):
        return None
    result = _mapping(payload.get("result"))
    return result


@dataclass(frozen=True, slots=True)
class SpikeUndoValidationToken(_SyncToken):
    """content phase から実取引の取消検証本体を呼ぶ命令。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent = field(repr=False)
    writer: object = field(repr=False)
    _capability_id = "CAP:operation_events:read"

    def __post_init__(self) -> None:
        """UUID/元参照を変換せず照合する。"""
        if (
            type(self.game_id) is not UUID
            or type(self.d5) is not UUID
            or type(self.event) is not SyncEvent
            or str(self.game_id) != self.event.game_id
            or str(self.d5) != self.event.d5
        ):
            raise ValueError("取消内容命令の参照が不一致")


@final
class SpikeUndoContentValidationPort:
    """実DBの対象行と正式 artifact の取消結果を同一取引で照合する。"""

    def validate(
        self, event: SyncEvent, writer: PortWriter
    ) -> tuple[bool, str | None]:
        """内容検証本体へ元event/同writerを渡し、自由boolを受け取らない。"""
        result = writer.run(
            SpikeUndoValidationToken(
                UUID(event.game_id), UUID(event.d5), event, writer
            )
        )
        if (
            type(result) is not TenantOperationResult
            or type(result.rows) is not tuple
            or len(result.rows) != 1
            or len(result.rows[0]) != 2
        ):
            raise RuntimeError(_ERROR)
        accepted, reason = result.rows[0]
        if (
            type(accepted) is not bool
            or (accepted and reason is not None)
            or (not accepted and (type(reason) is not str or not reason))
        ):
            raise RuntimeError(_ERROR)
        if accepted:
            return True, None
        if type(reason) is not str:
            raise RuntimeError(_ERROR)
        return False, reason


@final
class SpikeUndoProjectionPort:
    """監査行を残したまま、挿入済み取消行と対象行の存在を確認する。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """物理削除をせず、同じ取引内の行だけを確認する。"""
        game_id = UUID(event.game_id)
        generation, watermark = _generation(writer, game_id)
        if type(event.d1) is not int or event.d1 != watermark:
            raise RuntimeError(_ERROR)
        inserted = _event_row(writer, game_id, generation, event.d1)
        reference = _mapping(event.v10)
        if inserted is None or reference is None:
            raise RuntimeError(_ERROR)
        target_d1 = reference.get("d1")
        if type(target_d1) is not int:
            raise RuntimeError(_ERROR)
        if (
            inserted.get("event_kind") != "undo"
            or inserted.get("target_generation") != generation
            or inserted.get("target_d1") != target_d1
            or inserted.get("is_tombstone") is not False
            or inserted.get("replaced_at") is not None
            or inserted.get("retired_at") is not None
        ):
            raise RuntimeError(_ERROR)
        target = _event_row(writer, game_id, generation, target_d1)
        if target is None or target.get("retired_at") is not None:
            raise RuntimeError(_ERROR)
        if target.get("event_kind") != "play_input":
            raise RuntimeError(_ERROR)


__all__ = (
    "SpikeUndoContentValidationPort",
    "SpikeUndoProjectionPort",
    "SpikeUndoValidationToken",
)

