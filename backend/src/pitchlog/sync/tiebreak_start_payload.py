"""タイブレーク開始P2の閉じたV7を読む。保存資格や計算成功は発行しない。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from re import fullmatch
from typing import Any, cast

from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object
from pitchlog.sync.idempotency import _json_value
from pitchlog.sync.model import ABSENT, SyncEvent


class TiebreakStartPayloadError(ValueError):
    """タイブレーク開始の閉値が不一致。入力値・選手情報は理由へ含めない。"""


_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_POSITIVE = r"[1-9][0-9]*"
_DIGEST = r"[0-9a-f]{64}"
_PLACEMENTS = ("first-second", "second-third")


def _matches(value: object, pattern: str) -> bool:
    """bool/数値や末尾改行を正準文字列に補完しない。"""
    return type(value) is str and fullmatch(pattern, value) is not None


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    """未知・不足memberをともに閉じる。"""
    if type(value) is not dict or set(value) != keys:
        raise TiebreakStartPayloadError("タイブレーク開始のmemberが不一致です")
    return cast("dict[str, Any]", value)


@dataclass(frozen=True, slots=True)
class TiebreakStartEvent:
    """V7の閉じた開始入力。個人IDの実在は保存原本側で照合する。"""

    expected_checkpoint: Mapping[str, str]
    event_id: str
    runner_placement: str
    leadoff_batter: str
    inning: str
    first_runner_id: str
    second_runner_id: str

    def to_wire(self) -> dict[str, object]:
        """既V7と同じキーだけを返す。"""
        return {
            "formatVersion": "tiebreak-start-event-v1",
            "expectedCheckpoint": dict(self.expected_checkpoint),
            "eventId": self.event_id,
            "runnerPlacement": self.runner_placement,
            "leadoffBatter": self.leadoff_batter,
            "inning": self.inning,
            "firstRunnerId": self.first_runner_id,
            "secondRunnerId": self.second_runner_id,
        }


def _read(value: object) -> TiebreakStartEvent:
    """版・CP・開始入力の全memberを閉じる。"""
    item = _object(
        value,
        {
            "formatVersion",
            "expectedCheckpoint",
            "eventId",
            "runnerPlacement",
            "leadoffBatter",
            "inning",
            "firstRunnerId",
            "secondRunnerId",
        },
    )
    cp = _object(item["expectedCheckpoint"], {"id", "revision", "digest"})
    if (
        item["formatVersion"] != "tiebreak-start-event-v1"
        or not _matches(item["eventId"], _UUID)
        or not _matches(cp["id"], _UUID)
        or not _matches(cp["revision"], _POSITIVE)
        or not _matches(cp["digest"], _DIGEST)
        or item["runnerPlacement"] not in _PLACEMENTS
        or not _matches(item["leadoffBatter"], _POSITIVE)
        or int(cast(str, item["leadoffBatter"])) > 9
        or not _matches(item["inning"], _POSITIVE)
        or not _matches(item["firstRunnerId"], _UUID)
        or not _matches(item["secondRunnerId"], _UUID)
        or item["firstRunnerId"] == item["secondRunnerId"]
    ):
        raise TiebreakStartPayloadError("タイブレーク開始の版/CP/入力が不一致です")
    return TiebreakStartEvent(
        expected_checkpoint={
            "id": cast(str, cp["id"]),
            "revision": cast(str, cp["revision"]),
            "digest": cast(str, cp["digest"]),
        },
        event_id=cast(str, item["eventId"]),
        runner_placement=cast(str, item["runnerPlacement"]),
        leadoff_batter=cast(str, item["leadoffBatter"]),
        inning=cast(str, item["inning"]),
        first_runner_id=cast(str, item["firstRunnerId"]),
        second_runner_id=cast(str, item["secondRunnerId"]),
    )


def read_tiebreak_start_event(event: SyncEvent) -> TiebreakStartEvent:
    """実E-1 eventのV7だけを閉じた開始入力へ写す。

    Args:
        event: E-1の単一event。

    Returns:
        検証済みの開始入力。

    Raises:
        TiebreakStartPayloadError: V7が閉じた形・値でない場合。
    """
    if type(event) is not SyncEvent or event.v5 != "tiebreak_start":
        raise TiebreakStartPayloadError("タイブレーク開始のevent種別が不一致です")
    if event.v7 is ABSENT or event.v7 is None:
        raise TiebreakStartPayloadError("タイブレーク開始のpayloadがありません")
    raw = _json_value(event.v7)
    if type(raw) is str:
        try:
            parsed = json.loads(
                raw,
                parse_constant=_invalid_constant,
                object_pairs_hook=_unique_object,
            )
        except (ValueError, TypeError) as error:
            raise TiebreakStartPayloadError(
                "タイブレーク開始のJSONが不正です"
            ) from error
    else:
        parsed = raw
    if type(parsed) is not dict:
        raise TiebreakStartPayloadError(
            "タイブレーク開始のpayloadがobjectではありません"
        )
    return _read(parsed)
