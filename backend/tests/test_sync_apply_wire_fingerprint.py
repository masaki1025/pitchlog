"""原wire指紋の固定vector・不変化・外形/意味分離を検査する。"""

from __future__ import annotations

import builtins
import copy
import inspect
import json
import subprocess
import traceback
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from pitchlog.sync import idempotency
from pitchlog.sync.idempotency import (
    _json_value,
    event_source_fingerprint,
    operation_fingerprint,
)
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.wire_fingerprint import (
    WireEventValue,
    WireFingerprintError,
    freeze_wire_event,
    wire_event_fingerprint,
    wire_request_fingerprint,
)

_ROOT = Path(__file__).resolve().parents[2]
_VECTORS = json.loads(
    (_ROOT / "contracts/state-transition/wire_fingerprint_vectors_v1.json").read_text()
)
_EVENT_ROWS = _VECTORS["event_cases"]
_REQUEST_ROWS = _VECTORS["request_cases"]
_GAME = "10000000-0000-0000-0000-000000000001"
_D4 = "generation-A"
_ERROR = "E-1原wire指紋の入力又は不変値が不正"


def _base() -> dict[str, Any]:
    """固定原JSONを各試験へ独立供給する。"""
    return json.loads(_EVENT_ROWS[0]["raw_json"])


def _canonical(value: object) -> str:
    """試験のbyte観測だけに既container変換を再利用する。"""
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _request(events: tuple[WireEventValue, ...]) -> str:
    """同じ試験scopeだけを要求APIへ渡す。"""
    return wire_request_fingerprint(game_id=_GAME, d4=_D4, events=events)


@pytest.mark.parametrize("row", _EVENT_ROWS, ids=lambda row: row["case_id"])
def test_fixed_event_vector_full_bytes_and_fingerprint(row: dict[str, Any]) -> None:
    """期待hashを実行中生成せず、原JSON/全byteと固定vectorを比較する。"""
    value = freeze_wire_event(json.loads(row["raw_json"]))
    assert _canonical(value.wire_event) == row["canonical_event_json"]
    assert (
        _canonical(
            {
                "codec_version": 1,
                "wire_event": value.wire_event,
                "registration": value.wire_event.get("registration"),
            }
        )
        == row["canonical_wrapper_json"]
    )
    assert wire_event_fingerprint(value) == row["expected_fingerprint"]
    assert wire_event_fingerprint(value) == "wire-v1:" + row["wrapper_utf8_sha256"]


@pytest.mark.parametrize("row", _REQUEST_ROWS, ids=lambda row: row["case_id"])
def test_fixed_request_vector_orders_only_copied_references(
    row: dict[str, Any],
) -> None:
    """元tupleと原eventを変えず、D1順に限定した固定要求hashへ一致する。"""
    originals = json.loads(row["raw_events_json"])
    events = tuple(freeze_wire_event(event) for event in originals)
    before = tuple(wire_event_fingerprint(event) for event in events)
    assert (
        wire_request_fingerprint(game_id=row["game_id"], d4=row["d4"], events=events)
        == row["expected_fingerprint"]
    )
    assert tuple(wire_event_fingerprint(event) for event in events) == before
    assert [_canonical(event.wire_event) for event in events] == [
        _canonical(event) for event in originals
    ]
    ordered = sorted(events, key=lambda event: cast(int, event.wire_event["d1"]))
    assert [wire_event_fingerprint(event) for event in ordered] == row[
        "expected_event_fingerprints_d1_order"
    ]
    assert (
        _canonical(
            {
                "codec_version": 1,
                "game_id": row["game_id"],
                "d4": row["d4"],
                "events": row["expected_event_fingerprints_d1_order"],
            }
        )
        == row["canonical_wrapper_json"]
    )


@pytest.mark.parametrize("group", ["event", "request"])
def test_declared_equivalence_and_difference_relations(group: str) -> None:
    """欠落/null/数値型/Unicode/array順と要求並びの関係を固定する。"""
    rows = _EVENT_ROWS if group == "event" else _REQUEST_ROWS
    actual = {}
    for row in rows:
        if group == "event":
            actual[row["case_id"]] = wire_event_fingerprint(
                freeze_wire_event(json.loads(row["raw_json"]))
            )
        else:
            events = tuple(
                freeze_wire_event(x) for x in json.loads(row["raw_events_json"])
            )
            actual[row["case_id"]] = wire_request_fingerprint(
                game_id=row["game_id"], d4=row["d4"], events=events
            )
    for left, right in _VECTORS["relations"][group + "_equal"]:
        assert actual[left] == actual[right]
    for left, right in _VECTORS["relations"][group + "_different"]:
        assert actual[left] != actual[right]


