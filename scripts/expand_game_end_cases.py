"""終了判定の規範行から派生ケースを展開する。"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import check_expander_dependencies as dependency_checker
import representative_selection

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


def _predicate_holds(predicate: dict[str, Any], coordinate: dict[str, Any]) -> bool:
    """具体的な座標が終了判定の述語を満たすか判定する。

    Args:
        predicate: 終了判定行の事前条件。
        coordinate: 候補となる入力座標。

    Returns:
        述語の真偽。
    """
    return representative_selection.predicate_holds(predicate, coordinate)


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
    selection_policy = _document_by_key(documents, "predicateEvaluation")
    representative_selection.validate_policy(selection_policy)
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
    values_by_axis = representative_selection.axis_values(
        descriptor, ("gameEndAxes", "stateTransitionAxes")
    )
    used_axes = set().union(
        *(representative_selection.predicate_axes(row["precondition"]) for row in rows)
    )
    axis_order = [axis_id for axis_id in values_by_axis if axis_id in used_axes]
    if len(axis_order) != len(used_axes):
        raise CaseExpansionError("終了判定行に未宣言の軸がある")

    cases: list[dict[str, Any]] = []
    for row in rows[:limit]:
        branch_id = row["branchId"]
        branch = branch_by_id.get(branch_id)
        if branch is None or row["sourceClauseIds"] != branch.get("sourceClauseIds"):
            raise CaseExpansionError(f"行と条文分岐台帳の対応が不正: {branch_id}")
        input_coordinate = representative_selection.select_coordinate(
            row["precondition"], values_by_axis, axis_order, selection_policy
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


def _expand_coverage_from_declared_inputs(
    root: Path, rule: dependency_checker.ExpanderRule
) -> list[dict[str, Any]]:
    """既存4分岐を保持し、コールド行の状態・イベント代表を追加する。"""
    documents = [(path, _read_document(root, path)) for path in rule.allowed_read_paths]
    descriptor = _document_by_key(documents, "gameEndAxes")
    contract = _document_by_key(documents, "decisionRows")
    policy = _document_by_key(documents, "predicateEvaluation")
    values_by_axis = representative_selection.axis_values(
        descriptor, ("gameEndAxes", "stateTransitionAxes")
    )
    base_cases = _expand_from_declared_inputs(root, rule, len(contract["decisionRows"]))
    result = list(base_cases[:4])
    for row_index, row in enumerate(contract["decisionRows"]):
        if row["branchId"] == "COLD-08":
            result.append(base_cases[row_index])
        predicate = row["precondition"]
        used = representative_selection.predicate_axes(predicate)
        axes = [
            axis for axis in values_by_axis
            if axis in used or axis.startswith(("state.", "event."))
        ]
        choices: dict[str, list[Any]] = {}
        for axis in axes:
            if not axis.startswith(("state.", "event.")):
                continue
            allowed = []
            for value in values_by_axis[axis]:
                constraint = {"op": "eq", "axisId": axis, "value": value}
                try:
                    representative_selection.select_coordinate(
                        {"op": "and", "args": [predicate, constraint]},
                        values_by_axis, axes, policy,
                    )
                except representative_selection.RepresentativeSelectionError:
                    continue
                allowed.append(value)
            if not allowed:
                raise CaseExpansionError(f"行が状態・イベント軸に到達できない: {axis}")
            choices[axis] = allowed
        for index in range(max(map(len, choices.values()))):
            constraints = [
                {"op": "eq", "axisId": axis, "value": values[index % len(values)]}
                for axis, values in choices.items()
            ]
            coordinate = representative_selection.select_coordinate(
                {"op": "and", "args": [predicate, *constraints]},
                values_by_axis, axes, policy,
            )
            result.append(
                {
                    "caseId": f"GE-{row['branchId']}-COVERAGE-{index + 1:03d}",
                    "branchId": row["branchId"],
                    "rowRef": {
                        "layer": "decisionRows",
                        "coordinate": {"branchId": row["branchId"]},
                    },
                    "inputCoordinate": coordinate,
                    "decision": copy.deepcopy(row["decision"]),
                }
            )
    return result


def expand_coverage_traced(
    root: Path,
) -> tuple[list[dict[str, Any]], dependency_checker.ExpanderTrace]:
    """追加代表ケースを既存のallowlist監査下で展開する。"""
    policy = dependency_checker.load_policy(root)
    if EXPANDER_ID not in policy.expanders:
        raise CaseExpansionError("終了判定展開器の依存宣言がない")
    rule = policy.expanders[EXPANDER_ID]
    return dependency_checker.trace_expander_file_reads(
        root, policy, EXPANDER_ID,
        lambda: _expand_coverage_from_declared_inputs(root, rule),
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
    except (
        CaseExpansionError,
        dependency_checker.ExpanderDependencyError,
        representative_selection.RepresentativeSelectionError,
    ) as error:
        print(f"game-end-case-expander: 違反: {error}", file=sys.stderr)
        return 1
    print(json.dumps(cases, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
