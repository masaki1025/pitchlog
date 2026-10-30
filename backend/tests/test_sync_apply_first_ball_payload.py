"""V7/V8全値codecの固定vector・実artifactと、pure資格の境界を検査する。"""

from __future__ import annotations

import builtins
import json
import subprocess
import traceback
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest
from pydantic import ValidationError

from pitchlog.domainrt import first_pitch, first_pitch_continuation, host
from pitchlog.domainrt.first_ball_projection import FirstBallCalculationValue
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    evaluate_first_pitch_with_continuation,
)
from pitchlog.sync import first_ball_bridge
from pitchlog.sync.first_ball_payload import (
    FirstBallCourse,
    FirstBallObservations,
    FirstBallParticipants,
    FirstBallPayloadError,
    FirstBallPayloadValue,
    FirstBallPitchSpeed,
    FirstBallPlayPayload,
    format_first_ball_payload,
    read_first_ball_payload,
)
from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint

ROOT = Path(__file__).resolve().parents[2]
VECTOR = json.loads(
    (Path(__file__).parent / "fixtures/first_ball_payload_vectors_v1.json").read_text()
)
MATH = json.loads(
    (
        ROOT / "contracts/state-transition/t2_first_pitch_continuation_cases_v1.json"
    ).read_text()
)["cases"]
ERROR = "初球payloadの閉形式又は期待値が一致しません"


def js(value: object) -> str:
    """試験値のJSON表示だけを行い、数学は実装しない。"""
    return json.dumps(value, ensure_ascii=False)


@pytest.fixture(scope="module")
def evaluated() -> dict[str, dict[str, Any]]:
    """正式12caseを実artifactで各一度評価し、元期待値へ全比較する。"""
    assert VECTOR["mathCases"] == MATH
    assert len(MATH) == 12
    result = {}
    for case in MATH:
        request = CombinedRequest.model_validate_json(js(case["request"]))
        response = evaluate_first_pitch_with_continuation(request)
        actual = response.model_dump(mode="json", by_alias=True)
        assert actual == case["expected"]
        result[case["caseId"]] = {"request": case["request"], "response": actual}
    assert sum(x["response"]["ok"] for x in result.values()) == 4
    return result


def calculation(
    evaluated: dict[str, dict[str, Any]], index: int = 0
) -> FirstBallCalculationValue:
    """毎回新しいDTOを作り、共有fixtureへの強制変異を混入させない。"""
    row = evaluated[MATH[index]["caseId"]]
    return FirstBallCalculationValue.model_validate_json(
        js(
            {
                "formatVersion": "first-ball-calculation-v1",
                "artifactSha256": VECTOR["artifactSha256"],
                "request": row["request"],
                "response": row["response"],
            }
        )
    )


def participants() -> FirstBallParticipants:
    """pure試験のsynthetic期待参照。真正な同writer名簿ではない。"""
    return FirstBallParticipants.model_validate_json(js(VECTOR["participants"]))


def observations() -> FirstBallObservations:
    """正準観測の説明値を返す。画面変換/実観測を代替しない。"""
    return FirstBallObservations.model_validate_json(js(VECTOR["baseObservations"]))


