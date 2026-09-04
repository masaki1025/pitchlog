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
CONTRACT_AUTHZ_DIR = REPOSITORY_ROOT / "contracts" / "authz"
PROFILE_SAMPLE_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "profile-sample"
SAMPLE_REGISTRY_PATH = PROFILE_SAMPLE_DIR / "profiles" / "registry.json"
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
    expected = set(propagation.LEGACY_PROP_CHECK_IDS) | set(
        coverage.COVERAGE_CHECK_IDS
    )
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


def test_propagation_checker_and_claude_files_are_unchanged() -> None:
    """Claude設定が無変更である。"""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "HEAD",
            "--",
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
    assert invariants.required_declarations == {"MT-01"}
    assert invariants.declarations == (
        {"defect_id": "MT-01", "kind": "absent-section", "section": "1"},
        {
            "defect_id": "SP-10",
            "kind": "row-selector",
            "id": "sp10-route",
            "section": "8-1",
            "mode": "identifier",
            "keys": ["P3"],
        },
        {
            "defect_id": "SP-10",
            "kind": "row-selector",
            "id": "sp10-response",
            "section": "7-1",
            "mode": "needle",
            "keys": ["P3", "応答"],
        },
        {
            "defect_id": "SP-11",
            "kind": "row-selector",
            "id": "sp11-6-2",
            "section": "6-2",
            "mode": "needle",
            "keys": ["期待版不一致"],
        },
        {
            "defect_id": "SP-11",
            "kind": "row-selector",
            "id": "sp11-6-3",
            "section": "6-3",
            "mode": "needle",
            "keys": ["期待版不一致"],
        },
        {
            "defect_id": "SP-11",
            "kind": "row-selector",
            "id": "sp11-8-3",
            "section": "8-3",
            "mode": "needle",
            "keys": ["期待版不一致"],
        },
        {
            "defect_id": "SP-01",
            "kind": "row-selector",
            "id": "sp01-transition",
            "section": "7-2",
            "mode": "needle",
            "keys": ["未送信", "退避済み"],
        },
        {
            "defect_id": "SP-01",
            "kind": "row-contains",
            "row": "sp01-transition",
            "literals": ["A5", "退避"],
        },
        {
            "defect_id": "SP-01",
            "kind": "row-selector",
            "id": "sp01-boundary",
            "section": "6-3",
            "mode": "identifier",
            "keys": ["B4"],
        },
        {
            "defect_id": "SP-01",
            "kind": "row-contains",
            "row": "sp01-boundary",
            "literals": ["A5", "退避"],
        },
        {
            "defect_id": "SP-02",
            "kind": "row-selector",
            "id": "sp02-source",
            "section": "7-1",
            "mode": "identifier",
            "keys": ["A5"],
        },
        {
            "defect_id": "SP-02",
            "kind": "row-contains",
            "row": "sp02-source",
            "elements": {
                "relation": "R-ACK-STATE",
                "field": "source_elements",
            },
        },
        {
            "defect_id": "SP-02",
            "kind": "section-contains",
            "sections": ["6-3", "7-2"],
            "elements": {
                "relation": "R-ACK-STATE",
                "field": "source_elements",
            },
            "as": "row",
        },
        {
            "defect_id": "SP-03",
            "kind": "section-contains",
            "sections": ["6-3", "7-2", "9-5"],
            "elements": {
                "relation": "R-QUEUE-LIFE",
                "field": "source_elements",
            },
            "as": "identifier",
        },
        {
            "defect_id": "SP-13",
            "kind": "section-contains",
            "sections": ["4-3"],
            "elements": {
                "relation": "R-EVENT-FIELD",
                "field": "source_elements",
            },
            "as": "identified-row",
            "key": "id-part",
        },
        {
            "defect_id": "SP-13",
            "kind": "section-contains",
            "sections": ["4-3-A", "11-2"],
            "elements": {
                "relation": "R-EVENT-FIELD",
                "field": "source_elements",
            },
            "as": "identifier",
        },
        {
            "defect_id": "SP-14",
            "kind": "section-contains",
            "sections": ["4-3-A"],
            "literals": ["W3-a", "W3-b", "変更版順"],
            "as": "text",
        },
        {
            "defect_id": "SP-14",
            "kind": "section-contains",
            "sections": ["5-5", "11-2"],
            "literals": ["変更版順", "D1・D2", "論理再生順"],
            "as": "text",
        },
        {
            "defect_id": "SP-06",
            "kind": "exact-set",
            "sections": ["8-1", "10-2", "11-2"],
            "relation": "R-TXN-ROUTE",
            "routes": ["P1", "P2", "P3"],
        },
        {
            "defect_id": "SP-07",
            "kind": "exact-set",
            "sections": ["8-1"],
            "relation": "R-TXN-ROUTE",
            "routes": ["P4"],
        },
        {
            "defect_id": "SP-07",
            "kind": "row-selector",
            "id": "sp07-atomic-9-2",
            "section": "9-2",
            "mode": "needle",
            "keys": ["旧世代", "退避", "B4", "原子"],
        },
        {
            "defect_id": "SP-07",
            "kind": "row-selector",
            "id": "sp07-atomic-10-2",
            "section": "10-2",
            "mode": "needle",
            "keys": ["退避", "B4", "原子"],
        },
        {
            "defect_id": "SP-07",
            "kind": "row-selector",
            "id": "sp07-atomic-11-2",
            "section": "11-2",
            "mode": "needle",
            "keys": ["P4", "退避", "B4"],
        },
        {
            "defect_id": "SP-08",
            "kind": "element-lookup",
            "relation": "R-TXN-ROUTE",
            "prefix": "T6:",
            "section": "8-1",
            "row_identifier": "T6",
        },
        {
            "defect_id": "SP-08",
            "kind": "section-contains",
            "sections": ["4-4"],
            "literals": ["一時 ID", "写像"],
            "as": "text",
        },
        {
            "defect_id": "SP-08",
            "kind": "section-contains",
            "sections": ["7-1"],
            "literals": ["D5", "確定結果"],
            "as": "text",
        },
        {
            "defect_id": "SP-08",
            "kind": "exact-set",
            "sections": ["8-1"],
            "relation": "R-TXN-ROUTE",
            "routes": {"containing": "T6"},
        },
        {
            "defect_id": "SP-09",
            "kind": "row-selector",
            "id": "sp09-route",
            "section": "8-1",
            "mode": "identifier",
            "keys": ["P3"],
        },
        {
            "defect_id": "SP-09",
            "kind": "exact-set",
            "row": "sp09-route",
            "relation": "R-TXN-ROUTE",
            "routes": ["P3"],
            "prefix": "T",
        },
        {
            "defect_id": "SP-09",
            "kind": "row-scoped-forbidden",
            "row": "sp09-route",
            "literals": ["T5"],
        },
        {
            "defect_id": "SP-09",
            "kind": "any-of",
            "row": "sp09-route",
            "literals": ["T7", "V11"],
        },
        {
            "defect_id": "SP-12",
            "kind": "row-selector",
            "id": "sp12-boundary",
            "section": "6-3",
            "mode": "identifier",
            "keys": ["B3"],
        },
        {
            "defect_id": "SP-12",
            "kind": "required-exclusion",
            "row": "sp12-boundary",
            "terms": ["D1 を持たない変更イベント", "D5"],
        },
        {
            "defect_id": "SP-12",
            "kind": "row-selector",
            "id": "sp12-resume",
            "section": "6-4",
            "mode": "needle",
            "keys": ["D1 を持たない変更イベント", "D5"],
        },
        {
            "defect_id": "SP-12",
            "kind": "required-exclusion",
            "row": "sp12-resume",
            "terms": ["D5"],
        },
        {
            "defect_id": "SP-16",
            "kind": "required-exclusion",
            "sections": ["6-1", "6-2"],
            "terms": ["D1 を持たない変更イベント", "prefix"],
        },
        {
            "defect_id": "SP-20",
            "kind": "row-selector",
            "id": "sp20-definition",
            "section": "2-1",
            "mode": "needle",
            "keys": ["| D1 |"],
        },
        {
            "defect_id": "SP-20",
            "kind": "row-contains",
            "row": "sp20-definition",
            "literals": ["順序と欠落", "undo の逆順"],
        },
        {
            "defect_id": "SP-20",
            "kind": "row-selector",
            "id": "sp20-order-role",
            "section": "4-2",
            "mode": "needle",
            "keys": ["D1", "順序", "欠落"],
        },
        {
            "defect_id": "SP-20",
            "kind": "row-selector",
            "id": "sp20-idempotency-role",
            "section": "4-2",
            "mode": "needle",
            "keys": ["D5", "再送", "二重適用"],
        },
        {
            "defect_id": "SP-20",
            "kind": "conditional-forbidden",
            "row": "sp20-definition",
            "literal": "再送の重複排除",
            "unless": ["D5 の用途", "D1 の用途ではない"],
        },
        {
            "defect_id": "SP-18",
            "kind": "well-formedness",
            "scope": "4-3-A",
            "rule": "balanced-emphasis-per-table-row",
        },
    )
    assert not invariants.legacy_structural
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
            declarations=tuple(
                declaration
                for declaration in invariants.declarations
                if declaration["defect_id"] != "SP-09"
            ),
        )
    elif mutation == "legacy-outside-structural":
        invariants = replace(
            invariants,
            legacy_structural=invariants.legacy_structural | {"SP-19"},
        )
    elif mutation == "extra-declaration":
        invariants = replace(
            invariants,
            declarations=invariants.declarations
            + (
                {
                    "defect_id": "SP-19",
                    "kind": "forbidden-element",
                    "literals": ["禁止語"],
                },
            ),
        )
    else:
        forbidden.remove("SP-19")

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

    invariants = replace(
        invariants,
        legacy_structural=invariants.legacy_structural | {"SP-09"},
        declarations=tuple(
            declaration
            for declaration in invariants.declarations
            if declaration["defect_id"] != "SP-09"
        ),
    )
    with pytest.raises(profile_loader.ProfileError, match=r"結合規則3.*SP-09"):
        profile_loader.validate_binding_rules(
            invariants,
            machine_defect_ids=machine,
            forbidden_defect_ids=forbidden,
            legacy_branch_ids=legacy_branches - {"SP-09"},
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
        (
            {"defect_id": "MT-01", "kind": "absent-section"},
            "必須引数",
        ),
    ),
    ids=("missing-kind-arguments", "unknown-kind", "missing-absent-section"),
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


