"""入力軸descriptorのschema適合性と内容digestを検証する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

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
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_TOP_LEVEL_FIELDS = frozenset(
    {
        "descriptorId",
        "version",
        "digest",
        "digestSpec",
        "stateTransitionAxes",
        "gameEndAxes",
        "gameEndCombinationRules",
        "nonCoverageFields",
        "projectionRules",
    }
)
SAFE_INTEGER_LIMIT = 9_007_199_254_740_991
FORBIDDEN_STAGE1_REFERENCE_KEYS = frozenset(
    {"$ref", "externalRef", "externalReference", "externalReferences"}
)
CLAUSE_HEADING_PATTERN = re.compile(
    r"^#{2,6}\s+(?P<clause_id>(?:FR|NFR)-\d+|\d+\.\d+-\d+|[A-Z]-\d+[a-z]?)(?=[:\s])"
)
APPENDIX_HEADING_PATTERN = re.compile(r"^##\s+付録(?P<letter>[A-Z]):")
APPENDIX_ITEM_PATTERN = re.compile(r"^(?P<number>\d+)\.\s+")
STABLE_TABLE_CLAUSE_PATTERN = re.compile(
    r"^\s*\|\s*`(?P<clause_id>"
    r"(?:COLD|DRAW|XMARK|OUT3|ADV|INT|SO|RBI|XC)-\d+)`\s*\|"
)
EXPECTED_GAME_END_AXIS_FIELDS = {
    "gameEnd.regulationInnings": "regulationInnings",
    "gameEnd.coldConditions": "coldConditions",
    "gameEnd.extensionLimit": "extensionLimit",
    "gameEnd.tiebreak": "tiebreak",
}
EXPECTED_F1_RULE_FIELDS = frozenset(
    {"regulationInnings", "coldConditions", "extensionLimit", "tiebreak", "dh"}
)
EXPECTED_NON_COVERAGE_FIELDS = frozenset(
    {"dh", "tiebreak.runnerPlacement", "tiebreak.leadoffRule"}
)


class DescriptorCheckError(Exception):
    """descriptorを検証できない場合を表す。"""


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
    """要件書とADRの構造から実在する由来条文IDを抽出する。"""
    return load_clause_ids_from_paths(root, SOURCE_CLAUSE_PATHS)


def _expect_object(value: object, label: str) -> dict[str, Any]:
    """JSON値をobjectとして返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DescriptorCheckError(f"{label}は文字列キーのobjectでなければならない")
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


