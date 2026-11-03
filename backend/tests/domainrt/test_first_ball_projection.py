"""初球全値の往復・改変拒否と、純値と実保存証拠の境界を検査する。"""

from __future__ import annotations

import builtins
import copy
import json
import subprocess
import traceback
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from pitchlog.domainrt import first_pitch, first_pitch_continuation, host
from pitchlog.domainrt.first_ball_projection import (
    FirstBallCalculationValue,
    FirstBallProjectionError,
    format_first_ball_calculation,
    read_first_ball_calculation,
)
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    CombinedResponse,
    CombinedSuccess,
    decode_combined_response,
    evaluate_first_pitch_with_continuation,
)

_ROOT = Path(__file__).resolve().parents[3]
_CASES = json.loads(
    (
        _ROOT / "contracts/state-transition/t2_first_pitch_continuation_cases_v1.json"
    ).read_text()
)["cases"]
_SCHEMA = json.loads(
    (
        _ROOT / "contracts/state-transition/t2_first_pitch_continuation_schema_v1.json"
    ).read_text()
)
_ARTIFACT_SHA = json.loads(
    (_ROOT / "frontend/public/domain/pitchlog-domain.json").read_text()
)["sha256"]
_ERROR = "初球計算値の閉形式又は期待値が一致しません"


def _json(value: object) -> str:
    """試験JSONの生成だけを行い、意味を計算しない。"""
    return json.dumps(value, ensure_ascii=False)


@pytest.fixture(scope="module")
def evaluated() -> tuple[dict[str, Any], ...]:
    """実12要求を既callerで各一度評価し、旧schema/全期待値も検査する。"""
    assert len(_CASES) == 12
    results = []
    for case in _CASES:
        request = CombinedRequest.model_validate_json(_json(case["request"]))
        response = evaluate_first_pitch_with_continuation(request)
        actual = response.model_dump(mode="json", by_alias=True)
        Draft202012Validator(_SCHEMA).validate(actual)
        assert actual == case["expected"]
        results.append({"request": case["request"], "response": actual})
    assert sum(row["response"]["ok"] for row in results) == 4
    return tuple(results)


def _pair(
    evaluated: tuple[dict[str, Any], ...],
    index: int = 0,
) -> tuple[CombinedRequest, CombinedResponse]:
    """共有fixtureから独立した既DTOを再取得する。"""
    row = evaluated[index]
    return (
        CombinedRequest.model_validate_json(_json(row["request"])),
        decode_combined_response(_json(row["response"])),
    )


def _formatted(evaluated: tuple[dict[str, Any], ...], index: int = 0) -> str:
    request, response = _pair(evaluated, index)
    assert type(response) is CombinedSuccess
    return format_first_ball_calculation(
        request, response, artifact_sha256=_ARTIFACT_SHA
    )


def _read(
    raw: str,
    evaluated: tuple[dict[str, Any], ...],
    index: int = 0,
) -> FirstBallCalculationValue:
    request, response = _pair(evaluated, index)
    assert type(response) is CombinedSuccess
    return read_first_ball_calculation(
        raw,
        expected_request=request,
        expected_response=response,
        expected_artifact_sha256=_ARTIFACT_SHA,
    )


def _value_at(value: Any, path: tuple[str | int, ...]) -> Any:
    """故障注入対象だけをたどる。"""
    for name in path:
        value = value[name]
    return value


def _replace(value: Any, path: tuple[str | int, ...], replacement: Any) -> None:
    """一箇所だけを変更する。"""
    _value_at(value, path[:-1])[path[-1]] = replacement


def _leaves(
    value: Any, prefix: tuple[str | int, ...] = ()
) -> list[tuple[str | int, ...]]:
    """空containerも落とさず、全leafの比較対象を列挙する。"""
    if isinstance(value, dict) and value:
        return [
            path
            for key, item in value.items()
            for path in _leaves(item, (*prefix, key))
        ]
    if isinstance(value, list) and value:
        return [
            path
            for key, item in enumerate(value)
            for path in _leaves(item, (*prefix, key))
        ]
    return [prefix]


_RESPONSE_PATHS = _leaves(_CASES[0]["expected"])
_REQUEST_PATHS = _leaves(_CASES[0]["request"])


