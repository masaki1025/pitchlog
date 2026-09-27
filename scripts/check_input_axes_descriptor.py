"""入力軸descriptorのschema適合性と内容digestを検証する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from scripts import state_transition_freeze as freeze_checker
except ModuleNotFoundError:  # pragma: no cover - scriptを直接実行する経路
    import state_transition_freeze as freeze_checker  # type: ignore[no-redef]

DESCRIPTOR_PATH = PurePosixPath(
    "contracts/state-transition/input_axes_descriptor_v1.json"
)
SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/input_axes_descriptor_schema_v1.json"
)
SOURCE_CLAUSE_PATHS = (
    PurePosixPath("docs/requirements/requirements-pitchlog-2026-07-22.md"),
    PurePosixPath("docs/adr/ADR-003-domain-calc-method.md"),
)
SOURCE_CLAUSE_NAMESPACES = {
    SOURCE_CLAUSE_PATHS[0]: "req",
    SOURCE_CLAUSE_PATHS[1]: "adr",
}
CLAUSE_HEADING_PATTERN = re.compile(
    r"^#{2,6}\s+(?P<clause_id>(?:FR|NFR)-\d+|\d+\.\d+-\d+|[A-Z]-\d+[a-z]?)(?=[:\s])"
)
APPENDIX_HEADING_PATTERN = re.compile(r"^##\s+付録(?P<letter>[A-Z]):")
APPENDIX_ITEM_PATTERN = re.compile(r"^(?P<number>\d+)\.\s+")
STABLE_TABLE_CLAUSE_PATTERN = re.compile(
    r"^\s*\|\s*`(?P<clause_id>"
    r"(?:COLD|DRAW|XMARK|OUT3|ADV|INT|SO|RBI|XC)-\d+)`\s*\|"
)


class DescriptorCheckError(Exception):
    """descriptorを検証できない場合を表す。"""


@dataclass(frozen=True)
class DescriptorCriteria:
    """資産側宣言から読み込んだdescriptor検査の凍結基準。"""

    top_level_fields: frozenset[str]
    safe_integer_limit: int
    forbidden_stage1_reference_keys: frozenset[str]
    game_end_axis_fields: Mapping[str, str]
    f1_rule_fields: frozenset[str]
    non_coverage_fields: frozenset[str]
    exact_structured_axis_ids: frozenset[str]
    deferred_structured_axis_kinds: Mapping[str, str]
    deferred_structured_axis_dimensions: Mapping[str, tuple[str, ...]]
    deferred_structured_axis_variants: Mapping[str, frozenset[str]]
    stage2_constraint_classes: frozenset[str]
    stage2_required_artifacts: frozenset[str]
    fr040_conditional_values: Mapping[str, frozenset[str]]
    required_game_end_boundary_values: Mapping[
        str, tuple[frozenset[str], frozenset[str]]
    ]
    forbidden_game_end_invalid_boundary_values: Mapping[str, frozenset[str]]
    ambiguous_source_bindings: Mapping[str, str]
    checker_expected_values: Mapping[str, Any]


def _string_set(value: object, label: str) -> frozenset[str]:
    """重複のない空でない文字列配列を集合へ変換する。"""
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise DescriptorCheckError(f"凍結基準{label}が空でない文字列配列でない")
    result = frozenset(value)
    if len(result) != len(value):
        raise DescriptorCheckError(f"凍結基準{label}に重複がある")
    return result


def _string_map(value: object, label: str) -> dict[str, str]:
    """空でない文字列どうしの対応表を返す。"""
    if not isinstance(value, dict) or not value or not all(
        isinstance(key, str)
        and key
        and isinstance(item, str)
        and item
        for key, item in value.items()
    ):
        raise DescriptorCheckError(f"凍結基準{label}が文字列対応表でない")
    return dict(value)


def _string_set_map(value: object, label: str) -> dict[str, frozenset[str]]:
    """文字列キーから重複のない文字列集合への対応表を返す。"""
    if not isinstance(value, dict) or not value:
        raise DescriptorCheckError(f"凍結基準{label}がobjectでない")
    result: dict[str, frozenset[str]] = {}
    for key, items in value.items():
        if not isinstance(key, str) or not key:
            raise DescriptorCheckError(f"凍結基準{label}のキーが不正")
        result[key] = _string_set(items, f"{label}.{key}")
    return result


def load_descriptor_criteria(descriptor: Mapping[str, Any]) -> DescriptorCriteria:
    """descriptor内の資産側宣言を検証して型付き基準へ変換する。"""
    try:
        declaration = freeze_checker.validate_declaration(
            descriptor.get(freeze_checker.FREEZE_FIELD)
        )
        raw = freeze_checker.checker_criteria(declaration, __file__)
    except freeze_checker.FreezeBaselineError as error:
        raise DescriptorCheckError(f"凍結基準宣言を検証できない: {error}") from error

    dimensions_value = raw.get("deferredStructuredAxisDimensions")
    variants_value = raw.get("deferredStructuredAxisVariants")
    if not isinstance(dimensions_value, dict) or not isinstance(variants_value, dict):
        raise DescriptorCheckError("構造化入力軸の凍結基準がobjectでない")
    # 順序も意味を持つ dimensions は元配列順で保持する。
    dimensions = {
        axis_id: tuple(values)
        for axis_id, values in dimensions_value.items()
        if isinstance(axis_id, str)
        and isinstance(values, list)
        and values
        and all(isinstance(item, str) and item for item in values)
    }
    if set(dimensions) != set(dimensions_value):
        raise DescriptorCheckError("deferredStructuredAxisDimensionsの型が不正")
    variants = {
        axis_id: _string_set(values, f".deferredStructuredAxisVariants.{axis_id}")
        for axis_id, values in variants_value.items()
        if isinstance(axis_id, str)
    }
    if set(variants) != set(variants_value):
        raise DescriptorCheckError("deferredStructuredAxisVariantsの型が不正")
    boundary_value = raw.get("requiredGameEndBoundaryValues")
    if not isinstance(boundary_value, dict) or not boundary_value:
        raise DescriptorCheckError("requiredGameEndBoundaryValuesがobjectでない")
    required_boundaries: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for axis_id, partitions in boundary_value.items():
        if (
            not isinstance(axis_id, str)
            or not isinstance(partitions, dict)
            or set(partitions) != {"valid", "invalid"}
        ):
            raise DescriptorCheckError("requiredGameEndBoundaryValuesの型が不正")
        required_boundaries[axis_id] = (
            _string_set(partitions["valid"], f".requiredGameEndBoundaryValues.{axis_id}.valid"),
            _string_set(
                partitions["invalid"],
                f".requiredGameEndBoundaryValues.{axis_id}.invalid",
            ),
        )
    limit = raw.get("safeIntegerLimit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise DescriptorCheckError("safeIntegerLimitが正の整数でない")
    checker_expected_values = raw.get("checkerExpectedValues")
    if not isinstance(checker_expected_values, dict) or not checker_expected_values:
        raise DescriptorCheckError("checkerExpectedValuesが空でないobjectでない")
    return DescriptorCriteria(
        top_level_fields=_string_set(raw.get("topLevelFields"), ".topLevelFields"),
        safe_integer_limit=limit,
        forbidden_stage1_reference_keys=_string_set(
            raw.get("forbiddenStage1ReferenceKeys"),
            ".forbiddenStage1ReferenceKeys",
        ),
        game_end_axis_fields=_string_map(
            raw.get("gameEndAxisFields"), ".gameEndAxisFields"
        ),
        f1_rule_fields=_string_set(raw.get("f1RuleFields"), ".f1RuleFields"),
        non_coverage_fields=_string_set(
            raw.get("nonCoverageFields"), ".nonCoverageFields"
        ),
        exact_structured_axis_ids=_string_set(
            raw.get("exactStructuredAxisIds"), ".exactStructuredAxisIds"
        ),
        deferred_structured_axis_kinds=_string_map(
            raw.get("deferredStructuredAxisKinds"),
            ".deferredStructuredAxisKinds",
        ),
        deferred_structured_axis_dimensions=dimensions,
        deferred_structured_axis_variants=variants,
        stage2_constraint_classes=_string_set(
            raw.get("stage2ConstraintClasses"), ".stage2ConstraintClasses"
        ),
        stage2_required_artifacts=_string_set(
            raw.get("stage2RequiredArtifacts"), ".stage2RequiredArtifacts"
        ),
        fr040_conditional_values=_string_set_map(
            raw.get("fr040ConditionalValues"), ".fr040ConditionalValues"
        ),
        required_game_end_boundary_values=required_boundaries,
        forbidden_game_end_invalid_boundary_values=_string_set_map(
            raw.get("forbiddenGameEndInvalidBoundaryValues"),
            ".forbiddenGameEndInvalidBoundaryValues",
        ),
        ambiguous_source_bindings=_string_map(
            raw.get("ambiguousSourceBindings"), ".ambiguousSourceBindings"
        ),
        checker_expected_values=checker_expected_values,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSON objectの重複キーを拒否して辞書を返す。"""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DescriptorCheckError(f"JSON objectに重複キーがある: {key}")
        result[key] = value
    return result