def _canonical_json_text(value: object) -> str:
    """descriptorで許可するJSON値をRFC 8785形式へ正規化する。"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER_LIMIT:
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
        return "[" + ",".join(_canonical_json_text(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise DescriptorCheckError("JSON objectのキーは文字列でなければならない")
        try:
            keys = sorted(value, key=lambda key: key.encode("utf-16be"))
        except UnicodeEncodeError as error:
            raise DescriptorCheckError("objectキーに不正なUnicode surrogateがある") from error
        members = (
            f"{_canonical_json_text(key)}:{_canonical_json_text(value[key])}"
            for key in keys
        )
        return "{" + ",".join(members) + "}"
    raise DescriptorCheckError(f"JSON値として扱えない型がある: {type(value).__name__}")


def canonicalize_json(value: object) -> bytes:
    """JSON値をRFC 8785準拠のUTF-8バイト列へ正規化する。

    descriptor schemaは浮動小数点数を許さず、整数をI-JSON安全範囲へ閉じる。
    そのため数値表現の実装依存を持たず、標準ライブラリだけで再現できる。

    Args:
        value: 正規化するJSON値。

    Returns:
        正規化済みUTF-8バイト列。
    """
    return _canonical_json_text(value).encode("utf-8")


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
    digest_input = {key: value for key, value in descriptor.items() if key != "digest"}
    digest = hashlib.sha256(canonicalize_json(digest_input)).hexdigest()
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


def _validate_schema_contract(schema: Mapping[str, Any]) -> None:
    """schema自身がdescriptorの必須構造を閉じていることを検証する。"""
    if schema.get("$schema") != JSON_SCHEMA_DIALECT:
        raise DescriptorCheckError("schemaのdialectはJSON Schema 2020-12でなければならない")
    if schema.get("version") != SCHEMA_PATH.stem:
        raise DescriptorCheckError("schemaのファイル名と内部versionが一致しない")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise DescriptorCheckError("schemaのトップレベルobjectが閉じていない")
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or frozenset(required) != EXPECTED_TOP_LEVEL_FIELDS:
        raise DescriptorCheckError("schemaのトップレベルrequiredがexact-set不一致")
    if not isinstance(properties, dict) or frozenset(properties) != EXPECTED_TOP_LEVEL_FIELDS:
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
        "supportingClauseIds",
        "ruleFieldId",
        "coverageBound",
        "gameEndCombinationRules",
    }
    if not required_definitions <= set(definitions):
        missing = sorted(required_definitions - set(definitions))
        raise DescriptorCheckError(f"schemaの必須$defsが不足している: {missing!r}")


def _walk_for_stage1_external_references(value: object, path: str = "$") -> None:
    """段階1で禁止した外部参照キーがdescriptorに無いことを検証する。"""
    if isinstance(value, dict):
        forbidden = sorted(FORBIDDEN_STAGE1_REFERENCE_KEYS & set(value))
        if forbidden:
            raise DescriptorCheckError(f"段階1の外部参照キーがある: {path}: {forbidden!r}")
        for key, child in value.items():
            _walk_for_stage1_external_references(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_for_stage1_external_references(child, f"{path}[{index}]")


def _validate_source_clause_ids(
    descriptor: Mapping[str, Any], source_clause_ids: frozenset[str]
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
            for clause_id in cited_ids:
                if isinstance(clause_id, str) and clause_id not in source_clause_ids:
                    raise DescriptorCheckError(
                        "由来条文IDが正本に実在しない: "
                        f"{collection_name}[{index}]: {clause_id}"
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


def coverage_obligation_count(axis: Mapping[str, Any]) -> int:
    """軸から展開すべきcoverage座標の件数を返す。

    `non-finite`は理由だけではcoverage座標を生まないため0件とする。無限領域は
    `boundary-partition`として境界値・等価分割を明示してから登録しなければならない。
    """
    classification = axis.get("classification")
    if classification == "finite-enumerable":
        values = axis.get("values")
        return len(values) if isinstance(values, list) else 0
    if classification == "boundary-partition":
        values = axis.get("boundaryValues")
        invalid_values = axis.get("invalidBoundaryValues", [])
        valid_count = len(values) if isinstance(values, list) else 0
        invalid_count = len(invalid_values) if isinstance(invalid_values, list) else 0
        return valid_count + invalid_count
    return 0


def _validate_coverage_obligations(descriptor: Mapping[str, Any]) -> None:
    """全入力軸が1件以上のcoverage義務を生成することを検証する。"""
    for collection_name in ("stateTransitionAxes", "gameEndAxes"):
        axes = descriptor.get(collection_name)
        if not isinstance(axes, list):
            continue
        for index, axis_value in enumerate(axes):
            if not isinstance(axis_value, dict):
                continue
            if coverage_obligation_count(axis_value) == 0:
                axis_id = axis_value.get("axisId", f"index={index}")
                raise DescriptorCheckError(
                    f"coverage義務が0件の入力軸がある: {collection_name}: {axis_id}"
                )


def _validate_game_end_contract(descriptor: Mapping[str, Any]) -> None:
    """F-1の終了判定軸・非coverage項目・組合せ規則を検証する。"""
    game_end_axes = descriptor.get("gameEndAxes")
    if not isinstance(game_end_axes, list):
        return
    axis_fields = {
        axis.get("axisId"): axis.get("ruleFieldId")
        for axis in game_end_axes
        if isinstance(axis, dict)
    }
    if axis_fields != EXPECTED_GAME_END_AXIS_FIELDS:
        raise DescriptorCheckError(
            "gameEndAxesの4軸またはF-1フィールド帰属がexact-set不一致"
        )
    for axis in game_end_axes:
        if not isinstance(axis, dict):
            continue
        if axis.get("classification") != "boundary-partition":
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
    if non_coverage_ids != EXPECTED_NON_COVERAGE_FIELDS:
        raise DescriptorCheckError("nonCoverageFieldsの3件がexact-set不一致")
    if any(
        field.get("schemaRetention") != "required-by-projection"
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
    if covered_top_level | non_covered_top_level != EXPECTED_F1_RULE_FIELDS:
        raise DescriptorCheckError("F-1の5フィールドに未帰属または余分な帰属がある")

    combination_rules = descriptor.get("gameEndCombinationRules")
    if not isinstance(combination_rules, dict):
        return
    if combination_rules.get("ruleFieldCombination") != "pairwise-all-game-end-axes":
        raise DescriptorCheckError("終了規則フィールドは全4軸のペアワイズでなければならない")
    if (
        combination_rules.get("boundaryValueCombination")
        != "full-cross-product-with-all-state-and-event-axes"
    ):
        raise DescriptorCheckError(
            "終了規則の各境界値は全状態軸・イベント軸と直積しなければならない"
        )

    tiebreak_axis = next(
        axis
        for axis in game_end_axes
        if isinstance(axis, dict) and axis.get("axisId") == "gameEnd.tiebreak"
    )
    valid_tiebreak = set(tiebreak_axis.get("boundaryValues", []))
    invalid_tiebreak = set(tiebreak_axis.get("invalidBoundaryValues", []))
    if not {"none", "start:R+1", "start:L"} <= valid_tiebreak or not {
        "start:R",
        "start:L+1-when-finite",
    } <= invalid_tiebreak:
        raise DescriptorCheckError("タイブレーク開始回がDRAW-03の境界を覆っていない")


def _validate_projection_contract(descriptor: Mapping[str, Any]) -> None:
    """全軸と非coverage項目が一意かつ判定可能に射影されることを検証する。"""
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

    non_coverage_fields = descriptor.get("nonCoverageFields")
    if isinstance(non_coverage_fields, list):
        for field in non_coverage_fields:
            if not isinstance(field, dict):
                continue
            field_id = field.get("fieldId")
            if isinstance(field_id, str):
                expected_targets[field_id] = "non-coverage-field"

    rules = descriptor.get("projectionRules")
    if not isinstance(rules, list):
        return
    seen_rule_ids: set[str] = set()
    projected_targets: dict[str, str] = {}
    declared_source_kinds: set[str] = set()
    identity_targets = {"descriptorId", "version", "digest"}
    expected_kinds = {
        "finite-enumerable",
        "boundary-partition",
        "non-finite",
        "non-coverage-field",
        "descriptor-identity",
    }

    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("ruleId")
        source_kind = rule.get("sourceKind")
        target_ids = rule.get("targetIds")
        if not isinstance(rule_id, str) or not isinstance(source_kind, str):
            continue
        if rule_id in seen_rule_ids:
            raise DescriptorCheckError(f"射影判定不能: ruleIdが重複している: {rule_id}")
        seen_rule_ids.add(rule_id)
        declared_source_kinds.add(source_kind)
        if not isinstance(target_ids, list):
            continue

        if source_kind == "descriptor-identity":
            if set(target_ids) != identity_targets:
                raise DescriptorCheckError(
                    "射影判定不能: descriptorId・version・digestの拘束がexact-set不一致"
                )
            identity_keywords = rule.get("jsonSchemaKeywords")
            identity_parity = rule.get("parityChecks")
            if rule.get("projectionMode") != "descriptor-identity-binding" or not {
                "x-pitchlog-descriptor-id",
                "x-pitchlog-descriptor-version",
                "x-pitchlog-descriptor-digest",
            } <= (set(identity_keywords) if isinstance(identity_keywords, list) else set()):
                raise DescriptorCheckError(
                    "射影判定不能: descriptor identityのschema拘束が不足している"
                )
            if "descriptor-identity-exact" not in (
                set(identity_parity) if isinstance(identity_parity, list) else set()
            ):
                raise DescriptorCheckError(
                    "射影判定不能: descriptor identityの一致条件が不足している"
                )
            if rule.get("undecidableAction") != "fail":
                raise DescriptorCheckError(
                    "射影判定不能: descriptor identity規則がfail-closedでない"
                )
            continue

        for target_id in target_ids:
            if not isinstance(target_id, str):
                continue
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

            projection_mode = rule.get("projectionMode")
            if source_kind == "finite-enumerable" and projection_mode != "exact-enum":
                raise DescriptorCheckError(
                    f"射影判定不能: 有限列挙軸がenum射影でない: {target_id}"
                )
            if source_kind == "boundary-partition":
                axis = axes_by_id[target_id]
                expected_mode = (
                    "bounded-boundary-annotations"
                    if "coverageBounds" in axis
                    else "boundary-annotations"
                )
                if projection_mode != expected_mode:
                    raise DescriptorCheckError(
                        "射影判定不能: 境界値分割の射影方式が値域定義と一致しない: "
                        f"{target_id}"
                    )
            if (
                source_kind == "non-finite"
                and projection_mode != "open-domain-with-reason"
            ):
                raise DescriptorCheckError(
                    f"射影判定不能: 非有限軸の理由保持がない: {target_id}"
                )
            if (
                source_kind == "non-coverage-field"
                and projection_mode != "required-schema-property"
            ):
                raise DescriptorCheckError(
                    f"射影判定不能: 非coverage項目がschema必須項目でない: {target_id}"
                )

        keywords = rule.get("jsonSchemaKeywords")
        parity_checks = rule.get("parityChecks")
        keyword_set = set(keywords) if isinstance(keywords, list) else set()
        parity_set = set(parity_checks) if isinstance(parity_checks, list) else set()
        required_keywords: dict[str, set[str]] = {
            "finite-enumerable": {"enum"},
            "boundary-partition": {"x-pitchlog-boundary-values"},
            "non-finite": {"type", "x-pitchlog-non-finite-reason"},
            "non-coverage-field": {"properties", "required"},
        }
        required_parity: dict[str, set[str]] = {
            "finite-enumerable": {"values-exact-set"},
            "boundary-partition": {"boundaries-exact-set"},
            "non-finite": {"non-finite-reason-exact"},
            "non-coverage-field": {"field-id-exact", "schema-retention-exact"},
        }
        if not required_keywords.get(source_kind, set()) <= keyword_set:
            raise DescriptorCheckError(
                f"射影判定不能: JSON Schema keywordが不足している: {rule_id}"
            )
        if not required_parity.get(source_kind, set()) <= parity_set:
            raise DescriptorCheckError(
                f"射影判定不能: parity条件が不足している: {rule_id}"
            )
        if rule.get("projectionMode") == "bounded-boundary-annotations":
            if not {"minimum", "maximum"} <= keyword_set or "range-exact" not in parity_set:
                raise DescriptorCheckError(
                    f"射影判定不能: 整数値域のminimum・maximum拘束が不足している: {rule_id}"
                )
        if rule.get("undecidableAction") != "fail":
            raise DescriptorCheckError(
                f"射影判定不能: fail-closedでない規則がある: {rule_id}"
            )

    if declared_source_kinds != expected_kinds:
        raise DescriptorCheckError("射影判定不能: 射影方針の分類がexact-set不一致")
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
    _validate_schema_contract(schema)
    _validate_instance(descriptor, schema, schema, "$")
    _walk_for_stage1_external_references(descriptor)
    _validate_source_clause_ids(descriptor, source_clause_ids)
    _validate_coverage_obligations(descriptor)
    _validate_game_end_contract(descriptor)
    _validate_projection_contract(descriptor)
    if "history-depth.json" in _canonical_json_text(descriptor):
        raise DescriptorCheckError("descriptorはhistory-depth.jsonを参照してはならない")
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