@pytest.mark.parametrize("index", range(12), ids=lambda index: _CASES[index]["caseId"])
def test_real_artifact_all_cases_roundtrip_or_reject_non_success(
    evaluated: tuple[dict[str, Any], ...],
    index: int,
) -> None:
    """実artifact全値を保持し、非成功8件は候補へ昇格させない。"""
    request, response = _pair(evaluated, index)
    if type(response) is not CombinedSuccess:
        with pytest.raises(FirstBallProjectionError, match=_ERROR):
            format_first_ball_calculation(
                request, cast(CombinedSuccess, response), artifact_sha256=_ARTIFACT_SHA
            )
        return
    raw = format_first_ball_calculation(
        request, response, artifact_sha256=_ARTIFACT_SHA
    )
    value = _read(raw, evaluated, index)
    assert value.model_dump(mode="json", by_alias=True) == {
        "formatVersion": "first-ball-calculation-v1",
        "artifactSha256": _ARTIFACT_SHA,
        "request": evaluated[index]["request"],
        "response": evaluated[index]["response"],
    }
    assert value.response.value.t1.after == response.value.t1.after
    assert value.response.value.t1.history_context == response.value.t1.history_context
    assert value.response.value.t2 == response.value.t2
    assert len(type(value.response.value.t1.stat_flags).model_fields) == 23


@pytest.mark.parametrize(
    "path", _RESPONSE_PATHS, ids=lambda path: ".".join(map(str, path))
)
def test_each_response_value_is_compared_without_omission(
    evaluated: tuple[dict[str, Any], ...],
    path: tuple[str | int, ...],
) -> None:
    """23flag/after/履歴/T2を含む全leafの単独改変を拒否する。"""
    wire = json.loads(_formatted(evaluated))
    original = _value_at(wire["response"], path)
    changed = (
        not original if type(original) is bool else "2" if original != "2" else "3"
    )
    _replace(wire["response"], path, changed)
    with pytest.raises(FirstBallProjectionError):
        _read(_json(wire), evaluated)


@pytest.mark.parametrize(
    "path", _REQUEST_PATHS, ids=lambda path: ".".join(map(str, path))
)
def test_each_request_value_is_compared_without_recalculation(
    evaluated: tuple[dict[str, Any], ...],
    path: tuple[str | int, ...],
) -> None:
    """before/rules/DH/nullable値の差替えも固定期待値との全比較で拒否する。"""
    wire = json.loads(_formatted(evaluated))
    original = _value_at(wire["request"], path)
    changed = (
        not original if type(original) is bool else "2" if original != "2" else "3"
    )
    _replace(wire["request"], path, changed)
    with pytest.raises(FirstBallProjectionError):
        _read(_json(wire), evaluated)


@pytest.mark.parametrize("other_index", [1, 2])
def test_type_valid_t2_family_substitution_is_not_an_expected_match(
    evaluated: tuple[dict[str, Any], ...],
    other_index: int,
) -> None:
    """既ABIで正当な別T2 basisも、元評価の期待値へ混入させない。"""
    wire = json.loads(_formatted(evaluated))
    wire["response"]["value"]["t2"] = copy.deepcopy(
        evaluated[other_index]["response"]["value"]["t2"]
    )
    assert type(decode_combined_response(_json(wire["response"]))) is CombinedSuccess
    with pytest.raises(FirstBallProjectionError):
        _read(_json(wire), evaluated)


def test_full_flag_population_is_covered_by_leaf_mutations() -> None:
    """出力23flagと履歴23flagの両方が走査母集団へ含まれる。"""
    for prefix in [
        ("value", "t1", "statFlags"),
        ("value", "t1", "historyContext", 0, "difference", "statFlags"),
    ]:
        assert {path[-1] for path in _RESPONSE_PATHS if path[:-1] == prefix} == set(
            _value_at(_CASES[0]["expected"], prefix)
        )
        assert len([path for path in _RESPONSE_PATHS if path[:-1] == prefix]) == 23