def test_vector_population_and_semantic_qualification_are_frozen() -> None:
    """候補の全件消費と正式V7/V8/HTTP未成立の資格を保持する。"""
    assert _VECTORS["vector_version"] == 1
    assert len(_EVENT_ROWS) == 32
    assert len(_REQUEST_ROWS) == 8
    assert "not the formal V7/V8" in _VECTORS["qualification"]
    assert len({row["case_id"] for row in _EVENT_ROWS}) == 32


def test_deep_snapshot_is_detached_and_recursive_frozen() -> None:
    """元dict/listの後発更新と返却object操作を混入させない。"""
    raw = _base()
    raw["registration"] = {"bad": [False, {"name": "original"}]}
    original = copy.deepcopy(raw)
    value = freeze_wire_event(raw)
    digest = wire_event_fingerprint(value)
    raw["payload"]["value"] = 999
    raw["state_diff"]["flags"].append(True)
    cast(Any, raw["registration"]["bad"][1])["name"] = "changed"
    assert _canonical(value.wire_event) == _canonical(original)
    assert wire_event_fingerprint(value) == digest
    assert type(value.wire_event) is MappingProxyType
    assert type(cast(Any, value.wire_event["state_diff"])["flags"]) is tuple
    with pytest.raises(TypeError):
        cast(Any, value.wire_event)["d1"] = 2
    with pytest.raises(TypeError):
        cast(Any, value.wire_event["payload"])["value"] = 999
    with pytest.raises(FrozenInstanceError):
        setattr(value, "_fingerprint", "forged")
    assert "original" not in repr(value)


@pytest.mark.parametrize(
    "mutation",
    ["bare", "subclass", "seal", "digest", "wire", "mutable", "nested-mutable"],
)
def test_forged_and_force_modified_values_are_rejected(mutation: str) -> None:
    """実型だけの偽値や不変化後の強制差替えを再使用させない。"""
    value = freeze_wire_event(_base())
    if mutation == "bare":
        value = object.__new__(WireEventValue)
    elif mutation == "subclass":

        class Derived(WireEventValue):
            pass

        value = object.__new__(Derived)
    elif mutation == "seal":
        object.__setattr__(value, "_seal", object())
    elif mutation == "digest":
        object.__setattr__(value, "_fingerprint", "wire-v1:" + "0" * 64)
    elif mutation == "wire":
        changed = _base()
        changed["d1"] = 9
        object.__setattr__(value, "_wire_event", freeze_wire_event(changed).wire_event)
    elif mutation == "mutable":
        object.__setattr__(value, "_wire_event", _base())
    else:
        changed = dict(value.wire_event)
        cast(Any, changed)["payload"] = {"value": 1}
        object.__setattr__(value, "_wire_event", MappingProxyType(changed))
    for function in [lambda: wire_event_fingerprint(value), lambda: _request((value,))]:
        with pytest.raises(WireFingerprintError) as error:
            function()
        assert error.value.args == (_ERROR,)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        1,
        [],
        b"{}",
        {"x": b"bad"},
        {"x": Decimal("1")},
        {"x": UUID(_GAME)},
        {"x": {1, 2}},
        {"x": (1, 2)},
        {1: "bad"},
        {"x": float("nan")},
        {"x": float("inf")},
        {"x": float("-inf")},
        {"x": "\ud800"},
        {"\ud800": 1},
    ],
    ids=lambda raw: type(raw).__name__,
)
def test_freeze_itself_rejects_non_json_nonfinite_and_utf8_failure(raw: Any) -> None:
    """指紋呼出まで先送りせず、freeze入口で閉値外を固定拒否する。"""
    with pytest.raises(WireFingerprintError) as error:
        freeze_wire_event(raw)
    assert error.value.args == (_ERROR,)
    assert error.value.__suppress_context__ is True


def test_cycle_rejection_is_fixed_and_does_not_expose_input() -> None:
    """循環入力も元値/原例外を露出せず失敗する。"""
    raw: dict[str, Any] = {"private": "CANARY_PRIVATE_VALUE"}
    raw["cycle"] = raw
    with pytest.raises(WireFingerprintError) as error:
        freeze_wire_event(raw)
    assert error.value.args == (_ERROR,)
    shown = "".join(traceback.format_exception(error.value))
    assert "CANARY_PRIVATE_VALUE" not in shown
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("bad", [None, True, False, 0, -1, 1.0, "1", 2**53])
def test_request_d1_uses_exact_positive_safe_integer(bad: Any) -> None:
    """D1の文字列化/数値丸め/bool sort/欠落0補完を行わない。"""
    raw = _base()
    raw["d1"] = bad
    value = freeze_wire_event(raw)
    assert wire_event_fingerprint(value).startswith("wire-v1:")
    with pytest.raises(WireFingerprintError):
        _request((value,))


