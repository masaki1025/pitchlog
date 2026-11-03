"""実host接続と計算を行わない閉DTO decoderを区別して検査する。"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from pitchlog.domainrt import first_pitch
from pitchlog.domainrt.first_pitch import (
    FirstPitchFailure,
    FirstPitchProtocolError,
    FirstPitchRequest,
    FirstPitchSuccess,
    decode_first_pitch_response,
    evaluate_first_pitch,
)
from pitchlog.domainrt.host import DomainRuntimeError

_ROOT = Path(__file__).resolve().parents[3]


def _decimalize(value: Any) -> Any:
    """テストの契約整数表現だけを写し、効果を計算しない。"""
    if type(value) is int:
        return str(value)
    if isinstance(value, dict):
        return {key: _decimalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimalize(item) for item in value]
    return value


def _case() -> dict[str, Any]:
    """既正式caseをテストだけから参照する。"""
    contract = json.loads(
        (
            _ROOT / "contracts/state-transition/state_transition_contract_v1.json"
        ).read_text()
    )
    migrations = json.loads(
        (
            _ROOT / "contracts/state-transition/ordinary_pitch_vectors_v1.json"
        ).read_text()
    )["caseIdMigrations"]["caseIds"]
    current_id = migrations["ST-MATRIX-0529a0eb116d64a9"]
    if current_id != "ST-MATRIX-99b1523fb41399e3":
        raise ValueError("正式初球caseのID移行が不一致")
    return next(row for row in contract["cases"] if row["caseId"] == current_id)


def _request() -> dict[str, Any]:
    """実beforeと入力座標を閉要求へ写す。"""
    case = _case()
    return {
        "eventKind": case["inputCoordinate"]["eventKind"],
        "resultId": case["inputCoordinate"]["resultId"],
        "pitchEventKind": case["inputCoordinate"]["event.perPitch.pitchEventKind"],
        "before": _decimalize(case["historyInput"]["before"]),
    }


def _success() -> dict[str, Any]:
    """decoder単体試験用の既正式応答。製品hostへ差し込まない。"""
    case = _case()
    return {
        "ok": True,
        "value": _decimalize(
            {**case["expected"], "after": case["historyInput"]["after"]}
        ),
    }


def _at(value: Any, path: tuple[str | int, ...]) -> Any:
    """故障データを変更するための局所参照を返す。"""
    for key in path:
        value = value[key]
    return value


def test_fixed_product_host_matches_full_formal_response() -> None:
    """任意pathを渡さず実Nodeで全値を評価する。"""
    source = _request()
    request = FirstPitchRequest.model_validate(source)
    result = evaluate_first_pitch(request)
    assert type(result) is FirstPitchSuccess
    assert result.model_dump(mode="json", by_alias=True) == _success()
    assert len(result.value.stat_flags.model_fields_set) == 23
    assert type(result.value.history_context) is tuple
    assert result.value.out_effect.targets == ()
    assert source == _request()
    assert list(inspect.signature(evaluate_first_pitch).parameters) == ["request"]


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("root", "resultId", "batting-result.home-run"),
        ("root", "eventKind", "other"),
        ("stateFields", "state.count.balls", "1"),
        ("stateFields", "state.half", "bottom"),
        ("scoreboard", "hits", "1"),
    ],
)
def test_real_artifact_unsupported_stays_non_success(
    section: str,
    field: str,
    value: str,
) -> None:
    """型が正しい別scopeを計算せず、実artifactの非成功を受ける。"""
    raw = _request()
    target = raw if section == "root" else raw["before"][section]
    target[field] = value
    result = evaluate_first_pitch(FirstPitchRequest.model_validate(raw))
    assert type(result) is FirstPitchFailure
    assert result.error.code == "UNSUPPORTED_T1_SCOPE"


@pytest.mark.parametrize("raw", [0, False, "00", "-0", "0\n", "0\r\n", "0 ", "1e0"])
def test_request_decimal_is_strict_before_host(raw: object) -> None:
    """bool/int/非canonical表現を暗黙変換しない。"""
    value = _request()
    value["before"]["stateFields"]["state.count.balls"] = raw
    with pytest.raises(ValidationError):
        FirstPitchRequest.model_validate(value)


@pytest.mark.parametrize("raw", [0, "false", None, []])
def test_request_bool_is_strict(raw: object) -> None:
    """bool欄へ数値/文字列を受け入れない。"""
    value = _request()
    value["before"]["stateFields"]["state.gameEnded"] = raw
    with pytest.raises(ValidationError):
        FirstPitchRequest.model_validate(value)


def test_frozen_nested_data_and_detached_dumps() -> None:
    """入れ子model/tupleを変更できず、dump変更も逆流しない。"""
    request = FirstPitchRequest.model_validate(_request())
    result = decode_first_pitch_response(json.dumps(_success()))
    assert type(result) is FirstPitchSuccess
    for target, field, value in [
        (request.before.state_fields, "balls", "9"),
        (request.before.scoreboard.inning_scores, "home", "9"),
        (result.value.stat_flags, "pitch", False),
        (result.value.history_context[0].difference.state_fields.balls, "after", "9"),
        (result.value, "history_context", ()),
    ]:
        with pytest.raises(ValidationError):
            setattr(target, field, value)
    dump = result.model_dump(mode="json", by_alias=True)
    dump["value"]["after"]["stateFields"]["state.count.balls"] = "9"
    assert result.value.after.state_fields.balls == "1"


def test_forced_request_mutation_is_revalidated_before_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """低水準でfrozenを破った型不正も呼出前に拒否する。"""

    def forbidden_host() -> None:
        pytest.fail("不正入力でhostを開いてはならない")

    monkeypatch.setattr(first_pitch, "open_domain_host", forbidden_host)
    request = FirstPitchRequest.model_validate(_request())
    object.__setattr__(request.before.state_fields, "balls", 0)
    with pytest.raises(ValidationError):
        evaluate_first_pitch(request)
    with pytest.raises(TypeError):
        evaluate_first_pitch(cast(FirstPitchRequest, _request()))
    extra = FirstPitchRequest.model_validate(_request()).model_copy(
        update={"unexpected": "x"}
    )
    with pytest.raises(ValidationError):
        evaluate_first_pitch(extra)

    class DerivedRequest(FirstPitchRequest):
        """実型境界を確認する試験用派生型。"""

    with pytest.raises(TypeError):
        evaluate_first_pitch(DerivedRequest.model_validate(_request()))


def test_existing_host_failure_propagates_without_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """故障unitを実host成功と区別し、既障害を握り潰さない。"""

    def broken_host() -> None:
        raise DomainRuntimeError("HASH_MISMATCH", "試験故障")

    monkeypatch.setattr(first_pitch, "open_domain_host", broken_host)
    with pytest.raises(DomainRuntimeError, match="試験故障"):
        evaluate_first_pitch(FirstPitchRequest.model_validate(_request()))


@pytest.mark.parametrize(
    "code",
    [
        "INVALID_JSON",
        "INVALID_REQUEST",
        "INVALID_DECIMAL_INTEGER",
        "UNSUPPORTED_T1_SCOPE",
    ],
)
def test_decoder_accepts_only_existing_error_envelope(code: str) -> None:
    """既codeを型付きで返し、新しいACK等へ変換しない。"""
    result = decode_first_pitch_response(
        json.dumps({"ok": False, "error": {"code": code}})
    )
    assert type(result) is FirstPitchFailure
    assert result.error.code == code


@pytest.mark.parametrize(
    "wire",
    [
        "{",
        "null",
        "[]",
        "NaN",
        '{"ok":false,"error":{"code":"INVALID_STATE"}}',
        '{"ok":0,"error":{"code":"INVALID_JSON"}}',
        '{"ok":false,"error":{"code":"INVALID_JSON","detail":"private"}}',
        '{"ok":false,"ok":true,"error":{"code":"INVALID_JSON"}}',
        '{"ok":false,"error":{"code":"INVALID_JSON"},"value":{}}',
    ],
)
def test_decoder_rejects_broken_or_unknown_envelope(wire: str) -> None:
    """未知code/余剰/重複/不正JSONを固定例外へ閉じる。"""
    with pytest.raises(FirstPitchProtocolError) as error:
        decode_first_pitch_response(wire)
    assert str(error.value) == "数学核の応答が固定ABIに適合しません"
    assert error.value.__suppress_context__ is True


_DECIMAL_PATHS = [
    ("countEffect", "balls", "value"),
    ("outEffect", "count"),
    *(
        ("after", "stateFields", name)
        for name in (
            "state.count.strikes",
            "state.count.balls",
            "state.outs",
            "state.battingOrder",
            "state.inning",
        )
    ),
    ("after", "stateFields", "state.score", "home"),
    ("after", "stateFields", "state.score", "away"),
    ("after", "scoreboard", "inningScores", "home"),
    ("after", "scoreboard", "inningScores", "away"),
    *(
        ("after", "scoreboard", name)
        for name in ("hits", "errors", "strikeouts", "walks")
    ),
    ("historyContext", 0, "difference", "stateFields", "state.count.balls", "before"),
    ("historyContext", 0, "difference", "stateFields", "state.count.balls", "after"),
]


@pytest.mark.parametrize("path", _DECIMAL_PATHS)
@pytest.mark.parametrize("bad", [0, True, "0\n", "0\r\n", "00", "-0", "0 ", "1e0"])
def test_decoder_checks_every_decimal(path: tuple[str | int, ...], bad: object) -> None:
    """全17整数fieldへ同じ非canonical/型拒否を適用する。"""
    wire = _success()
    _at(wire["value"], path[:-1])[path[-1]] = bad
    with pytest.raises(FirstPitchProtocolError):
        decode_first_pitch_response(json.dumps(wire))


def test_decoder_missing_extra_boolean_and_tuple_failures() -> None:
    """全閉objectの欠落/余分、flagの型、配列長を拒否する。"""
    original = _success()
    paths: list[tuple[str | int, ...]] = []

    def objects(value: Any, path: tuple[str | int, ...] = ()) -> None:
        if isinstance(value, dict):
            paths.append(path)
            for key, item in value.items():
                objects(item, (*path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                objects(item, (*path, index))

    objects(original)
    for path in paths:
        raw = copy.deepcopy(original)
        _at(raw, path)["unknown"] = True
        with pytest.raises(FirstPitchProtocolError):
            decode_first_pitch_response(json.dumps(raw))
        for key in _at(original, path):
            raw = copy.deepcopy(original)
            del _at(raw, path)[key]
            with pytest.raises(FirstPitchProtocolError):
                decode_first_pitch_response(json.dumps(raw))
    for bad in [0, "false", None]:
        raw = copy.deepcopy(original)
        raw["value"]["statFlags"]["投球数"] = bad
        with pytest.raises(FirstPitchProtocolError):
            decode_first_pitch_response(json.dumps(raw))
    for field, values in [
        ("historyContext", [[], original["value"]["historyContext"] * 2]),
        ("outEffect", [{"count": "0", "targets": ["batter"]}]),
    ]:
        for value in values:
            raw = copy.deepcopy(original)
            raw["value"][field] = value
            with pytest.raises(FirstPitchProtocolError):
                decode_first_pitch_response(json.dumps(raw))


@pytest.mark.parametrize(
    ("path", "canonical", "python_name"),
    [
        (("value",), "countEffect", "count_effect"),
        (("value", "statFlags"), "投球数", "pitch"),
        (("value", "after"), "stateFields", "state_fields"),
        (("value", "after", "stateFields"), "state.count.balls", "balls"),
    ],
)
def test_wire_decoder_does_not_accept_python_attribute_aliases(
    path: tuple[str | int, ...],
    canonical: str,
    python_name: str,
) -> None:
    """Python DTOの属性名をwireの別memberとして許可しない。"""
    raw = _success()
    target = _at(raw, path)
    target[python_name] = target.pop(canonical)
    with pytest.raises(FirstPitchProtocolError):
        decode_first_pitch_response(json.dumps(raw))


@pytest.mark.parametrize("kind", ["missing", "unvalidated-before", "nested-type"])
def test_model_construct_bypass_cannot_reach_host(
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """model_constructで作った未検証値も製品入口で再検証する。"""

    def forbidden_host() -> None:
        pytest.fail("未検証DTOでhostを開いてはならない")

    monkeypatch.setattr(first_pitch, "open_domain_host", forbidden_host)
    valid = FirstPitchRequest.model_validate(_request())
    if kind == "missing":
        constructed = FirstPitchRequest.model_construct(event_kind="batting-result")
    elif kind == "unvalidated-before":
        bad = _request()
        bad["before"]["stateFields"]["state.gameEnded"] = 0
        constructed = FirstPitchRequest.model_construct(**bad)
    else:
        state_values: dict[str, Any] = valid.before.state_fields.model_dump()
        state_values["balls"] = 0
        state = type(valid.before.state_fields).model_construct(**state_values)
        before = type(valid.before).model_construct(
            state_fields=state, scoreboard=valid.before.scoreboard
        )
        constructed = FirstPitchRequest.model_construct(
            event_kind=valid.event_kind,
            result_id=valid.result_id,
            pitch_event_kind=valid.pitch_event_kind,
            before=before,
        )
    with pytest.raises(ValidationError):
        evaluate_first_pitch(constructed)


def test_decoder_rejects_nested_duplicate_member() -> None:
    """後勝ちJSONでflagを変える故障も拒否する。"""
    wire = json.dumps(_success(), ensure_ascii=False)
    wire = wire.replace('"投球数": true', '"投球数":true,"投球数":false', 1)
    with pytest.raises(FirstPitchProtocolError):
        decode_first_pitch_response(wire)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_decoder_rejects_nested_nonfinite_constant(constant: str) -> None:
    """既知の整数欄にJSON外の非有限数値を通さない。"""
    wire = json.dumps(_success()).replace('"count": "0"', '"count": ' + constant, 1)
    with pytest.raises(FirstPitchProtocolError):
        decode_first_pitch_response(wire)


@pytest.mark.parametrize(
    ("path", "canonical", "python_name"),
    [
        (("value",), "countEffect", "count_effect"),
        (("value",), "statFlags", "stat_flags"),
        (("value",), "historyContext", "history_context"),
        (("value", "after"), "stateFields", "state_fields"),
        (("value", "after", "stateFields"), "state.count.balls", "balls"),
        (("value", "after", "scoreboard"), "inningScores", "inning_scores"),
        (("value", "statFlags"), "投球数", "pitch"),
        (
            ("value", "historyContext", 0, "difference"),
            "stateFields",
            "state_fields",
        ),
    ],
)
@pytest.mark.parametrize("form", ["both", "name-only", "both-with-unknown"])
def test_decoder_rejects_alias_and_attribute_name_cutout(
    path: tuple[str | int, ...],
    canonical: str,
    python_name: str,
    form: str,
) -> None:
    """同値の二重名もdump時の黙示脱落を許可しない。"""
    raw = _success()
    target = _at(raw, path)
    target[python_name] = copy.deepcopy(target[canonical])
    if form == "name-only":
        del target[canonical]
    if form == "both-with-unknown":
        target["unknown_nested_member"] = True
    with pytest.raises(FirstPitchProtocolError):
        decode_first_pitch_response(json.dumps(raw, ensure_ascii=False))


@pytest.mark.parametrize(
    "path",
    [
        ("ok",),
        ("value", "plateAppearanceEnded"),
        ("value", "after", "stateFields", "state.gameEnded"),
        ("value", "after", "stateFields", "state.tiebreakActive"),
        ("value", "statFlags", "投球数"),
        ("value", "historyContext", 0, "difference", "statFlags", "投球数"),
    ],
)
@pytest.mark.parametrize("bad", [0, 1, 0.0, 1.0])
def test_response_boolean_does_not_use_python_numeric_equality(
    path: tuple[str | int, ...], bad: object
) -> None:
    """wire往復比較でboolと数値が同値でも既strict型で拒否する。"""
    raw = _success()
    _at(raw, path[:-1])[path[-1]] = bad
    with pytest.raises(FirstPitchProtocolError):
        decode_first_pitch_response(json.dumps(raw))
