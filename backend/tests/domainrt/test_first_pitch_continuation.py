"""初球T1/T2の実host全値と、型/decoder故障を別に検査する。"""

from __future__ import annotations

import copy
import inspect
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from pitchlog.domainrt import first_pitch_continuation as caller
from pitchlog.domainrt.first_pitch import (
    FirstPitchFailure,
    FirstPitchProtocolError,
    FirstPitchSuccess,
    evaluate_first_pitch,
)
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    CombinedSuccess,
    T2NotEvaluatedResponse,
    decode_combined_response,
    evaluate_first_pitch_with_continuation,
)
from pitchlog.domainrt.host import DomainRuntimeError

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT = (
    _ROOT / "contracts/state-transition/t2_first_pitch_continuation_cases_v1.json"
)
_SCHEMA = json.loads(
    (
        _ROOT / "contracts/state-transition/t2_first_pitch_continuation_schema_v1.json"
    ).read_text()
)
_CASES = json.loads(_CONTRACT.read_text())["cases"]
_RESPONSE_SCHEMA = {
    "$schema": _SCHEMA["$schema"],
    "$defs": _SCHEMA["$defs"],
    "$ref": "#/$defs/CombinedResponse",
}


def _request(index: int = 0) -> CombinedRequest:
    """契約のwireから型を読む。入力や効果を計算しない。"""
    return CombinedRequest.model_validate_json(
        json.dumps(_CASES[index]["request"]), by_alias=True, by_name=False
    )


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["caseId"])
def test_real_fixed_host_matches_all_twelve_full_values_and_schema(
    case: dict[str, Any],
) -> None:
    """固定製品hostを通り、partial/非成功も全値で契約へ一致する。"""
    request = CombinedRequest.model_validate_json(
        json.dumps(case["request"]), by_alias=True, by_name=False
    )
    response = evaluate_first_pitch_with_continuation(request)
    actual = response.model_dump(mode="json", by_alias=True)
    Draft202012Validator(_RESPONSE_SCHEMA).validate(actual)
    assert actual == case["expected"]
    if response.ok:
        assert type(response) is CombinedSuccess
        assert response.value.t2.kind == "evaluated-no-end-condition"
    elif response.error.code == "T2_NOT_EVALUATED":
        assert type(response) is T2NotEvaluatedResponse
        assert response.value.t2.kind == "not-evaluated"
        assert response.ok is False
    else:
        assert type(response) is FirstPitchFailure
        assert not hasattr(response, "value")


@pytest.mark.parametrize("index", (0, 1, 2, 3, 4, 8))
def test_old_first_pitch_response_is_unchanged(index: int) -> None:
    """別の回帰呼出で旧deriveStateを比較し、製品callerで二回呼びしない。"""
    request = _request(index)
    old = evaluate_first_pitch(request.t1)
    new = evaluate_first_pitch_with_continuation(request)
    if type(old) is FirstPitchFailure:
        assert new.model_dump(mode="json", by_alias=True) == old.model_dump(
            mode="json", by_alias=True
        )
    else:
        assert isinstance(old, FirstPitchSuccess)
        assert isinstance(new, (CombinedSuccess, T2NotEvaluatedResponse))
        assert new.value.t1.model_dump(
            mode="json", by_alias=True
        ) == old.value.model_dump(mode="json", by_alias=True)


def _at(value: Any, path: tuple[str | int, ...]) -> Any:
    """故障注入用の局所参照。"""
    for key in path:
        value = value[key]
    return value


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("value", "t1", "after", "stateFields", "state.count.balls"), 1),
        (("value", "t1", "after", "stateFields", "state.count.balls"), "01"),
        (("value", "t1", "outEffect", "targets"), ["batter"]),
        (("value", "t1", "historyContext"), []),
        (
            ("value", "t1", "historyContext"),
            [*(_CASES[0]["expected"]["value"]["t1"]["historyContext"] * 2)],
        ),
        (("value", "t1", "statFlags", "投球数"), 1),
        (("value", "t2", "kind"), "not-evaluated"),
        (("value", "t2", "evaluation_point"), "post-turn"),
        (("value", "t2", "basis", "regulation", "observed_inning"), 1),
        (("value", "t2", "basis", "regulation", "regulation_innings"), "8"),
        (("value", "t2", "basis", "regulation", "regulation_innings"), "7"),
        (
            ("value", "t2", "basis", "extra_and_draw", "configured_extension_limit"),
            "10",
        ),
        (("ok",), 1),
    ],
)
def test_decoder_rejects_numeric_cardinality_and_unpublished_success_shape(
    path: tuple[str | int, ...],
    value: Any,
) -> None:
    """計算値を補完せずschemaの閉形状と表現だけを拒否する。"""
    response = copy.deepcopy(_CASES[0]["expected"])
    _at(response, path[:-1])[path[-1]] = value
    with pytest.raises(FirstPitchProtocolError):
        decode_combined_response(json.dumps(response))


