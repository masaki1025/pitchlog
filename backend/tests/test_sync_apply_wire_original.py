"""原本codecの全固定値・型保持・厳密拒否を検査する。DB試験ではない。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint
from pitchlog.sync.wire_original import (
    WireOriginalError,
    decode_wire_original,
    encode_wire_original,
)

_ROOT = Path(__file__).resolve().parents[2]
_VECTORS = json.loads(
    (_ROOT / "contracts/state-transition/wire_fingerprint_vectors_v1.json").read_text()
)
_ERROR = "E-1原本の閉形式又は期待値が一致しません"


def _raw() -> dict[str, Any]:
    return json.loads(_VECTORS["event_cases"][0]["raw_json"])


def _envelope(raw: dict[str, Any]) -> dict[str, Any]:
    return json.loads(encode_wire_original(freeze_wire_event(raw)))


def _expected(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "game_id": raw["game_id"],
        "d4": raw["d4"],
        "d1": raw["d1"],
        "d5": raw["d5"],
        "expected_event_fingerprint": wire_event_fingerprint(freeze_wire_event(raw)),
    }


@pytest.mark.parametrize("row", _VECTORS["event_cases"], ids=lambda r: r["case_id"])
def test_fixed_vectors_roundtrip(row: dict[str, Any]) -> None:
    """固定期待hashと正準原JSONを全行消費する。"""
    raw = json.loads(row["raw_json"])
    envelope = _envelope(raw)
    assert envelope == {
        "format_version": "e1-original-v1",
        "codec_version": 1,
        "event_fingerprint": row["expected_fingerprint"],
        "wire_event_json": row["canonical_event_json"],
    }
    value = decode_wire_original(envelope, **_expected(raw))
    assert wire_event_fingerprint(value) == row["expected_fingerprint"]
    assert encode_wire_original(value) == encode_wire_original(freeze_wire_event(raw))


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        True,
        0,
        1,
        1.0,
        -0.0,
        1.7e308,
        5e-324,
        [],
        {},
        "é😀",
        {"x": [False, 1.0, None]},
        [1, 2],
    ],
)
@pytest.mark.parametrize("key", ["registration", "payload", "unknown"])
def test_raw_value_types_and_unknown_s2_preserved(key: str, value: object) -> None:
    """不正S2も含めて型を保ち、registrationを補完しない。"""
    raw = _raw()
    raw[key] = value
    expected = _expected(raw)
    envelope = _envelope(raw)
    raw[key] = "later-mutated"
    result = decode_wire_original(envelope, **expected)
    assert encode_wire_original(result) == json.dumps(
        envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert envelope["wire_event_json"] == json.dumps(
        {**_raw(), key: value},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@pytest.mark.parametrize(
    "field", ["format_version", "codec_version", "event_fingerprint", "wire_event_json"]
)
@pytest.mark.parametrize("change", ["missing", "extra", None, False, 0, 1.0, [], {}])
def test_outer_closed_fields(field: str, change: object) -> None:
    """外側の欠落/余剰/非strict値を拒否する。"""
    raw = _raw()
    envelope = _envelope(raw)
    if change == "missing":
        del envelope[field]
    elif change == "extra":
        envelope["secret-extra"] = "secret-value"
    else:
        envelope[field] = change
    with pytest.raises(WireOriginalError, match=f"^{_ERROR}$") as error:
        decode_wire_original(envelope, **_expected(raw))
    assert error.value.__cause__ is None
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize(
    "wire",
    [
        '{"d1":1,"d1":1}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":-Infinity}',
        "null",
        "[]",
        "true",
        "1",
        '{"x":1e9999}',
        '{"x":"\\ud800"}',
        '{"secret-value":',
        "",
    ],
)
def test_inner_json_rejections(wire: str) -> None:
    """重複key/非有限/不正Unicode/非objectを閉じる。"""
    raw = _raw()
    envelope = _envelope(raw)
    envelope["wire_event_json"] = wire
    with pytest.raises(WireOriginalError, match=f"^{_ERROR}$"):
        decode_wire_original(envelope, **_expected(raw))


@pytest.mark.parametrize(
    "field", ["game_id", "d4", "d1", "d5", "expected_event_fingerprint"]
)
@pytest.mark.parametrize("change", [None, False, 1.0, [], "secret-value"])
def test_independent_expected_scope_rejections(field: str, change: object) -> None:
    """期待値の自由差替えやbool/int等価を通さない。"""
    raw = _raw()
    expected = _expected(raw)
    expected[field] = change
    with pytest.raises(WireOriginalError, match=f"^{_ERROR}$"):
        decode_wire_original(_envelope(raw), **expected)


@pytest.mark.parametrize("field", ["d1", "d4", "d5", "game_id"])
def test_raw_scope_mismatch_despite_recomputed_hash(field: str) -> None:
    """hashだけ更新した原本で別scopeへ移らない。"""
    raw = _raw()
    expected = _expected(raw)
    raw[field] = (
        2
        if field == "d1"
        else (
            "other-generation"
            if field == "d4"
            else "30000000-0000-0000-0000-000000000001"
        )
    )
    with pytest.raises(WireOriginalError):
        decode_wire_original(_envelope(raw), **expected)


def test_missing_d1_is_not_repaired() -> None:
    """P3相当の欠落D1を期待値から埋めない。"""
    raw = _raw()
    expected = _expected(raw)
    del raw["d1"]
    with pytest.raises(WireOriginalError):
        decode_wire_original(_envelope(raw), **expected)


@pytest.mark.parametrize(
    "change",
    ["whitespace", "integer-to-float", "outer-hash", "unknown-version", "legacy-flat"],
)
def test_noncanonical_hash_and_legacy_envelopes_reject(change: str) -> None:
    """未知版や旧flatへfallbackせず、数値型を同一視しない。"""
    raw = _raw()
    envelope = _envelope(raw)
    if change == "whitespace":
        envelope["wire_event_json"] += " "
    elif change == "integer-to-float":
        envelope["wire_event_json"] = envelope["wire_event_json"].replace(
            '"value":1', '"value":1.0'
        )
    elif change == "outer-hash":
        envelope["event_fingerprint"] = "wire-request-v1:" + "0" * 64
    elif change == "unknown-version":
        envelope["format_version"] = "e1-original-v2"
    else:
        envelope = copy.deepcopy(raw)
    with pytest.raises(WireOriginalError):
        decode_wire_original(envelope, **_expected(raw))


@pytest.mark.parametrize("target", ["d1", "nested"])
def test_valid_full_original_duplicate_keys_rejected(target: str) -> None:
    """同値重複でも完全な原本のkey重複を許可しない。"""
    raw = _raw()
    envelope = _envelope(raw)
    old, replacement = (
        ('"d1":1', '"d1":1,"d1":1')
        if target == "d1"
        else ('"value":1', '"value":1,"value":1')
    )
    assert old in envelope["wire_event_json"]
    envelope["wire_event_json"] = envelope["wire_event_json"].replace(old, replacement)
    with pytest.raises(WireOriginalError):
        decode_wire_original(envelope, **_expected(raw))


@pytest.mark.parametrize("row", _VECTORS["event_cases"], ids=lambda r: r["case_id"])
def test_w2_wire_view_all_fixed_events(row: dict[str, Any]) -> None:
    """既32行の原値全体とd2欠落/nullの区別を保持する。"""
    from pitchlog.sync.idempotency import _json_value
    from pitchlog.sync.wire_original import rejected_original_view

    raw = json.loads(row["raw_json"])
    expected = _expected(raw)
    digest = expected.pop("expected_event_fingerprint")
    view = rejected_original_view(_envelope(raw), ledger_fingerprint=digest, **expected)
    assert view.origin == "wire"
    assert view.event_fingerprint == row["expected_fingerprint"]
    assert _json_value(view.payload) == raw
    assert ("d2" in view.payload) == ("d2" in raw)


@pytest.mark.parametrize("embedded", (False, True))
def test_w2_legacy_uses_existing_fingerprint(embedded: bool) -> None:
    """旧helperの両分岐と旧payload参照をそのまま保持する。"""
    from pitchlog.sync.idempotency import source_fingerprint
    from pitchlog.sync.wire_original import rejected_original_view

    raw = _raw()
    if embedded:
        raw["operation_fingerprint"] = "a" * 64
    digest = raw["operation_fingerprint"] if embedded else source_fingerprint(raw)
    view = rejected_original_view(
        raw,
        ledger_fingerprint=digest,
        **{k: raw[k] for k in ("game_id", "d4", "d1", "d5")},
    )
    assert view.origin == "legacy"
    assert view.payload is raw
    assert view.event_fingerprint == digest


@pytest.mark.parametrize("domain", ("wire-request-v1:abc", "future:abc", "", False, 42))
@pytest.mark.parametrize("envelope", (False, True))
def test_w2_unknown_domains_never_fallback(domain: Any, envelope: bool) -> None:
    """未知/request領域を旧fallbackへ流さない。"""
    from pitchlog.sync.wire_original import rejected_original_view

    raw = _raw()
    source = _envelope(raw) if envelope else raw
    with pytest.raises(WireOriginalError, match=_ERROR):
        rejected_original_view(
            source,
            ledger_fingerprint=domain,
            **{k: raw[k] for k in ("game_id", "d4", "d1", "d5")},
        )


@pytest.mark.parametrize(
    "key", ("format_version", "codec_version", "event_fingerprint", "wire_event_json")
)
def test_w2_legacy_rejects_partial_envelope(key: str) -> None:
    """一部envelope keyと再計算した旧hashでも降格を拒否する。"""
    from pitchlog.sync.idempotency import source_fingerprint
    from pitchlog.sync.wire_original import rejected_original_view

    raw = _raw()
    raw[key] = None
    with pytest.raises(WireOriginalError, match=_ERROR):
        rejected_original_view(
            raw,
            ledger_fingerprint=source_fingerprint(raw),
            **{k: raw[k] for k in ("game_id", "d4", "d1", "d5")},
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "wire_as_legacy",
        "legacy_as_wire",
        "digest",
        "game_id",
        "d4",
        "d1",
        "d5",
        "format",
        "extra",
        "missing",
    ),
)
def test_w2_wire_rejects_domain_scope_format(mutation: str) -> None:
    """台帳domain/期待scope/原本版の全不一致を拒否する。"""
    from pitchlog.sync.wire_original import rejected_original_view

    raw = _raw()
    source = _envelope(raw)
    expected = _expected(raw)
    expected["ledger_fingerprint"] = expected.pop("expected_event_fingerprint")
    if mutation == "wire_as_legacy":
        expected["ledger_fingerprint"] = "a" * 64
    elif mutation == "legacy_as_wire":
        source = raw
    elif mutation == "digest":
        expected["ledger_fingerprint"] = "wire-v1:" + "a" * 64
    elif mutation in ("game_id", "d5"):
        expected[mutation] = "99999999-9999-4999-8999-999999999999"
    elif mutation == "d4":
        expected[mutation] = "other-generation"
    elif mutation == "d1":
        expected[mutation] = 2
    elif mutation == "format":
        source["format_version"] = "future"
    elif mutation == "extra":
        source["extra"] = None
    else:
        del source["format_version"]
    with pytest.raises(WireOriginalError, match=_ERROR):
        rejected_original_view(source, **expected)


def test_w2_legacy_wrong_hash_type_and_nonmapping_rejected() -> None:
    """旧helper異型と不一致・非Mappingを固定pure例外で拒否する。"""
    from pitchlog.sync.wire_original import rejected_original_view

    raw = _raw()
    invalid_values: list[Any] = [
        None,
        [],
        {**raw, "operation_fingerprint": False},
        {**raw, "operation_fingerprint": "b" * 64},
    ]
    for source in invalid_values:
        with pytest.raises(WireOriginalError, match=_ERROR):
            rejected_original_view(
                source,
                ledger_fingerprint="a" * 64,
                **{k: raw[k] for k in ("game_id", "d4", "d1", "d5")},
            )


@pytest.mark.parametrize("domain", ("wire-request-v1:abc", "future:abc"))
def test_w2_unknown_domain_matching_embedded_hash_still_rejected(domain: str) -> None:
    """原本と台帳へ同じ未知domainを入れても旧helper一致で迂回しない。"""
    from pitchlog.sync.wire_original import rejected_original_view

    raw: dict[str, Any] = {**_raw(), "operation_fingerprint": domain}
    with pytest.raises(WireOriginalError, match=_ERROR):
        rejected_original_view(
            raw,
            ledger_fingerprint=domain,
            **{k: raw[k] for k in ("game_id", "d4", "d1", "d5")},
        )
