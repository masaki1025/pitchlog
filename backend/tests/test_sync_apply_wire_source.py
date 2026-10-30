"""原wire列の全値保持・索引・旧入口非変更を検査する。"""

from __future__ import annotations

import copy
import inspect
import json
from collections.abc import Mapping, MutableMapping
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, cast

import pytest

from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import RequestShapeError, SyncRequest
from pitchlog.sync.wire_fingerprint import (
    wire_event_fingerprint,
    wire_request_fingerprint,
)
from pitchlog.sync.wire_source import (
    WireSourceError,
    WireSourceValue,
    checked_wire_source,
    freeze_wire_source,
)

_ROOT = Path(__file__).resolve().parents[2]
_VECTORS = json.loads(
    (_ROOT / "contracts/state-transition/wire_fingerprint_vectors_v1.json").read_text()
)
_GAME = "10000000-0000-0000-0000-000000000001"
_D4 = "generation-A"
_ERROR = "E-1原wire列の不変値が不正"


def _raw() -> dict[str, Any]:
    return json.loads(_VECTORS["event_cases"][0]["raw_json"])


def _freeze(*events: dict[str, Any]) -> WireSourceValue:
    return freeze_wire_source(game_id=_GAME, d4=_D4, raw_events=events or (_raw(),))


@pytest.mark.parametrize("row", _VECTORS["event_cases"], ids=lambda x: x["case_id"])
def test_all_fixed_event_values(row: dict[str, Any]) -> None:
    """固定event全行の原専用hashと索引を確認する。"""
    raw = json.loads(row["raw_json"])
    value = freeze_wire_source(game_id=raw["game_id"], d4=raw["d4"], raw_events=(raw,))
    assert value.event_fingerprints == (row["expected_fingerprint"],)
    assert checked_wire_source(value) is value
    assert value.codec_version == 1
    assert value.positions_by_d1 == (1,)
    assert dict(value.positions_by_d5) == {raw["d5"]: (1,)}


@pytest.mark.parametrize("row", _VECTORS["request_cases"], ids=lambda x: x["case_id"])
def test_all_fixed_request_values(row: dict[str, Any]) -> None:
    """固定request全行の専用hashと原順索引を照合する。"""
    raw = tuple(json.loads(row["raw_events_json"]))
    value = freeze_wire_source(game_id=row["game_id"], d4=row["d4"], raw_events=raw)
    assert value.request_fingerprint == row["expected_fingerprint"]
    assert tuple(
        value.event_fingerprints[p - 1] for p in value.positions_by_d1
    ) == tuple(row["expected_event_fingerprints_d1_order"])
    assert value.request_fingerprint == wire_request_fingerprint(
        game_id=row["game_id"], d4=row["d4"], events=value.events
    )
    assert checked_wire_source(value) is value


@pytest.mark.parametrize(
    "registration", [None, False, 1, 1.0, [], {}, {"name": "秘密名", "extra": [True]}]
)
def test_registration_and_unknown_s2_are_preserved(registration: object) -> None:
    """不正を含む登録値と未解釈内容をそのまま保持する。"""
    raw = _raw()
    raw["registration"] = registration
    raw["unknown_s2"] = {"expected_version": None, "unimplemented": ["8", False]}
    raw["event_kind"] = ["not-a-kind"]
    raw["payload"] = None
    before = copy.deepcopy(raw)
    value = _freeze(raw)
    from pitchlog.sync.idempotency import _json_value

    assert _json_value(value.events[0].wire_event) == before
    assert value.event_fingerprints == (wire_event_fingerprint(value.events[0]),)
    # 値型はS-1全体/内容/登録/実受付成功を発行しない。
    assert not hasattr(value, "accepted")
    assert not hasattr(value, "writer")
    assert not hasattr(value, "context")
    assert raw == before
    assert checked_wire_source(value) is value


def test_missing_null_and_numeric_types_remain_distinct() -> None:
    """欠落とnullおよびJSON数値型を同一視しない。"""
    hashes = []
    for registration in ("absent-marker", None, False, 1, 1.0):
        raw = _raw()
        if registration != "absent-marker":
            raw["registration"] = registration
        hashes.append(_freeze(raw).event_fingerprints[0])
    assert len(set(hashes)) == 5


def test_indexes_preserve_original_order_and_duplicate_d5_positions() -> None:
    """D1順と原順を分け、同D5の全位置を落とさない。"""
    first, second = _raw(), _raw()
    first["d1"], second["d1"] = 3, 1
    value = _freeze(first, second)
    assert value.positions_by_d1 == (2, 1)
    assert value.positions_by_d5[first["d5"]] == (1, 2)
    assert tuple(e.wire_event["d1"] for e in value.events) == (3, 1)
    reverse = _freeze(second, first)
    assert value.request_fingerprint == reverse.request_fingerprint
    assert value.event_fingerprints == tuple(reversed(reverse.event_fingerprints))
    assert checked_wire_source(value) is value


