"""状況判定契約schemaの構造を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Mapping, Set
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/state_transition_contract_schema_v1.json"
)
DESCRIPTOR_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/input_axes_descriptor_v1.json"
)
DEFAULT_VOCABULARY_IDS_BY_SEED = {
    "batting_results": frozenset({"single"}),
}


class ReferenceConstraintError(ValueError):
    """状況判定契約の参照制約違反を表す。"""


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_CHECKER_PATH)
schema_checker = _load_module(
    "state_transition_contract_descriptor_checker", DESCRIPTOR_CHECKER_PATH
)


def _load_object(path: Path) -> dict[str, Any]:
    """JSON objectを読み込む。

    Args:
        path: 読み込むJSONファイル。

    Returns:
        読み込んだJSON object。
    """
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _schema() -> dict[str, Any]:
    """状況判定契約schemaを返す。"""
    return _load_object(SCHEMA_PATH)


def _descriptor() -> dict[str, Any]:
    """入力軸descriptorを返す。"""
    return _load_object(DESCRIPTOR_PATH)


def _stat_flag_values() -> dict[str, bool]:
    """schemaが宣言する全成績フラグのfalse値を返す。"""
    stat_flags = _schema()["$defs"]["statFlags"]
    properties = stat_flags["properties"]
    assert isinstance(properties, dict)
    return dict.fromkeys(properties, False)


def _minimal_contract() -> dict[str, Any]:
    """構造・参照検査を通る最小の状況判定契約を返す。"""
    descriptor = _descriptor()
    matrix_precondition = {"op": "eq", "axisId": "state.outs", "value": 0}
    matrix_row = {
        "eventKind": "batting-result",
        "resultId": "single",
        "precondition": matrix_precondition,
        "countEffect": {
            "strikes": {"kind": "unchanged"},
            "balls": {"kind": "unchanged"},
        },
        "plateAppearanceEnded": False,
        "batterDestination": {"kind": "continue"},
        "runnerDefaultAdvance": {
            "first": {"modality": "hold", "destination": None},
            "second": {"modality": "hold", "destination": None},
            "third": {"modality": "hold", "destination": None},
        },
        "outEffect": {"count": 0, "targets": []},
        "statFlags": _stat_flag_values(),
        "remarks": "基準行",
    }
    operation_precondition = {"op": "eq", "axisId": "state.outs", "value": 0}
    operation_row = {
        "operationKind": "substitution",
        "payloadShape": {"type": "object", "additionalProperties": False},
        "precondition": operation_precondition,
    }
    undo_precondition = {"op": "eq", "axisId": "history.depth", "value": 1}
    undo_row = {
        "targetKind": "confirmed-play",
        "precondition": undo_precondition,
    }
    return {
        "schemaVersion": 1,
        "version": "state_transition_contract_v1",
        "calculation": "state-transition",
        "inputAxesDescriptor": {
            "descriptorId": descriptor["descriptorId"],
            "version": descriptor["version"],
            "digest": descriptor["digest"],
        },
        "matrixRows": [matrix_row],
        "operationRows": [operation_row],
        "undoRows": [undo_row],
        "mustOperationCoverage": {},
        "requiredSet": {},
        "cases": [
            {
                "rowRef": {
                    "layer": "matrixRows",
                    "coordinate": {
                        "eventKind": matrix_row["eventKind"],
                        "resultId": matrix_row["resultId"],
                        "precondition": copy.deepcopy(matrix_precondition),
                    },
                }
            },
            {
                "rowRef": {
                    "layer": "operationRows",
                    "coordinate": copy.deepcopy(operation_row),
                }
            },
            {
                "rowRef": {
                    "layer": "undoRows",
                    "coordinate": copy.deepcopy(undo_row),
                }
            },
        ],
    }


def _required_object(value: object, label: str) -> dict[str, Any]:
    """参照制約宣言に必要なobjectを返す。

    Args:
        value: 検査対象の値。
        label: エラー表示用の位置。

    Returns:
        検査済みのobject。

    Raises:
        ReferenceConstraintError: 値がobjectでない場合。
    """
    if not isinstance(value, dict):
        raise ReferenceConstraintError(f"{label}がobjectでない")
    return value


def _required_string(value: object, label: str) -> str:
    """参照制約宣言に必要な文字列を返す。

    Args:
        value: 検査対象の値。
        label: エラー表示用の位置。

    Returns:
        検査済みの空でない文字列。

    Raises:
        ReferenceConstraintError: 値が空でない文字列でない場合。
    """
    if not isinstance(value, str) or not value:
        raise ReferenceConstraintError(f"{label}が空でない文字列でない")
    return value


def _annotated_collections(
    schema: Mapping[str, Any], annotation: str
) -> tuple[str, ...]:
    """指定annotationを持つ配列名をschemaから導出する。

    Args:
        schema: 状況判定契約schema。
        annotation: 参照制約宣言が指定したannotation名。

    Returns:
        schema内の出現順に並べた配列名。

    Raises:
        ReferenceConstraintError: 対象配列を導出できない場合。
    """
    properties = _required_object(schema.get("properties"), "schema.properties")
    collections = tuple(
        name
        for name, property_schema in properties.items()
        if isinstance(property_schema, dict) and property_schema.get(annotation) is True
    )
    if not collections:
        raise ReferenceConstraintError(
            f"参照対象collectionをannotationから導出できない: {annotation}"
        )
    return collections


def _coordinate_fields(
    schema: Mapping[str, Any], collection: str, annotation: str
) -> tuple[str, ...]:
    """規範行層の入力座標フィールドをschemaから返す。

    Args:
        schema: 状況判定契約schema。
        collection: 規範行層のプロパティ名。
        annotation: 入力座標フィールドを保持するannotation名。

    Returns:
        宣言順の入力座標フィールド。

    Raises:
        ReferenceConstraintError: 宣言が空、不正、または重複している場合。
    """
    properties = _required_object(schema.get("properties"), "schema.properties")
    collection_schema = _required_object(
        properties.get(collection), f"schema.properties.{collection}"
    )
    fields = collection_schema.get(annotation)
    if (
        not isinstance(fields, list)
        or not fields
        or not all(isinstance(field, str) and field for field in fields)
        or len(fields) != len(set(fields))
    ):
        raise ReferenceConstraintError(
            f"入力座標フィールド宣言が不正: collection={collection}"
        )
    return tuple(fields)


def _predicate_leaves(predicate: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Predicate木の停止節を出現順に返す。

    Args:
        predicate: schema検証済みのPredicate。

    Returns:
        `axisId`を持つ停止節。
    """
    args = predicate.get("args")
    if isinstance(args, list):
        return tuple(
            leaf
            for child in args
            for leaf in _predicate_leaves(_required_object(child, "Predicate.args[]"))
        )
    return (predicate,)


