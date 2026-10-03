"""BOOT-ACTIVATION 要求①の条項母集合を正本から逆引きする検査。"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
CLAUSES_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/boot/clauses.py"
ASSET_PATH = ROOT / "backend/domain/boot-clauses.json"
REQUIREMENTS_PATH = ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"

sys.path.insert(0, str(BACKEND_SRC))
CLAUSES = importlib.import_module("pitchlog.domaincheck.boot.clauses")


@pytest.fixture(scope="module")
def asset() -> dict[str, Any]:
    """固定した条項 ID 対応表を返す。"""
    return json.loads(ASSET_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def requirements_text() -> str:
    """条項母集合を逆引きする要件正本を返す。"""
    return REQUIREMENTS_PATH.read_text(encoding="utf-8")


def _ids(clauses: tuple[Any, ...]) -> set[str]:
    """導出条項の ID 集合を返す。"""
    return {clause.identifier for clause in clauses}


def test_clause_ids_are_reverse_looked_up_from_canonical_wording(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    derived = CLAUSES.derive_clauses(requirements_text, asset)
    observed = {entry["id"] for entry in asset["clauses"]}

    assert _ids(derived) == observed
    assert tuple(clause.identifier for clause in derived) == tuple(
        entry["id"] for entry in asset["clauses"]
    )


def test_clause_mother_set_has_exactly_twelve_entries(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    derived = CLAUSES.validate_registry(requirements_text, asset)

    assert len(derived) == 12
    assert len(asset["clauses"]) == 12


def test_each_clause_id_exists_verbatim_in_its_derived_range(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    derived = CLAUSES.validate_registry(requirements_text, asset)

    assert all(clause.verbatim in clause.normative_text for clause in derived)
    assert all(clause.normative_text for clause in derived)


def test_boot_state_is_derived_and_ci_meaning_is_out_of_range(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    identifiers = _ids(CLAUSES.derive_clauses(requirements_text, asset))

    assert "BOOT-STATE" in identifiers
    assert "BOOT-CI-MEANING" not in identifiers


def test_subsection_rule_excludes_boot_clause_outside_nfr018_e(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    outside = "**`BOOT-SYNTHETIC-OUTSIDE`（範囲外）**: 範囲外の合成条項\n"
    changed = requirements_text.replace(
        "- **測定方法**:",
        f"- **測定方法**:\n{outside}",
        1,
    )

    identifiers = _ids(CLAUSES.derive_clauses(changed, asset))

    assert "BOOT-SYNTHETIC-OUTSIDE" not in identifiers


def test_adding_a_declared_clause_inside_range_changes_derived_set(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    synthetic = "**`BOOT-SYNTHETIC`（合成条項）**: 合成した規範。 "
    changed = requirements_text.replace(
        "**`BOOT-ACTIVATION`（発効）**:",
        f"{synthetic}**`BOOT-ACTIVATION`（発効）**:",
        1,
    )
    before = CLAUSES.derive_clauses(requirements_text, asset)
    after = CLAUSES.derive_clauses(changed, asset)

    assert _ids(after) == _ids(before) | {"BOOT-SYNTHETIC"}
    with pytest.raises(CLAUSES.CheckerViolation, match="条項数が契約値と異なる"):
        CLAUSES.validate_registry(changed, asset)


def test_reverse_lookup_source_has_no_clause_id_enumeration(
    asset: dict[str, Any],
) -> None:
    tree = ast.parse(CLAUSES_SOURCE.read_text(encoding="utf-8"))
    string_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    derived_ids = {entry["id"] for entry in asset["clauses"]}
    source = CLAUSES_SOURCE.read_text(encoding="utf-8")
    pattern = asset["derivation"]["clauseDeclarationPattern"]

    assert string_constants.isdisjoint(derived_ids)
    assert all(identifier not in source for identifier in derived_ids)
    assert all(identifier not in pattern for identifier in derived_ids)


def test_missing_or_unknown_clause_row_fails_set_comparison(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    missing = copy.deepcopy(asset)
    missing["clauses"].pop()
    unknown = copy.deepcopy(asset)
    unknown["clauses"][-1]["id"] = "BOOT-SYNTHETIC"
    unknown["clauses"][-1]["authorityId"] = "NFR-018 (e) BOOT-SYNTHETIC"
    unknown["clauses"][-1]["verbatim"] = "`BOOT-SYNTHETIC`"
    unknown["clauses"][-1]["violationDetection"][
        "criterionAuthority"
    ] = "NFR-018 (e) BOOT-SYNTHETIC"

    with pytest.raises(CLAUSES.CheckerViolation, match="逆引きと条項対応表"):
        CLAUSES.validate_registry(requirements_text, missing)
    with pytest.raises(CLAUSES.CheckerViolation, match="逆引きと条項対応表"):
        CLAUSES.validate_registry(requirements_text, unknown)


def test_every_row_keeps_typed_case_id_fields_without_fixing_current_values(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    changed = copy.deepcopy(asset)
    changed["clauses"][0]["negativeCaseIds"] = ["negative-synthetic"]
    changed["clauses"][0]["positiveCaseIds"] = ["positive-synthetic"]

    CLAUSES.validate_registry(requirements_text, changed)
    assert all("negativeCaseIds" in entry for entry in asset["clauses"])
    assert all("positiveCaseIds" in entry for entry in asset["clauses"])
    assert all(isinstance(entry["negativeCaseIds"], list) for entry in asset["clauses"])
    assert all(isinstance(entry["positiveCaseIds"], list) for entry in asset["clauses"])


@pytest.mark.parametrize("field", ["negativeCaseIds", "positiveCaseIds"])
def test_missing_or_invalid_case_id_field_is_rejected(
    asset: dict[str, Any],
    requirements_text: str,
    field: str,
) -> None:
    missing = copy.deepcopy(asset)
    del missing["clauses"][0][field]
    invalid = copy.deepcopy(asset)
    invalid["clauses"][0][field] = [1]

    with pytest.raises(CLAUSES.CheckerViolation, match="キー集合が不一致"):
        CLAUSES.validate_registry(requirements_text, missing)
    with pytest.raises(CLAUSES.CheckerExecutionError, match="空でない文字列"):
        CLAUSES.validate_registry(requirements_text, invalid)


def test_each_row_has_violation_detection_mapping(
    asset: dict[str, Any],
    requirements_text: str,
) -> None:
    CLAUSES.validate_registry(requirements_text, asset)

    for entry in asset["clauses"]:
        assert entry["violationDetection"] == {
            "kind": "clause-violation",
            "criterionAuthority": entry["authorityId"],
        }


def test_registry_asset_is_pretty_json_with_trailing_newline() -> None:
    source = ASSET_PATH.read_text(encoding="utf-8")

    assert source.endswith("\n")
    assert "\n  \"schemaVersion\"" in source
