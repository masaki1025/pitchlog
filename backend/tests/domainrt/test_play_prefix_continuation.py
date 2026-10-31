"""v2契約・実artifact・型付きcaller・旧v1互換の純影響検査。"""

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
from pitchlog.domainrt.play_prefix_continuation import (
    PlayPrefixProtocolError,
    PlayPrefixRequest,
    decode_play_prefix_response,
    evaluate_play_prefix_continuation,
)

_ROOT = Path(__file__).resolve().parents[3]
_BASE = _ROOT / "contracts/state-transition"
_VECTORS = json.loads((_BASE / "play_prefix_v2_cases.json").read_text())
_SCHEMA = json.loads((_BASE / "play_prefix_v2_schema.json").read_text())
_ARTIFACT = _ROOT / "frontend/public/domain/pitchlog-domain.js"
_DECLARATION = _ROOT / "frontend/public/domain/pitchlog-domain.json"


def test_contract_closed_request_response_and_no_expected_output_generation() -> None:
    """既規範56期待を閉schema/DTOへ全値写像する。"""
    assert len(_VECTORS["cases"]) == 56
    for key, definition in [("request", "PlayRequest"), ("expected", "PlayResponse")]:
        validator = Draft202012Validator(
            {"$ref": "#/$defs/" + definition, "$defs": _SCHEMA["$defs"]}
        )
        for case in _VECTORS["cases"]:
            validator.validate(case[key])
    for case in _VECTORS["cases"]:
        request = PlayPrefixRequest.model_validate_json(json.dumps(case["request"]))
        assert (
            request.model_dump(mode="json", by_alias=True, exclude_unset=True)
            == case["request"]
        )
        response = decode_play_prefix_response(json.dumps(case["expected"]))
        assert (
            response.model_dump(mode="json", by_alias=True, exclude_unset=True)
            == case["expected"]
        )


def test_all_56_through_product_host_and_typed_caller(
    record_property: Callable[[str, object], None],
) -> None:
    """D11包絡も実消費し、型付きcaller/直接hostの56全値実測を記録する。"""
    source = _BASE / "play_prefix_v2_cases.json"
    wrapped = json.loads((_BASE / "play_prefix_v2_d11_vectors.json").read_text())
    assert (
        wrapped["sourcePath"] == "contracts/state-transition/play_prefix_v2_cases.json"
    )
    assert wrapped["sourceSha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert len(wrapped["cases"]) == len(_VECTORS["cases"]) == 56
    manifest_schema = json.loads(
        (_ROOT / "backend/domain/manifest.schema.json").read_text()
    )
    expectation_schema = Draft202012Validator(
        {"$ref": "#/$defs/ExpectedValue", "$defs": manifest_schema["$defs"]}
    )
    digest = hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest()
    assert wrapped["executionArtifactSha256"] == digest
    count = 0
    last = None
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        assert host.artifact_sha256 == digest
        for case, envelope in zip(_VECTORS["cases"], wrapped["cases"], strict=True):
            assert set(envelope) == {"caseId", "request", "expected"}
            assert envelope["caseId"] == case["caseId"]
            assert envelope["request"] == case["request"]
            expectation_schema.validate(envelope["expected"])
            assert envelope["expected"]["comparison"] == "exact"
            assert envelope["expected"]["provenance"] == (
                "NFR-018 (b)② 差分の検出可能性"
            )
            expected = envelope["expected"]["expected"]
            assert expected == case["expected"]
            typed = PlayPrefixRequest.model_validate_json(
                json.dumps(envelope["request"])
            )
            raw = host.call(
                "derivePlayPrefixWithContinuation",
                typed.model_dump_json(by_alias=True, exclude_unset=True),
            )
            direct = json.loads(raw)
            assert direct == expected, case["caseId"]
            result = evaluate_play_prefix_continuation(typed)
            entrypoint = result.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            )
            assert entrypoint == expected, case["caseId"]
            last = (case["caseId"], expected, entrypoint, direct)
            count += 1
    assert count == 56 and last is not None
    case_id, expected, entrypoint, direct = last
    measured = {
        "calculation": "play-prefix-v2",
        "propertyId": "playPrefixHostParity",
        "propertyKind": "equivalence",
        "generatedCases": count,
        "status": "passed",
        "trace": {
            "vector": "playPrefixVectors",
            "case": case_id,
            "entrypointId": "playPrefixServer",
            "directTargetId": "playPrefixDirect",
            "expected": expected,
            "entrypointOutput": entrypoint,
            "directTargetOutput": direct,
            "artifactHashes": {"single": "sha256:" + digest},
            "issuedSqlOrAst": None,
            "stageIO": [],
        },
    }
    for name, value in measured.items():
        record_property(name, json.dumps(value) if isinstance(value, dict) else value)