@pytest.mark.parametrize(
    "mutation",
    [
        "partial-ok-true",
        "partial-no-value",
        "partial-unknown-reason",
        "failure-extra-value",
        "unknown-code",
        "success-extra",
        "success-missing-family",
        "field-name-alias",
        "alias-and-name",
        "unknown-t2-key",
    ],
)
def test_decoder_never_promotes_partial_or_unknown_to_success(mutation: str) -> None:
    """partial/未知code/余剰/欠落/非wire別名を成功へ補完しない。"""
    response = copy.deepcopy(
        _CASES[4]["expected"]
        if mutation.startswith("partial")
        else _CASES[0]["expected"]
    )
    if mutation == "partial-ok-true":
        response["ok"] = True
    elif mutation == "partial-no-value":
        del response["value"]
    elif mutation == "partial-unknown-reason":
        response["value"]["t2"]["reason"] = "context-unverified"
    elif mutation == "failure-extra-value":
        response["ok"] = False
        response["error"] = {"code": "INVALID_REQUEST"}
    elif mutation == "unknown-code":
        response = {"ok": False, "error": {"code": "UNKNOWN"}}
    elif mutation == "success-extra":
        response["binding"] = {}
    elif mutation == "success-missing-family":
        del response["value"]["t2"]["basis"]["cold"]
    elif mutation in {"field-name-alias", "alias-and-name"}:
        after = response["value"]["t1"]["after"]
        after["state_fields"] = copy.deepcopy(after["stateFields"])
        if mutation == "field-name-alias":
            del after["stateFields"]
    else:
        response["value"]["t2"]["lock"] = False
    with pytest.raises(FirstPitchProtocolError):
        decode_combined_response(json.dumps(response))


@pytest.mark.parametrize(
    "code",
    [
        "INVALID_JSON",
        "INVALID_REQUEST",
        "INVALID_DECIMAL_INTEGER",
        "UNSUPPORTED_T1_SCOPE",
    ],
)
def test_existing_four_failure_codes_are_reused(code: str) -> None:
    """新local codeを旧4enumへ混ぜず既非成功DTOを再利用する。"""
    response = decode_combined_response(
        json.dumps({"ok": False, "error": {"code": code}})
    )
    assert type(response) is FirstPitchFailure
    assert response.ok is False
    assert response.error.code == code


