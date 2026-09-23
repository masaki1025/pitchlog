"""BOOT-REPORT が未解消要素の一覧と移行状態の意味を保持することを検査する。"""

from __future__ import annotations

import ast
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
REPORT_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/boot/report.py"
SCHEMA_PATH = ROOT / "backend/domain/boot-report.schema.json"
BOOT_SEAL_PATH = ROOT / "backend/domain/boot-seal.json"
CHECK_SETS_PATH = ROOT / "backend/domain/check-sets.json"

sys.path.insert(0, str(BACKEND_SRC))
REPORT = importlib.import_module("pitchlog.domaincheck.boot.report")
PHASE2 = importlib.import_module("pitchlog.domaincheck.boot.phase2")
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """未解消レポートの固定 schema を返す。"""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sealed_asset() -> dict[str, Any]:
    """既存の封印集合を返す。"""
    return json.loads(BOOT_SEAL_PATH.read_text(encoding="utf-8"))


def _copy_assets(root: Path) -> None:
    """出力試験用の一時ルートへ不変資産を複製する。"""
    domain = root / "backend/domain"
    domain.mkdir(parents=True)
    shutil.copy2(SCHEMA_PATH, domain / SCHEMA_PATH.name)
    shutil.copy2(BOOT_SEAL_PATH, domain / BOOT_SEAL_PATH.name)


