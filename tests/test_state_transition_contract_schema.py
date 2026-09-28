"""状況判定契約schemaの構造を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Mapping, Set
from itertools import product
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


class CrossConstraintError(ValueError):
    """状況判定契約の交差制約違反を表す。"""


class OperationRowConstraintError(ValueError):
    """操作規範行の参照・宣言制約違反を表す。"""


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


def _unchanged_effects(definition_name: str) -> dict[str, dict[str, str]]:
    """指定したStateEffect面の全フィールドを非変更として返す。"""
    definition = _schema()["$defs"][definition_name]
    return {field: {"kind": "unchanged"} for field in definition["required"]}


def _unchanged_state_effect() -> dict[str, Any]:
    """比較面4面をすべて保持する非変更StateEffectを返す。"""
    return {
        "stateFields": _unchanged_effects("stateFieldEffects"),
        "scoreboard": _unchanged_effects("scoreboardFieldEffects"),
        "statFlags": _unchanged_effects("statFlagEffects"),
        "historyAndResult": _unchanged_effects("historyAndResultEffects"),
    }


def _minimal_contract() -> dict[str, Any]:
    """構造・参照検査を通る最小の状況判定契約を返す。"""
    descriptor = _descriptor()
    matrix_precondition = {
        "op": "and",
        "args": [
            {"op": "eq", "axisId": "state.outs", "value": 0},
            {"op": "eq", "axisId": "state.runners", "value": "empty"},
        ],
    }
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
            "first": {"modality": "not-applicable", "destination": None},
            "second": {"modality": "not-applicable", "destination": None},
            "third": {"modality": "not-applicable", "destination": None},
        },
        "outEffect": {"count": 0, "targets": []},
        "statFlags": _stat_flag_values(),
        "remarks": "基準行",
    }
    operation_precondition = {"op": "eq", "axisId": "state.outs", "value": 0}
    operation_row = {
        "operationKind": "substitution",
        "clauseId": "FR-011",
        "payloadShape": {
            "type": "object",
            "properties": {
                "playerId": {"type": "string"},
            },
            "required": ["playerId"],
            "additionalProperties": False,
        },
        "precondition": operation_precondition,
        "stateEffect": _unchanged_state_effect(),
        "historyEffect": {"pushes": True, "kind": "confirmed-play"},
        "operationResult": "applied",
        "remarks": "選手交代の基準行",
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
                    "coordinate": {
                        "operationKind": operation_row["operationKind"],
                        "payloadShape": copy.deepcopy(operation_row["payloadShape"]),
                        "precondition": copy.deepcopy(operation_precondition),
                    },
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


def _json_equal(left: object, right: object) -> bool:
    """JSON値を型も含めて比較する。"""
    return schema_checker.canonicalize_json(left) == schema_checker.canonicalize_json(
        right
    )


def _resolve_json_pointer(value: object, pointer: str) -> object:
    """JSON Pointerが指す値を返す。

    Args:
        value: 探索元のJSON値。
        pointer: RFC 6901形式のJSON Pointer。

    Returns:
        Pointerが指すJSON値。

    Raises:
        CrossConstraintError: Pointerを解決できない場合。
    """
    if not pointer.startswith("/"):
        raise CrossConstraintError(f"JSON Pointerが不正: {pointer!r}")
    current = value
    for encoded_token in pointer[1:].split("/"):
        token = encoded_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise CrossConstraintError(f"JSON Pointerを解決できない: {pointer!r}")
        current = current[token]
    return current


def _descriptor_axis_values() -> dict[str, tuple[object, ...]]:
    """Predicate評価に使う全入力軸の値域をdescriptorから返す。"""
    schema = _schema()
    descriptor = _descriptor()
    rule = schema["x-pitchlog-reference-constraints"]["predicateAxisResolution"]
    value_fields = rule["descriptorValueFieldsByClassification"]
    axes: dict[str, tuple[object, ...]] = {}
    for collection in rule["descriptorCollections"]:
        for axis in descriptor[collection]:
            axis_id = axis[rule["descriptorAxisIdField"]]
            classification = axis[rule["descriptorClassificationField"]]
            value_field = value_fields.get(classification)
            values = axis.get(value_field) if isinstance(value_field, str) else None
            if axis_id in axes or not isinstance(values, list) or not values:
                raise CrossConstraintError(
                    f"入力軸の値域を一意に解決できない: axisId={axis_id!r}"
                )
            axes[axis_id] = tuple(values)
    return axes


def _evaluate_predicate(
    predicate: Mapping[str, Any], assignment: Mapping[str, object]
) -> bool:
    """指定した入力軸割当てでPredicateを評価する。"""
    operator = predicate["op"]
    if operator == "and":
        return all(
            _evaluate_predicate(_required_object(child, "Predicate.args[]"), assignment)
            for child in predicate["args"]
        )
    if operator == "or":
        return any(
            _evaluate_predicate(_required_object(child, "Predicate.args[]"), assignment)
            for child in predicate["args"]
        )
    if operator == "not":
        child = _required_object(predicate["args"][0], "Predicate.args[0]")
        return not _evaluate_predicate(child, assignment)

    axis_id = predicate["axisId"]
    if axis_id not in assignment:
        raise CrossConstraintError(f"Predicate評価の軸割当てが無い: {axis_id!r}")
    actual = assignment[axis_id]
    if operator == "eq":
        return _json_equal(actual, predicate["value"])
    if operator == "in":
        return any(_json_equal(actual, value) for value in predicate["values"])
    expected = predicate["value"]
    if (
        not isinstance(actual, int)
        or isinstance(actual, bool)
        or not isinstance(expected, int)
        or isinstance(expected, bool)
    ):
        raise CrossConstraintError(
            f"順序比較を整数として判定できない: axisId={axis_id!r}"
        )
    if operator == "gte":
        return actual >= expected
    if operator == "lte":
        return actual <= expected
    raise CrossConstraintError(f"未対応のPredicate演算子: {operator!r}")


def _satisfying_axis_values(
    predicate: Mapping[str, Any], target_axis_id: str
) -> tuple[object, ...]:
    """Predicateを充足できる対象軸の値を射影する。"""
    axes = _descriptor_axis_values()
    referenced_axis_ids = {leaf["axisId"] for leaf in _predicate_leaves(predicate)}
    enumerated_axis_ids = tuple(sorted(referenced_axis_ids | {target_axis_id}))
    try:
        domains = tuple(axes[axis_id] for axis_id in enumerated_axis_ids)
    except KeyError as exc:
        raise CrossConstraintError(
            f"Predicateの軸値域を解決できない: {exc.args[0]!r}"
        ) from exc

    satisfying_values: dict[bytes, object] = {}
    for values in product(*domains):
        assignment = dict(zip(enumerated_axis_ids, values, strict=True))
        if _evaluate_predicate(predicate, assignment):
            target_value = assignment[target_axis_id]
            satisfying_values[schema_checker.canonicalize_json(target_value)] = (
                target_value
            )
    if not satisfying_values:
        raise CrossConstraintError("Predicateの充足可能な入力座標が無い")
    return tuple(satisfying_values.values())


def _cross_constraint_configuration(
    schema: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """交差制約宣言を検証して設定と規則を返す。"""
    active_schema = _schema() if schema is None else schema
    configuration = _required_object(
        active_schema.get("x-pitchlog-matrix-cross-constraints"),
        "schema.x-pitchlog-matrix-cross-constraints",
    )
    raw_rules = configuration.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise CrossConstraintError("交差制約規則が空または配列でない")
    rules = tuple(
        _required_object(rule, "x-pitchlog-matrix-cross-constraints.rules[]")
        for rule in raw_rules
    )
    constraint_ids = [
        _required_string(rule.get("constraintId"), "交差制約ID") for rule in rules
    ]
    if len(constraint_ids) != len(set(constraint_ids)):
        raise CrossConstraintError("交差制約IDが重複している")

    parity = _descriptor()["freezeBaseline"]["criteria"]["threeWayParity"]
    expected_ids = {
        branch_id
        for branch_id in parity["requirementBranchIds"]
        if branch_id.startswith("XC-")
    }
    actual_ids = set(constraint_ids)
    if actual_ids != expected_ids:
        raise CrossConstraintError(
            "付録E-1の交差制約IDがdescriptorの分岐集合と一致しない: "
            f"expected={sorted(expected_ids)!r}; actual={sorted(actual_ids)!r}"
        )
    expected_exclusions = {
        branch_id
        for branch_id in parity["nonDefinitionBranchMentions"]
        if branch_id.startswith("XC-")
    }
    actual_exclusions = set(configuration.get("excludedConstraintIds", []))
    if actual_exclusions != expected_exclusions or actual_ids & actual_exclusions:
        raise CrossConstraintError(
            "付録E-1の外部制約除外が一致しない: "
            f"expected={sorted(expected_exclusions)!r}; "
            f"actual={sorted(actual_exclusions)!r}"
        )

    rules_by_id = {rule["constraintId"]: rule for rule in rules}
    principle_markers = parity["principleMarkers"]
    for constraint_id, principle_id in principle_markers.items():
        rule = rules_by_id.get(constraint_id)
        if (
            rule is None
            or rule.get("kind") != "deferred-derived-stat-flags-principle"
            or rule.get("principleId") != principle_id
            or rule.get("enforcement") != "deferred-stage-2"
            or rule.get("machineGuarantee") != "not-established"
        ):
            raise CrossConstraintError(
                f"{constraint_id}: 導出原則の段階2延期宣言が不正"
            )
        stage2 = _resolve_json_pointer(
            _descriptor(), _required_string(rule.get("stage2DeclarationPointer"), "")
        )
        if not isinstance(stage2, dict) or stage2.get("status") != "deferred":
            raise CrossConstraintError(
                f"{constraint_id}: descriptorの段階2延期を確認できない"
            )
        if not set(rule.get("deferredConstraintClasses", [])) <= set(
            stage2.get("constraintClasses", [])
        ):
            raise CrossConstraintError(
                f"{constraint_id}: 延期した制約クラスをdescriptorへ解決できない"
            )
        if not set(rule.get("requiredArtifacts", [])) <= set(
            stage2.get("requiredArtifacts", [])
        ):
            raise CrossConstraintError(
                f"{constraint_id}: 段階2の必須成果物をdescriptorへ解決できない"
            )
    return configuration, rules


def _runner_presence_by_base(
    predicate: Mapping[str, Any], configuration: Mapping[str, Any]
) -> dict[str, str]:
    """共通規則に従い各起点塁の走者存在を判定する。"""
    declaration = _required_object(
        configuration.get("runnerPresence"), "runnerPresence"
    )
    if declaration.get("undecidableAction") != "fail":
        raise CrossConstraintError("走者存在の判定不能時動作がfailでない")
    axis_id = _required_string(declaration.get("axisId"), "runnerPresence.axisId")
    possible_values = _satisfying_axis_values(predicate, axis_id)
    present_values_by_base = _required_object(
        declaration.get("presentValuesByBase"), "runnerPresence.presentValuesByBase"
    )
    result: dict[str, str] = {}
    for base, raw_present_values in present_values_by_base.items():
        if not isinstance(raw_present_values, list) or not raw_present_values:
            raise CrossConstraintError(f"走者存在集合が不正: base={base!r}")
        states = {
            "present"
            if any(_json_equal(value, present) for present in raw_present_values)
            else "absent"
            for value in possible_values
        }
        if len(states) != 1:
            raise CrossConstraintError(
                f"走者存在を一意に判定できない: base={base!r}; "
                f"states={sorted(states)!r}"
            )
        result[base] = states.pop()
    return result


def _cross_rule_violation(
    row: Mapping[str, Any],
    rule: Mapping[str, Any],
    configuration: Mapping[str, Any],
) -> str | None:
    """1規範行に対する1交差制約の違反理由を返す。"""
    kind = rule["kind"]
    if kind == "event-requires-batter-destination":
        if (
            row["eventKind"] == rule["eventKind"]
            and row["batterDestination"]["kind"]
            != rule["requiredDestinationKind"]
        ):
            return "走者イベントの打者行き先がnot-applicableでない"
        return None
    if kind == "absent-runner-requires-modality":
        presence = _runner_presence_by_base(row["precondition"], configuration)
        for base, state in presence.items():
            if (
                state == "absent"
                and row["runnerDefaultAdvance"][base]["modality"]
                != rule["requiredModality"]
            ):
                return f"不在走者の進塁種別が不正: base={base!r}"
        return None
    if kind == "advance-modality-destination-equivalence":
        null_modalities = set(rule["nullDestinationModalities"])
        non_null_modalities = set(rule["nonNullDestinationModalities"])
        for base, advance in row["runnerDefaultAdvance"].items():
            modality = advance["modality"]
            destination = advance["destination"]
            if (modality in null_modalities) != (destination is None):
                return f"停止種別とnull到達塁が双方向不一致: base={base!r}"
            if (modality in non_null_modalities) != (destination is not None):
                return f"進塁種別と非null到達塁が双方向不一致: base={base!r}"
        return None
    if kind == "out-count-target-cardinality-and-uniqueness":
        targets = row["outEffect"]["targets"]
        if row["outEffect"]["count"] != len(targets):
            return "アウト数と対象数が一致しない"
        canonical_targets = [
            schema_checker.canonicalize_json(target) for target in targets
        ]
        if len(canonical_targets) != len(set(canonical_targets)):
            return "アウト対象が重複している"
        return None
    if kind == "event-requires-count-effect":
        if row["eventKind"] != rule["eventKind"]:
            return None
        if any(
            effect["kind"] != rule["requiredEffectKind"]
            for effect in row["countEffect"].values()
        ):
            return "走者イベントがカウントを変更する"
        return None
    if kind == "plate-appearance-result-count-equivalence":
        if row["eventKind"] in rule["excludedEventKinds"]:
            return None
        destination_kind = row["batterDestination"]["kind"]
        allowed_destinations = rule["allowedDestinationKindsByEvent"].get(
            row["eventKind"], []
        )
        if destination_kind not in allowed_destinations:
            return "eventKind別allowlistに無い打者行き先"
        ended = row["plateAppearanceEnded"] is True
        if ended != (destination_kind in rule["endedDestinationKinds"]):
            return "打席終了と終端の打者行き先が双方向不一致"
        if (not ended) != (destination_kind in rule["continuingDestinationKinds"]):
            return "打席継続と継続側の打者行き先が双方向不一致"
        reset_kind = rule["requiredResetEffectKind"]
        if any((effect["kind"] == reset_kind) != ended for effect in row["countEffect"].values()):
            return "打席終了とS/Bリセットが双方向不一致"
        return None
    if kind == "event-plate-not-applicable-equivalence":
        if (row["eventKind"] == rule["eventKind"]) != (
            row["plateAppearanceEnded"] == rule["notApplicableValue"]
        ):
            return "走者イベントと打席終了not-applicableが双方向不一致"
        return None
    if kind == "runner-origin-destination-allowlist":
        for base, advance in row["runnerDefaultAdvance"].items():
            destination = advance["destination"]
            if (
                destination is not None
                and destination not in rule["allowedDestinationsByBase"][base]
            ):
                return f"起点塁から到達できない塁が指定された: base={base!r}"
        return None
    if kind == "batter-out-target-equivalence":
        batter_is_out = (
            row["batterDestination"]["kind"]
            == rule["batterOutDestinationKind"]
        )
        batter_is_target = any(
            _json_equal(target, rule["batterTarget"])
            for target in row["outEffect"]["targets"]
        )
        if batter_is_out != batter_is_target:
            return "打者アウトとアウト対象が双方向不一致"
        return None
    if kind == "maximum-prior-outs-plus-effect":
        if rule.get("undecidableAction") != "fail":
            return "事前アウト数の判定不能時動作がfailでない"
        possible_outs = _satisfying_axis_values(
            row["precondition"], rule["outsAxisId"]
        )
        integer_outs: list[int] = []
        for value in possible_outs:
            if not isinstance(value, int) or isinstance(value, bool):
                return "事前アウト数を整数として判定できない"
            integer_outs.append(value)
        if (
            max(integer_outs) + row["outEffect"]["count"]
            > rule["maximumPostPlayOuts"]
        ):
            return "許容される最大事前アウト数との合計が3を超える"
        return None
    if kind == "absent-runner-prohibits-out-target":
        presence = _runner_presence_by_base(row["precondition"], configuration)
        runner_number_to_base = configuration["runnerPresence"]["baseByRunnerNumber"]
        for target in row["outEffect"]["targets"]:
            if not isinstance(target, dict):
                continue
            base = runner_number_to_base[str(target["runner"])]
            if presence[base] == "absent":
                return f"不在走者がアウト対象に含まれる: base={base!r}"
        return None
    if kind == "deferred-derived-stat-flags-principle":
        return None
    return f"未対応の交差制約種別: {kind!r}"


def _validate_cross_constraints(contract: Mapping[str, Any]) -> None:
    """schema資産の宣言に従ってmatrixRowsの交差制約を検証する。"""
    configuration, rules = _cross_constraint_configuration()
    row_collection = _required_string(
        configuration.get("rowCollection"), "crossConstraints.rowCollection"
    )
    for row_index, row in enumerate(contract[row_collection]):
        violations: list[str] = []
        for rule in rules:
            if rule.get("enforcement") == "deferred-stage-2":
                continue
            constraint_id = rule["constraintId"]
            try:
                violation = _cross_rule_violation(row, rule, configuration)
            except CrossConstraintError as exc:
                violation = str(exc)
            if violation is not None:
                violations.append(f"{constraint_id}: {violation}")
        if violations:
            raise CrossConstraintError(
                f"{row_collection}[{row_index}]の交差制約違反: "
                + "; ".join(violations)
            )


def _operation_row_configuration(
    schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """D-8の操作規範行宣言を検証して返す。"""
    active_schema = _schema() if schema is None else schema
    configuration = _required_object(
        active_schema.get("x-pitchlog-operation-row-constraints"),
        "schema.x-pitchlog-operation-row-constraints",
    )
    definitions = _required_object(active_schema.get("$defs"), "schema.$defs")
    operation_kind = _required_object(
        definitions.get("operationKind"), "$defs.operationKind"
    )
    enum_values = operation_kind.get("enum")
    if (
        not isinstance(enum_values, list)
        or not enum_values
        or not all(isinstance(value, str) and value for value in enum_values)
    ):
        raise OperationRowConstraintError("operationKindのenumが不正")
    clause_by_kind = _required_object(
        configuration.get("clauseByOperationKind"), "clauseByOperationKind"
    )
    if set(enum_values) != set(clause_by_kind):
        raise OperationRowConstraintError(
            "operationKindと典拠FRの対応がexact-set不一致"
        )

    descriptor_axis = next(
        axis
        for axis in _descriptor()["stateTransitionAxes"]
        if axis["axisId"] == "event.operationKind"
    )
    descriptor_conditions = descriptor_axis.get("conditionalValues", [])
    declared_conditions = configuration.get("conditionalOperationKinds")
    schema_conditions = operation_kind.get("x-pitchlog-conditional-values")
    if not (
        _json_equal(declared_conditions, descriptor_conditions)
        and _json_equal(schema_conditions, descriptor_conditions)
    ):
        raise OperationRowConstraintError(
            "FR-040条件付きoperationKindがdescriptorと一致しない"
        )

    history_effect = _required_object(
        definitions.get("operationHistoryEffect"),
        "$defs.operationHistoryEffect",
    )
    variants = history_effect.get("oneOf")
    if not isinstance(variants, list) or len(variants) != 2:
        raise OperationRowConstraintError("historyEffectの双方向variantが不正")
    pushed_variant = _required_object(variants[1], "operationHistoryEffect.oneOf[1]")
    pushed_properties = _required_object(
        pushed_variant.get("properties"),
        "operationHistoryEffect.oneOf[1].properties",
    )
    history_kind = _required_object(
        pushed_properties.get("kind"),
        "operationHistoryEffect.oneOf[1].properties.kind",
    )
    if not _json_equal(
        history_kind.get("x-pitchlog-conditional-values"), descriptor_conditions
    ):
        raise OperationRowConstraintError(
            "FR-040条件付き履歴種別がdescriptorと一致しない"
        )

    state_fields = _required_object(
        definitions.get("stateFieldEffects"), "$defs.stateFieldEffects"
    )
    expected_state_fields = {
        axis["axisId"]
        for axis in _descriptor()["stateTransitionAxes"]
        if axis["axisId"].startswith("state.")
    }
    if set(state_fields.get("required", [])) != expected_state_fields:
        raise OperationRowConstraintError(
            "StateEffect.stateFieldsがdescriptorの状態軸と一致しない"
        )

    stat_flag_effects = _required_object(
        definitions.get("statFlagEffects"), "$defs.statFlagEffects"
    )
    stat_flags = _required_object(definitions.get("statFlags"), "$defs.statFlags")
    if set(stat_flag_effects.get("required", [])) != set(
        stat_flags.get("required", [])
    ):
        raise OperationRowConstraintError(
            "StateEffect.statFlagsが23フラグと一致しない"
        )
    return configuration


def _validate_operation_rows(
    contract: Mapping[str, Any], adopted_clause_ids: Set[str]
) -> None:
    """schema資産の宣言に従ってoperationRowsの参照制約を検証する。"""
    configuration = _operation_row_configuration()
    clause_by_kind = configuration["clauseByOperationKind"]
    payload_keywords = set(configuration["payloadSchemaRequiredKeywords"])
    conditional_clauses = {
        condition["value"]: condition["whenClauseId"]
        for condition in configuration["conditionalOperationKinds"]
    }
    for row_index, row in enumerate(contract["operationRows"]):
        operation_kind = row["operationKind"]
        required_clause = conditional_clauses.get(operation_kind)
        if required_clause is not None and required_clause not in adopted_clause_ids:
            raise OperationRowConstraintError(
                "未採用の条件付きoperationKindを使用している: "
                f"operationRows[{row_index}]; kind={operation_kind!r}"
            )
        if row["clauseId"] != clause_by_kind[operation_kind]:
            raise OperationRowConstraintError(
                "operationKindの典拠FRが一致しない: "
                f"operationRows[{row_index}]; kind={operation_kind!r}"
            )
        history_kind = row["historyEffect"]["kind"]
        history_required_clause = conditional_clauses.get(history_kind)
        if (
            history_required_clause is not None
            and history_required_clause not in adopted_clause_ids
        ):
            raise OperationRowConstraintError(
                "未採用の条件付き履歴種別を使用している: "
                f"operationRows[{row_index}]; kind={history_kind!r}"
            )
        payload_shape = row["payloadShape"]
        if set(payload_shape) != payload_keywords:
            raise OperationRowConstraintError(
                f"payloadShapeのkeyword集合が不正: operationRows[{row_index}]"
            )
        properties = payload_shape["properties"]
        required = payload_shape["required"]
        if not all(isinstance(field_schema, dict) for field_schema in properties.values()):
            raise OperationRowConstraintError(
                "payloadShape.propertiesのフィールドschemaがobjectでない: "
                f"operationRows[{row_index}]"
            )
        if not set(required) <= set(properties):
            raise OperationRowConstraintError(
                "payloadShape.requiredに未定義フィールドがある: "
                f"operationRows[{row_index}]"
            )


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
    row_collections = predicate_rule.get("rowCollections")
    if (
        not isinstance(row_collections, list)
        or not row_collections
        or not all(
            isinstance(collection, str) and collection
            for collection in row_collections
        )
    ):
        raise ReferenceConstraintError(
            "predicateAxisResolution.rowCollectionsが不正"
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
    for row_collection in row_collections:
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
                        "Predicate値域をdescriptorから解決できない: "
                        f"axisId={axis_id!r}"
                    )
                leaf_values = leaf.get("values")
                compared_values = (
                    leaf_values
                    if isinstance(leaf_values, list)
                    else [leaf["value"]]
                )
                canonical_allowed_values = {
                    schema_checker.canonicalize_json(value)
                    for value in allowed_values
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
    adopted_clause_ids: Set[str] = frozenset(),
) -> None:
    """状況判定契約のschema・参照制約・交差制約を検証する。"""
    _validate_schema(contract)
    _validate_operation_rows(contract, adopted_clause_ids)
    _validate_references(contract, vocabulary_ids_by_seed)
    _validate_cross_constraints(contract)


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


def test_undo_row_internals_remain_open_for_step35() -> None:
    """undo行の後続ステップ向け列を本ステップで閉じない。"""
    contract = _minimal_contract()
    contract["undoRows"][0]["futureConstraintField"] = {"notClosedYet": True}

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


OPERATION_ROW_COLUMNS = (
    "operationKind",
    "clauseId",
    "payloadShape",
    "precondition",
    "stateEffect",
    "historyEffect",
    "operationResult",
    "remarks",
)


def test_operation_row_is_closed_to_the_eight_d8_columns() -> None:
    """operationRowsの行をD-8が定める8列だけに閉じる。"""
    operation_row = _schema()["$defs"]["operationRow"]

    assert tuple(operation_row["required"]) == OPERATION_ROW_COLUMNS
    assert set(operation_row["properties"]) == set(OPERATION_ROW_COLUMNS)
    assert operation_row["additionalProperties"] is False
    assert not {
        "targetKind",
        "guaranteeMode",
    } & set(operation_row["properties"])


@pytest.mark.parametrize("missing_column", OPERATION_ROW_COLUMNS)
def test_each_missing_operation_row_column_is_red(missing_column: str) -> None:
    """D-8の操作規範行8列のいずれかが欠けた行を拒否する。"""
    contract = _minimal_contract()
    del contract["operationRows"][0][missing_column]

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match=rf"必須キー不足: .*{missing_column}",
    ):
        _validate(contract)


def test_unknown_operation_row_column_is_red() -> None:
    """D-8に無い操作規範行の列を拒否する。"""
    contract = _minimal_contract()
    contract["operationRows"][0]["guaranteeMode"] = "full-equality"

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="未知キー: .*guaranteeMode",
    ):
        _validate(contract)


@pytest.mark.parametrize(
    ("operation_kind", "clause_id"),
    [
        ("substitution", "FR-011"),
        ("tiebreak-start", "FR-009"),
        ("game-end-declaration", "FR-010"),
        ("adhoc-registration", "FR-015"),
    ],
)
def test_permanent_operation_kinds_resolve_to_their_clause(
    operation_kind: str, clause_id: str
) -> None:
    """常設4操作の種別と典拠FRの対応を受理する。"""
    contract = _minimal_contract()
    row = contract["operationRows"][0]
    row["operationKind"] = operation_kind
    row["clauseId"] = clause_id
    _sync_case_coordinate(contract, "operationRows")

    _validate(contract)


def test_state_correction_is_the_fr040_conditional_operation_kind() -> None:
    """状態補正をFR-040採用時だけの条件付き操作として宣言する。"""
    contract = _minimal_contract()
    row = contract["operationRows"][0]
    row["operationKind"] = "state-correction"
    row["clauseId"] = "FR-040"
    row["historyEffect"] = {"pushes": True, "kind": "state-correction"}
    _sync_case_coordinate(contract, "operationRows")

    _validate(contract, adopted_clause_ids=frozenset({"req:FR-040"}))
    configuration = _operation_row_configuration()
    descriptor_axis = next(
        axis
        for axis in _descriptor()["stateTransitionAxes"]
        if axis["axisId"] == "event.operationKind"
    )
    assert _json_equal(
        configuration["conditionalOperationKinds"],
        descriptor_axis["conditionalValues"],
    )


def test_state_correction_is_red_when_fr040_is_not_adopted() -> None:
    """FR-040未採用時の状態補正操作行を拒否する。"""
    contract = _minimal_contract()
    row = contract["operationRows"][0]
    row["operationKind"] = "state-correction"
    row["clauseId"] = "FR-040"
    row["historyEffect"] = {"pushes": True, "kind": "state-correction"}
    _sync_case_coordinate(contract, "operationRows")

    with pytest.raises(OperationRowConstraintError, match="未採用の条件付き"):
        _validate(contract)


def test_state_correction_history_kind_is_red_when_fr040_is_not_adopted() -> None:
    """FR-040未採用時の状態補正履歴種別を拒否する。"""
    contract = _minimal_contract()
    contract["operationRows"][0]["historyEffect"] = {
        "pushes": True,
        "kind": "state-correction",
    }

    with pytest.raises(OperationRowConstraintError, match="未採用の条件付き履歴種別"):
        _validate(contract)


def test_operation_kind_with_wrong_clause_is_red() -> None:
    """operationKindと典拠FRが一致しない操作規範行を拒否する。"""
    contract = _minimal_contract()
    contract["operationRows"][0]["clauseId"] = "FR-009"

    with pytest.raises(OperationRowConstraintError, match="典拠FRが一致しない"):
        _validate(contract)


def test_payload_shape_required_field_must_exist_in_properties() -> None:
    """payloadShapeの未定義フィールドをrequiredにできない。"""
    contract = _minimal_contract()
    contract["operationRows"][0]["payloadShape"]["required"] = ["missing"]
    _sync_case_coordinate(contract, "operationRows")

    with pytest.raises(
        OperationRowConstraintError,
        match="requiredに未定義フィールドがある",
    ):
        _validate(contract)


def test_operation_history_effect_is_bidirectionally_closed() -> None:
    """pushes=falseと非null履歴種別の組合せを拒否する。"""
    contract = _minimal_contract()
    contract["operationRows"][0]["historyEffect"] = {
        "pushes": False,
        "kind": "confirmed-play",
    }

    with pytest.raises(schema_checker.DescriptorCheckError, match="oneOf"):
        _validate(contract)


def test_operation_predicate_axis_must_resolve_to_descriptor() -> None:
    """操作行のPredicateもdescriptorに無いaxisIdを参照できない。"""
    contract = _minimal_contract()
    contract["operationRows"][0]["precondition"] = {
        "op": "eq",
        "axisId": "state.unknown",
        "value": 0,
    }
    _sync_case_coordinate(contract, "operationRows")

    with pytest.raises(
        ReferenceConstraintError,
        match="Predicate.axisIdをdescriptorへ必要件数で解決できない",
    ):
        _validate(contract)


def test_operation_state_effect_keeps_all_comparison_surfaces_closed() -> None:
    """StateEffectが状態軸・スコアボード・23フラグ・履歴結果を閉じる。"""
    schema = _schema()
    definitions = schema["$defs"]
    expected_state_fields = {
        axis["axisId"]
        for axis in _descriptor()["stateTransitionAxes"]
        if axis["axisId"].startswith("state.")
    }

    assert set(definitions["stateFieldEffects"]["required"]) == (
        expected_state_fields
    )
    assert set(definitions["statFlagEffects"]["required"]) == set(
        definitions["statFlags"]["required"]
    )
    for definition_name in (
        "stateFieldEffects",
        "scoreboardFieldEffects",
        "statFlagEffects",
        "historyAndResultEffects",
    ):
        definition = definitions[definition_name]
        assert set(definition["required"]) == set(definition["properties"])
        assert definition["additionalProperties"] is False


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
    """入力座標を保った複数出力列の変更でcase参照が変わらない。"""
    contract = _minimal_contract()
    row = contract["matrixRows"][0]
    row["countEffect"] = {
        "strikes": {"kind": "reset"},
        "balls": {"kind": "reset"},
    }
    row["plateAppearanceEnded"] = True
    row["batterDestination"] = {"kind": "reach", "base": 1}
    row["outEffect"] = {"count": 0, "targets": []}
    row["statFlags"]["安打"] = True
    row["remarks"] = "出力列を更新"

    _validate(contract)


def test_input_coordinate_comparison_uses_canonical_object_order() -> None:
    """JSON objectのキー順が違っても同じ入力座標へ解決する。"""
    contract = _minimal_contract()
    contract["cases"][0]["rowRef"]["coordinate"]["precondition"] = {
        "args": [
            {"value": 0, "axisId": "state.outs", "op": "eq"},
            {"value": "empty", "axisId": "state.runners", "op": "eq"},
        ],
        "op": "and",
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


def _matrix_precondition(
    *, outs: int | None = 0, runners: str | None = "empty"
) -> dict[str, Any]:
    """交差制約fixture用の事前状態Predicateを返す。"""
    leaves: list[dict[str, Any]] = []
    if outs is not None:
        leaves.append({"op": "eq", "axisId": "state.outs", "value": outs})
    if runners is not None:
        leaves.append(
            {"op": "eq", "axisId": "state.runners", "value": runners}
        )
    if len(leaves) == 1:
        return leaves[0]
    return {"op": "and", "args": leaves}


def _set_precondition(contract: dict[str, Any], predicate: dict[str, Any]) -> None:
    """matrixRows先頭行の前提とcase座標を同時に更新する。"""
    contract["matrixRows"][0]["precondition"] = predicate
    _sync_case_coordinate(contract, "matrixRows")


def _set_runner_state(contract: dict[str, Any], runners: str) -> None:
    """走者配置と各起点塁の存在に整合する既定進塁を設定する。"""
    _set_precondition(contract, _matrix_precondition(runners=runners))
    configuration, _ = _cross_constraint_configuration()
    present_values_by_base = configuration["runnerPresence"][
        "presentValuesByBase"
    ]
    for base, present_values in present_values_by_base.items():
        modality = "hold" if runners in present_values else "not-applicable"
        contract["matrixRows"][0]["runnerDefaultAdvance"][base] = {
            "modality": modality,
            "destination": None,
        }


def _set_runner_event(contract: dict[str, Any]) -> None:
    """matrixRows先頭行を交差制約に適合する走者イベントへ変える。"""
    row = contract["matrixRows"][0]
    row["eventKind"] = "runner-event"
    row["countEffect"] = {
        "strikes": {"kind": "unchanged"},
        "balls": {"kind": "unchanged"},
    }
    row["plateAppearanceEnded"] = "not-applicable"
    row["batterDestination"] = {"kind": "not-applicable"}
    _sync_case_coordinate(contract, "matrixRows")


def _set_batter_out(contract: dict[str, Any]) -> None:
    """matrixRows先頭行を打者アウトの整合した出力へ変える。"""
    row = contract["matrixRows"][0]
    row["countEffect"] = {
        "strikes": {"kind": "reset"},
        "balls": {"kind": "reset"},
    }
    row["plateAppearanceEnded"] = True
    row["batterDestination"] = {"kind": "out"}
    row["outEffect"] = {"count": 1, "targets": ["batter"]}


def test_cross_constraint_declaration_has_twelve_rules_and_excludes_xc09() -> None:
    """E-1の12制約だけを持ち、undo固有のXC-09を除外する。"""
    configuration, rules = _cross_constraint_configuration()

    assert len(rules) == 12
    assert "XC-09" in configuration["excludedConstraintIds"]
    assert "XC-09" not in {rule["constraintId"] for rule in rules}


def test_xc01_runner_event_requires_not_applicable_batter_destination() -> None:
    """XC-01: 走者イベントで打者行き先をcontinueにできない。"""
    contract = _minimal_contract()
    _set_runner_event(contract)
    contract["matrixRows"][0]["batterDestination"] = {"kind": "continue"}

    with pytest.raises(CrossConstraintError, match="XC-01"):
        _validate(contract)


def test_xc02_absent_runner_requires_not_applicable_advance() -> None:
    """XC-02: 不在の一塁走者をholdにできない。"""
    contract = _minimal_contract()
    contract["matrixRows"][0]["runnerDefaultAdvance"]["first"] = {
        "modality": "hold",
        "destination": None,
    }

    with pytest.raises(CrossConstraintError, match="XC-02"):
        _validate(contract)


def test_xc02_runner_presence_must_be_decidable() -> None:
    """XC-02共通判定: 走者存在を一意に射影できない述語を拒否する。"""
    contract = _minimal_contract()
    _set_precondition(contract, _matrix_precondition(runners=None))

    with pytest.raises(CrossConstraintError, match="XC-02"):
        _validate(contract)


@pytest.mark.parametrize(
    ("modality", "destination"),
    [("hold", 2), ("forced", None)],
)
def test_xc03_advance_modality_and_destination_are_bidirectional(
    modality: str, destination: int | None
) -> None:
    """XC-03: 停止/nullと進塁/非nullの双方向不一致を拒否する。"""
    contract = _minimal_contract()
    _set_runner_state(contract, "first")
    contract["matrixRows"][0]["runnerDefaultAdvance"]["first"] = {
        "modality": modality,
        "destination": destination,
    }

    with pytest.raises(CrossConstraintError, match="XC-03"):
        _validate(contract)


def test_xc04_out_count_must_match_target_count() -> None:
    """XC-04: アウト数と対象配列長の不一致を拒否する。"""
    contract = _minimal_contract()
    contract["matrixRows"][0]["outEffect"] = {"count": 2, "targets": []}

    with pytest.raises(CrossConstraintError, match="XC-04"):
        _validate(contract)


def test_xc04_out_targets_must_be_unique() -> None:
    """XC-04: 同じ打者を2回アウト対象にする行を拒否する。"""
    contract = _minimal_contract()
    _set_batter_out(contract)
    contract["matrixRows"][0]["outEffect"] = {
        "count": 2,
        "targets": ["batter", "batter"],
    }

    with pytest.raises(CrossConstraintError, match="XC-04"):
        _validate(contract)


def test_xc05_runner_event_cannot_change_count() -> None:
    """XC-05: 走者イベントによるストライク増分を拒否する。"""
    contract = _minimal_contract()
    _set_runner_event(contract)
    contract["matrixRows"][0]["countEffect"]["strikes"] = {
        "kind": "delta",
        "value": 1,
    }

    with pytest.raises(CrossConstraintError, match="XC-05"):
        _validate(contract)


def test_xc06_batting_result_out_cannot_continue_plate_appearance() -> None:
    """XC-06: batting-resultの打者アウトと打席継続の組合せを拒否する。"""
    contract = _minimal_contract()
    row = contract["matrixRows"][0]
    row["batterDestination"] = {"kind": "out"}
    row["outEffect"] = {"count": 1, "targets": ["batter"]}

    with pytest.raises(CrossConstraintError, match="XC-06"):
        _validate(contract)


def test_xc06_secondary_result_not_applicable_cannot_end_plate_appearance() -> None:
    """XC-06: secondary-resultの行き先なしと打席終了の組合せを拒否する。"""
    contract = _minimal_contract()
    row = contract["matrixRows"][0]
    row["eventKind"] = "secondary-result"
    row["countEffect"] = {
        "strikes": {"kind": "reset"},
        "balls": {"kind": "reset"},
    }
    row["plateAppearanceEnded"] = True
    row["batterDestination"] = {"kind": "not-applicable"}
    _sync_case_coordinate(contract, "matrixRows")

    with pytest.raises(CrossConstraintError, match="XC-06"):
        _validate(contract)


def test_xc06_batting_result_continuation_cannot_reset_count() -> None:
    """XC-06: batting-resultの打席継続時のS/Bリセットを拒否する。"""
    contract = _minimal_contract()
    contract["matrixRows"][0]["countEffect"] = {
        "strikes": {"kind": "reset"},
        "balls": {"kind": "reset"},
    }

    with pytest.raises(CrossConstraintError, match="XC-06"):
        _validate(contract)


def test_xc06_secondary_result_cannot_use_score_destination() -> None:
    """XC-06: eventKind別allowlist外のsecondary-result得点を拒否する。"""
    contract = _minimal_contract()
    row = contract["matrixRows"][0]
    row["eventKind"] = "secondary-result"
    row["countEffect"] = {
        "strikes": {"kind": "reset"},
        "balls": {"kind": "reset"},
    }
    row["plateAppearanceEnded"] = True
    row["batterDestination"] = {"kind": "score"}
    _sync_case_coordinate(contract, "matrixRows")

    with pytest.raises(CrossConstraintError, match="XC-06"):
        _validate(contract)


def test_xc06_does_not_apply_to_runner_event() -> None:
    """XC-06: 正しいrunner-eventは打席終了規則の対象外である。"""
    contract = _minimal_contract()
    _set_runner_event(contract)

    _validate(contract)


@pytest.mark.parametrize("plate_appearance_ended", [False, "not-applicable"])
def test_xc07_event_and_not_applicable_are_bidirectional(
    plate_appearance_ended: bool | str,
) -> None:
    """XC-07: runner-eventとのnot-applicable双方向不一致を拒否する。"""
    contract = _minimal_contract()
    if plate_appearance_ended is False:
        _set_runner_event(contract)
    contract["matrixRows"][0]["plateAppearanceEnded"] = plate_appearance_ended

    with pytest.raises(CrossConstraintError, match="XC-07"):
        _validate(contract)


def test_xc08_third_base_runner_cannot_advance_to_second() -> None:
    """XC-08: 三塁走者の二塁到達を拒否する。"""
    contract = _minimal_contract()
    _set_runner_state(contract, "third")
    contract["matrixRows"][0]["runnerDefaultAdvance"]["third"] = {
        "modality": "optional",
        "destination": 2,
    }

    with pytest.raises(CrossConstraintError, match="XC-08"):
        _validate(contract)


def test_xc10_batter_out_requires_batter_target() -> None:
    """XC-10: 打者アウトなのに対象に打者がない行を拒否する。"""
    contract = _minimal_contract()
    _set_batter_out(contract)
    contract["matrixRows"][0]["outEffect"] = {"count": 0, "targets": []}

    with pytest.raises(CrossConstraintError, match="XC-10"):
        _validate(contract)


def test_xc10_batter_target_requires_batter_out() -> None:
    """XC-10: 打者がアウトでない走者イベントの打者対象を拒否する。"""
    contract = _minimal_contract()
    _set_runner_event(contract)
    contract["matrixRows"][0]["outEffect"] = {
        "count": 1,
        "targets": ["batter"],
    }

    with pytest.raises(CrossConstraintError, match="XC-10"):
        _validate(contract)


def test_xc11_unique_prior_outs_use_their_maximum() -> None:
    """XC-11: 二死から2アウトを加える行を拒否する。"""
    contract = _minimal_contract()
    _set_runner_state(contract, "first")
    _set_precondition(contract, _matrix_precondition(outs=2, runners="first"))
    _set_batter_out(contract)
    contract["matrixRows"][0]["outEffect"] = {
        "count": 2,
        "targets": ["batter", {"runner": 1}],
    }

    with pytest.raises(CrossConstraintError, match="XC-11"):
        _validate(contract)


def test_xc11_range_predicate_uses_maximum_prior_outs() -> None:
    """XC-11: 0または1アウトの述語を最大値1で判定する。"""
    contract = _minimal_contract()
    _set_runner_state(contract, "first-second")
    _set_precondition(
        contract,
        {
            "op": "and",
            "args": [
                {"op": "in", "axisId": "state.outs", "values": [0, 1]},
                {
                    "op": "eq",
                    "axisId": "state.runners",
                    "value": "first-second",
                },
            ],
        },
    )
    _set_batter_out(contract)
    contract["matrixRows"][0]["outEffect"] = {
        "count": 3,
        "targets": ["batter", {"runner": 1}, {"runner": 2}],
    }

    with pytest.raises(CrossConstraintError, match="XC-11"):
        _validate(contract)


def test_xc11_unconstrained_outs_use_legal_maximum_two() -> None:
    """XC-11: outsを制約しない述語を合法値の最大2で判定する。"""
    contract = _minimal_contract()
    _set_runner_state(contract, "first")
    _set_precondition(contract, _matrix_precondition(outs=None, runners="first"))
    _set_batter_out(contract)
    contract["matrixRows"][0]["outEffect"] = {
        "count": 2,
        "targets": ["batter", {"runner": 1}],
    }

    with pytest.raises(CrossConstraintError, match="XC-11"):
        _validate(contract)


def test_xc12_absent_runner_cannot_be_out_target() -> None:
    """XC-12: 不在の一塁走者をアウト対象にできない。"""
    contract = _minimal_contract()
    _set_runner_event(contract)
    contract["matrixRows"][0]["outEffect"] = {
        "count": 1,
        "targets": [{"runner": 1}],
    }

    with pytest.raises(CrossConstraintError, match="XC-12"):
        _validate(contract)


def test_xc13_cannot_be_declared_machine_guaranteed_before_stage2() -> None:
    """XC-13: 導出表なしで機械保証済みとする宣言を拒否する。"""
    schema = copy.deepcopy(_schema())
    rule = next(
        rule
        for rule in schema["x-pitchlog-matrix-cross-constraints"]["rules"]
        if rule["constraintId"] == "XC-13"
    )
    rule["machineGuarantee"] = "established"

    with pytest.raises(CrossConstraintError, match="XC-13"):
        _cross_constraint_configuration(schema)


def test_xc13_stat_flag_row_derivation_is_explicitly_deferred() -> None:
    """XC-13: statFlags反転を現段階で機械保証したとは扱わない。"""
    contract = _minimal_contract()
    contract["matrixRows"][0]["statFlags"]["安打"] = True

    _validate(contract)
    _, rules = _cross_constraint_configuration()
    rule = next(rule for rule in rules if rule["constraintId"] == "XC-13")
    assert rule["enforcement"] == "deferred-stage-2"
    assert rule["machineGuarantee"] == "not-established"
