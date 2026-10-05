"""状況判定の規範行から派生ケースを展開する。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import check_expander_dependencies as dependency_checker
import representative_selection

ROOT = Path(__file__).resolve().parents[1]
EXPANDER_ID = "state-transition-cases"


class CaseExpansionError(ValueError):
    """規範行からケースを導出できない場合を表す。"""


def _read_document(root: Path, relative: PurePosixPath) -> dict[str, Any]:
    """宣言された入力資産をJSONとして読む。

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
) -> tuple[PurePosixPath, dict[str, Any]]:
    """構造キーから宣言済み入力を一意に見つける。

    Args:
        documents: 許可された入力資産。
        key: 当該資産を識別するトップレベルキー。

    Returns:
        資産の相対パスと内容。
    """
    matches = [(path, document) for path, document in documents if key in document]
    if len(matches) != 1:
        raise CaseExpansionError(f"入力資産を一意に識別できない: {key}")
    return matches[0]


def _row_bound_value_exceptions(
    policy: dict[str, Any],
    descriptor: dict[str, Any],
    rows: list[dict[str, Any]],
    values_by_axis: dict[str, list[Any]],
) -> tuple[dict[str, list[Any]], dict[str, dict[str, set[str]]]]:
    """根拠付き宣言から、軸値の行束縛と例外を検証して取得する。"""
    if (
        set(policy) != {"schemaVersion", "policyId", "rowBoundAxes"}
        or type(policy.get("schemaVersion")) is not int
        or policy["schemaVersion"] != 1
        or not isinstance(policy.get("policyId"), str)
        or not policy["policyId"]
        or not isinstance(policy.get("rowBoundAxes"), list)
        or not policy["rowBoundAxes"]
    ):
        raise CaseExpansionError("行束縛宣言の形式または版が不正")
    descriptor_axes = {
        axis["axisId"]: axis for axis in descriptor["stateTransitionAxes"]
        if isinstance(axis, dict) and isinstance(axis.get("axisId"), str)
    }
    constrained_axes = set().union(
        *(
            representative_selection.predicate_axes(row["precondition"])
            for row in rows
            if isinstance(row, dict)
        )
    )
    exceptions: dict[str, list[Any]] = {}
    value_row_bindings: dict[str, dict[str, set[str]]] = {}
    rows_by_id = {
        row["resultId"]: row for row in rows
        if isinstance(row, dict) and isinstance(row.get("resultId"), str)
    }
    for entry in policy["rowBoundAxes"]:
        required_fields = {"axisId", "sourceClauseIds", "unboundValues", "reason"}
        if not isinstance(entry, dict) or not (
            required_fields <= set(entry)
            and set(entry) <= required_fields | {"valueRowBindings"}
        ):
            raise CaseExpansionError("行束縛軸の宣言が不正")
        axis_id = entry["axisId"]
        clauses = entry["sourceClauseIds"]
        unbound = entry["unboundValues"]
        if (
            not isinstance(axis_id, str)
            or axis_id in exceptions
            or (axis_id not in constrained_axes and "valueRowBindings" not in entry)
            or axis_id not in values_by_axis
            or not isinstance(clauses, list)
            or not clauses
            or not all(isinstance(clause, str) and clause for clause in clauses)
            or len(clauses) != len(set(clauses))
            or not isinstance(unbound, list)
            or not isinstance(entry["reason"], str)
            or not entry["reason"]
        ):
            raise CaseExpansionError("行束縛軸のID・根拠または例外が不正")
        axis = descriptor_axes[axis_id]
        sources = {axis.get("sourceClauseId"), *axis.get("supportingClauseIds", [])}
        if not set(clauses) <= sources:
            raise CaseExpansionError(f"行束縛軸の根拠がdescriptorと不一致: {axis_id}")
        identities = [
            json.dumps(value, sort_keys=True, ensure_ascii=False) for value in unbound
        ]
        if len(identities) != len(set(identities)) or any(
            not any(
                type(value) is type(candidate) and value == candidate
                for candidate in values_by_axis[axis_id]
            )
            for value in unbound
        ):
            raise CaseExpansionError(f"行束縛軸の例外値が不正: {axis_id}")
        exceptions[axis_id] = unbound
        if "valueRowBindings" in entry:
            bindings = entry["valueRowBindings"]
            if not isinstance(bindings, list) or not bindings:
                raise CaseExpansionError(f"軸値の行束縛が空または不正: {axis_id}")
            by_value: dict[str, set[str]] = {}
            for binding in bindings:
                if not isinstance(binding, dict) or set(binding) != {"value", "resultIds"}:
                    raise CaseExpansionError(f"軸値の行束縛が不正: {axis_id}")
                value = binding["value"]
                identity = json.dumps(value, sort_keys=True, ensure_ascii=False)
                result_ids = binding["resultIds"]
                if (
                    identity in by_value
                    or not any(
                        type(value) is type(candidate) and value == candidate
                        for candidate in values_by_axis[axis_id]
                    )
                    or not isinstance(result_ids, list)
                    or not result_ids
                    or not all(isinstance(result_id, str) and result_id in rows_by_id
                               for result_id in result_ids)
                    or len(result_ids) != len(set(result_ids))
                ):
                    raise CaseExpansionError(f"軸値と規範行の束縛が不正: {axis_id}")
                by_value[identity] = set(result_ids)
            value_row_bindings[axis_id] = by_value
    return exceptions, value_row_bindings