@pytest.mark.parametrize(
    "reason", ["input-not-in-closed-unit", "evaluation-unavailable"]
)
def test_both_unevaluated_reasons_remain_non_success(reason: str) -> None:
    """未供給/評価不能もT1partialのまま非成功に閉じる。"""
    response = copy.deepcopy(_CASES[4]["expected"])
    response["value"]["t2"]["reason"] = reason
    value = decode_combined_response(json.dumps(response))
    assert type(value) is T2NotEvaluatedResponse and value.ok is False
    Draft202012Validator(_RESPONSE_SCHEMA).validate(
        value.model_dump(mode="json", by_alias=True)
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"ok":false,"ok":true,"error":{"code":"INVALID_JSON"}}',
        '{"ok":false,"error":{"code":"INVALID_JSON","code":"INVALID_REQUEST"}}',
        '{"ok":false,"error":{"code":NaN}}',
        '{"ok":false,"error":{"code":Infinity}}',
        '{"ok":false,"error":{"code":-Infinity}}',
        "not json",
        0,
        None,
    ],
)
def test_duplicate_nonfinite_or_non_json_response_is_rejected(raw: Any) -> None:
    """既JSON duplicate/nonfinite拒否をそのまま通す。"""
    with pytest.raises(FirstPitchProtocolError):
        decode_combined_response(raw)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("rules", "regulationInnings"), 9),
        (("rules", "regulationInnings"), "0"),
        (("rules", "regulationInnings"), "00"),
        (("rules", "regulationInnings"), "100"),
        (("rules", "extensionLimit"), "9\n"),
        (("rules", "extensionLimit"), True),
        (("rules", "dh"), 1),
        (
            ("rules", "coldConditions"),
            [{"pointDifference": "1", "startInning": "1"}] * 17,
        ),
        (("rules", "coldConditions"), [{"pointDifference": "0", "startInning": "1"}]),
        (
            ("rules", "tiebreak"),
            {"startInning": "1", "runnerPlacement": "", "leadoffRule": "x"},
        ),
    ],
)
def test_saved_rule_wire_rejects_noncanonical_and_cardinality(
    path: tuple[str | int, ...],
    value: Any,
) -> None:
    """保存規則の形/十進/上限だけを検証し野球相関を計算しない。"""
    request = copy.deepcopy(_CASES[0]["request"])
    _at(request, path[:-1])[path[-1]] = value
    with pytest.raises(ValidationError):
        CombinedRequest.model_validate_json(
            json.dumps(request), by_alias=True, by_name=False
        )


def test_nested_models_and_tuple_are_immutable_and_dumps_detached() -> None:
    """既frozen基底とtupleを保持し、dumpの変更を内部へ逆流させない。"""
    request = _request(6)
    response = decode_combined_response(json.dumps(_CASES[0]["expected"]))
    assert type(response) is CombinedSuccess
    assert type(request.rules.cold_conditions) is tuple
    assert type(response.value.t1.history_context) is tuple
    for model, field, value in [
        (request.rules, "dh", False),
        (request.rules.cold_conditions[0], "start_inning", "3"),
        (response.value.t2.basis.regulation, "observed_inning", "2"),
        (response.value.t1.stat_flags, "pitch", False),
    ]:
        with pytest.raises(ValidationError):
            setattr(model, field, value)
    dump = response.model_dump(mode="json", by_alias=True)
    dump["value"]["t2"]["basis"]["regulation"]["observed_inning"] = "2"
    assert response.value.t2.basis.regulation.observed_inning == "1"


