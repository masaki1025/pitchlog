"""BB/HBPの全値・閉decoder・固定host一回呼出しを純試験する。"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from pitchlog.domainrt.host import DomainRuntimeError, NodeDomainHost
from pitchlog.domainrt.terminal_pitch import (
    TerminalPitchProtocolError,
    TerminalPitchRequest,
    decode_terminal_pitch_response,
    evaluate_terminal_pitch,
)

_ROOT = Path(__file__).resolve().parents[3]
_VECTORS = json.loads(
    (_ROOT / "contracts/state-transition/terminal_pitch_cases_v1.json").read_text()
)
_SCHEMA = json.loads(
    (_ROOT / "contracts/state-transition/terminal_pitch_schema_v1.json").read_text()
)
_RESPONSE_SCHEMA = Draft202012Validator(
    {"$ref": "#/$defs/TerminalPitchResponse", "$defs": _SCHEMA["$defs"]}
)
_ARTIFACT = _ROOT / "frontend/public/domain/pitchlog-domain.js"
_DECLARATION = _ROOT / "frontend/public/domain/pitchlog-domain.json"


def test_actual_artifact_15_and_810_full_responses(
    record_property: Callable[[str, object], None],
) -> None:
    """期待は受理規範を展開し、製品出力から作らない。"""
    count = 0
    last_request = None
    last_expected = None
    last_direct = None
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        for case in _VECTORS["cases"]:
            for outs in _VECTORS["crossProduct"]["outs"]:
                for half in _VECTORS["crossProduct"]["half"]:
                    for order in _VECTORS["crossProduct"]["battingOrder"]:
                        request, expected = (
                            copy.deepcopy(case["request"]),
                            copy.deepcopy(case["expected"]),
                        )
                        after_order = _VECTORS["crossProduct"]["nextBattingOrder"][
                            order
                        ]
                        request["before"]["stateFields"].update(
                            {
                                "state.outs": outs,
                                "state.half": half,
                                "state.battingOrder": order,
                            }
                        )
                        expected["value"]["after"]["stateFields"].update(
                            {
                                "state.outs": outs,
                                "state.half": half,
                                "state.battingOrder": after_order,
                            }
                        )
                        expected["value"]["historyContext"][0]["difference"][
                            "stateFields"
                        ]["state.battingOrder"] = {
                            "before": order,
                            "after": after_order,
                        }
                        typed = TerminalPitchRequest.model_validate_json(
                            json.dumps(request)
                        )
                        raw = host.call(
                            "deriveTerminalPitch",
                            typed.model_dump_json(by_alias=True, exclude_unset=True),
                        )
                        actual = json.loads(raw)
                        _RESPONSE_SCHEMA.validate(actual)
                        assert actual == expected
                        assert (
                            decode_terminal_pitch_response(raw).model_dump(
                                mode="json", by_alias=True, exclude_unset=True
                            )
                            == actual
                        )
                        last_request, last_expected, last_direct = (
                            typed,
                            expected,
                            actual,
                        )
                        count += 1
    assert count == 810
    assert (
        last_request is not None
        and last_expected is not None
        and last_direct is not None
    )
    entrypoint = evaluate_terminal_pitch(last_request).model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    assert entrypoint == last_expected == last_direct
    _record_property(
        record_property,
        "terminalStateAxes",
        "invariant",
        count,
        "TERMINAL-HBP-S2-B3-outs2-bottom-order9",
        last_expected,
        entrypoint,
        last_direct,
    )


@pytest.mark.parametrize("case", _VECTORS["cases"], ids=lambda case: case["caseId"])
def test_fixed_product_host_full_response(case: dict) -> None:
    """製品固定pathを使うcallerも全15例の全wire値を保つ。"""
    request = TerminalPitchRequest.model_validate_json(json.dumps(case["request"]))
    result = evaluate_terminal_pitch(request)
    assert (
        result.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == case["expected"]
    )


def test_fixed_host_called_once_and_fault_not_completed() -> None:
    """一回のhost呼出し、未知応答拒否、障害伝播を観測する。"""
    case = _VECTORS["cases"][0]
    request = TerminalPitchRequest.model_validate_json(json.dumps(case["request"]))
    host = MagicMock()
    host.call.return_value = json.dumps(case["expected"])
    with patch("pitchlog.domainrt.terminal_pitch.open_domain_host") as factory:
        factory.return_value.__enter__.return_value = host
        result = evaluate_terminal_pitch(request)
        factory.assert_called_once_with()
        host.call.assert_called_once_with(
            "deriveTerminalPitch",
            request.model_dump_json(by_alias=True, exclude_unset=True),
        )
        assert (
            result.model_dump(mode="json", by_alias=True, exclude_unset=True)
            == case["expected"]
        )
        host.call.return_value = '{"ok":true}'
        with pytest.raises(TerminalPitchProtocolError):
            evaluate_terminal_pitch(request)
        host.call.side_effect = DomainRuntimeError("TIME_LIMIT", "試験故障")
        with pytest.raises(DomainRuntimeError, match="試験故障"):
            evaluate_terminal_pitch(request)
    with pytest.raises(TypeError):
        evaluate_terminal_pitch(case["request"])


@pytest.mark.parametrize(
    "flag", list(_VECTORS["cases"][0]["expected"]["value"]["statFlags"])
)
def test_decoder_rejects_each_corrupt_flag(flag: str) -> None:
    """23flagの各一箇所破損を成功へ補完しない。"""
    for case in _VECTORS["cases"]:
        wire = copy.deepcopy(case["expected"])
        wire["value"]["statFlags"][flag] = not wire["value"]["statFlags"][flag]
        with pytest.raises(TerminalPitchProtocolError):
            decode_terminal_pitch_response(json.dumps(wire))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "count",
        "base",
        "numeric",
        "boolean",
        "empty-history",
        "loaded",
        "negative-history",
        "null",
        "ended",
        "outs",
        "order",
        "inning",
    ],
)
def test_decoder_rejects_structural_and_canonical_corruption(mutation: str) -> None:
    """全比較面の閉形/有限範囲と新履歴語彙を検査する。"""
    wire = copy.deepcopy(_VECTORS["cases"][0]["expected"])
    value = wire["value"]
    if mutation == "missing":
        del value["after"]
    elif mutation == "extra":
        value["unexpected"] = "x"
    elif mutation == "count":
        value["countEffect"]["balls"]["value"] = "0"
    elif mutation == "base":
        value["batterDestination"]["base"] = "2"
    elif mutation == "numeric":
        value["after"]["scoreboard"]["walks"] = 1
    elif mutation == "boolean":
        value["plateAppearanceEnded"] = 1
    elif mutation == "empty-history":
        value["historyContext"] = []
    elif mutation == "loaded":
        value["historyContext"][0]["difference"]["stateFields"]["state.runners"][
            "before"
        ] = "loaded"
    elif mutation == "negative-history":
        value["historyContext"][0]["difference"]["stateFields"]["state.count.balls"][
            "before"
        ] = "-1"
    elif mutation == "null":
        value["historyContext"][0]["difference"]["scoreboard"]["hits"] = None
    elif mutation == "ended":
        value["after"]["stateFields"]["state.gameEnded"] = True
    elif mutation == "outs":
        value["after"]["stateFields"]["state.outs"] = "3"
    elif mutation == "order":
        value["after"]["stateFields"]["state.battingOrder"] = "0"
    else:
        value["after"]["stateFields"]["state.inning"] = "0"
    with pytest.raises(TerminalPitchProtocolError):
        decode_terminal_pitch_response(json.dumps(wire))


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        '{"ok":false,"ok":false,"error":{"code":"INVALID_JSON"}}',
        '{"ok":false,"error":{"code":"OTHER"}}',
        '{"ok":NaN}',
        '{"ok":1,"error":{"code":"INVALID_JSON"}}',
    ],
)
def test_decoder_rejects_bad_json_and_unknown_envelope(raw: str) -> None:
    """重複/非有限/未知code/数値boolを拒否する。"""
    with pytest.raises(TerminalPitchProtocolError):
        decode_terminal_pitch_response(raw)


def test_history_tail_and_structural_request_refusals() -> None:
    """新正準占有のtailを全値保持し、旧loaded等を拒否する。"""
    case = copy.deepcopy(_VECTORS["cases"][0])
    tail = copy.deepcopy(case["expected"]["value"]["historyContext"][0])
    tail["difference"]["stateFields"]["state.runners"]["before"] = "first-second-third"
    case["request"]["history"]["stack"] = [tail, copy.deepcopy(tail)]
    case["expected"]["value"]["historyContext"].extend([tail, copy.deepcopy(tail)])
    result = evaluate_terminal_pitch(
        TerminalPitchRequest.model_validate_json(json.dumps(case["request"]))
    )
    assert (
        result.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == case["expected"]
    )
    for replacement in ["loaded", "unknown", None, True]:
        changed = copy.deepcopy(case["request"])
        changed["history"]["stack"][0]["difference"]["stateFields"]["state.runners"][
            "before"
        ] = replacement
        with pytest.raises(ValidationError):
            TerminalPitchRequest.model_validate_json(json.dumps(changed))
    for field in ["eventKind", "before", "history"]:
        changed = copy.deepcopy(case["request"])
        del changed[field]
        with pytest.raises(ValidationError):
            TerminalPitchRequest.model_validate_json(json.dumps(changed))


def _record_property(
    record_property: Callable[[str, object], None],
    property_id: str,
    kind: str,
    count: int,
    case_id: str,
    expected: dict,
    entrypoint_output: dict,
    direct_output: dict,
) -> None:
    """既独立収集器へ実測二経路と実artifact hashを渡す。"""
    digest = "sha256:" + hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest()
    properties = {
        "calculation": "terminal-empty-bb-hbp-v1",
        "propertyId": property_id,
        "propertyKind": kind,
        "generatedCases": count,
        "status": "passed",
        "trace": {
            "vector": "terminalPitchVectors",
            "case": case_id,
            "entrypointId": "terminalPitchServer",
            "directTargetId": "terminalPitchDirect",
            "expected": expected,
            "entrypointOutput": entrypoint_output,
            "directTargetOutput": direct_output,
            "artifactHashes": {"single": digest},
            "issuedSqlOrAst": None,
            "stageIO": [],
        },
    }
    for name, value in properties.items():
        record_property(name, json.dumps(value) if isinstance(value, dict) else value)


def test_terminal_d11_real_host_parity(
    record_property: Callable[[str, object], None],
) -> None:
    """規範15例を実callerと実direct hostで別々に実行して比較する。"""
    count = 0
    last = None
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        for case in _VECTORS["cases"]:
            typed = TerminalPitchRequest.model_validate_json(
                json.dumps(case["request"])
            )
            entrypoint = evaluate_terminal_pitch(typed).model_dump(
                mode="json", by_alias=True, exclude_unset=True
            )
            direct = json.loads(
                host.call(
                    "deriveTerminalPitch",
                    typed.model_dump_json(by_alias=True, exclude_unset=True),
                )
            )
            assert entrypoint == case["expected"] == direct
            last = (case, entrypoint, direct)
            count += 1
    assert count == 15 and last is not None
    case, entrypoint, direct = last
    _record_property(
        record_property,
        "terminalHostParity",
        "equivalence",
        count,
        case["caseId"],
        case["expected"],
        entrypoint,
        direct,
    )


def test_terminal_d11_candidate_declarations_are_closed() -> None:
    """対象別候補は既manifest schemaと有限独立catalogに適合する。"""
    manifest = json.loads(
        (_ROOT / "backend/domain/terminal-pitch-manifest.json").read_text()
    )
    schema = json.loads((_ROOT / "backend/domain/manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    catalog = json.loads((_ROOT / manifest["propertyCatalog"]["path"]).read_text())
    catalog_schema = json.loads(
        (_ROOT / manifest["propertyCatalog"]["schema"]).read_text()
    )
    Draft202012Validator(catalog_schema).validate(catalog)
    calculation = manifest["calculations"][0]
    assert calculation["calculation"] == _VECTORS["calculation"] == catalog["scope"]
    assert (
        calculation["directTargets"][0]["hash"]
        == "sha256:" + hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest()
    )
    assert {
        (p["propertyId"], p["propertyKind"]) for p in calculation["properties"]
    } == {(p["propertyId"], p["propertyKind"]) for p in catalog["predicates"]}
    assert (
        calculation["vectors"][0]["path"]
        == "contracts/state-transition/terminal_pitch_cases_v1.json"
    )
    assert len(_VECTORS["cases"]) == 15
    for case in _VECTORS["cases"]:
        projected = {
            "expected": case["expected"],
            "comparison": "exact",
            "provenance": "付録E 打撃結果・状態遷移マトリクス",
        }
        Draft202012Validator(
            {"$ref": "#/$defs/ExpectedValue", "$defs": schema["$defs"]}
        ).validate(projected)
        assert projected["expected"] is case["expected"]