def _sync_case_coordinate(contract: dict[str, Any], layer: str) -> None:
    """指定層のcase参照を先頭の規範行の入力座標へ同期する。

    Args:
        contract: 更新する状況判定契約。
        layer: 同期する規範行層。
    """
    schema = _schema()
    row_rule = schema["x-pitchlog-reference-constraints"]["rowIdentity"]
    annotation = row_rule["coordinateFieldsAnnotation"]
    fields = _coordinate_fields(schema, layer, annotation)
    row = contract[layer][0]
    case = next(
        case for case in contract["cases"] if case["rowRef"]["layer"] == layer
    )
    case["rowRef"]["coordinate"] = {
        field: copy.deepcopy(row[field]) for field in fields
    }


def _validate_references(
    contract: Mapping[str, Any],
    vocabulary_ids_by_seed: Mapping[str, Set[str]] | None,
) -> None:
    """schema資産の宣言に従って参照制約を検証する。

    Args:
        contract: 検証する状況判定契約。
        vocabulary_ids_by_seed: 解決済み語彙シードごとのID集合。共有manifestを
            解決できない場合はNone。

    Raises:
        ReferenceConstraintError: IDの重複、参照切れ、語彙参照の不一致、
            または語彙manifest未解決がある場合。
    """
    schema = _schema()
    constraints = _required_object(
        schema.get("x-pitchlog-reference-constraints"),
        "schema.x-pitchlog-reference-constraints",
    )

    row_rule = _required_object(constraints.get("rowIdentity"), "rowIdentity")
    row_annotation = _required_string(
        row_rule.get("collectionAnnotation"), "rowIdentity.collectionAnnotation"
    )
    coordinate_annotation = _required_string(
        row_rule.get("coordinateFieldsAnnotation"),
        "rowIdentity.coordinateFieldsAnnotation",
    )
    canonicalization = _required_string(
        row_rule.get("canonicalization"), "rowIdentity.canonicalization"
    )
    if canonicalization != "RFC8785":
        raise ReferenceConstraintError(
            f"未対応の入力座標正規化方式: {canonicalization}"
        )
    maximum_occurrences = row_rule.get("maximumOccurrences")
    if not isinstance(maximum_occurrences, int) or maximum_occurrences < 1:
        raise ReferenceConstraintError("rowIdentity.maximumOccurrencesが正の整数でない")

    row_coordinates = [
        (
            collection,
            schema_checker.canonicalize_json(
                {
                    field: row[field]
                    for field in _coordinate_fields(
                        schema, collection, coordinate_annotation
                    )
                }
            ),
        )
        for collection in _annotated_collections(schema, row_annotation)
        for row in contract[collection]
    ]
    occurrences = Counter(row_coordinates)
    duplicates = sorted(
        (layer, coordinate.decode("utf-8"))
        for (layer, coordinate), count in occurrences.items()
        if count > maximum_occurrences
    )
    if duplicates:
        raise ReferenceConstraintError(f"規範行の入力座標が重複: {duplicates!r}")

    case_rule = _required_object(constraints.get("caseResolution"), "caseResolution")
    case_collection = _required_string(
        case_rule.get("collection"), "caseResolution.collection"
    )
    case_reference_field = _required_string(
        case_rule.get("referenceField"), "caseResolution.referenceField"
    )
    case_layer_field = _required_string(
        case_rule.get("layerField"), "caseResolution.layerField"
    )
    case_coordinate_field = _required_string(
        case_rule.get("coordinateField"), "caseResolution.coordinateField"
    )
    required_case_matches = case_rule.get("requiredMatchCount")
    if not isinstance(required_case_matches, int) or required_case_matches < 1:
        raise ReferenceConstraintError("caseResolution.requiredMatchCountが正の整数でない")
    for index, case in enumerate(contract[case_collection]):
        row_reference = case[case_reference_field]
        reference_key = (
            row_reference[case_layer_field],
            schema_checker.canonicalize_json(
                row_reference[case_coordinate_field]
            ),
        )
        if occurrences.get(reference_key, 0) != required_case_matches:
            raise ReferenceConstraintError(
                "caseの入力座標参照を必要件数へ解決できない: "
                f"{case_collection}[{index}].{case_reference_field}="
                f"{row_reference!r}"
            )

    vocabulary_rule = _required_object(
        constraints.get("vocabularyResolution"), "vocabularyResolution"
    )
    vocabulary_annotation = _required_string(
        vocabulary_rule.get("collectionAnnotation"),
        "vocabularyResolution.collectionAnnotation",
    )
    vocabulary_reference_field = _required_string(
        vocabulary_rule.get("referenceField"),
        "vocabularyResolution.referenceField",
    )
    required_vocabulary_matches = vocabulary_rule.get("requiredMatchCount")
    if not isinstance(required_vocabulary_matches, int) or required_vocabulary_matches < 1:
        raise ReferenceConstraintError(
            "vocabularyResolution.requiredMatchCountが正の整数でない"
        )
    vocabulary_references = [
        row[vocabulary_reference_field]
        for collection in _annotated_collections(schema, vocabulary_annotation)
        for row in contract[collection]
    ]
    if vocabulary_references and vocabulary_ids_by_seed is None:
        if vocabulary_rule.get("failWhenManifestUnavailable") is True:
            raise ReferenceConstraintError(
                "語彙manifestを解決できないため参照整合を未検査のまま受理できない"
            )
        raise ReferenceConstraintError(
            "語彙manifest未解決時のfail-closed宣言が欠けている"
        )
    if vocabulary_ids_by_seed is None:
        return
    for result_id in vocabulary_references:
        match_count = sum(
            result_id in seed_ids for seed_ids in vocabulary_ids_by_seed.values()
        )
        if match_count != required_vocabulary_matches:
            raise ReferenceConstraintError(
                "語彙IDを宣言済みシードへ必要件数で解決できない: "
                f"resultId={result_id!r}; matches={match_count}"
            )

    predicate_rule = _required_object(
        constraints.get("predicateAxisResolution"), "predicateAxisResolution"
    )
    row_collection = _required_string(
        predicate_rule.get("rowCollection"),
        "predicateAxisResolution.rowCollection",
    )
    predicate_field = _required_string(
        predicate_rule.get("predicateField"),
        "predicateAxisResolution.predicateField",
    )
    predicate_axis_id_field = _required_string(
        predicate_rule.get("axisIdField"),
        "predicateAxisResolution.axisIdField",
    )
    descriptor_axis_id_field = _required_string(
        predicate_rule.get("descriptorAxisIdField"),
        "predicateAxisResolution.descriptorAxisIdField",
    )
    descriptor_classification_field = _required_string(
        predicate_rule.get("descriptorClassificationField"),
        "predicateAxisResolution.descriptorClassificationField",
    )
    descriptor_collections = predicate_rule.get("descriptorCollections")
    if (
        not isinstance(descriptor_collections, list)
        or not descriptor_collections
        or not all(
            isinstance(collection, str) and collection
            for collection in descriptor_collections
        )
    ):
        raise ReferenceConstraintError(
            "predicateAxisResolution.descriptorCollectionsが不正"
        )
    value_fields_by_classification = _required_object(
        predicate_rule.get("descriptorValueFieldsByClassification"),
        "predicateAxisResolution.descriptorValueFieldsByClassification",
    )
    required_axis_matches = predicate_rule.get("requiredMatchCount")
    if not isinstance(required_axis_matches, int) or required_axis_matches < 1:
        raise ReferenceConstraintError(
            "predicateAxisResolution.requiredMatchCountが正の整数でない"
        )

    descriptor = _descriptor()
    axes = [
        axis
        for collection in descriptor_collections
        for axis in descriptor[collection]
    ]
    for row_index, row in enumerate(contract[row_collection]):
        for leaf in _predicate_leaves(row[predicate_field]):
            axis_id = leaf[predicate_axis_id_field]
            matching_axes = [
                axis
                for axis in axes
                if axis[descriptor_axis_id_field] == axis_id
            ]
            if len(matching_axes) != required_axis_matches:
                raise ReferenceConstraintError(
                    "Predicate.axisIdをdescriptorへ必要件数で解決できない: "
                    f"{row_collection}[{row_index}].{predicate_field}; "
                    f"axisId={axis_id!r}; matches={len(matching_axes)}"
                )
            axis = matching_axes[0]
            classification = axis[descriptor_classification_field]
            value_field = value_fields_by_classification.get(classification)
            if not isinstance(value_field, str) or not value_field:
                raise ReferenceConstraintError(
                    "Predicate値域の解決方法が未宣言: "
                    f"axisId={axis_id!r}; classification={classification!r}"
                )
            allowed_values = axis.get(value_field)
            if not isinstance(allowed_values, list) or not allowed_values:
                raise ReferenceConstraintError(
                    f"Predicate値域をdescriptorから解決できない: axisId={axis_id!r}"
                )
            leaf_values = leaf.get("values")
            compared_values = leaf_values if isinstance(leaf_values, list) else [leaf["value"]]
            canonical_allowed_values = {
                schema_checker.canonicalize_json(value) for value in allowed_values
            }
            for value in compared_values:
                if (
                    schema_checker.canonicalize_json(value)
                    not in canonical_allowed_values
                ):
                    raise ReferenceConstraintError(
                        "Predicate値がdescriptorの軸値域に属さない: "
                        f"axisId={axis_id!r}; value={value!r}"
                    )


