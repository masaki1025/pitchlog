"""P3既wire全値とnested閉境界を実routeの応答型で検査する。"""

import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from pitchlog.api.routers import sync
from pitchlog.api.schemas.past_correction_response import (
    AcceptedChangeResponse,
    RejectedChangeResponse,
    validate_change_result_response,
)
from pitchlog.sync.model import AcceptedChangeResult, RejectedChangeResult
from pitchlog.sync.past_correction_http_service import p3_response_body

_ROOT = Path(__file__).resolve().parents[2]
_CASE = next(
    case
    for case in json.loads(
        (
            _ROOT / "contracts/state-transition/lineup_play_prefix_cases_v1.json"
        ).read_text()
    )["cases"]
    if case["caseId"] == "V3-STARTED-CHAIN-01"
)
_PREFIX = _CASE["expected"]["value"]["nextPrefixRef"]
_D5 = str(UUID(int=901))
_EVENT = str(UUID(int=902))
_PLAY = str(UUID(int=903))
_STATS = str(UUID(int=904))


def _bodies():
    """規範fixtureの既型だけを借り、算出・保存の証拠にはしない。"""
    reference = {"game": _PREFIX["gameId"], "d4": _PREFIX["generation"], "d1": 1}
    target = {
        "target_reference": reference,
        "expected_version": 1,
        "expected_prefix_ref": _PREFIX,
        "target_event_id": _EVENT,
        "target_play_id": _PLAY,
        "original_result_id": "batting-result.ball",
    }
    confirmation = {
        "target_reference": reference,
        "confirmed_version": 2,
        "d5": _D5,
        "source_event_id": _EVENT,
        "target_play_id": _PLAY,
        "stats_version_id": _STATS,
        "current_prefix_ref": _PREFIX,
        "current_after": _CASE["expected"]["value"]["t1"]["after"],
    }
    accepted = {
        "boundary": "変更受理",
        "target_reference": {
            "試合": reference["game"],
            "対象の D4": reference["d4"],
            "対象の D1": 1,
        },
        "expected_version": 1,
        "d5": _D5,
        "confirmed_content": {
            "formatVersion": "p3-lineup-pitch-change-v1",
            "expectedPrefixRef": _PREFIX,
            "targetEventId": _EVENT,
            "targetPlayId": _PLAY,
            "originalResultId": "batting-result.ball",
            "replacementResultId": "batting-result.called-pitch",
            "replacementObservations": {
                "pitchTypeKey": "type-fastball",
                "course": {"unit": "1/263", "x": "132", "y": "131"},
                "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                "stance": None,
                "battingSide": None,
            },
        },
        "accepted_at": "2026-11-07T00:00:00+00:00",
    }
    rejected = {"boundary": "B8", "d5": _D5, "reason": None}
    return deepcopy((target, confirmation, accepted, rejected))


def _route(index):
    operation = (
        "read_sync_change_target",
        "read_sync_change_confirmation",
        "sync_change",
        "sync_change",
    )[index]
    return next(
        r
        for r in sync.router.routes
        if isinstance(r, APIRoute) and r.operation_id == operation
    )


@pytest.mark.parametrize("index", range(4))
def test_registered_response_preserves_every_existing_wire_value(index):
    """実routeの検証とserializeで別名・明示null・nested全値を一致させる。"""
    body = _bodies()[index]
    route = _route(index)
    assert route.response_model is not None and route.response_model_exclude_unset
    assert route.response_field is not None
    actual, errors = route.response_field.validate(body, {}, loc=("response",))
    assert not errors
    assert (
        route.response_field.serialize(
            actual, mode="json", by_alias=True, exclude_unset=True
        )
        == body
    )


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("fault", ["extra", "missing", "type", "nested"])
def test_response_shape_cannot_be_extended_or_coerced(index, fault):
    """未知member/欠落/型補正と日本語参照の別名変更を拒否する。"""
    body = _bodies()[index]
    if fault == "extra":
        body["extra"] = None
    elif fault == "missing":
        body.pop(next(iter(body)))
    elif fault == "type":
        if index == 0:
            body["expected_version"] = True
        elif index == 1:
            body["confirmed_version"] = "2"
        else:
            body["d5"] = 1
    elif index == 3:
        body["reason"] = {"unknown": "not-text"}
    else:
        body["target_reference"]["extra"] = None
    field = _route(index).response_field
    assert field is not None
    _, errors = field.validate(body, {}, loc=("response",))
    assert errors


@pytest.mark.parametrize("boundary", ["B8", "B9", "B10", "B11", "B12", "B13", "B14"])
def test_existing_rejection_union_keeps_explicit_null_reason(boundary):
    """既拒否だけを許可し、受理形へ合成しない。"""
    result = RejectedChangeResult(boundary, _D5, None)
    body = p3_response_body(result)
    actual = validate_change_result_response(body)
    assert type(actual) is RejectedChangeResponse
    assert actual.model_dump(mode="json", by_alias=True, exclude_unset=True) == body


def test_accepted_i6_is_identical_after_frozen_json_conversion():
    """既モデルの凍結JSON/I6を全項目付きのまま返す。"""
    body = _bodies()[2]
    result = AcceptedChangeResult(
        body["target_reference"], 1, _D5, body["confirmed_content"], body["accepted_at"]
    )
    assert p3_response_body(result) == body
    actual = validate_change_result_response(p3_response_body(result))
    assert type(actual) is AcceptedChangeResponse
    assert actual.model_dump(mode="json", by_alias=True, exclude_unset=True) == body


@pytest.mark.parametrize("boundary", ["受理", "B15", None, True])
def test_unknown_result_boundary_is_not_success(boundary):
    """通常ACK・未知boundary・型不正を既受理/拒否へ補修しない。"""
    body = _bodies()[3]
    body["boundary"] = boundary
    with pytest.raises(ValidationError):
        validate_change_result_response(body)


@pytest.mark.parametrize(
    "result_id",
    [
        "batting-result.single",
        "batting-result.double",
        "batting-result.triple",
        "batting-result.home-run",
    ],
)
def test_target_read_keeps_existing_batted_hit_result_identifiers(result_id):
    """読取対象の値域を変更payloadの3結果へ誤って狭めない。"""
    body = _bodies()[0]
    body["original_result_id"] = result_id
    field = _route(0).response_field
    assert field is not None
    actual, errors = field.validate(body, {}, loc=("response",))
    assert not errors
    assert (
        field.serialize(actual, mode="json", by_alias=True, exclude_unset=True) == body
    )


@pytest.mark.parametrize("value", [None, True, 1, ["batting-result.single"]])
def test_target_result_remains_strict_text_without_coercion(value):
    """元の文字列を補正せず、別型だけを拒否する。"""
    body = _bodies()[0]
    body["original_result_id"] = value
    field = _route(0).response_field
    assert field is not None
    _, errors = field.validate(body, {}, loc=("response",))
    assert errors


def test_readable_batted_hit_is_not_promoted_to_supported_correction():
    """対象の読取成功と変更POSTの既対応範囲を混同しない。"""
    body = _bodies()[2]
    body["confirmed_content"]["originalResultId"] = "batting-result.single"
    with pytest.raises(ValidationError):
        validate_change_result_response(body)
