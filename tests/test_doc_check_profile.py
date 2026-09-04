"""文書検査プロファイルとレジストリのデータ契約を検証する。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELATIONS_DIR = REPOSITORY_ROOT / "scripts" / "design_relations"
PROFILES_DIR = RELATIONS_DIR / "profiles"
SCHEMAS_DIR = RELATIONS_DIR / "schemas"
PROFILE_PATH = PROFILES_DIR / "sync-protocol.json"
REGISTRY_PATH = PROFILES_DIR / "registry.json"
DEFECTS_PATH = RELATIONS_DIR / "defects.json"
PROPAGATION_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_design_propagation.py"
COVERAGE_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_doc_coverage.py"

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
    "pattern",
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


propagation = _load_module("profile_propagation_under_test", PROPAGATION_SCRIPT)
coverage = _load_module("profile_coverage_under_test", COVERAGE_SCRIPT)
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
    """定数化されていない現行リテラルをソースと突合する。"""
    source = PROPAGATION_SCRIPT.read_text(encoding="utf-8")
    assert profile["section_id_grammar"] == r"\d+(?:-\d+(?:-[A-Z])?)?"
    assert profile["section_id_grammar"] in source
    assert profile["preamble"] == "first-h2"
    assert 'text.split("\\n## ", 1)[0]' in source
    assert profile["link_base_dir"] == "docs/design"
    assert 'root / "docs" / "design"' in source
    assert profile["noncanonical_scan_start"] == r"^##\s+2(?:[.\s]|$)"
    assert profile["noncanonical_scan_start"] in source

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
    assert '"2-5"' in source
    assert '"| **R-"' in source
    assert "len(cells) != 6" in source

    assert profile["exclusion_vocabulary"] == [
        "対象外",
        "対象にならない",
        "含めない",
    ]
    assert '("対象外", "対象にならない", "含めない")' in source
    citation = profile["citation"]
    assert citation == {
        "legacy_prefixes": ["docs/legacy/", "../legacy/"],
        "legacy_infix": "/docs/legacy/",
        "inherit_bare_line_from_same_line": True,
    }
    assert all(
        literal in source
        for literal in (*citation["legacy_prefixes"], citation["legacy_infix"])
    )


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
    assert "invariants_digest" not in entry["pins"]


def test_schemas_are_versioned_closed_and_list_required_keys() -> None:
    """両スキーマの版・閉包・トップレベル必須キーを固定する。"""
    profile_schema = _load_json(SCHEMAS_DIR / "profile.schema.json")
    registry_schema = _load_json(SCHEMAS_DIR / "registry.schema.json")

    assert profile_schema["schema_version"] == 1
    assert registry_schema["schema_version"] == 1
    assert set(profile_schema["required"]) == PROFILE_REQUIRED_KEYS
    assert set(profile) == PROFILE_REQUIRED_KEYS
    assert set(registry_schema["required"]) == {"schema_version", "profiles"}
    assert {"invariants", "direct_requirements"} <= set(
        profile_schema["properties"]
    )
    _assert_schema_subset(profile_schema, root=True)
    _assert_schema_subset(registry_schema, root=True)


def test_no_checker_or_claude_file_changed() -> None:
    """本ステップの差分に検査スクリプトとClaude設定を含めない。"""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "HEAD",
            "--",
            "scripts/*.py",
            ".claude/",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