def _profile_with_assets(
    tmp_path: Path,
    assets: dict[str, Any],
    *,
    structure_extractors: list[dict[str, Any]] | None = None,
    collection_sets: list[dict[str, Any]] | None = None,
    required_checks: tuple[str, ...] = (),
) -> Any:
    """本番プロファイルに合成資産宣言を差し込んで読む。"""
    value = _load_json(PROFILE_PATH)
    value["assets"] = assets
    value["structure_extractors"] = structure_extractors or []
    value["collection_sets"] = collection_sets or []
    for check_id in required_checks:
        value["required_checks"].append(check_id)
        del value["not_applicable"][check_id]
    profile_path = tmp_path / "asset-profile.json"
    _write_json(profile_path, value)
    return profile_loader.load_profile(
        profile_path,
        root=REPOSITORY_ROOT,
        schema_dir=SCHEMAS_DIR,
    )


def _contract_asset_declarations() -> dict[str, Any]:
    """contracts/authzの3資産を現物のID位置で宣言する。"""
    return {
        "claims": {
            "path": str(CONTRACT_AUTHZ_DIR / "requirement-claims.json"),
            "identity": {
                "schema_version": 1,
                "required_top_keys": ["input_manifest", "claims"],
            },
            "collections": [
                {
                    "items": "$.claims[*]",
                    "id": "source_id",
                    "namespace": "claim",
                    "fields": {"classification": "classification"},
                }
            ],
        },
        "auth_catalog": {
            "path": str(CONTRACT_AUTHZ_DIR / "auth-catalog.json"),
            "identity": {"schema_version": 1, "asset_kind": "authz_catalog"},
            "collections": [
                {
                    "items": "$.entries[*]",
                    "id": "catalog_entry_id",
                    "namespace": "auth",
                    "refs": "requirement_claim_id",
                }
            ],
        },
        "ddl_elements": {
            "path": str(CONTRACT_AUTHZ_DIR / "ddl-elements.json"),
            "identity": {
                "schema_version": 1,
                "asset_kind": "authz_candidate_ddl_manifest",
            },
            "collections": [
                {
                    "items": "$.tables[*]",
                    "id": "table_id",
                    "namespace": "table",
                    "refs": "policy_ids[*]",
                },
                {
                    "items": "$.tables[*]",
                    "id": "policy_ids[*]",
                    "namespace": "policy",
                    "role": "reference",
                },
                {
                    "items": "$.policies[*]",
                    "id": "policy_id",
                    "namespace": "policy",
                    "structure": {
                        "kind": "reference",
                        "source": "table_id",
                        "target": "role_ids[*]",
                        "direction": "source->target",
                        "participants": ["table_id", "role_ids[*]"],
                    },
                },
                {
                    "items": "$.policies[*]",
                    "id": "role_ids[*]",
                    "namespace": "role",
                    "role": "reference",
                },
                {
                    "items": "$.roles[*]",
                    "id": "role_id",
                    "namespace": "role",
                },
            ],
        },
    }


