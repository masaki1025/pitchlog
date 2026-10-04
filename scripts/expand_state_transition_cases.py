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


def _expand_from_declared_inputs(
    root: Path, rule: dependency_checker.ExpanderRule, limit: int
) -> list[dict[str, Any]]:
    """許可入力だけを読み、行参照から状況判定ケースを作る。

    Args:
        root: リポジトリルート。
        rule: 資産側の展開器依存宣言。
        limit: 今回出力する最大件数。

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
    return cases


def expand_traced(
    root: Path, *, limit: int = 1
) -> tuple[list[dict[str, Any]], dependency_checker.ExpanderTrace]:
    """資産側allowlistで読み取りを監査しながらケースを展開する。

    Args:
        root: リポジトリルート。
        limit: 今回出力する最大件数。

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
        lambda: _expand_from_declared_inputs(root, rule, limit),
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
    args = parser.parse_args(argv)
    try:
        cases, _ = expand_traced(args.root.resolve(), limit=args.limit)
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
