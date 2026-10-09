"""語彙シード共有manifestのschema・版・内容hash・参照を検証する。"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from check_input_axes_descriptor import (
    DescriptorCheckError,
    _validate_instance,
    canonicalize_json,
    load_json,
)

MANIFEST_PATH = PurePosixPath(
    "contracts/vocabulary/vocabulary_manifest_v1.json"
)
MANIFEST_SCHEMA_PATH = PurePosixPath(
    "contracts/vocabulary/vocabulary_manifest_schema_v1.json"
)
SEED_SCHEMA_PATH = PurePosixPath(
    "contracts/vocabulary/vocabulary_seed_schema_v1.json"
)
I_JSON_SAFE_INTEGER_LIMIT = (1 << 53) - 1
VERSIONED_FILENAME_PATTERN = re.compile(
    r"^(?P<vocabulary_id>[a-z]+(?:_[a-z]+)*)_v(?P<version>[1-9][0-9]*)\.json$"
)


class VocabularyManifestError(ValueError):
    """語彙manifestまたは参照先シードの契約違反を表す。"""


def _object(value: object, label: str) -> dict[str, Any]:
    """JSON値を文字列キーのobjectとして返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise VocabularyManifestError(f"{label}がobjectでない")
    return value


def _string(value: object, label: str) -> str:
    """JSON値を空でない文字列として返す。"""
    if not isinstance(value, str) or not value:
        raise VocabularyManifestError(f"{label}が空でない文字列でない")
    return value


def compute_content_hash(seed: object) -> str:
    """語彙シードJSON文書全体のRFC 8785 + SHA-256 hashを返す。

    Args:
        seed: schema検証と重複キー拒否を通過した語彙シード。

    Returns:
        `sha256:`接頭辞付きの小文字16進SHA-256。
    """
    canonical = canonicalize_json(seed, I_JSON_SAFE_INTEGER_LIMIT)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _validate_schema(
    value: Mapping[str, Any], schema: Mapping[str, Any], label: str
) -> None:
    """既存の汎用JSON Schema検証器で値を検証する。"""
    try:
        _validate_instance(value, schema, schema, label)
    except DescriptorCheckError as error:
        raise VocabularyManifestError(str(error)) from error


def _unique_fields(manifest_schema: Mapping[str, Any]) -> tuple[str, ...]:
    """manifest schemaが宣言する一意キーを返す。"""
    value = manifest_schema.get("x-pitchlog-uniqueBy")
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(field, str) and field for field in value)
        or len(value) != len(set(value))
    ):
        raise VocabularyManifestError("manifest schemaの一意キー宣言が不正")
    return tuple(value)


def _seed_location_rule(manifest_schema: Mapping[str, Any]) -> dict[str, str]:
    """manifest schemaが宣言する配置・版bindingを返す。"""
    raw = _object(
        manifest_schema.get("x-pitchlog-seed-location"),
        "manifest schemaのseed配置宣言",
    )
    required = {
        "root",
        "pathField",
        "vocabularyIdField",
        "versionField",
        "schemaVersionField",
    }
    if set(raw) != required:
        raise VocabularyManifestError("manifest schemaのseed配置宣言が閉じていない")
    return {key: _string(raw[key], f"seed配置宣言.{key}") for key in required}


def _content_hash_rule(manifest_schema: Mapping[str, Any]) -> dict[str, str]:
    """manifest schemaが宣言する内容hash規則を返す。"""
    raw = _object(
        manifest_schema.get("x-pitchlog-content-hash"),
        "manifest schemaの内容hash宣言",
    )
    expected_fields = {
        "field",
        "algorithm",
        "canonicalization",
        "encoding",
        "source",
    }
    if set(raw) != expected_fields:
        raise VocabularyManifestError("manifest schemaの内容hash宣言が閉じていない")
    rule = {key: _string(raw[key], f"内容hash宣言.{key}") for key in expected_fields}
    supported = {
        "algorithm": "SHA-256",
        "canonicalization": "RFC8785",
        "encoding": "UTF-8",
        "source": "entire-seed-document",
    }
    for field, expected in supported.items():
        if rule[field] != expected:
            raise VocabularyManifestError(
                f"未対応の内容hash規則: {field}={rule[field]!r}"
            )
    return rule


def _resolved_path(root: Path, relative: PurePosixPath) -> Path:
    """リポジトリ相対パスをroot配下の実パスへ解決する。"""
    if relative.is_absolute() or ".." in relative.parts:
        raise VocabularyManifestError(f"リポジトリ外を指すpath: {relative}")
    return root.joinpath(*relative.parts)


def _seed_ids(seed: Mapping[str, Any], seed_schema: Mapping[str, Any]) -> frozenset[str]:
    """seed schemaの一意性宣言に従い全語彙IDを返す。"""
    rule = _object(
        seed_schema.get("x-pitchlog-global-entry-id-uniqueness"),
        "seed schemaの大域ID一意性宣言",
    )
    axes_field = _string(rule.get("axesCollection"), "大域ID宣言.axesCollection")
    entries_field = _string(
        rule.get("entriesCollection"), "大域ID宣言.entriesCollection"
    )
    id_field = _string(rule.get("idField"), "大域ID宣言.idField")
    maximum = rule.get("maximumOccurrences")
    if maximum != 1:
        raise VocabularyManifestError("seed schemaの大域ID最大出現数が1でない")

    ids: list[str] = []
    for axis in seed[axes_field]:
        for entry in axis[entries_field]:
            ids.append(_string(entry[id_field], f"語彙entry.{id_field}"))
    if len(ids) != len(set(ids)):
        raise VocabularyManifestError("語彙シード内でIDが重複している")
    return frozenset(ids)


