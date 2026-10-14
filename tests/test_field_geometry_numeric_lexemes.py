"""フィールド領域と表示座標の契約 JSON の数値リテラルを検査する。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scripts import check_input_axes_descriptor as schema_checker

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIRECTORIES = (
    "contracts/field-regions",
    "contracts/display-geometry",
)
SCHEMA_PATHS = (
    "contracts/field-regions/field_region_seed_schema_v1.json",
    "contracts/display-geometry/field_geometry_vector_contract_schema_v1.json",
)
CONTRACT_SCHEMA_PAIRS = (
    (
        "contracts/field-regions/field_region_seed_v1.json",
        "contracts/field-regions/field_region_seed_schema_v1.json",
    ),
    (
        "contracts/field-regions/fielder_estimation_contract_v1.json",
        "contracts/display-geometry/field_geometry_vector_contract_schema_v1.json",
    ),
    (
        "contracts/display-geometry/coordinate_transform_contract_v1.json",
        "contracts/display-geometry/field_geometry_vector_contract_schema_v1.json",
    ),
)
EXPECTED_CONTRACT_DIRECTORY_JSON_COUNT = 5  # 両ディレクトリの実資産 3 本と schema 2 本。
SCHEMA_ANNOTATIONS = frozenset(
    {"$schema", "$id", "$defs", "$comment", "title", "description", "version"}
)
SCHEMA_ASSERTIONS = frozenset(
    {
        "$ref", "type", "required", "additionalProperties", "properties", "items",
        "minItems", "maxItems", "uniqueItems", "minLength", "pattern", "minimum",
        "maximum", "const", "enum", "oneOf", "anyOf", "if", "then", "not",
    }
)
NUMBER_TOKEN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*)?(?:[eE][+-]?[0-9]*)?")
NONFINITE_TOKENS = ("-Infinity", "Infinity", "NaN")


def _check_numeric_lexemes(path: Path) -> None:
    """JSON を parse せず、文字列の外にある数値リテラルを検査する。

    Args:
        path: 検査対象の JSON ファイル。

    Raises:
        AssertionError: 小数・指数・負のゼロ・非有限値が見つかった場合。
    """
    source = path.read_text(encoding="utf-8")
    in_string = False
    escaped = False
    index = 0

    while index < len(source):
        character = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            in_string = True
            index += 1
            continue

        for token in NONFINITE_TOKENS:
            if source.startswith(token, index):
                raise AssertionError(f"{path}: 禁止された数値リテラル {token}")

        if character == "-" or "0" <= character <= "9":
            match = NUMBER_TOKEN.match(source, index)
            if match is not None:
                token = match.group()
                if token == "-0" or "." in token or "e" in token.lower():
                    raise AssertionError(f"{path}: 禁止された数値リテラル {token}")
                index = match.end()
                continue

        index += 1


def _check_contract_directories(root: Path) -> int:
    """両契約ディレクトリの既存 JSON をすべて検査する。

    Args:
        root: 契約ディレクトリを含むルート。

    Returns:
        字句検査した JSON ファイルの件数。
    """
    count = 0
    for directory in CONTRACT_DIRECTORIES:
        for path in sorted((root / directory).rglob("*.json")):
            _check_numeric_lexemes(path)
            count += 1
    return count


def _check_supported_schema_keywords(schema: dict[str, Any], path: str = "$") -> None:
    """両 schema の全サブスキーマが検査可能な語だけを使うと確かめる。

    Args:
        schema: 調べるスキーマまたはサブスキーマ。
        path: エラーに表示する位置。

    Raises:
        DescriptorCheckError: 未対応の検証キーワードがある場合。
    """
    unknown = set(schema) - SCHEMA_ANNOTATIONS - SCHEMA_ASSERTIONS
    if unknown:
        raise schema_checker.DescriptorCheckError(
            f"schema: {path}: 未対応のキーワード: {sorted(unknown)!r}"
        )
    for container in ("$defs", "properties"):
        for name, child in schema.get(container, {}).items():
            _check_supported_schema_keywords(child, f"{path}.{container}.{name}")
    for name in ("items", "if", "then", "not"):
        if name in schema:
            _check_supported_schema_keywords(schema[name], f"{path}.{name}")
    for name in ("oneOf", "anyOf"):
        for index, child in enumerate(schema.get(name, [])):
            _check_supported_schema_keywords(child, f"{path}.{name}[{index}]")


def _json_equal(left: Any, right: Any) -> bool:
    """真偽値と整数を混同せず、JSON 値を再帰的に比較する。"""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(item, right[key]) for key, item in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return bool(left == right)


def _matches_schema(value: Any, schema: dict[str, Any], root_schema: dict[str, Any]) -> bool:
    """条件サブスキーマへの適合を返す。"""
    try:
        _validate_schema_instance(value, schema, root_schema, "$")
    except schema_checker.DescriptorCheckError:
        return False
    return True


def _validate_schema_instance(
    value: Any, schema: dict[str, Any], root_schema: dict[str, Any], path: str
) -> None:
    """両契約 schema が使う検証語を全文に適用する。

    既存の descriptor 検査器は anyOf・if/then・not を扱わず、oneOf の後で
    同じ階層の検証語を飛ばすため、使用語をここで漏れなく評価する。

    Args:
        value: 検査する JSON 値。
        schema: 現在のサブスキーマ。
        root_schema: `$ref` の解決元となる全文。
        path: エラーに表示する JSON 内の位置。

    Raises:
        DescriptorCheckError: 値がサブスキーマに違反する場合。
    """
    if "$ref" in schema:
        target = schema_checker._resolve_schema_reference(root_schema, schema["$ref"])
        _validate_schema_instance(value, target, root_schema, path)
    if "const" in schema and not _json_equal(value, schema["const"]):
        raise schema_checker.DescriptorCheckError(f"schema: {path}: const 不一致")
    if "enum" in schema and not any(
        _json_equal(value, item) for item in schema["enum"]
    ):
        raise schema_checker.DescriptorCheckError(f"schema: {path}: enum 外の値")
    if "type" in schema and not schema_checker._json_type_matches(value, schema["type"]):
        raise schema_checker.DescriptorCheckError(f"schema: {path}: 型不一致")
    if "oneOf" in schema and sum(
        _matches_schema(value, branch, root_schema) for branch in schema["oneOf"]
    ) != 1:
        raise schema_checker.DescriptorCheckError(f"schema: {path}: oneOf 不一致")
    if "anyOf" in schema and not any(
        _matches_schema(value, branch, root_schema) for branch in schema["anyOf"]
    ):
        raise schema_checker.DescriptorCheckError(f"schema: {path}: anyOf 不一致")
    if "not" in schema and _matches_schema(value, schema["not"], root_schema):
        raise schema_checker.DescriptorCheckError(f"schema: {path}: not 不一致")
    if "if" in schema and _matches_schema(value, schema["if"], root_schema):
        if "then" in schema:
            _validate_schema_instance(value, schema["then"], root_schema, path)

    if isinstance(value, dict):
        missing = sorted(set(schema.get("required", [])) - set(value))
        if missing:
            raise schema_checker.DescriptorCheckError(
                f"schema: {path}: 必須キー不足: {missing!r}"
            )
        properties = schema.get("properties", {})
        unknown = sorted(set(value) - set(properties))
        if schema.get("additionalProperties") is False and unknown:
            raise schema_checker.DescriptorCheckError(
                f"schema: {path}: 未知キー: {unknown!r}"
            )
        for key, child in value.items():
            if key in properties:
                _validate_schema_instance(
                    child, properties[key], root_schema, f"{path}.{key}"
                )
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise schema_checker.DescriptorCheckError(f"schema: {path}: minItems 不一致")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise schema_checker.DescriptorCheckError(f"schema: {path}: maxItems 不一致")
        if schema.get("uniqueItems") is True and any(
            _json_equal(left, right)
            for index, left in enumerate(value)
            for right in value[index + 1 :]
        ):
            raise schema_checker.DescriptorCheckError(f"schema: {path}: uniqueItems 不一致")
        if "items" in schema:
            for index, child in enumerate(value):
                _validate_schema_instance(
                    child, schema["items"], root_schema, f"{path}[{index}]"
                )
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise schema_checker.DescriptorCheckError(f"schema: {path}: minLength 不一致")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise schema_checker.DescriptorCheckError(f"schema: {path}: pattern 不一致")
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise schema_checker.DescriptorCheckError(f"schema: {path}: minimum 不一致")
        if "maximum" in schema and value > schema["maximum"]:
            raise schema_checker.DescriptorCheckError(f"schema: {path}: maximum 不一致")


def _validate_contract_asset(asset_path: Path, schema_path: Path) -> None:
    """実資産の JSON 全文を宣言元 schema のルートで検証する。

    Args:
        asset_path: 契約または参照データの JSON。
        schema_path: その契約が宣言する JSON Schema。
    """
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    _check_supported_schema_keywords(schema)
    _validate_schema_instance(asset, schema, schema, "$")


def _synthetic_seed() -> dict[str, Any]:
    """負例の出発点となる最小の領域シードを作る。"""
    return {
        "schemaVersion": 1,
        "version": "synthetic_seed_v1",
        "source": {
            "repository": "synthetic",
            "tag": "test",
            "path": "synthetic",
            "blobShaStatus": "取得は委任元が行う",
        },
        "fieldImage": {
            "originalWidth": 263,
            "originalHeight": 263,
            "normalization": {
                "sourceOrigin": "top-left",
                "targetOrigin": "bottom-left",
                "xMapping": "x / originalWidth",
                "yMapping": "1 - y / originalHeight",
            },
        },
        "regions": [
            {
                "regionId": "synthetic",
                "position": 1,
                "vertices": [
                    {"x": 0, "y": 0},
                    {"x": 1, "y": 0},
                    {"x": 0, "y": 1},
                ],
            }
        ],
        "tieBreak": "first-defined-region-wins",
    }


def _synthetic_vector() -> dict[str, Any]:
    """負例の出発点となる最小の計算ベクタを作る。"""
    return {
        "schemaVersion": 1,
        "version": "synthetic_contract_v1",
        "calculation": "synthetic",
        "independentVerifierId": "synthetic-verifier",
        "cases": [
            {
                "caseId": "synthetic-case",
                "provenance": {
                    "subjectKind": "clause",
                    "sources": [{"path": "synthetic"}],
                },
                "input": {
                    "coordinate": {"x": 0, "y": 0},
                    "coordinateSystem": "screen-263-top-left",
                },
                "expected": {"position": 1},
            }
        ],
    }


def _validate_synthetic_asset(
    tmp_path: Path, asset: dict[str, Any], schema_path: str
) -> None:
    """合成資産を一時 JSON に書いて全文検証する。

    Args:
        tmp_path: 合成資産の置き場。
        asset: 書き出す JSON の内容。
        schema_path: 対応する実 schema のリポジトリ相対パス。
    """
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(asset, ensure_ascii=False), encoding="utf-8")
    _validate_contract_asset(path, REPOSITORY_ROOT / schema_path)


def test_repository_contract_numeric_lexemes() -> None:
    """既存の契約 JSON に非正規の数値リテラルが無いことを検査する。"""
    assert (
        _check_contract_directories(REPOSITORY_ROOT)
        == EXPECTED_CONTRACT_DIRECTORY_JSON_COUNT
    )


@pytest.mark.parametrize("asset_path,schema_path", CONTRACT_SCHEMA_PAIRS)
def test_repository_contract_matches_declared_schema(
    asset_path: str, schema_path: str
) -> None:
    """3 つの実資産を各自の schema のルートに適合させる。"""
    _validate_contract_asset(REPOSITORY_ROOT / asset_path, REPOSITORY_ROOT / schema_path)


def test_synthetic_seed_without_field_image_is_rejected(tmp_path: Path) -> None:
    """合成領域シードの必須 fieldImage 欠落を拒否する。"""
    asset = _synthetic_seed()
    schema_path = SCHEMA_PATHS[0]
    _validate_synthetic_asset(tmp_path, asset, schema_path)
    del asset["fieldImage"]
    with pytest.raises(schema_checker.DescriptorCheckError, match="fieldImage"):
        _validate_synthetic_asset(tmp_path, asset, schema_path)


def test_synthetic_case_without_expected_is_rejected(tmp_path: Path) -> None:
    """合成計算ベクタのケースで必須 expected 欠落を拒否する。"""
    asset = _synthetic_vector()
    schema_path = SCHEMA_PATHS[1]
    _validate_synthetic_asset(tmp_path, asset, schema_path)
    del asset["cases"][0]["expected"]
    with pytest.raises(schema_checker.DescriptorCheckError, match="expected"):
        _validate_synthetic_asset(tmp_path, asset, schema_path)


def test_synthetic_unknown_coordinate_system_is_rejected(tmp_path: Path) -> None:
    """合成計算ベクタの座標系が enum 外なら拒否する。"""
    asset = _synthetic_vector()
    schema_path = SCHEMA_PATHS[1]
    _validate_synthetic_asset(tmp_path, asset, schema_path)
    asset["cases"][0]["input"]["coordinateSystem"] = "unknown-coordinate-system"
    with pytest.raises(schema_checker.DescriptorCheckError, match="enum 外"):
        _validate_synthetic_asset(tmp_path, asset, schema_path)


def test_synthetic_zero_ray_is_rejected(tmp_path: Path) -> None:
    """合成領域シードの零レイを not で拒否する。"""
    asset = _synthetic_seed()
    schema_path = SCHEMA_PATHS[0]
    asset["directionSectors"] = [
        {
            "directionId": "synthetic-direction",
            "startRay": {"x": 1, "y": 1},
            "endRay": {"x": 1, "y": 0},
        }
    ]
    _validate_synthetic_asset(tmp_path, asset, schema_path)
    asset["directionSectors"][0]["startRay"] = {"x": 0, "y": 0}
    with pytest.raises(schema_checker.DescriptorCheckError, match="not 不一致"):
        _validate_synthetic_asset(tmp_path, asset, schema_path)


def test_synthetic_empty_expected_is_rejected(tmp_path: Path) -> None:
    """合成計算ベクタの空 expected を anyOf で拒否する。"""
    asset = _synthetic_vector()
    schema_path = SCHEMA_PATHS[1]
    _validate_synthetic_asset(tmp_path, asset, schema_path)
    asset["cases"][0]["expected"] = {}
    with pytest.raises(schema_checker.DescriptorCheckError, match="anyOf 不一致"):
        _validate_synthetic_asset(tmp_path, asset, schema_path)


def test_synthetic_units_coordinate_requires_integer(tmp_path: Path) -> None:
    """単位 1/263 の座標では if/then により有理数を拒否する。"""
    asset = _synthetic_vector()
    schema_path = SCHEMA_PATHS[1]
    coordinate_input = asset["cases"][0]["input"]
    coordinate_input["coordinateSystem"] = "normalized-bottom-left-units-1-263"
    _validate_synthetic_asset(tmp_path, asset, schema_path)
    coordinate_input["coordinate"]["x"] = {"numerator": 1, "denominator": 263}
    with pytest.raises(schema_checker.DescriptorCheckError, match="型不一致"):
        _validate_synthetic_asset(tmp_path, asset, schema_path)


def test_synthetic_source_oneof_does_not_skip_siblings(tmp_path: Path) -> None:
    """oneOf の後も source の追加キー禁止を適用する。"""
    asset = _synthetic_seed()
    schema_path = SCHEMA_PATHS[0]
    _validate_synthetic_asset(tmp_path, asset, schema_path)
    asset["source"]["unexpected"] = "value"
    with pytest.raises(schema_checker.DescriptorCheckError, match="未知キー"):
        _validate_synthetic_asset(tmp_path, asset, schema_path)


def test_empty_contract_directories_pass(tmp_path: Path) -> None:
    """契約ディレクトリが空でも検査が成功する。"""
    for directory in CONTRACT_DIRECTORIES:
        (tmp_path / directory).mkdir(parents=True)
    _check_contract_directories(tmp_path)


def test_integer_literals_and_quoted_text_pass(tmp_path: Path) -> None:
    """整数は許容し、文字列内の数値らしい文字列は無視する。"""
    path = tmp_path / "valid.json"
    path.write_text(
        '{"text":"quoted \\"1.0\\" -0 NaN Infinity -Infinity",'
        '"values":[-10,0,10,1000]}',
        encoding="utf-8",
    )
    _check_numeric_lexemes(path)


@pytest.mark.parametrize(
    "token",
    ("1.0", "1e3", "1E+3", "-0", "-0.0", "-0e0", "NaN", "Infinity", "-Infinity"),
)
def test_noncanonical_numeric_literal_is_rejected(tmp_path: Path, token: str) -> None:
    """合成 JSON の禁止トークンを字句検査が拒否する。"""
    path = tmp_path / "invalid.json"
    path.write_text('{"value": ' + token + ', "scale": 10}', encoding="utf-8")

    with pytest.raises(AssertionError, match=re.escape(token)):
        _check_numeric_lexemes(path)


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS)
def test_numeric_value_accepts_three_distinct_forms(schema_path: str) -> None:
    """両 schema が整数・decimal・有理数をそれぞれ受理する。"""
    schema = json.loads((REPOSITORY_ROOT / schema_path).read_text(encoding="utf-8"))
    for value in (10**30, {"value": 1, "scale": 10}, {"numerator": 1, "denominator": 263}):
        schema_checker._validate_instance(value, schema["$defs"]["numericValue"], schema, "$")
    point = {"x": {"numerator": 1, "denominator": 263}, "y": 0}
    schema_checker._validate_instance(point, schema["$defs"]["point"], schema, "$")

    mixed = {"value": 1, "scale": 10, "numerator": 1, "denominator": 263}
    with pytest.raises(schema_checker.DescriptorCheckError):
        schema_checker._validate_instance(mixed, schema["$defs"]["numericValue"], schema, "$")


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS)
def test_zero_denominator_is_rejected(tmp_path: Path, schema_path: str) -> None:
    """合成 JSON の分母 0 は字句検査を通っても schema で拒否される。"""
    path = tmp_path / "zero_denominator.json"
    path.write_text('{"x":{"numerator":1,"denominator":0},"y":0}', encoding="utf-8")
    _check_numeric_lexemes(path)

    schema = json.loads((REPOSITORY_ROOT / schema_path).read_text(encoding="utf-8"))
    point = json.loads(path.read_text(encoding="utf-8"))
    with pytest.raises(schema_checker.DescriptorCheckError):
        schema_checker._validate_instance(point, schema["$defs"]["point"], schema, "$")