def _validate_schema(contract: dict[str, Any]) -> None:
    """既存の汎用validatorで状況判定契約schemaを検証する。"""
    schema = _schema()
    schema_checker._validate_instance(contract, schema, schema, "$")


def _validate(
    contract: dict[str, Any],
    vocabulary_ids_by_seed: Mapping[str, Set[str]] | None = (
        DEFAULT_VOCABULARY_IDS_BY_SEED
    ),
) -> None:
    """状況判定契約のschemaと参照制約を検証する。"""
    _validate_schema(contract)
    _validate_references(contract, vocabulary_ids_by_seed)


def test_repository_schema_accepts_the_three_normative_row_layers() -> None:
    """3規範行層と派生層を持つ最小構造を受理する。"""
    schema = _schema()

    assert schema["version"] == SCHEMA_PATH.stem
    assert "decisionRows" not in schema["properties"]
    _validate(_minimal_contract())


def test_schema_binding_matches_the_input_axes_descriptor_identity() -> None:
    """schemaのdescriptor拘束が正本descriptorのidentityと一致する。"""
    schema = _schema()
    descriptor = _descriptor()
    properties = schema["$defs"]["inputAxesDescriptorBinding"]["properties"]

    assert properties["descriptorId"]["const"] == descriptor["descriptorId"]
    assert properties["version"]["const"] == descriptor["version"]
    assert properties["digest"]["const"] == descriptor["digest"]