def validate_manifest(
    root: Path,
    *,
    manifest_value: Mapping[str, Any] | None = None,
    seed_values_by_path: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, frozenset[str]]:
    """共有manifestと全参照先シードを検証しID集合を返す。

    Args:
        root: リポジトリルート。
        manifest_value: テスト用のmanifest差し替え。省略時は実資産を読む。
        seed_values_by_path: テスト用のシード差し替え。キーはリポジトリ相対path。

    Returns:
        vocabularyIdから当該シードの語彙ID集合への写像。

    Raises:
        VocabularyManifestError: schema・配置・版・hash・一意性が不正な場合。
    """
    try:
        manifest_schema = _object(
            load_json(
                _resolved_path(root, MANIFEST_SCHEMA_PATH), "語彙manifest schema"
            ),
            "語彙manifest schema",
        )
        seed_schema = _object(
            load_json(_resolved_path(root, SEED_SCHEMA_PATH), "語彙シードschema"),
            "語彙シードschema",
        )
        manifest = (
            _object(
                load_json(_resolved_path(root, MANIFEST_PATH), "語彙manifest"),
                "語彙manifest",
            )
            if manifest_value is None
            else dict(manifest_value)
        )
    except DescriptorCheckError as error:
        raise VocabularyManifestError(str(error)) from error

    _validate_schema(manifest, manifest_schema, "$.manifest")
    if manifest["version"] != MANIFEST_PATH.stem:
        raise VocabularyManifestError("manifestのファイル名と内部versionが一致しない")

    unique_fields = _unique_fields(manifest_schema)
    location = _seed_location_rule(manifest_schema)
    hash_rule = _content_hash_rule(manifest_schema)
    seed_root = PurePosixPath(location["root"])
    declarations = manifest["seeds"]
    for field in unique_fields:
        values = [declaration[field] for declaration in declarations]
        if len(values) != len(set(values)):
            raise VocabularyManifestError(f"manifestの{field}が重複している")

    resolved: dict[str, frozenset[str]] = {}
    overrides = seed_values_by_path or {}
    for index, declaration in enumerate(declarations):
        label = f"seeds[{index}]"
        path_text = _string(declaration[location["pathField"]], f"{label}.path")
        relative = PurePosixPath(path_text)
        if relative.parent != seed_root:
            raise VocabularyManifestError(
                f"語彙シードpathが{seed_root.as_posix()}/直下でない: {path_text}"
            )
        filename_match = VERSIONED_FILENAME_PATTERN.fullmatch(relative.name)
        if filename_match is None:
            raise VocabularyManifestError(f"語彙シードのファイル名が不正: {path_text}")

        if path_text in overrides:
            seed = dict(overrides[path_text])
        else:
            seed_path = _resolved_path(root, relative)
            if not seed_path.is_file():
                raise VocabularyManifestError(f"語彙シードpathが実在しない: {path_text}")
            try:
                seed = _object(load_json(seed_path, "語彙シード"), "語彙シード")
            except DescriptorCheckError as error:
                raise VocabularyManifestError(str(error)) from error

        _validate_schema(seed, seed_schema, f"$.{path_text}")
        vocabulary_id_field = location["vocabularyIdField"]
        version_field = location["versionField"]
        schema_version_field = location["schemaVersionField"]
        filename_vocabulary_id = filename_match.group("vocabulary_id")
        filename_version = relative.stem
        if declaration[vocabulary_id_field] != filename_vocabulary_id:
            raise VocabularyManifestError(
                f"{label}のvocabularyIdとファイル名が一致しない"
            )
        if seed[vocabulary_id_field] != filename_vocabulary_id:
            raise VocabularyManifestError(
                f"{label}のファイル内vocabularyIdとファイル名が一致しない"
            )
        if declaration[version_field] != filename_version:
            raise VocabularyManifestError(f"{label}の宣言versionとファイル名が一致しない")
        if seed[version_field] != filename_version:
            raise VocabularyManifestError(
                f"{label}のファイル内versionとファイル名が一致しない"
            )
        if declaration[schema_version_field] != seed[schema_version_field]:
            raise VocabularyManifestError(
                f"{label}の宣言schemaVersionとファイル内値が一致しない"
            )

        expected_hash = declaration[hash_rule["field"]]
        actual_hash = compute_content_hash(seed)
        if expected_hash != actual_hash:
            raise VocabularyManifestError(
                f"{label}のcontentHashが語彙シード実体と一致しない: "
                f"期待={expected_hash}, 実際={actual_hash}"
            )
        vocabulary_id = declaration[vocabulary_id_field]
        resolved[vocabulary_id] = _seed_ids(seed, seed_schema)
    return resolved


def main(argv: list[str] | None = None) -> int:
    """語彙manifest検査CLIを実行する。"""
    parser = argparse.ArgumentParser(
        description="語彙シード共有manifestのschema・版・内容hashを検証する"
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        resolved = validate_manifest(args.root.resolve())
    except VocabularyManifestError as error:
        print(f"vocabulary-manifest: ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "vocabulary-manifest: OK "
        f"(seeds={len(resolved)}, ids={sum(len(ids) for ids in resolved.values())})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