def test_assets_schema_fixes_immutable_and_mutable_field_sets() -> None:
    """版1のbaseline対象・可変フィールドをexact-setで固定する。"""
    schema = _load_json(SCHEMAS_DIR / "assets.schema.json")

    assert schema["schema_version"] == 1
    assert schema["additionalProperties"] is False
    assert schema["properties"]["immutable_fields"]["enum"] == [
        list(profile_loader.ASSET_IMMUTABLE_FIELDS)
    ]
    assert schema["properties"]["mutable_fields"]["enum"] == [
        list(profile_loader.ASSET_MUTABLE_FIELDS)
    ]
    instance = {
        "schema_version": 1,
        "immutable_fields": list(profile_loader.ASSET_IMMUTABLE_FIELDS),
        "mutable_fields": list(profile_loader.ASSET_MUTABLE_FIELDS),
        "assets": {},
        "structure_extractors": [],
        "collection_sets": [],
    }
    instance["immutable_fields"] = [
        field for field in instance["immutable_fields"] if field != "baseline"
    ]
    with pytest.raises(profile_loader.ProfileError, match="enum"):
        profile_loader.validate_against_schema(instance, schema)


def test_contract_authz_assets_expand_ids_and_ddl_structures(
    tmp_path: Path,
) -> None:
    """現行3資産のIDとtable→role構造を宣言だけで得る。"""
    profile = _profile_with_assets(tmp_path, _contract_asset_declarations())
    loaded = profile_loader.load_assets(profile)
    claims = loaded.assets["claims"].collections[0]
    auth = loaded.assets["auth_catalog"].collections[0]
    ddl = loaded.assets["ddl_elements"].collections
    raw_claims = _load_json(CONTRACT_AUTHZ_DIR / "requirement-claims.json")
    raw_auth = _load_json(CONTRACT_AUTHZ_DIR / "auth-catalog.json")
    raw_ddl = _load_json(CONTRACT_AUTHZ_DIR / "ddl-elements.json")

    assert {
        identifier.id
        for record in claims.records
        for identifier in record.identifiers
    } == {claim["source_id"] for claim in raw_claims["claims"]}
    assert {
        identifier.id
        for record in auth.records
        for identifier in record.identifiers
    } == {entry["catalog_entry_id"] for entry in raw_auth["entries"]}
    assert {reference.id for record in auth.records for reference in record.refs} == {
        entry["requirement_claim_id"] for entry in raw_auth["entries"]
    }
    assert {collection.namespace for collection in ddl} == {"table", "policy", "role"}
    assert {
        reference.id
        for record in ddl[0].records
        for reference in record.refs
    } == {
        policy_id
        for table in raw_ddl["tables"]
        for policy_id in table["policy_ids"]
    }
    assert {
        identifier.id
        for record in ddl[0].records
        for identifier in record.identifiers
    } == {table["table_id"] for table in raw_ddl["tables"]}
    assert {
        identifier.id
        for record in ddl[1].records
        for identifier in record.identifiers
    } == {
        policy_id
        for table in raw_ddl["tables"]
        for policy_id in table["policy_ids"]
    }
    assert {
        identifier.id
        for record in ddl[2].records
        for identifier in record.identifiers
    } == {policy["policy_id"] for policy in raw_ddl["policies"]}
    assert {
        identifier.id
        for record in ddl[3].records
        for identifier in record.identifiers
    } == {
        role_id
        for policy in raw_ddl["policies"]
        for role_id in policy["role_ids"]
    }

    expected = {
        profile_loader.StructureTuple(
            kind="reference",
            source=profile_loader.NamespacedId("table", policy["table_id"]),
            target=profile_loader.NamespacedId("role", role_id),
            direction="source->target",
            participants=(
                profile_loader.NamespacedId("table", policy["table_id"]),
                profile_loader.NamespacedId("role", role_id),
            ),
        )
        for policy in raw_ddl["policies"]
        for role_id in policy["role_ids"]
    }
    actual = {
        structure
        for structure in loaded.structures
        if structure.kind == "reference"
    }
    assert actual == expected


