"""終了判定の規範行から派生ケースを展開する。"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import check_expander_dependencies as dependency_checker

ROOT = Path(__file__).resolve().parents[1]
EXPANDER_ID = "game-end-cases"


class CaseExpansionError(ValueError):
    """終了判定の規範行からケースを導出できない場合を表す。"""


def _read_document(root: Path, relative: PurePosixPath) -> dict[str, Any]:
    """宣言された入力資産をJSONオブジェクトとして読む。

    Args:
        root: リポジトリルート。
        relative: 宣言済みの相対パス。

    Returns:
        JSONオブジェクト。
    """
    document = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise CaseExpansionError(f"JSONオブジェクトでない: {relative}")
    return document


def _document_by_key(
    documents: list[tuple[PurePosixPath, dict[str, Any]]], key: str
) -> dict[str, Any]:
    """宣言済み入力を構造キーから一意に取得する。

    Args:
        documents: 宣言済みの入力資産。
        key: 識別に使うトップレベルキー。

    Returns:
        一意の入力資産。
    """
    matches = [document for _, document in documents if key in document]
    if len(matches) != 1:
        raise CaseExpansionError(f"入力資産を一意に識別できない: {key}")
    return matches[0]


def _predicate_axes(predicate: dict[str, Any]) -> set[str]:
    """述語が参照する軸IDを集める。

    Args:
        predicate: 終了判定行の事前条件。

    Returns:
        参照する軸IDの集合。
    """
    if predicate.get("op") == "eq":
        axis_id = predicate.get("axisId")
        if not isinstance(axis_id, str):
            raise CaseExpansionError("等値述語の軸IDが不正")
        return {axis_id}
    args = predicate.get("args")
    if not isinstance(args, list) or not args or not all(isinstance(arg, dict) for arg in args):
        raise CaseExpansionError("述語の引数が不正")
    return set().union(*(_predicate_axes(arg) for arg in args))


def _positive_equalities(predicate: dict[str, Any]) -> dict[str, Any]:
    """連言の正の等値条件だけを固定値として抽出する。

    Args:
        predicate: 終了判定行の事前条件。

    Returns:
        正の等値条件により固定された軸値。
    """
    operation = predicate.get("op")
    if operation == "eq":
        return {predicate["axisId"]: copy.deepcopy(predicate["value"])}
    if operation in ("not", "or"):
        return {}
    if operation != "and":
        raise CaseExpansionError(f"未対応の述語演算子: {operation}")
    fixed: dict[str, Any] = {}
    for child in predicate["args"]:
        for axis_id, value in _positive_equalities(child).items():
            if axis_id in fixed and fixed[axis_id] != value:
                raise CaseExpansionError(f"事前条件の固定値が矛盾する: {axis_id}")
            fixed[axis_id] = value
    return fixed


def _predicate_holds(predicate: dict[str, Any], coordinate: dict[str, Any]) -> bool:
    """具体的な座標が終了判定の述語を満たすか判定する。

    Args:
        predicate: 終了判定行の事前条件。
        coordinate: 候補となる入力座標。

    Returns:
        述語の真偽。
    """
    operation = predicate.get("op")
    if operation == "eq":
        actual = coordinate[predicate["axisId"]]
        expected = predicate["value"]
        return type(actual) is type(expected) and actual == expected
    args = predicate["args"]
    if operation == "and":
        return all(_predicate_holds(arg, coordinate) for arg in args)
    if operation == "or":
        return any(_predicate_holds(arg, coordinate) for arg in args)
    if operation == "not" and len(args) == 1:
        return not _predicate_holds(args[0], coordinate)
    raise CaseExpansionError(f"未対応の述語演算子: {operation}")


def _axis_values(descriptor: dict[str, Any]) -> dict[str, list[Any]]:
    """終了判定で使える軸の値域をdescriptorから取得する。

    Args:
        descriptor: 入力軸descriptor。

    Returns:
        軸IDごとの閉じた値域。
    """
    values: dict[str, list[Any]] = {}
    for group in ("gameEndAxes", "stateTransitionAxes"):
        axes = descriptor.get(group)
        if not isinstance(axes, list):
            raise CaseExpansionError(f"入力軸descriptorの軸群が不正: {group}")
        for axis in axes:
            if not isinstance(axis, dict) or not isinstance(axis.get("axisId"), str):
                raise CaseExpansionError("入力軸descriptorの軸が不正")
            axis_id = axis["axisId"]
            classification = axis.get("classification")
            if classification == "boundary-partition":
                field = "boundaryValues"
            elif classification == "finite-enumerable":
                field = "values"
            else:
                raise CaseExpansionError(f"入力軸descriptorの分類が不正: {axis_id}")
            candidates = axis.get(field)
            if axis_id in values or not isinstance(candidates, list) or not candidates:
                raise CaseExpansionError(f"入力軸descriptorの値域が不正: {axis_id}")
            values[axis_id] = candidates
    return values


def _representative_coordinate(
    predicate: dict[str, Any],
    values_by_axis: dict[str, list[Any]],
    axis_order: list[str],
) -> dict[str, Any]:
    """descriptor順の境界値から述語を満たす代表座標を選ぶ。

    Args:
        predicate: 終了判定行の事前条件。
        values_by_axis: descriptorの軸値域。
        axis_order: 現行行群が参照する軸の順序。

    Returns:
        全対象軸の具体的な入力座標。
    """
    fixed = _positive_equalities(predicate)
    predicate_axes = _predicate_axes(predicate)
    if not predicate_axes <= set(values_by_axis):
        raise CaseExpansionError("事前条件に未宣言の軸がある")
    for axis_id, value in fixed.items():
        if not any(
            type(value) is type(candidate) and value == candidate
            for candidate in values_by_axis[axis_id]
        ):
            raise CaseExpansionError(f"事前条件の値がdescriptor外: {axis_id}")
    coordinate = {axis_id: copy.deepcopy(values_by_axis[axis_id][0]) for axis_id in axis_order}
    coordinate.update(fixed)
    free_axes = [axis_id for axis_id in axis_order if axis_id in predicate_axes - fixed.keys()]
    for choice in itertools.product(*(values_by_axis[axis_id] for axis_id in free_axes)):
        candidate = {**coordinate, **dict(zip(free_axes, choice, strict=True))}
        if _predicate_holds(predicate, candidate):
            return candidate
    raise CaseExpansionError("事前条件を満たす代表座標がdescriptor内にない")


def _expand_from_declared_inputs(
    root: Path, rule: dependency_checker.ExpanderRule, limit: int
) -> list[dict[str, Any]]:
    """宣言済み入力だけから終了判定ケースを作る。

    Args:
        root: リポジトリルート。
        rule: 資産側の展開器依存宣言。
        limit: 今回出力する最大件数。

    Returns:
        規範行から導いた終了判定ケース。
    """
    documents = [(path, _read_document(root, path)) for path in rule.allowed_read_paths]
    descriptor = _document_by_key(documents, "gameEndAxes")
    contract = _document_by_key(documents, "decisionRows")
    register = _document_by_key(documents, "branches")
    binding = contract.get("inputAxesDescriptor")
    if not isinstance(binding, dict) or binding.get("digest") != descriptor.get("digest"):
        raise CaseExpansionError("契約と入力軸descriptorの識別値が一致しない")
    branches = register.get("branches")
    if not isinstance(branches, list) or register.get("branchCount") != len(branches):
        raise CaseExpansionError("条文分岐台帳の件数が不正")
    branch_by_id = {
        item["branchId"]: item
        for item in branches
        if isinstance(item, dict) and isinstance(item.get("branchId"), str)
    }
    if len(branch_by_id) != len(branches):
        raise CaseExpansionError("条文分岐台帳の分岐IDが重複または不正")
    rows = contract.get("decisionRows")
    if not isinstance(rows, list) or limit < 1 or limit > len(rows):
        raise CaseExpansionError("出力件数が終了判定行の範囲外")
    if not all(isinstance(row, dict) and isinstance(row.get("branchId"), str) for row in rows):
        raise CaseExpansionError("終了判定行の分岐IDが不正")
    if len({row["branchId"] for row in rows}) != len(rows):
        raise CaseExpansionError("終了判定行の分岐IDが重複または不正")
    values_by_axis = _axis_values(descriptor)
    used_axes = set().union(*(_predicate_axes(row["precondition"]) for row in rows))
    axis_order = [axis_id for axis_id in values_by_axis if axis_id in used_axes]
    if len(axis_order) != len(used_axes):
        raise CaseExpansionError("終了判定行に未宣言の軸がある")

    cases: list[dict[str, Any]] = []
    for row in rows[:limit]:
        branch_id = row["branchId"]
        branch = branch_by_id.get(branch_id)
        if branch is None or row["sourceClauseIds"] != branch.get("sourceClauseIds"):
            raise CaseExpansionError(f"行と条文分岐台帳の対応が不正: {branch_id}")
        input_coordinate = _representative_coordinate(
            row["precondition"], values_by_axis, axis_order
        )
        cases.append(
            {
                "caseId": f"GE-{branch_id}",
                "branchId": branch_id,
                "rowRef": {"layer": "decisionRows", "coordinate": {"branchId": branch_id}},
                "inputCoordinate": input_coordinate,
                "decision": copy.deepcopy(row["decision"]),
            }
        )
    return cases


def expand_traced(
    root: Path, *, limit: int = 1
) -> tuple[list[dict[str, Any]], dependency_checker.ExpanderTrace]:
    """資産側allowlistの読み取り監査下で終了判定を展開する。

    Args:
        root: リポジトリルート。
        limit: 今回出力する最大件数。

    Returns:
        派生ケースと観測した読み取りの証跡。
    """
    policy = dependency_checker.load_policy(root)
    if EXPANDER_ID not in policy.expanders:
        raise CaseExpansionError("終了判定展開器の依存宣言がない")
    rule = policy.expanders[EXPANDER_ID]
    return dependency_checker.trace_expander_file_reads(
        root,
        policy,
        EXPANDER_ID,
        lambda: _expand_from_declared_inputs(root, rule, limit),
    )


def main(argv: list[str] | None = None) -> int:
    """CLIで追跡済みの終了判定ケースを表示する。

    Args:
        argv: コマンドライン引数。

    Returns:
        成功なら0、それ以外は1。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        cases, _ = expand_traced(args.root.resolve(), limit=args.limit)
    except (CaseExpansionError, dependency_checker.ExpanderDependencyError) as error:
        print(f"game-end-case-expander: 違反: {error}", file=sys.stderr)
        return 1
    print(json.dumps(cases, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
