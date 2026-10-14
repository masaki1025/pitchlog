"""入力軸 descriptor と二契約の派生 schema の射影を照合する。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, cast

from pitchlog.domaincheck.runners.handoff import (
    DEPENDENCIES,
    DESCRIPTOR_PATH,
    HANDOFF_PATH,
    LoadedHandoff,
)

STATE_SCHEMA = "contracts/state-transition/state_transition_contract_schema_v1.json"
GAME_SCHEMA = "contracts/state-transition/game_end_contract_schema_v1.json"
HISTORY_PATH = "backend/domain/history-depth.json"

# 解釈できる規則を列挙する。追加・意味変更時は検査器の更新を必須とする。
RULE_MODES = {
    "projection.finiteEnumerable": ("finite-enumerable", "exact-enum"),
    "projection.boundaryPartition": ("boundary-partition", "boundary-annotations"),
    "projection.structuredBoundaryPartition": (
        "boundary-partition",
        "structured-boundary-annotations",
    ),
    "projection.deferredStructuredBoundaryPartition": (
        "boundary-partition",
        "deferred-structured-boundary-annotations",
    ),
    "projection.boundedBoundaryPartition": (
        "boundary-partition",
        "bounded-boundary-annotations",
    ),
    "projection.nonFinite": ("non-finite", "open-domain-with-reason"),
    "projection.nonCoverageField": ("non-coverage-field", "required-schema-property"),
    "projection.descriptorIdentity": (
        "descriptor-identity",
        "descriptor-identity-binding",
    ),
}
RULE_CHECKS = {
    "projection.finiteEnumerable": {
        "axis-id-exact",
        "classification-exact",
        "values-exact-set",
        "conditional-values-exact",
        "no-extra-or-missing-targets",
    },
    "projection.boundaryPartition": {
        "axis-id-exact",
        "classification-exact",
        "boundaries-exact-set",
        "conditional-values-exact",
        "no-extra-or-missing-targets",
    },
    "projection.structuredBoundaryPartition": {
        "axis-id-exact",
        "classification-exact",
        "boundaries-exact-set",
        "value-schema-exact",
        "conditional-values-exact",
        "no-extra-or-missing-targets",
    },
    "projection.deferredStructuredBoundaryPartition": {
        "axis-id-exact",
        "classification-exact",
        "boundaries-exact-set",
        "representation-capability-exact",
        "stage2-delegation-exact",
        "conditional-values-exact",
        "no-extra-or-missing-targets",
    },
    "projection.boundedBoundaryPartition": {
        "axis-id-exact",
        "classification-exact",
        "boundaries-exact-set",
        "range-exact",
        "no-extra-or-missing-targets",
    },
    "projection.nonFinite": {
        "axis-id-exact",
        "classification-exact",
        "non-finite-reason-exact",
        "no-extra-or-missing-targets",
    },
    "projection.nonCoverageField": {
        "field-id-exact",
        "reason-exact",
        "schema-retention-exact",
        "no-extra-or-missing-targets",
    },
    "projection.descriptorIdentity": {
        "descriptor-identity-exact",
        "no-extra-or-missing-targets",
    },
}
RULE_KEYWORDS = {
    "projection.finiteEnumerable": {
        "enum",
        "x-pitchlog-axis-id",
        "x-pitchlog-axis-classification",
        "x-pitchlog-conditional-values",
    },
    "projection.boundaryPartition": {
        "x-pitchlog-axis-id",
        "x-pitchlog-axis-classification",
        "x-pitchlog-boundary-values",
        "x-pitchlog-conditional-values",
    },
    "projection.structuredBoundaryPartition": {
        "x-pitchlog-axis-id",
        "x-pitchlog-axis-classification",
        "x-pitchlog-boundary-values",
        "x-pitchlog-value-schema",
        "x-pitchlog-conditional-values",
    },
    "projection.deferredStructuredBoundaryPartition": {
        "x-pitchlog-axis-id",
        "x-pitchlog-axis-classification",
        "x-pitchlog-boundary-values",
        "x-pitchlog-representation-capability",
        "x-pitchlog-stage2-external-constraints",
        "x-pitchlog-conditional-values",
    },
    "projection.boundedBoundaryPartition": {
        "minimum",
        "maximum",
        "x-pitchlog-axis-id",
        "x-pitchlog-axis-classification",
        "x-pitchlog-boundary-values",
        "x-pitchlog-invalid-boundary-values",
        "x-pitchlog-coverage-bounds",
    },
    "projection.nonFinite": {
        "type",
        "x-pitchlog-axis-id",
        "x-pitchlog-axis-classification",
        "x-pitchlog-non-finite-reason",
    },
    "projection.nonCoverageField": {
        "properties",
        "required",
        "x-pitchlog-non-coverage-field",
        "x-pitchlog-non-coverage-reason",
    },
    "projection.descriptorIdentity": {
        "x-pitchlog-descriptor-id",
        "x-pitchlog-descriptor-version",
        "x-pitchlog-descriptor-digest",
    },
}


class DescriptorParityError(ValueError):
    """射影不一致または判定不能を規則 ID とともに表す。"""

    def __init__(self, code: str, detail: str) -> None:
        """規則 ID と詳細を保持する。

        Args:
            code: 失敗した規則 ID。
            detail: 失敗した箇所。
        """
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class DescriptorParityResult:
    """検査済み規則と解決した履歴深さを保持する。"""

    rule_ids: tuple[str, ...]
    history_depth: int
    resolved_history_boundaries: Mapping[str, tuple[object, ...]]


def _fail(code: str, detail: str) -> NoReturn:
    """規則 ID を伴う失敗を起こす。"""
    raise DescriptorParityError(code, detail)


def _obj(value: object, label: str) -> dict[str, object]:
    """JSON object 以外を判定不能として拒否する。"""
    if not isinstance(value, dict):
        _fail("PARITY_UNDECIDABLE", label)
    return cast(dict[str, object], value)


def _items(value: object, label: str) -> list[object]:
    """JSON array 以外を判定不能として拒否する。"""
    if not isinstance(value, list):
        _fail("PARITY_UNDECIDABLE", label)
    return cast(list[object], value)


def _read(root: Path, path: str) -> tuple[bytes, dict[str, object]]:
    """既知の相対パスから JSON object を読む。"""

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _fail("PARITY_UNDECIDABLE", f"{path}: duplicate {key}")
            result[key] = value
        return result

    def reject_constant(_token: str) -> NoReturn:
        _fail("PARITY_UNDECIDABLE", f"{path}: nonfinite JSON number")

    try:
        raw = (root / path).read_bytes()
        data = json.loads(
            raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DescriptorParityError("PARITY_UNDECIDABLE", path) from error
    return raw, _obj(data, path)


def _equal(actual: object, expected: object, code: str, label: str) -> None:
    """型と値を同時に比較する。"""
    if type(actual) is not type(expected) or actual != expected:
        _fail(code, label)


def _exact_values(actual: object, expected: object, code: str, label: str) -> None:
    """JSON 値の重複も含む集合の一致を調べる。"""

    def tokens(value: object) -> Counter[str]:
        return Counter(
            json.dumps(item, ensure_ascii=False, sort_keys=True)
            for item in _items(value, label)
        )

    if tokens(actual) != tokens(expected):
        _fail(code, label)


def _indexed(items: object, key: str, label: str) -> dict[str, dict[str, object]]:
    """一意な ID で object 配列を引ける形にする。"""
    result: dict[str, dict[str, object]] = {}
    for item in _items(items, label):
        record = _obj(item, label)
        name = record.get(key)
        if not isinstance(name, str) or not name or name in result:
            _fail("PARITY_UNDECIDABLE", label)
        result[name] = record
    return result


def _annotations(node: object, key: str) -> dict[str, tuple[dict[str, object], bool]]:
    """Schema 全体から注釈と親の required 指定を収集する。"""
    found: dict[str, tuple[dict[str, object], bool]] = {}

    def visit(value: object, required: bool = False) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            record = cast(dict[str, object], value)
            if key in record:
                axis_id = record[key]
                if not isinstance(axis_id, str) or axis_id in found:
                    _fail("PARITY_UNDECIDABLE", key)
                found[axis_id] = (record, required)
            for name, child in record.items():
                if name == "properties" and isinstance(child, dict):
                    names = record.get("required")
                    if not isinstance(names, list):
                        _fail("PARITY_UNDECIDABLE", "required")
                    if not all(isinstance(item, str) for item in names):
                        _fail("PARITY_UNDECIDABLE", "required names")
                    for property_name, property_node in child.items():
                        visit(property_node, property_name in names)
                elif name == "properties":
                    _fail("PARITY_UNDECIDABLE", "properties")
                elif name != "properties":
                    visit(child)

    visit(node)
    return found


def _rules(descriptor: dict[str, object]) -> dict[str, dict[str, object]]:
    """全射影規則の方式・検査内容・軸の帰属を閉じて検査する。"""
    rules = _indexed(descriptor.get("projectionRules"), "ruleId", "projectionRules")
    if rules.keys() != RULE_MODES.keys():
        _fail("PARITY_UNDECIDABLE", "projectionRules ruleId")
    state_axes = _indexed(descriptor.get("stateTransitionAxes"), "axisId", "state axes")
    game_axes = _indexed(descriptor.get("gameEndAxes"), "axisId", "game axes")
    axes = state_axes | game_axes
    fields = _indexed(descriptor.get("nonCoverageFields"), "fieldId", "nonCoverage")
    if len(axes) != len(_items(descriptor["stateTransitionAxes"], "state axes")) + len(
        _items(descriptor["gameEndAxes"], "game axes")
    ):
        _fail("AXIS_SET", "duplicate axis")
    projected: list[str] = []
    for rule_id, rule in rules.items():
        kind, mode = RULE_MODES[rule_id]
        for key, expected in (
            ("sourceKind", kind),
            ("projectionMode", mode),
            ("verificationStage", "stage2-descriptorParity"),
            ("mismatchAction", "manifest-registration-denied"),
            ("undecidableAction", "fail"),
        ):
            _equal(rule.get(key), expected, "PARITY_UNDECIDABLE", f"{rule_id}.{key}")
        checks = _items(rule.get("parityChecks"), rule_id)
        if not all(isinstance(check, str) for check in checks):
            _fail("PARITY_UNDECIDABLE", f"{rule_id}.parityChecks")
        if (
            len(checks) != len(RULE_CHECKS[rule_id])
            or set(checks) != RULE_CHECKS[rule_id]
        ):
            _fail("PARITY_UNDECIDABLE", f"{rule_id}.parityChecks")
        keywords = _items(rule.get("jsonSchemaKeywords"), rule_id)
        if (
            not all(isinstance(word, str) for word in keywords)
            or len(keywords) != len(RULE_KEYWORDS[rule_id])
            or set(keywords) != RULE_KEYWORDS[rule_id]
        ):
            _fail("PARITY_UNDECIDABLE", f"{rule_id}.jsonSchemaKeywords")
        targets = _items(rule.get("targetIds"), rule_id)
        if not all(isinstance(target, str) for target in targets):
            _fail("PARITY_UNDECIDABLE", f"{rule_id}.targetIds")
        if rule_id == "projection.descriptorIdentity":
            if set(targets) != {"descriptorId", "version", "digest"}:
                _fail("DESCRIPTOR_IDENTITY", rule_id)
            continue
        target_names = cast(list[str], targets)
        projected.extend(target_names)
        if rule_id == "projection.nonCoverageField":
            source = fields
        elif rule_id == "projection.boundedBoundaryPartition":
            source = game_axes
        else:
            source = state_axes
        for target in target_names:
            if target not in source:
                _fail("AXIS_SET", f"{rule_id}: {target}")
            if (
                rule_id != "projection.nonCoverageField"
                and source[target].get("classification") != kind
            ):
                _fail("VALUE_RANGE", f"{rule_id}: {target}")
            if rule_id == "projection.structuredBoundaryPartition":
                _obj(source[target].get("valueSchema"), f"{target}.valueSchema")
            if rule_id == "projection.deferredStructuredBoundaryPartition":
                _obj(
                    source[target].get("representationCapability"),
                    f"{target}.representationCapability",
                )
            if rule_id != "projection.nonCoverageField":
                _axis_values(source[target], rule_id)
    external = _obj(descriptor.get("stage2ExternalConstraints"), "external")
    deferred = _items(
        rules["projection.deferredStructuredBoundaryPartition"].get("targetIds"),
        "deferred targets",
    )
    _exact_values(
        external.get("payloadAxisIds"),
        deferred,
        "VALUE_RANGE",
        "stage2ExternalConstraints.payloadAxisIds",
    )
    _equal(external.get("status"), "deferred", "PARITY_UNDECIDABLE", "external status")
    if (
        len(projected) != len(set(projected))
        or set(projected) != axes.keys() | fields.keys()
    ):
        _fail("AXIS_SET", "projection target exact-set")
    return rules


def _axis_values(axis: dict[str, object], rule_id: str) -> None:
    """分類に応じた値域と条件付き値の内部整合を検査する。"""
    key = "values" if rule_id == "projection.finiteEnumerable" else "boundaryValues"
    if rule_id == "projection.nonFinite":
        _fail("PARITY_UNDECIDABLE", "non-finite projection is not represented")
    values = _items(axis.get(key), f"{axis.get('axisId')}.{key}")
    if len(values) != len(
        {json.dumps(value, sort_keys=True, ensure_ascii=False) for value in values}
    ):
        _fail("VALUE_RANGE", f"{axis.get('axisId')}.duplicate values")
    value_tokens = {
        json.dumps(value, sort_keys=True, ensure_ascii=False) for value in values
    }
    for item in _items(axis.get("conditionalValues", []), "conditionalValues"):
        conditional = _obj(item, "conditionalValue")
        token = json.dumps(conditional.get("value"), sort_keys=True, ensure_ascii=False)
        if token not in value_tokens:
            _fail("VALUE_RANGE", f"{axis.get('axisId')}.conditionalValue")


def _identity(
    descriptor: dict[str, object],
    handoff: dict[str, object],
    schemas: list[dict[str, object]],
) -> None:
    """Handoff と両 schema の descriptor 拘束を照合する。"""
    parity = _obj(handoff.get("descriptorParity"), "descriptorParity")
    _equal(parity.get("descriptorPath"), DESCRIPTOR_PATH, "DESCRIPTOR_IDENTITY", "path")
    _equal(
        parity.get("descriptorId"),
        descriptor.get("descriptorId"),
        "DESCRIPTOR_IDENTITY",
        "id",
    )
    _equal(
        parity.get("projectionRulesPointer"),
        "/projectionRules",
        "DESCRIPTOR_IDENTITY",
        "rules pointer",
    )
    _equal(parity.get("verificationStage"), "stage-2", "DESCRIPTOR_IDENTITY", "stage")
    for schema in schemas:
        binding = _obj(schema.get("x-pitchlog-descriptor-identity-binding"), "binding")
        _equal(
            binding,
            {
                "contractField": "inputAxesDescriptor",
                "schemaDefinition": "inputAxesDescriptorBinding",
            },
            "DESCRIPTOR_IDENTITY",
            "binding",
        )
        ref = _obj(
            _obj(schema.get("properties"), "properties").get("inputAxesDescriptor"),
            "descriptor ref",
        )
        _equal(
            ref,
            {"$ref": "#/$defs/inputAxesDescriptorBinding"},
            "DESCRIPTOR_IDENTITY",
            "ref",
        )
        if "inputAxesDescriptor" not in _items(
            schema.get("required"), "schema required"
        ):
            _fail("DESCRIPTOR_IDENTITY", "schema required inputAxesDescriptor")
        definition = _obj(
            _obj(schema.get("$defs"), "$defs").get("inputAxesDescriptorBinding"),
            "identity definition",
        )
        _exact_values(
            definition.get("required"),
            ["descriptorId", "version", "digest"],
            "DESCRIPTOR_IDENTITY",
            "required",
        )
        _equal(
            definition.get("additionalProperties"),
            False,
            "DESCRIPTOR_IDENTITY",
            "additionalProperties",
        )
        properties = _obj(definition.get("properties"), "identity properties")
        if properties.keys() != {"descriptorId", "version", "digest"}:
            _fail("DESCRIPTOR_IDENTITY", "identity field set")
        for field in properties:
            _equal(
                _obj(properties[field], field).get("const"),
                descriptor.get(field),
                "DESCRIPTOR_IDENTITY",
                field,
            )


def _state_reference(schema: dict[str, object]) -> None:
    """状態遷移 schema の動的 descriptor 参照を閉じて検査する。

    状態遷移軸は個別の注釈ではなく、descriptor の集合と値域を
    predicateAxisResolution が参照する。この参照契約を固定する。
    """
    constraints = _obj(
        schema.get("x-pitchlog-reference-constraints"), "reference constraints"
    )
    resolver = _obj(constraints.get("predicateAxisResolution"), "axis resolver")
    expected = {
        "rowCollections": ["matrixRows", "operationRows", "undoRows"],
        "predicateField": "precondition",
        "axisIdField": "axisId",
        "descriptorCollections": ["stateTransitionAxes", "gameEndAxes"],
        "descriptorAxisIdField": "axisId",
        "descriptorClassificationField": "classification",
        "descriptorValueFieldsByClassification": {
            "finite-enumerable": "values",
            "boundary-partition": "boundaryValues",
        },
        "requiredMatchCount": 1,
    }
    _equal(resolver, expected, "PARITY_UNDECIDABLE", "predicateAxisResolution")


def _game_projection(descriptor: dict[str, object], schema: dict[str, object]) -> None:
    """終了判定の明示的な軸・値域・非 coverage field を照合する。"""
    projection = _obj(schema.get("x-pitchlog-descriptor-projection"), "projection")
    _equal(
        projection,
        {
            "descriptorPath": DESCRIPTOR_PATH,
            "identityDefinition": "inputAxesDescriptorBinding",
            "coverageCollection": "gameEndAxes",
            "coverageTargetAnnotation": "x-pitchlog-axis-id",
            "nonCoverageCollection": "nonCoverageFields",
            "nonCoverageTargetAnnotation": "x-pitchlog-non-coverage-field",
            "schemaRetentionAnnotation": "x-pitchlog-schema-retention",
            "requiredSchemaRetention": "required-by-projection",
        },
        "PARITY_UNDECIDABLE",
        "game projection declaration",
    )
    axes = _indexed(descriptor["gameEndAxes"], "axisId", "game axes")
    annotations = _annotations(schema, "x-pitchlog-axis-id")
    if annotations.keys() != axes.keys():
        _fail("AXIS_SET", "game schema axis annotations")
    for axis_id, axis in axes.items():
        node, _ = annotations[axis_id]
        _equal(
            node.get("x-pitchlog-axis-classification"),
            axis.get("classification"),
            "VALUE_RANGE",
            axis_id,
        )
        for source, target in (
            ("coverageBounds", "x-pitchlog-coverage-bounds"),
            ("boundaryValues", "x-pitchlog-boundary-values"),
            ("invalidBoundaryValues", "x-pitchlog-invalid-boundary-values"),
        ):
            if source == "invalidBoundaryValues" and source not in axis:
                if target in node:
                    _fail("VALUE_RANGE", f"{axis_id}.{source}")
                continue
            _exact_values(
                node.get(target), axis.get(source), "VALUE_RANGE", f"{axis_id}.{source}"
            )
    fields = _indexed(descriptor["nonCoverageFields"], "fieldId", "nonCoverage")
    retained = _annotations(schema, "x-pitchlog-non-coverage-field")
    if retained.keys() != fields.keys():
        _fail("NON_COVERAGE", "nonCoverageFields exact-set")
    for field_id, field in fields.items():
        node, required = retained[field_id]
        if not required:
            _fail("NON_COVERAGE", f"{field_id}.required")
        _equal(
            node.get("x-pitchlog-non-coverage-reason"),
            field.get("reason"),
            "NON_COVERAGE",
            f"{field_id}.reason",
        )
        _equal(
            node.get("x-pitchlog-schema-retention"),
            field.get("schemaRetention"),
            "NON_COVERAGE",
            f"{field_id}.retention",
        )
    _game_ranges(schema, axes)


def _game_ranges(schema: dict[str, object], axes: dict[str, dict[str, object]]) -> None:
    """注釈の整数範囲と実際の JSON Schema 制約を照合する。"""
    defs = _obj(schema.get("$defs"), "$defs")
    snapshot = _obj(defs.get("ruleSnapshot"), "ruleSnapshot")
    properties = _obj(snapshot.get("properties"), "ruleSnapshot properties")
    for axis in axes.values():
        field = axis.get("ruleFieldId")
        if not isinstance(field, str):
            _fail("PARITY_UNDECIDABLE", "ruleFieldId")
        node = _obj(properties.get(field), field)
        bounds = _indexed(axis.get("coverageBounds"), "dimension", f"{field}.bounds")
        for dimension, bound in bounds.items():
            if field == "regulationInnings" and dimension == "innings":
                actual = node
            elif field == "coldConditions" and dimension == "tierCount":
                _equal(
                    node.get("maxItems"),
                    bound.get("maximum"),
                    "VALUE_RANGE",
                    "tierCount",
                )
                _equal(bound.get("minimum"), 0, "VALUE_RANGE", "tierCount minimum")
                continue
            elif field == "coldConditions" and dimension in {
                "pointDifference",
                "startInning",
            }:
                tier = _obj(defs.get("coldConditionTier"), "coldConditionTier")
                actual = _obj(
                    _obj(tier.get("properties"), "tier properties").get(dimension),
                    dimension,
                )
            elif (
                axis.get("axisId") == "gameEnd.satisfiedColdTierCount"
                and dimension == "satisfiedTierCount"
            ):
                normalized = _obj(defs.get("normalizedCase"), "normalizedCase")
                coordinate = _obj(
                    _obj(normalized.get("properties"), "normalizedCase properties").get(
                        "inputCoordinate"
                    ),
                    "inputCoordinate",
                )
                actual = _obj(
                    _obj(
                        coordinate.get("properties"), "inputCoordinate properties"
                    ).get("gameEnd.satisfiedColdTierCount"),
                    "satisfiedColdTierCount",
                )
            elif field == "extensionLimit" and dimension == "innings":
                options = _items(node.get("oneOf"), "extensionLimit.oneOf")
                if len(options) != 2:
                    _fail("PARITY_UNDECIDABLE", "extensionLimit.oneOf")
                actual = _obj(options[0], "extensionLimit integer")
                _equal(
                    _obj(options[1], "extensionLimit null").get("type"),
                    "null",
                    "VALUE_RANGE",
                    "extensionLimit null",
                )
            elif field == "tiebreak" and dimension == "startInning":
                options = _items(node.get("oneOf"), "tiebreak.oneOf")
                if len(options) != 2:
                    _fail("PARITY_UNDECIDABLE", "tiebreak.oneOf")
                _equal(
                    _obj(options[0], "tiebreak ref").get("$ref"),
                    "#/$defs/tiebreakRule",
                    "VALUE_RANGE",
                    "tiebreak ref",
                )
                _equal(
                    _obj(options[1], "tiebreak null").get("type"),
                    "null",
                    "VALUE_RANGE",
                    "tiebreak null",
                )
                tiebreak = _obj(defs.get("tiebreakRule"), "tiebreakRule")
                actual = _obj(
                    _obj(tiebreak.get("properties"), "tiebreak properties").get(
                        "startInning"
                    ),
                    "startInning",
                )
            else:
                _fail("PARITY_UNDECIDABLE", f"{field}.{dimension}")
            _equal(
                actual.get("type"),
                "integer",
                "VALUE_RANGE",
                f"{field}.{dimension}.type",
            )
            for edge in ("minimum", "maximum"):
                _equal(
                    actual.get(edge),
                    bound.get(edge),
                    "VALUE_RANGE",
                    f"{field}.{dimension}.{edge}",
                )


def _history_depth(history: dict[str, object]) -> int:
    """宣言された max 導出式だけを解釈して D を得る。"""
    _equal(history.get("version"), 1, "HISTORY_DEPTH", "version")
    derivation = _obj(history.get("derivation"), "derivation")
    formula = _obj(derivation.get("formula"), "formula")
    _equal(formula.get("operator"), "max", "PARITY_UNDECIDABLE", "formula operator")
    _equal(
        formula.get("operands"),
        [
            {
                "cases": "requiredScenarioCases",
                "measure": "events.length",
                "aggregate": "max",
            },
            {
                "cases": "stackCompositionCases",
                "measure": "stackKinds.length",
                "aggregate": "max",
            },
        ],
        "PARITY_UNDECIDABLE",
        "formula operands",
    )
    maxima: list[int] = []
    for collection, field, declared in (
        ("requiredScenarioCases", "events", "length"),
        ("stackCompositionCases", "stackKinds", "minimumDepth"),
    ):
        lengths: list[int] = []
        for record in _items(derivation.get(collection), collection):
            case = _obj(record, collection)
            size = len(_items(case.get(field), field))
            if size < 1 or case.get(declared) != size:
                _fail("HISTORY_DEPTH", f"{collection}.{declared}")
            lengths.append(size)
        if not lengths:
            _fail("PARITY_UNDECIDABLE", collection)
        maxima.append(max(lengths))
    _equal(
        _obj(derivation.get("result"), "result").get("historyDepthFrom"),
        "formula",
        "PARITY_UNDECIDABLE",
        "result",
    )
    return max(maxima)


def _history_boundaries(
    descriptor: dict[str, object], history: dict[str, object], depth: int
) -> dict[str, tuple[object, ...]]:
    """D と D+1 を実値にし、履歴資産の case 集合と比較する。"""
    axes = _indexed(descriptor["stateTransitionAxes"], "axisId", "state axes")
    cases = _obj(history.get("caseSets"), "caseSets")
    plus_one = _obj(history.get("historyDepthPlusOne"), "historyDepthPlusOne")
    _equal(
        plus_one.get("valueFrom"),
        "historyDepthPlusOne",
        "HISTORY_DEPTH",
        "historyDepthPlusOne.valueFrom",
    )
    resolved: dict[str, tuple[object, ...]] = {}
    for suffix in ("depth", "scenarioLength"):
        axis_id = f"history.{suffix}"
        if axis_id not in axes:
            _fail("AXIS_SET", axis_id)
        source = _items(axes[axis_id].get("boundaryValues"), axis_id)
        values = tuple(
            depth if value == "D" else depth + 1 if value == "D+1" else value
            for value in source
        )
        if any(isinstance(value, str) and value.startswith("D") for value in values):
            _fail("PARITY_UNDECIDABLE", axis_id)
        expected: list[object] = []
        for item in _items(cases.get(suffix), suffix):
            case = _obj(item, suffix)
            if "value" in case and "valueFrom" not in case:
                expected.append(case["value"])
            elif case.get("valueFrom") == "historyDepth":
                expected.append(depth)
            elif case.get("valueFrom") == "historyDepthPlusOne":
                expected.append(depth + 1)
            else:
                _fail("PARITY_UNDECIDABLE", f"{suffix}.valueFrom")
        _exact_values(list(values), expected, "HISTORY_DEPTH", axis_id)
        resolved[axis_id] = values
    composition = _items(cases.get("composition"), "composition")
    declared_cases = _indexed(
        _obj(history["derivation"], "derivation").get("stackCompositionCases"),
        "id",
        "stack cases",
    )
    _exact_values(
        composition, list(declared_cases), "HISTORY_DEPTH", "composition cases"
    )
    # descriptor の coverage 名と資産の case ID の対応を明示して固定する。
    aliases = {
        "top-and-second-different": "top-two-different",
        "all-elements-same-kind": "all-same",
    }
    expected_composition = [aliases.get(value, value) for value in composition]
    if "history.composition" not in axes:
        _fail("AXIS_SET", "history.composition")
    _exact_values(
        axes["history.composition"].get("boundaryValues"),
        expected_composition,
        "HISTORY_DEPTH",
        "history.composition",
    )
    resolved["history.composition"] = tuple(expected_composition)
    return resolved


def check_descriptor_parity(
    root: Path, loaded: LoadedHandoff
) -> DescriptorParityResult:
    """読み込み済み handoff と派生 schema を全射影規則で照合する。

    Args:
        root: 既知の契約・schema・履歴資産を含むリポジトリのルート。
        loaded: ``load_handoff`` が返した版検査済みの入力。

    Returns:
        照合した規則 ID と実値へ解決した D と履歴境界。

    Raises:
        DescriptorParityError: 不一致または判定不能の場合。
    """
    descriptor = _obj(dict(loaded.descriptor), "descriptor")
    _, file_descriptor = _read(root, DESCRIPTOR_PATH)
    _equal(file_descriptor, descriptor, "DESCRIPTOR_IDENTITY", "loaded descriptor")
    _, handoff = _read(root, HANDOFF_PATH)
    _, state_schema = _read(root, STATE_SCHEMA)
    _, game_schema = _read(root, GAME_SCHEMA)
    raw_history, history = _read(root, HISTORY_PATH)
    _equal(
        state_schema.get("version"),
        "state_transition_contract_schema_v1",
        "SCHEMA_VERSION",
        STATE_SCHEMA,
    )
    _equal(
        game_schema.get("version"),
        "game_end_contract_schema_v1",
        "SCHEMA_VERSION",
        GAME_SCHEMA,
    )
    rules = _rules(descriptor)
    _identity(descriptor, handoff, [state_schema, game_schema])
    _state_reference(state_schema)
    _game_projection(descriptor, game_schema)
    depth = _history_depth(history)
    boundaries = _history_boundaries(descriptor, history, depth)
    actual_digest = "sha256:" + hashlib.sha256(raw_history).hexdigest()
    if actual_digest != DEPENDENCIES[HISTORY_PATH][1]:
        _fail("HISTORY_DEPTH", "pinned history-depth.json digest")
    return DescriptorParityResult(tuple(rules), depth, boundaries)


__all__ = ["DescriptorParityError", "DescriptorParityResult", "check_descriptor_parity"]