def test_asset_loader_rejects_identity_mismatch_and_missing_file(tmp_path: Path) -> None:
    """identity不一致と資産ファイル欠落をfail-closedにする。"""
    declarations = _contract_asset_declarations()
    declarations["auth_catalog"]["identity"]["asset_kind"] = "wrong"
    profile = _profile_with_assets(tmp_path, declarations)
    with pytest.raises(profile_loader.ProfileError, match="asset_kind 不一致"):
        profile_loader.load_assets(profile)

    declarations = _contract_asset_declarations()
    declarations["claims"]["path"] = str(tmp_path / "missing.json")
    profile = _profile_with_assets(tmp_path, declarations)
    with pytest.raises(profile_loader.ProfileError, match="JSONファイルを読めません"):
        profile_loader.load_assets(profile)


def test_asset_loader_rejects_bad_path_unknown_field_and_duplicate_key(
    tmp_path: Path,
) -> None:
    """パス文法、宣言の未知キー、資産JSONの重複キーを拒否する。"""
    declarations = _contract_asset_declarations()
    declarations["claims"]["collections"][0]["id"] = "nested.id"
    with pytest.raises(profile_loader.ProfileError, match="限定文法"):
        _profile_with_assets(tmp_path, declarations)

    declarations = _contract_asset_declarations()
    declarations["claims"]["unknown"] = True
    with pytest.raises(profile_loader.ProfileError, match="未知フィールド"):
        _profile_with_assets(tmp_path, declarations)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":1,"claims":[],"claims":[]}',
        encoding="utf-8",
    )
    declarations = {
        "claims": {
            "path": str(duplicate),
            "identity": {"schema_version": 1, "required_top_keys": ["claims"]},
            "collections": [{"items": "$.claims[*]", "id": "id", "namespace": "claim"}],
        }
    }
    profile = _profile_with_assets(tmp_path, declarations)
    with pytest.raises(profile_loader.ProfileError, match="JSONキー.*重複"):
        profile_loader.load_assets(profile)


