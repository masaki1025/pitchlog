"""design.md §2-1 と §16-12 が定める依拠条項台帳を検査する。"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "backend/domain/step-authorities.json"
STEPS_PATH = ROOT / "docs/features/domain-calc-dsl/steps.json"

CANONICAL_SOURCES = {
    "docs/requirements/requirements-pitchlog-2026-07-22.md",
    "docs/adr/ADR-003-domain-calc-method.md",
    "docs/development/dev-harness-design-2026-08-07.md",
}
TOP_LEVEL_KEYS = {"version", "authorityCatalog", "steps"}
CATALOG_ENTRY_KEYS = {"id", "source", "section", "verbatim"}
STEP_ENTRY_KEYS = {"stepId", "authorities", "requiresPositiveB", "pathAllowlist"}
AUTHORITY_ID_PATTERN = re.compile(
    r"(?:NFR-\d{3}|FR-\d{3}|付録[A-Z]-\d+|ADR-\d{3} D-\d+|設計書 \d+\.\d+) .+"
)
LINE_NUMBER_REFERENCE_PATTERN = re.compile(r":\d+")
ARTIFACT_PATH_PATTERN = re.compile(r"`([^`]+)`")


@pytest.fixture(scope="module")
def registry() -> dict[str, Any]:
    """依拠条項台帳を読み込む。"""
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps_source() -> dict[str, Any]:
    """全ステップの単一定義を読み込む。"""
    return json.loads(STEPS_PATH.read_text(encoding="utf-8"))


def _section_text(source_text: str, section_heading: str) -> str:
    """指定見出しに属する本文を取り出す。

    Args:
        source_text: Markdown 正本の全文。
        section_heading: `#` を含む見出しの逐語。

    Returns:
        指定見出しから次の同階層以上の見出し直前までの文字列。
    """
    lines = source_text.splitlines()
    try:
        start = lines.index(section_heading)
    except ValueError as error:
        raise AssertionError(f"正本に節見出しがありません: {section_heading}") from error

    level = len(section_heading) - len(section_heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        heading = re.match(r"^(#+)\s", lines[index])
        if heading is not None and len(heading.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _assert_authorities_exist(asset: dict[str, Any]) -> None:
    """台帳の全条項 ID と逐語が指定した正本に実在することを検査する。"""
    assert set(asset) == TOP_LEVEL_KEYS
    assert asset["version"] == 1

    catalog_entries = asset["authorityCatalog"]
    malformed_catalog = {
        entry.get("id", "<ID なし>")
        for entry in catalog_entries
        if set(entry) != CATALOG_ENTRY_KEYS
    }
    assert not malformed_catalog, f"条項カタログのキー集合が不正: {sorted(malformed_catalog)!r}"

    catalog_ids = [entry["id"] for entry in catalog_entries]
    duplicate_ids = {identifier for identifier in catalog_ids if catalog_ids.count(identifier) > 1}
    assert not duplicate_ids, f"重複した条項 ID: {sorted(duplicate_ids)!r}"

    invalid_ids = {
        identifier
        for identifier in catalog_ids
        if AUTHORITY_ID_PATTERN.fullmatch(identifier) is None
    }
    assert not invalid_ids, f"条項 ID の形式が不正: {sorted(invalid_ids)!r}"
    assert all("ADR-003 D-13" not in identifier for identifier in catalog_ids)

    invalid_sources = {
        entry["source"] for entry in catalog_entries if entry["source"] not in CANONICAL_SOURCES
    }
    assert not invalid_sources, f"正本以外の出典: {sorted(invalid_sources)!r}"

    for entry in catalog_entries:
        source_text = (ROOT / entry["source"]).read_text(encoding="utf-8")
        section_text = _section_text(source_text, entry["section"])
        assert entry["verbatim"] in section_text, (
            f"条項の逐語が指定節にありません: {entry['id']}"
        )

    declared_ids = set(catalog_ids)
    referenced_ids = {
        authority for row in asset["steps"] for authority in row.get("authorities", [])
    }
    unknown_ids = referenced_ids - declared_ids
    unused_ids = declared_ids - referenced_ids
    assert not unknown_ids, f"カタログに無い条項 ID: {sorted(unknown_ids)!r}"
    assert not unused_ids, f"ステップが依拠しない条項 ID: {sorted(unused_ids)!r}"


def _assert_no_line_number_references(asset: dict[str, Any]) -> None:
    """`:<数字>` 形式の正本参照が無いことを検査する。"""
    serialized = json.dumps(asset, ensure_ascii=False)
    match = LINE_NUMBER_REFERENCE_PATTERN.search(serialized)
    assert match is None, f"行番号参照を検出: {match.group(0) if match else ''}"


def _assert_complete_step_population(asset: dict[str, Any], source: dict[str, Any]) -> None:
    """台帳が全 56 ステップを一度ずつ宣言することを検査する。"""
    expected_ids = set(range(1, 57))
    source_ids = [step["id"] for step in source["steps"]]
    actual_ids = [row.get("stepId") for row in asset["steps"]]

    assert source["expected_total"] == 56
    assert len(source_ids) == 56
    assert set(source_ids) == expected_ids
    assert len(asset["steps"]) == 56

    missing = expected_ids - set(actual_ids)
    unexpected = set(actual_ids) - expected_ids
    assert not missing and not unexpected, (
        f"ステップ ID の集合差: 欠落={sorted(missing)!r}, 未知={sorted(unexpected)!r}"
    )
    duplicate_ids = {step_id for step_id in actual_ids if actual_ids.count(step_id) > 1}
    assert not duplicate_ids, f"重複したステップ ID: {sorted(duplicate_ids)!r}"

    source_by_id = {step["id"]: step for step in source["steps"]}
    for row in asset["steps"]:
        assert set(row) == STEP_ENTRY_KEYS, f"ステップ {row.get('stepId')} のキー集合が不正"
        assert row["authorities"], f"ステップ {row['stepId']} の依拠条項が空"
        assert len(row["authorities"]) == len(set(row["authorities"]))
        assert isinstance(row["requiresPositiveB"], bool)
        assert row["pathAllowlist"], f"ステップ {row['stepId']} のパス許可集合が空"
        assert len(row["pathAllowlist"]) == len(set(row["pathAllowlist"]))
        assert all(
            prefix and not prefix.startswith(("/", "../")) and "*" not in prefix
            for prefix in row["pathAllowlist"]
        )

        artifact_paths = ARTIFACT_PATH_PATTERN.findall(source_by_id[row["stepId"]]["artifact"])
        uncovered = {
            path
            for path in artifact_paths
            if not any(path.startswith(prefix) for prefix in row["pathAllowlist"])
        }
        assert not uncovered, (
            f"ステップ {row['stepId']} の成果物がパス許可集合の外: {sorted(uncovered)!r}"
        )


def _assert_requires_positive_b_matches(asset: dict[str, Any], source: dict[str, Any]) -> None:
    """`requiresPositiveB` が単一定義と全件一致することを検査する。"""
    expected = {step["id"]: step["requires_positive_b"] for step in source["steps"]}
    actual = {
        row["stepId"]: row.get("requiresPositiveB")
        for row in asset["steps"]
        if "stepId" in row
    }
    missing = set(expected) - set(actual)
    unexpected = set(actual) - set(expected)
    mismatched = {
        step_id
        for step_id in expected.keys() & actual.keys()
        if expected[step_id] != actual[step_id]
    }
    assert not missing and not unexpected and not mismatched, (
        "requiresPositiveB の集合差: "
        f"欠落={sorted(missing)!r}, 未知={sorted(unexpected)!r}, "
        f"不一致={sorted(mismatched)!r}"
    )


def test_all_authorities_exist_verbatim_in_canonical_sources(
    registry: dict[str, Any],
) -> None:
    _assert_authorities_exist(registry)


def test_registry_has_no_line_number_references(registry: dict[str, Any]) -> None:
    _assert_no_line_number_references(registry)


def test_registry_has_exactly_all_fifty_six_steps(
    registry: dict[str, Any], steps_source: dict[str, Any]
) -> None:
    _assert_complete_step_population(registry, steps_source)


def test_requires_positive_b_matches_steps_source(
    registry: dict[str, Any], steps_source: dict[str, Any]
) -> None:
    _assert_requires_positive_b_matches(registry, steps_source)


def test_registry_declares_its_own_existing_authorities(registry: dict[str, Any]) -> None:
    step_three = next(row for row in registry["steps"] if row["stepId"] == 3)
    assert step_three["authorities"]
    _assert_authorities_exist(
        {
            **registry,
            "steps": [step_three],
            "authorityCatalog": [
                entry
                for entry in registry["authorityCatalog"]
                if entry["id"] in step_three["authorities"]
            ],
        }
    )


def test_unknown_authority_is_rejected(registry: dict[str, Any]) -> None:
    mutated = copy.deepcopy(registry)
    unknown_id = "NFR-999 存在しない条項"
    mutated["steps"][0]["authorities"].append(unknown_id)

    with pytest.raises(AssertionError, match="NFR-999"):
        _assert_authorities_exist(mutated)


def test_flipped_requires_positive_b_is_rejected(
    registry: dict[str, Any], steps_source: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(registry)
    mutated["steps"][0]["requiresPositiveB"] = not mutated["steps"][0]["requiresPositiveB"]

    with pytest.raises(AssertionError, match=r"不一致=\[1\]"):
        _assert_requires_positive_b_matches(mutated, steps_source)


def test_missing_step_is_rejected(
    registry: dict[str, Any], steps_source: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(registry)
    mutated["steps"] = [row for row in mutated["steps"] if row["stepId"] != 56]

    with pytest.raises(AssertionError, match="56"):
        _assert_complete_step_population(mutated, steps_source)


def test_line_number_reference_is_rejected(registry: dict[str, Any]) -> None:
    mutated = copy.deepcopy(registry)
    mutated["authorityCatalog"][0]["id"] += ":" + "123"

    with pytest.raises(AssertionError, match="行番号参照"):
        _assert_no_line_number_references(mutated)
