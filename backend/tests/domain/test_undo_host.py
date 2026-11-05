"""取消の閉host境界を実artifactと破損応答対向で検証する。"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pitchlog.domainrt import undo
from pitchlog.domainrt.host import DomainRuntimeError, NodeDomainHost

_ROOT = Path(__file__).resolve().parents[3]
_CASES = json.loads(
    (_ROOT / "contracts/state-transition/undo_cases_v1.json").read_text()
)
_ARTIFACT = _ROOT / "frontend/public/domain/pitchlog-domain.js"
_DECLARATION = _ROOT / "frontend/public/domain/pitchlog-domain.json"


@pytest.mark.parametrize("case", _CASES["cases"], ids=lambda case: case["caseId"])
def test_actual_undo_host_preserves_every_contract_value(case, monkeypatch) -> None:
    """別作者規範の全状態・4比較面・完全履歴を実hostで比較する。"""
    monkeypatch.setattr(
        undo, "open_domain_host", lambda: NodeDomainHost(_ARTIFACT, _DECLARATION)
    )
    calls = []
    original_call = NodeDomainHost.call

    def recorded_call(host, operation, raw):
        calls.append((operation, raw))
        return original_call(host, operation, raw)

    monkeypatch.setattr(NodeDomainHost, "call", recorded_call)
    request = undo.UndoRequest(json.dumps(case["request"]))
    actual = undo.apply_undo(request)
    assert calls == [("applyUndo", request.json)]
    assert actual.to_wire() == case["expected"]
    assert request.to_wire() == case["request"]


@pytest.mark.parametrize(
    "raw",
    [
        "null",
        "[]",
        '{"ok":true,"value":{}}',
        '{"ok":false,"error":{"code":"UNKNOWN"}}',
        '{"ok":false,"error":{"code":"INVALID_REQUEST","extra":true}}',
        '{"ok":false,"ok":true,"error":{"code":"INVALID_REQUEST"}}',
        '{"ok":NaN,"error":{"code":"INVALID_REQUEST"}}',
        '{"ok":0,"error":{"code":"INVALID_REQUEST"}}',
    ],
)
def test_unknown_or_broken_response_is_a_protocol_failure(raw: str) -> None:
    """故障を内容拒否へ変換せず、閉応答以外を拒否する。"""
    with pytest.raises(undo.UndoProtocolError):
        undo.decode_undo_response(raw)


@pytest.mark.parametrize(
    "code",
    [
        "INVALID_JSON",
        "INVALID_REQUEST",
        "INVALID_DECIMAL_INTEGER",
        "UNSUPPORTED_T1_SCOPE",
    ],
)
def test_only_existing_domain_failure_codes_survive(code: str) -> None:
    """既数学非成功を同期拒否やD5状態へ読み替えない。"""
    value = {"ok": False, "error": {"code": code}}
    assert undo.decode_undo_response(json.dumps(value)).to_wire() == value


@pytest.mark.parametrize("fault", ["extra", "missing", "numeric", "newline", "flag"])
def test_complete_response_cannot_lose_or_coerce_fields(fault: str) -> None:
    """全23flag・5成功項目・正準整数の欠落や暗黙変換を拒否する。"""
    value = copy.deepcopy(_CASES["cases"][0]["expected"])
    if fault == "extra":
        value["value"]["extra"] = True
    elif fault == "missing":
        del value["value"]["historyContext"]
    elif fault == "numeric":
        value["value"]["after"]["stateFields"]["state.count.balls"] = 0
    elif fault == "newline":
        value["value"]["after"]["stateFields"]["state.inning"] = "1\n"
    else:
        del value["value"]["stateEffect"]["statFlags"]["打点"]
    with pytest.raises(undo.UndoProtocolError):
        undo.decode_undo_response(json.dumps(value))


@pytest.mark.parametrize(
    "raw",
    [
        "null",
        "{}",
        '{"current":{},"current":{},"history":{"stack":[]}}',
        '{"current":NaN,"history":{"stack":[]}}',
    ],
)
def test_bad_request_is_rejected_before_any_host(raw: str, monkeypatch) -> None:
    """欠落・重複・非JSON値をhost実行より先に拒否する。"""
    monkeypatch.setattr(undo, "open_domain_host", lambda: pytest.fail("host到達"))
    with pytest.raises(undo.UndoRequestError):
        undo.UndoRequest(raw)


def test_wire_copies_cannot_mutate_frozen_request_or_response() -> None:
    """呼出者の返却値変更で次回wireを変化させない。"""
    case = _CASES["cases"][0]
    request = undo.UndoRequest(json.dumps(case["request"]))
    response = undo.decode_undo_response(json.dumps(case["expected"]))
    request.to_wire()["current"].clear()
    response.to_wire()["value"].clear()
    assert request.to_wire() == case["request"]
    assert response.to_wire() == case["expected"]
    with pytest.raises(FrozenInstanceError):
        setattr(request, "json", "{}")


def test_runtime_failure_is_not_a_content_rejection(monkeypatch) -> None:
    """実行故障を内容Falseや新D5利用可へ変換しない。"""
    fault = DomainRuntimeError("TIME_LIMIT", "故障対向")

    def unavailable():
        raise fault

    monkeypatch.setattr(undo, "open_domain_host", unavailable)
    request = undo.UndoRequest(json.dumps(_CASES["cases"][0]["request"]))
    with pytest.raises(DomainRuntimeError) as caught:
        undo.apply_undo(request)
    assert caught.value is fault


def test_untyped_call_is_rejected_before_host(monkeypatch) -> None:
    """JSONや自由objectを専用実型と同等に扱わない。"""
    monkeypatch.setattr(undo, "open_domain_host", lambda: pytest.fail("host到達"))
    with pytest.raises(TypeError):
        undo.apply_undo(_CASES["cases"][0]["request"])


def test_decimal_size_and_history_depth_have_no_decoder_cap() -> None:
    """十進文字列の桁数と完全履歴を便宜的に切り捨てない。"""
    value = copy.deepcopy(
        next(
            row["request"]
            for row in _CASES["cases"]
            if row["request"]["history"]["stack"]
        )
    )
    value["current"]["stateFields"]["state.inning"] = "1" * 5001
    value["history"]["stack"] = value["history"]["stack"][:1] * 513
    # ここは構造検査のみ。head/current一致の意味判定をPythonへ複製しない。
    assert undo.UndoRequest(json.dumps(value)).to_wire() == value


def test_call_failure_after_start_still_propagates(monkeypatch) -> None:
    """起動後の実行故障も保存可否や内容拒否へ変換しない。"""
    fault = DomainRuntimeError("TIME_LIMIT", "実行後の故障対向")
    calls = []

    class Broken:
        """非成功の故障だけを注入し、成功応答は作らない。"""

        def call(self, operation, raw):
            """呼出しを記録して同じ技術故障を伝播する。"""
            calls.append((operation, raw))
            raise fault

    @contextmanager
    def broken_host():
        yield Broken()

    monkeypatch.setattr(undo, "open_domain_host", broken_host)
    request = undo.UndoRequest(json.dumps(_CASES["cases"][0]["request"]))
    with pytest.raises(DomainRuntimeError) as caught:
        undo.apply_undo(request)
    assert caught.value is fault
    assert calls == [("applyUndo", request.json)]


@pytest.mark.parametrize("definition", ["Request", "Response"])
@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef"])
@pytest.mark.parametrize(
    "uri",
    [
        "https://example.invalid/undo-schema",
        "http://example.invalid/undo-schema",
        "file:///unavailable-undo-schema.json",
    ],
)
def test_external_schema_resources_never_perform_io(
    definition: str, keyword: str, uri: str, monkeypatch, tmp_path: Path
) -> None:
    """外部refはI/Oへ到達せず要求/応答とも配置故障として拒否する。"""
    import urllib.request

    schema = json.loads(undo._SCHEMA_PATH.read_text())
    schema["$defs"][definition] = {keyword: uri}
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(schema))
    monkeypatch.setattr(undo, "_SCHEMA_PATH", path)
    calls = []

    def network_forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("外部schema取得へ到達")

    monkeypatch.setattr(urllib.request, "urlopen", network_forbidden)
    case = _CASES["cases"][0]
    undo._validator.cache_clear()
    try:
        with pytest.raises(undo.UndoProtocolError):
            if definition == "Request":
                undo.UndoRequest(json.dumps(case["request"]))
            else:
                undo.decode_undo_response(json.dumps(case["expected"]))
        assert calls == []
    finally:
        undo._validator.cache_clear()