def _id_asset_declaration(
    path: Path,
    ids: list[str],
    *,
    namespace: str,
    normalize: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """合成ID資産を書き、collection宣言を返す。"""
    _write_json(path, {"schema_version": 1, "items": [{"id": value} for value in ids]})
    declaration: dict[str, Any] = {
        "path": str(path),
        "identity": {"schema_version": 1, "required_top_keys": ["items"]},
        "collections": [
            {"items": "$.items[*]", "id": "id", "namespace": namespace}
        ],
    }
    if normalize is not None:
        declaration["normalize"] = normalize
    return declaration


def _normalizer(
    *,
    strip_prefixes: list[str] | None = None,
    separator: str = "-",
    aliases: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """テスト用の単一正規化宣言を返す。"""
    return {
        "strip_prefixes": strip_prefixes or [],
        "case": "preserve",
        "separator": separator,
        "aliases": aliases or {},
    }


def test_normalization_supports_prefix_alias_and_cross_namespace_names(
    tmp_path: Path,
) -> None:
    """明示prefix/alias統合を許容し、別名前空間は衝突させない。"""
    declarations = {
        "claims": _id_asset_declaration(
            tmp_path / "claims.json",
            ["DDL:orders", "orders", "legacy_orders"],
            namespace="table",
            normalize=_normalizer(
                strip_prefixes=["DDL:"],
                aliases={"table": {"legacy_orders": "orders"}},
            ),
        ),
        "auth_catalog": _id_asset_declaration(
            tmp_path / "auth.json",
            ["orders"],
            namespace="auth",
        ),
    }
    profile = _profile_with_assets(tmp_path, declarations)
    loaded = profile_loader.load_assets(profile)

    table_ids = {
        identifier
        for record in loaded.assets["claims"].collections[0].records
        for identifier in record.identifiers
    }
    auth_ids = {
        identifier
        for record in loaded.assets["auth_catalog"].collections[0].records
        for identifier in record.identifiers
    }
    assert table_ids == {profile_loader.NamespacedId("table", "orders")}
    assert auth_ids == {profile_loader.NamespacedId("auth", "orders")}


def test_normalization_rejects_namespace_collision_alias_conflict_and_cycle(
    tmp_path: Path,
) -> None:
    """暗黙衝突、alias競合、canonical再aliasの循環を拒否する。"""
    collision = {
        "claims": _id_asset_declaration(
            tmp_path / "collision.json",
            ["a_b", "a-b"],
            namespace="item",
            normalize=_normalizer(),
        )
    }
    with pytest.raises(profile_loader.ProfileError, match="異なる元ID.*衝突"):
        profile_loader.load_assets(_profile_with_assets(tmp_path, collision))

    conflict = {
        "claims": _id_asset_declaration(
            tmp_path / "conflict.json",
            ["a_b"],
            namespace="item",
            normalize=_normalizer(
                aliases={"item": {"a_b": "one", "a-b": "two"}}
            ),
        )
    }
    with pytest.raises(profile_loader.ProfileError, match="2つのcanonical"):
        _profile_with_assets(tmp_path, conflict)

    cycle = {
        "claims": _id_asset_declaration(
            tmp_path / "cycle.json",
            ["a"],
            namespace="item",
            normalize=_normalizer(aliases={"item": {"a": "b", "b": "a"}}),
        )
    }
    with pytest.raises(profile_loader.ProfileError, match="再aliasまたは循環"):
        _profile_with_assets(tmp_path, cycle)


@pytest.mark.parametrize(
    ("check_id", "assets", "extractors", "collection_sets", "message"),
    (
        ("forbidden-structure", {}, [], [], "必要なassets"),
        (
            "cross-consistency",
            _load_json(PROFILE_SAMPLE_DIR / "profiles/data-model-like.json")["assets"],
            [],
            [],
            "structure_extractorsが必要",
        ),
        ("collection-consistency", {}, [], [], "collection_setsが必要"),
    ),
    ids=("assets", "structure-extractors", "collection-sets"),
)
def test_required_checks_reject_missing_asset_declarations(
    tmp_path: Path,
    check_id: str,
    assets: dict[str, Any],
    extractors: list[dict[str, Any]],
    collection_sets: list[dict[str, Any]],
    message: str,
) -> None:
    """新必須検査と資産・抽出器・集合宣言を連動させる。"""
    with pytest.raises(profile_loader.ProfileError, match=message):
        _profile_with_assets(
            tmp_path,
            assets,
            structure_extractors=extractors,
            collection_sets=collection_sets,
            required_checks=(check_id,),
        )


def _sample_profiles() -> tuple[Any, ...]:
    """検証済みサンプルプロファイル列を返す。"""
    registry = profile_loader.load_registry(
        SAMPLE_REGISTRY_PATH,
        root=REPOSITORY_ROOT,
        schema_dir=SCHEMAS_DIR,
    )
    return profile_loader.resolve_profiles(registry, root=REPOSITORY_ROOT)


def _copy_sample_repository(tmp_path: Path) -> Path:
    """サンプル木とスキーマを一時リポジトリへ複製する。"""
    root = tmp_path / "sample-repository"
    shutil.copytree(
        PROFILE_SAMPLE_DIR,
        root / "tests/fixtures/profile-sample",
    )
    shutil.copytree(SCHEMAS_DIR, root / "scripts/design_relations/schemas")
    return root


def test_sample_extractors_derive_four_kinds_and_two_derived_rules() -> None:
    """サンプルの4 kindとinverse/closureの導出を固定する。"""
    profile = _sample_profiles()[1]
    assets = profile_loader.load_assets(profile)
    assert len(assets.joins) == 1
    assert assets.joins[0].target.id == "FR-001"
    text = profile.document.read_text(encoding="utf-8")
    manifest = _load_json(profile.manifest)
    actual = profile_loader.extract_structures(
        profile,
        assets,
        text=text,
        manifest=manifest,
    )

    assert {structures[0].kind for structures in actual.values()} == {
        "relation",
        "transition",
        "column-role",
        "reference",
    }
    inverse = actual["implicit-refs"][0]
    relation = actual["relations"][0]
    assert (inverse.source, inverse.target) == (relation.target, relation.source)

    raw = dict(profile.raw)
    raw["structure_extractors"] = [
        {
            "id": "edges",
            "source": "manifest",
                "kind": "edge",
                "map": {
                    "source": "node_id",
                    "target": "node_ids[*]",
                    "direction": "source->target",
                    "participants": ["node_id", "node_ids[*]"],
            },
        },
        {
            "id": "closure",
            "source": "derived",
            "kind": "closure",
            "from": "edges",
            "rule": "transitive-closure",
        },
    ]
    closure_profile = replace(profile, raw=raw)
    closure_manifest = {
        "relations": [
            {"node_id": "a", "node_ids": ["b"]},
            {"node_id": "b", "node_ids": ["c"]},
        ]
    }
    without_forbidden = replace(
        assets,
        assets={
            name: asset for name, asset in assets.assets.items() if name != "forbidden"
        },
    )
    derived = profile_loader.extract_structures(
        closure_profile,
        without_forbidden,
        text=text,
        manifest=closure_manifest,
    )
    assert {
        (structure.source.id, structure.target.id)
        for structure in derived["closure"]
    } == {("a", "b"), ("a", "c"), ("b", "c")}


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("header", "表ヘッダーが見つかりません"),
        ("column", "column=9.*範囲外"),
        ("alias", "未登録の別名またはID"),
        ("zero", "構造を1件も得られません"),
    ),
    ids=("header-mismatch", "column-offset", "unregistered-alias", "zero-result"),
)
def test_structure_extractors_fail_closed(
    mutation: str,
    message: str,
) -> None:
    """表不一致、列ずれ、未登録別名、抽出0件を拒否する。"""
    profile = _sample_profiles()[1]
    assets = profile_loader.load_assets(profile)
    text = profile.document.read_text(encoding="utf-8")
    manifest = _load_json(profile.manifest)
    raw = json.loads(json.dumps(profile.raw))
    if mutation == "header":
        text = text.replace("| 遷移 | 条件 |", "| 別の列 | 条件 |")
    elif mutation == "column":
        raw["structure_extractors"][1]["map"]["source"]["column"] = 9
    elif mutation == "alias":
        text = text.replace("| tenant_id | app_role |", "| tenant_id | unknown_role |")
    else:
        manifest["relations"] = []
    mutated = replace(profile, raw=raw)

    with pytest.raises(profile_loader.ProfileError, match=message):
        profile_loader.extract_structures(
            mutated,
            assets,
            text=text,
            manifest=manifest,
        )