def _expand_from_declared_inputs(
    root: Path, rule: dependency_checker.ExpanderRule, limit: int, mode: str
) -> list[dict[str, Any]]:
    """許可入力だけを読み、行参照から状況判定ケースを作る。

    Args:
        root: リポジトリルート。
        rule: 資産側の展開器依存宣言。
        limit: 今回対象とする規範行数。
        mode: 代表値または入力座標被覆の展開方式。

    Returns:
        規範行から導いたケース。
    """
    documents = [
        (path, _read_document(root, path)) for path in rule.allowed_read_paths
    ]
    _, descriptor = _document_by_key(documents, "stateTransitionAxes")
    seed_path, vocabulary = _document_by_key(documents, "axes")
    _, manifest = _document_by_key(documents, "seeds")
    _, contract = _document_by_key(documents, "matrixRows")
    _, register = _document_by_key(documents, "branches")
    _, selection_policy = _document_by_key(documents, "predicateEvaluation")
    _, row_binding_policy = _document_by_key(documents, "rowBoundAxes")
    representative_selection.validate_policy(selection_policy)

    binding = contract.get("inputAxesDescriptor")
    if not isinstance(binding, dict) or binding.get("digest") != descriptor.get("digest"):
        raise CaseExpansionError("契約と入力軸descriptorの識別値が一致しない")
    seed_bindings = manifest.get("seeds")
    if not isinstance(seed_bindings, list) or not any(
        isinstance(item, dict)
        and item.get("path") == seed_path.as_posix()
        and item.get("vocabularyId") == vocabulary.get("vocabularyId")
        for item in seed_bindings
    ):
        raise CaseExpansionError("語彙manifestとseedの対応が一致しない")
    axes = descriptor.get("stateTransitionAxes")
    if not isinstance(axes, list):
        raise CaseExpansionError("入力軸descriptorに状況判定軸がない")
    values_by_axis = representative_selection.axis_values(descriptor, ("stateTransitionAxes",))
    vocabulary_axes = vocabulary.get("axes")
    if not isinstance(vocabulary_axes, list):
        raise CaseExpansionError("語彙seedに軸がない")
    result_ids = {
        entry.get("id")
        for axis in vocabulary_axes
        if isinstance(axis, dict) and isinstance(axis.get("entries"), list)
        for entry in axis["entries"]
        if isinstance(entry, dict)
    }
    branches = register.get("branches")
    if (
        not isinstance(branches, list)
        or register.get("branchCount") != len(branches)
        or len({item.get("branchId") for item in branches if isinstance(item, dict)})
        != len(branches)
    ):
        raise CaseExpansionError("条文分岐台帳の件数またはIDが不正")

    mappings = contract.get("mustOperationCoverage", {}).get("mappings", [])
    per_pitch = [
        mapping
        for mapping in mappings
        if isinstance(mapping, dict) and mapping.get("operationType") == "per-pitch-input"
    ]
    if len(per_pitch) != 1 or not isinstance(per_pitch[0].get("rowRefs"), list):
        raise CaseExpansionError("毎球入力の行参照を一意に取得できない")
    rows = contract.get("matrixRows")
    if not isinstance(rows, list):
        raise CaseExpansionError("状況判定の規範行がない")
    references = per_pitch[0]["rowRefs"]
    if limit < 1 or limit > len(references):
        raise CaseExpansionError("出力件数が規範行参照の範囲外")
    if mode not in ("representative", "coverage"):
        raise CaseExpansionError(f"未対応の展開方式: {mode}")

    cases: list[dict[str, Any]] = []
    for reference in references[:limit]:
        if not isinstance(reference, dict) or reference.get("layer") != "matrixRows":
            raise CaseExpansionError("毎球入力の参照層が不正")
        coordinate = reference.get("coordinate")
        if not isinstance(coordinate, dict):
            raise CaseExpansionError("規範行の入力座標が不正")
        matches = [
            row
            for row in rows
            if isinstance(row, dict)
            and all(row.get(field) == value for field, value in coordinate.items())
        ]
        if len(matches) != 1:
            raise CaseExpansionError("行参照が規範行を一意に指していない")
        row = matches[0]
        result_id = coordinate.get("resultId")
        if result_id not in result_ids:
            raise CaseExpansionError("結果IDが語彙seedに存在しない")
        predicate = coordinate.get("precondition")
        if not isinstance(predicate, dict):
            raise CaseExpansionError("事前条件が述語でない")
        used_axes = representative_selection.predicate_axes(predicate)
        coordinate_axes = [axis_id for axis_id in values_by_axis if axis_id in used_axes]
        axes_coordinate = representative_selection.select_coordinate(
            predicate, values_by_axis, coordinate_axes, selection_policy
        )
        input_coordinate = {
            "eventKind": coordinate["eventKind"],
            "resultId": result_id,
            **axes_coordinate,
        }
        expected = {
            field: copy.deepcopy(value)
            for field, value in row.items()
            if field not in coordinate and field != "remarks"
        }
        identity = json.dumps(
            coordinate, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        case_id = f"ST-MATRIX-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
        cases.append(
            {
                "caseId": case_id,
                "rowRef": copy.deepcopy(reference),
                "inputCoordinate": input_coordinate,
                "expected": expected,
            }
        )
    if mode == "coverage":
        row_bound_exceptions, value_row_bindings = _row_bound_value_exceptions(
            row_binding_policy, descriptor, rows, values_by_axis
        )
        coverage = descriptor.get("inputCoordinateCoverage")
        if not isinstance(coverage, dict) or not isinstance(coverage.get("axisBindings"), list):
            raise CaseExpansionError("入力座標被覆の宣言がない")
        predicate_axes: set[str] = set()
        for binding in coverage["axisBindings"]:
            if not isinstance(binding, dict):
                raise CaseExpansionError("入力座標軸の割当が不正")
            for row_binding in binding.get("rowBindings", []):
                if (
                    isinstance(row_binding, dict)
                    and "matrixRows" in row_binding.get("rowLayers", [])
                    and row_binding.get("naturalKeyRole") == "predicate-axis"
                ):
                    predicate_axes.update(binding.get("axisIds", []))
        next_row = 0
        representatives = cases[:limit]
        for axis_id in values_by_axis:
            if axis_id not in predicate_axes:
                continue
            if (
                axis_id.startswith("event.perPitch.")
                and axis_id not in value_row_bindings
                and not any(
                    axis_id in representative_selection.predicate_axes(
                        base["rowRef"]["coordinate"]["precondition"]
                    )
                    for base in cases[:limit]
                )
            ):
                continue
            for value in values_by_axis[axis_id]:
                permitted_rows = value_row_bindings.get(axis_id, {}).get(
                    json.dumps(value, sort_keys=True, ensure_ascii=False)
                )
                if axis_id in value_row_bindings and permitted_rows is None:
                    continue
                if any(
                    base["inputCoordinate"].get(axis_id) == value
                    for base in representatives
                ):
                    continue
                for offset in range(limit):
                    base = representatives[(next_row + offset) % limit]
                    if permitted_rows is not None and (
                        base["rowRef"]["coordinate"]["resultId"] not in permitted_rows
                    ):
                        continue
                    if (
                        axis_id in row_bound_exceptions
                        and axis_id not in value_row_bindings
                        and not any(
                            type(value) is type(item) and value == item
                            for item in row_bound_exceptions[axis_id]
                        )
                        and axis_id not in representative_selection.predicate_axes(
                            base["rowRef"]["coordinate"]["precondition"]
                        )
                    ):
                        continue
                    coordinate = copy.deepcopy(base["inputCoordinate"])
                    coordinate[axis_id] = copy.deepcopy(value)
                    if representative_selection.predicate_holds(
                        base["rowRef"]["coordinate"]["precondition"], coordinate
                    ):
                        identity = json.dumps(
                            [base["caseId"], axis_id, value],
                            sort_keys=True,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        cases.append(
                            {
                                **copy.deepcopy(base),
                                "caseId": "ST-COVERAGE-"
                                + hashlib.sha256(identity.encode()).hexdigest()[:16],
                                "inputCoordinate": coordinate,
                            }
                        )
                        next_row = (next_row + offset + 1) % limit
                        break
    return cases


def expand_traced(
    root: Path, *, limit: int = 1, mode: str = "representative"
) -> tuple[list[dict[str, Any]], dependency_checker.ExpanderTrace]:
    """資産側allowlistで読み取りを監査しながらケースを展開する。

    Args:
        root: リポジトリルート。
        limit: 今回出力する最大件数。
        mode: 代表値または入力座標被覆の展開方式。

    Returns:
        派生ケースと観測した読み取りの証跡。
    """
    policy = dependency_checker.load_policy(root)
    rule = policy.expanders.get(EXPANDER_ID)
    if rule is None:
        raise CaseExpansionError("状況判定展開器の宣言がない")
    return dependency_checker.trace_expander_file_reads(
        root,
        policy,
        EXPANDER_ID,
        lambda: _expand_from_declared_inputs(root, rule, limit, mode),
    )


def main(argv: list[str] | None = None) -> int:
    """CLIで追跡済みの派生ケースを表示する。

    Args:
        argv: コマンドライン引数。

    Returns:
        成功なら0、それ以外は1。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--mode", choices=("representative", "coverage"), default="representative")
    args = parser.parse_args(argv)
    try:
        cases, _ = expand_traced(args.root.resolve(), limit=args.limit, mode=args.mode)
    except (
        CaseExpansionError,
        dependency_checker.ExpanderDependencyError,
        representative_selection.RepresentativeSelectionError,
    ) as error:
        print(f"state-transition-case-expander: 違反: {error}", file=sys.stderr)
        return 1
    print(json.dumps(cases, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