@pytest.mark.parametrize("missing_layer", ["matrixRows", "operationRows", "undoRows"])
def test_missing_normative_row_layer_is_red(missing_layer: str) -> None:
    """3規範行層のいずれかが欠けた契約を拒否する。"""
    contract = copy.deepcopy(_minimal_contract())
    del contract[missing_layer]

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match=rf"必須キー不足: .*{missing_layer}",
    ):
        _validate(contract)


def test_operation_and_undo_row_internals_remain_open_for_later_steps() -> None:
    """操作行とundo行の後続ステップ向け列を本ステップで閉じない。"""
    contract = _minimal_contract()
    for layer in ("operationRows", "undoRows"):
        contract[layer][0]["futureConstraintField"] = {"notClosedYet": True}

    _validate(contract)


def test_matrix_row_is_closed_to_the_ten_normative_columns() -> None:
    """matrixRowsの行を要件書が定める10列だけに閉じる。"""
    schema = _schema()
    matrix_row_schema = schema["$defs"]["matrixRow"]
    required = matrix_row_schema["required"]
    properties = matrix_row_schema["properties"]

    assert len(required) == 10
    assert set(required) == set(properties)
    assert matrix_row_schema["additionalProperties"] is False
    assert "rowId" not in properties

    contract = _minimal_contract()
    contract["matrixRows"][0]["rowId"] = "matrix.result.single.default"
    with pytest.raises(schema_checker.DescriptorCheckError, match="未知キー: .*rowId"):
        _validate(contract)