@pytest.mark.parametrize("index", range(4))
def test_nullable_and_valid_tuples_are_preserved(
    evaluated: tuple[dict[str, Any], ...],
    index: int,
) -> None:
    """既null・空tuple・history tupleを一律拒否せず保持する。"""
    value = _read(_formatted(evaluated, index), evaluated, index)
    assert value.request.rules.tiebreak is None
    assert value.request.rules.cold_conditions == ()
    assert value.response.value.t1.out_effect.targets == ()
    assert value.response.value.t1.runner_default_advance.first.destination is None
    assert type(value.response.value.t1.history_context) is tuple
    if index in (1, 2, 3):
        assert value.request.rules.extension_limit is None


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-after",
        "extra",
        "alias",
        "numeric-decimal",
        "noncanonical-decimal",
        "numeric-bool",
        "nonnull-null",
        "invalid-tuple-element",
        "history-missing",
        "history-empty",
        "history-truncated-flag",
        "t2-missing",
        "t2-unknown",
        "version",
        "version-bool",
        "hash-format",
        "hash-other-valid",
        "ok-one",
    ],
)
def test_closed_shape_and_expected_values_reject_mutations(
    evaluated: tuple[dict[str, Any], ...],
    mutation: str,
) -> None:
    """形状違反と型に適合する期待値改変をいずれも拒否する。"""
    wire = json.loads(_formatted(evaluated))
    t1 = wire["response"]["value"]["t1"]
    if mutation == "missing-after":
        del t1["after"]
    elif mutation == "extra":
        wire["unknown"] = "CANARY_INPUT"
    elif mutation == "alias":
        wire["artifact_sha256"] = wire.pop("artifactSha256")
    elif mutation == "numeric-decimal":
        t1["after"]["stateFields"]["state.count.balls"] = 1
    elif mutation == "noncanonical-decimal":
        t1["after"]["stateFields"]["state.count.balls"] = "01"
    elif mutation == "numeric-bool":
        t1["statFlags"]["投球数"] = 1
    elif mutation == "nonnull-null":
        wire["request"]["t1"]["before"]["stateFields"]["state.inning"] = None
    elif mutation == "invalid-tuple-element":
        t1["outEffect"]["targets"] = ["batter"]
    elif mutation == "history-missing":
        del t1["historyContext"]
    elif mutation == "history-empty":
        t1["historyContext"] = []
    elif mutation == "history-truncated-flag":
        del t1["historyContext"][0]["difference"]["statFlags"]["投球数"]
    elif mutation == "t2-missing":
        del wire["response"]["value"]["t2"]
    elif mutation == "t2-unknown":
        wire["response"]["value"]["t2"]["kind"] = "no-decision"
    elif mutation == "version":
        wire["formatVersion"] = "first-ball-calculation-v2"
    elif mutation == "version-bool":
        wire["formatVersion"] = True
    elif mutation == "hash-format":
        wire["artifactSha256"] = "A" * 64
    elif mutation == "hash-other-valid":
        wire["artifactSha256"] = "f" * 64
    elif mutation == "ok-one":
        wire["response"]["ok"] = 1
    else:
        raise AssertionError(mutation)
    with pytest.raises(FirstBallProjectionError) as error:
        _read(_json(wire), evaluated)
    assert error.value.args == (_ERROR,)
    assert "CANARY_INPUT" not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize(
    "raw", [None, True, {}, b"{}", "null", "[]", "{", "NaN", "Infinity"]
)
def test_invalid_json_or_nonstring_is_fixed_rejection(
    evaluated: tuple[dict[str, Any], ...],
    raw: object,
) -> None:
    """非JSON/nonfinite/非文字列を原例外付きで公開しない。"""
    with pytest.raises(FirstBallProjectionError) as error:
        _read(cast(str, raw), evaluated)
    assert error.value.args == (_ERROR,)


def test_duplicate_keys_at_root_and_nested_are_rejected(
    evaluated: tuple[dict[str, Any], ...],
) -> None:
    """同値の重複keyも黙って後勝ちへ正規化しない。"""
    raw = _formatted(evaluated)
    duplicates = [
        raw.replace(
            '"formatVersion":',
            '"formatVersion":"first-ball-calculation-v1","formatVersion":',
            1,
        ),
        raw.replace(
            '"state.count.balls":"0"',
            '"state.count.balls":"0","state.count.balls":"0"',
            1,
        ),
    ]
    for changed in duplicates:
        assert changed != raw
        with pytest.raises(FirstBallProjectionError):
            _read(changed, evaluated)


def test_cross_case_and_expected_hash_are_not_inferred_from_raw(
    evaluated: tuple[dict[str, Any], ...],
) -> None:
    """別要求と別hashをrawから自己承認しない。"""
    raw = _formatted(evaluated, 1)
    with pytest.raises(FirstBallProjectionError):
        _read(raw, evaluated, 0)
    request, response = _pair(evaluated)
    with pytest.raises(FirstBallProjectionError):
        read_first_ball_calculation(
            _formatted(evaluated),
            expected_request=request,
            expected_response=cast(CombinedSuccess, response),
            expected_artifact_sha256="f" * 64,
        )


def test_tuple_order_and_count_are_not_discarded(
    evaluated: tuple[dict[str, Any], ...],
) -> None:
    """人工の合法入力tupleで順序を検査し、実T2評価の根拠とは扱わない。"""
    request_wire = copy.deepcopy(evaluated[0]["request"])
    entries = [
        {"pointDifference": "7", "startInning": "8"},
        {"pointDifference": "9", "startInning": "9"},
    ]
    request_wire["rules"]["coldConditions"] = entries
    request = CombinedRequest.model_validate_json(_json(request_wire))
    _, response = _pair(evaluated)
    assert type(response) is CombinedSuccess
    raw = format_first_ball_calculation(
        request, response, artifact_sha256=_ARTIFACT_SHA
    )
    checked = read_first_ball_calculation(
        raw,
        expected_request=request,
        expected_response=response,
        expected_artifact_sha256=_ARTIFACT_SHA,
    )
    assert len(checked.request.rules.cold_conditions) == 2
    for modified in [list(reversed(entries)), entries[:1]]:
        changed = json.loads(raw)
        changed["request"]["rules"]["coldConditions"] = modified
        with pytest.raises(FirstBallProjectionError):
            read_first_ball_calculation(
                _json(changed),
                expected_request=request,
                expected_response=response,
                expected_artifact_sha256=_ARTIFACT_SHA,
            )