@pytest.mark.parametrize(
    "mutation",
    [
        "t1-decimal",
        "rules-decimal",
        "cold-list",
        "extra",
        "missing",
        "nested-alias",
        "rules-alias",
    ],
)
def test_forced_models_are_revalidated_before_opening_host(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """低水準で不変を破った型/extra/欠損も再検証してhost前に拒否する。"""

    def forbidden() -> Any:
        pytest.fail("壊れたmodelでhostを開かない")

    monkeypatch.setattr(caller, "open_domain_host", forbidden)
    request = _request()
    if mutation == "t1-decimal":
        object.__setattr__(request.t1.before.state_fields, "balls", 0)
    elif mutation == "rules-decimal":
        object.__setattr__(request.rules, "extension_limit", "09")
    elif mutation == "cold-list":
        object.__setattr__(request.rules, "cold_conditions", [])
    elif mutation == "extra":
        request = request.model_copy(update={"binding": {}})
    elif mutation == "nested-alias":
        object.__setattr__(
            request.t1.before, "stateFields", request.t1.before.state_fields
        )
    elif mutation == "rules-alias":
        object.__setattr__(
            request, "rules", request.rules.model_copy(update={"extensionLimit": "9"})
        )
    else:
        request = CombinedRequest.model_construct(t1=request.t1)
    with pytest.raises(ValidationError):
        evaluate_first_pitch_with_continuation(request)
    with pytest.raises(TypeError):
        evaluate_first_pitch_with_continuation(cast(CombinedRequest, {}))


def test_fixed_single_call_and_host_failures_are_not_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """試験だけのspyでliteral一回呼出を確認し製品へ注入口を作らない。"""
    calls = []
    response = _CASES[4]["expected"]

    class Host:
        def call(self, operation: str, raw: str) -> str:
            calls.append((operation, json.loads(raw)))
            return json.dumps(response)

    @contextmanager
    def fake_host() -> Any:
        yield Host()

    monkeypatch.setattr(caller, "open_domain_host", fake_host)
    actual = evaluate_first_pitch_with_continuation(_request(4))
    assert calls == [("deriveFirstPitchWithContinuation", _CASES[4]["request"])]
    assert type(actual) is T2NotEvaluatedResponse and actual.ok is False
    assert list(
        inspect.signature(evaluate_first_pitch_with_continuation).parameters
    ) == ["request"]

    @contextmanager
    def failed_host() -> Any:
        raise DomainRuntimeError("SYNTHETIC_UNAVAILABLE", "synthetic host unavailable")
        yield

    monkeypatch.setattr(caller, "open_domain_host", failed_host)
    with pytest.raises(DomainRuntimeError):
        evaluate_first_pitch_with_continuation(_request())


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-root",
        "missing-rule",
        "alias-name",
        "alias-both",
        "cold-extra",
        "tb-extra",
    ],
)
def test_saved_wire_closed_keys_and_aliases_are_not_normalized(mutation: str) -> None:
    """新保存規則のJSON keyはaliasだけに閉じ、余剰/不足を拒否する。"""
    value = copy.deepcopy(_CASES[0]["request"])
    if mutation == "unknown-root":
        value["binding"] = {}
    elif mutation == "missing-rule":
        del value["rules"]["dh"]
    elif mutation in {"alias-name", "alias-both"}:
        value["rules"]["regulation_innings"] = "9"
        if mutation == "alias-name":
            del value["rules"]["regulationInnings"]
    elif mutation == "cold-extra":
        value["rules"]["coldConditions"] = [
            {"pointDifference": "1", "startInning": "1", "extra": False}
        ]
    else:
        value["rules"]["tiebreak"] = {
            "startInning": "1",
            "runnerPlacement": "x",
            "leadoffRule": "x",
            "extra": False,
        }
    with pytest.raises(ValidationError):
        CombinedRequest.model_validate_json(
            json.dumps(value), by_alias=True, by_name=False
        )


@pytest.mark.parametrize("mutation", ["double-key", "t1-alias-both", "nonfinite"])
def test_request_wire_reader_reuses_json_fault_rejection(mutation: str) -> None:
    """raw要求も既JSON拒否と完全wire形比較を通り、aliasを捨てて受理しない。"""
    value = copy.deepcopy(_CASES[0]["request"])
    if mutation == "t1-alias-both":
        value["t1"]["before"]["state_fields"] = copy.deepcopy(
            value["t1"]["before"]["stateFields"]
        )
        raw = json.dumps(value)
    elif mutation == "nonfinite":
        raw = json.dumps(value).replace('"dh": true', '"dh": NaN')
    else:
        raw = json.dumps(value).replace('"dh": true', '"dh": false, "dh": true')
    with pytest.raises(ValidationError):
        CombinedRequest.model_validate_json(raw, by_alias=True, by_name=False)


@pytest.mark.parametrize("mutation", ["failure-zero", "failure-one", "flag-zero"])
def test_wire_roundtrip_does_not_replace_strict_bool_validation(mutation: str) -> None:
    """Pythonのbool/int同値比較に頼らず、先に既strict/ok exactで拒否する。"""
    if mutation == "flag-zero":
        raw = copy.deepcopy(_CASES[0]["expected"])
        raw["value"]["t1"]["statFlags"]["失策"] = 0
    else:
        raw = {
            "ok": 0 if mutation == "failure-zero" else 1,
            "error": {"code": "INVALID_REQUEST"},
        }
    with pytest.raises(FirstPitchProtocolError):
        decode_combined_response(json.dumps(raw))


@pytest.mark.parametrize("both", [False, True])
def test_standalone_saved_rule_json_reader_is_also_alias_only(both: bool) -> None:
    """保存規則単独のJSON読取でも別名だけ/両置を受理しない。"""
    from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire

    value = copy.deepcopy(_CASES[0]["request"]["rules"])
    value["regulation_innings"] = value["regulationInnings"]
    if not both:
        del value["regulationInnings"]
    with pytest.raises(ValidationError):
        SavedRuleWire.model_validate_json(
            json.dumps(value), by_alias=True, by_name=False
        )
