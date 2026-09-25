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
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_TOP_LEVEL_FIELDS = frozenset(
    {
        "descriptorId",
        "version",
        "digest",
        "digestSpec",
        "stateTransitionAxes",
        "gameEndAxes",
        "nonCoverageFields",
        "projectionRules",
    }
)
SAFE_INTEGER_LIMIT = 9_007_199_254_740_991
FORBIDDEN_STAGE1_REFERENCE_KEYS = frozenset(
    {"$ref", "externalRef", "externalReference", "externalReferences"}
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


def validate_descriptor_document(
    descriptor: Mapping[str, Any], schema: Mapping[str, Any]
) -> None:
    """descriptorのschema・段階1制約・digestを検証する。

    Args:
        descriptor: 検証対象descriptor。
        schema: descriptor用JSON Schema。

    Raises:
        DescriptorCheckError: いずれかの検証に失敗した場合。
    """
    _validate_schema_contract(schema)
    _validate_instance(descriptor, schema, schema, "$")
    _walk_for_stage1_external_references(descriptor)
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
    validate_descriptor_document(descriptor, schema)


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
