"""正本と表示語彙 schema から要求 case 集合を独立導出する。

`ADR-003 D-11 ② 入力範囲表 (β)①〜⑤ の集計行` の slash 区切りを
軸の母集合とし、`vocabulary.schema.json` の primitive union と値域を
case 生成へ使う。資産に書かれた case の自己申告から要求集合を作らない。
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from typing import cast

_AUTHORITY_ID = "ADR-003 D-11 入力範囲表"
_ADR_SOURCE = "docs/adr/ADR-003-domain-calc-method.md"
_ADR_SECTION = (
    "### D-11: (b) の検査設計"
    "(**決定** — 要件書 v2.2 の再定義後の条文に対する具体化)"
)
_TABLE_TARGET = "(β)①〜⑤ の集計"
_VOCABULARY_SOURCE = "backend/domain/vocabulary.schema.json"
_AXIS_SEPARATOR = "/"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]*$")


class CoverageError(Exception):
    """要求 case の導出または網羅性の不適合を表す。"""


@dataclass(frozen=True, slots=True)
class CoverageProof:
    """要求 case 集合と実行証跡集合の双方向差分。

    Attributes:
        required: 正本と schema から導出済みの要求 case ID。
        observed: Runner が消費した case ID。
        missing: 要求にあり証跡に無い case ID。
        unexpected: 証跡にあり要求に無い case ID。
    """

    required: frozenset[str]
    observed: frozenset[str]
    missing: frozenset[str]
    unexpected: frozenset[str]

    @property
    def complete(self) -> bool:
        """双方向の集合差が無く、要求集合が非空なら真を返す。"""
        return bool(self.required) and not self.missing and not self.unexpected


def _mapping(value: object, label: str) -> dict[str, object]:
    """文字列キーの object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise CoverageError(f"{label} が object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """Array を返す。"""
    if not isinstance(value, list):
        raise CoverageError(f"{label} が array でない")
    return value


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise CoverageError(f"{label} が空でない文字列でない")
    return value


def _section_text(source_text: str, heading: str) -> str:
    """Markdown 正本から指定見出しの節だけを取り出す。"""
    lines = source_text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError as error:
        raise CoverageError(f"正本に節見出しが無い: {heading}") from error
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        matched = re.match(r"^(#+)\s", lines[index])
        if matched is not None and len(matched.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _extract_axis_texts(adr_text: str) -> tuple[str, ...]:
    """D-11 の対象行から表示 primitive の軸列挙を抽出する。"""
    section = _section_text(adr_text, _ADR_SECTION)
    row = next(
        (
            line
            for line in section.splitlines()
            if line.startswith(f"| {_TABLE_TARGET} |")
        ),
        None,
    )
    if row is None:
        raise CoverageError(f"正本に入力範囲表の対象行が無い: {_TABLE_TARGET}")
    matched = re.search(
        r":\s*\*\*(?P<axes>.+?)\*\*。\*\*軸の組合せ要件",
        row,
    )
    if matched is None:
        raise CoverageError("対象行から表示 primitive の軸列挙を抽出できない")
    axes = tuple(
        axis.strip()
        for axis in re.split(r"\s*/\s*", matched.group("axes"))
    )
    if not axes or any(not axis for axis in axes):
        raise CoverageError("表示 primitive の軸列挙が空または不正")
    return axes


def _schema_definitions(schema: Mapping[str, object]) -> dict[str, object]:
    """語彙 schema の定義表を返す。"""
    return _mapping(schema.get("$defs"), "vocabulary.$defs")


def _primitive_definitions(
    schema: Mapping[str, object],
) -> dict[str, tuple[str, dict[str, object]]]:
    """NumericPrimitive union から kind と定義を導出する。"""
    definitions = _schema_definitions(schema)
    union = _mapping(definitions.get("NumericPrimitive"), "NumericPrimitive")
    branches = _array(union.get("oneOf"), "NumericPrimitive.oneOf")
    primitives: dict[str, tuple[str, dict[str, object]]] = {}
    for index, raw_branch in enumerate(branches):
        branch = _mapping(raw_branch, f"NumericPrimitive.oneOf[{index}]")
        reference = _string(branch.get("$ref"), "NumericPrimitive.$ref")
        prefix = "#/$defs/"
        if not reference.startswith(prefix):
            raise CoverageError(f"外部 primitive 参照は使えない: {reference}")
        definition_name = reference.removeprefix(prefix)
        definition = _mapping(
            definitions.get(definition_name),
            f"vocabulary.$defs.{definition_name}",
        )
        properties = _mapping(
            definition.get("properties"),
            f"{definition_name}.properties",
        )
        kind_schema = _mapping(properties.get("kind"), f"{definition_name}.kind")
        kind = _string(kind_schema.get("const"), f"{definition_name}.kind.const")
        if kind in primitives:
            raise CoverageError(f"primitive kind が重複: {kind}")
        primitives[kind] = (definition_name, definition)
    metadata = _mapping(schema.get("x-pitchlog"), "vocabulary.x-pitchlog")
    closed_sets = _mapping(metadata.get("closedSets"), "closedSets")
    declared = {
        _string(item, "numericPrimitives[]")
        for item in _array(closed_sets.get("numericPrimitives"), "numericPrimitives")
    }
    if set(primitives) != declared:
        raise CoverageError("NumericPrimitive union と閉集合の差がある")
    return primitives


def _axis_kind(source_text: str) -> str:
    """正本の軸逐語を閉じた機械 ID へ対応づける。"""
    signatures = (
        ("丸め境界", "rounding-boundary"),
        ("scale ", "scale-boundary"),
        ("正・負・0", "sign"),
        ("分母 0", "zero-denominator"),
        ("集計対象 0 件", "empty-aggregate"),
        ("剰余 0・1・分母−1", "remainder"),
        ("nullable", "nullable"),
        ("オーバーフロー", "overflow"),
    )
    matched = [
        axis_id
        for prefix, axis_id in signatures
        if source_text.startswith(prefix)
    ]
    if len(matched) != 1:
        raise CoverageError(f"未知または曖昧な表示 primitive 軸: {source_text}")
    return matched[0]


def _axis_partitions(axis_id: str) -> list[str]:
    """一軸の機械可読な同値分割を返す。"""
    partitions = {
        "rounding-boundary": ["before", "exact", "after"],
        "scale-boundary": ["minimum", "maximum"],
        "sign": ["positive", "negative", "zero"],
        "zero-denominator": ["zero"],
        "empty-aggregate": ["all-missing"],
        "remainder": ["zero", "one", "denominator-minus-one"],
        "nullable": ["null"],
        "overflow": ["signed-64-bit-maximum-plus-one"],
    }
    try:
        return partitions[axis_id]
    except KeyError as error:
        raise CoverageError(f"分割を持たない軸: {axis_id}") from error


def _axis_schema_pointers(
    axis_id: str,
    primitives: Mapping[str, tuple[str, dict[str, object]]],
) -> list[str]:
    """軸の値域を与える語彙 schema の JSON Pointer を返す。"""
    fixed_name = primitives["fixed-decimal"][0]
    percentage_name = primitives["percentage"][0]
    mixed_name = primitives["mixed-fraction"][0]
    pointers = {
        "rounding-boundary": [
            f"#/$defs/{fixed_name}/properties/rounding",
            f"#/$defs/{percentage_name}/properties/rounding",
        ],
        "scale-boundary": [
            f"#/$defs/{fixed_name}/properties/scale",
            f"#/$defs/{percentage_name}/properties/scale",
        ],
        "sign": ["#/$defs/NumericValue"],
        "zero-denominator": [
            "#/$defs/RationalValue/properties/denominator"
        ],
        "empty-aggregate": ["#/$defs/NumericValue"],
        "remainder": [
            f"#/$defs/{mixed_name}/properties/denominator",
            f"#/$defs/{mixed_name}/properties/zeroRemainder",
        ],
        "nullable": [
            "#/$defs/NumericValue",
            "#/$defs/NullSubstitute/properties/substitute",
        ],
        "overflow": ["#/$defs/IntegerValue/properties/value"],
    }
    return pointers[axis_id]


def _const_property(
    definition: Mapping[str, object],
    property_name: str,
) -> object:
    """Primitive 定義の const 値を返す。"""
    properties = _mapping(definition.get("properties"), "primitive.properties")
    property_schema = _mapping(
        properties.get(property_name),
        f"primitive.properties.{property_name}",
    )
    if "const" not in property_schema:
        raise CoverageError(f"primitive parameter が const でない: {property_name}")
    return property_schema["const"]


def _integer_bounds(
    definition: Mapping[str, object],
    property_name: str,
) -> tuple[int, int]:
    """Primitive 整数 parameter の有限な上下限を返す。"""
    properties = _mapping(definition.get("properties"), "primitive.properties")
    property_schema = _mapping(
        properties.get(property_name),
        f"primitive.properties.{property_name}",
    )
    minimum = property_schema.get("minimum")
    maximum = property_schema.get("maximum")
    if (
        not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or minimum > maximum
    ):
        raise CoverageError(f"{property_name} に有限な整数上下限が無い")
    return minimum, maximum


def _primitive_instance(
    kind: str,
    definition: Mapping[str, object],
    *,
    scale: int | None = None,
) -> dict[str, object]:
    """語彙 schema の必須 parameter を満たす primitive 入力を作る。"""
    required = [
        _string(item, "primitive.required[]")
        for item in _array(definition.get("required"), "primitive.required")
    ]
    properties = _mapping(definition.get("properties"), "primitive.properties")
    instance: dict[str, object] = {}
    for name in required:
        node = _mapping(properties.get(name), f"primitive.properties.{name}")
        if name == "kind":
            instance[name] = kind
        elif name == "scale" and scale is not None:
            instance[name] = scale
        elif "const" in node:
            instance[name] = node["const"]
        elif node.get("type") == "boolean":
            instance[name] = False
        elif name == "integerSuffix":
            instance[name] = "回"
        elif "enum" in node:
            values = _array(node["enum"], f"primitive.{name}.enum")
            if not values:
                raise CoverageError(f"primitive enum が空: {name}")
            instance[name] = values[0]
        elif name == "denominator":
            minimum = node.get("minimum")
            if not isinstance(minimum, int) or isinstance(minimum, bool):
                raise CoverageError("denominator の minimum が整数でない")
            instance[name] = minimum + 2
        elif node.get("type") == "string":
            instance[name] = "−"
        else:
            raise CoverageError(f"fixture 値を導出できない parameter: {name}")
    return instance


def _cover(axis_id: str, partition_id: str) -> dict[str, str]:
    """一つの軸分割への帰属を返す。"""
    return {"axisId": axis_id, "partitionId": partition_id}


def _case(
    case_id: str,
    covers: list[dict[str, str]],
    input_value: object,
) -> dict[str, object]:
    """要求 case の厳密な外形を返す。"""
    return {
        "id": case_id,
        "authorityId": _AUTHORITY_ID,
        "covers": covers,
        "input": input_value,
    }


def _rounding_sign_cases(
    fixed: tuple[str, dict[str, object]],
) -> list[dict[str, object]]:
    """丸め境界 3 分割と正負の直積 case を生成する。"""
    _, definition = fixed
    minimum_scale, maximum_scale = _integer_bounds(definition, "scale")
    boundary_by_sign = {
        "positive": Decimal("0.3335"),
        "negative": Decimal("-1.5"),
    }
    step = Decimal("0.0001")
    result: list[dict[str, object]] = []
    for position, sign in product(
        ("before", "exact", "after"),
        ("positive", "negative"),
    ):
        boundary = boundary_by_sign[sign]
        direction = Decimal(1) if sign == "positive" else Decimal(-1)
        offset = {"before": -step, "exact": Decimal(0), "after": step}[position]
        value = boundary + (offset * direction)
        scale = maximum_scale if sign == "positive" else minimum_scale
        primitive = _primitive_instance(
            "fixed-decimal",
            definition,
            scale=scale,
        )
        result.append(
            _case(
                f"display.rounding.{position}.{sign}",
                [
                    _cover("rounding-boundary", position),
                    _cover("sign", sign),
                ],
                {
                    "primitive": primitive,
                    "value": {
                        "kind": "exact-decimal",
                        "value": format(value, "f"),
                    },
                },
            )
        )
    return result


def _scale_cases(
    primitives: Mapping[str, tuple[str, dict[str, object]]],
) -> list[dict[str, object]]:
    """Scale を持つ全 primitive の schema 上下限 case を生成する。"""
    result: list[dict[str, object]] = []
    for kind, (_, definition) in primitives.items():
        properties = _mapping(definition.get("properties"), f"{kind}.properties")
        if "scale" not in properties:
            continue
        minimum, maximum = _integer_bounds(definition, "scale")
        for boundary, scale in (("minimum", minimum), ("maximum", maximum)):
            result.append(
                _case(
                    f"display.scale.{kind}.{boundary}.{scale}",
                    [_cover("scale-boundary", boundary)],
                    {
                        "primitive": _primitive_instance(
                            kind,
                            definition,
                            scale=scale,
                        ),
                        "value": {"kind": "integer", "value": 1},
                    },
                )
            )
    if not result:
        raise CoverageError("scale を持つ primitive が無い")
    return result


def _remaining_cases(
    primitives: Mapping[str, tuple[str, dict[str, object]]],
    vocabulary_schema: Mapping[str, object],
) -> list[dict[str, object]]:
    """直積と scale 以外の軸 case を schema 値域から生成する。"""
    definitions = _schema_definitions(vocabulary_schema)
    numeric_value = _mapping(definitions.get("NumericValue"), "NumericValue")
    numeric_branches = _array(numeric_value.get("oneOf"), "NumericValue.oneOf")
    if not any(
        _mapping(branch, "NumericValue.oneOf[]").get("type") == "null"
        for branch in numeric_branches
    ):
        raise CoverageError("NumericValue union に nullable 分岐が無い")
    rational = _mapping(definitions.get("RationalValue"), "RationalValue")
    rational_properties = _mapping(
        rational.get("properties"),
        "RationalValue.properties",
    )
    rational_denominator = _mapping(
        rational_properties.get("denominator"),
        "RationalValue.denominator",
    )
    denominator_minimum = rational_denominator.get("minimum")
    if not isinstance(denominator_minimum, int) or isinstance(
        denominator_minimum,
        bool,
    ):
        raise CoverageError("RationalValue.denominator の minimum が整数でない")
    zero_denominator = denominator_minimum - 1
    if zero_denominator:
        raise CoverageError("schema 境界の直前が分母 0 にならない")
    mixed = primitives["mixed-fraction"][1]
    null_substitute = primitives["null-substitute"][1]
    mixed_primitive = _primitive_instance("mixed-fraction", mixed)
    denominator = mixed_primitive["denominator"]
    if not isinstance(denominator, int) or isinstance(denominator, bool):
        raise CoverageError("合成分数の denominator を導出できない")
    remainder_values = {
        "zero": denominator,
        "one": denominator + 1,
        "denominator-minus-one": (denominator * 2) - 1,
    }
    result = [
        _case(
            "display.sign.zero",
            [_cover("sign", "zero")],
            {"value": {"kind": "integer", "value": 0}},
        ),
        _case(
            "display.denominator.zero",
            [_cover("zero-denominator", "zero")],
            {
                "operation": "division",
                "numerator": 1,
                "denominator": zero_denominator,
            },
        ),
        _case(
            "display.aggregate.all-missing",
            [_cover("empty-aggregate", "all-missing")],
            {"values": [None, None], "nonNullCount": 0},
        ),
    ]
    for partition, numerator in remainder_values.items():
        result.append(
            _case(
                f"display.remainder.{partition}",
                [_cover("remainder", partition)],
                {
                    "primitive": copy.deepcopy(mixed_primitive),
                    "value": {
                        "kind": "rational",
                        "numerator": numerator,
                        "denominator": denominator,
                    },
                },
            )
        )
    result.extend(
        [
            _case(
                "display.nullable.null",
                [_cover("nullable", "null")],
                {
                    "primitive": _primitive_instance(
                        "null-substitute",
                        null_substitute,
                    ),
                    "value": None,
                },
            ),
            _case(
                "display.overflow.signed-64-bit-maximum-plus-one",
                [
                    _cover(
                        "overflow",
                        "signed-64-bit-maximum-plus-one",
                    )
                ],
                {
                    "value": {
                        "kind": "integer",
                        "value": 2**63,
                    },
                    "signedWidth": 64,
                },
            ),
        ]
    )
    return result


def derive_required_case_asset(
    adr_text: str,
    vocabulary_schema: Mapping[str, object],
) -> dict[str, object]:
    """正本の軸と語彙 schema から要求 case 資産を導出する。

    Args:
        adr_text: `ADR-003` の全文。
        vocabulary_schema: ステップ 1 の表示語彙 schema。

    Returns:
        軸、導出規則、具体的な合成要求 case を持つ資産。

    Raises:
        CoverageError: 正本または schema から一意に導出できない場合。
    """
    axis_texts = _extract_axis_texts(adr_text)
    primitives = _primitive_definitions(vocabulary_schema)
    axes: list[dict[str, object]] = []
    seen_axis_ids: set[str] = set()
    for source_text in axis_texts:
        axis_id = _axis_kind(source_text)
        if axis_id in seen_axis_ids:
            raise CoverageError(f"正本の表示 primitive 軸が重複: {axis_id}")
        seen_axis_ids.add(axis_id)
        axes.append(
            {
                "id": axis_id,
                "sourceText": source_text,
                "partitions": _axis_partitions(axis_id),
                "schemaPointers": _axis_schema_pointers(axis_id, primitives),
            }
        )
    cases = [
        *_rounding_sign_cases(primitives["fixed-decimal"]),
        *_scale_cases(primitives),
        *_remaining_cases(primitives, vocabulary_schema),
    ]
    asset: dict[str, object] = {
        "schemaVersion": 1,
        "authority": {
            "id": _AUTHORITY_ID,
            "source": _ADR_SOURCE,
            "section": _ADR_SECTION,
            "tableTarget": _TABLE_TARGET,
        },
        "vocabularySchema": {
            "source": _VOCABULARY_SOURCE,
            "primitiveUnion": "#/$defs/NumericPrimitive",
            "numericValueUnion": "#/$defs/NumericValue",
        },
        "derivation": {
            "axisExtraction": {
                "syntax": "slash-separated-bold-list",
                "separator": _AXIS_SEPARATOR,
            },
            "caseIdentity": "authority-id + axis-partition + schema-boundary",
            "combinationRules": [
                {
                    "axes": ["rounding-boundary", "sign"],
                    "operation": "cartesian-product",
                    "partitions": {
                        "rounding-boundary": ["before", "exact", "after"],
                        "sign": ["positive", "negative"],
                    },
                },
                {
                    "axis": "scale-boundary",
                    "operation": "schema-minimum-maximum-per-primitive",
                },
                {
                    "axesFrom": "authority-row",
                    "operation": "cover-every-partition",
                },
            ],
            "concreteValuePolicy": {
                "positiveRoundingBoundary": "0.3335",
                "negativeRoundingBoundary": "-1.5",
                "roundingNeighborStep": "0.0001",
                "overflow": "signed-64-bit-maximum-plus-one",
            },
        },
        "axes": axes,
        "requiredCases": cases,
    }
    validate_required_case_set(asset)
    return asset


def _case_points(case: Mapping[str, object]) -> set[tuple[str, str]]:
    """一 case が覆う軸と分割の組を返す。"""
    points: set[tuple[str, str]] = set()
    for index, raw_cover in enumerate(_array(case.get("covers"), "case.covers")):
        cover = _mapping(raw_cover, f"case.covers[{index}]")
        if set(cover) != {"axisId", "partitionId"}:
            raise CoverageError("case.covers のキー集合が不正")
        point = (
            _string(cover.get("axisId"), "cover.axisId"),
            _string(cover.get("partitionId"), "cover.partitionId"),
        )
        if point in points:
            raise CoverageError(f"case 内で軸分割が重複: {point!r}")
        points.add(point)
    if not points:
        raise CoverageError("軸分割を一つも覆わない case がある")
    return points


def validate_required_case_set(asset: Mapping[str, object]) -> None:
    """要求 case 資産の exact-set、全軸、直積を検査する。

    Args:
        asset: 検査する要求 case 資産。

    Raises:
        CoverageError: 外形、軸の母集合、直積のいずれかが不適合な場合。
    """
    if set(asset) != {
        "schemaVersion",
        "authority",
        "vocabularySchema",
        "derivation",
        "axes",
        "requiredCases",
    }:
        raise CoverageError("required-cases 資産のキー集合が不正")
    if asset.get("schemaVersion") != 1:
        raise CoverageError("required-cases schemaVersion が不正")
    authority = _mapping(asset.get("authority"), "authority")
    if set(authority) != {"id", "source", "section", "tableTarget"}:
        raise CoverageError("authority のキー集合が不正")
    if authority.get("id") != _AUTHORITY_ID:
        raise CoverageError("要求 case の典拠 ID が不正")
    axes = [_mapping(item, "axes[]") for item in _array(asset.get("axes"), "axes")]
    if len(axes) != 8:
        raise CoverageError(f"表示 primitive 軸が 8 件でない: {len(axes)}")
    axis_partitions: dict[str, set[str]] = {}
    for axis in axes:
        if set(axis) != {"id", "sourceText", "partitions", "schemaPointers"}:
            raise CoverageError("axes[] のキー集合が不正")
        axis_id = _string(axis.get("id"), "axis.id")
        if _IDENTIFIER.fullmatch(axis_id) is None or axis_id in axis_partitions:
            raise CoverageError(f"軸 ID が不正または重複: {axis_id}")
        partitions = {
            _string(item, "axis.partitions[]")
            for item in _array(axis.get("partitions"), "axis.partitions")
        }
        pointers = {
            _string(item, "axis.schemaPointers[]")
            for item in _array(axis.get("schemaPointers"), "axis.schemaPointers")
        }
        if not partitions or not pointers:
            raise CoverageError(f"軸の分割または schema 参照が空: {axis_id}")
        axis_partitions[axis_id] = partitions
    cases = [
        _mapping(item, "requiredCases[]")
        for item in _array(asset.get("requiredCases"), "requiredCases")
    ]
    if not cases:
        raise CoverageError("要求 case 集合が空")
    case_ids: list[str] = []
    observed_points: set[tuple[str, str]] = set()
    cross_pairs: list[tuple[str, str]] = []
    for case in cases:
        if set(case) != {"id", "authorityId", "covers", "input"}:
            raise CoverageError("requiredCases[] のキー集合が不正")
        case_id = _string(case.get("id"), "case.id")
        if case.get("authorityId") != _AUTHORITY_ID:
            raise CoverageError(f"case の典拠 ID が不正: {case_id}")
        case_ids.append(case_id)
        points = _case_points(case)
        for axis_id, partition_id in points:
            if partition_id not in axis_partitions.get(axis_id, set()):
                raise CoverageError(
                    f"未知の軸分割: {axis_id}.{partition_id}"
                )
        observed_points.update(points)
        by_axis = dict(points)
        if "rounding-boundary" in by_axis and "sign" in by_axis:
            cross_pairs.append(
                (by_axis["rounding-boundary"], by_axis["sign"])
            )
    if len(case_ids) != len(set(case_ids)):
        raise CoverageError("要求 case ID が重複")
    expected_points = {
        (axis_id, partition_id)
        for axis_id, partitions in axis_partitions.items()
        for partition_id in partitions
    }
    missing_points = expected_points - observed_points
    if missing_points:
        raise CoverageError(f"case の無い軸分割: {sorted(missing_points)!r}")
    expected_cross = set(
        product(
            ("before", "exact", "after"),
            ("positive", "negative"),
        )
    )
    if set(cross_pairs) != expected_cross or len(cross_pairs) != len(expected_cross):
        raise CoverageError("丸め境界と正負の直積が完全一致しない")
    if ("exact", "negative") not in cross_pairs:
        raise CoverageError("負値の丸め境界一致 case が無い")


def validate_required_case_asset(
    asset: Mapping[str, object],
    adr_text: str,
    vocabulary_schema: Mapping[str, object],
) -> None:
    """固定資産が独立導出結果と完全一致することを検査する。"""
    validate_required_case_set(asset)
    derived = derive_required_case_asset(adr_text, vocabulary_schema)
    if asset != derived:
        raise CoverageError("required-cases 資産が正本と schema の導出結果に一致しない")


def required_case_ids(asset: Mapping[str, object]) -> frozenset[str]:
    """検証済み資産から要求 case ID 集合を返す。"""
    validate_required_case_set(asset)
    return frozenset(
        _string(_mapping(item, "requiredCases[]").get("id"), "case.id")
        for item in _array(asset.get("requiredCases"), "requiredCases")
    )


def prove_case_coverage(
    asset: Mapping[str, object],
    evidence_case_ids: Iterable[str],
) -> CoverageProof:
    """要求 case 集合と runner 証跡集合を双方向で突合する。"""
    required = required_case_ids(asset)
    observed_items = tuple(evidence_case_ids)
    if any(not isinstance(case_id, str) or not case_id for case_id in observed_items):
        raise CoverageError("証跡 case ID が空でない文字列でない")
    if len(observed_items) != len(set(observed_items)):
        raise CoverageError("証跡 case ID が重複")
    observed = frozenset(observed_items)
    return CoverageProof(
        required=required,
        observed=observed,
        missing=required - observed,
        unexpected=observed - required,
    )


def require_complete_coverage(
    asset: Mapping[str, object],
    evidence_case_ids: Iterable[str],
) -> CoverageProof:
    """集合差が無い証跡だけを受理し、網羅性の証明を返す。"""
    proof = prove_case_coverage(asset, evidence_case_ids)
    if not proof.complete:
        raise CoverageError(
            "要求 case 集合と証跡集合が不一致: "
            f"missing={sorted(proof.missing)!r}, "
            f"unexpected={sorted(proof.unexpected)!r}"
        )
    return proof


__all__ = [
    "CoverageError",
    "CoverageProof",
    "derive_required_case_asset",
    "prove_case_coverage",
    "require_complete_coverage",
    "required_case_ids",
    "validate_required_case_asset",
    "validate_required_case_set",
]