class _MutableGameIdProbe(Protocol):
    """凍結値への意図的不正代入を、実行時にそのまま試す試験用の見かけ型。"""

    game_id: str


def test_defensive_snapshot_and_read_only_members() -> None:
    """原入力の後変更と外側member書換えを遮断する。"""
    raw = _raw()
    raw["registration"] = {"name": "元の名", "extra": [1]}
    value = _freeze(raw)
    fingerprint = value.request_fingerprint
    raw["registration"]["extra"].append(2)
    raw["event_kind"] = "play_input"
    registration = value.events[0].wire_event["registration"]
    assert isinstance(registration, Mapping)
    assert registration["extra"] == (1,)
    assert value.events[0].wire_event["event_kind"] == "1"
    assert value.request_fingerprint == fingerprint
    with pytest.raises(TypeError):
        cast(MutableMapping[str, tuple[int, ...]], value.positions_by_d5)["bad"] = (1,)
    with pytest.raises(FrozenInstanceError):
        cast(_MutableGameIdProbe, value).game_id = "different"
    with pytest.raises(TypeError):
        WireSourceValue()


@pytest.mark.parametrize(
    "key,value",
    [
        ("d1", True),
        ("d1", 0),
        ("d1", "1"),
        ("d1", 2**53),
        ("d4", "other"),
        ("game_id", "other"),
        ("d5", None),
        ("d5", "NOT-UUID"),
    ],
)
def test_d1_scope_and_d5_shape_rejected(key: str, value: object) -> None:
    """D1付き列のscopeとD5外形を修復せず拒否する。"""
    raw = _raw()
    raw[key] = value
    with pytest.raises(WireSourceError, match=_ERROR) as error:
        _freeze(raw)
    assert error.value.__cause__ is None


def test_p3_empty_duplicate_d1_and_container_rejected() -> None:
    """P3や空列やD1重複をD1付き値へ補完しない。"""
    p3 = {"d5": _raw()["d5"], "game_id": _GAME, "payload": {}}
    for events in ((p3,), (), [_raw()], (_raw(), _raw())):
        with pytest.raises(WireSourceError):
            freeze_wire_source(
                game_id=_GAME,
                d4=_D4,
                raw_events=cast(tuple[Mapping[str, object], ...], events),
            )


@pytest.mark.parametrize(
    "member,changed",
    [
        ("game_id", "other"),
        ("d4", "other"),
        ("codec_version", True),
        ("codec_version", 2),
        ("events", ()),
        ("events", []),
        ("event_fingerprints", ("secret",)),
        ("request_fingerprint", "secret"),
        ("positions_by_d1", (True,)),
        ("positions_by_d1", (2,)),
        ("positions_by_d5", {}),
        ("positions_by_d5", MappingProxyType({"bad": (1,)})),
        ("positions_by_d5", MappingProxyType({_raw()["d5"]: (True,)})),
        ("_seal", object()),
    ],
)
def test_forced_member_mutation_rejected(member: str, changed: object) -> None:
    """発行後の型や指紋や索引の強制変更を拒否する。"""
    value = _freeze()
    object.__setattr__(value, member, changed)
    with pytest.raises(WireSourceError, match=_ERROR) as error:
        checked_wire_source(value)
    assert str(error.value) == _ERROR
    assert error.value.__cause__ is None


def test_fake_source_and_non_json_redact_input() -> None:
    """偽値とJSON外の値を機微値なしで拒否する。"""
    for value in (None, object(), object.__new__(WireSourceValue)):
        with pytest.raises(WireSourceError, match=_ERROR):
            checked_wire_source(cast(WireSourceValue, value))
    for invalid in (float("nan"), float("inf"), object(), "\ud800"):
        raw = _raw()
        raw["registration"] = {"secret-name": invalid}
        with pytest.raises(WireSourceError) as error:
            _freeze(raw)
        assert str(error.value) == _ERROR
        assert "secret-name" not in str(error.value)
        assert error.value.__cause__ is None


def test_old_dto_and_p3_paths_remain_independent() -> None:
    """旧DTO登録拒否とP3を変更せず別領域を維持する。"""
    raw = _raw()
    old = SyncRequest.from_payload("P2", _GAME, {"events": [raw]})
    value = _freeze(raw)
    assert (
        operation_fingerprint(old.events[0], "P2", None) != value.event_fingerprints[0]
    )
    raw["registration"] = None
    with pytest.raises(RequestShapeError):
        SyncRequest.from_payload("P2", _GAME, {"events": [raw]})
    change = {"d5": raw["d5"], "game_id": _GAME, "payload": None}
    p3 = SyncRequest.from_payload(
        "P3", _GAME, {"recovery_generation": "existing", "change": change}
    )
    assert p3.path == "P3"
    assert set(inspect.signature(freeze_wire_source).parameters) == {
        "game_id",
        "d4",
        "raw_events",
    }
