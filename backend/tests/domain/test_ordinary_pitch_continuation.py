"""通常37の閉型境界と単一artifactの完全応答を照合する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pitchlog.domainrt.ordinary_pitch_continuation import (
    OrdinaryContinuationProtocolError,
    OrdinaryContinuationRequest,
    decode_ordinary_continuation_response,
    evaluate_ordinary_pitch_with_continuation,
)

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT = json.loads(
    (
        _ROOT / "contracts/state-transition/ordinary37_continuation_candidate_v1.json"
    ).read_text()
)
_CASES = _CONTRACT["cases"]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["caseId"])
def test_candidate_request_wire_is_lossless(case: dict) -> None:
    """意味拒否予定の要求も構造で補修せずartifactへ渡せる。"""
    model = OrdinaryContinuationRequest.model_validate_json(json.dumps(case["request"]))
    assert model.model_dump(mode="json", by_alias=True) == case["request"]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["caseId"])
def test_complete_candidate_response_is_lossless(case: dict) -> None:
    """候補全20件を部分一致にせず読む。実hostの成功証拠とは区別する。"""
    expected = case["expected"]["response"]
    actual = decode_ordinary_continuation_response(json.dumps(expected))
    assert actual.model_dump(mode="json", by_alias=True, exclude_unset=True) == expected


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["caseId"])
def test_actual_artifact_matches_twenty_complete_responses(case: dict) -> None:
    """固定製品hostに新operationを実行させ、全封筒を照合する。"""
    request = OrdinaryContinuationRequest.model_validate_json(
        json.dumps(case["request"])
    )
    actual = evaluate_ordinary_pitch_with_continuation(request)
    assert (
        actual.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == (case["expected"]["response"])
    )


@pytest.mark.parametrize("value", ["-1", "01", "+1", "1.0", 1, True])
def test_prefix_watermark_requires_canonical_string(value: object) -> None:
    """水位の表現を補修しない。"""
    request = copy.deepcopy(_CASES[0]["request"])
    request["prefixRef"]["length"] = value
    with pytest.raises(ValidationError):
        OrdinaryContinuationRequest.model_validate_json(json.dumps(request))


@pytest.mark.parametrize(
    "value",
    [
        "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
        "1",
        "0" * 32,
        "11111111-1111-4111-8111-111111111111\n",
    ],
)
def test_prefix_uuid_does_not_normalize(value: str) -> None:
    """UUIDの省略や大小文字を補修しない。"""
    request = copy.deepcopy(_CASES[0]["request"])
    request["prefixRef"]["tenantId"] = value
    with pytest.raises(ValidationError):
        OrdinaryContinuationRequest.model_validate_json(json.dumps(request))


@pytest.mark.parametrize(
    "raw",
    [
        '{"ok":false,"ok":true,"error":{"code":"INVALID_REQUEST"}}',
        '{"ok":false,"error":{"code":"INVALID_REQUEST"},"extra":0}',
        '{"ok":false,"error":{"code":"NEW_CODE"}}',
        '{"ok":false,"error":{"code":"INVALID_REQUEST"},"value":NaN}',
        '{"ok":0,"error":{"code":"INVALID_REQUEST"}}',
    ],
)
def test_malformed_guest_wire_is_not_success(raw: str) -> None:
    """壊れたhost封筒を成功へ補完しない。"""
    with pytest.raises(OrdinaryContinuationProtocolError):
        decode_ordinary_continuation_response(raw)


@pytest.mark.parametrize("field", ["priorOpen", "halfCompleted", "scoreUnchanged"])
def test_t2_literal_booleans_reject_numeric_aliases(field: str) -> None:
    """T2の真理値に数値を受け入れない。"""
    response = copy.deepcopy(_CASES[0]["expected"]["response"])
    response["value"]["t2"]["basis"][field] = int(
        response["value"]["t2"]["basis"][field]
    )
    with pytest.raises(OrdinaryContinuationProtocolError):
        decode_ordinary_continuation_response(json.dumps(response))


def test_literal_stat_flag_rejects_numeric_alias() -> None:
    """フラグの数値を真理値へ補修しない。"""
    response = copy.deepcopy(_CASES[0]["expected"]["response"])
    response["value"]["t1"]["statFlags"]["投球数"] = 1
    with pytest.raises(OrdinaryContinuationProtocolError):
        decode_ordinary_continuation_response(json.dumps(response))


def test_history_does_not_accept_explicit_null_or_full_stack() -> None:
    """空差分と明示nullを区別し全履歴の混入を拒否する。"""
    for field, value in (("state.count.balls", None), ("historyContext", [])):
        response = copy.deepcopy(_CASES[0]["expected"]["response"])
        if field == "historyContext":
            response["value"]["t1"][field] = value
        else:
            response["value"]["newHistoryEntry"]["difference"]["stateFields"][field] = (
                value
            )
        with pytest.raises(OrdinaryContinuationProtocolError):
            decode_ordinary_continuation_response(json.dumps(response))


def test_forced_nested_alias_is_rejected_before_host() -> None:
    """強制追加されたmodel aliasをhost起動前に拒否する。"""
    request = OrdinaryContinuationRequest.model_validate_json(
        json.dumps(_CASES[0]["request"])
    )
    object.__setattr__(request.prefix_ref, "tenantId", "forged")
    with pytest.raises(ValidationError):
        evaluate_ordinary_pitch_with_continuation(request)


def test_untyped_request_cannot_open_host() -> None:
    """dictを型付き数学要求として扱わない。"""
    with pytest.raises(TypeError):
        evaluate_ordinary_pitch_with_continuation(_CASES[0]["request"])
