"""宣言モデルを言語非依存の中間表現へ変換する生成コア。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

GENERATOR_VERSION = "1.0.0"
EXIT_GENERATED = 0
EXIT_GENERATION_FAILED = 1

_MODEL_SCHEMA = "model.schema.json"
_MANIFEST_SCHEMA = "manifest.schema.json"
_VOCABULARY_SCHEMA = "vocabulary.schema.json"
_SCHEMA_VERSION = 1
_HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"

INTERMEDIATE_REPRESENTATION_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://pitchlog.local/schemas/domain/intermediate.json",
    "title": "ドメイン計算の言語非依存中間表現",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schemaVersion",
        "generatorVersion",
        "displayRules",
        "calculations",
    ],
    "properties": {
        "schemaVersion": {"const": _SCHEMA_VERSION},
        "generatorVersion": {"type": "string", "minLength": 1},
        "displayRules": {"$ref": "model.schema.json#/properties/displayRules"},
        "calculations": {
            "type": "array",
            "items": {"$ref": "#/$defs/Calculation"},
            "x-uniqueBy": "calculationId",
        },
    },
    "$defs": {
        "Calculation": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "calculationId",
                "sourceId",
                "declaration",
                "targets",
            ],
            "properties": {
                "calculationId": {"$ref": "model.schema.json#/$defs/Identifier"},
                "sourceId": {"$ref": "manifest.schema.json#/$defs/AuthorityId"},
                "declaration": {"$ref": "model.schema.json#/$defs/Calculation"},
                "targets": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/$defs/Target"},
                    "x-uniqueBy": "directTargetId",
                },
            },
        },
        "Target": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "directTargetId",
                "targetClass",
                "kind",
                "stages",
                "invocation",
            ],
            "properties": {
                "directTargetId": {"$ref": "manifest.schema.json#/$defs/Identifier"},
                "targetClass": {"type": "string", "minLength": 1},
                "kind": {"enum": ["single", "composite"]},
                "stages": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/$defs/Stage"},
                    "x-uniqueBy": "generatedId",
                },
                "invocation": {"$ref": "manifest.schema.json#/$defs/Invocation"},
            },
        },
        "Stage": {
            "type": "object",
            "additionalProperties": False,
            "required": ["stage", "generatedId", "sourceHash"],
            "properties": {
                "stage": {"type": "string", "minLength": 1},
                "generatedId": {"$ref": "manifest.schema.json#/$defs/Identifier"},
                "sourceHash": {
                    "type": "string",
                    "pattern": _HASH_PATTERN,
                },
            },
        },
    },
}


class GenerationError(Exception):
    """入力から中間表現を生成できないことを表す。"""


@dataclass(frozen=True, slots=True)
class SourceSchemas:
    """既存資産から読み込んだ生成入力の schema 群。

    Attributes:
        model: 宣言モデルの schema。
        manifest: マニフェストの schema。
        vocabulary: 宣言モデルが外部参照する表示語彙 schema。
    """

    model: Mapping[str, object]
    manifest: Mapping[str, object]
    vocabulary: Mapping[str, object]

    def documents(self) -> dict[str, Mapping[str, object]]:
        """外部参照名から schema への対応を返す。"""
        return {
            _MODEL_SCHEMA: self.model,
            _MANIFEST_SCHEMA: self.manifest,
            _VOCABULARY_SCHEMA: self.vocabulary,
        }


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を生成失敗へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを生成失敗として送出する。"""
        raise GenerationError(message)


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GenerationError(f"{label}が JSON object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise GenerationError(f"{label}が JSON array でない")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise GenerationError(f"{label}が空でない文字列でない")
    return value


def _canonical_json(value: object) -> str:
    """Hash と標準出力に使う canonical JSON を返す。"""
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise GenerationError(f"JSON に変換できない: {error}") from error
    return f"{serialized}\n"


def _canonical_hash(value: object) -> str:
    """値の canonical JSON に対する SHA-256 hash を返す。"""
    digest = hashlib.sha256(_canonical_json(value).encode()).hexdigest()
    return f"sha256:{digest}"


def _read_json(path: Path) -> object:
    """UTF-8 の JSON ファイルを読み込む。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GenerationError(f"JSON を読めない: {path}: {error}") from error


def _pointer(document: object, pointer: str, label: str) -> object:
    """同一文書内の JSON Pointer を解決する。"""
    if not pointer.startswith("#"):
        raise GenerationError(f"{label}の JSON Pointer が不正: {pointer}")
    node = document
    if pointer == "#":
        return node
    if not pointer.startswith("#/"):
        raise GenerationError(f"{label}の JSON Pointer が不正: {pointer}")
    try:
        for raw_token in pointer[2:].split("/"):
            token = raw_token.replace("~1", "/").replace("~0", "~")
            node = _object(node, label)[token]
    except KeyError as error:
        raise GenerationError(f"{label}の参照先がない: {pointer}") from error
    return node


def _resolve_ref(
    ref: str,
    current_name: str,
    schemas: Mapping[str, Mapping[str, object]],
) -> tuple[object, str]:
    """ローカル参照と許可した schema 間参照を解決する。"""
    if ref.startswith("#"):
        document_name = current_name
        pointer = ref
    else:
        document_name, separator, fragment = ref.partition("#")
        pointer = f"#{fragment}" if separator else "#"
    try:
        document = schemas[document_name]
    except KeyError as error:
        raise GenerationError(f"許可されていない schema 参照: {ref}") from error
    return _pointer(document, pointer, ref), document_name


def _matches_type(value: object, expected: str) -> bool:
    """JSON 値が schema の基本型に適合するかを返す。"""
    match expected:
        case "object":
            return isinstance(value, dict)
        case "array":
            return isinstance(value, list)
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        case "boolean":
            return isinstance(value, bool)
        case "null":
            return value is None
        case _:
            raise GenerationError(f"未対応の schema type: {expected}")


def _validate_instance(
    value: object,
    node: object,
    current_name: str,
    schemas: Mapping[str, Mapping[str, object]],
    path: str,
) -> None:
    """既存 schema が使う閉じた語彙で入力を検証する。"""
    if node is True:
        return
    if node is False:
        raise GenerationError(f"{path}が false schema により拒否された")
    schema = _object(node, f"{path}の schema")

    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved, resolved_name = _resolve_ref(ref, current_name, schemas)
        _validate_instance(value, resolved, resolved_name, schemas, path)
        return

    branches = schema.get("oneOf")
    if isinstance(branches, list):
        matches = 0
        failures: list[str] = []
        for branch in branches:
            try:
                _validate_instance(value, branch, current_name, schemas, path)
            except GenerationError as error:
                failures.append(str(error))
                continue
            matches += 1
        if matches != 1:
            raise GenerationError(
                f"{path}の oneOf 適合数が {matches} である: " + "; ".join(failures)
            )
        return

    if "const" in schema and value != schema["const"]:
        raise GenerationError(f"{path}が const に適合しない")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        raise GenerationError(f"{path}が enum に適合しない")

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _matches_type(value, expected_type):
        raise GenerationError(f"{path}が {expected_type} 型でない")

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            raise GenerationError(f"{path}が minLength に適合しない")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise GenerationError(f"{path}が pattern に適合しない")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise GenerationError(f"{path}が minimum に適合しない")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise GenerationError(f"{path}が maximum に適合しない")

    if isinstance(value, dict):
        properties = _object(schema.get("properties", {}), f"{path}.properties")
        required_value = schema.get("required", [])
        required_items = _array(required_value, f"{path}.required")
        if not all(isinstance(item, str) for item in required_items):
            raise GenerationError(f"{path}.requiredが文字列配列でない")
        required = set(cast(list[str], required_items))
        missing = required - set(value)
        unknown = set(value) - set(properties)
        if missing:
            raise GenerationError(f"{path}の必須キー不足: {sorted(missing)!r}")
        if schema.get("additionalProperties") is False and unknown:
            raise GenerationError(f"{path}の未知キー: {sorted(unknown)!r}")
        for key, child in value.items():
            child_schema = properties.get(key)
            if child_schema is not None:
                _validate_instance(
                    child,
                    child_schema,
                    current_name,
                    schemas,
                    f"{path}.{key}",
                )

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        maximum_items = schema.get("maxItems")
        if isinstance(minimum_items, int) and len(value) < minimum_items:
            raise GenerationError(f"{path}が minItems に適合しない")
        if isinstance(maximum_items, int) and len(value) > maximum_items:
            raise GenerationError(f"{path}が maxItems に適合しない")
        canonical = [_canonical_json(item) for item in value]
        if schema.get("uniqueItems") is True and len(canonical) != len(set(canonical)):
            raise GenerationError(f"{path}が uniqueItems に適合しない")
        unique_by = schema.get("x-uniqueBy")
        if isinstance(unique_by, str):
            identifiers = [
                item.get(unique_by) if isinstance(item, dict) else None
                for item in value
            ]
            serialized = [_canonical_json(item) for item in identifiers]
            if len(serialized) != len(set(serialized)):
                raise GenerationError(f"{path}の {unique_by} が重複している")
        stage_order = schema.get("x-stageOrder")
        if isinstance(stage_order, list):
            observed = [
                item.get("stage") if isinstance(item, dict) else None for item in value
            ]
            if observed != stage_order:
                raise GenerationError(f"{path}の段順が schema と異なる")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, child in enumerate(value):
                _validate_instance(
                    child,
                    item_schema,
                    current_name,
                    schemas,
                    f"{path}[{index}]",
                )


def _validate_source_document(
    value: object,
    name: str,
    schemas: SourceSchemas,
) -> None:
    """入力資産を既存 schema そのものに対して検証する。"""
    documents = schemas.documents()
    _validate_instance(value, documents[name], name, documents, "$")


def _section_text(source: str, heading: str) -> str:
    """正本文書から指定した節の本文だけを取り出す。"""
    lines = source.splitlines()
    try:
        start = lines.index(heading)
    except ValueError as error:
        raise GenerationError(f"正本に節見出しがない: {heading}") from error
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#+)\s", lines[index])
        if match is not None and len(match.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _validate_authority(
    authority_id: str,
    schemas: SourceSchemas,
    root: Path,
) -> None:
    """生成元条項 ID の形式と指定節における逐語の実在を検証する。"""
    documents = schemas.documents()
    authority_schema = schemas.manifest.get("$defs")
    definitions = _object(authority_schema, "manifest.$defs")
    _validate_instance(
        authority_id,
        definitions.get("AuthorityId"),
        _MANIFEST_SCHEMA,
        documents,
        "sourceId",
    )

    candidates: list[dict[str, object]] = []
    for name, document in (
        (_MODEL_SCHEMA, schemas.model),
        (_MANIFEST_SCHEMA, schemas.manifest),
    ):
        entries = _array(document.get("x-authorityCatalog", []), f"{name}.catalog")
        for index, entry in enumerate(entries):
            candidate = _object(entry, f"{name}.catalog[{index}]")
            if candidate.get("id") == authority_id:
                candidates.append(candidate)
    if len(candidates) != 1:
        raise GenerationError(
            f"生成元条項 ID のカタログ対応が一意でない: {authority_id}"
        )

    entry = candidates[0]
    source_path = root / _string(entry.get("source"), "authority.source")
    section = _string(entry.get("section"), "authority.section")
    verbatim = _string(entry.get("verbatim"), "authority.verbatim")
    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GenerationError(f"正本を読めない: {source_path}: {error}") from error
    if verbatim not in _section_text(source, section):
        raise GenerationError(f"生成元条項の逐語が正本にない: {authority_id}")


def _index_by(
    values: list[object],
    key: str,
    label: str,
) -> dict[str, dict[str, object]]:
    """Object の配列を文字列 ID で一意に索引化する。"""
    indexed: dict[str, dict[str, object]] = {}
    for index, value in enumerate(values):
        item = _object(value, f"{label}[{index}]")
        identifier = _string(item.get(key), f"{label}[{index}].{key}")
        if identifier in indexed:
            raise GenerationError(f"{label}の {key} が重複している: {identifier}")
        indexed[identifier] = item
    return indexed


def _selected_display_rules(
    declaration: Mapping[str, object],
    display_rules: Mapping[str, dict[str, object]],
) -> list[dict[str, object]]:
    """計算が参照する表示規則だけを宣言順で返す。"""
    references = _array(
        declaration.get("displayRuleRefs"),
        "calculation.displayRuleRefs",
    )
    selected: list[dict[str, object]] = []
    for raw_reference in references:
        reference = _string(raw_reference, "displayRuleRefs[]")
        try:
            selected.append(display_rules[reference])
        except KeyError as error:
            raise GenerationError(f"未知の表示規則参照: {reference}") from error
    return selected


def _target_stages(
    target: Mapping[str, object],
    artifacts: Mapping[str, dict[str, object]],
) -> list[tuple[str, str]]:
    """Manifest schema の target 分岐から段名と生成物 ID を取り出す。"""
    kind = _string(target.get("kind"), "directTarget.kind")
    if kind == "single":
        generated_id = _string(target.get("generated"), "directTarget.generated")
        try:
            artifact = artifacts[generated_id]
        except KeyError as error:
            raise GenerationError(f"未知の生成物参照: {generated_id}") from error
        stage = _string(artifact.get("artifactKind"), "generated.artifactKind")
        return [(stage, generated_id)]
    if kind != "composite":
        raise GenerationError(f"未知の direct target kind: {kind}")

    stages: list[tuple[str, str]] = []
    components = _array(target.get("components"), "directTarget.components")
    for index, raw_component in enumerate(components):
        component = _object(raw_component, f"components[{index}]")
        stage = _string(component.get("stage"), f"components[{index}].stage")
        generated_id = _string(
            component.get("generated"),
            f"components[{index}].generated",
        )
        if generated_id not in artifacts:
            raise GenerationError(f"未知の生成物参照: {generated_id}")
        stages.append((stage, generated_id))
    return stages


def _build_target(
    declaration: Mapping[str, object],
    display_rules: list[dict[str, object]],
    target: Mapping[str, object],
    artifacts: Mapping[str, dict[str, object]],
    source_id: str,
) -> dict[str, object]:
    """一つの direct target を段別 hash 付き中間表現へ変換する。"""
    direct_target_id = _string(
        target.get("directTargetId"),
        "directTarget.directTargetId",
    )
    target_class = _string(target.get("targetClass"), "directTarget.targetClass")
    kind = _string(target.get("kind"), "directTarget.kind")
    invocation = _object(target.get("invocation"), "directTarget.invocation")

    stages: list[dict[str, object]] = []
    for stage, generated_id in _target_stages(target, artifacts):
        source_payload = {
            "generatorVersion": GENERATOR_VERSION,
            "sourceId": source_id,
            "declaration": declaration,
            "displayRules": display_rules,
            "target": {
                "directTargetId": direct_target_id,
                "targetClass": target_class,
                "kind": kind,
                "invocation": invocation,
            },
            "stage": {"stage": stage, "generatedId": generated_id},
        }
        stages.append(
            {
                "stage": stage,
                "generatedId": generated_id,
                "sourceHash": _canonical_hash(source_payload),
            }
        )
    return {
        "directTargetId": direct_target_id,
        "targetClass": target_class,
        "kind": kind,
        "stages": stages,
        "invocation": copy.deepcopy(invocation),
    }


def generate_intermediate_representation(
    model: object | None,
    manifest: object | None,
    schemas: SourceSchemas,
    root: Path,
) -> dict[str, object]:
    """宣言モデルとマニフェストから言語非依存の中間表現を生成する。

    Args:
        model: 宣言モデル。`None` は処理対象がない空入力を表す。
        manifest: 宣言モデルに対応するマニフェスト。
        schemas: 入力フィールドの正とする既存 schema 群。
        root: 条項 ID の逐語を検証するリポジトリルート。

    Returns:
        段別 hash、生成器 version、生成元条項 ID を持つ中間表現。

    Raises:
        GenerationError: 入力が schema に不適合、または対応が一意でない場合。
    """
    if model is None and manifest is None:
        intermediate = {
            "schemaVersion": _SCHEMA_VERSION,
            "generatorVersion": GENERATOR_VERSION,
            "displayRules": [],
            "calculations": [],
        }
        validate_intermediate_representation(intermediate, schemas)
        return intermediate
    if model is None or manifest is None:
        raise GenerationError("model と manifest は同時に指定しなければならない")

    _validate_source_document(model, _MODEL_SCHEMA, schemas)
    _validate_source_document(manifest, _MANIFEST_SCHEMA, schemas)
    model_object = _object(model, "model")
    manifest_object = _object(manifest, "manifest")
    model_calculations = _index_by(
        _array(model_object.get("calculations"), "model.calculations"),
        "calculationId",
        "model.calculations",
    )
    manifest_calculations = _index_by(
        _array(manifest_object.get("calculations"), "manifest.calculations"),
        "calculation",
        "manifest.calculations",
    )
    if set(model_calculations) != set(manifest_calculations):
        model_only = sorted(set(model_calculations) - set(manifest_calculations))
        manifest_only = sorted(set(manifest_calculations) - set(model_calculations))
        raise GenerationError(
            "model と manifest の calculation 集合が一致しない: "
            f"modelのみ={model_only!r}, manifestのみ={manifest_only!r}"
        )

    raw_display_rules = _array(model_object.get("displayRules"), "displayRules")
    display_rules = _index_by(raw_display_rules, "id", "displayRules")
    calculations: list[dict[str, object]] = []
    for calculation_id, declaration in model_calculations.items():
        manifest_calculation = manifest_calculations[calculation_id]
        source = _object(manifest_calculation.get("source"), "calculation.source")
        source_id = _string(source.get("provenance"), "source.provenance")
        _validate_authority(source_id, schemas, root)
        artifacts = _index_by(
            _array(manifest_calculation.get("generated"), "calculation.generated"),
            "generatedId",
            "calculation.generated",
        )
        selected_rules = _selected_display_rules(declaration, display_rules)
        targets = [
            _build_target(
                declaration,
                selected_rules,
                _object(target, "calculation.directTargets[]"),
                artifacts,
                source_id,
            )
            for target in _array(
                manifest_calculation.get("directTargets"),
                "calculation.directTargets",
            )
        ]
        calculations.append(
            {
                "calculationId": calculation_id,
                "sourceId": source_id,
                "declaration": copy.deepcopy(declaration),
                "targets": targets,
            }
        )

    intermediate = {
        "schemaVersion": _SCHEMA_VERSION,
        "generatorVersion": GENERATOR_VERSION,
        "displayRules": copy.deepcopy(raw_display_rules),
        "calculations": calculations,
    }
    validate_intermediate_representation(intermediate, schemas)
    return intermediate


def validate_intermediate_representation(
    intermediate: object,
    schemas: SourceSchemas,
) -> None:
    """中間表現を exact-set の schema に対して検証する。

    Args:
        intermediate: 検証する中間表現。
        schemas: 外部参照する既存 schema 群。

    Raises:
        GenerationError: 未知キー、欠落キー、型不一致などがある場合。
    """
    documents = schemas.documents()
    documents["intermediate.json"] = INTERMEDIATE_REPRESENTATION_SCHEMA
    _validate_instance(
        intermediate,
        INTERMEDIATE_REPRESENTATION_SCHEMA,
        "intermediate.json",
        documents,
        "$",
    )


def _default_root() -> Path:
    """モジュール位置からリポジトリルートを返す。"""
    return Path(__file__).resolve().parents[4]


def _resolve_path(root: Path, path: Path) -> Path:
    """相対パスをリポジトリルート基準で解決する。"""
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _load_schema(path: Path, label: str) -> Mapping[str, object]:
    """Schema ファイルを object として読み込む。"""
    return _object(_read_json(path), label)


def _build_parser() -> argparse.ArgumentParser:
    """生成専用 CLI の引数パーサを作る。"""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_default_root())
    parser.add_argument("--model", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--model-schema",
        type=Path,
        default=Path("backend/domain/model.schema.json"),
    )
    parser.add_argument(
        "--manifest-schema",
        type=Path,
        default=Path("backend/domain/manifest.schema.json"),
    )
    parser.add_argument(
        "--vocabulary-schema",
        type=Path,
        default=Path("backend/domain/vocabulary.schema.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """中間表現を標準出力へ生成し、生成成否だけを exit code で返す。

    Args:
        argv: CLI 引数。`None` ならプロセス引数を使う。

    Returns:
        生成成功は 0、生成失敗は 1。適合・不適合・判定不能の契約ではない。
    """
    try:
        arguments = _build_parser().parse_args(argv)
        root = arguments.root.resolve()
        if not root.is_dir():
            raise GenerationError(f"リポジトリルートを読めない: {root}")
        schemas = SourceSchemas(
            model=_load_schema(
                _resolve_path(root, arguments.model_schema),
                "model schema",
            ),
            manifest=_load_schema(
                _resolve_path(root, arguments.manifest_schema),
                "manifest schema",
            ),
            vocabulary=_load_schema(
                _resolve_path(root, arguments.vocabulary_schema),
                "vocabulary schema",
            ),
        )
        model = (
            _read_json(_resolve_path(root, arguments.model))
            if arguments.model is not None
            else None
        )
        manifest = (
            _read_json(_resolve_path(root, arguments.manifest))
            if arguments.manifest is not None
            else None
        )
        intermediate = generate_intermediate_representation(
            model,
            manifest,
            schemas,
            root,
        )
        sys.stdout.write(_canonical_json(intermediate))
    except GenerationError as error:
        print(f"生成失敗: {error}", file=sys.stderr)
        return EXIT_GENERATION_FAILED
    return EXIT_GENERATED


def typed_expression(
    node: Mapping[str, Any],
    language: str,
    fields: Mapping[str, Any],
    items: Mapping[str, Any] | None = None,
) -> str:
    """検査済み閉式を直接実行式へ下げ、runtime interpreterを作らない。"""
    js = language == "typescript"
    op = node["op"]
    if op == "literal":
        value = node["value"]
        if type(value) is int:
            return f"{value}n" if js else str(value)
        return json.dumps(value, ensure_ascii=False) if js else repr(value)
    if op == "ref":
        path = str(node["path"])
        owner = "item" if path.startswith("item.") else "event"
        key = path.removeprefix("item.") if owner == "item" else path
        descriptor = (items or {})[key] if owner == "item" else fields[key]
        args = [
            descriptor["type"],
            descriptor["nullable"],
            str(descriptor["minimum"]) if "minimum" in descriptor else None,
            str(descriptor["maximum"]) if "maximum" in descriptor else None,
            descriptor.get("enum"),
        ]
        arguments = ", ".join(
            json.dumps(v, ensure_ascii=False) if js else repr(v) for v in args
        )
        value = (
            f"_checked_ref({owner}, {json.dumps(key, ensure_ascii=False)}, {arguments})"
        )
        return f"_n({value})" if descriptor["type"] == "integer" else value
    if op in {"and", "or", "add"}:
        token = {
            "and": " && " if js else " and ",
            "or": " || " if js else " or ",
            "add": " + ",
        }[str(op)]
        return (
            "("
            + token.join(
                typed_expression(n, language, fields, items) for n in node["args"]
            )
            + ")"
        )
    if op in {"eq", "ne"}:
        token = (
            (" === " if op == "eq" else " !== ")
            if js
            else (" == " if op == "eq" else " != ")
        )
        return (
            "("
            + typed_expression(node["left"], language, fields, items)
            + token
            + typed_expression(node["right"], language, fields, items)
            + ")"
        )
    if op == "lookup":
        value = typed_expression(node["value"], language, fields, items)
        pairs = [(str(k), v) for k, v in node["cases"].items()]
        if js:
            literal = (
                "{"
                + ",".join(json.dumps(k) + ":" + str(v) + "n" for k, v in pairs)
                + "}"
            )
            return f"_lookup({literal}, {value})"
        return f"{dict(pairs)!r}[{value}]"
    raise GenerationError("未対応のtyped式")


def generate_primitive_bundle(
    common_model: Mapping[str, Any], consumer_model: Mapping[str, Any]
) -> dict[str, str]:
    """D-1共通式とhash付き参照だけから実行可能な三言語targetを生成する。

    Args:
        common_model: 唯一の人手式を持つ共通model。
        consumer_model: 同じprimitive ID/type/hashだけを参照するstats model。

    Returns:
        固定された生成先と生成内容。

    Raises:
        GenerationError: 未知/型違い/循環参照や宣言違反がある場合。
    """
    from pitchlog.domaingen.backends import python as py_backend
    from pitchlog.domaingen.backends import sql as sql_backend
    from pitchlog.domaingen.backends import typescript as ts_backend
    from pitchlog.domaingen.formatter import integer_target
    from pitchlog.domaingen.pregen_checks import validate_typed_program

    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError

        schema_path = Path(__file__).resolve().parents[3] / "domain/model.schema.json"
        validator = Draft202012Validator(json.loads(schema_path.read_text()))
        for document in (common_model, consumer_model):
            try:
                validator.validate(document)
            except ValidationError as error:
                raise ValueError("typed modelのschema違反") from error
        for model in (common_model, consumer_model):
            if set(model) != {"schemaVersion", "calculations", "displayRules"}:
                raise ValueError("modelの生成入力は閉集合が必要")
            if model["schemaVersion"] != 1 or model["displayRules"] != []:
                raise ValueError("typed modelの版/表示宣言が不正")
            if (
                not isinstance(model["calculations"], list)
                or len(model["calculations"]) != 1
            ):
                raise ValueError("typed modelは単一計算が必要")
            if set(model["calculations"][0]) != {"calculationId", "typedProgram"}:
                raise ValueError("計算宣言の閉キーが不正")
        calculation = common_model["calculations"][0]
        program = calculation["typedProgram"]
        validate_typed_program(program)
        reference = consumer_model["calculations"][0]["typedProgram"]
        if set(reference) != {
            "kind",
            "version",
            "commonCalculationId",
            "commonModelHash",
            "refs",
        }:
            raise ValueError("consumerはID/hash/type参照だけが必要")
        source_hash = _canonical_hash(common_model)
        if (
            reference["kind"] != "primitive-refs"
            or reference["version"] != 1
            or reference["commonCalculationId"] != calculation["calculationId"]
            or reference["commonModelHash"] != source_hash
            or consumer_model["calculations"][0]["calculationId"]
            == calculation["calculationId"]
        ):
            raise ValueError("未知/循環/版不一致の共通model参照")
        expected = [{"id": m["id"], "type": "integer"} for m in program["metrics"]]
        if reference["refs"] != expected:
            raise ValueError("primitive ID/型/順序の参照不一致")
        py = py_backend.generate_typed_facts(program, source_hash)
        ts = ts_backend.generate_typed_facts(program, source_hash)
        queries = sql_backend.generate_typed_queries(program, source_hash)
        raw_bundle = {
            "backend/src/pitchlog/stats/generated/facts.py": py,
            "frontend/src/lib/generated/statsPrimitives.ts": ts,
            "backend/src/pitchlog/exports/generated/play_primitives.sql": queries[
                "window"
            ],
            "backend/src/pitchlog/stats/generated/stats.sql": queries["grouped"],
            "backend/src/pitchlog/stats/generated/receiver.py": py_backend.generate_typed_receiver(  # noqa: E501 — 生成targetのliteral
                program, source_hash
            ),
            "backend/src/pitchlog/stats/generated/formatter.py": integer_target(
                "python", source_hash
            ),
            "frontend/src/lib/generated/statsFormatter.ts": integer_target(
                "typescript", source_hash
            ),
        }
        return {
            path: _format_typed_target(path, content)
            for path, content in raw_bundle.items()
        }  # noqa: E501 — 生成targetのliteral
    except (KeyError, TypeError, ValueError) as error:
        raise GenerationError(f"typed primitiveを生成できない: {error}") from error


def _format_typed_target(path: str, content: str) -> str:
    """固定toolchainで生成bytesを整形し、日本語docstringを補う。"""
    import ast
    import subprocess

    root = Path(__file__).resolve().parents[4]
    if path.endswith(".py"):
        tree = ast.parse(content)
        if ast.get_docstring(tree) is None:
            tree.body.insert(
                0, ast.Expr(value=ast.Constant("自動生成された整数表示・型検証。"))
            )
        imports = [
            node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        tree.body = [node for node in tree.body if node not in imports]
        imports.sort(
            key=lambda node: (not isinstance(node, ast.Import), ast.unparse(node))
        )
        tree.body[1:1] = imports
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if ast.get_docstring(node) is None:
                    node.body.insert(
                        0,
                        ast.Expr(
                            value=ast.Constant("生成された型検証・有限寄与処理。")
                        ),
                    )  # noqa: E501 — 生成targetのliteral
        prefix = content.splitlines()[0] + "\n" if content.startswith("#") else ""
        raw = prefix + ast.unparse(ast.fix_missing_locations(tree)) + "\n"
        command = [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--stdin-filename",
            str(root / path),
            "-",
        ]  # noqa: E501 — 生成targetのliteral
    elif path.endswith(".ts"):
        raw = content
        command = [
            str(root / "frontend/node_modules/.bin/prettier"),
            "--stdin-filepath",
            str(root / path),
        ]  # noqa: E501 — 生成targetのliteral
    else:
        return content
    process = subprocess.run(
        command, input=raw, text=True, capture_output=True, check=True
    )  # noqa: E501 — 生成targetのliteral
    return process.stdout


if __name__ == "__main__":
    raise SystemExit(main())
