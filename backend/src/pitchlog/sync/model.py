"""同期要求と確定結果の不変な値型を定義する。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from re import fullmatch
from types import MappingProxyType
from typing import Literal, cast


class MissingValue(Enum):
    """JSON の null と区別して、要求からの欠落を表す。"""

    ABSENT = "absent"


ABSENT = MissingValue.ABSENT

type FrozenJson = (
    None
    | bool
    | int
    | float
    | str
    | tuple[FrozenJson, ...]
    | MappingProxyType[str, FrozenJson]
)
# Wire は任意の JSON 値を渡す。意味上の値域は後段で判定する。
type StageValue = object
type ApplicationPath = Literal["P1", "P2", "P3", "P4"]
type A5State = Literal["受理", "重複", "拒否", "退避", "未処理"]
type BoundaryResult = Literal[
    "B1",
    "B2",
    "B3",
    "B4",
    "B5",
    "B6",
    "B7",
    "B8",
    "B9",
    "B10",
    "B11",
    "B12",
    "B13",
    "B14",
]
type AckBoundary = Literal["B1", "B2", "B3", "B4"]
type B3Branch = Literal["B3a", "B3b", "O4", "O5"]
type ChangeBoundary = Literal["変更受理", "B8", "B9", "B10", "B11", "B12", "B13", "B14"]
type RejectedChangeBoundary = Literal["B8", "B9", "B10", "B11", "B12", "B13", "B14"]


class RequestShapeError(ValueError):
    """S-1 の要求外形違反を表す。境界結果 B1〜B14 ではない。"""


_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_MAX_SAFE_INTEGER = 2**53 - 1


def _canonical_uuid(value: object) -> bool:
    """Wire の UUID 正規表記を判定する。"""
    return type(value) is str and fullmatch(_UUID_PATTERN, value) is not None


def _opaque_string(value: object) -> bool:
    """不透明な識別子の S-1 型だけを判定する。"""
    return type(value) is str and bool(value)


def _object_with_keys(value: object, allowed: frozenset[str]) -> Mapping[str, object]:
    """JSON object と未知キー不在だけを検査する。"""
    if not isinstance(value, Mapping) or any(
        type(key) is not str or key not in allowed for key in value
    ):
        raise RequestShapeError("S-1: JSON object またはキーの外形が不正")
    return cast(Mapping[str, object], value)


def freeze_json(value: object) -> FrozenJson:
    """JSON の形を保ったまま、入れ子のコンテナを不変化する。"""
    if value is None or type(value) in (bool, int, float, str):
        return cast(FrozenJson, value)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError("JSON object のキーは文字列が必要")
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    raise TypeError("JSON に含められない値")


def _stage_value(value: object) -> StageValue:
    """欠落を残し、存在する JSON 値は不変化する。"""
    if value is ABSENT:
        return ABSENT
    return freeze_json(value)


@dataclass(frozen=True, slots=True, init=False)
class SyncEvent:
    """D5 と試合を持つイベント。V5〜V11 の成立は処理段階へ委ねる。"""

    d5: str
    game_id: str
    d1: int | None = None
    d4: str | None = None
    v5: StageValue = ABSENT
    v6: StageValue = ABSENT
    v7: StageValue = ABSENT
    v8: StageValue = ABSENT
    v9: StageValue = ABSENT
    v10: StageValue = ABSENT
    v11: StageValue = ABSENT

    def __new__(
        cls,
        d5: str,
        game_id: str,
        d1: int | None = None,
        d4: str | None = None,
        v5: StageValue = ABSENT,
        v6: StageValue = ABSENT,
        v7: StageValue = ABSENT,
        v8: StageValue = ABSENT,
        v9: StageValue = ABSENT,
        v10: StageValue = ABSENT,
        v11: StageValue = ABSENT,
    ) -> SyncEvent:
        """V5〜V11 の任意の JSON 値を欠落と区別して固定する。"""
        if not _canonical_uuid(d5) or not _canonical_uuid(game_id):
            raise RequestShapeError("S-1: D5 または試合 ID が UUID 正規形ではない")
        instance = object.__new__(cls)
        for name, value in (
            ("d5", d5),
            ("game_id", game_id),
            ("d1", d1),
            ("d4", d4),
            ("v5", _stage_value(v5)),
            ("v6", _stage_value(v6)),
            ("v7", _stage_value(v7)),
            ("v8", _stage_value(v8)),
            ("v9", _stage_value(v9)),
            ("v10", _stage_value(v10)),
            ("v11", _stage_value(v11)),
        ):
            object.__setattr__(instance, name, value)
        return instance


@dataclass(frozen=True, slots=True, init=False)
class SyncRequest:
    """単一試合の要求。V12 と復旧世代の成否は処理段階で決める。"""

    path: ApplicationPath
    game_id: str
    events: tuple[SyncEvent, ...]
    d4: str | None = None
    recovery_generation: str | MissingValue = ABSENT
    v12: StageValue = ABSENT

    def __new__(
        cls,
        path: ApplicationPath,
        game_id: str,
        events: tuple[SyncEvent, ...],
        d4: str | None = None,
        recovery_generation: str | MissingValue = ABSENT,
        v12: StageValue = ABSENT,
    ) -> SyncRequest:
        """イベント列と V12 を不変化して保持する。"""
        if path not in ("P1", "P2", "P3", "P4"):
            raise RequestShapeError("S-1: 未知の適用経路")
        if not _canonical_uuid(game_id):
            raise RequestShapeError("S-1: 試合 ID が UUID 正規形ではない")
        if not isinstance(events, (list, tuple)) or any(
            type(event) is not SyncEvent for event in events
        ):
            raise RequestShapeError("S-1: イベント列の外形が不正")
        if path == "P3":
            if len(events) != 1:
                raise RequestShapeError("S-1: P3 は変更イベント 1 件が必要")
            if not _opaque_string(recovery_generation):
                raise RequestShapeError("S-1: P3 の復旧世代がないか型が不正")
            if d4 is not None or any(
                event.d1 is not None
                or event.d4 is not None
                or any(value is not ABSENT for value in (event.v6, event.v8, event.v9))
                for event in events
            ):
                raise RequestShapeError("S-1: P3 に D1・D4・V6・V8・V9 を指定できない")
        else:
            if recovery_generation is not ABSENT or any(
                event.v11 is not ABSENT for event in events
            ):
                raise RequestShapeError(
                    "S-1: D1 付き経路に復旧世代・V11 を指定できない"
                )
            _validate_d1_events(d4, events)
        if any(event.game_id != game_id for event in events):
            raise RequestShapeError("S-1: 試合 ID がイベント列と一致しない")
        instance = object.__new__(cls)
        for name, value in (
            ("path", path),
            ("game_id", game_id),
            ("events", tuple(events)),
            ("d4", d4),
            ("recovery_generation", recovery_generation),
            ("v12", _stage_value(v12)),
        ):
            object.__setattr__(instance, name, value)
        return instance

    @classmethod
    def from_payload(
        cls, path: ApplicationPath, game_id: str, payload: object
    ) -> SyncRequest:
        """URL の経路・試合と E-1/E-2 本文の S-1 外形を照合する。"""
        if path == "P3":
            body = _object_with_keys(
                payload,
                frozenset({"recovery_generation", "recording_right_proof", "change"}),
            )
            change = _object_with_keys(
                body.get("change"),
                frozenset(
                    {
                        "d5",
                        "game_id",
                        "event_kind",
                        "payload",
                        "target_reference",
                        "expected_version",
                    }
                ),
            )
            if "d5" not in change or "game_id" not in change:
                raise RequestShapeError("S-1: 変更イベントの識別がない")
            event = SyncEvent(
                d5=cast(str, change["d5"]),
                game_id=cast(str, change["game_id"]),
                v5=change.get("event_kind", ABSENT),
                v7=change.get("payload", ABSENT),
                v10=change.get("target_reference", ABSENT),
                v11=change.get("expected_version", ABSENT),
            )
            return cls(
                path,
                game_id,
                (event,),
                recovery_generation=cast(
                    str | MissingValue, body.get("recovery_generation", ABSENT)
                ),
                v12=body.get("recording_right_proof", ABSENT),
            )
        body, events = _parse_d1_payload(payload)
        return cls(
            path,
            game_id,
            tuple(events),
            d4=events[0].d4,
            v12=body.get("recording_right_proof", ABSENT),
        )


def _validate_d1_events(d4: str | None, events: tuple[SyncEvent, ...]) -> None:
    """D1 付き要求に共通する識別子とイベント列の外形を照合する。"""
    if not events:
        raise RequestShapeError("S-1: D1 付き経路のイベント列は空にできない")
    if not _opaque_string(d4):
        raise RequestShapeError("S-1: D1 付き経路の D4 がないか型が不正")
    if any(
        type(event.d1) is not int
        or not 1 <= event.d1 <= _MAX_SAFE_INTEGER
        or event.d4 != d4
        for event in events
    ):
        raise RequestShapeError("S-1: D1 または要求内 D4 が不正")
    d1_values = [event.d1 for event in events]
    if len(d1_values) != len(set(d1_values)):
        raise RequestShapeError("S-1: D1 が重複している")


def _parse_d1_payload(
    payload: object,
) -> tuple[Mapping[str, object], tuple[SyncEvent, ...]]:
    """両入口の D1 付き本文を同じ S-1 規則で取り出す。"""
    body = _object_with_keys(payload, frozenset({"recording_right_proof", "events"}))
    raw_events = body.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise RequestShapeError("S-1: イベント列は空でない JSON array が必要")
    events: list[SyncEvent] = []
    event_keys = frozenset(
        {
            "d5",
            "d1",
            "d4",
            "game_id",
            "event_kind",
            "d2",
            "payload",
            "state_diff",
            "replacement_state",
            "target_reference",
        }
    )
    for raw_event in raw_events:
        item = _object_with_keys(raw_event, event_keys)
        if "d5" not in item or "game_id" not in item:
            raise RequestShapeError("S-1: イベントの識別がない")
        events.append(
            SyncEvent(
                d5=cast(str, item["d5"]),
                game_id=cast(str, item["game_id"]),
                d1=cast(int | None, item.get("d1")),
                d4=cast(str | None, item.get("d4")),
                v5=item.get("event_kind", ABSENT),
                v6=item.get("d2", ABSENT),
                v7=item.get("payload", ABSENT),
                v8=item.get("state_diff", ABSENT),
                v9=item.get("replacement_state", ABSENT),
                v10=item.get("target_reference", ABSENT),
            )
        )
    return body, tuple(events)


@dataclass(frozen=True, slots=True, init=False)
class SyncEventBatch:
    """経路を持たない E-1 の D1 付き同期要求。"""

    game_id: str
    d4: str
    events: tuple[SyncEvent, ...]
    v12: StageValue = ABSENT

    def __new__(
        cls,
        game_id: str,
        d4: str,
        events: tuple[SyncEvent, ...],
        v12: StageValue = ABSENT,
    ) -> SyncEventBatch:
        """S-1 外形を照合し、イベント列と V12 を固定する。"""
        if not _canonical_uuid(game_id):
            raise RequestShapeError("S-1: 試合 ID が UUID 正規形ではない")
        if not isinstance(events, (list, tuple)) or any(
            type(event) is not SyncEvent for event in events
        ):
            raise RequestShapeError("S-1: イベント列の外形が不正")
        _validate_d1_events(d4, tuple(events))
        if any(event.v11 is not ABSENT for event in events):
            raise RequestShapeError("S-1: D1 付き経路に復旧世代・V11 を指定できない")
        if any(event.game_id != game_id for event in events):
            raise RequestShapeError("S-1: 試合 ID がイベント列と一致しない")
        instance = object.__new__(cls)
        for name, value in (
            ("game_id", game_id),
            ("d4", d4),
            ("events", tuple(events)),
            ("v12", _stage_value(v12)),
        ):
            object.__setattr__(instance, name, value)
        return instance

    @classmethod
    def from_payload(cls, game_id: str, payload: object) -> SyncEventBatch:
        """U-S1 表現の E-1 本文を S-1 で照合する。"""
        body, events = _parse_d1_payload(payload)
        return cls(
            game_id,
            cast(str, events[0].d4),
            events,
            body.get("recording_right_proof", ABSENT),
        )


@dataclass(frozen=True, slots=True)
class A5Result:
    """D4・D1・D5 で識別するイベント単位の確定結果。"""

    d4: str
    d1: int
    d5: str
    state: A5State
    reason: str | None = None


@dataclass(frozen=True, slots=True, init=False)
class AckResult:
    """D1 付き経路で実際に返す B1〜B4 と A5・D3。"""

    boundary: AckBoundary
    d3: int
    a5: tuple[A5Result, ...]
    b3_branch: B3Branch | None = None
    reason: str | None = None
    temporary_id_mapping: Mapping[str, str]

    def __new__(
        cls,
        boundary: AckBoundary,
        d3: int,
        a5: tuple[A5Result, ...],
        b3_branch: B3Branch | None = None,
        reason: str | None = None,
        temporary_id_mapping: Mapping[str, str] | None = None,
    ) -> AckResult:
        """結果列と A4 の一時 ID 写像を不変化する。"""
        instance = object.__new__(cls)
        for name, value in (
            ("boundary", boundary),
            ("d3", d3),
            ("a5", tuple(a5)),
            ("b3_branch", b3_branch),
            ("reason", reason),
            (
                "temporary_id_mapping",
                MappingProxyType(dict(temporary_id_mapping or {})),
            ),
        ):
            object.__setattr__(instance, name, value)
        return instance


@dataclass(frozen=True, slots=True, init=False)
class AcceptedChangeResult:
    """P3 の変更受理と端末が保持する I6 全項目を表す。"""

    target_reference: Mapping[str, FrozenJson]
    expected_version: StageValue
    d5: str
    confirmed_content: FrozenJson
    accepted_at: str
    boundary: Literal["変更受理"] = "変更受理"

    def __new__(
        cls,
        target_reference: Mapping[str, object],
        expected_version: StageValue,
        d5: str,
        confirmed_content: object,
        accepted_at: str,
    ) -> AcceptedChangeResult:
        """I6 の対象参照・期待版・確定内容を不変化する。"""
        if (
            set(target_reference) != {"試合", "対象の D4", "対象の D1"}
            or not isinstance(accepted_at, str)
            or not accepted_at
        ):
            raise ValueError("変更受理には I6 の対象参照と確定時刻が必要")
        if expected_version is ABSENT or confirmed_content is ABSENT:
            raise ValueError("変更受理には期待版と確定内容が必要")
        instance = object.__new__(cls)
        for name, value in (
            ("target_reference", freeze_json(target_reference)),
            ("expected_version", _stage_value(expected_version)),
            ("d5", d5),
            ("confirmed_content", freeze_json(confirmed_content)),
            ("accepted_at", accepted_at),
            ("boundary", "変更受理"),
        ):
            object.__setattr__(instance, name, value)
        return instance


@dataclass(frozen=True, slots=True)
class RejectedChangeResult:
    """P3 の B8〜B14 の拒否だけを表す。"""

    boundary: RejectedChangeBoundary
    d5: str
    reason: str | None = None

    def __post_init__(self) -> None:
        """変更受理を拒否型へ偽装できないようにする。"""
        if self.boundary not in ("B8", "B9", "B10", "B11", "B12", "B13", "B14"):
            raise ValueError("P3 の拒否結果には B8〜B14 が必要")


type ChangeResult = AcceptedChangeResult | RejectedChangeResult