def test_decision_rows_belong_to_the_separate_game_end_contract() -> None:
    """終了判定のdecisionRowsを状況判定契約へ混在させない。"""
    contract = _minimal_contract()
    contract["decisionRows"] = []

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="未知キー: .*decisionRows",
    ):
        _validate(contract)


@pytest.mark.parametrize("layer", ["matrixRows", "operationRows", "undoRows"])
def test_duplicate_input_coordinate_in_normative_layer_is_red(layer: str) -> None:
    """同じ規範行層で入力座標を再利用した契約を拒否する。"""
    contract = _minimal_contract()
    duplicate = copy.deepcopy(contract[layer][0])
    if layer == "matrixRows":
        duplicate["remarks"] = "出力列だけが異なる重複行"
    contract[layer].append(duplicate)

    with pytest.raises(ReferenceConstraintError, match="規範行の入力座標が重複"):
        _validate(contract)


def test_case_reference_to_unknown_normative_row_is_red() -> None:
    """実在しない規範行を参照する派生caseを拒否する。"""
    contract = _minimal_contract()
    contract["cases"][0]["rowRef"]["coordinate"]["resultId"] = "missing-result"

    with pytest.raises(
        ReferenceConstraintError,
        match="caseの入力座標参照を必要件数へ解決できない",
    ):
        _validate(contract)


def test_case_reference_is_stable_when_only_output_columns_change() -> None:
    """出力7列の変更では入力座標によるcase参照が変わらない。"""
    contract = _minimal_contract()
    row = contract["matrixRows"][0]
    row["countEffect"] = {
        "strikes": {"kind": "reset"},
        "balls": {"kind": "reset"},
    }
    row["plateAppearanceEnded"] = True
    row["batterDestination"] = {"kind": "reach", "base": 1}
    row["runnerDefaultAdvance"] = {
        "first": {"modality": "optional", "destination": 2},
        "second": {"modality": "optional", "destination": 3},
        "third": {"modality": "optional", "destination": 4},
    }
    row["outEffect"] = {"count": 0, "targets": []}
    row["statFlags"]["安打"] = True
    row["remarks"] = "出力列を更新"

    _validate(contract)


def test_input_coordinate_comparison_uses_canonical_object_order() -> None:
    """JSON objectのキー順が違っても同じ入力座標へ解決する。"""
    contract = _minimal_contract()
    contract["cases"][0]["rowRef"]["coordinate"]["precondition"] = {
        "value": 0,
        "axisId": "state.outs",
        "op": "eq",
    }

    _validate(contract)


def test_unknown_vocabulary_reference_is_red() -> None:
    """どの宣言済み語彙シードにも存在しないresultIdを拒否する。"""
    contract = _minimal_contract()
    contract["matrixRows"][0]["resultId"] = "unknown-result"
    _sync_case_coordinate(contract, "matrixRows")

    with pytest.raises(
        ReferenceConstraintError,
        match="語彙IDを宣言済みシードへ必要件数で解決できない",
    ):
        _validate(contract)


