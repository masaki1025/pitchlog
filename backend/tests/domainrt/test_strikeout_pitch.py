"""三振24全応答/独立cursor交差と固定一回host・厳密不変DTOを検証する。"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from contextlib import nullcontext
from itertools import product
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

import pitchlog
from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.domainrt.strikeout_pitch import (
    StrikeoutPitchProtocolError,
    StrikeoutPitchRequest,
    decode_strikeout_pitch_response,
    evaluate_strikeout_pitch,
)

_ROOT = Path(__file__).resolve().parents[3]
_BASE = _ROOT / "contracts/state-transition"
_VECTORS = json.loads((_BASE / "strikeout_pitch_cases_v1.json").read_text())
_TERMINAL = json.loads((_BASE / "terminal_pitch_cases_v1.json").read_text())
_SCHEMA = json.loads((_BASE / "strikeout_pitch_schema_v1.json").read_text())
_RESPONSE_SCHEMA = Draft202012Validator(
    {
        "$ref": "#/$defs/StrikeoutPitchResponse",
        "$defs": _SCHEMA["$defs"],
    }
)
_ARTIFACT = _ROOT / "frontend/public/domain/pitchlog-domain.js"
_DECLARATION = _ROOT / "frontend/public/domain/pitchlog-domain.json"


def _wire(response: Any) -> dict[str, Any]:
    """省略差分をnull補完せず、実応答をJSON値へ写す。"""
    return response.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _crossing(
    case: dict[str, Any],
    half: str,
    order: str,
    runners: str,
    inactive: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """受理手例の効果を保持し、両cursorと攻守交代の規範だけを展開する。"""
    request, response = copy.deepcopy(case["request"]), copy.deepcopy(case["expected"])
    before, after = request["before"], response["value"]["after"]
    state = before["stateFields"]
    state.update(
        {"state.half": half, "state.battingOrder": order, "state.runners": runners}
    )
    outgoing, incoming = ("away", "home") if half == "top" else ("home", "away")
    before["battingOrderBySide"] = {outgoing: order, incoming: inactive}
    next_order = _VECTORS["crossProduct"]["nextBattingOrder"][order]
    after["battingOrderBySide"] = {outgoing: next_order, incoming: inactive}
    third = state["state.outs"] == "2"
    after["stateFields"].update(
        {
            "state.half": ("bottom" if half == "top" else "top") if third else half,
            "state.inning": "4" if third and half == "bottom" else "3",
            "state.runners": "empty" if third else runners,
            "state.battingOrder": inactive if third else next_order,
        }
    )
    response["value"]["runnerDefaultAdvance"] = {
        runner: {
            "modality": "hold" if runner in runners.split("-") else "not-applicable",
            "destination": None,
        }
        for runner in ("first", "second", "third")
    }
    difference: dict[str, Any] = {
        face: {
            key: {"before": old, "after": after[face][key]}
            for key, old in fields.items()
            if old != after[face][key]
        }
        for face, fields in before.items()
    }
    difference["statFlags"] = copy.deepcopy(response["value"]["statFlags"])
    response["value"]["historyContext"] = [
        {"kind": "confirmed-play", "difference": difference},
        *request["history"]["stack"],
    ]
    return request, response


def test_24_actual_product_host_and_typed_caller_full_responses(
    record_property: Callable[[str, object], None],
) -> None:
    """editable旧sourceを試験せず、同artifact二経路の全応答を規範と比較する。"""
    import pitchlog.domainrt.strikeout_pitch as module

    assert Path(pitchlog.__file__).resolve().is_relative_to(_ROOT / "backend/src")
    assert (
        Path(module.__file__).resolve()
        == _ROOT / "backend/src/pitchlog/domainrt/strikeout_pitch.py"
    )
    wrapped = json.loads((_BASE / "strikeout_pitch_d11_vectors_v1.json").read_text())
    assert (
        wrapped["sourcePath"]
        == "contracts/state-transition/strikeout_pitch_cases_v1.json"
    )
    assert (
        wrapped["sourceSha256"]
        == hashlib.sha256(
            (_BASE / "strikeout_pitch_cases_v1.json").read_bytes()
        ).hexdigest()
    )
    digest = hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest()
    assert wrapped["executionArtifactSha256"] == digest
    assert wrapped["calculation"] == "regular-caught-strikeout-v1"
    assert len(wrapped["cases"]) == len(_VECTORS["cases"]) == 24
    schema = json.loads((_ROOT / "backend/domain/manifest.schema.json").read_text())
    expected_schema = Draft202012Validator(
        {"$ref": "#/$defs/ExpectedValue", "$defs": schema["$defs"]}
    )
    measured = None
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        assert host.artifact_sha256 == digest
        for case, envelope in zip(_VECTORS["cases"], wrapped["cases"], strict=True):
            assert set(envelope) == {"caseId", "request", "expected"}
            assert envelope["caseId"] == case["caseId"]
            assert envelope["request"] == case["request"]
            expected_schema.validate(envelope["expected"])
            assert envelope["expected"] == {
                "comparison": "exact",
                "expected": case["expected"],
                "provenance": "NFR-018 (b)② 差分の検出可能性",
            }
            raw = host.call("deriveStrikeoutPitch", json.dumps(envelope["request"]))
            _RESPONSE_SCHEMA.validate(json.loads(raw))
            assert json.loads(raw) == case["expected"]
            request = StrikeoutPitchRequest.model_validate_json(
                json.dumps(case["request"])
            )
            with patch.object(
                module, "open_domain_host", return_value=nullcontext(host)
            ):
                entrypoint = _wire(evaluate_strikeout_pitch(request))
                assert entrypoint == case["expected"]
            measured = {
                "calculation": "regular-caught-strikeout-v1",
                "propertyId": "strikeoutHostParity",
                "propertyKind": "equivalence",
                "generatedCases": 24,
                "status": "passed",
                "trace": {
                    "vector": "strikeoutPitchVectors",
                    "case": case["caseId"],
                    "entrypointId": "strikeoutPitchServer",
                    "directTargetId": "strikeoutPitchDirect",
                    "expected": case["expected"],
                    "entrypointOutput": entrypoint,
                    "directTargetOutput": json.loads(raw),
                    "artifactHashes": {"single": "sha256:" + digest},
                    "issuedSqlOrAst": None,
                    "stageIO": [],
                },
            }
    assert measured is not None
    for name, value in measured.items():
        record_property(name, json.dumps(value) if isinstance(value, dict) else value)
    # 24正例と代表拒否は製品factoryを改変せず毎回open/closeする。
    for case in _VECTORS["cases"]:
        request = StrikeoutPitchRequest.model_validate_json(json.dumps(case["request"]))
        assert _wire(evaluate_strikeout_pitch(request)) == case["expected"]
    for path, value in (
        (["resultId"], "batting-result.k3"),
        (["before", "stateFields", "state.outs"], "3"),
        (["before", "battingOrderBySide", "away"], "0"),
    ):
        raw = copy.deepcopy(_VECTORS["cases"][0]["request"])
        target = raw
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        request = StrikeoutPitchRequest.model_validate_json(json.dumps(raw))
        assert _wire(evaluate_strikeout_pitch(request)) == {
            "ok": False,
            "error": {"code": "UNSUPPORTED_T1_SCOPE"},
        }


def test_all_31104_through_actual_typed_single_artifact(
    record_property: Callable[[str, object], None],
) -> None:
    """実hostを再利用するが、各typed評価は固定入口を一回だけ呼ぶ。"""
    count = equal_scalar = 0
    axes = _VECTORS["crossProduct"]
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        with patch(
            "pitchlog.domainrt.strikeout_pitch.open_domain_host",
            side_effect=lambda: nullcontext(host),
        ):
            for case, half, order, runners, inactive in product(
                _VECTORS["cases"],
                axes["halves"],
                axes["battingOrders"],
                axes["runners"],
                axes["inactiveBattingOrders"],
            ):
                request, expected = _crossing(case, half, order, runners, inactive)
                parsed = StrikeoutPitchRequest.model_validate_json(json.dumps(request))
                response = evaluate_strikeout_pitch(parsed)
                actual = _wire(response)
                assert actual == expected
                if (
                    request["before"]["stateFields"]["state.outs"] == "2"
                    and order == inactive
                ):
                    equal_scalar += 1
                    difference = actual["value"]["historyContext"][0]["difference"]
                    assert "state.battingOrder" not in difference["stateFields"]
                    assert difference["battingOrderBySide"]
                count += 1
    assert count == 31104 and equal_scalar == 1152
    record_property("strikeout_actual_typed_cases", count)
    record_property("strikeout_equal_scalar_cursor_changes", equal_scalar)


def test_90_digit_boards_and_old_new_history_tail_are_preserved() -> None:
    """大整数と旧新tailを実hostに通し、省略も全値も保持する。"""
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        for case in _VECTORS["cases"]:
            request, expected = (
                copy.deepcopy(case["request"]),
                copy.deepcopy(case["expected"]),
            )
            before, after = request["before"], expected["value"]["after"]
            huge = "9" * 90
            state, next_state = before["stateFields"], after["stateFields"]
            state["state.inning"] = huge
            next_state["state.inning"] = str(
                int(huge)
                + int(state["state.outs"] == "2" and state["state.half"] == "bottom")
            )
            state["state.tiebreakActive"] = next_state["state.tiebreakActive"] = True
            state["state.score"] = {"home": huge, "away": "9007199254740993"}
            next_state["state.score"] = copy.deepcopy(state["state.score"])
            for board in (before["scoreboard"], after["scoreboard"]):
                board.update({key: huge for key in ("hits", "errors", "walks")})
                board["inningScores"] = copy.deepcopy(state["state.score"])
            before["scoreboard"]["strikeouts"] = huge
            after["scoreboard"]["strikeouts"] = str(int(huge) + 1)
            difference = expected["value"]["historyContext"][0]["difference"]
            if state["state.outs"] == "2" and state["state.half"] == "bottom":
                difference["stateFields"]["state.inning"] = {
                    "before": huge,
                    "after": next_state["state.inning"],
                }
            difference["scoreboard"]["strikeouts"] = {
                "before": huge,
                "after": after["scoreboard"]["strikeouts"],
            }
            tail = [
                _TERMINAL["cases"][0]["expected"]["value"]["historyContext"][0],
                case["expected"]["value"]["historyContext"][0],
            ]
            request["history"]["stack"] = copy.deepcopy(tail)
            expected["value"]["historyContext"].extend(copy.deepcopy(tail))
            parsed = StrikeoutPitchRequest.model_validate_json(json.dumps(request))
            with patch(
                "pitchlog.domainrt.strikeout_pitch.open_domain_host",
                return_value=nullcontext(host),
            ):
                assert _wire(evaluate_strikeout_pitch(parsed)) == expected


def test_host_call_is_exactly_once_and_bound_to_fixed_operation() -> None:
    """固定操作を一回だけ呼び、型違いをhost前に拒否する。"""
    case = _VECTORS["cases"][0]
    request = StrikeoutPitchRequest.model_validate_json(json.dumps(case["request"]))
    host = MagicMock()
    host.call.return_value = json.dumps(case["expected"])
    with patch("pitchlog.domainrt.strikeout_pitch.open_domain_host") as factory:
        factory.return_value.__enter__.return_value = host
        assert _wire(evaluate_strikeout_pitch(request)) == case["expected"]
        host.call.assert_called_once_with(
            "deriveStrikeoutPitch",
            request.model_dump_json(by_alias=True, exclude_unset=True),
        )
        factory.assert_called_once_with()
    with pytest.raises(TypeError):
        evaluate_strikeout_pitch(cast(StrikeoutPitchRequest, object()))


def test_nested_cursor_models_are_frozen_and_not_aliased_or_defaulted() -> None:
    """実不変DTOを変更できず、欠落/別名/型を補完しない。"""
    case = _VECTORS["cases"][0]
    request = StrikeoutPitchRequest.model_validate_json(json.dumps(case["request"]))
    response = decode_strikeout_pitch_response(json.dumps(case["expected"]))
    assert response.ok
    with pytest.raises(ValidationError):
        setattr(request.before.batting_order_by_side, "home", "2")
    with pytest.raises(ValidationError):
        setattr(response.value.after.batting_order_by_side, "home", "2")
    for replacement in (None, {}, {"away": "1"}, {"away": 1, "home": "5"}):
        changed = copy.deepcopy(case["request"])
        changed["before"]["battingOrderBySide"] = replacement
        with pytest.raises(ValidationError):
            StrikeoutPitchRequest.model_validate_json(json.dumps(changed))
    changed = copy.deepcopy(case["request"])
    changed["before"]["batting_order_by_side"] = changed["before"].pop(
        "battingOrderBySide"
    )
    with pytest.raises(ValidationError):
        StrikeoutPitchRequest.model_validate_json(
            json.dumps(changed), by_alias=True, by_name=False
        )


def test_every_flag_number_extra_alias_and_cursor_shape_is_protocol_error() -> None:
    """各flag変異/型偽装と閉構造の破損をprotocolerrorにする。"""
    original = _VECTORS["cases"][0]["expected"]
    for flag, value in original["value"]["statFlags"].items():
        for replacement in (not value, int(value)):
            changed = copy.deepcopy(original)
            changed["value"]["statFlags"][flag] = replacement
            with pytest.raises(StrikeoutPitchProtocolError):
                decode_strikeout_pitch_response(json.dumps(changed))
    for kind in (
        "extra",
        "alias",
        "cursor-null",
        "cursor-extra",
        "cursor-number",
        "pair-null",
        "head-cursor-missing",
        "head-cursor-empty",
    ):
        changed = copy.deepcopy(original)
        if kind == "extra":
            changed["value"]["free"] = True
        elif kind == "alias":
            changed["value"]["stat_flags"] = changed["value"].pop("statFlags")
        elif kind == "cursor-null":
            changed["value"]["after"]["battingOrderBySide"] = None
        elif kind == "cursor-extra":
            changed["value"]["after"]["battingOrderBySide"]["other"] = "1"
        elif kind == "cursor-number":
            changed["value"]["after"]["battingOrderBySide"]["away"] = 2
        elif kind == "head-cursor-missing":
            del changed["value"]["historyContext"][0]["difference"][
                "battingOrderBySide"
            ]
        elif kind == "head-cursor-empty":
            changed["value"]["historyContext"][0]["difference"][
                "battingOrderBySide"
            ] = {}
        else:
            changed["value"]["historyContext"][0]["difference"][
                "battingOrderBySide"
            ] = None
        with pytest.raises(StrikeoutPitchProtocolError):
            decode_strikeout_pitch_response(json.dumps(changed))
    for raw in ('{"ok":false,"ok":true}', '{"ok":NaN}', '{"ok":true'):
        with pytest.raises(StrikeoutPitchProtocolError):
            decode_strikeout_pitch_response(raw)
