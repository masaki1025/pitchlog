"""ドメイン計算の宣言資産を検査する共通 CLI を提供する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, NoReturn, Protocol, Sequence

EXIT_CONFORMING = 0
EXIT_NONCONFORMING = 1
EXIT_INDETERMINATE = 2

_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_SUPPORTED_TYPES = frozenset(
    {"object", "array", "string", "integer", "number", "boolean", "null"}
)


class CheckerViolation(Exception):
    """検査対象が宣言契約に適合しないことを表す。"""


class CheckerExecutionError(Exception):
    """入力不備により適合性を判定できないことを表す。"""


class IndependentCollector(Protocol):
    """検査器側が実測値を独立採取するための受け口。"""

    def collect(self, root: Path) -> Mapping[str, object]:
        """リポジトリから自己申告に依存しない実測値を採取する。

        Args:
            root: 採取対象のリポジトリルート。

        Returns:
            検査器が直接採取した識別子と値の対応。
        """
        ...


@dataclass(frozen=True, slots=True)
class ExactSetDifference:
    """期待集合と実測集合の双方向差分。

    Attributes:
        missing: 期待に存在し、実測に存在しない要素。
        unexpected: 実測に存在し、期待に存在しない要素。
    """

    missing: frozenset[str]
    unexpected: frozenset[str]

    @property
    def matches(self) -> bool:
        """双方向の差がともに空なら `True` を返す。"""
        return not self.missing and not self.unexpected


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を判定不能の例外へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを送出する。"""
        raise CheckerExecutionError(message)


def canonical_json(value: object) -> str:
    """キー順序・空白・改行を固定した JSON を返す。

    Args:
        value: JSON として表現可能な値。

    Returns:
        末尾改行を 1 つ持つ canonical JSON。

    Raises:
        CheckerExecutionError: JSON として表現できない場合。
    """
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        message = f"canonical JSON に変換できない: {error}"
        raise CheckerExecutionError(message) from error
    return f"{serialized}\n"


def canonical_hash(value: object) -> str:
    """Canonical JSON の SHA-256 hash を返す。

    Args:
        value: JSON として表現可能な値。

    Returns:
        `sha256:` 接頭辞を持つ内容 hash。
    """
    digest = hashlib.sha256(canonical_json(value).encode()).hexdigest()
    return f"sha256:{digest}"


def read_json(path: Path) -> object:
    """UTF-8 JSON 資産を読み込む。

    Args:
        path: 読み込む資産のパス。

    Returns:
        JSON の値。

    Raises:
        CheckerExecutionError: 読み込みまたは JSON 解釈に失敗した場合。
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CheckerExecutionError(f"JSON 資産を読めない: {path}: {error}") from error


def write_canonical_json(path: Path, value: object) -> None:
    """Canonical JSON を UTF-8 で書き込む。

    Args:
        path: 書き込み先。
        value: JSON として表現可能な値。

    Raises:
        CheckerExecutionError: 変換または書き込みに失敗した場合。
    """
    serialized = canonical_json(value)
    try:
        path.write_text(serialized, encoding="utf-8")
    except OSError as error:
        message = f"canonical JSON を書けない: {path}: {error}"
        raise CheckerExecutionError(message) from error


def exact_set_difference(
    expected: set[str] | frozenset[str],
    observed: set[str] | frozenset[str],
) -> ExactSetDifference:
    """期待集合と実測集合の双方向差分を返す。

    Args:
        expected: 期待する識別子集合。
        observed: 実測した識別子集合。

    Returns:
        欠落と未登録を分離した差分。
    """
    return ExactSetDifference(
        missing=frozenset(expected - observed),
        unexpected=frozenset(observed - expected),
    )


def collect_independently(
    collector: IndependentCollector, root: Path
) -> dict[str, object]:
    """独立収集器を実行して実測値を通常の辞書で返す。

    Args:
        collector: 検査器が所有する収集器。
        root: 採取対象のリポジトリルート。

    Returns:
        収集器が直接採取した値。

    Raises:
        CheckerExecutionError: 収集結果のキーが文字列でない場合。
    """
    observed = collector.collect(root)
    if not all(isinstance(key, str) for key in observed):
        raise CheckerExecutionError("独立収集結果のキーは文字列でなければならない")
    return dict(observed)


def _default_root() -> Path:
    """モジュール配置からリポジトリルートを解決する。"""
    return Path(__file__).resolve().parents[4]


def _resolve_path(root: Path, path: Path) -> Path:
    """相対パスをリポジトリルート基準で解決する。"""
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _resolve_ref(schema: Mapping[str, object], ref: str) -> object:
    """同一 schema 内の JSON Pointer を解決する。"""
    if not ref.startswith("#/"):
        raise CheckerExecutionError(f"外部または不正な $ref: {ref}")
    node: object = schema
    try:
        for raw_token in ref[2:].split("/"):
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict):
                raise KeyError(token)
            node = node[token]
    except KeyError as error:
        raise CheckerExecutionError(f"解決できない $ref: {ref}") from error
    return node


def _expect_schema_mapping(value: object, label: str) -> dict[str, object]:
    """JSON object の schema 節を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckerExecutionError(f"{label}は schema object でなければならない")
    return value