def test_ambiguous_vocabulary_reference_is_red() -> None:
    """複数の宣言済み語彙シードへ解決するresultIdを拒否する。"""
    contract = _minimal_contract()
    duplicate_seed_ids = {
        "batting_results": frozenset({"single"}),
        "secondary_results": frozenset({"single"}),
    }

    with pytest.raises(
        ReferenceConstraintError,
        match=r"resultId='single'; matches=2",
    ):
        _validate(contract, duplicate_seed_ids)


def test_vocabulary_reference_is_red_when_manifest_is_unavailable() -> None:
    """共有manifestを解決できない参照検査を未確認の緑にしない。"""
    contract = _minimal_contract()

    with pytest.raises(
        ReferenceConstraintError,
        match="語彙manifestを解決できないため参照整合を未検査のまま受理できない",
    ):
        _validate(contract, None)


MATRIX_COLUMNS = (
    "eventKind",
    "resultId",
    "precondition",
    "countEffect",
    "plateAppearanceEnded",
    "batterDestination",
    "runnerDefaultAdvance",
    "outEffect",
    "statFlags",
    "remarks",
)


def _invalid_matrix_column_value(column: str) -> object:
    """指定したMatrixRow列の単一列値域に違反する値を返す。

    Args:
        column: 違反させる列名。

    Returns:
        その列だけでは受理できない値。
    """
    invalid_values: dict[str, object] = {
        "eventKind": "unknown-event",
        "resultId": 1,
        "precondition": {"op": "eq", "axisId": "state.unknown", "value": 0},
        "countEffect": {
            "strikes": {"kind": "delta", "value": 3},
            "balls": {"kind": "unchanged"},
        },
        "plateAppearanceEnded": "ended",
        "batterDestination": {"kind": "reach", "base": 4},
        "runnerDefaultAdvance": {
            "first": {"modality": "hold", "destination": None},
            "second": {"modality": "hold", "destination": None},
        },
        "outEffect": {"count": 0, "targets": [{"runner": 4}]},
        "statFlags": {**_stat_flag_values(), "打点": "yes"},
        "remarks": {"text": "自由記述ではない型"},
    }
    return invalid_values[column]


@pytest.mark.parametrize("column", MATRIX_COLUMNS)
def test_each_matrix_column_rejects_an_out_of_domain_value(column: str) -> None:
    """MatrixRowの10列それぞれについて単一列の値域違反を拒否する。"""
    contract = _minimal_contract()
    contract["matrixRows"][0][column] = _invalid_matrix_column_value(column)

    expected_error = (
        ReferenceConstraintError
        if column == "precondition"
        else schema_checker.DescriptorCheckError
    )
    with pytest.raises(expected_error):
        _validate(contract)


def test_predicate_literal_outside_descriptor_axis_domain_is_red() -> None:
    """実在軸でもdescriptorの値域外を参照するPredicateを拒否する。"""
    contract = _minimal_contract()
    contract["matrixRows"][0]["precondition"] = {
        "op": "eq",
        "axisId": "state.outs",
        "value": 3,
    }
    _sync_case_coordinate(contract, "matrixRows")

    with pytest.raises(
        ReferenceConstraintError,
        match="Predicate値がdescriptorの軸値域に属さない",
    ):
        _validate(contract)


def test_stat_flags_are_exactly_the_twenty_three_boolean_keys() -> None:
    """statFlagsを23件の必須booleanだけに閉じる。"""
    schema = _schema()
    stat_flags = schema["$defs"]["statFlags"]

    assert len(stat_flags["required"]) == 23
    assert set(stat_flags["required"]) == set(stat_flags["properties"])
    assert stat_flags["additionalProperties"] is False

    missing = _minimal_contract()
    del missing["matrixRows"][0]["statFlags"]["打点"]
    with pytest.raises(schema_checker.DescriptorCheckError, match="必須キー不足"):
        _validate(missing)

    unknown = _minimal_contract()
    unknown["matrixRows"][0]["statFlags"]["未知フラグ"] = False
    with pytest.raises(schema_checker.DescriptorCheckError, match="未知キー"):
        _validate(unknown)


def test_matrix_cross_column_constraints_remain_deferred() -> None:
    """単一列では妥当な列間不一致をステップ33より前に拒否しない。"""
    contract = _minimal_contract()
    row = contract["matrixRows"][0]
    row["outEffect"] = {"count": 2, "targets": ["batter"]}
    row["runnerDefaultAdvance"]["third"] = {
        "modality": "hold",
        "destination": 2,
    }

    _validate(contract)
