"""文書検査プロファイルとレジストリのデータ契約を検証する。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELATIONS_DIR = REPOSITORY_ROOT / "scripts" / "design_relations"
PROFILES_DIR = RELATIONS_DIR / "profiles"
SCHEMAS_DIR = RELATIONS_DIR / "schemas"
INVARIANTS_DIR = RELATIONS_DIR / "invariants"
PROFILE_PATH = PROFILES_DIR / "sync-protocol.json"
REGISTRY_PATH = PROFILES_DIR / "registry.json"
INVARIANTS_PATH = INVARIANTS_DIR / "sync-protocol.json"
DEFECTS_PATH = RELATIONS_DIR / "defects.json"
PROPAGATION_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_design_propagation.py"
COVERAGE_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_doc_coverage.py"
PROFILE_LOADER_SCRIPT = REPOSITORY_ROOT / "scripts" / "doc_check_profile.py"

ALL_CHECK_IDS = {
    "manifest-consistency",
    "element-coverage",
    "enum-propagation",
    "condition-key",
    "route-matrix",
    "scope-declaration",
    "order-use",
    "citation-format",
    "noncanonical-reference",
    "link-target",
    "emphasis",
    "draft-metadata",
    "attribution",
    "ledger",
    "forbidden-structure",
    "cross-consistency",
    "collection-consistency",
    "baseline-digest",
    "unique-owner",
    "reference-class",
    "attribution-destination",
    "attribution-direct",
}
GATING_KEYS = (
    "required_checks",
    "not_applicable",
    "invariant_kinds",
    "structure_extractors",
    "collection_sets",
    "assets",
    "direct_requirements",
    "reference_policy",
)
PROFILE_REQUIRED_KEYS = {
    "schema_version",
    "name",
    "document",
    "manifest",
    "defects",
    "requirements",
    "universe",
    "section_id_grammar",
    "preamble",
    "link_base_dir",
    "noncanonical_scan_start",
    "noncanonical_path_pattern",
    "declaration_table",
    "exclusion_vocabulary",
    "citation",
    "attribution",
    "defect_id_namespaces",
    "invariant_kinds",
    "required_checks",
    "not_applicable",
    "assets",
    "structure_extractors",
    "collection_sets",
    "reference_policy",
}
SCHEMA_KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "items",
    "minLength",
    "minItems",
    "pattern",
    "uniqueItems",
}


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.pathの変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    """JSONオブジェクトをUTF-8で読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _gating_digest(profile_data: dict[str, Any]) -> str:
    """ゲート節をcanonical JSON化してSHA-256を返す。"""
    gating = {key: profile_data[key] for key in GATING_KEYS if key in profile_data}
    canonical = json.dumps(
        gating,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_schema_subset(schema: dict[str, Any], *, root: bool = False) -> None:
    """最小検証器が扱うキーワードだけでスキーマが構成されることを確認する。"""
    allowed = SCHEMA_KEYWORDS | ({"schema_version"} if root else set())
    assert set(schema) <= allowed
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False
    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    for child in properties.values():
        assert isinstance(child, dict)
        _assert_schema_subset(child)
    items = schema.get("items")
    if items is not None:
        assert isinstance(items, dict)
        _assert_schema_subset(items)


def _write_json(path: Path, value: Any) -> None:
    """テスト用JSONを読みやすい形式で書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_profile_tree(tmp_path: Path) -> Path:
    """本番スキーマとプロファイルを一時リポジトリへ複製する。"""
    root = tmp_path / "repository"
    relations_dir = root / "scripts" / "design_relations"
    shutil.copytree(SCHEMAS_DIR, relations_dir / "schemas")
    shutil.copytree(PROFILES_DIR, relations_dir / "profiles")
    shutil.copytree(INVARIANTS_DIR, relations_dir / "invariants")
    return root


def _temporary_profile_path(root: Path) -> Path:
    """一時リポジトリの同期プロファイルパスを返す。"""
    return root / "scripts/design_relations/profiles/sync-protocol.json"


def _temporary_registry_path(root: Path) -> Path:
    """一時リポジトリのレジストリパスを返す。"""
    return root / "scripts/design_relations/profiles/registry.json"


propagation = _load_module("profile_propagation_under_test", PROPAGATION_SCRIPT)
coverage = _load_module("profile_coverage_under_test", COVERAGE_SCRIPT)
profile_loader = _load_module("doc_check_profile_under_test", PROFILE_LOADER_SCRIPT)
profile = _load_json(PROFILE_PATH)
registry = _load_json(REGISTRY_PATH)


def test_profile_paths_match_current_module_constants() -> None:
    """移送したファイルパスが両検査の現行定数と一致する。"""
    assert profile["document"] == propagation.DEFAULT_DOCUMENT.as_posix()
    assert profile["document"] == coverage.DEFAULT_DOCUMENT.as_posix()
    assert profile["manifest"] == propagation.DEFAULT_MANIFEST.as_posix()
    assert profile["defects"] == propagation.DEFAULT_DEFECTS.as_posix()
    assert profile["requirements"] == coverage.DEFAULT_REQUIREMENTS.as_posix()
    assert profile["universe"] == coverage.DEFAULT_UNIVERSE.as_posix()
    assert (
        profile["noncanonical_path_pattern"]
        == propagation.NONCANONICAL_PATH_RE.pattern
    )


def test_profile_attribution_matches_current_module_constants() -> None:
    """帰属表と台帳の契約が現行定数と一致する。"""
    attribution = profile["attribution"]
    assert set(attribution["kinds"]) == set(coverage.ASSIGNMENT_KINDS)
    assert attribution["assignment_header"] == list(coverage.ASSIGNMENT_HEADER)
    assert attribution["ledger_header"] == list(coverage.LEDGER_HEADER)
    assert set(attribution["reference_kinds"]) == set(coverage.REFERENCE_KINDS)
    assert set(attribution["ledger_verdicts"]) == set(coverage.LEDGER_VERDICTS)
    assert attribution["ledger_section"] == coverage.LEDGER_SECTION_ID


def test_required_checks_match_current_module_constants() -> None:
    """同期プロファイルの必須検査が現行14検査と一致する。"""
    expected = set(propagation.CHECK_IDS) | set(coverage.COVERAGE_CHECK_IDS)
    assert set(profile["required_checks"]) == expected
    assert len(profile["required_checks"]) == 14


def test_nonconstant_profile_values_match_current_source() -> None:
    """外部化した値が関数単体呼び出し用の既定値と一致する。"""
    source = PROPAGATION_SCRIPT.read_text(encoding="utf-8")
    assert profile["section_id_grammar"] == propagation.DEFAULT_SECTION_ID_GRAMMAR
    assert profile["preamble"] == propagation.DEFAULT_PREAMBLE
    assert 'text.split("\\n## ", 1)[0]' in source
    assert profile["link_base_dir"] == "docs/design"
    assert 'root / "docs" / "design"' in source
    assert (
        profile["noncanonical_scan_start"]
        == propagation.DEFAULT_NONCANONICAL_SCAN_START
    )

    declaration = profile["declaration_table"]
    assert declaration == {
        "section": "2-5",
        "row_prefix": "| **R-",
        "column_count": 6,
        "columns": [
            "関係 ID",
            "正本の表",
            "伝播先の表",
            "比較キー",
            "正本の要素全集合",
            "伝播先ごとの期待部分集合",
        ],
    }
    assert declaration["section"] == propagation.DEFAULT_DECLARATION_SECTION
    assert declaration["row_prefix"] == propagation.DEFAULT_DECLARATION_ROW_PREFIX
    assert (
        declaration["column_count"]
        == propagation.DEFAULT_DECLARATION_COLUMN_COUNT
    )

    assert profile["exclusion_vocabulary"] == [
        "対象外",
        "対象にならない",
        "含めない",
    ]
    assert profile["exclusion_vocabulary"] == list(
        propagation.DEFAULT_EXCLUSION_VOCABULARY
    )
    citation = profile["citation"]
    assert citation == {
        "legacy_prefixes": ["docs/legacy/", "../legacy/"],
        "legacy_infix": "/docs/legacy/",
        "inherit_bare_line_from_same_line": True,
    }
    assert citation["legacy_prefixes"] == list(propagation.DEFAULT_LEGACY_PREFIXES)
    assert citation["legacy_infix"] == propagation.DEFAULT_LEGACY_INFIX


def test_defect_namespaces_match_defects_oracle() -> None:
    """欠陥oracleの全名前空間と機械検査名前空間を突合する。"""
    defects = _load_json(DEFECTS_PATH)
    entries = {
        identifier: value
        for identifier, value in defects.items()
        if not identifier.startswith("_")
    }
    all_namespaces = {identifier.split("-", 1)[0] for identifier in entries}
    machine_namespaces = {
        identifier.split("-", 1)[0]
        for identifier, value in entries.items()
        if value["detection"] == "machine"
    }
    assert set(profile["defect_id_namespaces"]["all"]) == all_namespaces
    assert set(profile["defect_id_namespaces"]["machine"]) == machine_namespaces


def test_checks_are_a_complete_disjoint_partition() -> None:
    """全22検査を必須または適用外理由へ重複なく分割する。"""
    required = set(profile["required_checks"])
    not_applicable = set(profile["not_applicable"])
    assert required | not_applicable == ALL_CHECK_IDS
    assert required.isdisjoint(not_applicable)
    assert all(reason.strip() for reason in profile["not_applicable"].values())


def test_registry_matches_profile_directory_and_gating_digest() -> None:
    """レジストリの列挙・必須検査・pinを実ファイルと突合する。"""
    entries = registry["profiles"]
    registered_files = {entry["file"] for entry in entries}
    actual_files = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in PROFILES_DIR.glob("*.json")
        if path != REGISTRY_PATH
    }
    assert registered_files == actual_files
    assert len(entries) == 1

    entry = entries[0]
    assert entry["name"] == profile["name"]
    assert entry["document"] == profile["document"]
    assert set(entry["must_require"]) <= set(profile["required_checks"])
    assert entry["must_require"] == profile["required_checks"]
    assert entry["pins"]["profile_gating_digest"] == _gating_digest(profile)
    assert entry["pins"]["asset_digests"] == {}
    assert entry["pins"]["invariants_digest"] == profile_loader.canonical_digest(
        _load_json(INVARIANTS_PATH)
    )


def test_schemas_are_versioned_closed_and_list_required_keys() -> None:
    """全スキーマの版・閉包・トップレベル必須キーを固定する。"""
    profile_schema = _load_json(SCHEMAS_DIR / "profile.schema.json")
    registry_schema = _load_json(SCHEMAS_DIR / "registry.schema.json")
    invariant_schema = _load_json(SCHEMAS_DIR / "invariant.schema.json")

    assert profile_schema["schema_version"] == 1
    assert registry_schema["schema_version"] == 1
    assert invariant_schema["schema_version"] == 1
    assert set(profile_schema["required"]) == PROFILE_REQUIRED_KEYS
    assert set(profile) == PROFILE_REQUIRED_KEYS | {"invariants"}
    assert set(registry_schema["required"]) == {"schema_version", "profiles"}
    assert set(invariant_schema["required"]) == {
        "schema_version",
        "structural_required",
        "legacy_structural",
        "required_declarations",
        "declarations",
    }
    assert {"invariants", "direct_requirements"} <= set(
        profile_schema["properties"]
    )
    _assert_schema_subset(profile_schema, root=True)
    _assert_schema_subset(registry_schema, root=True)
    _assert_schema_subset(invariant_schema, root=True)


def test_no_checker_or_claude_file_changed() -> None:
    """本ステップで対象外のCOV検査とClaude設定が無変更であることを確認する。"""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "HEAD",
            "--",
            "scripts/check_doc_coverage.py",
            ".claude/",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_production_registry_resolves_and_validates_all_defect_namespaces() -> None:
    """本番レジストリと同期プロファイル、欠陥40件を正常に解決する。"""
    loaded_registry = profile_loader.load_registry(
        profile_loader.default_registry_path(REPOSITORY_ROOT),
        root=REPOSITORY_ROOT,
    )
    profiles = profile_loader.resolve_profiles(
        loaded_registry,
        root=REPOSITORY_ROOT,
    )
    assert len(profiles) == 1
    loaded_profile = profiles[0]
    assert loaded_profile.name == "sync-protocol"
    assert loaded_profile.path == PROFILE_PATH.resolve()
    assert loaded_profile.document.is_absolute()
    assert loaded_profile.manifest.is_absolute()

    defects = profile_loader.load_json(DEFECTS_PATH)
    defect_ids = tuple(
        identifier for identifier in defects if not identifier.startswith("_")
    )
    assert len(defect_ids) == 40
    profile_loader.validate_defect_id_namespaces(loaded_profile, defect_ids)


def test_schema_validator_supports_multiple_types_and_array_constraints() -> None:
    """複数type、minItems、uniqueItemsを解釈する。"""
    schema = {
        "type": ["array", "string"],
        "items": {"type": "integer"},
        "minItems": 2,
        "uniqueItems": True,
    }
    profile_loader.validate_against_schema([1, 2], schema)
    profile_loader.validate_against_schema("文字列", schema)
    with pytest.raises(profile_loader.ProfileError, match=r"\$.*minItems"):
        profile_loader.validate_against_schema([1], schema)
    with pytest.raises(profile_loader.ProfileError, match=r"\$\[1\].*uniqueItems"):
        profile_loader.validate_against_schema([1, 1], schema)


@pytest.mark.parametrize(
    "mutation",
    ("missing-required", "wrong-version", "unknown-field"),
)
def test_profile_schema_violations_are_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    """必須欠落、版不一致、未知フィールドを拒否する。"""
    root = _copy_profile_tree(tmp_path)
    path = _temporary_profile_path(root)
    value = _load_json(path)
    if mutation == "missing-required":
        del value["document"]
    elif mutation == "wrong-version":
        value["schema_version"] = 2
    else:
        value["unknown_field"] = True
    _write_json(path, value)

    with pytest.raises(profile_loader.ProfileError, match=r"\$"):
        profile_loader.load_profile(path, root=root)


@pytest.mark.parametrize("mutation", ("missing-id", "overlapping-id"))
def test_check_partition_violations_are_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    """検査IDの不足と両集合への重複を拒否する。"""
    root = _copy_profile_tree(tmp_path)
    path = _temporary_profile_path(root)
    value = _load_json(path)
    if mutation == "missing-id":
        value["required_checks"].remove("ledger")
    else:
        value["not_applicable"]["ledger"] = "重複させる負例"
    _write_json(path, value)

    with pytest.raises(profile_loader.ProfileError, match="完全分割|重複"):
        profile_loader.load_profile(path, root=root)


def test_duplicate_required_check_is_fail_closed(tmp_path: Path) -> None:
    """required_checks配列内の同一ID重複を拒否する。"""
    root = _copy_profile_tree(tmp_path)
    path = _temporary_profile_path(root)
    value = _load_json(path)
    value["required_checks"].append(value["required_checks"][0])
    _write_json(path, value)

    with pytest.raises(profile_loader.ProfileError, match="重複ID"):
        profile_loader.load_profile(path, root=root)


def test_empty_not_applicable_reason_is_fail_closed(tmp_path: Path) -> None:
    """空白だけの適用外理由を拒否する。"""
    root = _copy_profile_tree(tmp_path)
    path = _temporary_profile_path(root)
    value = _load_json(path)
    value["not_applicable"]["forbidden-structure"] = "  "
    _write_json(path, value)

    with pytest.raises(profile_loader.ProfileError, match="理由が空"):
        profile_loader.load_profile(path, root=root)


def test_unknown_not_applicable_id_is_fail_closed(tmp_path: Path) -> None:
    """not_applicableの未知検査IDを拒否する。"""
    root = _copy_profile_tree(tmp_path)
    path = _temporary_profile_path(root)
    value = _load_json(path)
    value["not_applicable"]["unknown-check"] = "未知IDの負例"
    _write_json(path, value)

    with pytest.raises(profile_loader.ProfileError, match="未知フィールド|未知ID"):
        profile_loader.load_profile(path, root=root)


def test_unknown_invariant_kind_is_fail_closed(tmp_path: Path) -> None:
    """invariant_kindsの未知kindを拒否する。"""
    root = _copy_profile_tree(tmp_path)
    path = _temporary_profile_path(root)
    value = _load_json(path)
    value["invariant_kinds"][0] = "unknown-kind"
    _write_json(path, value)

    with pytest.raises(profile_loader.ProfileError, match="enum|未知kind"):
        profile_loader.load_profile(path, root=root)


def test_registry_rejects_unregistered_profile_file(tmp_path: Path) -> None:
    """profilesディレクトリの未登録JSONを拒否する。"""
    root = _copy_profile_tree(tmp_path)
    extra = _temporary_registry_path(root).parent / "unregistered.json"
    _write_json(extra, profile)

    with pytest.raises(profile_loader.ProfileError, match="未登録"):
        profile_loader.load_registry(_temporary_registry_path(root), root=root)


def test_registry_rejects_registered_missing_file(tmp_path: Path) -> None:
    """レジストリに登録済みだが存在しないプロファイルを拒否する。"""
    root = _copy_profile_tree(tmp_path)
    _temporary_profile_path(root).unlink()

    with pytest.raises(profile_loader.ProfileError, match="登録先不在"):
        profile_loader.load_registry(_temporary_registry_path(root), root=root)


@pytest.mark.parametrize("duplicate_field", ("name", "document"))
def test_registry_rejects_duplicate_identity_fields(
    tmp_path: Path,
    duplicate_field: str,
) -> None:
    """レジストリのnameとdocumentの重複を拒否する。"""
    root = _copy_profile_tree(tmp_path)
    registry_path = _temporary_registry_path(root)
    profiles_dir = registry_path.parent
    second_profile = profiles_dir / "second.json"
    _write_json(second_profile, profile)

    value = _load_json(registry_path)
    first = value["profiles"][0]
    second = json.loads(json.dumps(first))
    second["file"] = second_profile.relative_to(root).as_posix()
    second["name"] = "second"
    second["document"] = "docs/design/second.md"
    second[duplicate_field] = first[duplicate_field]
    value["profiles"].append(second)
    _write_json(registry_path, value)

    with pytest.raises(profile_loader.ProfileError, match=duplicate_field):
        profile_loader.load_registry(registry_path, root=root)


def test_registry_rejects_zero_profiles(tmp_path: Path) -> None:
    """0件のレジストリを拒否する。"""
    root = _copy_profile_tree(tmp_path)
    registry_path = _temporary_registry_path(root)
    value = _load_json(registry_path)
    value["profiles"] = []
    _write_json(registry_path, value)

    with pytest.raises(profile_loader.ProfileError, match="1件以上"):
        profile_loader.load_registry(registry_path, root=root)


def test_resolve_profiles_rejects_must_require_violation(tmp_path: Path) -> None:
    """プロファイルがレジストリのmust_requireを満たさない場合に拒否する。"""
    root = _copy_profile_tree(tmp_path)
    registry_path = _temporary_registry_path(root)
    value = _load_json(registry_path)
    value["profiles"][0]["must_require"].append("forbidden-structure")
    _write_json(registry_path, value)
    loaded_registry = profile_loader.load_registry(registry_path, root=root)

    with pytest.raises(profile_loader.ProfileError, match="must_require"):
        profile_loader.resolve_profiles(loaded_registry, root=root)


def test_resolve_profiles_rejects_document_mismatch(tmp_path: Path) -> None:
    """entryとプロファイルのdocument不一致を拒否する。"""
    root = _copy_profile_tree(tmp_path)
    registry_path = _temporary_registry_path(root)
    value = _load_json(registry_path)
    value["profiles"][0]["document"] = "docs/design/other.md"
    _write_json(registry_path, value)
    loaded_registry = profile_loader.load_registry(registry_path, root=root)

    with pytest.raises(profile_loader.ProfileError, match="document"):
        profile_loader.resolve_profiles(loaded_registry, root=root)


def test_resolve_profiles_rejects_gating_digest_mismatch(tmp_path: Path) -> None:
    """ゲート節のprofile_gating_digest不一致を拒否する。"""
    root = _copy_profile_tree(tmp_path)
    registry_path = _temporary_registry_path(root)
    value = _load_json(registry_path)
    value["profiles"][0]["pins"]["profile_gating_digest"] = "0" * 64
    _write_json(registry_path, value)
    loaded_registry = profile_loader.load_registry(registry_path, root=root)

    with pytest.raises(profile_loader.ProfileError, match="profile_gating_digest"):
        profile_loader.resolve_profiles(loaded_registry, root=root)


def test_load_json_rejects_duplicate_keys_and_missing_file(tmp_path: Path) -> None:
    """JSON重複キーとファイル欠落をProfileErrorへ写す。"""
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"value": 1, "value": 2}\n', encoding="utf-8")
    with pytest.raises(profile_loader.ProfileError, match="重複"):
        profile_loader.load_json(duplicate)
    with pytest.raises(profile_loader.ProfileError, match="読めません"):
        profile_loader.load_json(tmp_path / "missing.json")


def test_canonical_digest_matches_registry_and_rejects_float() -> None:
    """canonical digestをレジストリ値と突合しfloatを拒否する。"""
    gating = {key: profile[key] for key in GATING_KEYS if key in profile}
    expected = registry["profiles"][0]["pins"]["profile_gating_digest"]
    assert profile_loader.canonical_digest(gating) == expected
    assert profile_loader.canonical_digest(gating) == _gating_digest(profile)
    with pytest.raises(profile_loader.ProfileError, match=r"\$\.nested\[1\].*float"):
        profile_loader.canonical_digest({"nested": [1, 1.5]})


def test_schema_validator_rejects_unsupported_keyword() -> None:
    """未対応スキーマキーワードを使用位置にかかわらず拒否する。"""
    schema = {
        "type": "object",
        "properties": {"optional": {"type": "string", "$ref": "other.json"}},
        "additionalProperties": False,
    }
    with pytest.raises(profile_loader.ProfileError, match=r"\$ref"):
        profile_loader.validate_against_schema({}, schema)


def test_resolve_profiles_requires_invariants_digest(tmp_path: Path) -> None:
    """invariants指定時にinvariants_digestが無ければ拒否する。"""
    root = _copy_profile_tree(tmp_path)
    registry_path = _temporary_registry_path(root)
    value = _load_json(registry_path)
    del value["profiles"][0]["pins"]["invariants_digest"]
    _write_json(registry_path, value)
    loaded_registry = profile_loader.load_registry(
        registry_path,
        root=root,
    )

    with pytest.raises(profile_loader.ProfileError, match="invariants_digest"):
        profile_loader.resolve_profiles(loaded_registry, root=root)


def test_resolve_profiles_accepts_matching_invariants_digest(tmp_path: Path) -> None:
    """invariants本体と一致するinvariants_digestを受理する。"""
    root = _copy_profile_tree(tmp_path)
    registry_path = _temporary_registry_path(root)
    invariants_path = root / "scripts/design_relations/invariants/sync-protocol.json"
    invariants = _load_json(invariants_path)
    invariants["legacy_structural"] = list(reversed(invariants["legacy_structural"]))
    _write_json(invariants_path, invariants)

    registry_value = _load_json(registry_path)
    registry_value["profiles"][0]["pins"]["invariants_digest"] = (
        profile_loader.canonical_digest(invariants)
    )
    _write_json(registry_path, registry_value)

    loaded_registry = profile_loader.load_registry(registry_path, root=root)
    assert len(profile_loader.resolve_profiles(loaded_registry, root=root)) == 1


def test_validate_defect_namespaces_rejects_machine_namespace_gap(
    tmp_path: Path,
) -> None:
    """機械欠陥の接頭辞がmachineから欠落したプロファイルを拒否する。"""
    root = _copy_profile_tree(tmp_path)
    profile_path = _temporary_profile_path(root)
    defect_path = root / "scripts/design_relations/defects.json"
    shutil.copy2(DEFECTS_PATH, defect_path)
    profile_value = _load_json(profile_path)
    profile_value["defect_id_namespaces"]["machine"] = ["SP"]
    _write_json(profile_path, profile_value)
    loaded_profile = profile_loader.load_profile(profile_path, root=root)
    defects = profile_loader.load_json(defect_path)
    defect_ids = (
        identifier for identifier in defects if not identifier.startswith("_")
    )

    with pytest.raises(profile_loader.ProfileError, match="machine"):
        profile_loader.validate_defect_id_namespaces(loaded_profile, defect_ids)


def test_staging_tree_resolves_and_rejects_unrelated_json(tmp_path: Path) -> None:
    """staging直下のprofiles構成を解決し、無関係なJSONを拒否する。"""
    root = tmp_path / "staging"
    profiles_dir = root / "profiles"
    profile_path = profiles_dir / "x.json"
    registry_path = profiles_dir / "registry.json"
    profile_value = json.loads(json.dumps(profile))
    profile_value["name"] = "x"
    _write_json(profile_path, profile_value)
    staging_invariants = root / "scripts/design_relations/invariants"
    shutil.copytree(INVARIANTS_DIR, staging_invariants)

    entry = json.loads(json.dumps(registry["profiles"][0]))
    entry["name"] = "x"
    entry["file"] = "profiles/x.json"
    _write_json(
        registry_path,
        {"schema_version": 1, "profiles": [entry]},
    )
    assert {path.name for path in profiles_dir.glob("*.json")} == {
        "registry.json",
        "x.json",
    }

    loaded_registry = profile_loader.load_registry(
        registry_path,
        root=root,
        schema_dir=SCHEMAS_DIR,
    )
    profiles = profile_loader.resolve_profiles(loaded_registry, root=root)
    assert len(profiles) == 1
    assert profiles[0].path == profile_path.resolve()

    _write_json(profiles_dir / "unrelated.json", {})
    with pytest.raises(profile_loader.ProfileError, match="未登録"):
        profile_loader.load_registry(
            registry_path,
            root=root,
            schema_dir=SCHEMAS_DIR,
        )


def _binding_inputs() -> tuple[set[str], set[str], frozenset[str]]:
    """本番欠陥oracleから結合規則のM・F・旧分岐集合を返す。"""
    entries = {
        identifier: value
        for identifier, value in _load_json(DEFECTS_PATH).items()
        if not identifier.startswith("_")
    }
    machine = {
        identifier
        for identifier, value in entries.items()
        if value["detection"] == "machine"
    }
    forbidden = {
        identifier
        for identifier, value in entries.items()
        if value["detection"] == "machine"
        and value["invariant"]["forbidden"]
    }
    return machine, forbidden, propagation.LEGACY_STRUCTURAL_BRANCH_IDS


def test_production_invariants_load_and_satisfy_binding_rules() -> None:
    """同期宣言資産を読み、結合規則1〜5が成立することを確認する。"""
    invariants = profile_loader.load_invariants(INVARIANTS_PATH)
    machine, forbidden, legacy_branches = _binding_inputs()

    assert invariants.path == INVARIANTS_PATH.resolve()
    assert invariants.declarations == ()
    assert invariants.global_invariants == ()
    profile_loader.validate_binding_rules(
        invariants,
        machine_defect_ids=machine,
        forbidden_defect_ids=forbidden,
        legacy_branch_ids=legacy_branches,
    )


@pytest.mark.parametrize(
    ("rule", "mutation"),
    (
        (1, "outside-machine"),
        (2, "missing-declaration"),
        (3, "legacy-outside-structural"),
        (4, "extra-declaration"),
        (5, "forbidden-gap"),
    ),
    ids=("rule-1", "rule-2", "rule-3", "rule-4", "rule-5"),
)
def test_binding_rules_are_always_fail_closed(rule: int, mutation: str) -> None:
    """結合規則1〜5の各違反を常時ProfileErrorにする。"""
    invariants = profile_loader.load_invariants(INVARIANTS_PATH)
    machine, forbidden, legacy_branches = _binding_inputs()
    if mutation == "outside-machine":
        invariants = replace(
            invariants,
            structural_required=invariants.structural_required | {"SP-99"},
        )
    elif mutation == "missing-declaration":
        invariants = replace(
            invariants,
            legacy_structural=invariants.legacy_structural - {"SP-01"},
        )
    elif mutation == "legacy-outside-structural":
        invariants = replace(
            invariants,
            structural_required=invariants.structural_required - {"SP-01"},
        )
    elif mutation == "extra-declaration":
        invariants = replace(
            invariants,
            declarations=(
                {
                    "defect_id": "SP-19",
                    "kind": "forbidden-element",
                    "literals": ["禁止語"],
                },
            ),
        )
    else:
        forbidden.remove("MT-01")

    with pytest.raises(profile_loader.ProfileError, match=rf"結合規則{rule}.*"):
        profile_loader.validate_binding_rules(
            invariants,
            machine_defect_ids=machine,
            forbidden_defect_ids=forbidden,
            legacy_branch_ids=legacy_branches,
        )


def test_binding_rule_three_rejects_legacy_branch_mismatch() -> None:
    """legacy IDに対応する旧分岐が無ければ規則3で拒否する。"""
    invariants = profile_loader.load_invariants(INVARIANTS_PATH)
    machine, forbidden, legacy_branches = _binding_inputs()

    with pytest.raises(profile_loader.ProfileError, match=r"結合規則3.*SP-01"):
        profile_loader.validate_binding_rules(
            invariants,
            machine_defect_ids=machine,
            forbidden_defect_ids=forbidden,
            legacy_branch_ids=legacy_branches - {"SP-01"},
        )


@pytest.mark.parametrize(
    ("declaration", "message"),
    (
        (
            {"defect_id": "SP-01", "kind": "row-selector"},
            "必須引数",
        ),
        (
            {"defect_id": "SP-01", "kind": "unknown-kind"},
            "enum|未対応",
        ),
    ),
    ids=("missing-kind-arguments", "unknown-kind"),
)
def test_load_invariants_rejects_invalid_declarations(
    tmp_path: Path,
    declaration: dict[str, Any],
    message: str,
) -> None:
    """kind別必須引数の欠落と未知kindを宣言資産の読み込みで拒否する。"""
    root = _copy_profile_tree(tmp_path)
    path = root / "scripts/design_relations/invariants/sync-protocol.json"
    value = _load_json(path)
    value["declarations"] = [declaration]
    _write_json(path, value)

    with pytest.raises(profile_loader.ProfileError, match=message):
        profile_loader.load_invariants(path)