def _validate_schema_node(node: object, root: Mapping[str, object], path: str) -> None:
    """本検査器が扱う JSON Schema 節の構文を検査する。"""
    if isinstance(node, bool):
        return
    mapping = _expect_schema_mapping(node, path)

    ref = mapping.get("$ref")
    if ref is not None:
        if not isinstance(ref, str):
            raise CheckerExecutionError(f"{path}.$refは文字列でなければならない")
        _resolve_ref(root, ref)

    schema_type = mapping.get("type")
    if schema_type is not None and schema_type not in _SUPPORTED_TYPES:
        raise CheckerExecutionError(f"{path}.typeが未対応である: {schema_type}")

    required = mapping.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(
            isinstance(key, str) for key in required
        ):
            raise CheckerExecutionError(f"{path}.requiredが文字列 array でない")
        if len(required) != len(set(required)):
            raise CheckerExecutionError(f"{path}.requiredに重複がある")

    properties = mapping.get("properties")
    if properties is not None:
        property_nodes = _expect_schema_mapping(properties, f"{path}.properties")
        for name, child in property_nodes.items():
            _validate_schema_node(child, root, f"{path}.properties.{name}")

    definitions = mapping.get("$defs")
    if definitions is not None:
        definition_nodes = _expect_schema_mapping(definitions, f"{path}.$defs")
        for name, child in definition_nodes.items():
            _validate_schema_node(child, root, f"{path}.$defs.{name}")

    one_of = mapping.get("oneOf")
    if one_of is not None:
        if not isinstance(one_of, list) or not one_of:
            raise CheckerExecutionError(f"{path}.oneOfが空でない array でない")
        for index, child in enumerate(one_of):
            _validate_schema_node(child, root, f"{path}.oneOf[{index}]")

    if "items" in mapping:
        _validate_schema_node(mapping["items"], root, f"{path}.items")

    additional = mapping.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        raise CheckerExecutionError(f"{path}.additionalPropertiesが boolean でない")

    for keyword in ("minItems", "maxItems", "minLength"):
        value = mapping.get(keyword)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise CheckerExecutionError(f"{path}.{keyword}が非負整数でない")
    min_items = mapping.get("minItems")
    max_items = mapping.get("maxItems")
    if (
        isinstance(min_items, int)
        and not isinstance(min_items, bool)
        and isinstance(max_items, int)
        and not isinstance(max_items, bool)
        and min_items > max_items
    ):
        raise CheckerExecutionError(f"{path}の minItems が maxItems を超える")

    unique_items = mapping.get("uniqueItems")
    if unique_items is not None and not isinstance(unique_items, bool):
        raise CheckerExecutionError(f"{path}.uniqueItemsが boolean でない")

    enum = mapping.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum):
        raise CheckerExecutionError(f"{path}.enumが空でない array でない")

    pattern = mapping.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise CheckerExecutionError(f"{path}.patternが文字列でない")
        try:
            re.compile(pattern)
        except re.error as error:
            raise CheckerExecutionError(f"{path}.patternが不正: {error}") from error

    unique_by = mapping.get("x-uniqueBy")
    if unique_by is not None and not isinstance(unique_by, str):
        raise CheckerExecutionError(f"{path}.x-uniqueByが文字列でない")
    stage_order = mapping.get("x-stageOrder")
    if stage_order is not None and (
        not isinstance(stage_order, list)
        or not all(isinstance(stage, str) for stage in stage_order)
    ):
        raise CheckerExecutionError(f"{path}.x-stageOrderが文字列 array でない")