def test_fixed_host_once_and_loaded_hash_mismatch_is_not_success() -> None:
    """実loaded hashを一回call前に照合し、相違/故障/破損を補完しない。"""
    case = _VECTORS["cases"][0]
    request = PlayPrefixRequest.model_validate_json(json.dumps(case["request"]))
    host = MagicMock()
    host.artifact_sha256 = request.source.execution_artifact_sha256
    host.call.return_value = json.dumps(case["expected"])
    with patch(
        "pitchlog.domainrt.play_prefix_continuation.open_domain_host"
    ) as factory:
        factory.return_value.__enter__.return_value = host
        actual = evaluate_play_prefix_continuation(request)
        assert (
            actual.model_dump(mode="json", by_alias=True, exclude_unset=True)
            == case["expected"]
        )
        factory.assert_called_once_with()
        host.call.assert_called_once_with(
            "derivePlayPrefixWithContinuation",
            request.model_dump_json(by_alias=True, exclude_unset=True),
        )
        host.call.reset_mock()
        host.artifact_sha256 = "9" * 64
        with pytest.raises(PlayPrefixProtocolError):
            evaluate_play_prefix_continuation(request)
        host.call.assert_not_called()
        host.artifact_sha256 = request.source.execution_artifact_sha256
        host.call.side_effect = DomainRuntimeError("TIME_LIMIT", "試験故障")
        with pytest.raises(DomainRuntimeError, match="試験故障"):
            evaluate_play_prefix_continuation(request)
        host.call.side_effect = None
        host.call.return_value = '{"ok":true}'
        with pytest.raises(PlayPrefixProtocolError):
            evaluate_play_prefix_continuation(request)
    with pytest.raises(TypeError):
        evaluate_play_prefix_continuation(case["request"])


def test_loaded_hash_property_does_not_reread_or_allow_assignment() -> None:
    """起動後にファイルを読まず、既検証source自身のhashだけを返す。"""
    digest = hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest()
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("再読込禁止")):
            assert host.artifact_sha256 == digest
        with pytest.raises(AttributeError):
            setattr(host, "artifact_sha256", "9" * 64)


@pytest.mark.parametrize("field", ["source", "t1", "playIdentity", "nextCheckpoint"])
def test_request_missing_members_are_not_completed(field: str) -> None:
    """sourceや参照の欠損を暗黙に生成しない。"""
    request = copy.deepcopy(_VECTORS["cases"][0]["request"])
    del request[field]
    with pytest.raises(ValidationError):
        PlayPrefixRequest.model_validate_json(json.dumps(request))


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "numeric",
        "boolean",
        "history-extra",
        "runner-null",
        "v1-ref",
        "missing-t2",
        "bad-count",
        "bad-flags",
        "negative",
        "loaded",
        "invalid-code",
    ],
)
def test_response_decoder_rejects_corrupt_closed_wire(mutation: str) -> None:
    """新応答の余剰/型/欠損/旧語彙を厳密に拒否する。"""
    wire = copy.deepcopy(_VECTORS["cases"][0]["expected"])
    value = wire["value"]
    if mutation == "extra":
        value["ack"] = True
    elif mutation == "numeric":
        value["nextPrefixRef"]["length"] = 4
    elif mutation == "boolean":
        value["t1"]["plateAppearanceEnded"] = 1
    elif mutation == "history-extra":
        value["newHistoryEntry"]["difference"]["unexpected"] = []
    elif mutation == "runner-null":
        value["runners"][0]["responsiblePitcherId"] = None
    elif mutation == "v1-ref":
        value["nextPrefixRef"]["version"] = "1"
    elif mutation == "missing-t2":
        del value["t2"]
    elif mutation == "bad-count":
        value["t1"]["countEffect"]["balls"]["value"] = "0"
    elif mutation == "bad-flags":
        value["t1"]["statFlags"]["打数"] = True
    elif mutation == "negative":
        value["newHistoryEntry"]["difference"]["stateFields"]["state.count.balls"][
            "before"
        ] = "-1"
    elif mutation == "loaded":
        value["t1"]["after"]["stateFields"]["state.runners"] = "loaded"
    else:
        wire = {"ok": False, "error": {"code": "SAVE_OK"}}
    with pytest.raises(PlayPrefixProtocolError):
        decode_play_prefix_response(json.dumps(wire))


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        '{"ok":false,"ok":false,"error":{"code":"INVALID_JSON"}}',
        '{"ok":NaN}',
        '{"ok":0,"error":{"code":"INVALID_JSON"}}',
    ],
)
def test_response_invalid_json_and_duplicate_keys(raw: str) -> None:
    """重複/非有限/数値真理値は閉境界で拒否する。"""
    with pytest.raises(PlayPrefixProtocolError):
        decode_play_prefix_response(raw)
