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
        if row["targetKind"] == "none" and (
            row["guaranteeMode"] != "full-equality"
            or not _all_unchanged(row["stateEffect"]["stateFields"])
            or not _all_unchanged(row["stateEffect"]["scoreboard"])
        ):
            _fail("HISTORY_NONE_EFFECT", label)


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
    projected = [
        arg for arg in args
        if not (
            isinstance(arg, dict)
            and arg.get("op") == "eq"
            and arg.get("axisId") == "gameEnd.satisfiedColdTierCount"
        )
    ]
    if len(args) - len(projected) != 1:
        raise BranchRowMappingError("終了判定行の成立段数軸が一意でない")
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
