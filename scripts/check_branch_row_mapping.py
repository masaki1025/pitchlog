"""分岐と規範行の対応表を台帳・行・凍結fixtureへ突合する。"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from itertools import product
from pathlib import Path
from typing import Any, NoReturn

import representative_selection

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAME = "branch_row_mapping_schema_v1.json"


class BranchRowMappingError(ValueError):
    """対応表の宣言または参照整合が不正である。"""


class HistoryEffectError(ValueError):
    """履歴面の規範行または入力スナップショットが不正な場合を表す。"""


def _fail(rule_id: str, detail: str) -> NoReturn:
    """規則 ID を含む違反を返す。"""
    raise HistoryEffectError(f"{rule_id}: {detail}")


def resolve_history_depth(history: dict[str, Any]) -> int:
    """history-depth の宣言済み max 式から D の実値を得る。"""
    try:
        derivation = history["derivation"]
        if history["version"] != 1 or derivation["formula"] != {
            "operator": "max",
            "operands": [
                {"cases": "requiredScenarioCases", "measure": "events.length", "aggregate": "max"},
                {
                    "cases": "stackCompositionCases",
                    "measure": "stackKinds.length",
                    "aggregate": "max",
                },
            ],
        }:
            _fail("HISTORY_DEPTH", "D の導出式が不明")
        sizes: list[int] = []
        for collection, field, declared in (
            ("requiredScenarioCases", "events", "length"),
            ("stackCompositionCases", "stackKinds", "minimumDepth"),
        ):
            records = derivation[collection]
            if not isinstance(records, list) or not records:
                _fail("HISTORY_DEPTH", f"{collection} が空")
            for item in records:
                size = len(item[field])
                if size < 1 or item[declared] != size:
                    _fail("HISTORY_DEPTH", f"{collection}.{declared} が不一致")
                sizes.append(size)
        if derivation["result"]["historyDepthFrom"] != "formula":
            _fail("HISTORY_DEPTH", "結果の参照先が不明")
        return max(sizes)
    except (KeyError, TypeError, ValueError) as error:
        raise HistoryEffectError("HISTORY_DEPTH: D を解決できない") from error


def _depth_zero_only(predicate: dict[str, Any], descriptor: dict[str, Any]) -> bool:
    """述語が許す履歴深さの集合が 0 だけかを列挙して調べる。"""
    axes = sorted(representative_selection.predicate_axes(predicate))
    if "history.depth" not in axes:
        return False
    values_by_axis = representative_selection.axis_values(
        descriptor, ("stateTransitionAxes",)
    )
    if any(axis not in values_by_axis for axis in axes):
        _fail("HISTORY_UNDECIDABLE", "述語に未登録の軸がある")
    if predicate.get("op") == "and" and all(
        isinstance(arg, dict) and arg.get("op") == "eq"
        for arg in predicate.get("args", [])
    ):
        equalities = predicate["args"]
        if any(
            arg.get("axisId") not in values_by_axis
            or arg.get("value") not in values_by_axis[arg["axisId"]]
            for arg in equalities
        ):
            _fail("HISTORY_UNDECIDABLE", "述語の固定値が軸の値域外")
        fixed: dict[str, Any] = {}
        for arg in equalities:
            axis_id = arg["axisId"]
            if axis_id in fixed and fixed[axis_id] != arg["value"]:
                _fail("HISTORY_UNDECIDABLE", "述語の同一軸に矛盾する固定値がある")
            fixed[axis_id] = arg["value"]
        depth_values = {
            arg["value"] for arg in equalities if arg["axisId"] == "history.depth"
        }
        return depth_values == {0}
    size = 1
    for axis in axes:
        size *= len(values_by_axis[axis])
        if size > 100_000:
            _fail("HISTORY_UNDECIDABLE", "述語の入力直積が上限を超える")
    possible = {
        coordinate["history.depth"]
        for values in product(*(values_by_axis[axis] for axis in axes))
        if representative_selection.predicate_holds(
            predicate, coordinate := dict(zip(axes, values, strict=True))
        )
    }
    return possible == {0}


def _all_unchanged(fields: object) -> bool:
    """比較面の全フィールドが非変更であることを返す。"""
    return isinstance(fields, dict) and all(
        value == {"kind": "unchanged"} for value in fields.values()
    )


def _scenario_d_plus_one_only(predicate: dict[str, Any], descriptor: dict[str, Any]) -> bool:
    """述語が許すシナリオ長が D+1 だけかを値域から判定する。"""
    axes = sorted(representative_selection.predicate_axes(predicate))
    if "history.scenarioLength" not in axes:
        return False
    values_by_axis = representative_selection.axis_values(
        descriptor, ("stateTransitionAxes",)
    )
    if any(axis not in values_by_axis for axis in axes):
        _fail("XC-09", "述語に未登録の軸がある")
    size = 1
    for axis in axes:
        size *= len(values_by_axis[axis])
        if size > 100_000:
            _fail("XC-09", "述語の入力直積が上限を超える")
    possible = {
        coordinate["history.scenarioLength"]
        for values in product(*(values_by_axis[axis] for axis in axes))
        if representative_selection.predicate_holds(
            predicate, coordinate := dict(zip(axes, values, strict=True))
        )
    }
    return possible == {"D+1"}


def compare_liveness_undo(
    input_stack: object, expected: object, actual: object,
) -> bool:
    """保証範囲外の undo で結果と履歴要素数だけを比較する。"""
    if (
        not isinstance(input_stack, list)
        or not isinstance(expected, dict)
        or expected.get("guaranteeMode") != "liveness-only"
        or expected.get("operationResult") != "applied"
        or not isinstance(actual, dict)
        or not isinstance(actual.get("historyContext"), list)
    ):
        return False
    return (
        actual.get("operationResult") == "applied"
        and len(actual["historyContext"]) == len(input_stack) - 1
    )


def validate_rows(contract: dict[str, Any], descriptor: dict[str, Any]) -> None:
    """操作・undo の列と StateEffect の面の同値を検査する。

    Args:
        contract: 状況判定契約。
        descriptor: 履歴深さの値域を持つ入力軸 descriptor。

    Raises:
        HistoryEffectError: D-8 の列・面・交差制約に違反する場合。
    """
    for index, row in enumerate(contract["operationRows"]):
        label = f"operationRows[{index}]"
        column = row["historyEffect"]
        face = row["stateEffect"]["historyAndResult"]
        expected_history = (
            {"kind": "push", "entryKind": column["kind"]}
            if column["pushes"] else {"kind": "unchanged"}
        )
        if face["history"].get("kind") == "pop":
            _fail("HISTORY_OPERATION_POP", label)
        if face["history"] != expected_history:
            _fail("HISTORY_COLUMN_FACE", label)
        if face["operationResult"] != {"kind": "set", "value": row["operationResult"]}:
            _fail("RESULT_COLUMN_FACE", label)
        if row["operationResult"] != "applied" and column["pushes"]:
            _fail("HISTORY_REJECTED_PUSH", label)
        if column["pushes"] and (
            row["operationKind"] != "state-correction"
            or column["kind"] != "state-correction"
        ):
            _fail("HISTORY_PUSH_KIND", label)
        if row["operationKind"] == "tiebreak-start":
            _validate_tiebreak_row(row, label)

    for index, row in enumerate(contract["undoRows"]):
        label = f"undoRows[{index}]"
        pops = row["historyEffect"]["pops"]
        face = row["stateEffect"]["historyAndResult"]
        expected_history = {"kind": "pop", "count": 1} if pops == 1 else {"kind": "unchanged"}
        if face["history"].get("kind") == "push":
            _fail("HISTORY_UNDO_PUSH", label)
        if face["history"] != expected_history:
            _fail("HISTORY_COLUMN_FACE", label)
        if face["operationResult"] != {"kind": "set", "value": row["operationResult"]}:
            _fail("RESULT_COLUMN_FACE", label)
        if (row["operationResult"] == "applied") != (pops == 1):
            _fail("HISTORY_UNDO_RESULT", label)
        liveness = row["guaranteeMode"] == "liveness-only"
        if liveness and not (
            _scenario_d_plus_one_only(row["precondition"], descriptor)
            and row["targetKind"] != "none"
            and pops == 1
            and row["operationResult"] == "applied"
            and all(
                _all_unchanged(row["stateEffect"][face])
                for face in ("stateFields", "scoreboard", "statFlags")
            )
            and "比較対象外" in row["remarks"]
        ):
            _fail("XC-09", label)
        depth_zero = _depth_zero_only(row["precondition"], descriptor)
        if not (
            (row["targetKind"] == "none")
            == (row["operationResult"] == "nothing-to-undo")
            == depth_zero
            == (pops == 0)
        ):
            _fail("HISTORY_NONE_EQUIVALENCE", label)
        if not _all_unchanged(row["stateEffect"]["statFlags"]):
            _fail("HISTORY_UNDO_FLAGS", label)
        if row["stateEffect"]["stateFields"]["state.score"].get("kind") == "set":
            predicate = row["precondition"]
            terms = predicate.get("args") if predicate.get("op") == "and" else None
            fixed = {
                term["axisId"]: term["value"]
                for term in terms or []
                if isinstance(term, dict) and term.get("op") == "eq"
            }
            for axis_id, face, member in (
                ("history.topDifference.state.score.away.before", "stateFields", "away"),
                ("history.topDifference.scoreboard.inningScores.home.before", "scoreboard", "home"),
                ("history.topDifference.scoreboard.inningScores.away.before", "scoreboard", "away"),
            ):
                value = row["stateEffect"][face][
                    "state.score" if face == "stateFields" else "inningScores"
                ]
                if value.get("kind") != "set" or fixed.get(axis_id) != value["value"][member]:
                    _fail("HISTORY_UNDO_SET_BOUNDARY", label)
        if row["targetKind"] == "none" and (
            row["guaranteeMode"] != "full-equality"
            or not _all_unchanged(row["stateEffect"]["stateFields"])
            or not _all_unchanged(row["stateEffect"]["scoreboard"])
        ):
            _fail("HISTORY_NONE_EFFECT", label)


def _validate_tiebreak_row(row: dict[str, Any], label: str) -> None:
    """FR-009 の指定値と操作行の比較面の一致を検査する。"""
    predicate = row["precondition"]
    args = predicate.get("args") if predicate.get("op") == "and" else None
    if not isinstance(args, list) or any(
        not isinstance(item, dict) or item.get("op") != "eq" for item in args
    ):
        _fail("TIEBREAK_PRECONDITION", label)
    fixed = {item["axisId"]: item["value"] for item in args}
    if len(fixed) != len(args) or any(
        axis not in fixed for axis in (
            "event.tiebreakStart.runnerPlacement",
            "event.tiebreakStart.leadoffBatter",
            "event.tiebreakStart.inning",
            "event.tiebreakStart.activationRelation",
            "rules.tiebreakStartInning",
        )
    ):
        _fail("TIEBREAK_PRECONDITION", label)
    effect = row["stateEffect"]
    if row["operationResult"] == "applied":
        if (fixed["event.tiebreakStart.activationRelation"] != "ready"
            or fixed["rules.tiebreakStartInning"] == "none"):
            _fail("TIEBREAK_ACTIVATION", label)
        pairs = (
            ("state.runners", "event.tiebreakStart.runnerPlacement"),
            ("state.battingOrder", "event.tiebreakStart.leadoffBatter"),
            ("state.inning", "event.tiebreakStart.inning"),
        )
        for output, source in pairs:
            if effect["stateFields"][output] != {"kind": "set", "value": fixed[source]}:
                _fail("TIEBREAK_PAYLOAD_SET", label)
        if effect["stateFields"]["state.tiebreakActive"] != {
            "kind": "set", "value": True,
        }:
            _fail("TIEBREAK_ACTIVATION", label)
    elif row["operationResult"] == "rejected-precondition":
        if fixed["event.tiebreakStart.activationRelation"] != "not-ready":
            _fail("TIEBREAK_ACTIVATION", label)
        if any(
            item != {"kind": "unchanged"}
            for face in ("stateFields", "scoreboard", "statFlags")
            for item in effect[face].values()
        ):
            _fail("TIEBREAK_REJECTED_EFFECT", label)
    else:
        _fail("TIEBREAK_RESULT", label)


def validate_undo_case_differences(contract: dict[str, Any], depth: int) -> None:
    """undo の先頭差分と逆適用、残る履歴要素を照合する。

    Args:
        contract: 規範行と派生 case を持つ状況判定契約。
        depth: history-depth から解決した D の実値。
    """
    consecutive: list[dict[str, Any]] = []
    single: list[dict[str, Any]] = []
    for case in contract["cases"]:
        reference = case.get("rowRef", {})
        if reference.get("layer") != "undoRows":
            continue
        coordinate = case.get("inputCoordinate", {})
        if "history.topDifference.changedFaces" not in coordinate:
            continue
        label = case.get("caseId", "undo")
        expected = case.get("expected", {})
        stack = case.get("historyInput", {}).get("stack")
        if (
            not isinstance(stack, list)
            or not stack
            or expected.get("guaranteeMode") != "full-equality"
            or expected.get("operationResult") != "applied"
        ):
            _fail("UNDO_DIFFERENCE_INPUT", label)
        declared_depth = coordinate.get("history.depth")
        if (depth if declared_depth == "D" else declared_depth) != len(stack):
            _fail("UNDO_DIFFERENCE_INPUT", label)
        if coordinate.get("history.scenarioLength") != declared_depth:
            _fail("UNDO_DIFFERENCE_INPUT", label)
        top = stack[0]
        if top.get("kind") != "confirmed-play":
            _fail("UNDO_DIFFERENCE_INPUT", label)
        difference = top.get("difference", {})
        face = expected.get("stateEffect", {})
        if (
            "state.score" in difference.get("stateFields", {})
            and difference.get("statFlags", {}).get("得点") is True
            and "inningScores" not in difference.get("scoreboard", {})
        ):
            _fail("UNDO_INNING_SCORE_DIFF", label)
        for surface in ("stateFields", "scoreboard"):
            changed = difference.get(surface)
            effects = face.get(surface)
            if not isinstance(changed, dict) or not isinstance(effects, dict):
                _fail("UNDO_DIFFERENCE_INPUT", label)
            for field, effect in effects.items():
                if field not in changed:
                    inverse = {"kind": "unchanged"}
                else:
                    pair = changed[field]
                    if not isinstance(pair, dict) or set(pair) != {"before", "after"}:
                        _fail("UNDO_DIFFERENCE_INPUT", label)
                    before, after = pair["before"], pair["after"]
                    if before == after:
                        _fail("UNDO_DIFFERENCE_INPUT", label)
                    inverse = (
                        {"kind": "delta", "value": before - after}
                        if type(before) is int and type(after) is int
                        and "state.half" not in difference["stateFields"]
                        else {"kind": "set", "value": before}
                    )
                if effect != inverse:
                    _fail("UNDO_INVERSE_DIFF", f"{label}: {surface}.{field}")
        changed_state = bool(difference["stateFields"])
        changed_board = bool(difference["scoreboard"])
        changed_faces = (
            "half-inning-boundary" if "state.half" in difference["stateFields"]
            else "state-and-scoreboard" if changed_state and changed_board
            else "state-only" if changed_state
            else "scoreboard-only" if changed_board
            else None
        )
        if coordinate["history.topDifference.changedFaces"] != changed_faces:
            _fail("UNDO_SCALAR_BINDING", label)
        scalar_fields = {
            "state.outs.before": ("stateFields", "state.outs", None, "before"),
            "state.outs.delta": ("stateFields", "state.outs", None, "delta"),
            "state.score.home.before": ("stateFields", "state.score", "home", "before"),
            "state.score.home.delta": ("stateFields", "state.score", "home", "delta"),
            "state.score.away.before": ("stateFields", "state.score", "away", "before"),
            "state.half.before": ("stateFields", "state.half", None, "before"),
            "state.inning.before": ("stateFields", "state.inning", None, "before"),
            "scoreboard.hits.before": ("scoreboard", "hits", None, "before"),
            "scoreboard.hits.delta": ("scoreboard", "hits", None, "delta"),
            "scoreboard.inningScores.home.before": (
                "scoreboard", "inningScores", "home", "before"
            ),
            "scoreboard.inningScores.home.delta": (
                "scoreboard", "inningScores", "home", "delta"
            ),
            "scoreboard.inningScores.away.before": (
                "scoreboard", "inningScores", "away", "before"
            ),
        }
        required_by_field = {
            ("stateFields", "state.outs"): ("state.outs.before",),
            ("stateFields", "state.score"): (
                "state.score.home.before", "state.score.home.delta",
                "state.score.away.before",
            ),
            ("stateFields", "state.half"): ("state.half.before",),
            ("stateFields", "state.inning"): ("state.inning.before",),
            ("scoreboard", "hits"): ("scoreboard.hits.before", "scoreboard.hits.delta"),
            ("scoreboard", "inningScores"): (
                "scoreboard.inningScores.home.before",
                "scoreboard.inningScores.home.delta",
                "scoreboard.inningScores.away.before",
            ),
        }
        for surface in ("stateFields", "scoreboard"):
            for field in difference[surface]:
                suffixes = required_by_field.get((surface, field))
                if suffixes is None or any(
                    f"history.topDifference.{suffix}" not in coordinate
                    for suffix in suffixes
                ):
                    _fail("UNDO_SCALAR_BINDING", f"{label}: {surface}.{field}")
                if field == "state.outs" and "state.half" not in difference["stateFields"]:
                    if "history.topDifference.state.outs.delta" not in coordinate:
                        _fail("UNDO_SCALAR_BINDING", f"{label}: {surface}.{field}")
                if field == "state.score" and (
                    difference[surface][field]["before"].get("away")
                    != difference[surface][field]["after"].get("away")
                ):
                    _fail("UNDO_SCALAR_BINDING", f"{label}: {surface}.{field}")
        contribution = coordinate.get("history.topDifference.statFlags.contribution")
        contribution_flags = {
            "out-and-pitch": {"投球数", "投球回算入アウト"},
            "run-hit-and-pitch": {"投球数", "被安打", "安打", "得点", "打点"},
            "hit-and-pitch": {"投球数", "被安打", "安打"},
        }
        flags = difference.get("statFlags")
        if (
            not isinstance(flags, dict)
            or set(flags) != set(face["statFlags"])
            or any(type(value) is not bool for value in flags.values())
            or {name for name, value in flags.items() if value}
            != contribution_flags.get(contribution)
        ):
            _fail("UNDO_SCALAR_BINDING", f"{label}: statFlags.contribution")
        for suffix, (surface, field, member, measure) in scalar_fields.items():
            axis_id = f"history.topDifference.{suffix}"
            if axis_id not in coordinate:
                continue
            pair = difference[surface].get(field)
            if not isinstance(pair, dict):
                _fail("UNDO_SCALAR_BINDING", f"{label}: {axis_id}")
            before, after = pair["before"], pair["after"]
            if member is not None:
                if not isinstance(before, dict) or not isinstance(after, dict):
                    _fail("UNDO_SCALAR_BINDING", f"{label}: {axis_id}")
                before, after = before.get(member), after.get(member)
            value = after - before if measure == "delta" else before
            if coordinate[axis_id] != value:
                _fail("UNDO_SCALAR_BINDING", f"{label}: {axis_id}")
        if expected.get("historyContext") != stack[1:]:
            _fail("UNDO_TAIL_PRESERVATION", label)
        if len(stack) == 2:
            consecutive.append(case)
        elif len(stack) == 1:
            single.append(case)
    if not any(
        first["expected"]["historyContext"] == second["historyInput"]["stack"]
        for first in consecutive for second in single
    ):
        _fail("UNDO_CONTINUITY", "連続undoの2回目へ差分が渡らない")


def push_entry(
    entry_kind: str,
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    stat_flags: dict[str, bool],
    state_fields: set[str],
    scoreboard_fields: set[str],
    flag_fields: set[str],
) -> dict[str, Any]:
    """比較面の前後と操作が出力したフラグから積む要素を作る。

    Args:
        entry_kind: 取消可能な操作の種別。
        before: 状態欄とスコアボードの適用前の値。
        after: 状態欄とスコアボードの適用後の値。
        stat_flags: 当該操作が出力した 23 フラグ。
        state_fields: 状態欄の全フィールド名。
        scoreboard_fields: スコアボードの全フィールド名。
        flag_fields: 成績計上フラグの全フィールド名。

    Returns:
        種別と差分を持つ履歴要素。

    Raises:
        HistoryEffectError: 前後の比較面またはフラグが不足する場合。
    """
    expected_faces = {"stateFields": state_fields, "scoreboard": scoreboard_fields}
    for face, fields in expected_faces.items():
        if (
            set(before.get(face, {})) != fields
            or set(after.get(face, {})) != fields
        ):
            _fail("HISTORY_SNAPSHOT", f"{face} の前後フィールドが不足する")
    if set(stat_flags) != flag_fields or any(
        type(value) is not bool for value in stat_flags.values()
    ):
        _fail("HISTORY_FLAGS", "当該操作が出力した23フラグが不足する")
    return {
        "kind": entry_kind,
        "difference": {
            face: {
                field: {
                    "before": copy.deepcopy(before[face][field]),
                    "after": copy.deepcopy(after[face][field]),
                }
                for field in sorted(fields)
                if before[face][field] != after[face][field]
            }
            for face, fields in expected_faces.items()
        } | {"statFlags": copy.deepcopy(stat_flags)},
    }


def apply_history(
    stack: list[dict[str, Any]], effect: dict[str, Any], entry: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """履歴面を入力スタックへ適用し、遷移後のスタックを返す。

    Args:
        stack: 適用前の履歴スタック。
        effect: unchanged・push・pop の履歴面。
        entry: push で積む履歴要素。

    Returns:
        面を適用した履歴スタック。

    Raises:
        HistoryEffectError: 面とスタックを適用できない場合。
    """
    result = copy.deepcopy(stack)
    kind = effect.get("kind")
    if kind == "unchanged":
        return result
    if kind == "pop" and effect.get("count") == 1 and result:
        return result[1:]
    if kind == "push" and entry is not None and entry.get("kind") == effect.get("entryKind"):
        return [copy.deepcopy(entry), *result]
    _fail("HISTORY_APPLY", "履歴面と入力スタックを適用できない")


def validate_push_entry(
    entry: dict[str, Any],
    entry_kind: str,
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    stat_flags: dict[str, bool],
    state_fields: set[str],
    scoreboard_fields: set[str],
    flag_fields: set[str],
) -> None:
    """履歴要素が前後差分と操作出力の 23 値に完全一致するか調べる。

    Args:
        entry: 照合する履歴要素。
        entry_kind: 取消可能な操作の種別。
        before: 状態欄とスコアボードの適用前の値。
        after: 状態欄とスコアボードの適用後の値。
        stat_flags: 当該操作が出力した 23 フラグ。
        state_fields: 状態欄の全フィールド名。
        scoreboard_fields: スコアボードの全フィールド名。
        flag_fields: 成績計上フラグの全フィールド名。

    Raises:
        HistoryEffectError: 差分または出力フラグと一致しない場合。
    """
    canonical = push_entry(
        entry_kind, before, after, stat_flags,
        state_fields, scoreboard_fields, flag_fields,
    )
    if entry != canonical:
        _fail("HISTORY_ENTRY_DIFFERENCE", "push 要素が前後差分または出力フラグと不一致")


def project_legacy_operation_fixture(expected: dict[str, Any]) -> dict[str, Any]:
    """凍結済みの旧操作 fixture を D-8 の結果面へ射影する。

    Args:
        expected: 凍結済みの操作結果。

    Returns:
        結果面だけを現行の set へ移した操作結果。

    Raises:
        HistoryEffectError: 旧 fixture の形が想定と異なる場合。
    """
    projected = copy.deepcopy(expected)
    face = projected.get("stateEffect", {}).get("historyAndResult", {})
    if (
        face.get("history") != {"kind": "unchanged"}
        or face.get("operationResult") != {"kind": "unchanged"}
        or projected.get("operationResult") != "applied"
    ):
        _fail("HISTORY_LEGACY_FIXTURE", "旧操作 fixture の比較面が想定外")
    face["operationResult"] = {"kind": "set", "value": "applied"}
    return projected

def _validate_instance(
    value: Any, schema: dict[str, Any], root_schema: dict[str, Any], path: str
) -> None:
    """対応表schemaで使う閉じたJSON Schema語彙を検査する。

    Args:
        value: 検査対象の値。
        schema: 現在のschema節。
        root_schema: ローカル参照の起点。
        path: エラー表示用の位置。
    """
    reference = schema.get("$ref")
    if isinstance(reference, str):
        if not reference.startswith("#/$defs/"):
            raise BranchRowMappingError(f"schema参照が不正: {path}")
        name = reference.removeprefix("#/$defs/")
        target = root_schema.get("$defs", {}).get(name)
        if not isinstance(target, dict):
            raise BranchRowMappingError(f"schema参照先がない: {path}")
        _validate_instance(value, target, root_schema, path)
        return
    variants = schema.get("oneOf")
    if isinstance(variants, list):
        matched = 0
        for variant in variants:
            if not isinstance(variant, dict):
                raise BranchRowMappingError(f"schemaのoneOfが不正: {path}")
            try:
                _validate_instance(value, variant, root_schema, path)
            except BranchRowMappingError:
                continue
            matched += 1
        if matched != 1:
            raise BranchRowMappingError(f"schemaのoneOfに一意に一致しない: {path}")
        return
    if "const" in schema and value != schema["const"]:
        raise BranchRowMappingError(f"schemaのconst不一致: {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise BranchRowMappingError(f"schemaのenum外: {path}")
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(value, dict):
        raise BranchRowMappingError(f"schemaのobject型違反: {path}")
    if expected_type == "array" and not isinstance(value, list):
        raise BranchRowMappingError(f"schemaのarray型違反: {path}")
    if expected_type == "string" and not isinstance(value, str):
        raise BranchRowMappingError(f"schemaのstring型違反: {path}")
    if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise BranchRowMappingError(f"schemaのinteger型違反: {path}")
    if expected_type == "integer" and value < schema.get("minimum", 0):
        raise BranchRowMappingError(f"schemaの整数下限違反: {path}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise BranchRowMappingError(f"schemaの必須列欠落: {path}: {sorted(missing)}")
        unknown = set(value) - set(properties)
        if schema.get("additionalProperties") is False and unknown:
            raise BranchRowMappingError(f"schemaの未知キー: {path}: {sorted(unknown)}")
        for key, child in value.items():
            if key in properties:
                _validate_instance(child, properties[key], root_schema, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise BranchRowMappingError(f"schemaの配列要素が不足: {path}")
        unique_values = {json.dumps(item, sort_keys=True) for item in value}
        if schema.get("uniqueItems") is True and len(unique_values) != len(value):
            raise BranchRowMappingError(f"schemaの配列要素が重複: {path}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_instance(item, item_schema, root_schema, f"{path}[{index}]")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        raise BranchRowMappingError(f"schemaの文字列が短い: {path}")


def _read_object(root: Path, relative: str | Path) -> dict[str, Any]:
    """リポジトリ内のJSONオブジェクトを読む。

    Args:
        root: リポジトリルート。
        relative: 資産で宣言された相対パス。

    Returns:
        JSONオブジェクト。
    """
    path = Path(relative)
    if path.is_absolute() or not (root / path).resolve().is_relative_to(root.resolve()):
        raise BranchRowMappingError(f"参照先がリポジトリ外: {relative}")
    document = json.loads((root / path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise BranchRowMappingError(f"JSONオブジェクトでない: {relative}")
    return document


def _predicate_holds(predicate: dict[str, Any], coordinate: dict[str, Any]) -> bool:
    """fixture座標が規範行の述語を満たすか判定する。

    Args:
        predicate: 規範行の事前条件。
        coordinate: fixtureの入力座標。

    Returns:
        述語の真偽。
    """
    operation = predicate.get("op")
    if operation == "eq":
        axis_id = predicate.get("axisId")
        if not isinstance(axis_id, str) or axis_id not in coordinate:
            raise BranchRowMappingError(f"述語の軸をfixtureで評価できない: {axis_id}")
        return coordinate[axis_id] == predicate.get("value")
    if operation == "in":
        if set(predicate) != {"op", "axisId", "values"}:
            raise BranchRowMappingError("有限inのfieldが不正")
        axis_id = predicate["axisId"]
        if not isinstance(axis_id, str) or axis_id not in coordinate:
            raise BranchRowMappingError(f"述語の軸をfixtureで評価できない: {axis_id}")
        values = predicate["values"]
        if (
            not isinstance(values, list) or not values
            or type(values[0]) not in (str, int, bool)
            or any(type(value) is not type(values[0]) for value in values)
            or len(values) != len(set(values))
        ):
            raise BranchRowMappingError("有限inの値が空・異型・重複")
        return any(type(coordinate[axis_id]) is type(value)
                   and coordinate[axis_id] == value for value in values)
    args = predicate.get("args")
    if not isinstance(args, list) or not args or not all(isinstance(arg, dict) for arg in args):
        raise BranchRowMappingError("規範行の述語引数が不正")
    if operation == "and":
        return all(_predicate_holds(arg, coordinate) for arg in args)
    if operation == "or":
        return any(_predicate_holds(arg, coordinate) for arg in args)
    if operation == "not" and len(args) == 1:
        return not _predicate_holds(args[0], coordinate)
    raise BranchRowMappingError(f"未対応の述語演算子: {operation}")


def _legacy_game_end_predicate(predicate: dict[str, Any]) -> dict[str, Any]:
    """凍結済み手作業fixtureの4軸射影で旧行との対応を照合する。"""
    if predicate.get("op") != "and" or not isinstance(predicate.get("args"), list):
        raise BranchRowMappingError("終了判定行の旧fixture射影を判定できない")
    args = predicate["args"]
    omitted_axes = {
        "gameEnd.satisfiedColdTierCount",
        "state.outs",
        "state.runners",
        "state.count.strikes",
        "state.count.balls",
        "event.operationPayload",
        "event.perPitch.pitchEventKind",
        "event.perPitch.runnerEventPayload",
        "event.perPitch.runnerAdvanceOverridesByRunner",
        "event.perPitch.thirdOutTimingByRunner",
        "event.perPitch.interferenceRuling",
        "event.perPitch.officialScoringPayload",
        "event.perPitch.rbi.doublePlayRelayError",
        "event.perPitch.rbi.runnerContinuityByRunner",
        "event.perPitch.rbi.wouldScoreWithoutErrorByRunner",
    }
    projected = [
        arg for arg in args
        if not (
            isinstance(arg, dict)
            and arg.get("op") == "eq"
            and arg.get("axisId") in omitted_axes
        )
    ]
    removed = [arg.get("axisId") for arg in args if arg not in projected]
    if removed not in [
        ["gameEnd.satisfiedColdTierCount"],
        [
            "gameEnd.satisfiedColdTierCount",
            "state.outs", "state.runners", "state.count.strikes", "state.count.balls",
        ],
        [
            "gameEnd.satisfiedColdTierCount",
            "state.outs", "state.runners",
            "event.operationPayload", "event.perPitch.pitchEventKind",
            "event.perPitch.runnerEventPayload",
            "event.perPitch.runnerAdvanceOverridesByRunner",
            "event.perPitch.thirdOutTimingByRunner",
            "event.perPitch.interferenceRuling",
            "event.perPitch.officialScoringPayload",
            "event.perPitch.rbi.doublePlayRelayError",
            "event.perPitch.rbi.runnerContinuityByRunner",
            "event.perPitch.rbi.wouldScoreWithoutErrorByRunner",
        ],
    ]:
        raise BranchRowMappingError("終了判定行の旧fixture射影の除外軸が不正")
    return {"op": "and", "args": projected}


def _unique_rows(rows: list[dict[str, Any]], coordinate: dict[str, Any]) -> dict[str, Any]:
    """自然キーが指す規範行を一意に得る。

    Args:
        rows: 対象層の規範行。
        coordinate: 自然キー。

    Returns:
        一意の規範行。
    """
    matches = [
        row for row in rows
        if all(row.get(field) == value for field, value in coordinate.items())
    ]
    if len(matches) != 1:
        raise BranchRowMappingError(f"規範行の座標が一意に実在しない: {coordinate}")
    return matches[0]


def _check_additional_matrix_cases(
    entry: dict[str, Any], fixture: dict[str, Any],
    contract: dict[str, Any], coverage_refs: list[dict[str, Any]],
) -> None:
    """既分岐の追加正例を追加fixture・実行case・規範行へ双方向に束縛する。"""
    cases = fixture.get("additionalCases", [])
    mappings = entry.get("additionalCaseMappings", [])
    case_ids = [case["caseId"] for case in cases]
    mapping_ids = [mapping["caseId"] for mapping in mappings]
    if (len(set(case_ids)) != len(case_ids)
            or len(set(mapping_ids)) != len(mapping_ids)
            or set(case_ids) != set(mapping_ids)):
        raise BranchRowMappingError("追加caseと対応表のexact-setが不一致")
    if not cases:
        return
    if entry["fixtureRelation"] != "row-output" or entry["rowRef"]["layer"] != "matrixRows":
        raise BranchRowMappingError("追加caseは既matrix正例の分岐だけに許す")
    by_id = {case["caseId"]: case for case in cases}
    for mapping in mappings:
        case = by_id[mapping["caseId"]]
        reference = mapping["rowRef"]
        if case["branchId"] != entry["branchId"]:
            raise BranchRowMappingError("追加caseの分岐IDが主fixtureと一致しない")
        if reference["layer"] != "matrixRows" or reference not in coverage_refs:
            raise BranchRowMappingError("追加caseの参照が既matrix行参照にない")
        row = _unique_rows(contract["matrixRows"], reference["coordinate"])
        coordinate = case["inputCoordinate"]
        if (coordinate.get("eventKind") != row["eventKind"]
                or coordinate.get("resultId") != row["resultId"]
                or not _predicate_holds(row["precondition"], coordinate)):
            raise BranchRowMappingError("追加caseの入力が規範行の前提を満たさない")
        output = {key: value for key, value in row.items()
                  if key not in {"eventKind", "resultId", "precondition", "remarks"}}
        if case["expected"] != output:
            raise BranchRowMappingError("追加caseの六効果が規範行と一致しない")
        consumed = [item for item in contract["cases"] if item["caseId"] == case["caseId"]]
        if len(consumed) != 1 or consumed[0]["rowRef"] != reference:
            raise BranchRowMappingError("追加caseの実行case参照が一意でない")
        fields = ("caseId", "inputId", "inputPayload", "inputCoordinate", "expected")
        if any(case.get(key) != consumed[0].get(key) for key in fields):
            raise BranchRowMappingError("追加fixtureと実行caseが一致しない")


def check_documents(
    mapping: dict[str, Any],
    schema: dict[str, Any],
    coverage: dict[str, Any],
    register: dict[str, Any],
    state_contract: dict[str, Any],
    game_end_contract: dict[str, Any],
    fixture_documents: dict[str, dict[str, Any]],
) -> None:
    """対応表を実資産と双方向に照合する。

    Args:
        mapping: 分岐・規範行対応表。
        schema: 対応表の閉じたschema。
        coverage: 手作業fixtureの被覆宣言。
        register: 条文分岐台帳。
        state_contract: 状況判定契約。
        game_end_contract: 終了判定契約。
        fixture_documents: パス別の凍結fixture。
    """
    _validate_instance(mapping, schema, schema, "$")

    branches = register["branches"]
    register_by_id = {branch["branchId"]: branch for branch in branches}
    if len(register_by_id) != len(branches):
        raise BranchRowMappingError("条文分岐台帳のIDが重複する")
    if len(branches) != mapping["expectedRegisterBranches"]:
        raise BranchRowMappingError("台帳の期待分岐件数が不一致")
    missing_ids = {item["branchId"] for item in coverage["missingFixtureBranches"]}
    if len(missing_ids) != len(coverage["missingFixtureBranches"]):
        raise BranchRowMappingError("fixture免除宣言のIDが重複する")
    if len(missing_ids) != mapping["expectedExcludedBranches"]:
        raise BranchRowMappingError("照合対象外の期待分岐件数が不一致")
    fixtures: dict[str, dict[str, Any]] = {}
    for source in coverage["fixtureSources"]:
        document = fixture_documents[source["fixturePath"]]
        for item in document["fixtures"]:
            branch_id = item["case"]["branchId"]
            if branch_id in fixtures:
                raise BranchRowMappingError(f"fixtureの分岐IDが重複する: {branch_id}")
            fixtures[branch_id] = item
    if set(register_by_id) - set(fixtures) != missing_ids:
        raise BranchRowMappingError("fixture免除のexact-setが台帳と一致しない")
    if set(fixtures) - set(register_by_id):
        raise BranchRowMappingError("台帳にないfixture分岐がある")

    entries = mapping["mappings"]
    entry_ids = [entry["branchId"] for entry in entries]
    if len(set(entry_ids)) != len(entry_ids):
        raise BranchRowMappingError("対応表の分岐IDが重複する")
    unknown = set(entry_ids) - set(register_by_id)
    if unknown:
        raise BranchRowMappingError(f"台帳にない対応表の分岐ID: {sorted(unknown)}")
    if set(entry_ids) != set(fixtures):
        raise BranchRowMappingError("対応表とfixtureを持つ分岐のexact-setが不一致")
    positive_entries = [
        entry for entry in entries
        if entry["fixtureRelation"] != "cross-constraint-negative"
    ]
    negative_entries = [
        entry for entry in entries
        if entry["fixtureRelation"] == "cross-constraint-negative"
    ]
    if len(positive_entries) != mapping["expectedPositiveMatches"]:
        raise BranchRowMappingError("正例の期待照合件数が不一致")
    if len(negative_entries) != mapping["expectedNegativeMatches"]:
        raise BranchRowMappingError("負例の期待照合件数が不一致")
    if any("expectedViolationIds" in entry for entry in positive_entries):
        raise BranchRowMappingError("正例に違反集合の宣言がある")
    if any("expectedViolationIds" not in entry for entry in negative_entries):
        raise BranchRowMappingError("負例の違反集合宣言がない")

    all_case_ids = [
        case["caseId"] for fixture in fixtures.values()
        for case in [fixture["case"], *fixture.get("additionalCases", [])]
    ]
    if len(all_case_ids) != len(set(all_case_ids)):
        raise BranchRowMappingError("主fixtureと追加fixtureのcaseIDが重複する")
    coverage_refs = [
        reference
        for item in state_contract["mustOperationCoverage"]["mappings"]
        for reference in item["rowRefs"]
    ]
    for entry in entries:
        branch_id = entry["branchId"]
        reference = entry["rowRef"]
        layer = reference["layer"]
        coordinate = reference["coordinate"]
        relation = entry["fixtureRelation"]
        _check_additional_matrix_cases(
            entry, fixtures[branch_id], state_contract, coverage_refs
        )
        fixture = fixtures[branch_id]["case"]
        source_ids = {
            source["sourceId"] for source in fixtures[branch_id]["provenance"]["sources"]
        }
        if not source_ids.intersection(register_by_id[branch_id]["sourceClauseIds"]):
            raise BranchRowMappingError(f"fixtureと台帳に共通の典拠がない: {branch_id}")
        if layer == "decisionRows":
            row = _unique_rows(game_end_contract[layer], coordinate)
            if coordinate["branchId"] != branch_id or row["branchId"] != branch_id:
                raise BranchRowMappingError(f"終了判定行自身の分岐IDが不一致: {branch_id}")
            if relation != "decision-output":
                raise BranchRowMappingError(f"終了判定のfixture関係が不正: {branch_id}")
            if not _predicate_holds(
                _legacy_game_end_predicate(row["precondition"]),
                fixture["inputCoordinate"],
            ):
                raise BranchRowMappingError(f"fixtureが終了判定の前提を満たさない: {branch_id}")
            if fixture["decision"] != row["decision"]:
                raise BranchRowMappingError(f"fixtureと終了判定の出力が異なる: {branch_id}")
            continue

        row = _unique_rows(state_contract[layer], coordinate)
        if reference not in coverage_refs:
            raise BranchRowMappingError(f"既存の行参照にない座標: {branch_id}")
        fixture_input = fixture["inputCoordinate"]
        for field in coordinate:
            if field in ("precondition", "payloadShape") and layer == "operationRows":
                continue
            if field != "precondition" and fixture_input.get(field) != coordinate[field]:
                raise BranchRowMappingError(f"fixtureと規範行の入力種別が異なる: {branch_id}")
        row_output = {
            field: value for field, value in row.items()
            if field not in coordinate and field != "remarks"
        }
        if relation == "row-output":
            if not _predicate_holds(row["precondition"], fixture_input):
                raise BranchRowMappingError(f"fixtureが規範行の前提を満たさない: {branch_id}")
            fixture_output = fixture["expected"]
            if branch_id == "DRAW-05":
                fixture_output = project_legacy_operation_fixture(
                    fixture_output
                )
            if fixture_output != row_output:
                raise BranchRowMappingError(f"fixtureと規範行の出力が異なる: {branch_id}")
        elif relation == "cross-constraint-negative" and layer == "matrixRows":
            candidate = fixture_input.get("candidateEffects")
            if not isinstance(candidate, dict) or (
                _predicate_holds(row["precondition"], fixture_input)
                and candidate == row_output
            ):
                raise BranchRowMappingError(f"交差制約fixtureに変異がない: {branch_id}")
        else:
            raise BranchRowMappingError(f"fixture関係と行層が整合しない: {branch_id}")


def check_repository(
    root: Path,
    mapping_relative: Path,
    mapping_override: dict[str, Any] | None = None,
) -> None:
    """リポジトリの宣言から対応表の全参照を検査する。

    Args:
        root: リポジトリルート。
        mapping_relative: 対応表への相対パス。
        mapping_override: 負例で使う対応表の差し替え。
    """
    mapping = (
        mapping_override
        if mapping_override is not None
        else _read_object(root, mapping_relative)
    )
    schema = _read_object(root, mapping_relative.parent / SCHEMA_NAME)
    _validate_instance(mapping, schema, schema, "$")
    coverage = _read_object(root, mapping["fixtureCoveragePath"])
    fixture_documents = {
        source["fixturePath"]: _read_object(root, source["fixturePath"])
        for source in coverage["fixtureSources"]
    }
    check_documents(
        mapping,
        schema,
        coverage,
        _read_object(root, coverage["branchRegisterPath"]),
        _read_object(root, mapping["stateContractPath"]),
        _read_object(root, mapping["gameEndContractPath"]),
        fixture_documents,
    )


def main(argv: list[str] | None = None) -> int:
    """CLIで実資産の対応表を検査する。

    Args:
        argv: コマンドライン引数。

    Returns:
        正常なら0、違反なら1。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--mapping", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        check_repository(args.root.resolve(), args.mapping)
    except (BranchRowMappingError, OSError, ValueError, KeyError) as error:
        print(f"branch-row-mapping: 違反: {error}", file=sys.stderr)
        return 1
    print("branch-row-mapping: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