def test_structure_extractors_must_cover_every_forbidden_kind() -> None:
    """forbiddenに現れるkindを抽出器の完全集合で覆う。"""
    profile = _sample_profiles()[1]
    assets = profile_loader.load_assets(profile)
    raw = json.loads(json.dumps(profile.raw))
    raw["structure_extractors"] = raw["structure_extractors"][:-1]

    with pytest.raises(profile_loader.ProfileError, match="reference"):
        profile_loader.extract_structures(
            replace(profile, raw=raw),
            assets,
            text=profile.document.read_text(encoding="utf-8"),
            manifest=_load_json(profile.manifest),
        )


def test_sample_collection_sets_cover_all_three_relations_and_report_differences() -> None:
    """exact/subset/disjointを評価し、違反時は差集合を示す。"""
    profile = _sample_profiles()[1]
    assets = profile_loader.load_assets(profile)
    manifest = _load_json(profile.manifest)
    results = profile_loader.evaluate_collection_sets(
        profile,
        assets,
        manifest=manifest,
    )

    assert {result.relation for result in results} == {"exact", "subset", "disjoint"}
    assert all(result.satisfied for result in results)

    raw = json.loads(json.dumps(profile.raw))
    target = next(
        declaration
        for declaration in raw["collection_sets"]
        if declaration["id"] == "direct-requirements-vs-claims"
    )
    target["right"] = {
        "asset": "claims",
        "collection": 0,
        "key": "source_id",
    }
    mismatched = next(
        result
        for result in profile_loader.evaluate_collection_sets(
            replace(profile, raw=raw),
            assets,
            manifest=manifest,
        )
        if result.id == "direct-requirements-vs-claims"
    )
    assert not mismatched.satisfied
    assert mismatched.right_only == frozenset({"R-SAMPLE"})
    assert "right-only=['R-SAMPLE']" in str(mismatched.reason)


