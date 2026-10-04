"""状況判定契約schemaの構造を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Mapping, Set
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
VOCABULARY_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_vocabulary_manifest.py"
PROVENANCE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_provenance.py"
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/state_transition_contract_schema_v1.json"
)
CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/state_transition_contract_v1.json"
)
REQUIRED_SET_ROW_RULES_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/required_set_row_rules_v1.json"
)
GAP_REGISTER_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/gap_register_v1.json"
)
DESCRIPTOR_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/input_axes_descriptor_v1.json"
)
_DEFAULT_VOCABULARY_IDS_BY_SEED = object()
_DEFAULT_VECTOR_MANIFEST = object()


class ReferenceConstraintError(ValueError):
    """状況判定契約の参照制約違反を表す。"""


class CrossConstraintError(ValueError):
    """状況判定契約の交差制約違反を表す。"""


class OperationRowConstraintError(ValueError):
    """操作規範行の参照・宣言制約違反を表す。"""


class UndoRowConstraintError(ValueError):
    """undo規範行の参照・交差制約違反を表す。"""


class MustOperationCoverageError(ValueError):
    """Must操作被覆の写像・宣言制約違反を表す。"""


class VocabularyAxisCoverageError(ValueError):
    """語彙軸と規範行のexact-set被覆違反を表す。"""


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
    "check_input_axes_descriptor", DESCRIPTOR_CHECKER_PATH
)
vocabulary_checker = _load_module(
    "check_vocabulary_manifest", VOCABULARY_CHECKER_PATH
)
provenance_checker = _load_module("check_provenance", PROVENANCE_CHECKER_PATH)


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


def _repository_contract() -> dict[str, Any]:
    """段階実装中の状況判定契約を返す。"""
    return _load_object(CONTRACT_PATH)


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


def _provenance() -> dict[str, Any]:
    """宣言済みの機械保証範囲を充足する由来記録を返す。"""
    return {
        "subjectKind": "normative-branch-or-state-effect",
        "sources": [
            {
                "sourceKind": "requirements",
                "sourceId": "req:E-1",
            }
        ],
        "authorId": "contract-author",
        "independentVerifierId": "independent-verifier",
        "independentReview": {
            "verifiedOn": "2026-09-29",
            "reviewerRole": "reviewer",
            "authorWorkExposure": "not-seen-before-source-review",
            "chronology": [
                {
                    "sequence": 1,
                    "actorId": "independent-verifier",
                    "activity": "典拠を確認した",
                }
            ],
            "findings": ["典拠が対象を支持する"],
        },
        "attestations": [
            {
                "attestationId": "direct-source-clause-review",
                "response": True,
            },
            {
                "attestationId": "author-work-exposure",
                "response": "not-seen-before-source-review",
            },
            {
                "attestationId": "source-support-judgment",
                "response": True,
            },
        ],
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
        "resultId": "batting-result.single",
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
        "stateEffect": _unchanged_state_effect(),
        "historyEffect": {"pops": 1},
        "operationResult": "applied",
        "guaranteeMode": "full-equality",
        "remarks": "確定プレイを取り消す基準行",
    }
    secondary_row = copy.deepcopy(matrix_row)
    secondary_row["eventKind"] = "secondary-result"
    secondary_row["remarks"] = "副次結果の基準行"
    runner_row = copy.deepcopy(matrix_row)
    runner_row["eventKind"] = "runner-event"
    runner_row["plateAppearanceEnded"] = "not-applicable"
    runner_row["batterDestination"] = {"kind": "not-applicable"}
    runner_row["remarks"] = "走者イベントの基準行"

    operation_rows = [operation_row]
    for operation_kind, clause_id, remarks in (
        ("tiebreak-start", "FR-009", "タイブレーク開始の基準行"),
        ("game-end-declaration", "FR-010", "試合終了宣言の基準行"),
        ("adhoc-registration", "FR-015", "その場登録の基準行"),
    ):
        row = copy.deepcopy(operation_row)
        row["operationKind"] = operation_kind
        row["clauseId"] = clause_id
        row["remarks"] = remarks
        operation_rows.append(row)

    matrix_rows = [matrix_row, secondary_row, runner_row]
    coverage_mappings = [
        {
            "operationType": "per-pitch-input",
            "rowRefs": [
                _row_reference("matrixRows", row) for row in matrix_rows
            ],
        },
        {
            "operationType": "undo",
            "rowRefs": [_row_reference("undoRows", undo_row)],
        },
        *(
            {
                "operationType": row["operationKind"],
                "rowRefs": [_row_reference("operationRows", row)],
            }
            for row in operation_rows
        ),
    ]
    return {
        "schemaVersion": 1,
        "version": "state_transition_contract_v1",
        "calculation": "state-transition",
        "inputAxesDescriptor": {
            "descriptorId": descriptor["descriptorId"],
            "version": descriptor["version"],
            "digest": descriptor["digest"],
        },
        "provenance": _provenance(),
        "matrixRows": matrix_rows,
        "operationRows": operation_rows,
        "undoRows": [undo_row],
        "mustOperationCoverage": {"mappings": coverage_mappings},
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
                    "coordinate": {
                        "targetKind": undo_row["targetKind"],
                        "precondition": copy.deepcopy(undo_precondition),
                    },
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


def _undo_row_configuration(
    schema: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """D-8のundo規範行宣言とXC-09を検証して返す。"""
    active_schema = _schema() if schema is None else schema
    configuration = _required_object(
        active_schema.get("x-pitchlog-undo-row-constraints"),
        "schema.x-pitchlog-undo-row-constraints",
    )
    definitions = _required_object(active_schema.get("$defs"), "schema.$defs")
    target_kind = _required_object(
        definitions.get("undoTargetKind"), "$defs.undoTargetKind"
    )
    enum_values = target_kind.get("enum")
    if (
        not isinstance(enum_values, list)
        or not enum_values
        or not all(isinstance(value, str) and value for value in enum_values)
    ):
        raise UndoRowConstraintError("targetKindのenumが不正")
    declared_conditions = configuration.get("conditionalTargetKinds")
    schema_conditions = target_kind.get("x-pitchlog-conditional-values")
    descriptor_axis = next(
        axis
        for axis in _descriptor()["stateTransitionAxes"]
        if axis["axisId"] == "event.operationKind"
    )
    descriptor_conditions = [
        condition
        for condition in descriptor_axis.get("conditionalValues", [])
        if condition.get("value") == "state-correction"
    ]
    if not (
        _json_equal(declared_conditions, descriptor_conditions)
        and _json_equal(schema_conditions, descriptor_conditions)
    ):
        raise UndoRowConstraintError(
            "FR-040条件付きtargetKindがdescriptorと一致しない"
        )

    raw_rules = configuration.get("rules")
    if not isinstance(raw_rules, list) or len(raw_rules) != 1:
        raise UndoRowConstraintError("undoRowsの交差制約が1件でない")
    rule = _required_object(raw_rules[0], "x-pitchlog-undo-row-constraints.rules[0]")
    parity = _descriptor()["freezeBaseline"]["criteria"]["threeWayParity"]
    owner = parity["requirementConstraintOwners"].get(rule.get("constraintId"))
    if (
        rule.get("constraintId") not in parity["adrD8ConstraintIds"]
        or not isinstance(owner, dict)
        or owner.get("decisionId") != "D-8"
        or owner.get("layer") != "undoRows[]"
    ):
        raise UndoRowConstraintError("XC-09のD-8・undoRows帰属を解決できない")
    if rule.get("undecidableAction") != "fail":
        raise UndoRowConstraintError("XC-09の判定不能時動作がfailでない")

    depth_axis_id = _required_string(rule.get("depthAxisId"), "XC-09.depthAxisId")
    scenario_axis_id = _required_string(
        rule.get("scenarioLengthAxisId"), "XC-09.scenarioLengthAxisId"
    )
    try:
        depth_axis = next(
            axis
            for axis in _descriptor()["stateTransitionAxes"]
            if axis["axisId"] == depth_axis_id
        )
        scenario_axis = next(
            axis
            for axis in _descriptor()["stateTransitionAxes"]
            if axis["axisId"] == scenario_axis_id
        )
    except StopIteration as exc:
        raise UndoRowConstraintError(
            "XC-09のD+1入力軸をdescriptorへ解決できない"
        ) from exc
    if not any(
        _json_equal(value, rule.get("depthLimitValue"))
        for value in depth_axis.get("boundaryValues", [])
    ):
        raise UndoRowConstraintError(
            "XC-09のD値をdescriptorの履歴深さ境界へ解決できない"
        )
    if not any(
        _json_equal(value, rule.get("dPlusOneValue"))
        for value in scenario_axis.get("boundaryValues", [])
    ):
        raise UndoRowConstraintError(
            "XC-09のD+1値をdescriptorの境界値へ解決できない"
        )
    guarantee_modes = definitions["undoRow"]["properties"]["guaranteeMode"].get(
        "enum", []
    )
    if {
        rule.get("livenessMode"),
        rule.get("defaultMode"),
    } != set(guarantee_modes):
        raise UndoRowConstraintError("XC-09とguaranteeModeのenumが一致しない")
    return configuration, rule


def _validate_undo_rows(
    contract: Mapping[str, Any], adopted_clause_ids: Set[str]
) -> None:
    """schema資産の宣言に従ってundoRowsとXC-09を検証する。"""
    configuration, xc09 = _undo_row_configuration()
    conditional_clauses = {
        condition["value"]: condition["whenClauseId"]
        for condition in configuration["conditionalTargetKinds"]
    }
    axis_prefix = _required_string(
        configuration.get("preconditionAxisIdPrefix"),
        "undoRowConstraints.preconditionAxisIdPrefix",
    )
    for row_index, row in enumerate(contract["undoRows"]):
        target_kind = row["targetKind"]
        required_clause = conditional_clauses.get(target_kind)
        if required_clause is not None and required_clause not in adopted_clause_ids:
            raise UndoRowConstraintError(
                "未採用の条件付きtargetKindを使用している: "
                f"undoRows[{row_index}]; kind={target_kind!r}"
            )
        axis_ids = {
            leaf["axisId"] for leaf in _predicate_leaves(row["precondition"])
        }
        if not axis_ids or any(
            not axis_id.startswith(axis_prefix) for axis_id in axis_ids
        ):
            raise UndoRowConstraintError(
                "undoRowsのpreconditionが履歴文脈軸だけを参照していない: "
                f"undoRows[{row_index}]; axes={sorted(axis_ids)!r}"
            )
        if row["guaranteeMode"] != xc09["livenessMode"]:
            continue
        try:
            possible_lengths = _satisfying_axis_values(
                row["precondition"], xc09["scenarioLengthAxisId"]
            )
        except CrossConstraintError as exc:
            raise UndoRowConstraintError(
                f"XC-09: D+1行を判定できない: undoRows[{row_index}]"
            ) from exc
        if len(possible_lengths) != 1 or not _json_equal(
            possible_lengths[0], xc09["dPlusOneValue"]
        ):
            raise UndoRowConstraintError(
                "XC-09: liveness-onlyはD+1の行だけに許す: "
                f"undoRows[{row_index}]; possible={possible_lengths!r}"
            )


def _must_operation_coverage_configuration() -> dict[str, Any]:
    """Must操作被覆の資産側宣言を返す。

    Returns:
        状況判定契約schemaに置かれた被覆宣言。

    Raises:
        MustOperationCoverageError: 宣言がobjectでない場合。
    """
    value = _schema().get("x-pitchlog-must-operation-coverage")
    if not isinstance(value, dict):
        raise MustOperationCoverageError("Must操作被覆宣言がobjectでない")
    return value


def _row_reference(layer: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """規範行の入力座標参照を返す。

    Args:
        layer: 規範行層。
        row: 参照対象の規範行。

    Returns:
        出力列を含まない入力座標参照。
    """
    schema = _schema()
    rule = schema["x-pitchlog-reference-constraints"]["rowIdentity"]
    fields = _coordinate_fields(
        schema, layer, rule["coordinateFieldsAnnotation"]
    )
    return {
        "layer": layer,
        "coordinate": {field: copy.deepcopy(row[field]) for field in fields},
    }


def _resolved_vector_manifest(
    adopted_clause_ids: Set[str] = frozenset(),
) -> dict[str, Any]:
    """未整備の製品manifestを模す解決済みfixtureを返す。

    Args:
        adopted_clause_ids: 採用済みの任意条文ID。

    Returns:
        schemaの解決宣言から組み立てた`vectors[]` fixture。
    """
    configuration = _must_operation_coverage_configuration()
    manifest_rule = configuration["manifestOmissionResolution"]
    exclusions = []
    for operation in configuration["conditionalOperations"]:
        clause_id = operation["whenClauseId"]
        if clause_id not in adopted_clause_ids:
            exclusions.append(
                {
                    manifest_rule["operationTypeField"]: operation[
                        "operationType"
                    ],
                    manifest_rule["clauseIdField"]: clause_id,
                    manifest_rule["adoptionStateField"]: manifest_rule[
                        "notAdoptedValue"
                    ],
                }
            )
    return {
        manifest_rule["collection"]: [
            {
                manifest_rule["calculationField"]: manifest_rule[
                    "calculationValue"
                ],
                manifest_rule["exclusionsField"]: exclusions,
            }
        ]
    }


def _add_state_correction_operation(contract: dict[str, Any]) -> None:
    """FR-040採用時の状態補正行と被覆写像を追加する。

    Args:
        contract: 更新する状況判定契約。
    """
    row = copy.deepcopy(contract["operationRows"][0])
    row["operationKind"] = "state-correction"
    row["clauseId"] = "FR-040"
    row["historyEffect"] = {"pushes": True, "kind": "state-correction"}
    row["remarks"] = "状態補正の基準行"
    contract["operationRows"].append(row)
    contract["mustOperationCoverage"]["mappings"].append(
        {
            "operationType": "state-correction",
            "rowRefs": [_row_reference("operationRows", row)],
        }
    )


def _coverage_row_index(
    contract: Mapping[str, Any], configuration: Mapping[str, Any]
) -> tuple[dict[tuple[str, bytes], Mapping[str, Any]], set[tuple[str, bytes]]]:
    """規範行を入力座標で索引化する。

    Args:
        contract: 検証する状況判定契約。
        configuration: Must操作被覆宣言。

    Returns:
        入力座標から行への索引と全入力座標の集合。

    Raises:
        MustOperationCoverageError: 行層宣言または入力座標宣言が不正な場合。
    """
    schema = _schema()
    try:
        layers = _annotated_collections(
            schema, configuration["rowLayerAnnotation"]
        )
        coordinate_annotation = configuration["coordinateFieldsAnnotation"]
        indexed_rows = [
            (
                (
                    layer,
                    schema_checker.canonicalize_json(
                        {
                            field: row[field]
                            for field in _coordinate_fields(
                                schema, layer, coordinate_annotation
                            )
                        }
                    ),
                ),
                row,
            )
            for layer in layers
            for row in contract[layer]
        ]
    except (KeyError, ReferenceConstraintError) as exc:
        raise MustOperationCoverageError(
            "規範行層または入力座標の宣言を解決できない"
        ) from exc
    return dict(indexed_rows), {key for key, _ in indexed_rows}


def _validate_manifest_omission_declaration(
    configuration: Mapping[str, Any],
    adopted_clause_ids: Set[str],
    vector_manifest: Mapping[str, Any] | None,
) -> None:
    """FR-040不採用宣言を解決し、宣言のない除外を拒否する。

    Args:
        configuration: Must操作被覆宣言。
        adopted_clause_ids: 採用済みの任意条文ID。
        vector_manifest: 解決済みの宣言マニフェスト。解決不能時はNone。

    Raises:
        MustOperationCoverageError: マニフェストを解決できない、または条件付き
            操作の採用状態と除外宣言が一致しない場合。
    """
    manifest_rule = configuration.get("manifestOmissionResolution")
    if not isinstance(manifest_rule, dict):
        raise MustOperationCoverageError("マニフェスト除外宣言の解決規則が不正")
    if vector_manifest is None:
        if manifest_rule.get("failWhenManifestUnavailable") is True:
            raise MustOperationCoverageError(
                "vectors[]マニフェストを解決できず除外宣言を確認できない"
            )
        raise MustOperationCoverageError(
            "マニフェスト未解決時のfail-closed宣言が欠けている"
        )

    collection = vector_manifest.get(manifest_rule["collection"])
    if not isinstance(collection, list):
        raise MustOperationCoverageError("マニフェストのvectors[]を解決できない")
    vector_matches = [
        vector
        for vector in collection
        if isinstance(vector, dict)
        and vector.get(manifest_rule["calculationField"])
        == manifest_rule["calculationValue"]
    ]
    if len(vector_matches) != manifest_rule["requiredMatchCount"]:
        raise MustOperationCoverageError(
            "状況判定のvectors[]宣言を必要件数へ解決できない"
        )
    exclusions = vector_matches[0].get(manifest_rule["exclusionsField"])
    if not isinstance(exclusions, list):
        raise MustOperationCoverageError("vectors[]の任意操作除外宣言が配列でない")

    for operation in configuration["conditionalOperations"]:
        expected = {
            manifest_rule["operationTypeField"]: operation["operationType"],
            manifest_rule["clauseIdField"]: operation["whenClauseId"],
            manifest_rule["adoptionStateField"]: manifest_rule["notAdoptedValue"],
        }
        matches = sum(
            isinstance(exclusion, dict)
            and all(exclusion.get(key) == value for key, value in expected.items())
            for exclusion in exclusions
        )
        adopted = operation["whenClauseId"] in adopted_clause_ids
        expected_matches = 0 if adopted else manifest_rule["requiredMatchCount"]
        if matches != expected_matches:
            raise MustOperationCoverageError(
                "FR-040の採用状態とvectors[]の除外宣言が一致しない: "
                f"operationType={operation['operationType']!r}; matches={matches}"
            )


def _validate_must_operation_coverage(
    contract: Mapping[str, Any],
    adopted_clause_ids: Set[str],
    vector_manifest: Mapping[str, Any] | None,
) -> None:
    """Must 6種と条件付き第7種の写像へ5検査を適用する。

    Args:
        contract: 検証する状況判定契約。
        adopted_clause_ids: 採用済みの任意条文ID。
        vector_manifest: 解決済みの宣言マニフェスト。解決不能時はNone。

    Raises:
        MustOperationCoverageError: 5検査のいずれか、またはFR-040の
            除外宣言が成立しない場合。
    """
    configuration = _must_operation_coverage_configuration()
    required_operations = configuration.get("requiredOperations")
    conditional_operations = configuration.get("conditionalOperations")
    checks = configuration.get("checks")
    if not (
        isinstance(required_operations, list)
        and isinstance(conditional_operations, list)
        and isinstance(checks, dict)
    ):
        raise MustOperationCoverageError("Must操作被覆宣言の構造が不正")
    operation_conditions = _operation_row_configuration()[
        "conditionalOperationKinds"
    ]
    coverage_conditions = [
        {
            "value": operation["operationType"],
            "whenClauseId": operation["whenClauseId"],
            "whenState": operation["whenState"],
        }
        for operation in conditional_operations
    ]
    if not _json_equal(coverage_conditions, operation_conditions):
        raise MustOperationCoverageError(
            "条件付き第7種の宣言がoperationKind宣言と一致しない"
        )
    active_operations = [
        *required_operations,
        *(
            operation
            for operation in conditional_operations
            if operation.get("whenClauseId") in adopted_clause_ids
        ),
    ]
    expected_by_type = {
        operation["operationType"]: operation for operation in active_operations
    }
    if len(expected_by_type) != len(active_operations):
        raise MustOperationCoverageError("被覆対象の操作種別宣言が重複")

    coverage = contract["mustOperationCoverage"]
    mappings = coverage[configuration["mappingCollection"]]
    operation_type_field = configuration["operationTypeField"]
    row_references_field = configuration["rowReferencesField"]
    operation_type_counts = Counter(
        mapping[operation_type_field] for mapping in mappings
    )
    duplicate_rule = checks["duplicateProhibition"]
    if any(
        count > duplicate_rule["operationTypeMaximumOccurrences"]
        for count in operation_type_counts.values()
    ):
        raise MustOperationCoverageError("③操作種別の写像が重複")
    if set(operation_type_counts) != set(expected_by_type):
        raise MustOperationCoverageError(
            "Must 6種と条件付き第7種の写像がexact-set不一致"
        )

    row_index, all_row_keys = _coverage_row_index(contract, configuration)
    required_matches = checks["referenceExistence"]["requiredMatchCount"]
    assigned_keys: list[tuple[str, bytes]] = []
    rows_by_operation_type: dict[str, list[Mapping[str, Any]]] = {}
    for mapping in mappings:
        operation_type = mapping[operation_type_field]
        operation_rule = expected_by_type[operation_type]
        mapped_rows: list[Mapping[str, Any]] = []
        for row_reference in mapping[row_references_field]:
            layer = row_reference[configuration["rowLayerField"]]
            coordinate = schema_checker.canonicalize_json(
                row_reference[configuration["rowCoordinateField"]]
            )
            key = (layer, coordinate)
            matches = int(key in row_index)
            if matches != required_matches:
                raise MustOperationCoverageError(
                    "①写像の参照先を必要件数へ解決できない: "
                    f"operationType={operation_type!r}"
                )
            row = row_index[key]
            if layer != operation_rule["rowLayer"]:
                raise MustOperationCoverageError(
                    "②操作種別と規範行層が一致しない: "
                    f"operationType={operation_type!r}; layer={layer!r}"
                )
            discriminator_field = operation_rule.get("discriminatorField")
            exact_values = operation_rule.get("exactDiscriminatorValues")
            if discriminator_field is not None and (
                not isinstance(exact_values, list)
                or row.get(discriminator_field) not in exact_values
            ):
                raise MustOperationCoverageError(
                    "②操作種別と行の識別値が一致しない: "
                    f"operationType={operation_type!r}"
                )
            assigned_keys.append(key)
            mapped_rows.append(row)
        rows_by_operation_type[operation_type] = mapped_rows

    assigned_counts = Counter(assigned_keys)
    if any(
        count > duplicate_rule["rowReferenceMaximumOccurrences"]
        for count in assigned_counts.values()
    ):
        raise MustOperationCoverageError("③同じ規範行が複数の写像へ重複帰属")
    if set(assigned_counts) != all_row_keys:
        raise MustOperationCoverageError("④いずれの操作種別にも帰属しない規範行が存在")
    if any(
        count != checks["unassignedRows"]["maximumOccurrences"]
        for count in assigned_counts.values()
    ):
        raise MustOperationCoverageError("④規範行の帰属件数が不正")

    per_pitch_type = checks["perPitchSubtypeExactSet"]["operationType"]
    per_pitch_rule = expected_by_type[per_pitch_type]
    discriminator_field = per_pitch_rule["discriminatorField"]
    actual_subtypes = {
        row[discriminator_field] for row in rows_by_operation_type[per_pitch_type]
    }
    if actual_subtypes != set(per_pitch_rule["exactDiscriminatorValues"]):
        raise MustOperationCoverageError(
            "⑤毎球入力の3下位分類がexact-set不一致"
        )

    _validate_manifest_omission_declaration(
        configuration, adopted_clause_ids, vector_manifest
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
    for mapping in contract["mustOperationCoverage"]["mappings"]:
        for row_reference in mapping["rowRefs"]:
            if row_reference["layer"] == layer:
                row_reference["coordinate"] = {
                    field: copy.deepcopy(row[field]) for field in fields
                }
                return


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


def _validate_vocabulary_axis_coverage(
    contract: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """schema宣言に従い複数の語彙軸と規範行のID集合を照合する。

    Args:
        contract: 検証する状況判定契約。
        schema: テスト用のschema差し替え。省略時はリポジトリ資産を使う。

    Raises:
        VocabularyAxisCoverageError: manifest・シード・軸を一意に解決できないか、
            語彙ID集合がexact-setで一致しない場合。
    """
    active_schema = _schema() if schema is None else schema
    configuration = _required_object(
        active_schema.get("x-pitchlog-vocabulary-axis-coverage"),
        "schema.x-pitchlog-vocabulary-axis-coverage",
    )
    if configuration.get("requiredRelationship") != "exact-set":
        raise VocabularyAxisCoverageError("語彙軸被覆の関係がexact-setでない")

    try:
        resolved_ids = vocabulary_checker.validate_manifest(REPOSITORY_ROOT)
    except vocabulary_checker.VocabularyManifestError as error:
        raise VocabularyAxisCoverageError(str(error)) from error
    manifest_path = REPOSITORY_ROOT / _required_string(
        configuration.get("manifestPath"), "vocabularyAxisCoverage.manifestPath"
    )
    manifest = _load_object(manifest_path)
    vocabulary_id = _required_string(
        configuration.get("vocabularyId"), "vocabularyAxisCoverage.vocabularyId"
    )
    if vocabulary_id not in resolved_ids:
        raise VocabularyAxisCoverageError(
            "語彙軸のvocabularyIdを検証済みmanifestへ解決できない"
        )
    declarations = [
        declaration
        for declaration in manifest["seeds"]
        if declaration["vocabularyId"] == vocabulary_id
    ]
    if len(declarations) != 1:
        raise VocabularyAxisCoverageError(
            "語彙軸のシード宣言をmanifestへ一意に解決できない"
        )
    seed = _load_object(REPOSITORY_ROOT / declarations[0]["path"])

    axis_collection = _required_string(
        configuration.get("axisCollection"),
        "vocabularyAxisCoverage.axisCollection",
    )
    axis_id_field = _required_string(
        configuration.get("axisIdField"), "vocabularyAxisCoverage.axisIdField"
    )
    entries_collection = _required_string(
        configuration.get("entriesCollection"),
        "vocabularyAxisCoverage.entriesCollection",
    )
    entry_id_field = _required_string(
        configuration.get("entryIdField"),
        "vocabularyAxisCoverage.entryIdField",
    )
    row_collection = _required_string(
        configuration.get("rowCollection"),
        "vocabularyAxisCoverage.rowCollection",
    )
    discriminator_field = _required_string(
        configuration.get("rowDiscriminatorField"),
        "vocabularyAxisCoverage.rowDiscriminatorField",
    )
    row_id_field = _required_string(
        configuration.get("rowVocabularyIdField"),
        "vocabularyAxisCoverage.rowVocabularyIdField",
    )
    coverage_sets = configuration.get("coverageSets")
    if not isinstance(coverage_sets, list) or not coverage_sets:
        raise VocabularyAxisCoverageError("語彙軸被覆のcoverageSetsが空または配列でない")
    required_axis_ids_value = configuration.get("requiredAxisIds")
    if not isinstance(required_axis_ids_value, list) or not required_axis_ids_value:
        raise VocabularyAxisCoverageError("語彙軸被覆のrequiredAxisIdsが空または配列でない")
    required_axis_ids = {
        _required_string(axis_id, "vocabularyAxisCoverage.requiredAxisIds[]")
        for axis_id in required_axis_ids_value
    }
    if len(required_axis_ids) != len(required_axis_ids_value):
        raise VocabularyAxisCoverageError("語彙軸被覆のrequiredAxisIdsが重複している")
    seen_axis_ids: set[str] = set()
    seen_discriminator_values: set[str] = set()
    for index, raw_coverage_set in enumerate(coverage_sets):
        coverage_set = _required_object(
            raw_coverage_set,
            f"vocabularyAxisCoverage.coverageSets[{index}]",
        )
        raw_axis_ids = coverage_set.get("axisIds")
        if not isinstance(raw_axis_ids, list) or not raw_axis_ids:
            raise VocabularyAxisCoverageError(
                "語彙軸被覆のaxisIdsが空または配列でない"
            )
        axis_ids = [
            _required_string(
                axis_id,
                f"vocabularyAxisCoverage.coverageSets[{index}].axisIds[]",
            )
            for axis_id in raw_axis_ids
        ]
        if len(set(axis_ids)) != len(axis_ids):
            raise VocabularyAxisCoverageError("語彙軸被覆の同一集合内で軸が重複")
        discriminator_value = _required_string(
            coverage_set.get("rowDiscriminatorValue"),
            "vocabularyAxisCoverage."
            f"coverageSets[{index}].rowDiscriminatorValue",
        )
        if seen_axis_ids.intersection(axis_ids) or (
            discriminator_value in seen_discriminator_values
        ):
            raise VocabularyAxisCoverageError("語彙軸被覆の宣言が重複している")
        seen_axis_ids.update(axis_ids)
        seen_discriminator_values.add(discriminator_value)

        expected: set[str] = set()
        for axis_id in axis_ids:
            axes = [
                axis
                for axis in seed[axis_collection]
                if axis[axis_id_field] == axis_id
            ]
            if len(axes) != 1:
                raise VocabularyAxisCoverageError(
                    "語彙シードの対象軸を一意に解決できない: "
                    f"axisId={axis_id!r}"
                )
            expected.update(
                entry[entry_id_field] for entry in axes[0][entries_collection]
            )
        actual = {
            row[row_id_field]
            for row in contract[row_collection]
            if row[discriminator_field] == discriminator_value
        }
        if actual != expected:
            raise VocabularyAxisCoverageError(
                "語彙軸と規範行がexact-set不一致: "
                f"axisIds={axis_ids!r}; "
                f"missing={sorted(expected - actual)!r}; "
                f"unexpected={sorted(actual - expected)!r}"
            )
    if seen_axis_ids != required_axis_ids:
        raise VocabularyAxisCoverageError(
            "語彙軸被覆の宣言軸がexact-set不一致: "
            f"missing={sorted(required_axis_ids - seen_axis_ids)!r}; "
            f"unexpected={sorted(seen_axis_ids - required_axis_ids)!r}"
        )


def _validate(
    contract: dict[str, Any],
    vocabulary_ids_by_seed: Mapping[str, Set[str]] | None | object = (
        _DEFAULT_VOCABULARY_IDS_BY_SEED
    ),
    adopted_clause_ids: Set[str] = frozenset(),
    vector_manifest: Mapping[str, Any] | None | object = _DEFAULT_VECTOR_MANIFEST,
) -> None:
    """状況判定契約のschema・参照制約・交差制約を検証する。"""
    resolved_vocabulary_ids = (
        vocabulary_checker.validate_manifest(REPOSITORY_ROOT)
        if vocabulary_ids_by_seed is _DEFAULT_VOCABULARY_IDS_BY_SEED
        else vocabulary_ids_by_seed
    )
    if resolved_vocabulary_ids is not None and not isinstance(
        resolved_vocabulary_ids, Mapping
    ):
        raise ReferenceConstraintError("解決済み語彙ID集合がobjectでない")
    resolved_vector_manifest = (
        _resolved_vector_manifest(adopted_clause_ids)
        if vector_manifest is _DEFAULT_VECTOR_MANIFEST
        else vector_manifest
    )
    if resolved_vector_manifest is not None and not isinstance(
        resolved_vector_manifest, Mapping
    ):
        raise MustOperationCoverageError(
            "解決済みvectors[]マニフェストがobjectでない"
        )
    _validate_schema(contract)
    provenance_checker.validate_provenance(
        REPOSITORY_ROOT,
        contract["provenance"],
        schema_value=_schema(),
    )
    _validate_operation_rows(contract, adopted_clause_ids)
    _validate_undo_rows(contract, adopted_clause_ids)
    _validate_references(contract, resolved_vocabulary_ids)
    _validate_cross_constraints(contract)
    _validate_must_operation_coverage(
        contract, adopted_clause_ids, resolved_vector_manifest
    )


def test_repository_schema_accepts_the_three_normative_row_layers() -> None:
    """3規範行層と派生層を持つ最小構造を受理する。"""
    schema = _schema()

    assert schema["version"] == SCHEMA_PATH.stem
    assert "decisionRows" not in schema["properties"]
    _validate(_minimal_contract())


def test_repository_contract_step51_to_step60_rows_satisfy_constraints() -> None:
    """ステップ51〜60の42行が10列exact型・参照・XCを充足する。"""
    contract = _repository_contract()
    step51_result_ids = {
        "batting-result.called-pitch",
        "batting-result.swinging-strike",
        "batting-result.foul",
        "batting-result.ball",
    }
    step52_result_ids = {
        "batting-result.called-strikeout",
        "batting-result.swinging-strikeout",
        "batting-result.dropped-third-strike",
        "batting-result.k3",
        "batting-result.strikeout-double-play",
    }
    step53_result_ids = {
        "batting-result.walk",
        "batting-result.hit-by-pitch",
        "batting-result.intentional-walk",
    }
    step54_result_ids = {
        "batting-result.single",
        "batting-result.double",
        "batting-result.triple",
        "batting-result.home-run",
    }
    step55_result_ids = {
        "batting-result.batted-out",
        "batting-result.batted-reach",
        "batting-result.foul-fly",
    }
    step56_result_ids = {
        "batting-result.double-play",
        "batting-result.line-double-play",
        "batting-result.error",
        "batting-result.fielders-choice",
    }
    step57_result_ids = {
        "batting-result.sacrifice-bunt",
        "batting-result.sacrifice-fly",
        "batting-result.sacrifice-bunt-error",
    }

    _validate_schema(contract)
    _validate_references(
        contract,
        vocabulary_checker.validate_manifest(REPOSITORY_ROOT),
    )
    _validate_cross_constraints(contract)
    _validate_vocabulary_axis_coverage(contract)

    rows = contract["matrixRows"]
    assert len(rows) == 42
    assert {row["resultId"] for row in rows[:4]} == step51_result_ids
    assert {row["resultId"] for row in rows[4:9]} == step52_result_ids
    assert {row["resultId"] for row in rows[9:12]} == step53_result_ids
    assert {row["resultId"] for row in rows[12:16]} == step54_result_ids
    assert {row["resultId"] for row in rows[16:19]} == step55_result_ids
    assert {row["resultId"] for row in rows[19:23]} == step56_result_ids
    assert {row["resultId"] for row in rows[23:26]} == step57_result_ids
    assert all(row["eventKind"] == "batting-result" for row in rows[:26])
    assert all(row["plateAppearanceEnded"] is False for row in rows[:4])
    assert all(row["batterDestination"] == {"kind": "continue"} for row in rows[:4])
    assert all(row["outEffect"] == {"count": 0, "targets": []} for row in rows[:4])
    assert all(
        {name for name, enabled in row["statFlags"].items() if enabled}
        == {"投球数"}
        for row in rows[:4]
    )
    strikeout_rows = rows[4:9]
    assert all(row["plateAppearanceEnded"] is True for row in strikeout_rows)
    assert all(
        row["countEffect"]
        == {"strikes": {"kind": "reset"}, "balls": {"kind": "reset"}}
        for row in strikeout_rows
    )
    by_result = {row["resultId"]: row for row in strikeout_rows}
    dropped = by_result["batting-result.dropped-third-strike"]
    assert dropped["batterDestination"] == {"kind": "reach", "base": 1}
    assert dropped["outEffect"] == {"count": 0, "targets": []}
    assert {
        name for name, enabled in dropped["statFlags"].items() if enabled
    } == {"投球数", "奪三振", "打席", "打数", "三振"}
    double_play = by_result["batting-result.strikeout-double-play"]
    assert double_play["outEffect"] == {
        "count": 2,
        "targets": ["batter", {"runner": 1}],
    }
    for result_id, row in by_result.items():
        if result_id == "batting-result.dropped-third-strike":
            continue
        assert row["batterDestination"] == {"kind": "out"}
        assert row["statFlags"]["投球回算入アウト"] is True

    four_ball_rows = {row["resultId"]: row for row in rows[9:12]}
    assert all(row["plateAppearanceEnded"] is True for row in rows[9:12])
    assert all(
        row["batterDestination"] == {"kind": "reach", "base": 1}
        for row in rows[9:12]
    )
    assert all(
        row["outEffect"] == {"count": 0, "targets": []} for row in rows[9:12]
    )
    assert all(
        row["runnerDefaultAdvance"]
        == {
            "first": {"modality": "forced", "destination": 2},
            "second": {"modality": "not-applicable", "destination": None},
            "third": {"modality": "hold", "destination": None},
        }
        for row in rows[9:12]
    )
    assert {
        name
        for name, enabled in four_ball_rows["batting-result.walk"]["statFlags"].items()
        if enabled
    } == {"投球数", "与四球", "打席", "四球"}
    assert {
        name
        for name, enabled in four_ball_rows["batting-result.hit-by-pitch"]["statFlags"].items()
        if enabled
    } == {"投球数", "与死球", "打席", "死球"}
    assert {
        name
        for name, enabled in four_ball_rows["batting-result.intentional-walk"]["statFlags"].items()
        if enabled
    } == {"与四球", "打席", "四球"}
    intentional_precondition = four_ball_rows["batting-result.intentional-walk"][
        "precondition"
    ]
    assert {
        argument["axisId"]: argument["value"]
        for argument in intentional_precondition["args"]
    }["event.perPitch.pitchEventKind"] == "non-pitch-event"

    hit_rows = {row["resultId"]: row for row in rows[12:16]}
    assert all(row["plateAppearanceEnded"] is True for row in hit_rows.values())
    assert all(
        row["countEffect"]
        == {"strikes": {"kind": "reset"}, "balls": {"kind": "reset"}}
        for row in hit_rows.values()
    )
    assert all(
        row["outEffect"] == {"count": 0, "targets": []}
        for row in hit_rows.values()
    )
    total_bases_by_result = {
        "batting-result.single": 1,
        "batting-result.double": 2,
        "batting-result.triple": 3,
        "batting-result.home-run": 4,
    }
    for result_id, total_bases in total_bases_by_result.items():
        row = hit_rows[result_id]
        assert row["statFlags"]["塁打"] is True
        assert f"塁打{total_bases}" in row["remarks"]
    for result_id, base in {
        "batting-result.single": 1,
        "batting-result.double": 2,
        "batting-result.triple": 3,
    }.items():
        row = hit_rows[result_id]
        assert row["batterDestination"] == {"kind": "reach", "base": base}
        assert {
            name for name, enabled in row["statFlags"].items() if enabled
        } == {"投球数", "被安打", "打席", "打数", "安打", "塁打"}
        assert row["runnerDefaultAdvance"] == {
            "first": {"modality": "not-applicable", "destination": None},
            "second": {"modality": "not-applicable", "destination": None},
            "third": {"modality": "not-applicable", "destination": None},
        }
    home_run = hit_rows["batting-result.home-run"]
    assert home_run["batterDestination"] == {"kind": "score"}
    assert home_run["runnerDefaultAdvance"] == {
        "first": {"modality": "optional", "destination": 4},
        "second": {"modality": "optional", "destination": 4},
        "third": {"modality": "optional", "destination": 4},
    }
    assert {
        name for name, enabled in home_run["statFlags"].items() if enabled
    } == {
        "投球数",
        "被安打",
        "被本塁打",
        "失点",
        "打席",
        "打数",
        "安打",
        "本塁打",
        "塁打",
        "得点",
        "打点",
    }
    home_run_precondition = {
        argument["axisId"]: argument["value"]
        for argument in home_run["precondition"]["args"]
    }
    assert home_run_precondition["state.runners"] == "loaded"
    scored_runner_count = sum(
        advance["destination"] == 4
        for advance in home_run["runnerDefaultAdvance"].values()
    )
    assert scored_runner_count + (home_run["batterDestination"]["kind"] == "score") == 4

    ordinary_out_rows = {row["resultId"]: row for row in rows[16:19]}
    for result_id in {"batting-result.batted-out", "batting-result.foul-fly"}:
        row = ordinary_out_rows[result_id]
        assert row["batterDestination"] == {"kind": "out"}
        assert row["outEffect"] == {"count": 1, "targets": ["batter"]}
        assert {
            name for name, enabled in row["statFlags"].items() if enabled
        } == {"投球回算入アウト", "投球数", "打席", "打数"}
    batted_reach = ordinary_out_rows["batting-result.batted-reach"]
    assert batted_reach["batterDestination"] == {"kind": "reach", "base": 1}
    assert batted_reach["runnerDefaultAdvance"] == {
        "first": {"modality": "forced", "destination": 2},
        "second": {"modality": "forced", "destination": 3},
        "third": {"modality": "not-applicable", "destination": None},
    }
    assert batted_reach["outEffect"] == {"count": 0, "targets": []}
    assert {
        name for name, enabled in batted_reach["statFlags"].items() if enabled
    } == {"投球数", "打席", "打数"}
    assert "公式記録上の分類" in batted_reach["remarks"]
    assert "段階2待ち" in batted_reach["remarks"]
    stage2 = _descriptor()["stage2ExternalConstraints"]
    assert "official-scorer-judgment-inputs" in stage2["constraintClasses"]
    assert "official-scorer-judgment-input-contract" in stage2["requiredArtifacts"]

    step56_rows = {row["resultId"]: row for row in rows[19:23]}
    for result_id in {
        "batting-result.double-play",
        "batting-result.line-double-play",
    }:
        row = step56_rows[result_id]
        assert row["batterDestination"] == {"kind": "out"}
        assert row["outEffect"] == {
            "count": 2,
            "targets": ["batter", {"runner": 1}],
        }
        assert {
            name for name, enabled in row["statFlags"].items() if enabled
        } == {"投球回算入アウト", "投球数", "打席", "打数"}
        precondition = {
            argument["axisId"]: argument["value"]
            for argument in row["precondition"]["args"]
        }
        assert precondition["state.outs"] == 0
        assert precondition["state.runners"] == "first"
        assert precondition["state.outs"] + row["outEffect"]["count"] == 2
        assert "OUT3-*対象外" in row["remarks"]

    for result_id in {
        "batting-result.error",
        "batting-result.fielders-choice",
    }:
        row = step56_rows[result_id]
        assert row["batterDestination"] == {"kind": "reach", "base": 1}
        assert row["runnerDefaultAdvance"] == {
            "first": {"modality": "forced", "destination": 2},
            "second": {"modality": "forced", "destination": 3},
            "third": {"modality": "not-applicable", "destination": None},
        }
        assert row["outEffect"] == {"count": 0, "targets": []}
        assert row["statFlags"]["打数"] is True
        assert row["statFlags"]["安打"] is False
        assert "公式記録判断" in row["remarks"]
        assert "段階2待ち" in row["remarks"]
    assert {
        name
        for name, enabled in step56_rows["batting-result.error"]["statFlags"].items()
        if enabled
    } == {"投球数", "失策", "打席", "打数"}
    assert {
        name
        for name, enabled in step56_rows[
            "batting-result.fielders-choice"
        ]["statFlags"].items()
        if enabled
    } == {"投球数", "打席", "打数"}

    step57_rows = {row["resultId"]: row for row in rows[23:26]}
    sacrifice_bunt = step57_rows["batting-result.sacrifice-bunt"]
    assert sacrifice_bunt["batterDestination"] == {"kind": "out"}
    assert sacrifice_bunt["runnerDefaultAdvance"] == {
        "first": {"modality": "optional", "destination": 2},
        "second": {"modality": "optional", "destination": 3},
        "third": {"modality": "not-applicable", "destination": None},
    }
    assert sacrifice_bunt["outEffect"] == {"count": 1, "targets": ["batter"]}
    assert {
        name for name, enabled in sacrifice_bunt["statFlags"].items() if enabled
    } == {"投球回算入アウト", "投球数", "打席", "犠打"}

    sacrifice_fly = step57_rows["batting-result.sacrifice-fly"]
    assert sacrifice_fly["batterDestination"] == {"kind": "out"}
    assert sacrifice_fly["runnerDefaultAdvance"] == {
        "first": {"modality": "not-applicable", "destination": None},
        "second": {"modality": "not-applicable", "destination": None},
        "third": {"modality": "optional", "destination": 4},
    }
    assert sacrifice_fly["outEffect"] == {"count": 1, "targets": ["batter"]}
    assert {
        name for name, enabled in sacrifice_fly["statFlags"].items() if enabled
    } == {"投球回算入アウト", "投球数", "失点", "打席", "犠飛", "得点", "打点"}
    assert "RBI-08" in sacrifice_fly["remarks"]

    sacrifice_bunt_error = step57_rows["batting-result.sacrifice-bunt-error"]
    assert sacrifice_bunt_error["batterDestination"] == {"kind": "reach", "base": 1}
    assert sacrifice_bunt_error["runnerDefaultAdvance"] == {
        "first": {"modality": "forced", "destination": 2},
        "second": {"modality": "forced", "destination": 3},
        "third": {"modality": "not-applicable", "destination": None},
    }
    assert sacrifice_bunt_error["outEffect"] == {"count": 0, "targets": []}
    assert {
        name
        for name, enabled in sacrifice_bunt_error["statFlags"].items()
        if enabled
    } == {"投球数", "失策", "打席", "犠打"}
    assert "公認野球規則9.08" in sacrifice_bunt_error["remarks"]
    assert "安打狙い" in sacrifice_bunt_error["remarks"]
    assert "GAP-09" in sacrifice_bunt_error["remarks"]
    assert "公式記録上の分類" in sacrifice_bunt_error["remarks"]
    assert "段階2待ち" in sacrifice_bunt_error["remarks"]
    gap = next(
        item
        for item in _load_object(GAP_REGISTER_PATH)["gaps"]
        if item["gapId"] == "GAP-09"
    )
    assert gap["state"] == "open"
    assert {"A-3", "FR-004"}.issubset(gap["clauseIds"])
    stage2 = _descriptor()["stage2ExternalConstraints"]
    assert "official-scorer-judgment-inputs" in stage2["constraintClasses"]
    assert "official-scorer-judgment-input-contract" in stage2["requiredArtifacts"]
    assert all(row["statFlags"]["打数"] is False for row in step57_rows.values())


def test_repository_contract_step58_rows_satisfy_constraints() -> None:
    """ステップ58の7行がexact型・参照・XCと代表分岐の宣言を充足する。"""
    contract = _repository_contract()
    rows = contract["matrixRows"][26:33]
    expected_result_ids = {
        "secondary-result.passed-ball",
        "secondary-result.wild-pitch",
        "secondary-result.offensive-interference",
        "secondary-result.batting-interference",
        "secondary-result.obstruction",
        "secondary-result.balk",
        "secondary-result.pitch-clock-violation",
    }

    _validate_schema(contract)
    _validate_references(
        contract,
        vocabulary_checker.validate_manifest(REPOSITORY_ROOT),
    )
    _validate_cross_constraints(contract)
    _validate_vocabulary_axis_coverage(contract)

    assert len(rows) == 7
    assert {row["resultId"] for row in rows} == expected_result_ids
    assert all(row["eventKind"] == "secondary-result" for row in rows)
    step58_rows = {row["resultId"]: row for row in rows}

    for result_id in {
        "secondary-result.passed-ball",
        "secondary-result.wild-pitch",
        "secondary-result.balk",
    }:
        row = step58_rows[result_id]
        assert row["runnerDefaultAdvance"] == {
            "first": {"modality": "optional", "destination": 2},
            "second": {"modality": "optional", "destination": 3},
            "third": {"modality": "optional", "destination": 4},
        }
        assert "代表値" in row["remarks"]
        assert "段階2待ち" in row["remarks"]

    offensive = step58_rows["secondary-result.offensive-interference"]
    assert offensive["batterDestination"] == {"kind": "out"}
    assert offensive["outEffect"] == {"count": 1, "targets": ["batter"]}
    assert offensive["statFlags"]["打数"] is True
    assert "INT-06" in offensive["remarks"]
    assert "INT-07" in offensive["remarks"]

    batting = step58_rows["secondary-result.batting-interference"]
    assert batting["batterDestination"] == {"kind": "reach", "base": 1}
    assert batting["statFlags"]["打数"] is False
    assert batting["statFlags"]["打撃妨害出塁"] is True
    assert all(f"INT-0{number}" in batting["remarks"] for number in range(1, 4))

    obstruction = step58_rows["secondary-result.obstruction"]
    assert obstruction["batterDestination"] == {"kind": "reach", "base": 1}
    assert obstruction["statFlags"]["打数"] is False
    assert obstruction["statFlags"]["走塁妨害出塁"] is True
    assert "INT-04" in obstruction["remarks"]
    assert "INT-05" in obstruction["remarks"]
    assert "ADV-02" in obstruction["remarks"]
    assert "ADV-03" in obstruction["remarks"]

    pitch_clock = step58_rows["secondary-result.pitch-clock-violation"]
    assert pitch_clock["countEffect"] == {
        "strikes": {"kind": "unchanged"},
        "balls": {"kind": "delta", "value": 1},
    }
    assert pitch_clock["batterDestination"] == {"kind": "continue"}
    assert pitch_clock["statFlags"]["投球数"] is False
    assert "規則上の既定ではない" in pitch_clock["remarks"]
    assert "GAP-07" in pitch_clock["remarks"]
    assert "2ストライク未満=S+1・打席継続" in pitch_clock["remarks"]
    assert "2ストライク=打者アウト・打席終了・S/B reset" in pitch_clock[
        "remarks"
    ]
    assert (
        "打者側ピッチクロック違反のために許す"
        "batterDestination.kind=out経路は現状の規範行から到達不能"
    ) in pitch_clock["remarks"]
    gap = next(
        item
        for item in _load_object(GAP_REGISTER_PATH)["gaps"]
        if item["gapId"] == "GAP-07"
    )
    assert gap["state"] == "open"
    assert {"E-1", "FR-004"}.issubset(gap["clauseIds"])


def test_repository_contract_records_step58_and_step59_review_as_not_performed() -> None:
    """ステップ58・59の独立確認を未実施のまま記録する。"""
    provenance = _repository_contract()["provenance"]

    assert provenance["authorId"] == "codex"
    assert provenance["independentVerifierId"] == "not-performed"
    assert "independentReview" not in provenance
    assert {source["sourceId"] for source in provenance["sources"]}.issuperset(
        {
            "req:E-1",
            "req:FR-003",
            "req:A-3",
            "req:ADV-03",
            "req:RBI-08",
            "req:INT-01",
            "req:INT-02",
            "req:INT-03",
            "req:INT-04",
            "req:INT-05",
            "req:INT-06",
            "req:INT-07",
            "req:A-4",
            "req:FR-027",
            "obr:9.02(a)(1)",
            "obr:9.08",
            "docs/legacy/research/input-screen.md:151",
            "docs/legacy/research/input-screen.md:152",
            "docs/legacy/research/input-screen.md:155",
            "docs/legacy/research/input-screen.md:161",
            "docs/legacy/research/input-screen.md:162",
            "docs/legacy/research/input-screen.md:163",
            "docs/legacy/research/input-screen.md:70",
            "docs/legacy/research/input-screen.md:71",
        }
    )
    assert provenance["attestations"] == [
        {"attestationId": "direct-source-clause-review", "response": False},
        {"attestationId": "author-work-exposure", "response": "not-performed"},
        {"attestationId": "source-support-judgment", "response": False},
    ]
    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="宣誓応答が充足値でない",
    ):
        provenance_checker.validate_provenance(
            REPOSITORY_ROOT,
            provenance,
            schema_value=_schema(),
        )


def test_step53_four_ball_results_use_identity_partition_without_gap() -> None:
    """四死球系3語彙がrequiredSet①の単一行規則に属する。"""
    rules = _load_object(REQUIRED_SET_ROW_RULES_PATH)
    identity_rule = next(
        rule
        for rule in rules["partitionRules"]
        if rule["partitionRuleId"] == "identity"
    )
    result_ids = {
        "batting-result.walk",
        "batting-result.hit-by-pitch",
        "batting-result.intentional-walk",
    }

    assert identity_rule["partitions"] == ["identity"]
    assert result_ids.issubset(identity_rule["vocabularyIds"])


def test_step54_hit_results_use_identity_partition_without_gap() -> None:
    """安打系4語彙がrequiredSet①の単一行規則に属する。"""
    rules = _load_object(REQUIRED_SET_ROW_RULES_PATH)
    identity_rule = next(
        rule
        for rule in rules["partitionRules"]
        if rule["partitionRuleId"] == "identity"
    )
    result_ids = {
        "batting-result.single",
        "batting-result.double",
        "batting-result.triple",
        "batting-result.home-run",
    }

    assert identity_rule["partitions"] == ["identity"]
    assert result_ids.issubset(identity_rule["vocabularyIds"])


def test_step55_ordinary_out_results_use_identity_partition_without_gap() -> None:
    """凡打系3語彙がrequiredSet①の単一行規則に属する。"""
    rules = _load_object(REQUIRED_SET_ROW_RULES_PATH)
    identity_rule = next(
        rule
        for rule in rules["partitionRules"]
        if rule["partitionRuleId"] == "identity"
    )
    result_ids = {
        "batting-result.batted-out",
        "batting-result.batted-reach",
        "batting-result.foul-fly",
    }

    assert identity_rule["partitions"] == ["identity"]
    assert result_ids.issubset(identity_rule["vocabularyIds"])


def test_step56_results_use_identity_partition_without_gap() -> None:
    """併殺系・失策系4語彙がrequiredSet①の単一行規則に属する。"""
    rules = _load_object(REQUIRED_SET_ROW_RULES_PATH)
    identity_rule = next(
        rule
        for rule in rules["partitionRules"]
        if rule["partitionRuleId"] == "identity"
    )
    result_ids = {
        "batting-result.double-play",
        "batting-result.line-double-play",
        "batting-result.error",
        "batting-result.fielders-choice",
    }

    assert identity_rule["partitions"] == ["identity"]
    assert result_ids.issubset(identity_rule["vocabularyIds"])
    error_type_assignment = next(
        assignment
        for assignment in rules["axisAssignments"]
        if assignment["axisId"] == "error-type"
    )
    assert error_type_assignment["role"] == "not-result-id-source"
    assert "eventKind" not in error_type_assignment


def test_step57_sacrifice_results_use_identity_partition_without_gap() -> None:
    """犠打系3語彙がrequiredSet①の単一行規則に属する。"""
    rules = _load_object(REQUIRED_SET_ROW_RULES_PATH)
    identity_rule = next(
        rule
        for rule in rules["partitionRules"]
        if rule["partitionRuleId"] == "identity"
    )
    result_ids = {
        "batting-result.sacrifice-bunt",
        "batting-result.sacrifice-fly",
        "batting-result.sacrifice-bunt-error",
    }

    assert identity_rule["partitions"] == ["identity"]
    assert result_ids.issubset(identity_rule["vocabularyIds"])


def test_repository_batting_result_rows_exactly_cover_the_vocabulary_axis() -> None:
    """打撃結果の規範行が語彙シードの26値をexact-setで覆う。"""
    contract = _repository_contract()

    _validate_vocabulary_axis_coverage(contract)

    batting_rows = [
        row for row in contract["matrixRows"] if row["eventKind"] == "batting-result"
    ]
    assert len(batting_rows) == 26


def test_batting_result_vocabulary_coverage_is_red_when_a_value_is_missing() -> None:
    """打撃結果の規範行を1値欠くとexact-set検査が拒む。"""
    contract = _repository_contract()
    contract["matrixRows"] = [
        row
        for row in contract["matrixRows"]
        if row["resultId"] != "batting-result.sacrifice-bunt-error"
    ]

    with pytest.raises(VocabularyAxisCoverageError, match="missing=.*sacrifice-bunt-error"):
        _validate_vocabulary_axis_coverage(contract)


def test_batting_result_vocabulary_coverage_is_red_for_an_extra_value() -> None:
    """語彙シードに無い打撃結果を足すとexact-set検査が拒む。"""
    contract = _repository_contract()
    extra = copy.deepcopy(contract["matrixRows"][25])
    extra["resultId"] = "batting-result.not-declared"
    contract["matrixRows"].append(extra)

    with pytest.raises(VocabularyAxisCoverageError, match="unexpected=.*not-declared"):
        _validate_vocabulary_axis_coverage(contract)


def test_repository_secondary_result_rows_exactly_cover_the_vocabulary_axis() -> None:
    """打撃結果2の規範行が語彙シードの7値をexact-setで覆う。"""
    contract = _repository_contract()

    _validate_vocabulary_axis_coverage(contract)

    secondary_rows = [
        row
        for row in contract["matrixRows"]
        if row["eventKind"] == "secondary-result"
    ]
    assert len(secondary_rows) == 7


def test_secondary_result_vocabulary_coverage_is_red_when_a_value_is_missing() -> None:
    """打撃結果2の規範行を1値欠くとexact-set検査が拒む。"""
    contract = _repository_contract()
    contract["matrixRows"] = [
        row
        for row in contract["matrixRows"]
        if row["resultId"] != "secondary-result.pitch-clock-violation"
    ]

    with pytest.raises(
        VocabularyAxisCoverageError,
        match="axisIds=.*secondary-result.*missing=.*pitch-clock-violation",
    ):
        _validate_vocabulary_axis_coverage(contract)


def test_secondary_result_vocabulary_coverage_is_red_for_an_extra_value() -> None:
    """語彙シードに無い打撃結果2を足すとexact-set検査が拒む。"""
    contract = _repository_contract()
    extra = copy.deepcopy(
        next(
            row
            for row in contract["matrixRows"]
            if row["resultId"] == "secondary-result.pitch-clock-violation"
        )
    )
    extra["resultId"] = "secondary-result.not-declared"
    contract["matrixRows"].append(extra)

    with pytest.raises(
        VocabularyAxisCoverageError,
        match="axisIds=.*secondary-result.*unexpected=.*not-declared",
    ):
        _validate_vocabulary_axis_coverage(contract)


def test_repository_per_pitch_mapping_covers_all_materialized_matrix_rows() -> None:
    """実資産の全matrixRowsを毎球入力写像へ1回ずつ帰属させる。"""
    contract = _repository_contract()
    mapping = next(
        item
        for item in contract["mustOperationCoverage"]["mappings"]
        if item["operationType"] == "per-pitch-input"
    )
    actual = {
        schema_checker.canonicalize_json(reference["coordinate"])
        for reference in mapping["rowRefs"]
        if reference["layer"] == "matrixRows"
    }
    expected = {
        schema_checker.canonicalize_json(
            {
                "eventKind": row["eventKind"],
                "resultId": row["resultId"],
                "precondition": row["precondition"],
            }
        )
        for row in contract["matrixRows"]
    }

    assert actual == expected
    assert len(mapping["rowRefs"]) == len(contract["matrixRows"]) == 42


def test_so03_deferred_partition_difference_remains_declared_and_open() -> None:
    """SO-03の要求2件と実体1行の差を段階2待ちとして保持する。"""
    contract = _repository_contract()
    schema = _schema()
    descriptor = _descriptor()
    rules = _load_object(REQUIRED_SET_ROW_RULES_PATH)
    gap_register = _load_object(GAP_REGISTER_PATH)

    deferment = schema["x-pitchlog-deferred-row-requirements"]["deferments"][0]
    partition_rule = next(
        rule
        for rule in rules["partitionRules"]
        if rule["partitionRuleId"] == deferment["partitionRuleId"]
    )
    rows = [
        row
        for row in contract["matrixRows"]
        if row["resultId"] == "batting-result.dropped-third-strike"
    ]
    gap = next(
        item for item in gap_register["gaps"] if item["gapId"] == deferment["gapId"]
    )

    assert deferment["status"] == "open-stage-2"
    assert partition_rule["partitions"] == ["safe", "out"]
    assert deferment["requiredPartitions"] == partition_rule["partitions"]
    assert deferment["materializedPartitions"] == ["safe"]
    assert deferment["missingPartitions"] == ["out"]
    assert deferment["requiredRowCount"] == 2
    assert deferment["materializedRowCount"] == len(rows) == 1
    assert deferment["stage2DeclarationAsset"] == (
        "contracts/state-transition/input_axes_descriptor_v1.json"
    )
    assert deferment["stage2DeclarationPointer"] == "/stage2ExternalConstraints"
    assert deferment["deferredConstraintClass"] == (
        "third-out-type-observation-input"
    )
    assert deferment["requiredArtifact"] == "third-out-type-input-contract"
    stage2 = descriptor["stage2ExternalConstraints"]
    assert deferment["deferredConstraintClass"] in stage2["constraintClasses"]
    assert deferment["requiredArtifact"] in stage2["requiredArtifacts"]
    assert gap["state"] == "open"
    assert {"SO-03", "XC-13"}.issubset(gap["clauseIds"])


def test_provenance_declares_machine_and_human_assurance_boundaries() -> None:
    """provenanceの機械保証と人間統制の境界を資産側で宣言する。"""
    policy = _schema()["x-pitchlog-provenance-policy"]
    official_rules = policy["sourceKinds"]["official-baseball-rules"]
    assurance = policy["assuranceBoundary"]

    assert official_rules["machineCapability"] == "identifier-format-only"
    assert set(official_rules["notMechanicallyVerified"]) == {
        "rule-number-existence",
        "rule-content",
    }
    assert "official-rule-number-exists-and-content-is-correct" in assurance[
        "humanControls"
    ]
    assert "ステップ43" in assurance["step43Excluded"]


def test_provenance_is_required_at_contract_top_level() -> None:
    """provenanceを規範行の列を増やさず契約単位で必須にする。"""
    contract = _minimal_contract()
    del contract["provenance"]

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="必須キー不足: .*provenance",
    ):
        _validate(contract)


def test_same_recorded_author_and_independent_verifier_is_red() -> None:
    """記録上の作成者と独立確認者が同一のprovenanceを拒否する。"""
    contract = _minimal_contract()
    contract["provenance"]["independentVerifierId"] = contract["provenance"][
        "authorId"
    ]

    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="作成者と独立確認者が記録上同一",
    ):
        _validate(contract)


def test_legacy_research_only_provenance_is_red() -> None:
    """パスと行が実在しても旧調査資料だけの由来を拒否する。"""
    contract = _minimal_contract()
    contract["provenance"]["sources"] = [
        {
            "sourceKind": "legacy-research",
            "sourceId": "docs/legacy/research/data-layer.md:197",
        }
    ]

    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="対象種別を支える優先典拠が無い",
    ):
        _validate(contract)


def test_missing_provenance_attestation_is_red() -> None:
    """①由来記録の3宣誓項目から1件欠けたprovenanceを拒否する。"""
    contract = _minimal_contract()
    contract["provenance"]["attestations"].pop()

    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="宣誓項目がexact-set不一致",
    ):
        _validate(contract)


def test_unknown_requirement_source_id_is_red() -> None:
    """要件書の機械抽出集合に実在しない典拠IDを拒否する。"""
    contract = _minimal_contract()
    contract["provenance"]["sources"][0]["sourceId"] = "req:FR-999"

    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="要件書の典拠IDが実在しない",
    ):
        _validate(contract)


def test_official_rule_source_checks_format_without_claiming_existence() -> None:
    """公認野球規則は条番号形式だけを機械検査する。"""
    contract = _minimal_contract()
    contract["provenance"]["sources"] = [
        {
            "sourceKind": "official-baseball-rules",
            "sourceId": "obr:99.99(z)",
        }
    ]

    _validate(contract)


def test_vocabulary_source_alone_is_limited_to_vocabulary_origin() -> None:
    """vocab.ts由来だけの記録を語彙対象にのみ許す。"""
    provenance = _provenance()
    provenance["sources"] = [
        {
            "sourceKind": "legacy-vocab-mirror",
            "sourceId": "batting-result.single",
        }
    ]

    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="対象種別を支える優先典拠が無い",
    ):
        provenance_checker.validate_provenance(REPOSITORY_ROOT, provenance)

    provenance["subjectKind"] = "vocabulary-origin"
    provenance_checker.validate_provenance(REPOSITORY_ROOT, provenance)


def _coverage_mapping(
    contract: Mapping[str, Any], operation_type: str
) -> dict[str, Any]:
    """指定操作種別の被覆写像を返す。

    Args:
        contract: 状況判定契約。
        operation_type: 検索する操作種別。

    Returns:
        一意な被覆写像。
    """
    matches = [
        mapping
        for mapping in contract["mustOperationCoverage"]["mappings"]
        if mapping["operationType"] == operation_type
    ]
    assert len(matches) == 1
    return matches[0]


def test_must_operation_coverage_declares_six_required_and_one_conditional_type() -> None:
    """4.0-4のMust 6種とFR-040採用時の第7種を資産側へ宣言する。"""
    configuration = _must_operation_coverage_configuration()
    contract = _minimal_contract()
    declared_required_types = {
        operation["operationType"]
        for operation in configuration["requiredOperations"]
    }
    mapped_types = {
        mapping["operationType"]
        for mapping in contract["mustOperationCoverage"]["mappings"]
    }

    assert mapped_types == declared_required_types
    _validate(contract)


def test_coverage_reference_to_unknown_normative_row_is_red() -> None:
    """①入力座標を実在行へ解決できない被覆写像を拒否する。"""
    contract = _minimal_contract()
    reference = _coverage_mapping(contract, "substitution")["rowRefs"][0]
    reference["coordinate"]["precondition"] = {
        "op": "eq",
        "axisId": "state.outs",
        "value": 1,
    }

    with pytest.raises(MustOperationCoverageError, match="①写像の参照先"):
        _validate(contract)


def test_coverage_operation_type_must_match_row_layer_and_discriminator() -> None:
    """②操作種別を異なる規範行層へ結び付けた写像を拒否する。"""
    contract = _minimal_contract()
    _coverage_mapping(contract, "substitution")["rowRefs"] = copy.deepcopy(
        _coverage_mapping(contract, "undo")["rowRefs"]
    )

    with pytest.raises(MustOperationCoverageError, match="②操作種別と規範行層"):
        _validate(contract)


def test_coverage_operation_mapping_must_not_be_duplicated() -> None:
    """③同じ操作種別を2回写像した契約を拒否する。"""
    contract = _minimal_contract()
    contract["mustOperationCoverage"]["mappings"].append(
        copy.deepcopy(_coverage_mapping(contract, "substitution"))
    )

    with pytest.raises(MustOperationCoverageError, match="③操作種別の写像が重複"):
        _validate(contract)


def test_unassigned_normative_row_is_red() -> None:
    """④どのMust操作にも帰属しない規範行を拒否する。"""
    contract = _minimal_contract()
    unassigned = copy.deepcopy(contract["matrixRows"][0])
    unassigned["precondition"] = {
        "op": "and",
        "args": [
            {"op": "eq", "axisId": "state.outs", "value": 1},
            {"op": "eq", "axisId": "state.runners", "value": "empty"},
        ],
    }
    unassigned["remarks"] = "未帰属行"
    contract["matrixRows"].append(unassigned)

    with pytest.raises(MustOperationCoverageError, match="④いずれの操作種別にも"):
        _validate(contract)


def test_per_pitch_subtypes_must_be_an_exact_set() -> None:
    """⑤毎球入力から3下位分類の1つを落とした契約を拒否する。"""
    contract = _minimal_contract()
    runner_row = next(
        row for row in contract["matrixRows"] if row["eventKind"] == "runner-event"
    )
    contract["matrixRows"].remove(runner_row)
    mapping = _coverage_mapping(contract, "per-pitch-input")
    mapping["rowRefs"] = [
        reference
        for reference in mapping["rowRefs"]
        if reference["coordinate"]["eventKind"] != "runner-event"
    ]

    with pytest.raises(MustOperationCoverageError, match="⑤毎球入力の3下位分類"):
        _validate(contract)


def test_unadopted_fr040_requires_an_explicit_vector_exclusion() -> None:
    """FR-040未採用をvectors[]へ宣言しない除外を拒否する。"""
    contract = _minimal_contract()
    manifest = _resolved_vector_manifest()
    configuration = _must_operation_coverage_configuration()
    rule = configuration["manifestOmissionResolution"]
    manifest[rule["collection"]][0][rule["exclusionsField"]] = []

    with pytest.raises(
        MustOperationCoverageError,
        match=r"FR-040の採用状態とvectors\[\]の除外宣言が一致しない",
    ):
        _validate(contract, vector_manifest=manifest)


def test_vector_manifest_unavailability_is_red() -> None:
    """vectors[]を解決不能な被覆検査を未確認の緑にしない。"""
    contract = _minimal_contract()

    with pytest.raises(
        MustOperationCoverageError,
        match=r"vectors\[\]マニフェストを解決できず",
    ):
        _validate(contract, vector_manifest=None)


def test_fr040_adoption_adds_the_seventh_covered_operation() -> None:
    """FR-040採用時だけ状態補正を第7種として被覆する。"""
    contract = _minimal_contract()
    _add_state_correction_operation(contract)

    _validate(contract, adopted_clause_ids=frozenset({"req:FR-040"}))


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
    row = next(
        row
        for row in contract["operationRows"]
        if row["operationKind"] == operation_kind
    )

    _validate(contract)
    assert row["clauseId"] == clause_id


def test_state_correction_is_the_fr040_conditional_operation_kind() -> None:
    """状態補正をFR-040採用時だけの条件付き操作として宣言する。"""
    contract = _minimal_contract()
    _add_state_correction_operation(contract)

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


UNDO_ROW_COLUMNS = (
    "targetKind",
    "precondition",
    "stateEffect",
    "historyEffect",
    "operationResult",
    "guaranteeMode",
    "remarks",
)


def test_undo_row_is_closed_to_the_seven_d8_columns() -> None:
    """undoRowsの行をD-8が定める7列だけに閉じる。"""
    undo_row = _schema()["$defs"]["undoRow"]

    assert tuple(undo_row["required"]) == UNDO_ROW_COLUMNS
    assert set(undo_row["properties"]) == set(UNDO_ROW_COLUMNS)
    assert undo_row["additionalProperties"] is False
    assert not {
        "operationKind",
        "clauseId",
        "payloadShape",
    } & set(undo_row["properties"])


@pytest.mark.parametrize("missing_column", UNDO_ROW_COLUMNS)
def test_each_missing_undo_row_column_is_red(missing_column: str) -> None:
    """D-8のundo規範行7列のいずれかが欠けた行を拒否する。"""
    contract = _minimal_contract()
    del contract["undoRows"][0][missing_column]

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match=rf"必須キー不足: .*{missing_column}",
    ):
        _validate(contract)


def test_unknown_undo_row_column_is_red() -> None:
    """D-8に無いundo規範行の列を拒否する。"""
    contract = _minimal_contract()
    contract["undoRows"][0]["operationKind"] = "undo"

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="未知キー: .*operationKind",
    ):
        _validate(contract)


def test_target_kind_undo_is_rejected_by_the_closed_enum() -> None:
    """undoをundoするtargetKindを交差制約ではなくenumで拒否する。"""
    contract = _minimal_contract()
    contract["undoRows"][0]["targetKind"] = "undo"
    _sync_case_coordinate(contract, "undoRows")

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="enum外の値: 'undo'",
    ):
        _validate(contract)


def test_guarantee_mode_outside_the_closed_enum_is_red() -> None:
    """D-8に無いguaranteeModeを拒否する。"""
    contract = _minimal_contract()
    contract["undoRows"][0]["guaranteeMode"] = "best-effort"

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="enum外の値: 'best-effort'",
    ):
        _validate(contract)


def test_undo_history_effect_is_closed_to_zero_or_one_pop() -> None:
    """undoの履歴効果で2件以上を一度に取り消す指定を拒否する。"""
    contract = _minimal_contract()
    contract["undoRows"][0]["historyEffect"] = {"pops": 2}

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="enum外の値: 2",
    ):
        _validate(contract)


def test_undo_history_effect_is_closed_to_the_pops_field() -> None:
    """undoの履歴効果へ未知フィールドを追加した行を拒否する。"""
    contract = _minimal_contract()
    contract["undoRows"][0]["historyEffect"]["kind"] = "undo"

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="未知キー: .*kind",
    ):
        _validate(contract)


def test_state_correction_target_requires_fr040_adoption() -> None:
    """FR-040未採用時の状態補正targetKindを拒否する。"""
    contract = _minimal_contract()
    contract["undoRows"][0]["targetKind"] = "state-correction"
    _sync_case_coordinate(contract, "undoRows")

    with pytest.raises(UndoRowConstraintError, match="未採用の条件付きtargetKind"):
        _validate(contract)


def test_state_correction_target_is_accepted_when_fr040_is_adopted() -> None:
    """FR-040採用時だけ状態補正targetKindを受理する。"""
    contract = _minimal_contract()
    _add_state_correction_operation(contract)
    contract["undoRows"][0]["targetKind"] = "state-correction"
    _sync_case_coordinate(contract, "undoRows")

    _validate(contract, adopted_clause_ids=frozenset({"req:FR-040"}))


def test_xc09_liveness_only_is_red_at_history_depth_d() -> None:
    """XC-09: 履歴深さDの行でliveness-onlyを拒否する。"""
    contract = _minimal_contract()
    row = contract["undoRows"][0]
    row["precondition"] = {
        "op": "eq",
        "axisId": "history.depth",
        "value": "D",
    }
    row["guaranteeMode"] = "liveness-only"
    _sync_case_coordinate(contract, "undoRows")

    with pytest.raises(UndoRowConstraintError, match="XC-09"):
        _validate(contract)


def test_xc09_liveness_only_is_accepted_only_at_d_plus_one() -> None:
    """XC-09: descriptorのD+1座標だけでliveness-onlyを受理する。"""
    contract = _minimal_contract()
    row = contract["undoRows"][0]
    row["precondition"] = {
        "op": "eq",
        "axisId": "history.scenarioLength",
        "value": "D+1",
    }
    row["guaranteeMode"] = "liveness-only"
    _sync_case_coordinate(contract, "undoRows")

    _validate(contract)


def test_xc09_rejects_a_precondition_that_also_allows_d_or_below() -> None:
    """XC-09: D+1以外も許す述語を判定不能側へ推測せず拒否する。"""
    contract = _minimal_contract()
    row = contract["undoRows"][0]
    row["precondition"] = {
        "op": "in",
        "axisId": "history.scenarioLength",
        "values": ["D", "D+1"],
    }
    row["guaranteeMode"] = "liveness-only"
    _sync_case_coordinate(contract, "undoRows")

    with pytest.raises(UndoRowConstraintError, match="XC-09"):
        _validate(contract)


def test_undo_precondition_must_use_only_history_context_axes() -> None:
    """undoRowsのpreconditionから状態軸を参照する行を拒否する。"""
    contract = _minimal_contract()
    contract["undoRows"][0]["precondition"] = {
        "op": "eq",
        "axisId": "state.outs",
        "value": 0,
    }
    _sync_case_coordinate(contract, "undoRows")

    with pytest.raises(UndoRowConstraintError, match="履歴文脈軸だけ"):
        _validate(contract)


def test_repository_step65_empty_history_row_and_mapping() -> None:
    """空履歴だけを偽の逆差分なしで規範行と操作写像へ置く。"""
    contract = _repository_contract()
    _validate_schema(contract)
    _validate_undo_rows(contract, frozenset())
    _validate_references(contract, vocabulary_checker.validate_manifest(REPOSITORY_ROOT))

    assert len(contract["matrixRows"]) == 42
    assert len(contract["operationRows"]) == 6
    assert len(contract["undoRows"]) == 1
    row = contract["undoRows"][0]
    assert set(row) == set(UNDO_ROW_COLUMNS)
    assert row["targetKind"] == "confirmed-play"
    assert row["precondition"] == {
        "op": "eq", "axisId": "history.depth", "value": 0,
    }
    assert row["stateEffect"] == _unchanged_state_effect()
    assert row["historyEffect"] == {"pops": 0}
    assert row["operationResult"] == "nothing-to-undo"
    assert row["guaranteeMode"] == "full-equality"
    assert "適用側の行をこの行で充足したとは主張しない" in row["remarks"]

    mappings = {
        mapping["operationType"]: mapping["rowRefs"]
        for mapping in contract["mustOperationCoverage"]["mappings"]
    }
    assert mappings["undo"] == [_row_reference("undoRows", row)]
    assert mappings["per-pitch-input"] == [
        _row_reference("matrixRows", item) for item in contract["matrixRows"]
    ]
    for operation_kind in (
        "substitution", "game-end-declaration", "adhoc-registration",
    ):
        assert mappings[operation_kind] == [
            _row_reference("operationRows", item)
            for item in contract["operationRows"]
            if item["operationKind"] == operation_kind
        ]
    assert "tiebreak-start" not in mappings
    sources = {item["sourceId"] for item in contract["provenance"]["sources"]}
    assert "req:FR-006" in sources
    assert not any(source.startswith("adr:") for source in sources)
    assert contract["provenance"]["independentVerifierId"] == "not-performed"


@pytest.mark.parametrize("missing_column", UNDO_ROW_COLUMNS)
def test_repository_step65_missing_undo_column_is_red(missing_column: str) -> None:
    """実資産のundo行から必須7列のいずれかを削る変異を拒否する。"""
    contract = _repository_contract()
    del contract["undoRows"][0][missing_column]

    with pytest.raises(schema_checker.DescriptorCheckError, match="必須キー不足"):
        _validate_schema(contract)


def test_repository_step65_unknown_undo_column_is_red() -> None:
    """実資産のundo行へD-8に無い列を足す変異を拒否する。"""
    contract = _repository_contract()
    contract["undoRows"][0]["payloadShape"] = {}

    with pytest.raises(schema_checker.DescriptorCheckError, match="未知キー"):
        _validate_schema(contract)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("targetKind", "undo"),
        ("operationResult", "rejected-precondition"),
        ("guaranteeMode", "best-effort"),
    ],
)
def test_repository_step65_closed_enum_rejects_mutation(
    field: str, value: str,
) -> None:
    """実資産のundo対象・操作結果・保証モードのenum外変異を拒否する。"""
    contract = _repository_contract()
    contract["undoRows"][0][field] = value

    with pytest.raises(schema_checker.DescriptorCheckError, match="enum外の値"):
        _validate_schema(contract)


@pytest.mark.parametrize("history_effect", [{"pops": 2}, {"pops": 0, "kind": "undo"}])
def test_repository_step65_history_pop_is_closed(history_effect: dict[str, Any]) -> None:
    """実資産のundo履歴効果を0または1件のpopだけに閉じる。"""
    contract = _repository_contract()
    contract["undoRows"][0]["historyEffect"] = history_effect

    with pytest.raises(schema_checker.DescriptorCheckError):
        _validate_schema(contract)


def test_repository_step65_non_history_precondition_is_red() -> None:
    """実資産のundo行が履歴文脈以外の軸を参照する変異を拒否する。"""
    contract = _repository_contract()
    contract["undoRows"][0]["precondition"] = {
        "op": "eq", "axisId": "state.outs", "value": 0,
    }

    with pytest.raises(UndoRowConstraintError, match="履歴文脈軸だけ"):
        _validate_undo_rows(contract, frozenset())


def test_repository_step65_liveness_only_at_depth_d_is_red() -> None:
    """実資産の深さD行をliveness-onlyへ変異させるとXC-09で拒否する。"""
    contract = _repository_contract()
    row = contract["undoRows"][0]
    row["precondition"] = {
        "op": "eq", "axisId": "history.depth", "value": "D",
    }
    row["guaranteeMode"] = "liveness-only"

    with pytest.raises(UndoRowConstraintError, match="XC-09"):
        _validate_undo_rows(contract, frozenset())


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
        "batting_results": frozenset({"batting-result.single"}),
        "secondary_results": frozenset({"batting-result.single"}),
    }

    with pytest.raises(
        ReferenceConstraintError,
        match=r"resultId='batting-result.single'; matches=2",
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
    runner_index = next(
        index
        for index, row in enumerate(contract["matrixRows"])
        if row["eventKind"] == "runner-event"
    )
    contract["matrixRows"][0], contract["matrixRows"][runner_index] = (
        contract["matrixRows"][runner_index],
        contract["matrixRows"][0],
    )


def _set_secondary_result(contract: dict[str, Any]) -> None:
    """matrixRows先頭行を副次結果行へ入れ替える。"""
    secondary_index = next(
        index
        for index, row in enumerate(contract["matrixRows"])
        if row["eventKind"] == "secondary-result"
    )
    contract["matrixRows"][0], contract["matrixRows"][secondary_index] = (
        contract["matrixRows"][secondary_index],
        contract["matrixRows"][0],
    )


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
    _set_secondary_result(contract)
    row = contract["matrixRows"][0]
    row["countEffect"] = {
        "strikes": {"kind": "reset"},
        "balls": {"kind": "reset"},
    }
    row["plateAppearanceEnded"] = True
    row["batterDestination"] = {"kind": "not-applicable"}

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
    _set_secondary_result(contract)
    row = contract["matrixRows"][0]
    row["countEffect"] = {
        "strikes": {"kind": "reset"},
        "balls": {"kind": "reset"},
    }
    row["plateAppearanceEnded"] = True
    row["batterDestination"] = {"kind": "score"}

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


def test_repository_contract_step59_rows_satisfy_runner_event_constraints() -> None:
    """作戦3系統を各1行とし、走者イベントの固定列と既定進塁を検査する。"""
    contract = _repository_contract()
    rows = contract["matrixRows"][33:36]
    expected_result_ids = {
        "strategy-category.steal",
        "strategy-category.bunt",
        "strategy-category.hit-and-run",
    }

    _validate_schema(contract)
    _validate_references(
        contract,
        vocabulary_checker.validate_manifest(REPOSITORY_ROOT),
    )
    _validate_cross_constraints(contract)
    _validate_vocabulary_axis_coverage(contract)

    assert len(rows) == 3
    assert {row["resultId"] for row in rows} == expected_result_ids
    assert all(row["eventKind"] == "runner-event" for row in rows)
    assert all(
        row["countEffect"]
        == {"strikes": {"kind": "unchanged"}, "balls": {"kind": "unchanged"}}
        for row in rows
    )
    assert all(row["plateAppearanceEnded"] == "not-applicable" for row in rows)
    assert all(row["batterDestination"] == {"kind": "not-applicable"} for row in rows)
    assert all(row["outEffect"] == {"count": 0, "targets": []} for row in rows)
    assert all(row["statFlags"]["投球回算入アウト"] is False for row in rows)
    assert all(row["statFlags"]["投球数"] is True for row in rows)
    assert all(
        "event.perPitch.runnerEventPayload"
        not in {leaf["axisId"] for leaf in _predicate_leaves(row["precondition"])}
        for row in rows
    )

    by_result = {row["resultId"]: row for row in rows}
    optional_advance = {
        "first": {"modality": "optional", "destination": 2},
        "second": {"modality": "not-applicable", "destination": None},
        "third": {"modality": "not-applicable", "destination": None},
    }
    assert by_result["strategy-category.steal"]["runnerDefaultAdvance"] == optional_advance
    assert (
        by_result["strategy-category.hit-and-run"]["runnerDefaultAdvance"]
        == optional_advance
    )
    assert by_result["strategy-category.bunt"]["runnerDefaultAdvance"] == {
        "first": {"modality": "hold", "destination": None},
        "second": {"modality": "not-applicable", "destination": None},
        "third": {"modality": "not-applicable", "destination": None},
    }
    assert all("本行単独からは導出しない" in row["remarks"] for row in rows)
    assert "旧input-screen:155" in by_result["strategy-category.steal"]["remarks"]
    assert "旧input-screen:155" in by_result["strategy-category.hit-and-run"]["remarks"]


def test_step59_strategy_results_use_identity_partition_without_gap() -> None:
    """作戦3系統がrequiredSet①のidentity各1行に属する。"""
    rules = _load_object(REQUIRED_SET_ROW_RULES_PATH)
    identity_rule = next(
        rule
        for rule in rules["partitionRules"]
        if rule["partitionRuleId"] == "identity"
    )

    assert identity_rule["partitions"] == ["identity"]
    assert {
        "strategy-category.steal",
        "strategy-category.bunt",
        "strategy-category.hit-and-run",
    }.issubset(identity_rule["vocabularyIds"])


def test_step60_runner_event_coverage_declaration_uses_three_axis_union() -> None:
    """走者イベント9値を3語彙軸の和集合として宣言する。"""
    coverage = _schema()["x-pitchlog-vocabulary-axis-coverage"]

    assert coverage["coverageSets"] == [
        {"axisIds": ["batting-result"], "rowDiscriminatorValue": "batting-result"},
        {
            "axisIds": ["secondary-result"],
            "rowDiscriminatorValue": "secondary-result",
        },
        {
            "axisIds": [
                "strategy-category",
                "pitcher-pickoff-destination",
                "catcher-pickoff-destination",
            ],
            "rowDiscriminatorValue": "runner-event",
        },
    ]


def test_repository_contract_step60_pickoff_rows_satisfy_constraints() -> None:
    """投手・捕手の牽制6値を各1行の非投球走者イベントとして検査する。"""
    contract = _repository_contract()
    rows = contract["matrixRows"][36:]
    expected_result_ids = {
        "pitcher-pickoff-destination.first",
        "pitcher-pickoff-destination.second",
        "pitcher-pickoff-destination.third",
        "catcher-pickoff-destination.first",
        "catcher-pickoff-destination.second",
        "catcher-pickoff-destination.third",
    }
    base_by_suffix = {"first": "first", "second": "second", "third": "third"}

    _validate_schema(contract)
    _validate_references(
        contract,
        vocabulary_checker.validate_manifest(REPOSITORY_ROOT),
    )
    _validate_cross_constraints(contract)
    _validate_vocabulary_axis_coverage(contract)

    assert len(contract["matrixRows"]) == 42
    assert len(rows) == 6
    assert {row["resultId"] for row in rows} == expected_result_ids
    assert all(row["eventKind"] == "runner-event" for row in rows)
    assert all(
        row["countEffect"]
        == {"strikes": {"kind": "unchanged"}, "balls": {"kind": "unchanged"}}
        for row in rows
    )
    assert all(row["plateAppearanceEnded"] == "not-applicable" for row in rows)
    assert all(row["batterDestination"] == {"kind": "not-applicable"} for row in rows)
    assert all(row["outEffect"] == {"count": 0, "targets": []} for row in rows)
    assert all(not any(row["statFlags"].values()) for row in rows)
    assert all("実結果であり、本行の既定ではない" in row["remarks"] for row in rows)

    for row in rows:
        suffix = row["resultId"].rsplit(".", maxsplit=1)[1]
        target_base = base_by_suffix[suffix]
        leaves = {
            leaf["axisId"]: leaf["value"]
            for leaf in _predicate_leaves(row["precondition"])
        }
        assert leaves["state.runners"] == target_base
        assert leaves["event.perPitch.pitchEventKind"] == "non-pitch-event"
        assert row["runnerDefaultAdvance"][target_base] == {
            "modality": "hold",
            "destination": None,
        }
        assert all(
            effect == {"modality": "not-applicable", "destination": None}
            for base, effect in row["runnerDefaultAdvance"].items()
            if base != target_base
        )


def test_pitch_count_flag_matches_pitch_event_kind_for_all_42_rows() -> None:
    """42行で投球数フラグと投球イベント区分の同値関係を保つ。"""
    contract = _repository_contract()

    for row in contract["matrixRows"]:
        pitch_event_kind = next(
            leaf["value"]
            for leaf in _predicate_leaves(row["precondition"])
            if leaf["axisId"] == "event.perPitch.pitchEventKind"
        )
        assert row["statFlags"]["投球数"] is (
            pitch_event_kind == "pitch-event"
        )


def test_repository_runner_event_rows_exactly_cover_three_vocabulary_axes() -> None:
    """走者イベント9値が3語彙軸の和集合をexact-setで覆う。"""
    contract = _repository_contract()

    _validate_vocabulary_axis_coverage(contract)

    runner_rows = [
        row for row in contract["matrixRows"] if row["eventKind"] == "runner-event"
    ]
    assert len(runner_rows) == 9


def test_runner_event_vocabulary_coverage_is_red_when_a_value_is_missing() -> None:
    """走者イベントの規範行を1値欠くとexact-set検査が拒む。"""
    contract = _repository_contract()
    contract["matrixRows"] = [
        row
        for row in contract["matrixRows"]
        if row["resultId"] != "catcher-pickoff-destination.third"
    ]

    with pytest.raises(
        VocabularyAxisCoverageError,
        match="missing=.*catcher-pickoff-destination.third",
    ):
        _validate_vocabulary_axis_coverage(contract)


def test_runner_event_vocabulary_coverage_is_red_for_an_extra_value() -> None:
    """語彙シードに無い走者イベントを足すとexact-set検査が拒む。"""
    contract = _repository_contract()
    extra = copy.deepcopy(contract["matrixRows"][-1])
    extra["resultId"] = "catcher-pickoff-destination.not-declared"
    contract["matrixRows"].append(extra)

    with pytest.raises(
        VocabularyAxisCoverageError,
        match="unexpected=.*catcher-pickoff-destination.not-declared",
    ):
        _validate_vocabulary_axis_coverage(contract)


def test_runner_event_vocabulary_coverage_is_red_when_one_axis_is_omitted() -> None:
    """走者イベントの和集合宣言から1軸を外す弱化を拒む。"""
    contract = _repository_contract()
    schema = _schema()
    coverage_sets = schema["x-pitchlog-vocabulary-axis-coverage"]["coverageSets"]
    runner_coverage = next(
        coverage_set
        for coverage_set in coverage_sets
        if coverage_set["rowDiscriminatorValue"] == "runner-event"
    )
    runner_coverage["axisIds"].remove("catcher-pickoff-destination")

    with pytest.raises(
        VocabularyAxisCoverageError,
        match="unexpected=.*catcher-pickoff-destination",
    ):
        _validate_vocabulary_axis_coverage(contract, schema=schema)


def test_runner_event_rows_are_declared_and_enforced_as_matrix_rows() -> None:
    """走者イベントを毎球入力のmatrixRows層から他層へ移すと拒む。"""
    schema = _schema()
    per_pitch_rule = next(
        operation
        for operation in schema["x-pitchlog-must-operation-coverage"][
            "requiredOperations"
        ]
        if operation["operationType"] == "per-pitch-input"
    )
    assert per_pitch_rule["rowLayer"] == "matrixRows"
    assert "runner-event" in per_pitch_rule["exactDiscriminatorValues"]

    contract = _repository_contract()
    moved = next(
        row for row in contract["matrixRows"] if row["eventKind"] == "runner-event"
    )
    contract["matrixRows"].remove(moved)
    contract["operationRows"].append(moved)

    with pytest.raises(schema_checker.DescriptorCheckError):
        _validate_schema(contract)


def test_step60_pickoff_results_use_identity_and_exclude_pickoff_outcome_ids() -> None:
    """牽制先6値だけをidentityのresultId源とし、牽制結果は除外する。"""
    rules = _load_object(REQUIRED_SET_ROW_RULES_PATH)
    identity_rule = next(
        rule
        for rule in rules["partitionRules"]
        if rule["partitionRuleId"] == "identity"
    )
    pickoff_ids = {
        f"{actor}-pickoff-destination.{base}"
        for actor in ("pitcher", "catcher")
        for base in ("first", "second", "third")
    }
    pickoff_result_assignment = next(
        assignment
        for assignment in rules["axisAssignments"]
        if assignment["axisId"] == "pickoff-result"
    )

    assert pickoff_ids.issubset(identity_rule["vocabularyIds"])
    assert pickoff_result_assignment["role"] == "not-result-id-source"
    assert "eventKind" not in pickoff_result_assignment


def test_repository_contract_step61_substitution_rows_and_mapping() -> None:
    """選手交代の2入力座標と比較面・Must操作写像を実資産で照合する。"""
    contract = _repository_contract()
    _validate_schema(contract)
    _validate_operation_rows(contract, frozenset())
    _validate_references(contract, vocabulary_checker.validate_manifest(REPOSITORY_ROOT))

    rows = [
        row for row in contract["operationRows"]
        if row["operationKind"] == "substitution"
    ]
    assert len(rows) == 2
    assert {row["operationResult"] for row in rows} == {
        "applied",
        "rejected-precondition",
    }
    assert {
        (row["precondition"]["axisId"], row["precondition"]["value"])
        for row in rows
    } == {("state.gameEnded", False), ("state.gameEnded", True)}
    assert all(row["operationKind"] == "substitution" for row in rows)
    assert all(row["clauseId"] == "FR-011" for row in rows)
    assert all(row["historyEffect"] == {"pushes": False, "kind": None} for row in rows)

    effect_definitions = _schema()["$defs"]
    for row in rows:
        for face, definition_name in (
            ("stateFields", "stateFieldEffects"),
            ("scoreboard", "scoreboardFieldEffects"),
            ("statFlags", "statFlagEffects"),
            ("historyAndResult", "historyAndResultEffects"),
        ):
            assert set(row["stateEffect"][face]) == set(
                effect_definitions[definition_name]["required"]
            )
            assert all(
                effect == {"kind": "unchanged"}
                for effect in row["stateEffect"][face].values()
            )
        assert all(
            phrase in row["remarks"]
            for phrase in (
                "ADR-003 D-8",
                "状態中立",
                "フィールド一意性",
                "参照整合",
                "相反指定",
                "FR-015の任意選手名",
            )
        )

    mappings = {
        mapping["operationType"]: mapping["rowRefs"]
        for mapping in contract["mustOperationCoverage"]["mappings"]
    }
    assert mappings["substitution"] == [
        _row_reference("operationRows", row) for row in rows
    ]
    assert mappings["per-pitch-input"] == [
        _row_reference("matrixRows", row) for row in contract["matrixRows"]
    ]
    assert len(contract["matrixRows"]) == 42
    sources = {source["sourceId"] for source in contract["provenance"]["sources"]}
    assert {"req:FR-011", "req:FR-006"} <= sources
    assert not any(source.startswith("adr:") for source in sources)
    assert contract["provenance"]["independentVerifierId"] == "not-performed"


def test_repository_step61_payload_shape_accepts_only_declared_fields() -> None:
    """段階1のpayloadは閉じた列と必須欄だけを機械判定する。"""
    shape = _repository_contract()["operationRows"][0]["payloadShape"]
    assert set(shape) == {"type", "properties", "required", "additionalProperties"}
    assert shape["type"] == "object"
    assert shape["additionalProperties"] is False
    assert set(shape["properties"]) == {
        "substitutionType",
        "battingOrderSlot",
        "outgoingPlayerId",
        "incomingPlayerId",
        "defensivePositionId",
    }
    assert set(shape["required"]) == {
        "substitutionType",
        "outgoingPlayerId",
        "incomingPlayerId",
    }
    valid = {
        "substitutionType": "pitcher",
        "outgoingPlayerId": "player-1",
        "incomingPlayerId": "player-2",
    }
    schema_checker._validate_instance(valid, shape, shape, "$")
    schema_checker._validate_instance(
        {**valid, "battingOrderSlot": 4, "defensivePositionId": "position-1"},
        shape,
        shape,
        "$",
    )


@pytest.mark.parametrize(
    ("invalid_payload", "message"),
    [
        (
            {
                "substitutionType": "pitcher",
                "outgoingPlayerId": "player-1",
                "incomingPlayerId": "player-2",
                "comment": "余分",
            },
            "未知キー",
        ),
        ({"substitutionType": "pitcher", "incomingPlayerId": "player-2"}, "必須キー不足"),
        (
            {"substitutionType": "pitcher", "outgoingPlayerId": "player-1", "incomingPlayerId": 2},
            "型不一致",
        ),
        (
            {
                "substitutionType": "unknown",
                "outgoingPlayerId": "player-1",
                "incomingPlayerId": "player-2",
            },
            "enum外",
        ),
    ],
)
def test_repository_step61_payload_rejection_is_detected(
    invalid_payload: dict[str, Any], message: str
) -> None:
    """宣言外・必須欠落・型違反・交代種別外のpayloadを拒否する。"""
    shape = _repository_contract()["operationRows"][0]["payloadShape"]
    with pytest.raises(schema_checker.DescriptorCheckError, match=message):
        schema_checker._validate_instance(invalid_payload, shape, shape, "$")


@pytest.mark.parametrize("missing_column", OPERATION_ROW_COLUMNS)
def test_repository_step61_missing_operation_column_is_red(missing_column: str) -> None:
    """実資産の選手交代行でもD-8の8列を省略できない。"""
    contract = _repository_contract()
    del contract["operationRows"][0][missing_column]
    with pytest.raises(schema_checker.DescriptorCheckError, match="必須キー不足"):
        _validate_schema(contract)


def test_repository_step61_unknown_operation_column_is_red() -> None:
    """実資産の選手交代行に宣言外の列を加えると拒否する。"""
    contract = _repository_contract()
    contract["operationRows"][0]["extra"] = True
    with pytest.raises(schema_checker.DescriptorCheckError, match="未知キー"):
        _validate_schema(contract)


def test_repository_step61_unknown_operation_result_is_red() -> None:
    """実資産の選手交代行でoperationResultのenum外値を拒否する。"""
    contract = _repository_contract()
    contract["operationRows"][0]["operationResult"] = "unknown"
    with pytest.raises(schema_checker.DescriptorCheckError, match="enum外"):
        _validate_schema(contract)


@pytest.mark.parametrize(
    "history_effect",
    [
        {"pushes": False, "kind": "confirmed-play"},
        {"pushes": True, "kind": None},
    ],
)
def test_repository_step61_history_effect_bidirectional_violation_is_red(
    history_effect: dict[str, Any],
) -> None:
    """pushesとkindの両方向制約を実資産の変異で検査する。"""
    contract = _repository_contract()
    contract["operationRows"][0]["historyEffect"] = history_effect
    with pytest.raises(schema_checker.DescriptorCheckError, match="oneOf"):
        _validate_schema(contract)


def test_repository_step61_payload_shape_must_remain_closed() -> None:
    """payloadShape自体の追加フィールド禁止が失われたら拒否する。"""
    contract = _repository_contract()
    contract["operationRows"][0]["payloadShape"]["additionalProperties"] = True
    with pytest.raises(schema_checker.DescriptorCheckError, match="const不一致"):
        _validate_schema(contract)


def test_repository_step61_invalid_payload_result_cannot_duplicate_natural_key() -> None:
    """不正payload値のない第3行を足して入力座標を重複させない。"""
    contract = _repository_contract()
    invalid_payload_row = copy.deepcopy(contract["operationRows"][0])
    invalid_payload_row["operationResult"] = "rejected-invalid-payload"
    contract["operationRows"].append(invalid_payload_row)

    with pytest.raises(ReferenceConstraintError, match="入力座標が重複"):
        _validate_references(contract, vocabulary_checker.validate_manifest(REPOSITORY_ROOT))


def _step63_rows(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    """試合終了宣言の規範行だけを取り出す。

    Args:
        contract: 状況判定契約。

    Returns:
        試合終了宣言の規範行。
    """
    return [
        row for row in contract["operationRows"]
        if row["operationKind"] == "game-end-declaration"
    ]


def test_repository_contract_step63_game_end_rows_and_mapping() -> None:
    """終了宣言の2入力座標・比較面・Must操作写像を実資産で照合する。"""
    contract = _repository_contract()
    _validate_schema(contract)
    _validate_operation_rows(contract, frozenset())
    _validate_references(contract, vocabulary_checker.validate_manifest(REPOSITORY_ROOT))

    rows = _step63_rows(contract)
    assert len(rows) == 2
    assert {row["operationResult"] for row in rows} == {
        "applied", "rejected-precondition",
    }
    assert {
        (row["precondition"]["axisId"], row["precondition"]["value"])
        for row in rows
    } == {("state.gameEnded", False), ("state.gameEnded", True)}
    assert all(row["clauseId"] == "FR-010" for row in rows)
    assert all(row["historyEffect"] == {"pushes": False, "kind": None} for row in rows)

    definitions = _schema()["$defs"]
    for row in rows:
        effects = row["stateEffect"]
        for face, definition_name in (
            ("stateFields", "stateFieldEffects"),
            ("scoreboard", "scoreboardFieldEffects"),
            ("statFlags", "statFlagEffects"),
            ("historyAndResult", "historyAndResultEffects"),
        ):
            assert set(effects[face]) == set(definitions[definition_name]["required"])
            assert all(
                effect == {"kind": "unchanged"}
                for field, effect in effects[face].items()
                if field != "state.gameEnded"
            )
        expected_game_ended = (
            {"kind": "set", "value": True}
            if row["operationResult"] == "applied"
            else {"kind": "unchanged"}
        )
        assert effects["stateFields"]["state.gameEnded"] == expected_game_ended
        assert all(
            phrase in row["remarks"]
            for phrase in (
                "ADR-003 D-8", "フィールド一意性", "参照整合", "相反指定",
                "FR-015の任意選手名", "state.score", "同期", "FR-006",
            )
        )

    mappings = {
        mapping["operationType"]: mapping["rowRefs"]
        for mapping in contract["mustOperationCoverage"]["mappings"]
    }
    assert mappings["game-end-declaration"] == [
        _row_reference("operationRows", row) for row in rows
    ]
    assert mappings["substitution"] == [
        _row_reference("operationRows", row)
        for row in contract["operationRows"]
        if row["operationKind"] == "substitution"
    ]
    assert mappings["per-pitch-input"] == [
        _row_reference("matrixRows", row) for row in contract["matrixRows"]
    ]
    assert "tiebreak-start" not in mappings
    assert len(contract["matrixRows"]) == 42
    sources = {source["sourceId"] for source in contract["provenance"]["sources"]}
    assert {"req:FR-010", "req:FR-005", "req:FR-006", "req:4.0-1"} <= sources
    assert not any(source.startswith("adr:") for source in sources)
    assert contract["provenance"]["independentVerifierId"] == "not-performed"


def test_repository_step63_payload_shape_accepts_only_empty_object() -> None:
    """FR-010が名指ししないpayload項目を段階1で推測して許可しない。"""
    shape = _step63_rows(_repository_contract())[0]["payloadShape"]
    assert shape == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    schema_checker._validate_instance({}, shape, shape, "$")
    with pytest.raises(schema_checker.DescriptorCheckError, match="未知キー"):
        schema_checker._validate_instance({"reason": "rain"}, shape, shape, "$")


@pytest.mark.parametrize("missing_column", OPERATION_ROW_COLUMNS)
def test_repository_step63_missing_operation_column_is_red(missing_column: str) -> None:
    """終了宣言行でもD-8の8列を省略できない。"""
    contract = _repository_contract()
    del _step63_rows(contract)[0][missing_column]
    with pytest.raises(schema_checker.DescriptorCheckError, match="必須キー不足"):
        _validate_schema(contract)


def test_repository_step63_unknown_operation_column_is_red() -> None:
    """終了宣言行に宣言外の列を加えると拒否する。"""
    contract = _repository_contract()
    _step63_rows(contract)[0]["extra"] = True
    with pytest.raises(schema_checker.DescriptorCheckError, match="未知キー"):
        _validate_schema(contract)


def test_repository_step63_unknown_operation_result_is_red() -> None:
    """終了宣言行でoperationResultのenum外値を拒否する。"""
    contract = _repository_contract()
    _step63_rows(contract)[0]["operationResult"] = "unknown"
    with pytest.raises(schema_checker.DescriptorCheckError, match="enum外"):
        _validate_schema(contract)


@pytest.mark.parametrize(
    "history_effect",
    [
        {"pushes": False, "kind": "confirmed-play"},
        {"pushes": True, "kind": None},
    ],
)
def test_repository_step63_history_effect_bidirectional_violation_is_red(
    history_effect: dict[str, Any],
) -> None:
    """終了宣言行でpushesとkindの双方向制約を検査する。"""
    contract = _repository_contract()
    _step63_rows(contract)[0]["historyEffect"] = history_effect
    with pytest.raises(schema_checker.DescriptorCheckError, match="oneOf"):
        _validate_schema(contract)


def test_repository_step63_payload_shape_must_remain_closed() -> None:
    """終了宣言のpayloadShapeで追加項目を許す変異を拒否する。"""
    contract = _repository_contract()
    _step63_rows(contract)[0]["payloadShape"]["additionalProperties"] = True
    with pytest.raises(schema_checker.DescriptorCheckError, match="const不一致"):
        _validate_schema(contract)


def test_repository_step63_invalid_payload_result_cannot_duplicate_natural_key() -> None:
    """不正payload用の別行を足して入力座標を重複させない。"""
    contract = _repository_contract()
    invalid_payload_row = copy.deepcopy(_step63_rows(contract)[0])
    invalid_payload_row["operationResult"] = "rejected-invalid-payload"
    contract["operationRows"].append(invalid_payload_row)
    with pytest.raises(ReferenceConstraintError, match="入力座標が重複"):
        _validate_references(contract, vocabulary_checker.validate_manifest(REPOSITORY_ROOT))


def _step64_rows(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    """その場登録の規範行だけを取り出す。

    Args:
        contract: 状況判定契約。

    Returns:
        その場登録の規範行。
    """
    return [
        row for row in contract["operationRows"]
        if row["operationKind"] == "adhoc-registration"
    ]


def test_repository_contract_step64_registration_rows_and_mapping() -> None:
    """その場登録の2入力座標・非影響面・Must操作写像を実資産で照合する。"""
    contract = _repository_contract()
    _validate_schema(contract)
    _validate_operation_rows(contract, frozenset())
    _validate_references(contract, vocabulary_checker.validate_manifest(REPOSITORY_ROOT))

    rows = _step64_rows(contract)
    assert len(rows) == 2
    assert {row["operationResult"] for row in rows} == {
        "applied", "rejected-precondition",
    }
    assert {
        (row["precondition"]["axisId"], row["precondition"]["value"])
        for row in rows
    } == {("state.gameEnded", False), ("state.gameEnded", True)}
    assert all(row["clauseId"] == "FR-015" for row in rows)
    assert all(row["historyEffect"] == {"pushes": False, "kind": None} for row in rows)

    definitions = _schema()["$defs"]
    for row in rows:
        for face, definition_name in (
            ("stateFields", "stateFieldEffects"),
            ("scoreboard", "scoreboardFieldEffects"),
            ("statFlags", "statFlagEffects"),
            ("historyAndResult", "historyAndResultEffects"),
        ):
            effects = row["stateEffect"][face]
            assert set(effects) == set(definitions[definition_name]["required"])
            assert all(effect == {"kind": "unchanged"} for effect in effects.values())
        assert all(
            phrase in row["remarks"]
            for phrase in (
                "ADR-003 D-8", "状態量", "背番号表示", "同番号の警告",
                "フィールド一意性", "参照整合", "相反指定",
                "D-8の文字列型制約とFR-015の任意選手名との整合",
                "payload-string-policy-reconciliation",
            )
        )

    mappings = {
        mapping["operationType"]: mapping["rowRefs"]
        for mapping in contract["mustOperationCoverage"]["mappings"]
    }
    assert mappings["adhoc-registration"] == [
        _row_reference("operationRows", row) for row in rows
    ]
    assert mappings["game-end-declaration"] == [
        _row_reference("operationRows", row)
        for row in contract["operationRows"]
        if row["operationKind"] == "game-end-declaration"
    ]
    assert mappings["substitution"] == [
        _row_reference("operationRows", row)
        for row in contract["operationRows"]
        if row["operationKind"] == "substitution"
    ]
    assert mappings["per-pitch-input"] == [
        _row_reference("matrixRows", row) for row in contract["matrixRows"]
    ]
    assert "tiebreak-start" not in mappings
    assert len(contract["matrixRows"]) == 42
    assert len(contract["operationRows"]) == 6
    sources = {source["sourceId"] for source in contract["provenance"]["sources"]}
    assert "req:FR-015" in sources
    assert not any(source.startswith("adr:") for source in sources)
    assert contract["provenance"]["independentVerifierId"] == "not-performed"


def test_repository_step64_payload_shape_has_only_clause_named_elements() -> None:
    """FR-015の名指し要素と必須区分だけを段階1のpayloadへ置く。"""
    shape = _step64_rows(_repository_contract())[0]["payloadShape"]
    assert shape == {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "throws": {"type": "string", "enum": ["right", "left"]},
            "bats": {"type": "string", "enum": ["right", "left", "both"]},
            "uniformNumber": {"type": "string"},
            "temporaryPlayerId": {"type": "string"},
        },
        "required": ["name", "throws", "bats"],
        "additionalProperties": False,
    }
    schema_checker._validate_instance(
        {"name": "山田", "throws": "right", "bats": "both"},
        shape, shape, "$",
    )
    schema_checker._validate_instance(
        {
            "name": "山田", "throws": "left", "bats": "left",
            "uniformNumber": "00", "temporaryPlayerId": "temporary-id",
        },
        shape, shape, "$",
    )


@pytest.mark.parametrize(
    ("invalid_payload", "message"),
    [
        ({"name": "山田", "throws": "right", "bats": "left", "memo": "余分"}, "未知キー"),
        ({"throws": "right", "bats": "left"}, "必須キー不足"),
        ({"name": 12, "throws": "right", "bats": "left"}, "型不一致"),
        ({"name": "山田", "throws": "center", "bats": "left"}, "enum外"),
        ({"name": "山田", "throws": "right", "bats": "center"}, "enum外"),
    ],
)
def test_repository_step64_payload_rejection_is_detected(
    invalid_payload: dict[str, Any], message: str,
) -> None:
    """宣言外・必須欠落・型違反・投打の値域外を拒否する。"""
    shape = _step64_rows(_repository_contract())[0]["payloadShape"]
    with pytest.raises(schema_checker.DescriptorCheckError, match=message):
        schema_checker._validate_instance(invalid_payload, shape, shape, "$")


@pytest.mark.parametrize("missing_column", OPERATION_ROW_COLUMNS)
def test_repository_step64_missing_operation_column_is_red(missing_column: str) -> None:
    """その場登録行でもD-8の8列を省略できない。"""
    contract = _repository_contract()
    del _step64_rows(contract)[0][missing_column]
    with pytest.raises(schema_checker.DescriptorCheckError, match="必須キー不足"):
        _validate_schema(contract)


def test_repository_step64_unknown_operation_column_is_red() -> None:
    """その場登録行に宣言外の列を加えると拒否する。"""
    contract = _repository_contract()
    _step64_rows(contract)[0]["extra"] = True
    with pytest.raises(schema_checker.DescriptorCheckError, match="未知キー"):
        _validate_schema(contract)


def test_repository_step64_unknown_operation_result_is_red() -> None:
    """その場登録行でoperationResultのenum外値を拒否する。"""
    contract = _repository_contract()
    _step64_rows(contract)[0]["operationResult"] = "unknown"
    with pytest.raises(schema_checker.DescriptorCheckError, match="enum外"):
        _validate_schema(contract)


@pytest.mark.parametrize(
    "history_effect",
    [
        {"pushes": False, "kind": "confirmed-play"},
        {"pushes": True, "kind": None},
    ],
)
def test_repository_step64_history_effect_bidirectional_violation_is_red(
    history_effect: dict[str, Any],
) -> None:
    """その場登録行でpushesとkindの双方向制約を検査する。"""
    contract = _repository_contract()
    _step64_rows(contract)[0]["historyEffect"] = history_effect
    with pytest.raises(schema_checker.DescriptorCheckError, match="oneOf"):
        _validate_schema(contract)


def test_repository_step64_payload_shape_must_remain_closed() -> None:
    """その場登録のpayloadShapeで追加項目を許す変異を拒否する。"""
    contract = _repository_contract()
    _step64_rows(contract)[0]["payloadShape"]["additionalProperties"] = True
    with pytest.raises(schema_checker.DescriptorCheckError, match="const不一致"):
        _validate_schema(contract)


def test_repository_step64_invalid_payload_result_cannot_duplicate_natural_key() -> None:
    """不正payload用の別行を足して入力座標を重複させない。"""
    contract = _repository_contract()
    invalid_payload_row = copy.deepcopy(_step64_rows(contract)[0])
    invalid_payload_row["operationResult"] = "rejected-invalid-payload"
    contract["operationRows"].append(invalid_payload_row)
    with pytest.raises(ReferenceConstraintError, match="入力座標が重複"):
        _validate_references(contract, vocabulary_checker.validate_manifest(REPOSITORY_ROOT))


def _manual_fixture_assets() -> tuple[dict[str, Any], dict[str, Any]]:
    """手作業fixtureと資産側schemaを返す。"""
    schema = _load_object(
        REPOSITORY_ROOT
        / "contracts/state-transition/state_transition_manual_fixture_schema_v1.json"
    )
    path = schema["x-pitchlog-manual-fixture-policy"]["fixturePath"]
    return _load_object(REPOSITORY_ROOT / path), schema


def _manual_fixture_coordinate(row: dict[str, Any]) -> dict[str, Any]:
    """規範行の自然キーを軸値の対へ展開する。

    Args:
        row: 状況判定の規範行。

    Returns:
        入力座標を構成する全ての軸値。
    """
    coordinate = {"eventKind": row["eventKind"], "resultId": row["resultId"]}
    assert row["precondition"]["op"] == "and"
    for predicate in row["precondition"]["args"]:
        assert predicate["op"] == "eq"
        assert predicate["axisId"] not in coordinate
        coordinate[predicate["axisId"]] = predicate["value"]
    return coordinate


def _manual_fixture_candidate(case: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """負例の全入力座標と候補出力から検査対象行を復元する。

    Args:
        case: 手作業の完全な期待ケース。
        row: 同じ結果IDの規範行。

    Returns:
        交差制約を検査する候補行。
    """
    coordinate = case["inputCoordinate"]
    candidate = {
        "eventKind": coordinate["eventKind"],
        "resultId": coordinate["resultId"],
        "precondition": {
            "op": "and",
            "args": [
                {"op": "eq", "axisId": axis_id, "value": value}
                for axis_id, value in coordinate.items()
                if axis_id not in ("eventKind", "resultId", "candidateEffects")
            ],
        },
        **copy.deepcopy(coordinate["candidateEffects"]),
        "remarks": row["remarks"],
    }
    return candidate


def _validate_manual_fixtures(
    document: dict[str, Any], schema: dict[str, Any]
) -> None:
    """fixtureの型・典拠・分岐・行参照を確認する。

    Args:
        document: fixture文書。
        schema: fixtureのschemaと宣言。
    """
    schema_checker._validate_instance(document, schema, schema, "$")
    policy = schema["x-pitchlog-manual-fixture-policy"]
    register = _load_object(REPOSITORY_ROOT / policy["branchRegisterPath"])
    contract = _repository_contract()
    known_clause_ids = schema_checker.load_clause_ids_from_paths(
        REPOSITORY_ROOT, (PurePosixPath(policy["requirementsPath"]),)
    )
    known_sources = {f"req:{clause_id}" for clause_id in known_clause_ids}
    branches = {branch["branchId"]: branch for branch in register["branches"]}
    game_end_sources = set(policy["sourceClausePartition"]["gameEndSourceClauseIds"])
    situation_ids = {
        branch_id
        for branch_id, branch in branches.items()
        if not set(branch["sourceClauseIds"]) & game_end_sources
    }
    deferred = policy["deferredBranches"]
    assert all(isinstance(reason, str) and reason for reason in deferred.values())
    fixtures = document["fixtures"]
    fixture_ids = [fixture["case"]["caseId"] for fixture in fixtures]
    branch_ids = [fixture["case"]["branchId"] for fixture in fixtures]
    assert len(fixture_ids) == len(set(fixture_ids))
    assert len(branch_ids) == len(set(branch_ids))
    assert set(branch_ids).isdisjoint(deferred)
    assert set(branch_ids) | set(deferred) == situation_ids
    output_fields = policy["positiveExpectedFields"]
    configuration, rules = _cross_constraint_configuration()
    rule_by_id = {rule["constraintId"]: rule for rule in rules}
    for fixture in fixtures:
        case = fixture["case"]
        branch = branches[case["branchId"]]
        kind = (
            "constraint-negative"
            if "candidateEffects" in case["inputCoordinate"]
            else "normative-branch"
        )
        assert kind == policy["fixtureKindByRegisterCoverageKind"][
            branch["coverageKind"]
        ]
        for source in fixture["provenance"]["sources"]:
            if source["sourceKind"] == "requirements":
                assert source["sourceId"] in known_sources
                assert source["sourceId"] in branch["sourceClauseIds"]
        coordinate = case["inputCoordinate"]
        rows = [
            row
            for row in contract["matrixRows"]
            if row["eventKind"] == coordinate["eventKind"]
            and row["resultId"] == coordinate["resultId"]
        ]
        assert len(rows) == 1
        row = rows[0]
        if kind == "normative-branch":
            assert coordinate == _manual_fixture_coordinate(row)
            assert case["expected"] == {field: row[field] for field in output_fields}
        else:
            assert case["expected"] == {"rejectedBy": case["branchId"]}
            candidate = _manual_fixture_candidate(case, row)
            assert candidate != row
            assert sum(
                candidate[field] != row[field] for field in row
            ) == 1
            assert _cross_rule_violation(
                candidate, rule_by_id[case["branchId"]], configuration
            ) is not None


def test_repository_manual_fixtures_match_declared_boundaries() -> None:
    """実資産と未作成分岐の切り分けを検査する。"""
    document, schema = _manual_fixture_assets()
    _validate_manual_fixtures(document, schema)
    policy = schema["x-pitchlog-manual-fixture-policy"]
    assert policy["comparisonStatus"] == (
        "complete-expected-case-awaits-expander-and-digest-freeze"
    )
    assert policy["comparisonFields"] == [
        "caseId", "branchId", "inputCoordinate", "expected"
    ]
    assert len(policy["positiveExpectedFields"]) == 6
    assert "complete-equality-with-expanded-cases" in policy["futureMachineGuarantees"]
    assert "fixture-digest-freeze" in policy["futureMachineGuarantees"]
    assert "semantic-completeness-of-each-branch" in policy["humanControls"]
    assert policy["independenceClaim"] == (
        "independent-from-expander-only-not-from-clause-branch-register"
    )


@pytest.mark.parametrize("change", ["unknown-key", "missing-provenance", "wrong-author"])
def test_manual_fixture_schema_rejects_malformed_fixture(change: str) -> None:
    """閉じたschemaと作成者宣言の負例を確かめる。"""
    document, schema = _manual_fixture_assets()
    fixture = document["fixtures"][0]
    if change == "unknown-key":
        fixture["unexpected"] = True
    elif change == "missing-provenance":
        del fixture["provenance"]
    else:
        fixture["provenance"]["authorId"] = "human"
    with pytest.raises(schema_checker.DescriptorCheckError):
        _validate_manual_fixtures(document, schema)


@pytest.mark.parametrize("change", ["missing-branch", "bad-source", "bad-expected"])
def test_manual_fixture_reference_negatives(change: str) -> None:
    """欠落分岐・実在しない条文・行との不一致を捕まえる。"""
    document, schema = _manual_fixture_assets()
    if change == "missing-branch":
        document["fixtures"].pop(0)
    elif change == "bad-source":
        document["fixtures"][0]["provenance"]["sources"][0]["sourceId"] = (
            "req:NOT-EXISTS"
        )
    else:
        document["fixtures"][0]["case"]["expected"]["statFlags"]["三振"] = False
    with pytest.raises(AssertionError):
        _validate_manual_fixtures(document, schema)


def test_manual_fixture_deferred_partition_is_not_silent() -> None:
    """未作成分岐を隠せないことを確かめる。"""
    document, schema = _manual_fixture_assets()
    schema["x-pitchlog-manual-fixture-policy"]["deferredBranches"].pop("OUT3-01")
    with pytest.raises(AssertionError):
        _validate_manual_fixtures(document, schema)


def test_manual_fixture_negative_mutations_hit_named_constraint() -> None:
    """XC負例が宣言した交差制約を実際に破ることを確かめる。"""
    document, _ = _manual_fixture_assets()
    contract = _repository_contract()
    configuration, rules = _cross_constraint_configuration()
    rule_by_id = {rule["constraintId"]: rule for rule in rules}
    for fixture in document["fixtures"]:
        case = fixture["case"]
        if "candidateEffects" not in case["inputCoordinate"]:
            continue
        coordinate = case["inputCoordinate"]
        row = copy.deepcopy(
            next(
                row
                for row in contract["matrixRows"]
                if row["eventKind"] == coordinate["eventKind"]
                and row["resultId"] == coordinate["resultId"]
            )
        )
        candidate = _manual_fixture_candidate(case, row)
        rule = rule_by_id[case["branchId"]]
        assert _cross_rule_violation(candidate, rule, configuration) is not None


@pytest.mark.parametrize(
    "change",
    ["missing-output", "extra-output", "missing-candidate", "partial-candidate"],
)
def test_manual_fixture_complete_case_schema_negatives(change: str) -> None:
    """部分的な期待値と候補入力へ戻れないことを確かめる。"""
    document, schema = _manual_fixture_assets()
    positive = document["fixtures"][0]["case"]
    negative = next(
        item["case"]
        for item in document["fixtures"]
        if "candidateEffects" in item["case"]["inputCoordinate"]
    )
    if change == "missing-output":
        del positive["expected"]["statFlags"]
    elif change == "extra-output":
        positive["expected"]["unknown"] = True
    elif change == "missing-candidate":
        del negative["inputCoordinate"]["candidateEffects"]
    else:
        del negative["inputCoordinate"]["candidateEffects"]["outEffect"]
    with pytest.raises(schema_checker.DescriptorCheckError):
        _validate_manual_fixtures(document, schema)


def _manual_fixture_branch_coverage_assets() -> tuple[dict[str, Any], dict[str, Any]]:
    """双方向被覆の宣言と閉じたschemaを読み込む。

    Returns:
        宣言とschemaの組。
    """
    directory = REPOSITORY_ROOT / "contracts/state-transition"
    document = _load_object(directory / "manual_fixture_branch_coverage_v1.json")
    schema = _load_object(directory / "manual_fixture_branch_coverage_schema_v1.json")
    return document, schema


def _validate_manual_fixture_branch_coverage(
    document: dict[str, Any],
    schema: dict[str, Any],
    fixture_documents: dict[str, dict[str, Any]] | None = None,
) -> None:
    """台帳と両fixtureを突合し、未作成分岐の理由付きexact-setを検査する。

    Args:
        document: 未作成分岐の宣言。
        schema: 宣言の閉じたschema。
        fixture_documents: 負例用に変異させた実fixture文書。
    """
    schema_checker._validate_instance(document, schema, schema, "$")
    register = _load_object(REPOSITORY_ROOT / document["branchRegisterPath"])
    register_ids = [branch["branchId"] for branch in register["branches"]]
    assert len(register_ids) == len(set(register_ids))
    source_paths = [source["fixturePath"] for source in document["fixtureSources"]]
    assert len(source_paths) == len(set(source_paths))
    discovered_paths = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in REPOSITORY_ROOT.glob(document["fixtureDiscoveryPattern"])
    }
    assert set(source_paths) == discovered_paths
    fixture_ids: list[str] = []
    case_ids: list[str] = []
    existing_deferred: set[str] = set()
    for source in document["fixtureSources"]:
        fixture_path = source["fixturePath"]
        fixture = (
            fixture_documents[fixture_path]
            if fixture_documents is not None
            else _load_object(REPOSITORY_ROOT / fixture_path)
        )
        fixture_ids.extend(item["case"]["branchId"] for item in fixture["fixtures"])
        case_ids.extend(item["case"]["caseId"] for item in fixture["fixtures"])
        fixture_schema = _load_object(REPOSITORY_ROOT / source["schemaPath"])
        deferred = fixture_schema["x-pitchlog-manual-fixture-policy"]["deferredBranches"]
        assert existing_deferred.isdisjoint(deferred)
        existing_deferred.update(deferred)
    assert len(fixture_ids) == len(set(fixture_ids))
    assert len(case_ids) == len(set(case_ids))
    type_ids = [item["id"] for item in document["reasonTypes"]]
    assert len(type_ids) == len(set(type_ids))
    missing = document["missingFixtureBranches"]
    declared_ids = [item["branchId"] for item in missing]
    assert len(declared_ids) == len(set(declared_ids))
    assert {item["reasonType"] for item in missing} == set(type_ids)
    fixture_set = set(fixture_ids)
    register_set = set(register_ids)
    declared_set = set(declared_ids)
    assert fixture_set - register_set == set()
    assert register_set - fixture_set == declared_set
    assert existing_deferred == declared_set


def test_repository_manual_fixture_branch_coverage_is_bidirectional() -> None:
    """実資産の31件と未作成37件を台帳の68件へ双方向で一致させる。"""
    document, schema = _manual_fixture_branch_coverage_assets()
    _validate_manual_fixture_branch_coverage(document, schema)


@pytest.mark.parametrize(
    "change",
    [
        "missing-increases",
        "missing-decreases",
        "phantom-fixture",
        "declaration-decreases",
        "unknown-reason-type",
    ],
)
def test_manual_fixture_branch_coverage_negatives(change: str) -> None:
    """欠落の増減・幻の分岐・理由宣言の不整合を検出する。"""
    document, schema = _manual_fixture_branch_coverage_assets()
    fixtures = {
        source["fixturePath"]: _load_object(REPOSITORY_ROOT / source["fixturePath"])
        for source in document["fixtureSources"]
    }
    first_path = document["fixtureSources"][0]["fixturePath"]
    if change == "missing-increases":
        fixtures[first_path]["fixtures"].pop()
    elif change in ("missing-decreases", "phantom-fixture"):
        added = copy.deepcopy(fixtures[first_path]["fixtures"][0])
        added["case"]["caseId"] = "ST-COVERAGE-NEGATIVE"
        added["case"]["branchId"] = (
            document["missingFixtureBranches"][0]["branchId"]
            if change == "missing-decreases"
            else "NOT-IN-REGISTER"
        )
        fixtures[first_path]["fixtures"].append(added)
    elif change == "declaration-decreases":
        document["missingFixtureBranches"].pop()
    else:
        document["missingFixtureBranches"][0]["reasonType"] = "unknown-type"
    with pytest.raises(AssertionError):
        _validate_manual_fixture_branch_coverage(document, schema, fixtures)


_load_module("frozen_history", REPOSITORY_ROOT / "scripts/frozen_history.py")
manual_fixture_baseline_checker = _load_module(
    "manual_fixture_baseline_checker",
    REPOSITORY_ROOT / "scripts/check_manual_fixture_baselines.py",
)
GAME_END_MANUAL_FIXTURE_PATH = (
    "contracts/state-transition/game_end_manual_fixtures_v1.json"
)
MANUAL_FIXTURE_COVERAGE_PATH = (
    "contracts/state-transition/manual_fixture_branch_coverage_v1.json"
)


def test_repository_manual_fixture_baselines_are_valid() -> None:
    """両fixtureの凍結宣言とdigestが現行資産に一致する。"""
    manual_fixture_baseline_checker.check_repository(
        REPOSITORY_ROOT, MANUAL_FIXTURE_COVERAGE_PATH
    )


def test_manual_fixture_baseline_fails_when_declaration_cannot_be_read() -> None:
    """対象宣言を読めなければ凍結検査は閉じて失敗する。"""
    with pytest.raises(
        manual_fixture_baseline_checker.FixtureBaselineError, match="解決できない"
    ):
        manual_fixture_baseline_checker.check_repository(
            REPOSITORY_ROOT,
            "contracts/state-transition/missing_fixture_coverage_v1.json",
        )


def test_manual_fixture_baseline_fails_when_digest_differs() -> None:
    """期待ケースを変異させると宣言されたdigestと一致しない。"""
    asset = _load_object(REPOSITORY_ROOT / GAME_END_MANUAL_FIXTURE_PATH)
    decision = asset["fixtures"][0]["case"]["decision"]
    decision["automaticallyEndsGame"] = not decision["automaticallyEndsGame"]
    with pytest.raises(
        manual_fixture_baseline_checker.FixtureBaselineError, match="digestが不一致"
    ):
        manual_fixture_baseline_checker.check_repository(
            REPOSITORY_ROOT,
            MANUAL_FIXTURE_COVERAGE_PATH,
            asset_overrides={GAME_END_MANUAL_FIXTURE_PATH: asset},
        )


def test_manual_fixture_baseline_fails_without_asset_declaration() -> None:
    """fixture自身の凍結宣言が欠ければ失敗する。"""
    asset = _load_object(REPOSITORY_ROOT / GAME_END_MANUAL_FIXTURE_PATH)
    del asset["baseline_control"]
    with pytest.raises(
        manual_fixture_baseline_checker.FixtureBaselineError, match="baseline_control"
    ):
        manual_fixture_baseline_checker.check_repository(
            REPOSITORY_ROOT,
            MANUAL_FIXTURE_COVERAGE_PATH,
            asset_overrides={GAME_END_MANUAL_FIXTURE_PATH: asset},
        )


def test_manual_fixture_baseline_history_is_append_only() -> None:
    """受理済みの記録を書き換えた履歴は失敗する。"""
    previous = _load_object(REPOSITORY_ROOT / GAME_END_MANUAL_FIXTURE_PATH)
    old_record = previous["baseline_control"]["history"][0]
    old_record["source_commit"] = "a" * 40
    old_record["approved_by"] = "確認者"
    old_record["approved_on"] = "2026-10-04"
    old_record["acceptance_id"] = "example/pitchlog#1"
    asset = copy.deepcopy(previous)
    asset["baseline_control"]["history"][0]["reason"] = "過去の理由を書き換えた"
    with pytest.raises(
        manual_fixture_baseline_checker.FixtureBaselineError, match="追記のみでない"
    ):
        manual_fixture_baseline_checker.validate_asset(
            REPOSITORY_ROOT, GAME_END_MANUAL_FIXTURE_PATH, asset, previous
        )


def test_manual_fixture_baseline_provisional_bootstrap_can_be_updated() -> None:
    """未承認の初回記録では期待座標とdigestを同じ受理前の作業で更新できる。"""
    previous = _load_object(REPOSITORY_ROOT / GAME_END_MANUAL_FIXTURE_PATH)
    asset = copy.deepcopy(previous)
    asset["fixtures"][0]["case"]["inputCoordinate"]["state.score"] = "home-lead:M"
    digest = manual_fixture_baseline_checker._projection_digest(
        REPOSITORY_ROOT, asset, GAME_END_MANUAL_FIXTURE_PATH
    )
    identity = asset["baseline_control"]["identity"]
    identity["current_identifiers"] = [f"{identity['identifier_prefix']}{digest}"]
    record = asset["baseline_control"]["history"][0]
    record["new_baseline_identifiers"] = identity["current_identifiers"]
    record["change"]["after"]["frozen_projection_sha256"] = digest
    asset["baseline_control"]["history"][0]["reason"] = "初回受理前の根拠を補う"
    manual_fixture_baseline_checker.validate_asset(
        REPOSITORY_ROOT, GAME_END_MANUAL_FIXTURE_PATH, asset, previous
    )


def test_manual_fixture_baseline_rejects_inconsistent_provisional_record() -> None:
    """sourceだけ暫定で承認者を人名に変えた記録は拒否する。"""
    previous = _load_object(REPOSITORY_ROOT / GAME_END_MANUAL_FIXTURE_PATH)
    asset = copy.deepcopy(previous)
    asset["baseline_control"]["history"][0]["approved_by"] = "確認者"
    with pytest.raises(
        manual_fixture_baseline_checker.FixtureBaselineError,
        match="暫定記録の整合",
    ):
        manual_fixture_baseline_checker.validate_asset(
            REPOSITORY_ROOT, GAME_END_MANUAL_FIXTURE_PATH, asset, previous
        )


def test_manual_fixture_baseline_rejects_provisional_acceptance_id() -> None:
    """暫定記録へ受理 ID だけを付けても受理済みにはできない。"""
    previous = _load_object(REPOSITORY_ROOT / GAME_END_MANUAL_FIXTURE_PATH)
    asset = copy.deepcopy(previous)
    asset["baseline_control"]["history"][0]["acceptance_id"] = "example/pitchlog#1"
    with pytest.raises(
        manual_fixture_baseline_checker.FixtureBaselineError,
        match="暫定記録の整合",
    ):
        manual_fixture_baseline_checker.validate_asset(
            REPOSITORY_ROOT, GAME_END_MANUAL_FIXTURE_PATH, asset, previous
        )


def test_manual_fixture_baseline_rejects_disguised_accepted_bootstrap() -> None:
    """暫定の初回記録を受理済みのように書き換える経路を拒否する。"""
    previous = _load_object(REPOSITORY_ROOT / GAME_END_MANUAL_FIXTURE_PATH)
    asset = copy.deepcopy(previous)
    record = asset["baseline_control"]["history"][0]
    record["source_commit"] = "a" * 40
    record["approved_by"] = "確認者"
    record["approved_on"] = "2026-10-04"
    record["acceptance_id"] = "example/pitchlog#1"
    with pytest.raises(
        manual_fixture_baseline_checker.FixtureBaselineError,
        match="暫定記録を受理済みに偽装",
    ):
        manual_fixture_baseline_checker.validate_asset(
            REPOSITORY_ROOT, GAME_END_MANUAL_FIXTURE_PATH, asset, previous
        )
