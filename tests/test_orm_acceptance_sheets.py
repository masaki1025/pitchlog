"""ORM スキーマ移行の受入証跡突合シートを検査する。"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_orm_acceptance_sheets.py"
SCHEMA_AUDIT = REPO_ROOT / "backend" / "tests" / "db" / "test_schema_audit.py"


def _load_generator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "generate_orm_acceptance_sheets_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generator = _load_generator()
OUTPUT_ROOT = REPO_ROOT / generator.OUTPUT_RELATIVE_PATH


def _read_committed_sheets() -> dict[str, str]:
    return {
        filename: (OUTPUT_ROOT / filename).read_text(encoding="utf-8")
        for filename in generator.SHEET_FILENAMES
    }


def _single_row_sheet(judgment: str, rationale: str = "") -> str:
    return "\n".join(
        (
            "| 対象 | 正本側 | 実装側 | 判定 | 理由と典拠 |",
            "| --- | --- | --- | --- | --- |",
            f"| 対象 | data-model.md §5-1 | manifest: games | {judgment} | {rationale} |",
        )
    )


def _same_sheet_for_all(content: str) -> dict[str, str]:
    return {filename: content for filename in generator.SHEET_FILENAMES}


def _subscript_chain(node: ast.expr) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    ):
        return (*_subscript_chain(node.value), node.slice.value)
    return ()


def _called_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _schema_audit_compares_all_manifest_columns() -> bool:
    module = ast.parse(SCHEMA_AUDIT.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    manifest_columns = functions.get("_manifest_columns")
    audit_test = functions.get(
        "test_schema_manifest_matches_catalog_and_cross_table_rules"
    )
    if manifest_columns is None or audit_test is None:
        return False

    iterated_sets = {
        _subscript_chain(comprehension.iter)
        for node in ast.walk(manifest_columns)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp))
        for comprehension in node.generators
    }
    if not {("manifest", "tables"), ("table", "columns")} <= iterated_sets:
        return False

    assigned_calls: dict[str, str | None] = {}
    for node in ast.walk(audit_test):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            assigned_calls[node.targets[0].id] = _called_name(node.value)
    if assigned_calls.get("expected_columns") != "_manifest_columns":
        return False
    if assigned_calls.get("actual_columns") != "_column_catalog":
        return False

    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_set_violations"
        and len(node.args) >= 3
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "列"
        and isinstance(node.args[1], ast.Name)
        and node.args[1].id == "expected_columns"
        and isinstance(node.args[2], ast.Name)
        and node.args[2].id == "actual_columns"
        for node in ast.walk(audit_test)
    )


def test_acceptance_sheets_are_generated_from_current_sources() -> None:
    expected = generator.render_sheets(REPO_ROOT)
    assert set(expected) == {*generator.SHEET_FILENAMES, "README.md"}
    assert {path.name for path in OUTPUT_ROOT.glob("*.md")} == set(expected)

    for filename in generator.SHEET_FILENAMES:
        actual_content = (OUTPUT_ROOT / filename).read_text(encoding="utf-8")
        assert generator.without_human_judgments(actual_content) == expected[filename]
        assert generator.parse_sheet_rows(actual_content)
        assert "## 判定区分と適格条件" in actual_content
        assert "## 差分時の是正遷移" in actual_content

    assert (OUTPUT_ROOT / "README.md").read_text(
        encoding="utf-8"
    ) == expected["README.md"]

    assert generator.N3_TERMS == (
        "不変",
        "変えない",
        "昇格させない",
        "後退させない",
        "追記のみ",
        "変更不可",
        "更新しない",
        "上書きしない",
        "書き換えない",
    )
    assert {
        filename: len(generator.parse_sheet_rows(expected[filename]))
        for filename in generator.SHEET_FILENAMES
    } == {
        "N1-table-completeness.md": 100,
        "N3-immutability-completeness.md": 77,
        "N4-deletion-lifecycle.md": 54,
        "N7-required-attributes.md": 96,
    }
    assert all(
        "manifest=" in row.implementation
        and "models=" in row.implementation
        and "実カタログ=" in row.implementation
        for row in generator.parse_sheet_rows(expected["N7-required-attributes.md"])
    )
    assert all(
        "default=" not in row.implementation
        for row in generator.parse_sheet_rows(expected["N7-required-attributes.md"])
    )
    assert all(
        "照合済み" in row.implementation
        for row in generator.parse_sheet_rows(expected["N7-required-attributes.md"])
        if "manifest=該当候補なし" not in row.implementation
    )
    change_history_rows = [
        row
        for row in generator.parse_sheet_rows(
            expected["N3-immutability-completeness.md"]
        )
        if row.canonical.startswith("data-model.md §変更履歴")
    ]
    assert change_history_rows
    assert all(
        re.fullmatch(
            r"data-model\.md §変更履歴 — 版 \S+ の行（語: \S+）",
            row.canonical,
        )
        for row in change_history_rows
    )

    manifest = json.loads(
        (REPO_ROOT / generator.MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    manifest_tables = {table["name"] for table in manifest["tables"]}
    n4_manifest_candidates = {
        row.target.removeprefix("正本に直接割当なし候補: ")
        for row in generator.parse_sheet_rows(expected["N4-deletion-lifecycle.md"])
        if row.target.startswith("正本に直接割当なし候補: ")
    }
    assert n4_manifest_candidates == manifest_tables

    readme = expected["README.md"]
    assert "N2: TSK-250" in readme
    assert "N5: TSK-356" in readme
    assert "N6: 運用証跡" in readme


def test_n7_catalog_claim_is_covered_by_schema_audit() -> None:
    generated = generator.render_sheets(REPO_ROOT)
    n7_tables = set(
        re.findall(
            r"manifest=([a-z0-9_]+)\(列契約ブロック\)",
            generated["N7-required-attributes.md"],
        )
    )
    manifest = json.loads(
        (REPO_ROOT / generator.MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    manifest_tables = {table["name"] for table in manifest["tables"]}

    assert _schema_audit_compares_all_manifest_columns()
    audit_tables = manifest_tables
    assert n7_tables
    assert n7_tables <= audit_tables


def test_generator_does_not_fill_human_judgments() -> None:
    generated = generator.render_sheets(REPO_ROOT)
    for filename in generator.SHEET_FILENAMES:
        assert all(
            not row.judgment and not row.rationale
            for row in generator.parse_sheet_rows(generated[filename])
        )


def test_generation_comparison_detects_stale_column_contract_block() -> None:
    """判定外の列契約ブロックが古ければ全文比較で検出できる。"""
    expected = generator.render_sheets(REPO_ROOT)["N7-required-attributes.md"]
    stale = expected.replace(
        "tenant_id:uuid/NOT NULL/default=なし",
        "tenant_id:text/NOT NULL/default=なし",
        1,
    )

    assert stale != expected
    assert generator.without_human_judgments(stale) != expected


def test_carry_forward_rejects_changed_row_key() -> None:
    """三つ組が変わった行の判定を持ち越さない。"""
    previous = _single_row_sheet("一致")
    generated = _single_row_sheet("").replace(
        "manifest: games", "manifest: players"
    )

    carried, stats = generator.carry_forward_sheet(generated, previous, set())

    assert generator.parse_sheet_rows(carried)[0].judgment == ""
    assert stats.key_changed == 1
    assert stats.reset == 1


def test_carry_forward_rejects_previous_difference() -> None:
    """三つ組が同じでも差分判定を持ち越さない。"""
    previous = _single_row_sheet("差分", "未解消 data-model.md:5-1")
    generated = _single_row_sheet("")

    carried, stats = generator.carry_forward_sheet(generated, previous, set())

    assert generator.parse_sheet_rows(carried)[0].judgment == ""
    assert stats.difference == 1
    assert stats.reset == 1


def test_carry_forward_rejects_changed_identifier_in_rationale() -> None:
    """旧理由が変更識別子を含む行を持ち越さない。"""
    previous = _single_row_sheet(
        "一致", "status_source を確認した data-model.md:5-2"
    )
    generated = _single_row_sheet("")

    carried, stats = generator.carry_forward_sheet(
        generated, previous, {"status_source"}
    )

    row = generator.parse_sheet_rows(carried)[0]
    assert row.judgment == ""
    assert row.rationale == ""
    assert stats.changed_identifier == 1
    assert stats.reset == 1


def test_carry_forward_preserves_eligible_judgment() -> None:
    """除外条件に当たらない旧判定と理由を持ち越す。"""
    previous = _single_row_sheet(
        "対象外", "表定義の範囲外である data-model.md:5-1"
    )
    generated = _single_row_sheet("")

    carried, stats = generator.carry_forward_sheet(
        generated, previous, {"status_source"}
    )

    row = generator.parse_sheet_rows(carried)[0]
    assert row.judgment == "対象外"
    assert row.rationale == "表定義の範囲外である data-model.md:5-1"
    assert stats.carried == 1
    assert stats.reset == 0


def test_changed_identifiers_are_derived_from_contract_diff_lines() -> None:
    """追加・削除行から宣言名・値・CHECK 変更を抽出する。"""
    diff = "\n".join(
        (
            '-        {"name": "compatibility_payload", "type": "jsonb"}',
            '+        {"name": "status_source", "type": "text"}',
            '+    status_source: Mapped[str] = mapped_column(Text)',
            "+        CheckConstraint(\"status_source IN ('auto', 'manual')\"),",
        )
    )

    identifiers = generator._identifiers_from_contract_diff(diff)

    assert {
        "compatibility_payload",
        "jsonb",
        "status_source",
        "text",
        "auto",
        "manual",
        "CHECK",
    } <= identifiers


def test_judgment_validator_accepts_eligible_completed_rows() -> None:
    content = _single_row_sheet("一致")
    assert generator.judgment_errors(_same_sheet_for_all(content)) == []


def test_judgment_validator_rejects_unresolved_differences() -> None:
    content = _single_row_sheet("差分")
    errors = generator.judgment_errors(_same_sheet_for_all(content))
    assert all("未解消の差分 1 行" in error for error in errors)


def test_judgment_validator_requires_out_of_scope_evidence() -> None:
    content = _single_row_sheet("対象外", "範囲外のため")
    errors = generator.judgment_errors(_same_sheet_for_all(content))
    assert all("理由とファイル:節の典拠がない対象外 1 行" in error for error in errors)

    eligible = _single_row_sheet("対象外", "表定義ではないため data-model.md:5-1")
    assert generator.judgment_errors(_same_sheet_for_all(eligible)) == []


def test_acceptance_sheet_judgments_are_complete() -> None:
    errors = generator.judgment_errors(_read_committed_sheets())
    assert errors == []