def _validate_schema(schema: object) -> dict[str, object]:
    """Schema 全体を検査して object として返す。"""
    mapping = _expect_schema_mapping(schema, "schema")
    if mapping.get("$schema") != _JSON_SCHEMA_DIALECT:
        raise CheckerExecutionError("JSON Schema dialect が draft 2020-12 でない")
    _validate_schema_node(mapping, mapping, "schema")
    return mapping


def _matches_type(instance: object, expected: str) -> bool:
    """JSON 値が指定した基本型に適合するかを返す。"""
    match expected:
        case "object":
            return isinstance(instance, dict)
        case "array":
            return isinstance(instance, list)
        case "string":
            return isinstance(instance, str)
        case "integer":
            return isinstance(instance, int) and not isinstance(instance, bool)
        case "number":
            return isinstance(instance, (int, float)) and not isinstance(instance, bool)
        case "boolean":
            return isinstance(instance, bool)
        case "null":
            return instance is None
        case _:
            return False


def _format_values(values: frozenset[str]) -> str:
    """識別子集合を安定したリスト表記へ変換する。"""
    return repr(sorted(values))


def _raise_key_difference(path: str, expected: set[str], observed: set[str]) -> None:
    """厳密キー集合の双方向差分があれば不適合を送出する。"""
    difference = exact_set_difference(expected, observed)
    if not difference.matches:
        raise CheckerViolation(
            f"{path}: キー集合が不一致: "
            f"不足={_format_values(difference.missing)}, "
            f"未登録={_format_values(difference.unexpected)}"
        )


