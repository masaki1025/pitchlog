"""通常33入力と実Node artifactの全値・履歴保持を検証する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.domainrt.ordinary_pitch import (
    OrdinaryPitchProtocolError,
    OrdinaryPitchRequest,
    decode_ordinary_pitch_response,
    evaluate_ordinary_pitch,
)

_ROOT = Path(__file__).resolve().parents[3]
_VECTORS = json.loads(
    (_ROOT / "contracts/state-transition/ordinary_pitch_vectors_v1.json").read_text()
)
_SCHEMA = Draft202012Validator(
    json.loads(
        (
            _ROOT / "contracts/state-transition/ordinary_pitch_response_schema_v1.json"
        ).read_text()
    )
)
_ARTIFACT = _ROOT / "frontend/public/domain/pitchlog-domain.js"
_DECLARATION = _ROOT / "frontend/public/domain/pitchlog-domain.json"


def test_all_33_formal_vectors_through_actual_node() -> None:
    """正式33全値を同一artifact経由で完全比較する。"""
    assert len(_VECTORS["cases"]) == 33
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        for case in _VECTORS["cases"]:
            request = OrdinaryPitchRequest.model_validate_json(
                json.dumps(case["request"])
            )
            actual = json.loads(
                host.call(
                    "deriveOrdinaryPitch",
                    request.model_dump_json(by_alias=True, exclude_unset=True),
                )
            )
            _SCHEMA.validate(actual)
            assert actual == case["expected"]
            decoded = decode_ordinary_pitch_response(json.dumps(actual))
            assert (
                decoded.model_dump(mode="json", by_alias=True, exclude_unset=True)
                == actual
            )


def test_real_forward_result_is_only_source_of_following_history() -> None:
    """実calledの出力だけをballへ渡し先頭とtailを完全比較する。"""
    scenario = _VECTORS["historyTailCases"][0]
    first = next(
        case for case in _VECTORS["cases"] if case["caseId"] == scenario["firstCaseId"]
    )
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        h = json.loads(host.call("deriveOrdinaryPitch", json.dumps(first["request"])))
        second = copy.deepcopy(scenario["second"]["request"])
        second["before"] = h["value"]["after"]
        second["history"]["stack"] = h["value"]["historyContext"]
        actual = json.loads(host.call("deriveOrdinaryPitch", json.dumps(second)))
    assert actual == scenario["second"]["expected"]
    _SCHEMA.validate(actual)


def test_typed_caller_calls_fixed_host_once_without_python_calculation() -> None:
    """固定operation literalと要求全wireが一度だけ呼ばれる。"""
    case = _VECTORS["cases"][0]
    request = OrdinaryPitchRequest.model_validate_json(json.dumps(case["request"]))
    host = MagicMock()
    host.call.return_value = json.dumps(case["expected"])
    manager = MagicMock()
    manager.__enter__.return_value = host
    with patch(
        "pitchlog.domainrt.ordinary_pitch.open_domain_host", return_value=manager
    ) as opener:
        actual = evaluate_ordinary_pitch(request)
    opener.assert_called_once_with()
    host.call.assert_called_once_with(
        "deriveOrdinaryPitch",
        request.model_dump_json(by_alias=True, exclude_unset=True),
    )
    assert (
        actual.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == case["expected"]
    )
    with pytest.raises(ValidationError):
        setattr(request.history, "stack", ())


@pytest.mark.parametrize(
    "mutation",
    [
        "history-missing",
        "stack-missing",
        "stack-null",
        "extra",
        "state-extra",
        "null-difference",
        "alias-name",
        "integer-number",
        "integer-leading-zero",
        "boolean-number",
        "missing-flag",
    ],
)
def test_request_dto_rejects_closed_shape_violations(mutation: str) -> None:
    """未知fieldや履歴の既定値補完を拒否する。"""
    request = copy.deepcopy(_VECTORS["historyTailCases"][0]["second"]["request"])
    match mutation:
        case "history-missing":
            del request["history"]
        case "stack-missing":
            request["history"] = {}
        case "stack-null":
            request["history"]["stack"] = None
        case "extra":
            request["extra"] = "x"
        case "state-extra":
            request["before"]["stateFields"]["extra"] = "0"
        case "null-difference":
            request["history"]["stack"][0]["difference"]["stateFields"][
                "state.outs"
            ] = None
        case "alias-name":
            request["before"]["stateFields"]["half"] = request["before"][
                "stateFields"
            ].pop("state.half")
        case "integer-number":
            request["before"]["stateFields"]["state.count.balls"] = 1
        case "integer-leading-zero":
            request["history"]["stack"][0]["difference"]["stateFields"][
                "state.count.strikes"
            ]["after"] = "01"
        case "boolean-number":
            request["before"]["stateFields"]["state.gameEnded"] = 0
        case "missing-flag":
            del request["history"]["stack"][0]["difference"]["statFlags"]["打点"]
    with pytest.raises(ValidationError):
        OrdinaryPitchRequest.model_validate_json(
            json.dumps(request), by_alias=True, by_name=False
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-history",
        "empty-history",
        "extra",
        "unknown-code",
        "ok-number",
        "flag-number",
        "flag-true",
        "delta-two",
        "duplicate",
        "nonfinite",
        "head-extra",
        "head-board",
        "head-axis",
        "after-scope",
    ],
)
def test_response_dto_rejects_corrupt_guest_wire(mutation: str) -> None:
    """未知応答・非JSON・型同値化・構造の取りこぼしを拒否する。"""
    response = copy.deepcopy(_VECTORS["cases"][0]["expected"])
    match mutation:
        case "missing-history":
            del response["value"]["historyContext"]
        case "empty-history":
            response["value"]["historyContext"] = []
        case "extra":
            response["value"]["extra"] = None
        case "unknown-code":
            response = {"ok": False, "error": {"code": "UNKNOWN"}}
        case "ok-number":
            response["ok"] = 1
        case "flag-number":
            response["value"]["statFlags"]["得点"] = 0
        case "flag-true":
            response["value"]["statFlags"]["得点"] = True
        case "delta-two":
            response["value"]["countEffect"]["strikes"]["value"] = "2"
        case "head-extra":
            response["value"]["historyContext"][0]["difference"]["stateFields"][
                "unknown"
            ] = {"before": "0", "after": "1"}
        case "head-board":
            response["value"]["historyContext"][0]["difference"]["scoreboard"][
                "hits"
            ] = {"before": "0", "after": "1"}
        case "head-axis":
            difference = response["value"]["historyContext"][0]["difference"][
                "stateFields"
            ]
            difference["state.count.balls"] = difference.pop("state.count.strikes")
        case "after-scope":
            response["value"]["after"]["stateFields"]["state.inning"] = "2"
    raw = json.dumps(response)
    if mutation == "duplicate":
        raw = '{"ok":false,"ok":false,"error":{"code":"INVALID_REQUEST"}}'
    if mutation == "nonfinite":
        raw = '{"ok":false,"error":{"code":NaN}}'
    with pytest.raises(OrdinaryPitchProtocolError):
        decode_ordinary_pitch_response(raw)