def _initialise_runtime_repository(root: Path) -> None:
    """実状態測定用に Git 履歴と対象導出資産を用意する。"""
    _copy_assets(root)
    shutil.copy2(CHECK_SETS_PATH, root / "backend/domain/check-sets.json")
    commands = (
        ("init", "--quiet"),
        ("config", "user.name", "BOOT Report Test"),
        ("config", "user.email", "boot-report@example.invalid"),
        ("add", "."),
        ("commit", "--quiet", "-m", "fixture base"),
    )
    for command in commands:
        result = subprocess.run(
            ["git", *command],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def _resolved_ids(sealed_asset: dict[str, Any]) -> frozenset[str]:
    """固定件数に依存しない合成解消済み集合を返す。"""
    elements = sealed_asset["elements"]
    assert elements
    return frozenset({elements[0]["id"], elements[-1]["id"]})


def _report(
    sealed_asset: dict[str, Any],
    resolved_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """封印集合差から妥当な合成レポートを返す。"""
    resolved = _resolved_ids(sealed_asset) if resolved_ids is None else resolved_ids
    return REPORT.build_boot_report(sealed_asset, resolved)


def test_schema_fixes_output_filename_and_is_pretty_json(
    schema: dict[str, Any],
) -> None:
    assert schema["x-outputPath"] == "backend/domain/boot-report.json"
    source = SCHEMA_PATH.read_text(encoding="utf-8")
    assert source.endswith("\n")
    assert "\n  \"$schema\"" in source


def test_schema_and_implementation_have_the_same_exact_key_sets(
    schema: dict[str, Any],
    sealed_asset: dict[str, Any],
) -> None:
    item = schema["properties"]["unresolvedElements"]["items"]
    meaning = schema["properties"]["transitionMeaning"]
    provenance = schema["properties"]["provenance"]
    input_item = provenance["properties"]["inputFiles"]["items"]
    report = _report(sealed_asset, frozenset())
    schema_sets = (
        frozenset(schema["required"]),
        frozenset(item["required"]),
        frozenset(meaning["required"]),
        frozenset(provenance["required"]),
        frozenset(input_item["required"]),
    )
    implementation_sets = (
        frozenset(report),
        frozenset(report["unresolvedElements"][0]),
        frozenset(report["transitionMeaning"]),
        frozenset(report["provenance"]),
        frozenset(report["provenance"]["inputFiles"][0]),
    )

    assert schema_sets == implementation_sets
    assert frozenset(schema["properties"]) == schema_sets[0]
    assert frozenset(item["properties"]) == schema_sets[1]
    assert frozenset(meaning["properties"]) == schema_sets[2]
    assert frozenset(provenance["properties"]) == schema_sets[3]
    assert frozenset(input_item["properties"]) == schema_sets[4]
    assert schema["additionalProperties"] is False
    assert item["additionalProperties"] is False
    assert meaning["additionalProperties"] is False
    assert provenance["additionalProperties"] is False
    assert input_item["additionalProperties"] is False
    assert schema["properties"]["unresolvedCount"]["minimum"] == 0


@pytest.mark.parametrize("mutation", ["unknown", "missing"])
def test_unknown_and_missing_top_level_keys_are_rejected(
    schema: dict[str, Any],
    sealed_asset: dict[str, Any],
    mutation: str,
) -> None:
    changed = _report(sealed_asset)
    if mutation == "unknown":
        changed["unexpected"] = True
    else:
        del changed["reportType"]

    with pytest.raises(REPORT.CheckerViolation, match="キー集合が不一致"):
        REPORT.validate_asset(changed, schema)


@pytest.mark.parametrize("mutation", ["unknown", "missing"])
def test_unknown_and_missing_element_keys_are_rejected(
    schema: dict[str, Any],
    sealed_asset: dict[str, Any],
    mutation: str,
) -> None:
    changed = _report(sealed_asset, frozenset())
    first = changed["unresolvedElements"][0]
    if mutation == "unknown":
        first["unexpected"] = True
    else:
        del first["canonicalKey"]

    with pytest.raises(REPORT.CheckerViolation, match="キー集合が不一致"):
        REPORT.validate_asset(changed, schema)


def test_count_only_output_is_rejected(
    schema: dict[str, Any],
    sealed_asset: dict[str, Any],
) -> None:
    count_only = _report(sealed_asset)
    del count_only["unresolvedElements"]

    with pytest.raises(REPORT.CheckerViolation, match="unresolvedElements"):
        REPORT.validate_asset(count_only, schema)


def test_count_and_list_are_derived_from_sealed_minus_resolved(
    schema: dict[str, Any],
    sealed_asset: dict[str, Any],
) -> None:
    resolved = _resolved_ids(sealed_asset)
    report = REPORT.build_boot_report(sealed_asset, resolved)
    sealed_ids = {element["id"] for element in sealed_asset["elements"]}
    observed = {
        element["elementId"] for element in report["unresolvedElements"]
    }

    assert observed == sealed_ids - resolved
    assert report["unresolvedCount"] == len(report["unresolvedElements"])
    REPORT.assert_report_matches(sealed_asset, resolved, report, schema)


def test_wrong_count_is_rejected_even_when_list_is_unchanged(
    schema: dict[str, Any],
    sealed_asset: dict[str, Any],
) -> None:
    resolved = _resolved_ids(sealed_asset)
    changed = _report(sealed_asset, resolved)
    changed["unresolvedCount"] += 1

    with pytest.raises(REPORT.CheckerViolation, match="集合の差に一致しない"):
        REPORT.assert_report_matches(sealed_asset, resolved, changed, schema)


def test_report_measures_resolution_through_phase2_instead_of_fixing_empty() -> None:
    tree = ast.parse(REPORT_SOURCE.read_text(encoding="utf-8"))
    called_names = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "evaluate_phase2" in called_names
    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    assert not any(
        isinstance(node, ast.Tuple) and not node.elts for node in ast.walk(main)
    )


def test_declaration_only_phase2_change_resolves_no_elements(
    sealed_asset: dict[str, Any],
) -> None:
    universe = PHASE2.load_target_universe(ROOT)
    target_id = next(iter(universe.identifiers))
    state = STALL.activate(
        STALL.defined_state(len(universe.identifiers)),
        "synthetic-activation",
    )
    empty = PHASE2.SemanticSnapshot.empty()
    declaration_only = PHASE2.SemanticSnapshot(
        declarations=frozenset({target_id}),
        generated=frozenset(),
        product_calls=frozenset(),
        vector_checks=frozenset(),
        property_checks=frozenset(),
        mutation_checks=frozenset(),
    )
    decision = PHASE2.classify_phase2(state, universe, empty, declaration_only)

    assert decision.resolution_target_ids == frozenset()
    assert REPORT.resolved_element_ids_from_phase2(
        sealed_asset,
        decision,
    ) == frozenset()


def test_no_claim_and_ci_green_meaning_are_in_every_report(
    schema: dict[str, Any],
    sealed_asset: dict[str, Any],
) -> None:
    report = _report(sealed_asset)
    meaning = report["transitionMeaning"]

    assert meaning["noClaimAuthority"] == "NFR-018 (e) BOOT-NO-CLAIM"
    assert meaning["nfr018b2Satisfied"] is False
    assert meaning["nfr019aPassed"] is False
    assert meaning["ciMeaningAuthority"] == "設計書 10.1 BOOT-CI-MEANING"
    assert meaning["ciGreenMeaning"] == "transition-requirements-only"
    assert "移行状態の要求を満たしていることのみ" in meaning["statement"]
    REPORT.validate_asset(report, schema)


def test_green_without_report_output_is_rejected(tmp_path: Path) -> None:
    _copy_assets(tmp_path)

    with pytest.raises(REPORT.CheckerViolation, match="出力のない緑"):
        REPORT.accept_transition_green(tmp_path, frozenset())


def test_correct_report_is_emitted_and_green_is_accepted(
    tmp_path: Path,
    sealed_asset: dict[str, Any],
) -> None:
    _copy_assets(tmp_path)
    resolved = _resolved_ids(sealed_asset)

    output = REPORT.emit_boot_report(tmp_path, resolved)
    accepted = REPORT.accept_transition_green(tmp_path, resolved)

    assert output == tmp_path / "backend/domain/boot-report.json"
    assert output.is_file()
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert accepted["unresolvedCount"] == len(accepted["unresolvedElements"])


def test_green_rejects_report_for_a_different_resolved_set(
    tmp_path: Path,
    sealed_asset: dict[str, Any],
) -> None:
    _copy_assets(tmp_path)
    REPORT.emit_boot_report(tmp_path, frozenset())

    with pytest.raises(REPORT.CheckerViolation, match="集合の差に一致しない"):
        REPORT.accept_transition_green(tmp_path, _resolved_ids(sealed_asset))


def test_actual_measurement_records_head_and_input_digests(tmp_path: Path) -> None:
    """実状態からの出力が HEAD と封印・解消証跡の digest を持つ。"""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialise_runtime_repository(repository)

    output = REPORT.emit_boot_report(repository)
    report = json.loads(output.read_text(encoding="utf-8"))
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert report["provenance"]["commitOid"] == head
    assert report["provenance"]["inputDigest"].startswith("sha256:")
    assert report["provenance"]["sealedSetDigest"].startswith("sha256:")
    assert report["provenance"]["resolutionEvidenceDigest"].startswith("sha256:")
    assert {
        item["path"] for item in report["provenance"]["inputFiles"]
    } == {
        "backend/domain/boot-report.schema.json",
        "backend/domain/boot-seal.json",
        "backend/domain/check-sets.json",
    }
    assert REPORT.accept_transition_green(repository)["provenance"] == report["provenance"]


def test_old_report_is_rejected_after_head_advances(tmp_path: Path) -> None:
    """古い HEAD で生成した出力を残したまま次の commit を通せない。"""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialise_runtime_repository(repository)
    REPORT.emit_boot_report(repository)
    (repository / "head-advanced.txt").write_text("new head\n", encoding="utf-8")
    for command in (("add", "head-advanced.txt"), ("commit", "--quiet", "-m", "advance")):
        result = subprocess.run(
            ["git", *command],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    with pytest.raises(REPORT.CheckerViolation, match="一致しない"):
        REPORT.accept_transition_green(repository)


def test_unused_check_set_change_invalidates_existing_report(tmp_path: Path) -> None:
    """縮約結果が同じでも、実際に読んだ入力の変更は古い出力を拒否する。"""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialise_runtime_repository(repository)
    REPORT.emit_boot_report(repository)
    path = repository / "backend/domain/check-sets.json"
    check_sets = json.loads(path.read_text(encoding="utf-8"))
    check_sets["targetDerivation"]["groups"].append(
        {
            "id": "unused-review-negative",
            "marker": "未使用",
            "syntax": "unused",
        }
    )
    path.write_text(
        json.dumps(check_sets, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(REPORT.CheckerViolation, match="一致しない"):
        REPORT.accept_transition_green(repository)