def _validate_instance(
    instance: object,
    node: object,
    schema: Mapping[str, object],
    path: str,
) -> None:
    """宣言 schema に対して JSON 値を検証する。"""
    if node is True:
        return
    if node is False:
        raise CheckerViolation(f"{path}: false schema により拒否された")
    mapping = _expect_schema_mapping(node, path)

    ref = mapping.get("$ref")
    if isinstance(ref, str):
        _validate_instance(instance, _resolve_ref(schema, ref), schema, path)
        return

    one_of = mapping.get("oneOf")
    if isinstance(one_of, list):
        matches = 0
        for branch in one_of:
            try:
                _validate_instance(instance, branch, schema, path)
            except CheckerViolation:
                continue
            matches += 1
        if matches != 1:
            raise CheckerViolation(f"{path}: oneOf の適合数が {matches} である")
        return

    if "const" in mapping and instance != mapping["const"]:
        raise CheckerViolation(f"{path}: const に適合しない")
    enum = mapping.get("enum")
    if isinstance(enum, list) and instance not in enum:
        raise CheckerViolation(f"{path}: enum に適合しない")

    expected_type = mapping.get("type")
    if isinstance(expected_type, str) and not _matches_type(instance, expected_type):
        raise CheckerViolation(f"{path}: {expected_type} 型でない")

    if isinstance(instance, str):
        min_length = mapping.get("minLength")
        if isinstance(min_length, int) and len(instance) < min_length:
            raise CheckerViolation(f"{path}: minLength に適合しない")
        pattern = mapping.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, instance) is None:
            raise CheckerViolation(f"{path}: pattern に適合しない")

    if isinstance(instance, dict):
        properties_value = mapping.get("properties", {})
        properties = _expect_schema_mapping(properties_value, f"{path}.properties")
        required_value = mapping.get("required", [])
        required = set(required_value) if isinstance(required_value, list) else set()
        observed = set(instance)
        if mapping.get("additionalProperties") is False:
            allowed = set(properties)
            if required == allowed:
                _raise_key_difference(path, allowed, observed)
            else:
                missing = required - observed
                unexpected = observed - allowed
                difference = ExactSetDifference(
                    missing=frozenset(missing),
                    unexpected=frozenset(unexpected),
                )
                if not difference.matches:
                    raise CheckerViolation(
                        f"{path}: キー集合が不一致: "
                        f"不足={_format_values(difference.missing)}, "
                        f"未登録={_format_values(difference.unexpected)}"
                    )
        elif missing := required - observed:
            raise CheckerViolation(f"{path}: 必須キー不足={sorted(missing)!r}")
        for key, value in instance.items():
            child = properties.get(key)
            if child is not None:
                _validate_instance(value, child, schema, f"{path}.{key}")

    if isinstance(instance, list):
        min_items = mapping.get("minItems")
        max_items = mapping.get("maxItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            raise CheckerViolation(f"{path}: minItems に適合しない")
        if isinstance(max_items, int) and len(instance) > max_items:
            raise CheckerViolation(f"{path}: maxItems に適合しない")
        if mapping.get("uniqueItems") is True:
            values = [canonical_json(value) for value in instance]
            if len(values) != len(set(values)):
                raise CheckerViolation(f"{path}: uniqueItems に適合しない")
        unique_by = mapping.get("x-uniqueBy")
        if isinstance(unique_by, str):
            values = [
                value.get(unique_by) if isinstance(value, dict) else None
                for value in instance
            ]
            canonical_values = [canonical_json(value) for value in values]
            if len(values) != len(set(canonical_values)):
                raise CheckerViolation(f"{path}: {unique_by} が重複している")
        stage_order = mapping.get("x-stageOrder")
        if isinstance(stage_order, list):
            stages = [
                value.get("stage") if isinstance(value, dict) else None
                for value in instance
            ]
            if stages != stage_order:
                raise CheckerViolation(f"{path}: 段の順序が宣言と異なる")
        if "items" in mapping:
            for index, value in enumerate(instance):
                _validate_instance(
                    value,
                    mapping["items"],
                    schema,
                    f"{path}[{index}]",
                )


def validate_asset(asset: object, schema: object) -> None:
    """資産が schema に適合することを検査する。

    Args:
        asset: 検査対象の JSON 値。
        schema: JSON Schema draft 2020-12 の schema。

    Raises:
        CheckerExecutionError: schema が不正または未対応の場合。
        CheckerViolation: 資産が schema に適合しない場合。
    """
    validated_schema = _validate_schema(schema)
    _validate_instance(asset, validated_schema, validated_schema, "$")


def _build_parser() -> argparse.ArgumentParser:
    """共通 CLI の引数パーサを作る。"""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_default_root())
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("backend/domain/manifest.schema.json"),
    )
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--print-hash", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """資産を検査し、適合・不適合・判定不能を exit コードで返す。

    Args:
        argv: CLI 引数。`None` ならプロセス引数を使う。

    Returns:
        適合は 0、不適合は 1、判定不能は 2。
    """
    try:
        arguments = _build_parser().parse_args(argv)
        root = arguments.root.resolve()
        if not root.is_dir():
            raise CheckerExecutionError(f"リポジトリルートを読めない: {root}")
        schema = read_json(_resolve_path(root, arguments.schema))
        asset = read_json(_resolve_path(root, arguments.asset))
        validate_asset(asset, schema)
        if arguments.print_hash:
            print(canonical_hash(asset))
    except CheckerViolation as error:
        print(f"不適合: {error}", file=sys.stderr)
        return EXIT_NONCONFORMING
    except CheckerExecutionError as error:
        print(f"判定不能: {error}", file=sys.stderr)
        return EXIT_INDETERMINATE
    return EXIT_CONFORMING


if __name__ == "__main__":
    raise SystemExit(main())