@pytest.mark.parametrize(
    "mutation",
    ("extractor", "ddl-structure-collection", "map"),
)
def test_registry_gating_pin_detects_structural_declaration_changes(
    tmp_path: Path,
    mutation: str,
) -> None:
    """抽出器・DDL構造collection・map改変をゲートpinで検出する。"""
    root = _copy_sample_repository(tmp_path)
    profile_path = root / "tests/fixtures/profile-sample/profiles/data-model-like.json"
    value = _load_json(profile_path)
    if mutation == "extractor":
        value["structure_extractors"].pop()
    elif mutation == "ddl-structure-collection":
        value["assets"]["ddl_elements"]["collections"].pop(2)
    else:
        value["structure_extractors"][0]["map"]["direction"] = "target->source"
    _write_json(profile_path, value)
    registry_path = root / "tests/fixtures/profile-sample/profiles/registry.json"
    registry = profile_loader.load_registry(registry_path, root=root)

    with pytest.raises(profile_loader.ProfileError, match="profile_gating_digest"):
        profile_loader.resolve_profiles(registry, root=root)


def test_registry_asset_pins_reject_missing_pin_and_one_byte_change(
    tmp_path: Path,
) -> None:
    """必須資産pinの欠落とファイル1バイト改変を検出する。"""
    root = _copy_sample_repository(tmp_path)
    registry_path = root / "tests/fixtures/profile-sample/profiles/registry.json"
    registry_value = _load_json(registry_path)
    del registry_value["profiles"][1]["pins"]["asset_digests"]["direct_requirements"]
    _write_json(registry_path, registry_value)
    registry = profile_loader.load_registry(registry_path, root=root)
    with pytest.raises(profile_loader.ProfileError, match="pins.asset_digests"):
        profile_loader.resolve_profiles(registry, root=root)

    root = _copy_sample_repository(tmp_path / "byte-change")
    target = root / "tests/fixtures/profile-sample/assets/direct-requirements.json"
    target.write_bytes(target.read_bytes() + b" ")
    registry_path = root / "tests/fixtures/profile-sample/profiles/registry.json"
    registry = profile_loader.load_registry(registry_path, root=root)
    with pytest.raises(profile_loader.ProfileError, match="asset_digests.*不一致"):
        profile_loader.resolve_profiles(registry, root=root)


