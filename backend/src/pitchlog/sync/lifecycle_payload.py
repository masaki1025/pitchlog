"""終了と追記再開を偽称せず、D1/D2/V7の閉提案を読む。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from jsonschema.exceptions import ValidationError

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.sync.idempotency import _json_value
from pitchlog.sync.model import _MAX_SAFE_INTEGER, ABSENT, SyncEvent
from pitchlog.sync.ordering import _MAX_D2
from pitchlog.sync.undo_payload import _load


class LifecyclePayloadError(ValueError):
    """内容不一致だけを表し、権限/DB不明を隠さない。"""


def _uuid(raw):
    try:
        if type(raw) is not str or str(UUID(raw)) != raw:
            raise ValueError
    except ValueError as error:
        raise LifecyclePayloadError("終了再開のUUIDが不正です") from error
    return raw


def _positive(raw):
    return (
        type(raw) is str
        and raw.isascii()
        and raw.isdecimal()
        and not raw.startswith("0")
    )


def _read(raw):
    try:
        v = _load(raw)
    except (ValueError, TypeError) as error:
        raise LifecyclePayloadError("終了再開のJSONが不正です") from error
    if type(v) is not dict or set(v) != {
        "formatVersion",
        "action",
        "checkpointRef",
        "target",
        "event",
    }:
        raise LifecyclePayloadError("終了再開のpayload全memberが不一致です")
    if (
        v["formatVersion"] != "native-game-lifecycle-v1"
        or type(v["action"]) is not str
        or v["action"] not in {"end", "reopen"}
    ):
        raise LifecyclePayloadError("終了再開の版/操作が不一致です")
    ids = v["event"]
    if type(ids) is not dict or set(ids) != {"eventId", "receiptId"}:
        raise LifecyclePayloadError("終了再開のevent予約値が不一致です")
    _uuid(ids["eventId"])
    _uuid(ids["receiptId"])
    _checkpoint_ref(v["checkpointRef"])
    target = v["target"]
    if v["action"] == "end":
        if target is not None:
            raise LifecyclePayloadError("終了宣言は再開対象を持ちません")
    else:
        _reopen_target(target)
    return v


def _closed(value, fields):
    """観測原値を補修せず、閉unionの全memberを検査する。"""
    if type(value) is not dict or set(value) != fields:
        raise LifecyclePayloadError("終了再開の参照memberが不一致です")


def _position(value):
    """既V3の参照wire域を使い、真正世代の資格を発行しない。"""
    from pitchlog.sync.undo_payload import _validate_value

    try:
        _validate_value(value["d4"], "Generation")
        _validate_value(value["d1"], "WireD1")
    except (ValueError, ValidationError) as error:
        raise LifecyclePayloadError("終了再開の先行位置が不正です") from error
    _uuid(value["d5"])


def _checkpoint_ref(ref):
    """確定CP・受理prefix・未送信直前位置を混同しない。"""
    if type(ref) is not dict:
        raise LifecyclePayloadError("終了再開のCP参照が不正です")
    kind = ref.get("kind")
    if kind == "confirmed":
        _closed(ref, {"kind", "id", "revision", "digest"})
    elif kind == "confirmed_prefix":
        _closed(ref, {"kind", "id", "revision", "digest", "d4", "d1", "d5"})
        _position(ref)
    elif kind == "queued_predecessor":
        _closed(ref, {"kind", "d4", "d1", "d5"})
        _position(ref)
        return
    else:
        raise LifecyclePayloadError("終了再開の参照種別が不正です")
    _uuid(ref["id"])
    digest = ref["digest"]
    if (
        not _positive(ref["revision"])
        or type(digest) is not str
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise LifecyclePayloadError("終了再開のCP版/指紋が不一致です")


def _reopen_target(target):
    """予約終了を確定終了版へ推測変換しない。"""
    if type(target) is not dict:
        raise LifecyclePayloadError("追記再開は終了参照を明示します")
    kind = target.get("kind")
    if kind == "confirmed":
        _closed(target, {"kind", "version", "eventId", "receiptId"})
        if not _positive(target["version"]):
            raise LifecyclePayloadError("追記再開の終了版が不正です")
    elif kind == "queued_end":
        _closed(target, {"kind", "d4", "d1", "d5", "eventId", "receiptId"})
        _position(target)
    else:
        raise LifecyclePayloadError("追記再開の終了参照種別が不正です")
    _uuid(target["eventId"])
    _uuid(target["receiptId"])


@dataclass(frozen=True, slots=True)
class LifecyclePayload:
    """純入力の不変値。実source資格ではない。"""

    json: str

    def __post_init__(self):
        """constructorの抜け道を作らない。"""
        _read(self.json)

    def to_wire(self):
        """変更可能な共有参照を返さない。"""
        return _read(self.json)


def read_lifecycle_event(event):
    """再開を終了宣言と偽称せず、両者の論理位置を厳密に検査する。"""
    if (
        type(event) is not SyncEvent
        or type(event.d1) is not int
        or not 0 < event.d1 <= _MAX_SAFE_INTEGER
        or type(event.v6) is not int
        or not 0 <= event.v6 <= _MAX_D2
        or event.v8 is not ABSENT
        or event.v9 is not ABSENT
        or event.v10 is not ABSENT
        or event.v11 is not ABSENT
    ):
        raise LifecyclePayloadError("終了再開のD1/D2/従属項目が不一致です")
    from pitchlog.sync.undo_payload import _validate_value

    try:
        _validate_value(event.d4, "Generation")
        raw = _canonical_json(_json_value(event.v7))
    except (TypeError, ValueError, ValidationError) as error:
        raise LifecyclePayloadError("終了再開のwire値が不正です") from error
    value = _read(raw)
    if (
        event.v5
        != {"end": "game_end_declaration", "reopen": "game_reopen"}[value["action"]]
    ):
        raise LifecyclePayloadError("終了と再開の原イベント種別が不一致です")
    return LifecyclePayload(_canonical_json(value))
