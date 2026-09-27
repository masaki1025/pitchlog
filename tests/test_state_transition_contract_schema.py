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


def _minimal_contract() -> dict[str, Any]:
    """構造・参照検査を通る最小の状況判定契約を返す。"""
    descriptor = _descriptor()
    return {
        "schemaVersion": 1,
        "version": "state_transition_contract_v1",
        "calculation": "state-transition",
        "inputAxesDescriptor": {
            "descriptorId": descriptor["descriptorId"],
            "version": descriptor["version"],
            "digest": descriptor["digest"],
        },
        "matrixRows": [
            {
                "rowId": "matrix.result.single.default",
                "resultId": "single",
            }
        ],
        "operationRows": [{"rowId": "operation.substitution.default"}],
        "undoRows": [{"rowId": "undo.confirmed-play.default"}],
        "mustOperationCoverage": {},
        "requiredSet": {},
        "cases": [{"rowId": "matrix.result.single.default"}],
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
    row_id_field = _required_string(row_rule.get("idField"), "rowIdentity.idField")
    maximum_occurrences = row_rule.get("maximumOccurrences")
    if not isinstance(maximum_occurrences, int) or maximum_occurrences < 1:
        raise ReferenceConstraintError("rowIdentity.maximumOccurrencesが正の整数でない")

    row_ids = [
        row[row_id_field]
        for collection in _annotated_collections(schema, row_annotation)
        for row in contract[collection]
    ]
    occurrences = Counter(row_ids)
    duplicates = sorted(
        row_id
        for row_id, count in occurrences.items()
        if count > maximum_occurrences
    )
    if duplicates:
        raise ReferenceConstraintError(f"規範行IDが3層を通して重複: {duplicates!r}")

    case_rule = _required_object(constraints.get("caseResolution"), "caseResolution")
    case_collection = _required_string(
        case_rule.get("collection"), "caseResolution.collection"
    )
    case_reference_field = _required_string(
        case_rule.get("referenceField"), "caseResolution.referenceField"
    )
    required_case_matches = case_rule.get("requiredMatchCount")
    if not isinstance(required_case_matches, int) or required_case_matches < 1:
        raise ReferenceConstraintError("caseResolution.requiredMatchCountが正の整数でない")
    for index, case in enumerate(contract[case_collection]):
        referenced_row_id = case[case_reference_field]
        if occurrences.get(referenced_row_id, 0) != required_case_matches:
            raise ReferenceConstraintError(
                "caseの規範行参照を必要件数へ解決できない: "
                f"{case_collection}[{index}].{case_reference_field}="
                f"{referenced_row_id!r}"
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


def test_row_internals_remain_open_for_later_constraint_steps() -> None:
    """参照shell以外の値域・交差制約を本ステップで先取りしない。"""
    contract = _minimal_contract()
    for layer in ("matrixRows", "operationRows", "undoRows"):
        contract[layer][0]["futureConstraintField"] = {"notClosedYet": True}

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


def test_duplicate_row_id_across_normative_layers_is_red() -> None:
    """異なる規範行層で同じrowIdを再利用した契約を拒否する。"""
    contract = _minimal_contract()
    contract["operationRows"][0]["rowId"] = contract["matrixRows"][0]["rowId"]

    with pytest.raises(ReferenceConstraintError, match="規範行IDが3層を通して重複"):
        _validate(contract)


def test_case_reference_to_unknown_normative_row_is_red() -> None:
    """実在しない規範行を参照する派生caseを拒否する。"""
    contract = _minimal_contract()
    contract["cases"][0]["rowId"] = "matrix.missing"

    with pytest.raises(
        ReferenceConstraintError,
        match="caseの規範行参照を必要件数へ解決できない",
    ):
        _validate(contract)


def test_unknown_vocabulary_reference_is_red() -> None:
    """どの宣言済み語彙シードにも存在しないresultIdを拒否する。"""
    contract = _minimal_contract()
    contract["matrixRows"][0]["resultId"] = "unknown-result"

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
