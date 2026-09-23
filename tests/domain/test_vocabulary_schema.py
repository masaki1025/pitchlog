"""ADR-003 D-1 の閉じた表示語彙 schema を検査する。

パス allowlist は本ステップでは検査しない。各ステップの allowlist はステップ 3 の
`step-authorities.json` が宣言し、コミット差分との突合はステップ 51 が履歴に対して行う。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "backend/domain/vocabulary.schema.json"
REQUIREMENTS_PATH = ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"


class SchemaValidationError(AssertionError):
    """テスト対象の JSON Schema に入力が適合しないことを表す。"""


def _resolve_ref(schema: dict[str, Any], ref: str) -> dict[str, Any]:
    """同一 schema 内の JSON Pointer を解決する。

    Args:
        schema: 参照元となる JSON Schema。
        ref: `#` から始まるローカル参照。

    Returns:
        参照先の schema 断片。
    """
    if not ref.startswith("#/"):
        raise SchemaValidationError(f"ローカル参照ではありません: {ref}")
    node: Any = schema
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        node = node[token]
    if not isinstance(node, dict):
        raise SchemaValidationError(f"参照先が schema ではありません: {ref}")
    return node


def _matches_type(instance: Any, expected: str) -> bool:
    """JSON Schema の基本型に適合するかを返す。"""
    match expected:
        case "object":
            return isinstance(instance, dict)
        case "array":
            return isinstance(instance, list)
        case "string":
            return isinstance(instance, str)
        case "integer":
            return isinstance(instance, int) and not isinstance(instance, bool)
        case "boolean":
            return isinstance(instance, bool)
        case "null":
            return instance is None
        case _:
            raise SchemaValidationError(f"テスト検証器が未対応の型です: {expected}")


def _validate(instance: Any, node: dict[str, Any], schema: dict[str, Any], path: str = "$") -> None:
    """本 schema が使うキーワードで入力を検証する。

    依存追加を避けるため、ステップ 1 の schema が使う JSON Schema キーワードだけを
    テスト内で解釈する。未知のキーワードは schema の注釈として扱う。
    """
    if "$ref" in node:
        _validate(instance, _resolve_ref(schema, node["$ref"]), schema, path)
        return

    if "oneOf" in node:
        matched = 0
        for branch in node["oneOf"]:
            try:
                _validate(instance, branch, schema, path)
            except SchemaValidationError:
                continue
            matched += 1
        if matched != 1:
            raise SchemaValidationError(f"{path}: oneOf の適合数が {matched} 件です")

    if "const" in node and instance != node["const"]:
        raise SchemaValidationError(f"{path}: const に適合しません")
    if "enum" in node and instance not in node["enum"]:
        raise SchemaValidationError(f"{path}: enum に適合しません")

    expected_type = node.get("type")
    if expected_type is not None and not _matches_type(instance, expected_type):
        raise SchemaValidationError(f"{path}: {expected_type} ではありません")

    if isinstance(instance, dict):
        required = set(node.get("required", []))
        missing = required - instance.keys()
        if missing:
            raise SchemaValidationError(f"{path}: 必須キーがありません: {sorted(missing)}")
        if len(instance) < node.get("minProperties", 0):
            raise SchemaValidationError(f"{path}: プロパティ数が不足しています")

        properties = node.get("properties", {})
        additional = node.get("additionalProperties", True)
        for key, value in instance.items():
            child_path = f"{path}.{key}"
            if key in properties:
                _validate(value, properties[key], schema, child_path)
            elif additional is False:
                raise SchemaValidationError(f"{child_path}: 未知のキーです")
            elif isinstance(additional, dict):
                _validate(value, additional, schema, child_path)

    if isinstance(instance, list):
        if len(instance) < node.get("minItems", 0):
            raise SchemaValidationError(f"{path}: 要素数が不足しています")
        if "items" in node:
            for index, item in enumerate(instance):
                _validate(item, node["items"], schema, f"{path}[{index}]")

    if isinstance(instance, str):
        if len(instance) < node.get("minLength", 0):
            raise SchemaValidationError(f"{path}: 文字数が不足しています")
        if "pattern" in node and re.fullmatch(node["pattern"], instance) is None:
            raise SchemaValidationError(f"{path}: pattern に適合しません")

    if isinstance(instance, int) and not isinstance(instance, bool):
        if "minimum" in node and instance < node["minimum"]:
            raise SchemaValidationError(f"{path}: minimum より小さい値です")
        if "maximum" in node and instance > node["maximum"]:
            raise SchemaValidationError(f"{path}: maximum より大きい値です")


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """語彙 schema を読み込む。"""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _assert_valid(instance: Any, schema: dict[str, Any], ref: str | None = None) -> None:
    node = schema if ref is None else {"$ref": ref}
    _validate(instance, node, schema)


def _assert_rejected(instance: Any, schema: dict[str, Any], ref: str | None = None) -> None:
    with pytest.raises(SchemaValidationError):
        _assert_valid(instance, schema, ref)


def _valid_template() -> dict[str, Any]:
    return {
        "kind": "template",
        "id": "pitchTypeShare",
        "pattern": "{name} {share}({count}球)",
        "placeholders": {
            "name": {
                "type": "DisplayAtom",
                "source": {
                    "kind": "resolved-name",
                    "vocabularyId": "pitch-types",
                    "entityId": "slider",
                },
            },
            "share": {
                "type": "DisplayAtom",
                "source": {
                    "kind": "numeric-primitive-output",
                    "primitiveId": "integerPercentage",
                    "value": {"kind": "rational", "numerator": 2, "denominator": 5},
                },
            },
            "count": {
                "type": "DisplayAtom",
                "source": {
                    "kind": "enum-map-output",
                    "mapId": "countLabels",
                    "value": "twelve",
                },
            },
        },
    }


def _valid_fixed_decimal() -> dict[str, Any]:
    return {
        "kind": "fixed-decimal",
        "scale": 3,
        "rounding": "half-up",
        "leadingZero": False,
        "sign": "negative-only-hyphen-minus",
    }


def test_closed_sets_are_exact(schema: dict[str, Any]) -> None:
    closed = schema["x-pitchlog"]["closedSets"]
    assert closed["displayRuleKinds"] == ["enum-map", "template", "numeric-primitive"]
    assert len(closed["displayRuleKinds"]) == 3
    assert closed["numericValueForms"] == ["integer", "exact-decimal", "rational"]
    assert len(closed["numericValueForms"]) == 3
    assert closed["displayAtomSources"] == [
        "numeric-primitive-output",
        "enum-map-output",
        "resolved-name",
    ]
    assert len(closed["displayAtomSources"]) == 3
    assert closed["numericPrimitives"] == [
        "fixed-decimal",
        "percentage",
        "mixed-fraction",
        "null-substitute",
    ]
    assert len(closed["numericPrimitives"]) == 4

    display_rule_definitions = [
        branch["$ref"].rsplit("/", maxsplit=1)[1] for branch in schema["oneOf"]
    ]
    assert display_rule_definitions == [
        "EnumDisplayMap",
        "DisplayTemplate",
        "NumericDisplayPrimitive",
    ]

    numeric_value_branches = schema["$defs"]["NumericValue"]["oneOf"]
    assert [branch["$ref"].rsplit("/", maxsplit=1)[1] for branch in numeric_value_branches[:3]] == [
        "IntegerValue",
        "ExactDecimalValue",
        "RationalValue",
    ]
    assert numeric_value_branches[3] == {"type": "null"}

    source_definitions = [
        branch["$ref"].rsplit("/", maxsplit=1)[1]
        for branch in schema["$defs"]["DisplayAtomSource"]["oneOf"]
    ]
    assert source_definitions == ["NumericPrimitiveOutput", "EnumMapOutput", "ResolvedName"]

    primitive_definitions = [
        branch["$ref"].rsplit("/", maxsplit=1)[1]
        for branch in schema["$defs"]["NumericPrimitive"]["oneOf"]
    ]
    assert primitive_definitions == [
        "FixedDecimal",
        "Percentage",
        "MixedFraction",
        "NullSubstitute",
    ]

    assert len(display_rule_definitions) == 3
    assert len(numeric_value_branches) - 1 == 3
    assert len(source_definitions) == 3
    assert len(primitive_definitions) == 4


def test_three_display_rule_declarations_are_accepted(schema: dict[str, Any]) -> None:
    enum_map = {
        "kind": "enum-map",
        "id": "inningSideLabels",
        "enumId": "InningSide",
        "stability": "stable",
        "managedBy": "system",
        "members": [
            {"value": "top", "display": "表"},
            {"value": "bottom", "display": "裏"},
        ],
    }
    primitive = {
        "kind": "numeric-primitive",
        "id": "battingAverage",
        "primitive": _valid_fixed_decimal(),
    }

    for declaration in (enum_map, _valid_template(), primitive):
        _assert_valid(declaration, schema)


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "integer", "value": 12},
        {"kind": "exact-decimal", "value": "0.125"},
        {"kind": "rational", "numerator": 2, "denominator": 3},
        None,
    ],
)
def test_numeric_value_three_forms_and_nullable_are_accepted(
    value: Any, schema: dict[str, Any]
) -> None:
    _assert_valid(value, schema, "#/$defs/NumericValue")


@pytest.mark.parametrize(
    "source",
    [
        {
            "kind": "numeric-primitive-output",
            "primitiveId": "integerCount",
            "value": {"kind": "integer", "value": 12},
        },
        {"kind": "enum-map-output", "mapId": "inningSideLabels", "value": "top"},
        {
            "kind": "resolved-name",
            "vocabularyId": "batting-results",
            "entityId": "called-strikeout",
        },
    ],
)
def test_three_display_atom_sources_are_accepted(
    source: dict[str, Any], schema: dict[str, Any]
) -> None:
    _assert_valid(source, schema, "#/$defs/DisplayAtomSource")


@pytest.mark.parametrize(
    "primitive",
    [
        _valid_fixed_decimal(),
        {
            "kind": "percentage",
            "scale": 0,
            "rounding": "half-up",
            "leadingZero": True,
            "symbol": "percent",
        },
        {
            "kind": "mixed-fraction",
            "denominator": 3,
            "integerSuffix": "回",
            "zeroRemainder": "omit-fraction",
            "fractionStyle": "ascii-numerator-slash-denominator",
        },
        {"kind": "null-substitute", "substitute": "−"},
    ],
)
def test_four_numeric_primitives_are_accepted(
    primitive: dict[str, Any], schema: dict[str, Any]
) -> None:
    _assert_valid(primitive, schema, "#/$defs/NumericPrimitive")


def test_unknown_key_is_rejected(schema: dict[str, Any]) -> None:
    declaration = _valid_template()
    declaration["unknown"] = True
    _assert_rejected(declaration, schema)


def test_conditional_declaration_is_rejected(schema: dict[str, Any]) -> None:
    declaration = _valid_template()
    declaration["pattern"] = "{count?value:fallback}"
    _assert_rejected(declaration, schema)


def test_substring_operation_is_rejected(schema: dict[str, Any]) -> None:
    declaration = _valid_template()
    declaration["pattern"] = "{name[0:3]}"
    _assert_rejected(declaration, schema)


def test_numeric_formatting_outside_primitive_is_rejected(schema: dict[str, Any]) -> None:
    declaration = _valid_template()
    declaration["pattern"] = "{share:.1%}"
    _assert_rejected(declaration, schema)


def test_unit_parameter_is_absent_and_rejected(schema: dict[str, Any]) -> None:
    primitive_names = ("FixedDecimal", "Percentage", "MixedFraction", "NullSubstitute")
    forbidden = {"unit", "units", "unitLabel"}
    for name in primitive_names:
        assert forbidden.isdisjoint(schema["$defs"][name]["properties"])

    primitive = _valid_fixed_decimal()
    primitive["unit"] = "km/h"
    _assert_rejected(primitive, schema, "#/$defs/NumericPrimitive")


def test_template_rejects_non_display_atom_placeholder(schema: dict[str, Any]) -> None:
    declaration = _valid_template()
    declaration["placeholders"]["count"] = {"kind": "integer", "value": 12}
    _assert_rejected(declaration, schema)


@pytest.mark.parametrize(
    ("primitive", "scale"),
    [
        (_valid_fixed_decimal(), -1),
        (_valid_fixed_decimal(), 4),
        (
            {
                "kind": "percentage",
                "scale": 0,
                "rounding": "half-up",
                "leadingZero": True,
                "symbol": "percent",
            },
            3,
        ),
    ],
)
def test_out_of_range_scale_is_rejected(
    primitive: dict[str, Any], scale: int, schema: dict[str, Any]
) -> None:
    primitive["scale"] = scale
    _assert_rejected(primitive, schema, "#/$defs/NumericPrimitive")


def _section_lines(document: str, section_id: str) -> list[str]:
    lines = document.splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.startswith(f"### {section_id} ")
    )
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("### ") or lines[index].startswith("## ")
        ),
        len(lines),
    )
    return lines[start:end]


def _markdown_cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _format_bindings_in_section(document: str, section_id: str) -> list[str]:
    lines = _section_lines(document, section_id)
    bindings: list[str] = []
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        headers = _markdown_cells(line)
        if "表示書式" not in headers:
            continue
        format_index = headers.index("表示書式")
        row_index = index + 2
        while row_index < len(lines) and lines[row_index].startswith("|"):
            cells = _markdown_cells(lines[row_index])
            if len(cells) > format_index and "表示書式なし" not in cells[format_index]:
                bindings.append(cells[0])
            row_index += 1
    return bindings


def test_appendix_a_binding_population_is_derived_from_authoritative_tables(
    schema: dict[str, Any],
) -> None:
    policy = schema["x-pitchlog"]["appendixABindingPopulation"]
    assert policy["authority"] == "要件書 付録A 表示書式列"
    assert "bindingCount" not in policy
    assert policy["splitCompositeRows"] is False
    assert "分解しない" in policy["compositeRowPolicy"]

    document = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    by_section = {
        section: _format_bindings_in_section(document, section) for section in policy["sections"]
    }
    assert {section: len(rows) for section, rows in by_section.items()} == {
        "A-2": 12,
        "A-2b": 4,
        "A-3": 7,
        "A-4": 1,
        "A-5": 8,
    }

    derived_bindings = [row for rows in by_section.values() for row in rows]
    assert set(policy["compositeRows"]) == {
        "最速・平均球速",
        "勝 / 敗 / 分",
        "得点 / 失点",
        "イニング別得点・失点",
    }
    assert set(policy["compositeRows"]).issubset(derived_bindings)
    assert len(derived_bindings) == 32


def test_authority_references_use_clause_ids(schema: dict[str, Any]) -> None:
    references = schema["x-pitchlog"]["authorities"]
    assert references == [
        "ADR-003 D-1 正本の射程行",
        "ADR-003 D-1 生成前検査行",
        "要件書 付録A-1 表示書式の共通規定",
    ]
    assert all(re.search(r":\d+", reference) is None for reference in references)
