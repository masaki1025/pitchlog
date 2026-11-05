"""取消の接続spikeの内容検証本体。

ポートの静的検査対象外。content phase の制限された read token ではなく、
同じ取引の handle から対象イベント・水位を読み、正式 artifact で再計算する。
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.spike_undo_artifact import invoke_undo_artifact
from pitchlog.sync.spike_undo_ports import (
    _event_row,
    _generation,
    _mapping,
    _same,
    _snapshot,
)


def validate_spike_undo(
    handle: object, event: SyncEvent, writer: PortWriter
) -> tuple[bool, str | None]:
    """直前の確定プレイ 1 件だけを対象に受理可否を返す。"""
    try:
        if type(handle) is not _TenantTransaction:
            return False, "取消の取引文脈を確認できません"
        if type(writer) is not PortWriter:
            return False, "取消のwriter文脈を確認できません"
        game_id = UUID(event.game_id)
        generation, watermark = _generation(writer, game_id)
        reference = _mapping(event.v10)
        if reference is None:
            return False, "取消対象の参照がありません"
        target_d1 = reference.get("d1")
        if type(event.d1) is not int or event.d1 != watermark + 1:
            return False, "取消の連番が現在水位の次ではありません"
        if type(target_d1) is not int or target_d1 != watermark:
            return False, "取消対象は直前の操作ではありません"
        target = _event_row(writer, game_id, generation, target_d1)
        if target is None:
            return False, "取消対象が保存されていません"
        if (
            target.get("event_kind") != "play_input"
            or target.get("is_tombstone") is not False
            or target.get("replaced_at") is not None
            or target.get("retired_at") is not None
        ):
            return False, "取消対象は取消可能な確定プレイではありません"
        snapshot = _snapshot(target.get("payload"))
        if snapshot is None:
            return False, "取消対象の履歴差分を読めません"
        after = _mapping(snapshot.get("after"))
        entry = snapshot.get("entry")
        if after is None or not isinstance(entry, Mapping):
            return False, "取消対象の状態または履歴行が不正です"
        result = invoke_undo_artifact(after, [entry])
        if result is None:
            return False, "正式取消計算が失敗しました"
        if result.get("operationResult") != "applied":
            return False, "正式取消計算が適用ではありません"
        expected = _payload_result(event)
        if expected is None:
            return False, "取消結果の封筒が不正です"
        if expected.get("operationResult") != "applied":
            return False, "取消結果が適用ではありません"
        history_effect = _mapping(expected.get("historyEffect"))
        if history_effect is None or history_effect.get("pops") != "1":
            return False, "取消の履歴効果が不正です"
        if not _same(expected.get("after"), result.get("after")):
            return False, "取消結果が正式計算と一致しません"
        if not _same(
            expected.get("historyContext"), result.get("historyContext")
        ):
            return False, "取消後の履歴文脈が正式計算と一致しません"
        return True, None
    except Exception:
        # 原値・資格・DB例外を外へ出さない。
        return False, "取消の内容を確認できません"


def _payload_result(event: SyncEvent) -> Mapping[str, object] | None:
    """V7 の取消spike封筒と対象参照を読む。"""
    payload = _mapping(event.v7)
    target = _mapping(event.v10)
    if payload is None or target is None:
        return None
    if payload.get("formatVersion") != "undo-connection-spike-v1":
        return None
    if not _same(payload.get("target"), dict(target)):
        return None
    return _mapping(payload.get("result"))


__all__ = ("validate_spike_undo",)