def load_json(path: Path, label: str) -> object:
    """UTF-8 JSONを重複キー拒否付きで読む。

    Args:
        path: 読み込むJSONファイル。
        label: エラーへ表示する資産名。

    Returns:
        読み込んだJSON値。

    Raises:
        DescriptorCheckError: ファイルまたはJSONが不正な場合。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise DescriptorCheckError(f"{label}をUTF-8で読めない: {path}: {error}") from error
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise DescriptorCheckError(f"{label}がJSONでない: {path}: {error}") from error


def load_clause_ids_from_paths(
    root: Path, source_clause_paths: Sequence[PurePosixPath]
) -> frozenset[str]:
    """指定した正本の構造から実在する条文IDを抽出する。

    Args:
        root: リポジトリルート。
        source_clause_paths: 条文IDを抽出する正本のリポジトリ相対パス。

    Returns:
        見出しIDと付録の番号付き項目IDの集合。

    Raises:
        DescriptorCheckError: 正本を読めない場合、またはIDを抽出できない場合。
    """
    clause_ids: set[str] = set()
    for relative_path in source_clause_paths:
        path = root / relative_path
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise DescriptorCheckError(
                f"由来条文の正本をUTF-8で読めない: {path}: {error}"
            ) from error

        appendix_letter: str | None = None
        for line in lines:
            heading = CLAUSE_HEADING_PATTERN.match(line)
            if heading is not None:
                clause_ids.add(heading.group("clause_id"))
            stable_table_clause = STABLE_TABLE_CLAUSE_PATTERN.match(line)
            if stable_table_clause is not None:
                clause_ids.add(stable_table_clause.group("clause_id"))

            appendix_heading = APPENDIX_HEADING_PATTERN.match(line)
            if appendix_heading is not None:
                appendix_letter = appendix_heading.group("letter")
                continue
            if line.startswith("## "):
                appendix_letter = None
                continue
            if appendix_letter is None:
                continue
            appendix_item = APPENDIX_ITEM_PATTERN.match(line)
            if appendix_item is not None:
                clause_ids.add(
                    f"{appendix_letter}-{int(appendix_item.group('number'))}"
                )

    if not clause_ids:
        raise DescriptorCheckError("由来条文IDを正本から抽出できない")
    return frozenset(clause_ids)


def load_source_clause_ids(root: Path) -> frozenset[str]:
    """要件書とADRから名前空間付きの実在条文IDを抽出する。"""
    namespaced: set[str] = set()
    for path in SOURCE_CLAUSE_PATHS:
        namespace = SOURCE_CLAUSE_NAMESPACES[path]
        namespaced.update(
            f"{namespace}:{clause_id}"
            for clause_id in load_clause_ids_from_paths(root, (path,))
        )
    return frozenset(namespaced)


def _expect_object(value: object, label: str) -> dict[str, Any]:
    """JSON値をobjectとして返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DescriptorCheckError(f"{label}は文字列キーのobjectでなければならない")
    return value


def _expected_object(criteria: DescriptorCriteria, key: str) -> dict[str, Any]:
    """検査器期待値宣言からobjectを取得する。"""
    return _expect_object(
        criteria.checker_expected_values.get(key),
        f"checkerExpectedValues.{key}",
    )


def _expected_string(criteria: DescriptorCriteria, key: str) -> str:
    """検査器期待値宣言から空でない文字列を取得する。"""
    value = criteria.checker_expected_values.get(key)
    if not isinstance(value, str) or not value:
        raise DescriptorCheckError(
            f"checkerExpectedValues.{key}は空でない文字列でなければならない"
        )
    return value


def _expected_positive_integer(criteria: DescriptorCriteria, key: str) -> int:
    """検査器期待値宣言から正の整数を取得する。"""
    value = criteria.checker_expected_values.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DescriptorCheckError(
            f"checkerExpectedValues.{key}は正の整数でなければならない"
        )
    return value