@pytest.mark.parametrize(
    "mutation",
    [
        "empty",
        "list",
        "fake",
        "duplicate",
        "missing-d1",
        "wrong-game",
        "wrong-d4",
        "missing-game",
        "missing-d4",
    ],
)
def test_request_structure_scope_and_nonempty_sequence(mutation: str) -> None:
    """S-1scope外やD1重複に任意tie-break/補完hashを返さない。"""
    raw = _base()
    if mutation.startswith("missing-"):
        del raw[
            {"missing-d1": "d1", "missing-game": "game_id", "missing-d4": "d4"}[
                mutation
            ]
        ]
    elif mutation == "wrong-game":
        raw["game_id"] = "10000000-0000-0000-0000-000000000002"
    elif mutation == "wrong-d4":
        raw["d4"] = "different"
    event = freeze_wire_event(raw)
    events: Any = (event,)
    if mutation == "empty":
        events = ()
    elif mutation == "list":
        events = [event]
    elif mutation == "fake":
        events = ("wire-v1:" + "0" * 64,)
    elif mutation == "duplicate":
        events = (event, event)
    with pytest.raises(WireFingerprintError):
        _request(cast(tuple[WireEventValue, ...], events))


@pytest.mark.parametrize(
    "game,d4",
    [
        ("AAAAAAAA-0000-0000-0000-000000000001", "x"),
        ("bad", "x"),
        (" " + _GAME, "x"),
        (_GAME, ""),
        (_GAME, 1),
        (UUID(_GAME), "x"),
    ],
)
def test_request_scope_uses_existing_s1_shape_without_correction(
    game: Any, d4: Any
) -> None:
    """URL/D4を正規化補正せず、既S-1の外形で拒否する。"""
    with pytest.raises(WireFingerprintError):
        wire_request_fingerprint(
            game_id=game, d4=d4, events=(freeze_wire_event(_base()),)
        )


def test_s2_bad_values_are_hashed_without_dto_or_registration_repair() -> None:
    """未知種別/不正登録/数値payloadを意味変換せず要求にも保持する。"""
    raw = _base()
    raw.update(
        event_kind="unknown", registration=False, payload=3.0, state_diff=["bad"]
    )
    value = freeze_wire_event(raw)
    assert value.wire_event["event_kind"] == "unknown"
    assert type(value.wire_event["payload"]) is float
    assert value.wire_event["registration"] is False
    assert _request((value,)).startswith("wire-request-v1:")
    repaired = _base()
    assert _request((value,)) != _request((freeze_wire_event(repaired),))


def test_request_hash_api_has_no_v12_attempt_or_free_hash_inputs() -> None:
    """要求wrapper除外値と自由hash/版引数をAPIへ加えない。"""
    assert set(inspect.signature(wire_request_fingerprint).parameters) == {
        "game_id",
        "d4",
        "events",
    }
    assert set(inspect.signature(wire_event_fingerprint).parameters) == {"event"}
    events = (freeze_wire_event(_base()),)
    for ignored in [
        {"v12": "secret"},
        {"attempt_id": "next"},
        {"codec_version": True},
        {"fingerprints": ["forged"]},
    ]:
        with pytest.raises(TypeError):
            wire_request_fingerprint(game_id=_GAME, d4=_D4, events=events, **ignored)


def test_existing_dto_and_operation_fingerprints_remain_different() -> None:
    """旧指紋を新領域へaliasせず、同D5の異内容を同一化しない。"""
    raw = _base()
    old = SyncEvent(
        d5=raw["d5"],
        game_id=_GAME,
        d1=1,
        d4=_D4,
        v5="1",
        v6=10,
        v7=raw["payload"],
        v8=raw["state_diff"],
    )
    before = (event_source_fingerprint(old), operation_fingerprint(old, "P2", None))
    event = freeze_wire_event(raw)
    assert wire_event_fingerprint(event) not in before
    assert _request((event,)) != wire_event_fingerprint(event)
    assert (
        event_source_fingerprint(old),
        operation_fingerprint(old, "P2", None),
    ) == before


def test_no_legacy_event_recipe_or_external_io_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既source正規化以外の旧再計算/保存/I/Oを呼ばない。"""

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("旧recipe/外部I/Oへ到達")

    for name in [
        "event_source",
        "event_source_fingerprint",
        "operation_fingerprint",
        "classify_d5",
        "recheck_and_insert_result",
    ]:
        monkeypatch.setattr(idempotency, name, forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    event = freeze_wire_event(_base())
    assert wire_event_fingerprint(event) == _EVENT_ROWS[0]["expected_fingerprint"]
    assert _request((event,)) == _REQUEST_ROWS[2]["expected_fingerprint"]
