"""語彙manifestのschema・版・内容hash・参照解決を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
VOCABULARY_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_vocabulary_manifest.py"
MANIFEST_PATH = (
    REPOSITORY_ROOT / "contracts/vocabulary/vocabulary_manifest_v1.json"
)
SEED_PATH = REPOSITORY_ROOT / "contracts/vocabulary/input_vocabulary_v1.json"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_CHECKER_PATH)
schema_checker = _load_module("check_input_axes_descriptor", DESCRIPTOR_CHECKER_PATH)
checker = _load_module("check_vocabulary_manifest", VOCABULARY_CHECKER_PATH)


def _load_object(path: Path) -> dict[str, Any]:
    """重複キーを拒否してJSON objectを読み込む。"""
    value = schema_checker.load_json(path, path.name)
    assert isinstance(value, dict)
    return value


def _manifest() -> dict[str, Any]:
    """共有語彙manifestを返す。"""
    return _load_object(MANIFEST_PATH)


def _seed() -> dict[str, Any]:
    """入力語彙シードを返す。"""
    return _load_object(SEED_PATH)


def _validate(
    manifest: dict[str, Any],
    *,
    seed_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, frozenset[str]]:
    """テスト値を共有manifest検査器へ渡す。"""
    return checker.validate_manifest(
        REPOSITORY_ROOT,
        manifest_value=manifest,
        seed_values_by_path=seed_overrides,
    )


def _reverse_object_keys(value: object) -> object:
    """値を変えず全objectのキー挿入順だけを逆転する。"""
    if isinstance(value, dict):
        return {
            key: _reverse_object_keys(value[key])
            for key in reversed(tuple(value))
        }
    if isinstance(value, list):
        return [_reverse_object_keys(item) for item in value]
    return value


def test_repository_manifest_resolves_all_seed_ids() -> None:
    """D-12の宣言先から実シード116 IDを一意に解決する。"""
    resolved = checker.validate_manifest(REPOSITORY_ROOT)

    assert set(resolved) == {"input_vocabulary"}
    assert len(resolved["input_vocabulary"]) == 116
    assert "batting-result.single" in resolved["input_vocabulary"]


def test_manifest_unknown_field_fails() -> None:
    """共有manifestの未知フィールドを拒否する。"""
    manifest = _manifest()
    manifest["unknownField"] = True

    with pytest.raises(checker.VocabularyManifestError, match="unknownField"):
        _validate(manifest)


def test_duplicate_vocabulary_id_fails() -> None:
    """seeds内のvocabularyId重複を拒否する。"""
    manifest = _manifest()
    duplicate = copy.deepcopy(manifest["seeds"][0])
    duplicate["path"] = "contracts/vocabulary/another_v1.json"
    duplicate["version"] = "another_v1"
    manifest["seeds"].append(duplicate)

    with pytest.raises(checker.VocabularyManifestError, match="vocabularyIdが重複"):
        _validate(manifest)


def test_duplicate_seed_path_fails() -> None:
    """seeds内のpath重複を拒否する。"""
    manifest = _manifest()
    duplicate = copy.deepcopy(manifest["seeds"][0])
    duplicate["vocabularyId"] = "another"
    manifest["seeds"].append(duplicate)

    with pytest.raises(checker.VocabularyManifestError, match="pathが重複"):
        _validate(manifest)


def test_seed_path_outside_vocabulary_directory_fails() -> None:
    """contracts/vocabulary外のseed pathを拒否する。"""
    manifest = _manifest()
    manifest["seeds"][0]["path"] = "contracts/state-transition/input_vocabulary_v1.json"

    with pytest.raises(checker.VocabularyManifestError, match="path"):
        _validate(manifest)


def test_missing_seed_path_fails() -> None:
    """実在しないseed pathを拒否する。"""
    manifest = _manifest()
    declaration = manifest["seeds"][0]
    declaration["vocabularyId"] = "missing"
    declaration["path"] = "contracts/vocabulary/missing_v1.json"
    declaration["version"] = "missing_v1"

    with pytest.raises(checker.VocabularyManifestError, match="実在しない"):
        _validate(manifest)


def test_filename_version_mismatch_fails() -> None:
    """ファイル名と宣言versionの不一致を拒否する。"""
    manifest = _manifest()
    declaration = manifest["seeds"][0]
    new_path = "contracts/vocabulary/input_vocabulary_v2.json"
    declaration["path"] = new_path

    with pytest.raises(checker.VocabularyManifestError, match="宣言version"):
        _validate(manifest, seed_overrides={new_path: _seed()})


def test_seed_internal_version_mismatch_fails() -> None:
    """ファイル名とseed内部versionの不一致を拒否する。"""
    manifest = _manifest()
    seed = _seed()
    seed["version"] = "input_vocabulary_v2"

    with pytest.raises(checker.VocabularyManifestError, match="ファイル内version"):
        _validate(
            manifest,
            seed_overrides={manifest["seeds"][0]["path"]: seed},
        )


def test_declared_version_mismatch_fails() -> None:
    """ファイル名・seed内部値と宣言versionの不一致を拒否する。"""
    manifest = _manifest()
    manifest["seeds"][0]["version"] = "input_vocabulary_v2"

    with pytest.raises(checker.VocabularyManifestError, match="宣言version"):
        _validate(manifest)


def test_declared_schema_version_mismatch_fails() -> None:
    """宣言schemaVersionとseed内部値の不一致を拒否する。"""
    manifest = _manifest()
    manifest["seeds"][0]["schemaVersion"] = 2

    with pytest.raises(checker.VocabularyManifestError, match="schemaVersion"):
        _validate(manifest)


def test_one_character_seed_change_fails_content_hash() -> None:
    """初期表示名を1文字変えたseedをcontentHash不一致で拒否する。"""
    manifest = _manifest()
    seed = _seed()
    seed["axes"][0]["entries"][0]["initialDisplayName"] += "差"

    with pytest.raises(checker.VocabularyManifestError, match="contentHash"):
        _validate(
            manifest,
            seed_overrides={manifest["seeds"][0]["path"]: seed},
        )


def test_whitespace_and_object_key_order_do_not_change_content_hash() -> None:
    """空白・改行・objectキー順の表現差をJCSで同一hashへ正規化する。"""
    seed = _seed()
    pretty = json.loads(json.dumps(seed, ensure_ascii=False, indent=4))
    compact = json.loads(
        json.dumps(seed, ensure_ascii=False, separators=(",", ":"))
    )
    reordered = _reverse_object_keys(seed)

    expected = checker.compute_content_hash(seed)
    assert checker.compute_content_hash(pretty) == expected
    assert checker.compute_content_hash(compact) == expected
    assert checker.compute_content_hash(reordered) == expected


@pytest.mark.parametrize(
    "mutate",
    [
        lambda seed: seed["axes"][0]["entries"][0].__setitem__(
            "id", "batting-result.changed"
        ),
        lambda seed: seed["axes"][0].__setitem__(
            "sourceRef", seed["axes"][0]["sourceRef"] + " changed"
        ),
        lambda seed: seed["axes"][0]["entries"][0].__setitem__(
            "initialDisplayName", "変更表示名"
        ),
        lambda seed: seed["axes"][0]["entries"][0].__setitem__(
            "classification", "changed"
        ),
    ],
    ids=("id", "meaning", "initial-display-name", "classification"),
)
def test_semantic_content_change_changes_hash(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """ID・意味・初期表示名・分類の差がcontentHashを変える。"""
    seed = _seed()
    changed = copy.deepcopy(seed)
    mutate(changed)

    assert checker.compute_content_hash(changed) != checker.compute_content_hash(seed)