def _json_equal(left: object, right: object) -> bool:
    """booleanとintegerを混同せずJSON値を比較する。"""
    return type(left) is type(right) and left == right


def _json_type_matches(value: object, type_name: str) -> bool:
    """Python値が指定されたJSON型に一致するか返す。"""
    type_table = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    predicate = type_table.get(type_name)
    if predicate is None:
        raise DescriptorCheckError(f"未対応のJSON Schema type: {type_name}")
    return bool(predicate(value))


def _decode_json_pointer_token(token: str) -> str:
    """JSON Pointerの1 tokenを復号する。"""
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_schema_reference(root_schema: Mapping[str, Any], reference: str) -> dict[str, Any]:
    """同一schema内のJSON Pointer参照を解決する。"""
    if not reference.startswith("#/"):
        raise DescriptorCheckError(f"外部JSON Schema参照は使えない: {reference}")
    current: object = root_schema
    for raw_token in reference.removeprefix("#/").split("/"):
        token = _decode_json_pointer_token(raw_token)
        if not isinstance(current, dict) or token not in current:
            raise DescriptorCheckError(f"JSON Schema参照を解決できない: {reference}")
        current = current[token]
    return _expect_object(current, f"JSON Schema参照先({reference})")


def _canonical_json_text(
    value: object, safe_integer_limit: int | None = None
) -> str:
    """descriptorで許可するJSON値をRFC 8785形式へ正規化する。"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if safe_integer_limit is not None and abs(value) > safe_integer_limit:
            raise DescriptorCheckError(
                f"RFC 8785のI-JSON安全整数範囲を超えている: {value}"
            )
        return str(value)
    if isinstance(value, float):
        raise DescriptorCheckError("descriptorでは浮動小数点数を使用できない")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise DescriptorCheckError("文字列に不正なUnicode surrogateがある") from error
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(
            _canonical_json_text(item, safe_integer_limit) for item in value
        ) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise DescriptorCheckError("JSON objectのキーは文字列でなければならない")
        try:
            keys = sorted(value, key=lambda key: key.encode("utf-16be"))
        except UnicodeEncodeError as error:
            raise DescriptorCheckError("objectキーに不正なUnicode surrogateがある") from error
        members = (
            f"{_canonical_json_text(key, safe_integer_limit)}:"
            f"{_canonical_json_text(value[key], safe_integer_limit)}"
            for key in keys
        )
        return "{" + ",".join(members) + "}"
    raise DescriptorCheckError(f"JSON値として扱えない型がある: {type(value).__name__}")


def canonicalize_json(
    value: object, safe_integer_limit: int | None = None
) -> bytes:
    """JSON値をRFC 8785準拠のUTF-8バイト列へ正規化する。

    descriptor schemaは浮動小数点数を許さず、整数をI-JSON安全範囲へ閉じる。
    そのため数値表現の実装依存を持たず、標準ライブラリだけで再現できる。

    Args:
        value: 正規化するJSON値。
        safe_integer_limit: 整数の絶対値上限。省略時は上限検査を行わない。

    Returns:
        正規化済みUTF-8バイト列。
    """
    return _canonical_json_text(value, safe_integer_limit).encode("utf-8")


def compute_descriptor_digest(descriptor: Mapping[str, Any]) -> str:
    """`digest`を除いたdescriptor全体のSHA-256を返す。

    Args:
        descriptor: digestを計算するdescriptor。

    Returns:
        `sha256:`接頭辞付きの小文字16進digest。

    Raises:
        DescriptorCheckError: `digest`が欠落している場合。
    """
    if "digest" not in descriptor:
        raise DescriptorCheckError("descriptorにdigestがない")
    criteria = load_descriptor_criteria(descriptor)
    digest_input = {key: value for key, value in descriptor.items() if key != "digest"}
    digest = hashlib.sha256(
        canonicalize_json(digest_input, criteria.safe_integer_limit)
    ).hexdigest()
    return f"sha256:{digest}"


def _validate_instance(
    value: object,
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    path: str,
) -> None:
    """本descriptor schemaが使うJSON Schemaキーワードを検証する。"""
    reference = schema.get("$ref")
    if isinstance(reference, str):
        referenced = _resolve_schema_reference(root_schema, reference)
        _validate_instance(value, referenced, root_schema, path)

    variants = schema.get("oneOf")
    if isinstance(variants, list):
        matched = 0
        for variant in variants:
            if not isinstance(variant, dict):
                raise DescriptorCheckError(f"JSON SchemaのoneOfが不正: {path}")
            try:
                _validate_instance(value, variant, root_schema, path)
            except DescriptorCheckError:
                continue
            matched += 1
        if matched != 1:
            raise DescriptorCheckError(f"schema: {path}: oneOfに一意に一致しない")
        return

    if "const" in schema and not _json_equal(value, schema["const"]):
        raise DescriptorCheckError(
            f"schema: {path}: const不一致: 期待={schema['const']!r}; 実際={value!r}"
        )
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and not any(
        _json_equal(value, candidate) for candidate in enum_values
    ):
        raise DescriptorCheckError(f"schema: {path}: enum外の値: {value!r}")

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _json_type_matches(value, expected_type):
        raise DescriptorCheckError(
            f"schema: {path}: 型不一致: 期待={expected_type}; 実際={type(value).__name__}"
        )

    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(
            isinstance(item, str) for item in required
        ):
            raise DescriptorCheckError(f"JSON Schemaのrequiredが不正: {path}")
        missing = sorted(set(required) - set(value))
        if missing:
            raise DescriptorCheckError(f"schema: {path}: 必須キー不足: {missing!r}")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise DescriptorCheckError(f"JSON Schemaのpropertiesが不正: {path}")
        unknown = sorted(set(value) - set(properties))
        if schema.get("additionalProperties", True) is False and unknown:
            raise DescriptorCheckError(f"schema: {path}: 未知キー: {unknown!r}")
        for key, child in value.items():
            child_schema = properties.get(key)
            if child_schema is None:
                continue
            if not isinstance(child_schema, dict):
                raise DescriptorCheckError(
                    f"JSON Schemaのproperty定義が不正: {path}.{key}"
                )
            _validate_instance(child, child_schema, root_schema, f"{path}.{key}")

    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise DescriptorCheckError(
                f"schema: {path}: 配列要素数が下限未満: {len(value)} < {minimum}"
            )
        if isinstance(maximum, int) and len(value) > maximum:
            raise DescriptorCheckError(
                f"schema: {path}: 配列要素数が上限超過: {len(value)} > {maximum}"
            )
        if schema.get("uniqueItems") is True:
            canonical_items = [canonicalize_json(item) for item in value]
            if len(canonical_items) != len(set(canonical_items)):
                raise DescriptorCheckError(f"schema: {path}: 配列要素が重複している")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_instance(item, item_schema, root_schema, f"{path}[{index}]")

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            raise DescriptorCheckError(f"schema: {path}: 文字列が短すぎる")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise DescriptorCheckError(f"schema: {path}: pattern不一致: {value!r}")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int) and value < minimum:
            raise DescriptorCheckError(
                f"schema: {path}: 整数が下限未満: {value} < {minimum}"
            )
        if isinstance(maximum, int) and value > maximum:
            raise DescriptorCheckError(
                f"schema: {path}: 整数が上限超過: {value} > {maximum}"
            )


def _validate_schema_contract(
    schema: Mapping[str, Any], criteria: DescriptorCriteria
) -> None:
    """schema自身がdescriptorの必須構造を閉じていることを検証する。"""
    if schema.get("$schema") != _expected_string(criteria, "jsonSchemaDialect"):
        raise DescriptorCheckError("schemaのdialectはJSON Schema 2020-12でなければならない")
    if schema.get("version") != SCHEMA_PATH.stem:
        raise DescriptorCheckError("schemaのファイル名と内部versionが一致しない")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise DescriptorCheckError("schemaのトップレベルobjectが閉じていない")
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or frozenset(required) != criteria.top_level_fields:
        raise DescriptorCheckError("schemaのトップレベルrequiredがexact-set不一致")
    if (
        not isinstance(properties, dict)
        or frozenset(properties) != criteria.top_level_fields
    ):
        raise DescriptorCheckError("schemaのトップレベルpropertiesがexact-set不一致")
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        raise DescriptorCheckError("schemaに$defsがない")
    required_definitions = {
        "axis",
        "axisClassification",
        "finiteEnumerableAxis",
        "boundaryPartitionAxis",
        "nonFiniteAxis",
        "nonCoverageField",
        "projectionRule",
        "digestSpec",
        "freezeBaseline",
        "stage2ExternalConstraints",
        "supportingClauseIds",
        "ruleFieldId",
        "coverageBound",
        "conditionalValues",
        "valueSchema",
        "representationCapability",
        "gameEndCombinationRules",
    }
    if not required_definitions <= set(definitions):
        missing = sorted(required_definitions - set(definitions))
        raise DescriptorCheckError(f"schemaの必須$defsが不足している: {missing!r}")


def _walk_for_stage1_external_references(
    value: object,
    forbidden_keys: frozenset[str],
    path: str = "$",
) -> None:
    """段階1で禁止した外部参照キーがdescriptorに無いことを検証する。"""
    if isinstance(value, dict):
        forbidden = sorted(forbidden_keys & set(value))
        if forbidden:
            raise DescriptorCheckError(f"段階1の外部参照キーがある: {path}: {forbidden!r}")
        for key, child in value.items():
            _walk_for_stage1_external_references(
                child, forbidden_keys, f"{path}.{key}"
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_for_stage1_external_references(
                child, forbidden_keys, f"{path}[{index}]"
            )


def _validate_source_clause_ids(
    descriptor: Mapping[str, Any],
    source_clause_ids: frozenset[str],
    criteria: DescriptorCriteria,
) -> None:
    """全入力軸の一次・補助典拠が正本に実在することを検証する。"""
    for collection_name in ("stateTransitionAxes", "gameEndAxes"):
        axes = descriptor.get(collection_name)
        if not isinstance(axes, list):
            continue
        for index, axis_value in enumerate(axes):
            if not isinstance(axis_value, dict):
                continue
            cited_ids: list[object] = [axis_value.get("sourceClauseId")]
            supporting = axis_value.get("supportingClauseIds", [])
            if isinstance(supporting, list):
                cited_ids.extend(supporting)
            conditional_values = axis_value.get("conditionalValues", [])
            if isinstance(conditional_values, list):
                cited_ids.extend(
                    item.get("whenClauseId")
                    for item in conditional_values
                    if isinstance(item, dict)
                )
            for clause_id in cited_ids:
                if isinstance(clause_id, str) and clause_id not in source_clause_ids:
                    raise DescriptorCheckError(
                        "由来条文IDが正本に実在しない: "
                        f"{collection_name}[{index}]: {clause_id}"
                    )
            axis_id = axis_value.get("axisId")
            expected_source = criteria.ambiguous_source_bindings.get(axis_id)
            if expected_source is not None and axis_value.get("sourceClauseId") != expected_source:
                raise DescriptorCheckError(
                    "同名条文IDの名前空間が誤っている: "
                    f"{axis_id}: expected={expected_source}; "
                    f"actual={axis_value.get('sourceClauseId')}"
                )

    non_coverage_fields = descriptor.get("nonCoverageFields")
    if isinstance(non_coverage_fields, list):
        for index, field_value in enumerate(non_coverage_fields):
            if not isinstance(field_value, dict):
                continue
            cited_ids: list[object] = [field_value.get("sourceClauseId")]
            supporting = field_value.get("supportingClauseIds", [])
            if isinstance(supporting, list):
                cited_ids.extend(supporting)
            for clause_id in cited_ids:
                if isinstance(clause_id, str) and clause_id not in source_clause_ids:
                    raise DescriptorCheckError(
                        "由来条文IDが正本に実在しない: "
                        f"nonCoverageFields[{index}]: {clause_id}"
                    )

    combination_rules = descriptor.get("gameEndCombinationRules")
    if isinstance(combination_rules, dict):
        clause_id = combination_rules.get("sourceClauseId")
        if isinstance(clause_id, str) and clause_id not in source_clause_ids:
            raise DescriptorCheckError(
                "由来条文IDが正本に実在しない: "
                f"gameEndCombinationRules: {clause_id}"
            )

    stage2_constraints = descriptor.get("stage2ExternalConstraints")
    if isinstance(stage2_constraints, dict):
        clause_id = stage2_constraints.get("sourceClauseId")
        if isinstance(clause_id, str) and clause_id not in source_clause_ids:
            raise DescriptorCheckError(
                "由来条文IDが正本に実在しない: "
                f"stage2ExternalConstraints: {clause_id}"
            )

    projection_rules = descriptor.get("projectionRules")
    if isinstance(projection_rules, list):
        for index, rule_value in enumerate(projection_rules):
            if not isinstance(rule_value, dict):
                continue
            clause_id = rule_value.get("sourceClauseId")
            if isinstance(clause_id, str) and clause_id not in source_clause_ids:
                raise DescriptorCheckError(
                    "由来条文IDが正本に実在しない: "
                    f"projectionRules[{index}]: {clause_id}"
                )


def _walk_embedded_value_schema(value: object, path: str) -> None:
    """構造化入力の内包JSON Schemaが閉じていることを再帰検証する。"""
    if isinstance(value, dict):
        if "$ref" in value:
            raise DescriptorCheckError(f"valueSchemaは参照を持てない: {path}")
        if value.get("type") == "object" and value.get("additionalProperties") is not False:
            raise DescriptorCheckError(
                f"valueSchemaのobjectはadditionalProperties:falseが必須: {path}"
            )
        unique_by = value.get("x-pitchlog-uniqueBy")
        if unique_by is not None:
            items = value.get("items")
            variants = items.get("oneOf") if isinstance(items, dict) else None
            if not isinstance(unique_by, str) or not isinstance(variants, list):
                raise DescriptorCheckError(
                    f"valueSchemaのuniqueByを検証できない: {path}"
                )
            if any(
                not isinstance(variant, dict)
                or unique_by not in variant.get("required", [])
                for variant in variants
            ):
                raise DescriptorCheckError(
                    f"valueSchemaのuniqueByが全variantの必須キーでない: {path}"
                )
        for key, child in value.items():
            _walk_embedded_value_schema(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_embedded_value_schema(child, f"{path}[{index}]")


def _validate_structured_input_axes(
    descriptor: Mapping[str, Any], criteria: DescriptorCriteria
) -> None:
    """段階1で閉じる構造と段階2へ委任する表現能力を区別して検証する。"""
    axes = descriptor.get("stateTransitionAxes")
    if not isinstance(axes, list):
        return
    structured_axes = {
        axis.get("axisId"): axis
        for axis in axes
        if isinstance(axis, dict) and "valueSchema" in axis
    }
    if frozenset(structured_axes) != criteria.exact_structured_axis_ids:
        raise DescriptorCheckError(
            "段階1で閉じる構造化入力軸がexact-set不一致: "
            f"expected={sorted(criteria.exact_structured_axis_ids)!r}; "
            f"actual={sorted(structured_axes)!r}"
        )
    for axis_id, axis in structured_axes.items():
        value_schema = axis.get("valueSchema")
        if not isinstance(value_schema, dict):
            raise DescriptorCheckError(f"valueSchemaがobjectでない: {axis_id}")
        if value_schema.get("$schema") != _expected_string(
            criteria, "jsonSchemaDialect"
        ):
            raise DescriptorCheckError(
                f"valueSchemaのdialectがDraft 2020-12でない: {axis_id}"
            )
        _walk_embedded_value_schema(value_schema, f"{axis_id}.valueSchema")

    deferred_axes = {
        axis.get("axisId"): axis
        for axis in axes
        if isinstance(axis, dict) and "representationCapability" in axis
    }
    expected_deferred_ids = frozenset(criteria.deferred_structured_axis_kinds)
    if frozenset(deferred_axes) != expected_deferred_ids:
        raise DescriptorCheckError(
            "段階2へ委任する構造化入力軸がexact-set不一致: "
            f"expected={sorted(expected_deferred_ids)!r}; "
            f"actual={sorted(deferred_axes)!r}"
        )
    for axis_id, axis in deferred_axes.items():
        if "valueSchema" in axis:
            raise DescriptorCheckError(
                f"段階2へ委任したpayload内部制約をvalueSchemaで保証してはならない: {axis_id}"
            )
        capability = axis.get("representationCapability")
        if not isinstance(capability, dict):
            raise DescriptorCheckError(f"表現能力宣言がobjectでない: {axis_id}")
        expected_kind = criteria.deferred_structured_axis_kinds[axis_id]
        if capability.get("kind") != expected_kind:
            raise DescriptorCheckError(
                f"表現能力のkindが一致しない: {axis_id}: expected={expected_kind}"
            )
        dimensions = capability.get("dimensions")
        if dimensions != list(criteria.deferred_structured_axis_dimensions[axis_id]):
            raise DescriptorCheckError(
                f"表現能力のdimensionsがexact-set不一致: {axis_id}"
            )
        variant_tags = capability.get("variantTags")
        if not isinstance(variant_tags, list) or frozenset(variant_tags) != (
            criteria.deferred_structured_axis_variants[axis_id]
        ):
            raise DescriptorCheckError(
                f"表現能力のvariantTagsがexact-set不一致: {axis_id}"
            )


def _validate_stage2_external_constraints(
    descriptor: Mapping[str, Any], criteria: DescriptorCriteria
) -> None:
    """payload内部制約と状態遷移の軸間規則の段階2委任を検証する。"""
    declaration = descriptor.get("stage2ExternalConstraints")
    if not isinstance(declaration, dict):
        raise DescriptorCheckError("stage2ExternalConstraintsがobjectでない")
    if (
        frozenset(declaration.get("payloadAxisIds", []))
        != frozenset(criteria.deferred_structured_axis_kinds)
    ):
        raise DescriptorCheckError("段階2へ委任した入力軸がexact-set不一致")
    if (
        frozenset(declaration.get("constraintClasses", []))
        != criteria.stage2_constraint_classes
    ):
        raise DescriptorCheckError("段階2へ委任した制約種別がexact-set不一致")
    if (
        frozenset(declaration.get("requiredArtifacts", []))
        != criteria.stage2_required_artifacts
    ):
        raise DescriptorCheckError("段階2で必須の成果物がexact-set不一致")


def _validate_fr040_conditionals(
    descriptor: Mapping[str, Any], criteria: DescriptorCriteria
) -> None:
    """FR-040採用時だけ加わる値を操作・payload・履歴で同じ条件に揃える。"""
    axes = descriptor.get("stateTransitionAxes")
    if not isinstance(axes, list):
        return
    axes_by_id = {
        axis.get("axisId"): axis for axis in axes if isinstance(axis, dict)
    }
    expected = criteria.fr040_conditional_values
    entry_expectation = _expected_object(criteria, "fr040ConditionalEntry")
    conditional_axis_ids = {
        axis_id
        for axis_id, axis in axes_by_id.items()
        if isinstance(axis_id, str) and axis.get("conditionalValues")
    }
    if conditional_axis_ids != set(expected):
        raise DescriptorCheckError("FR-040条件付き軸がexact-set不一致")
    for axis_id, expected_values in expected.items():
        axis = axes_by_id.get(axis_id)
        if not isinstance(axis, dict):
            raise DescriptorCheckError(f"FR-040条件付き軸がない: {axis_id}")
        entries = axis.get("conditionalValues")
        if not isinstance(entries, list):
            raise DescriptorCheckError(f"conditionalValuesが配列でない: {axis_id}")
        actual_values = {entry.get("value") for entry in entries if isinstance(entry, dict)}
        if actual_values != expected_values or any(
            not isinstance(entry, dict)
            or any(entry.get(key) != value for key, value in entry_expectation.items())
            for entry in entries
        ):
            raise DescriptorCheckError(f"FR-040採用条件が一致しない: {axis_id}")
        declared_values = axis.get("values", axis.get("boundaryValues", []))
        if not isinstance(declared_values, list) or not actual_values <= set(declared_values):
            raise DescriptorCheckError(
                f"FR-040条件付き値が軸の値集合にない: {axis_id}"
            )
    operation_payload_axis_id = _expected_string(
        criteria, "operationPayloadAxisId"
    )
    operation_payload = axes_by_id.get(operation_payload_axis_id)
    capability = (
        operation_payload.get("representationCapability")
        if isinstance(operation_payload, dict)
        else None
    )
    variant_tags = capability.get("variantTags") if isinstance(capability, dict) else None
    if not isinstance(variant_tags, list) or (
        frozenset(variant_tags)
        != criteria.deferred_structured_axis_variants[operation_payload_axis_id]
    ):
        raise DescriptorCheckError(
            "状態補正payload variantを含む操作payloadのタグ集合が構造上exact-set不一致"
        )


def coverage_obligation_count(
    axis: Mapping[str, Any], criteria: DescriptorCriteria
) -> int:
    """軸から展開すべきcoverage座標の件数を返す。

    `non-finite`は理由だけではcoverage座標を生まないため0件とする。無限領域は
    `boundary-partition`として境界値・等価分割を明示してから登録しなければならない。
    """
    classification = axis.get("classification")
    value_fields = _expected_object(
        criteria, "coverageValueFieldsByClassification"
    ).get(classification)
    if not isinstance(value_fields, list) or not all(
        isinstance(item, str) and item for item in value_fields
    ):
        return 0
    return sum(
        len(values)
        for field in value_fields
        if isinstance((values := axis.get(field, [])), list)
    )


def _validate_coverage_obligations(
    descriptor: Mapping[str, Any], criteria: DescriptorCriteria
) -> None:
    """全入力軸が1件以上のcoverage義務を生成することを検証する。"""
    minimum_obligations = _expected_positive_integer(
        criteria, "minimumCoverageObligationsPerAxis"
    )
    for collection_name in ("stateTransitionAxes", "gameEndAxes"):
        axes = descriptor.get(collection_name)
        if not isinstance(axes, list):
            continue
        for index, axis_value in enumerate(axes):
            if not isinstance(axis_value, dict):
                continue
            if coverage_obligation_count(axis_value, criteria) < minimum_obligations:
                axis_id = axis_value.get("axisId", f"index={index}")
                raise DescriptorCheckError(
                    "coverage義務が宣言した最小件数未満の入力軸がある: "
                    f"{collection_name}: {axis_id}"
                )


def _validate_game_end_contract(
    descriptor: Mapping[str, Any], criteria: DescriptorCriteria
) -> None:
    """F-1の終了判定軸・非coverage項目・組合せ規則を検証する。"""
    game_end_axes = descriptor.get("gameEndAxes")
    if not isinstance(game_end_axes, list):
        return
    axis_fields = {
        axis.get("axisId"): axis.get("ruleFieldId")
        for axis in game_end_axes
        if isinstance(axis, dict)
    }
    if axis_fields != criteria.game_end_axis_fields:
        raise DescriptorCheckError(
            "gameEndAxesの4軸またはF-1フィールド帰属がexact-set不一致"
        )
    required_supporting_clause = _expected_string(
        criteria, "gameEndAxisSupportingClauseId"
    )
    required_classification = _expected_string(
        criteria, "gameEndAxisClassification"
    )
    for axis in game_end_axes:
        if not isinstance(axis, dict):
            continue
        supporting_clause_ids = axis.get("supportingClauseIds", [])
        if (
            not isinstance(supporting_clause_ids, list)
            or required_supporting_clause not in supporting_clause_ids
        ):
            raise DescriptorCheckError(
                f"gameEndAxesの安全範囲にadr:D-11の典拠がない: {axis.get('axisId')}"
            )
        if axis.get("classification") != required_classification:
            raise DescriptorCheckError("gameEndAxesは境界値・等価分割で閉じなければならない")
        bounds = axis.get("coverageBounds")
        if not isinstance(bounds, list) or not bounds:
            raise DescriptorCheckError(
                f"gameEndAxesの安全範囲がない: {axis.get('axisId')}"
            )
        dimensions = {
            bound.get("dimension") for bound in bounds if isinstance(bound, dict)
        }
        if len(dimensions) != len(bounds):
            raise DescriptorCheckError(
                f"gameEndAxesの安全範囲dimensionが重複している: {axis.get('axisId')}"
            )
        for bound in bounds:
            if not isinstance(bound, dict):
                continue
            minimum = bound.get("minimum")
            maximum = bound.get("maximum")
            if (
                isinstance(minimum, int)
                and not isinstance(minimum, bool)
                and isinstance(maximum, int)
                and not isinstance(maximum, bool)
                and minimum > maximum
            ):
                raise DescriptorCheckError(
                    f"gameEndAxesの安全範囲が逆転している: {axis.get('axisId')}"
                )
        valid_boundaries = axis.get("boundaryValues")
        invalid_boundaries = axis.get("invalidBoundaryValues")
        if isinstance(valid_boundaries, list) and isinstance(invalid_boundaries, list):
            valid_canonical = {canonicalize_json(value) for value in valid_boundaries}
            invalid_canonical = {
                canonicalize_json(value) for value in invalid_boundaries
            }
            if valid_canonical & invalid_canonical:
                raise DescriptorCheckError(
                    f"gameEndAxesの有効・不正境界が重複している: {axis.get('axisId')}"
                )

    non_coverage_fields = descriptor.get("nonCoverageFields")
    if not isinstance(non_coverage_fields, list):
        return
    non_coverage_ids = {
        field.get("fieldId")
        for field in non_coverage_fields
        if isinstance(field, dict)
    }
    if non_coverage_ids != criteria.non_coverage_fields:
        raise DescriptorCheckError("nonCoverageFieldsの3件がexact-set不一致")
    schema_retention = _expected_string(criteria, "nonCoverageSchemaRetention")
    if any(
        field.get("schemaRetention") != schema_retention
        for field in non_coverage_fields
        if isinstance(field, dict)
    ):
        raise DescriptorCheckError("nonCoverageFieldsはschemaへの射影保持が必須")

    covered_top_level = set(axis_fields.values())
    non_covered_top_level = {
        field_id
        for field_id in non_coverage_ids
        if isinstance(field_id, str) and "." not in field_id
    }
    if covered_top_level & non_covered_top_level:
        raise DescriptorCheckError("F-1フィールドがcoverageと非coverageへ重複帰属している")
    if covered_top_level | non_covered_top_level != criteria.f1_rule_fields:
        raise DescriptorCheckError("F-1の5フィールドに未帰属または余分な帰属がある")

    combination_rules = descriptor.get("gameEndCombinationRules")
    if not isinstance(combination_rules, dict):
        return
    expected_combinations = _expected_object(criteria, "gameEndCombinationRules")
    mismatched_combinations = {
        key: {"expected": expected, "actual": combination_rules.get(key)}
        for key, expected in expected_combinations.items()
        if combination_rules.get(key) != expected
    }
    if mismatched_combinations:
        raise DescriptorCheckError(
            "終了判定の組合せ規則が凍結基準と一致しない: "
            f"{mismatched_combinations!r}"
        )

    axes_by_id = {
        axis.get("axisId"): axis
        for axis in game_end_axes
        if isinstance(axis, dict) and isinstance(axis.get("axisId"), str)
    }
    for axis_id, (required_valid, required_invalid) in (
        criteria.required_game_end_boundary_values.items()
    ):
        axis = axes_by_id.get(axis_id)
        if not isinstance(axis, dict):
            raise DescriptorCheckError(
                f"必須境界値を検査する終了判定軸がない: {axis_id}"
            )
        valid = set(axis.get("boundaryValues", []))
        invalid = set(axis.get("invalidBoundaryValues", []))
        if not required_valid <= valid or not required_invalid <= invalid:
            raise DescriptorCheckError(
                f"終了判定軸が条文由来の必須境界を覆っていない: {axis_id}"
            )
    for axis_id, forbidden_values in (
        criteria.forbidden_game_end_invalid_boundary_values.items()
    ):
        axis = axes_by_id.get(axis_id)
        if not isinstance(axis, dict):
            raise DescriptorCheckError(
                f"不正境界値を検査する終了判定軸がない: {axis_id}"
            )
        actual_invalid = set(axis.get("invalidBoundaryValues", []))
        forbidden = sorted(forbidden_values & actual_invalid)
        if forbidden:
            raise DescriptorCheckError(
                f"条文根拠のない不正境界値がある: {axis_id}: {forbidden!r}"
            )


def _validate_projection_contract(
    descriptor: Mapping[str, Any], criteria: DescriptorCriteria
) -> None:
    """全軸と非coverage項目を資産側の射影期待値で検証する。"""
    expected_targets: dict[str, str] = {}
    axes_by_id: dict[str, Mapping[str, Any]] = {}
    for collection_name in ("stateTransitionAxes", "gameEndAxes"):
        axes = descriptor.get(collection_name)
        if not isinstance(axes, list):
            continue
        for axis in axes:
            if not isinstance(axis, dict):
                continue
            axis_id = axis.get("axisId")
            classification = axis.get("classification")
            if isinstance(axis_id, str) and isinstance(classification, str):
                expected_targets[axis_id] = classification
                axes_by_id[axis_id] = axis

    non_coverage_kind = _expected_string(criteria, "nonCoverageTargetKind")
    non_coverage_fields = descriptor.get("nonCoverageFields")
    if isinstance(non_coverage_fields, list):
        for field in non_coverage_fields:
            if not isinstance(field, dict):
                continue
            field_id = field.get("fieldId")
            if isinstance(field_id, str):
                expected_targets[field_id] = non_coverage_kind

    rules = descriptor.get("projectionRules")
    if not isinstance(rules, list):
        return
    expectations = _expected_object(criteria, "projectionRules")
    actual_rules: dict[str, Mapping[str, Any]] = {}
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("ruleId"), str):
            continue
        rule_id = rule["ruleId"]
        if rule_id in actual_rules:
            raise DescriptorCheckError(f"射影判定不能: ruleIdが重複している: {rule_id}")
        actual_rules[rule_id] = rule
    if set(actual_rules) != set(expectations):
        raise DescriptorCheckError("射影判定不能: projection rule IDがexact-set不一致")

    projected_targets: dict[str, str] = {}
    conditional_requirements = _expected_object(
        criteria, "conditionalProjectionRequirements"
    )
    for rule_id, rule in actual_rules.items():
        expectation = _expect_object(
            expectations[rule_id], f"projectionRules.{rule_id}"
        )
        source_kind = expectation.get("sourceKind")
        projection_mode = expectation.get("projectionMode")
        undecidable_action = expectation.get("undecidableAction")
        if (
            not isinstance(source_kind, str)
            or rule.get("sourceKind") != source_kind
            or not isinstance(projection_mode, str)
            or rule.get("projectionMode") != projection_mode
            or not isinstance(undecidable_action, str)
            or rule.get("undecidableAction") != undecidable_action
        ):
            raise DescriptorCheckError(
                f"射影判定不能: 射影規則が凍結基準と一致しない: {rule_id}"
            )
        target_ids = rule.get("targetIds")
        if not isinstance(target_ids, list) or not all(
            isinstance(item, str) for item in target_ids
        ):
            raise DescriptorCheckError(
                f"射影判定不能: targetIdsが文字列配列でない: {rule_id}"
            )

        identity_targets = expectation.get("identityTargetIds")
        if identity_targets is not None:
            if not isinstance(identity_targets, list) or set(target_ids) != set(
                identity_targets
            ):
                raise DescriptorCheckError(
                    f"射影判定不能: identity targetがexact-set不一致: {rule_id}"
                )
        else:
            required_target_fields = expectation.get("requiredTargetFields", [])
            forbidden_target_fields = expectation.get("forbiddenTargetFields", [])
            if not isinstance(required_target_fields, list) or not isinstance(
                forbidden_target_fields, list
            ):
                raise DescriptorCheckError(
                    f"射影判定不能: target shape期待値が配列でない: {rule_id}"
                )
            for target_id in target_ids:
                expected_kind = expected_targets.get(target_id)
                if expected_kind is None:
                    raise DescriptorCheckError(
                        f"射影判定不能: 実在しないtargetIdを参照している: {target_id}"
                    )
                if expected_kind != source_kind:
                    raise DescriptorCheckError(
                        "射影判定不能: targetIdの分類とsourceKindが一致しない: "
                        f"{target_id}: {source_kind} != {expected_kind}"
                    )
                if target_id in projected_targets:
                    raise DescriptorCheckError(
                        f"射影判定不能: targetIdが複数規則へ重複している: {target_id}"
                    )
                projected_targets[target_id] = rule_id
                target = axes_by_id.get(target_id)
                if target is not None and (
                    any(field not in target for field in required_target_fields)
                    or any(field in target for field in forbidden_target_fields)
                ):
                    raise DescriptorCheckError(
                        f"射影判定不能: target shapeが射影規則と一致しない: {target_id}"
                    )

        keyword_set = (
            set(rule["jsonSchemaKeywords"])
            if isinstance(rule.get("jsonSchemaKeywords"), list)
            else set()
        )
        parity_set = (
            set(rule["parityChecks"])
            if isinstance(rule.get("parityChecks"), list)
            else set()
        )
        required_keywords = expectation.get("requiredJsonSchemaKeywords", [])
        required_parity = expectation.get("requiredParityChecks", [])
        if not isinstance(required_keywords, list) or not set(required_keywords) <= keyword_set:
            raise DescriptorCheckError(
                f"射影判定不能: JSON Schema keywordが不足している: {rule_id}"
            )
        if not isinstance(required_parity, list) or not set(required_parity) <= parity_set:
            raise DescriptorCheckError(
                f"射影判定不能: parity条件が不足している: {rule_id}"
            )
        conditional_targets = [
            target_id
            for target_id in target_ids
            if target_id in axes_by_id
            and axes_by_id[target_id].get("conditionalValues")
        ]
        if conditional_targets:
            conditional_keywords = conditional_requirements.get(
                "requiredJsonSchemaKeywords"
            )
            conditional_parity = conditional_requirements.get(
                "requiredParityChecks"
            )
            if (
                not isinstance(conditional_keywords, list)
                or not set(conditional_keywords) <= keyword_set
                or not isinstance(conditional_parity, list)
                or not set(conditional_parity) <= parity_set
            ):
                raise DescriptorCheckError(
                    "射影判定不能: 条件付き値のschema拘束が不足している: "
                    f"{rule_id}: {conditional_targets!r}"
                )

    missing_targets = sorted(set(expected_targets) - set(projected_targets))
    extra_targets = sorted(set(projected_targets) - set(expected_targets))
    if missing_targets or extra_targets:
        raise DescriptorCheckError(
            "射影判定不能: 全軸・非coverage項目の射影に覆い漏れまたは余分がある: "
            f"missing={missing_targets!r}; extra={extra_targets!r}"
        )


def validate_descriptor_document(
    descriptor: Mapping[str, Any],
    schema: Mapping[str, Any],
    source_clause_ids: frozenset[str],
) -> None:
    """descriptorのschema・段階1制約・digestを検証する。

    Args:
        descriptor: 検証対象descriptor。
        schema: descriptor用JSON Schema。
        source_clause_ids: 正本から抽出した実在条文ID。

    Raises:
        DescriptorCheckError: いずれかの検証に失敗した場合。
    """
    criteria = load_descriptor_criteria(descriptor)
    _validate_schema_contract(schema, criteria)
    _validate_instance(descriptor, schema, schema, "$")
    _walk_for_stage1_external_references(
        descriptor, criteria.forbidden_stage1_reference_keys
    )
    _validate_source_clause_ids(descriptor, source_clause_ids, criteria)
    _validate_structured_input_axes(descriptor, criteria)
    _validate_stage2_external_constraints(descriptor, criteria)
    _validate_fr040_conditionals(descriptor, criteria)
    _validate_coverage_obligations(descriptor, criteria)
    _validate_game_end_contract(descriptor, criteria)
    _validate_projection_contract(descriptor, criteria)
    forbidden_token_parts = criteria.checker_expected_values.get(
        "forbiddenDocumentTokenParts"
    )
    if not isinstance(forbidden_token_parts, list) or not all(
        isinstance(parts, list)
        and parts
        and all(isinstance(item, str) and item for item in parts)
        for parts in forbidden_token_parts
    ):
        raise DescriptorCheckError("forbiddenDocumentTokenPartsが文字列の二次元配列でない")
    forbidden_tokens = ["".join(parts) for parts in forbidden_token_parts]
    descriptor_contract = {
        key: value
        for key, value in descriptor.items()
        if key != freeze_checker.FREEZE_FIELD
    }
    descriptor_text = _canonical_json_text(descriptor_contract)
    present_forbidden_tokens = sorted(
        token for token in forbidden_tokens if token in descriptor_text
    )
    if present_forbidden_tokens:
        raise DescriptorCheckError(
            f"descriptorが禁止参照を含む: {present_forbidden_tokens!r}"
        )
    expected_digest = compute_descriptor_digest(descriptor)
    actual_digest = descriptor.get("digest")
    if actual_digest != expected_digest:
        raise DescriptorCheckError(
            f"descriptorのdigest不一致: 期待={expected_digest}; 実際={actual_digest}"
        )


def check_repository(root: Path) -> None:
    """リポジトリ内のdescriptorとschemaを検証する。

    Args:
        root: リポジトリルート。
    """
    descriptor = _expect_object(
        load_json(root / DESCRIPTOR_PATH, "入力軸descriptor"), "入力軸descriptor"
    )
    schema = _expect_object(
        load_json(root / SCHEMA_PATH, "入力軸descriptor schema"),
        "入力軸descriptor schema",
    )
    source_clause_ids = load_source_clause_ids(root)
    validate_descriptor_document(descriptor, schema, source_clause_ids)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """CLI引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="入力軸descriptorのschema適合性とdigestを検証する"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """検査CLIを実行する。

    Args:
        argv: コマンドライン引数。省略時はプロセス引数を使う。

    Returns:
        成功時0、検査違反時1。
    """
    args = _parse_args(argv)
    try:
        check_repository(args.root.resolve())
    except DescriptorCheckError as error:
        print(f"input-axes-descriptor: ERROR: {error}", file=sys.stderr)
        return 1
    print("input-axes-descriptor: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