def test_profile_sample_layout_shapes_and_data_model_registry() -> None:
    """合成木の完全性、現行3資産との同形性、pin一致を固定する。"""
    expected = {
        "profiles/registry.json",
        "profiles/profile.json",
        "profiles/data-model-like.json",
        "doc/document.md",
        "doc/manifest.json",
        "doc/defects.json",
        "doc/invariants.json",
        "doc/requirements.md",
        "doc/req-universe.json",
        "assets/requirement-claims.json",
        "assets/auth-catalog.json",
        "assets/ddl-elements.json",
        "assets/auth-ddl-map.json",
        "assets/product-ddl-map.json",
        "assets/waiting.json",
        "assets/forbidden.json",
        "assets/direct-requirements.json",
        "assets/expected-ids.json",
        "assets/baseline-digest.txt",
    }
    assert {
        str(path.relative_to(PROFILE_SAMPLE_DIR))
        for path in PROFILE_SAMPLE_DIR.rglob("*")
        if path.is_file()
    } == expected
    assert {
        path.name for path in (PROFILE_SAMPLE_DIR / "profiles").glob("*.json")
    } == {"registry.json", "profile.json", "data-model-like.json"}

    for filename, collection in (
        ("requirement-claims.json", "claims"),
        ("auth-catalog.json", "entries"),
        ("ddl-elements.json", "tables"),
    ):
        actual = _load_json(CONTRACT_AUTHZ_DIR / filename)
        sample = _load_json(PROFILE_SAMPLE_DIR / "assets" / filename)
        assert set(sample) == set(actual)
        assert set(sample[collection][0]) == set(actual[collection][0])

    profiles = _sample_profiles()
    assert [profile.name for profile in profiles] == [
        "sample-minimal",
        "data-model-like",
    ]
    assert profiles[1].required_checks == set(profile_loader.CHECK_IDS_ALL)

    claims = _load_json(PROFILE_SAMPLE_DIR / "assets/requirement-claims.json")
    assert any(
        claim["classification"] == "direct_requirement"
        for claim in claims["claims"]
    )
    auth_map = _load_json(PROFILE_SAMPLE_DIR / "assets/auth-ddl-map.json")
    assert all(entry["ddl_ids"] and entry["structures"] for entry in auth_map["entries"])
    referenced_ids = {
        ddl_id
        for entry in auth_map["entries"]
        for ddl_id in entry["ddl_ids"]
    } | {
        endpoint["id"]
        for entry in auth_map["entries"]
        for structure in entry["structures"]
        for endpoint in (
            structure["source"],
            structure["target"],
            *structure["participants"],
        )
    }
    product_map = _load_json(PROFILE_SAMPLE_DIR / "assets/product-ddl-map.json")
    assert referenced_ids <= {entry["ddl_id"] for entry in product_map["entries"]}


def test_unique_owner_required_profile_rejects_missing_expected_ids(
    tmp_path: Path,
) -> None:
    """unique-owner必須時のexpected_ids資産省略を拒否する。"""
    value = _load_json(PROFILE_SAMPLE_DIR / "profiles/data-model-like.json")
    del value["assets"]["expected_ids"]
    path = tmp_path / "missing-expected-ids.json"
    _write_json(path, value)

    with pytest.raises(profile_loader.ProfileError, match="expected_ids"):
        profile_loader.load_profile(
            path,
            root=REPOSITORY_ROOT,
            schema_dir=SCHEMAS_DIR,
        )


def test_unique_owner_required_registry_rejects_missing_global_declaration(
    tmp_path: Path,
) -> None:
    """unique-owner必須時のglobal invariant欠落を拒否する。"""
    root = _copy_sample_repository(tmp_path)
    invariant_path = root / "tests/fixtures/profile-sample/doc/invariants.json"
    invariant_value = _load_json(invariant_path)
    invariant_value["global_invariants"] = []
    _write_json(invariant_path, invariant_value)
    digest = profile_loader.canonical_digest(invariant_value)

    registry_path = root / "tests/fixtures/profile-sample/profiles/registry.json"
    registry_value = _load_json(registry_path)
    for entry in registry_value["profiles"]:
        entry["pins"]["invariants_digest"] = digest
    _write_json(registry_path, registry_value)
    registry = profile_loader.load_registry(registry_path, root=root)

    with pytest.raises(profile_loader.ProfileError, match="global_invariants"):
        profile_loader.resolve_profiles(registry, root=root)