@pytest.mark.parametrize(
    "mutation", ["extra", "missing", "tuple-list", "numeric-ok", "bare-instance"]
)
def test_forced_models_cannot_be_silently_normalized(
    evaluated: tuple[dict[str, Any], ...],
    mutation: str,
) -> None:
    """強制改変や偽instanceを既modelへ黙って正規化しない。"""
    request, response = _pair(evaluated)
    assert type(response) is CombinedSuccess
    if mutation == "extra":
        response.__dict__["CANARY_INPUT"] = "CANARY_INPUT"
    elif mutation == "missing":
        del response.value.t1.__dict__["after"]
    elif mutation == "tuple-list":
        object.__setattr__(
            response.value.t1,
            "history_context",
            list(response.value.t1.history_context),
        )
    elif mutation == "numeric-ok":
        object.__setattr__(response, "ok", 1)
    elif mutation == "bare-instance":
        response = object.__new__(CombinedSuccess)
    with pytest.raises(FirstBallProjectionError) as error:
        format_first_ball_calculation(request, response, artifact_sha256=_ARTIFACT_SHA)
    assert str(error.value) == _ERROR


def test_output_graph_and_json_are_detached_from_inputs_and_dumps(
    evaluated: tuple[dict[str, Any], ...],
) -> None:
    """返却と原値のobjectを共有せず、後発変更を混入させない。"""
    request, response = _pair(evaluated)
    assert type(response) is CombinedSuccess
    raw = format_first_ball_calculation(
        request, response, artifact_sha256=_ARTIFACT_SHA
    )
    first = read_first_ball_calculation(
        raw,
        expected_request=request,
        expected_response=response,
        expected_artifact_sha256=_ARTIFACT_SHA,
    )
    assert first.request is not request and first.response is not response
    assert first.response.value.t1.after is not response.value.t1.after
    dumped = first.model_dump(mode="json", by_alias=True)
    dumped["response"]["value"]["t1"]["after"]["stateFields"]["state.count.balls"] = (
        "900"
    )
    assert first.response.value.t1.after.state_fields.balls == "1"
    with pytest.raises(ValidationError):
        setattr(first.response.value.t1.after.state_fields, "balls", "900")
    object.__setattr__(response.value.t1.after.state_fields, "balls", "900")
    assert first.response.value.t1.after.state_fields.balls == "1"
    assert _read(raw, evaluated).response.value.t1.after.state_fields.balls == "1"
    with pytest.raises(FirstBallProjectionError):
        read_first_ball_calculation(
            raw,
            expected_request=request,
            expected_response=response,
            expected_artifact_sha256=_ARTIFACT_SHA,
        )


def test_formatter_and_reader_do_not_open_host_database_or_files(
    evaluated: tuple[dict[str, Any], ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pure入口の実行中に外部効果を呼ばない。"""
    request, response = _pair(evaluated)
    assert type(response) is CombinedSuccess

    def forbidden(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("pure APIから外部効果へ到達")

    with monkeypatch.context() as patch:
        for module in [host, first_pitch, first_pitch_continuation]:
            patch.setattr(module, "open_domain_host", forbidden)
        patch.setattr(psycopg, "connect", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        raw = format_first_ball_calculation(
            request, response, artifact_sha256=_ARTIFACT_SHA
        )
        value = read_first_ball_calculation(
            raw,
            expected_request=request,
            expected_response=response,
            expected_artifact_sha256=_ARTIFACT_SHA,
        )
    assert value.response.value.t1.after == response.value.t1.after


def test_matching_values_are_not_a_mathematical_or_saving_certificate(
    evaluated: tuple[dict[str, Any], ...],
) -> None:
    """同じ偽期待値も型に合えば値として往復する限界を明示する。"""
    request, _ = _pair(evaluated)
    changed = copy.deepcopy(evaluated[0]["response"])
    changed["value"]["t1"]["after"]["stateFields"]["state.count.balls"] = "123"
    response = decode_combined_response(_json(changed))
    assert type(response) is CombinedSuccess
    raw = format_first_ball_calculation(
        request, response, artifact_sha256=_ARTIFACT_SHA
    )
    value = read_first_ball_calculation(
        raw,
        expected_request=request,
        expected_response=response,
        expected_artifact_sha256=_ARTIFACT_SHA,
    )
    assert value.response.value.t1.after.state_fields.balls == "123"
    assert set(FirstBallCalculationValue.model_fields) == {
        "format_version",
        "artifact_sha256",
        "request",
        "response",
    }
    with pytest.raises(FirstBallProjectionError):
        _read(raw, evaluated)