def pair(evaluated: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """実評価値とsynthetic観測/参加者をencodeする。"""
    return format_first_ball_payload(
        observations(), participants(), calculation(evaluated)
    )


def read(
    v7: str, v8: str, evaluated: dict[str, dict[str, Any]]
) -> FirstBallPayloadValue:
    """rawと独立に実評価済期待値/参照を供給する。"""
    return read_first_ball_payload(
        v7,
        v8,
        expected_calculation=calculation(evaluated),
        expected_participants=participants(),
    )


@pytest.mark.parametrize("case", VECTOR["cases"], ids=lambda case: case["id"])
def test_all_fixed_cases_use_actual_existing_math_and_full_values(
    evaluated: dict[str, dict[str, Any]],
    case: dict[str, Any],
) -> None:
    """全caseを消費し、期待値を製品codecから生成せず全比較する。"""
    expected_case = next(
        i for i, x in enumerate(MATH) if x["caseId"] == case["expectedCalculationCase"]
    )
    calc = calculation(evaluated, expected_case)
    if case["expected"]["kind"] == "closed-rejection":
        with pytest.raises(FirstBallPayloadError) as error:
            read_first_ball_payload(
                case["v7Json"],
                case["v8Json"],
                expected_calculation=calc,
                expected_participants=participants(),
            )
        assert error.value.args == (ERROR,)
        assert error.value.__suppress_context__ is True
        assert "CANARY_INPUT" not in "".join(traceback.format_exception(error.value))
        return
    value = read_first_ball_payload(
        case["v7Json"],
        case["v8Json"],
        expected_calculation=calc,
        expected_participants=participants(),
    )
    assert value.model_dump(mode="json", by_alias=True) == case["expected"]["value"]
    raw = json.loads(case["v7Json"])
    encoded = format_first_ball_payload(
        FirstBallObservations.model_validate_json(js(raw["observations"])),
        participants(),
        calc,
    )
    assert {"v7": json.loads(encoded[0]), "v8": json.loads(encoded[1])} == case[
        "expected"
    ]["value"]


def test_vector_count_and_type_target_are_exact() -> None:
    """87case/旧12数学値/全23flagと承認型表識別値を固定する。"""
    assert VECTOR["caseCount"] == len(VECTOR["cases"]) == 87
    assert len({x["id"] for x in VECTOR["cases"]}) == 87
    assert sum(x["expected"]["kind"] == "accepted" for x in VECTOR["cases"]) == 15
    assert (
        VECTOR["typeTargetSha256"]
        == "72d2620c6731a5e9367880f2967a7771cc75e5c6e76a18052b988943ff2af921"
    )
    assert (
        VECTOR["typeFieldsSha256"]
        == "9555f1650b070b08539a7a20b9551f3c67d3f28818630d9b72c7028b649c80d3"
    )
    assert set(FirstBallPlayPayload.model_fields) == {
        "format_version",
        "observations",
        "participants",
        "calculation",
    }
    assert set(FirstBallObservations.model_fields) == {
        "pitch_type_key",
        "course",
        "pitch_speed",
        "stance",
        "batting_side",
    }
    assert set(FirstBallCourse.model_fields) == {"unit", "x", "y"}
    assert set(FirstBallPitchSpeed.model_fields) == {"kmh", "outside_range_confirmed"}
    assert set(FirstBallParticipants.model_fields) == {
        "batter_id",
        "pitcher_id",
        "catcher_id",
        "batting_order",
    }


def leaves(
    value: object, path: tuple[str | int, ...] = ()
) -> list[tuple[str | int, ...]]:
    """空containerも含め、固定期待の全leafを走査する。"""
    if isinstance(value, dict) and value:
        return [
            p for key, member in value.items() for p in leaves(member, (*path, key))
        ]
    if isinstance(value, list) and value:
        return [
            p
            for index, member in enumerate(value)
            for p in leaves(member, (*path, index))
        ]
    return [path]


def replace_leaf(value: Any, path: tuple[str | int, ...]) -> None:
    """一箇所だけを型適合又は型不適合値へ改変する。"""
    parent = value
    for key in path[:-1]:
        parent = parent[key]
    original = parent[path[-1]]
    parent[path[-1]] = (
        not original if type(original) is bool else "2" if original != "2" else "3"
    )


CALC_LEAVES = leaves(json.loads(VECTOR["cases"][0]["v7Json"])["calculation"])
DIFF_LEAVES = leaves(json.loads(VECTOR["cases"][0]["v8Json"]))


@pytest.mark.parametrize("path", CALC_LEAVES, ids=lambda path: ".".join(map(str, path)))
def test_each_calculation_leaf_is_compared_without_omission(
    evaluated: dict[str, dict[str, Any]],
    path: tuple[str | int, ...],
) -> None:
    """request/rules/23flag/after/history/T2全leafの改変を拒否する。"""
    v7, v8 = pair(evaluated)
    wire = json.loads(v7)
    replace_leaf(wire["calculation"], path)
    with pytest.raises(FirstBallPayloadError):
        read(js(wire), v8, evaluated)


@pytest.mark.parametrize("path", DIFF_LEAVES, ids=lambda path: ".".join(map(str, path)))
def test_each_v8_leaf_is_compared_without_omission(
    evaluated: dict[str, dict[str, Any]],
    path: tuple[str | int, ...],
) -> None:
    """V8単独の前後値/23flag/空boardを同じ実評価へ全比較する。"""
    v7, v8 = pair(evaluated)
    wire = json.loads(v8)
    replace_leaf(wire, path)
    with pytest.raises(FirstBallPayloadError):
        read(v7, js(wire), evaluated)


def test_mutation_population_contains_all_three_flag_sets() -> None:
    """T1出力/履歴/V8の23flagを一つも走査対象から落とさない。"""
    for population, prefix in [
        (CALC_LEAVES, ("response", "value", "t1", "statFlags")),
        (
            CALC_LEAVES,
            ("response", "value", "t1", "historyContext", 0, "difference", "statFlags"),
        ),
        (DIFF_LEAVES, ("statFlags",)),
    ]:
        assert len([p for p in population if p[:-1] == prefix]) == 23


@pytest.mark.parametrize(
    "bad", [None, True, {}, [], b"{}", "null", "[]", "{", "NaN", "Infinity"]
)
@pytest.mark.parametrize("side", ["v7", "v8"])
def test_invalid_raw_values_are_fixed_rejection(
    evaluated: dict[str, dict[str, Any]],
    bad: Any,
    side: str,
) -> None:
    """非文字列/非object/非JSON拡張を修復しない。"""
    v7, v8 = pair(evaluated)
    with pytest.raises(FirstBallPayloadError) as error:
        read(bad if side == "v7" else v7, bad if side == "v8" else v8, evaluated)
    assert error.value.args == (ERROR,)


@pytest.mark.parametrize(
    "variant",
    [
        "missing",
        "extra",
        "tuple-list",
        "ok-int",
        "alias",
        "participants-extra",
        "observation-type",
        "subclass",
        "bare",
    ],
)
def test_forced_models_cannot_bypass_full_revalidation(
    evaluated: dict[str, dict[str, Any]],
    variant: str,
) -> None:
    """frozenの強制差替えや同型fakeを黙って正規化しない。"""
    calc = calculation(evaluated)
    people = participants()
    obs = observations()
    if variant == "missing":
        del calc.response.value.t1.__dict__["after"]
    elif variant == "extra":
        calc.__dict__["CANARY_INPUT"] = "CANARY_INPUT"
    elif variant == "tuple-list":
        object.__setattr__(
            calc.response.value.t1,
            "history_context",
            list(calc.response.value.t1.history_context),
        )
    elif variant == "ok-int":
        object.__setattr__(calc.response, "ok", 1)
    elif variant == "alias":
        obs.__dict__["pitchTypeKey"] = "CANARY_INPUT"
    elif variant == "participants-extra":
        people.__dict__["CANARY_INPUT"] = "CANARY_INPUT"
    elif variant == "observation-type":
        object.__setattr__(obs.course, "x", 132)
    elif variant == "subclass":

        class Derived(FirstBallObservations):
            pass

        obs = Derived.model_validate_json(js(VECTOR["baseObservations"]))
    else:
        calc = object.__new__(FirstBallCalculationValue)
    with pytest.raises(FirstBallPayloadError) as error:
        format_first_ball_payload(obs, people, calc)
    assert error.value.args == (ERROR,)


def test_expected_models_are_mandatory_and_revalidated(
    evaluated: dict[str, dict[str, Any]],
) -> None:
    """raw自身のexpected採用や不正期待値の成功化を許さない。"""
    v7, v8 = pair(evaluated)
    with pytest.raises(TypeError):
        cast(Any, read_first_ball_payload)(v7, v8)
    with pytest.raises(FirstBallPayloadError):
        read_first_ball_payload(
            v7,
            v8,
            expected_calculation=cast(Any, None),
            expected_participants=participants(),
        )
    people = participants()
    people.__dict__["extra"] = False
    with pytest.raises(FirstBallPayloadError):
        read_first_ball_payload(
            v7,
            v8,
            expected_calculation=calculation(evaluated),
            expected_participants=people,
        )


def test_graph_and_raw_are_detached_and_no_wire_fingerprint_is_replaced(
    evaluated: dict[str, dict[str, Any]],
) -> None:
    """元event/元dictの変更や別名化を行わず独立な全値を返す。"""
    v7, v8 = pair(evaluated)
    p7, p8 = json.loads(v7), json.loads(v8)
    raw = {
        "d5": "20000000-0000-0000-0000-000000000001",
        "game_id": "30000000-0000-0000-0000-000000000001",
        "d1": 1,
        "d4": "generation-A",
        "event_kind": "1",
        "d2": 10,
        "payload": p7,
        "state_diff": p8,
    }
    frozen = freeze_wire_event(raw)
    digest = wire_event_fingerprint(frozen)
    old = SyncEvent(
        d5=raw["d5"],
        game_id=raw["game_id"],
        d1=1,
        d4=raw["d4"],
        v5="1",
        v6=10,
        v7=p7,
        v8=p8,
    )
    legacy = operation_fingerprint(old, "P2", None)
    value = read(v7, v8, evaluated)
    assert value.model_dump(mode="json", by_alias=True) == {"v7": p7, "v8": p8}
    assert (
        value.v8
        is not value.v7.calculation.response.value.t1.history_context[0].difference
    )
    p7["observations"]["course"]["x"] = "9"
    assert value.v7.observations.course.x == "132"
    dumped = value.model_dump(mode="json", by_alias=True)
    dumped["v8"]["statFlags"]["投球数"] = False
    assert value.v8.stat_flags.pitch is True
    with pytest.raises(ValidationError):
        setattr(value.v7.observations.course, "x", "7")
    assert wire_event_fingerprint(frozen) == digest
    assert operation_fingerprint(old, "P2", None) == legacy
    assert old.v5 == "1"


def test_matching_forged_expectations_are_only_values_not_writer_evidence(
    evaluated: dict[str, dict[str, Any]],
) -> None:
    """同じ偽pair/名簿を両側へ渡せても数学/認可/frameの資格を出さない。"""
    calc = calculation(evaluated)
    object.__setattr__(calc.response.value.t1.after.state_fields, "balls", "123")
    people = participants()
    object.__setattr__(people, "batter_id", "10000000-0000-0000-0000-000000000099")
    before = dict(first_ball_bridge._STATES)
    v7, v8 = format_first_ball_payload(observations(), people, calc)
    value = read_first_ball_payload(
        v7, v8, expected_calculation=calc, expected_participants=people
    )
    assert value.v7.calculation.response.value.t1.after.state_fields.balls == "123"
    assert first_ball_bridge._STATES == before
    assert set(type(value).model_fields) == {"v7", "v8"}
    with pytest.raises(FirstBallPayloadError):
        read(v7, v8, evaluated)


def test_formatter_and_reader_call_no_host_db_network_or_file_io(
    evaluated: dict[str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実評価済みの値変換中は外部呼出をせず、単一TSを複製しない。"""
    obs = observations()
    people = participants()
    calc = calculation(evaluated)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("外部I/Oへ到達")

    for module in [first_pitch, first_pitch_continuation, host]:
        monkeypatch.setattr(module, "open_domain_host", forbidden)
    monkeypatch.setattr(host.NodeDomainHost, "call", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    v7, v8 = format_first_ball_payload(obs, people, calc)
    assert (
        read_first_ball_payload(
            v7, v8, expected_calculation=calc, expected_participants=people
        ).v7.observations.pitch_speed.kmh
        is None
    )


def member_paths(
    value: object, path: tuple[str | int, ...] = ()
) -> list[tuple[str | int, ...]]:
    """全object memberの必須性を、型表の実JSON形から検査する。"""
    if isinstance(value, dict):
        return [(*path, key) for key in value] + [
            p for key, child in value.items() for p in member_paths(child, (*path, key))
        ]
    if isinstance(value, list):
        return [
            p
            for index, child in enumerate(value)
            for p in member_paths(child, (*path, index))
        ]
    return []


REQUIRED_MEMBERS = [
    ("v7", p) for p in member_paths(json.loads(VECTOR["cases"][0]["v7Json"]))
] + [("v8", p) for p in member_paths(json.loads(VECTOR["cases"][0]["v8Json"]))]


@pytest.mark.parametrize(
    "side,path",
    REQUIRED_MEMBERS,
    ids=lambda v: ".".join(map(str, v)) if isinstance(v, tuple) else v,
)
def test_every_declared_member_is_required_without_defaulting(
    evaluated: dict[str, dict[str, Any]],
    side: str,
    path: tuple[str | int, ...],
) -> None:
    """nullableや23flagも省略せず、補完/partial受入を拒否する。"""
    v7, v8 = pair(evaluated)
    wire = json.loads(v7 if side == "v7" else v8)
    parent = wire
    for key in path[:-1]:
        parent = parent[key]
    del parent[path[-1]]
    with pytest.raises(FirstBallPayloadError):
        read(
            js(wire) if side == "v7" else v7,
            js(wire) if side == "v8" else v8,
            evaluated,
        )


@pytest.mark.parametrize("index", range(4, 12), ids=lambda i: MATH[i]["caseId"])
def test_formatter_cannot_promote_existing_non_success_evaluations(
    evaluated: dict[str, dict[str, Any]],
    index: int,
) -> None:
    """実評価failure/partialを強制DTOへ詰めても成功encodeしない。"""
    from pitchlog.domainrt.first_pitch_continuation import decode_combined_response

    row = evaluated[MATH[index]["caseId"]]
    forged = FirstBallCalculationValue.model_construct(
        format_version="first-ball-calculation-v1",
        artifact_sha256=VECTOR["artifactSha256"],
        request=CombinedRequest.model_validate_json(js(row["request"])),
        response=decode_combined_response(js(row["response"])),
    )
    with pytest.raises(FirstBallPayloadError):
        format_first_ball_payload(observations(), participants(), forged)


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_kind", "other"),
        ("result_id", "batting-result.called-pitch"),
        ("pitch_event_kind", "non-pitch-event"),
    ],
)
def test_formatter_has_no_other_operation_success_fallback(
    evaluated: dict[str, dict[str, Any]],
    field: str,
    value: str,
) -> None:
    """型適合の偽成功値でも、別操作へ初球variantを流用しない。"""
    calc = calculation(evaluated)
    object.__setattr__(calc.request.t1, field, value)
    with pytest.raises(FirstBallPayloadError):
        format_first_ball_payload(observations(), participants(), calc)
