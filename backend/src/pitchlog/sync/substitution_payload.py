"""選手交代P2の閉じたV7を読む。保存資格や計算成功は発行しない。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from re import fullmatch
from typing import Any, cast

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object
from pitchlog.sync.idempotency import _json_value, event_source
from pitchlog.sync.model import ABSENT, SyncEvent


class SubstitutionPayloadError(ValueError):
    """交代の閉値が不一致。入力値・選手情報は理由へ含めない。"""


_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_POSITIVE = r"[1-9][0-9]*"
_DIGEST = r"[0-9a-f]{64}"


def _matches(value: object, pattern: str) -> bool:
    """bool/数値や末尾改行を正準文字列に補完しない。"""
    return type(value) is str and fullmatch(pattern, value) is not None


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    """未知・不足memberをともに閉じる。"""
    if type(value) is not dict or set(value) != keys:
        raise SubstitutionPayloadError("交代のmemberが不一致です")
    return cast("dict[str, Any]", value)


def _operation(value: object) -> None:
    """4種の交代選択肢だけを許す。意味判定は真正保存原本との評価へ委ねる。"""
    if not isinstance(value, Mapping):
        raise SubstitutionPayloadError("交代操作が不一致です")
    if value.get("side") not in ("away", "home"):
        raise SubstitutionPayloadError("交代側が不一致です")
    kind = value.get("kind")
    if kind == "pitcher":
        item = _object(
            value,
            {"kind", "side", "outgoingId", "incomingId", "count", "dh"},
        )
        count = _object(item["count"], {"strikes", "balls"})
        if (
            count["strikes"] not in ("0", "1", "2")
            or count["balls"] not in ("0", "1", "2", "3")
            or item["dh"] not in ("retain", "pitcher-takes-dh-slot")
        ):
            raise SubstitutionPayloadError("投手交代の値が不一致です")
    elif kind == "pinch-hitter":
        item = _object(
            value, {"kind", "side", "outgoingId", "incomingId", "battingSlot"}
        )
        if item["battingSlot"] not in tuple("123456789"):
            raise SubstitutionPayloadError("打順枠が不一致です")
    elif kind == "pinch-runner":
        item = _object(value, {"kind", "side", "outgoingId", "incomingId", "base"})
        if item["base"] not in ("1", "2", "3"):
            raise SubstitutionPayloadError("塁が不一致です")
    elif kind == "defense":
        item = _object(value, {"kind", "side", "changes"})
        changes = item["changes"]
        if type(changes) is not list or not 1 <= len(changes) <= 9:
            raise SubstitutionPayloadError("守備変更数が不一致です")
        seen: set[str] = set()
        for change in changes:
            entry = _object(change, {"position", "outgoingId", "incomingId"})
            position = entry["position"]
            if position not in tuple("123456789") or position in seen:
                raise SubstitutionPayloadError("守備位置が不一致です")
            seen.add(position)
            for key in ("outgoingId", "incomingId"):
                if entry[key] is not None and not _matches(entry[key], _UUID):
                    raise SubstitutionPayloadError("守備選手IDが不一致です")
        return
    else:
        raise SubstitutionPayloadError("未知の交代操作です")
    if not _matches(item["outgoingId"], _UUID) or not _matches(
        item["incomingId"], _UUID
    ):
        raise SubstitutionPayloadError("交代選手IDが不一致です")


def _payload(value: object) -> None:
    """schema未配置の段階でも版・CP・操作の全memberを閉じる。"""
    item = _object(
        value,
        {
            "formatVersion",
            "expectedCheckpoint",
            "eventId",
            "operation",
            "incomingSnapshots",
        },
    )
    cp = _object(item["expectedCheckpoint"], {"id", "revision", "digest"})
    if (
        item["formatVersion"] != "substitution-event-v1"
        or not _matches(item["eventId"], _UUID)
        or not _matches(cp["id"], _UUID)
        or not _matches(cp["revision"], _POSITIVE)
        or not _matches(cp["digest"], _DIGEST)
    ):
        raise SubstitutionPayloadError("交代版またはCPが不一致です")
    _operation(item["operation"])
    op = item["operation"]
    if op["kind"] == "defense":
        incoming = [
            change["incomingId"]
            for change in op["changes"]
            if change["incomingId"] is not None
        ]
    else:
        incoming = [op["incomingId"]]
    snapshots = item["incomingSnapshots"]
    if (
        type(snapshots) is not list
        or len(snapshots) != len(incoming)
        or len(set(incoming)) != len(incoming)
    ):
        raise SubstitutionPayloadError("交代背番号原本が不一致です")
    for expected, raw in zip(incoming, snapshots, strict=True):
        row = _object(raw, {"playerId", "uniformNumber"})
        if row["playerId"] != expected or (
            row["uniformNumber"] is not None and type(row["uniformNumber"]) is not str
        ):
            raise SubstitutionPayloadError("交代背番号原本が不一致です")


@dataclass(frozen=True, slots=True)
class SubstitutionPayload:
    """純入力の不変JSON。これだけでは真正CPとの一致は成立しない。"""

    json: str

    def __post_init__(self) -> None:
        """自由constructorでも閉値を再検査する。"""
        _payload(
            json.loads(
                self.json,
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
        )

    def to_wire(self) -> dict[str, Any]:
        """呼出元に独立した全値を返す。"""
        return cast("dict[str, Any]", json.loads(self.json))


def read_substitution_payload(raw: str) -> SubstitutionPayload:
    """重複key・未知key・非有限値を正規化前に拒否する。"""
    try:
        if type(raw) is not str:
            raise SubstitutionPayloadError("交代JSON文字列が必要です")
        value = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        _payload(value)
        return SubstitutionPayload(_canonical_json(value))
    except (ValueError, TypeError, KeyError) as error:
        raise SubstitutionPayloadError("交代V7が不一致です") from error


def read_substitution_event(event: SyncEvent) -> SubstitutionPayload:
    """S-1済みの実eventからV5/D2/禁止値/閉V7を照合する。"""
    if (
        type(event) is not SyncEvent
        or type(event.d1) is not int
        or event.d1 < 1
        or type(event.d4) is not str
        or not event.d4
        or event.v5 != "substitution"
        or type(event.v6) is not int
        or event.v6 < 0
        or event.v8 is not ABSENT
        or event.v9 is not ABSENT
        or event.v10 is not ABSENT
        or event.v11 is not ABSENT
    ):
        raise SubstitutionPayloadError("交代イベントの境界が不一致です")
    raw = cast("dict[str, Any]", _json_value(event_source(event)))["payload"]
    return read_substitution_payload(_canonical_json(raw))
