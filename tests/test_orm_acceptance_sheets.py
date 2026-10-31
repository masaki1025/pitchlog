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
    n3_candidate_rows = [
        row
        for row in generator.parse_sheet_rows(
            expected["N3-immutability-completeness.md"]
        )
        if "manifest immutability: 該当候補なし" not in row.implementation
    ]
    assert n3_candidate_rows
    assert all(
        "conditional=" in row.implementation
        and "coverage=" in row.implementation
        and "unclassified_handoff=" in row.implementation
        for row in n3_candidate_rows
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


def _occurrence_sheet(rows: tuple[tuple[str, str, str], ...]) -> str:
    """出現番号付きの行を持つ最小のシートを作る。"""
    lines = [
        "| 対象 | 正本側 | 実装側 | 判定 | 理由と典拠 |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {target} | data-model.md §7-1 | manifest: games "
        f"| {judgment} | {rationale} |"
        for target, judgment, rationale in rows
    )
    return "\n".join(lines)


def test_carry_forward_preserves_judgment_across_occurrence_renumbering() -> None:
    """出現番号の繰り上がりだけでは判定を空欄に戻さない。"""
    previous = _occurrence_sheet(
        (("出現 062: 不変", "一致", "既存の判定 data-model.md:7-1"),)
    )
    generated = _occurrence_sheet((("出現 064: 不変", "", ""),))

    carried, stats = generator.carry_forward_sheet(generated, previous, set())

    row = generator.parse_sheet_rows(carried)[0]
    assert row.judgment == "一致"
    assert row.rationale == "既存の判定 data-model.md:7-1"
    assert stats.carried == 1
    assert stats.key_changed == 0
    assert stats.reset == 0


def test_carry_forward_matches_duplicate_keys_in_occurrence_order() -> None:
    """同じ三つ組が複数あるときは出現順に対応させる。"""
    previous = _occurrence_sheet(
        (
            ("出現 001: 不変", "一致", "先行 data-model.md:7-1"),
            ("出現 002: 不変", "対象外", "後続 data-model.md:7-1"),
        )
    )
    generated = _occurrence_sheet(
        (("出現 003: 不変", "", ""), ("出現 004: 不変", "", ""))
    )

    carried, stats = generator.carry_forward_sheet(generated, previous, set())

    rows = generator.parse_sheet_rows(carried)
    assert [row.judgment for row in rows] == ["一致", "対象外"]
    assert stats.carried == 2
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


def test_rg1_fresh_open_invariant_is_captured_in_n3() -> None:
    """採用済§3-2の追加1出現と実rowを結び、件数だけの追随にしない。"""
    sentence = "初期highwater=0をopen期間中の不変条件にもしない。"
    model = (REPO_ROOT / generator.DATA_MODEL_RELATIVE_PATH).read_text(
        encoding="utf-8"
    )
    assert model.count(sentence) == 1
    rows = generator.parse_sheet_rows(
        generator.render_sheets(REPO_ROOT)["N3-immutability-completeness.md"]
    )
    fresh = [
        row for row in rows
        if row.canonical.startswith("data-model.md §3-2 — 最初のfresh供給と残件:")
    ]
    assert len(fresh) == 1
    assert sentence in fresh[0].canonical
    assert fresh[0].target == "出現 030: 不変"
    assert fresh[0].implementation == (
        "rg1_restore_gate: protected=['singleton_id']; allowed=['state']; "
        "conditional=['recovery_generation']; coverage=exhaustive; "
        "unclassified_handoff=None"
    )



def test_generated_row_counts_match_all_current_source_rows() -> None:
    """正本・manifestの全抽出行数を上限ではなく完全一致で固定する。"""
    expected = generator.render_sheets(REPO_ROOT)
    assert {
        filename: len(generator.parse_sheet_rows(expected[filename]))
        for filename in generator.SHEET_FILENAMES
    } == {
        "N1-table-completeness.md": 104,
        "N3-immutability-completeness.md": 113,
        "N4-deletion-lifecycle.md": 59,
        "N7-required-attributes.md": 105,
    }



def test_n4_playless_game_supplement_preserves_all_other_direct_targets() -> None:
    """プレイ0件の試合だけに実列を補助表示し、主系統と旧8対象を保つ。"""
    tables = generator._load_manifest_tables(REPO_ROOT)
    before = json.dumps(tables, sort_keys=True)
    source = (REPO_ROOT / generator.DATA_MODEL_RELATIVE_PATH).read_text().splitlines()
    rows = generator._n4_direct_rows(generator._markdown_tables(source), tables)
    assert json.dumps(tables, sort_keys=True) == before
    assert len(rows) == 9
    assert tuple(row.target for row in rows) == (
        "11-1 対象 01: 試合のみ",
        "11-1 対象 02: 選手",
        "11-1 対象 03: プレイ行",
        "11-1 対象 04: 対戦相手チームレコード",
        "11-1 対象 05: プレイ 0 件の試合(ゴミ箱を経ず即時)",
        "11-1 対象 06: テナント(データ全保全)",
        "11-1 対象 07: 語彙(削除不可・無効化のみ)",
        "11-1 対象 08: グループの終了(不可逆)",
        "11-1 対象 09: 参加の離脱",
    )
    old_candidates = (
        "manifest lifecycle.deletion=ゴミ箱 の候補: games",
        "manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows",
        "manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows",
        "manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows",
        None,
        "manifest lifecycle.deletion=無効化 の候補: tenants, system_vocabularies, "
        "admin_vocabularies, tenant_vocabularies, trusted_devices, recording_right_deliveries",
        "manifest lifecycle.deletion=無効化 の候補: tenants, system_vocabularies, "
        "admin_vocabularies, tenant_vocabularies, trusted_devices, recording_right_deliveries",
        "manifest lifecycle.deletion=終了・離脱 の候補: analysis_groups, "
        "group_memberships, group_invitations",
        "manifest lifecycle.deletion=終了・離脱 の候補: analysis_groups, "
        "group_memberships, group_invitations",
    )
    for row, old in zip(rows, old_candidates, strict=True):
        if old is not None:
            assert row.implementation == old
        assert row.judgment == row.rationale == ""
    assert rows[4].canonical == "data-model.md §11-1 — 軸1=非表示"
    assert rows[4].implementation == (
        "manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows"
        " / 条件付き補助参照: games.hidden_at（プレイ0件、"
        "11-1/P-10の条件付き非表示。主系統はゴミ箱）"
    )
    games = next(t for t in tables if t["name"] == "games")
    assert games["lifecycle"]["deletion"] == "ゴミ箱"
    assert any(column["name"] == "hidden_at" for column in games["columns"])


def test_n4_supplement_requires_exact_source_target_lifecycle_and_real_column() -> None:
    """任意の試合語や別系統へ補助参照を広げず、存在しない列を生成しない。"""
    import copy
    from dataclasses import replace

    source = (REPO_ROOT / generator.DATA_MODEL_RELATIVE_PATH).read_text().splitlines()
    markdown_tables = generator._markdown_tables(source)
    tables = generator._load_manifest_tables(REPO_ROOT)
    for mode in ("target", "lifecycle", "missing_column", "main_lifecycle"):
        changed_markdown = list(markdown_tables)
        changed_tables = copy.deepcopy(tables)
        if mode in {"missing_column", "main_lifecycle"}:
            games = next(t for t in changed_tables if t["name"] == "games")
            if mode == "missing_column":
                games["columns"] = [c for c in games["columns"] if c["name"] != "hidden_at"]
            else:
                games["lifecycle"]["deletion"] = "終了・離脱"
        else:
            index = next(i for i, t in enumerate(changed_markdown)
                         if t.section == "11-1" and t.headers[:2] == ("系統", "対象"))
            table = changed_markdown[index]
            rows = list(table.rows)
            index_row = next(i for i, r in enumerate(rows) if "プレイ 0 件の試合" in r.cells[1])
            row = rows[index_row]
            cells = list(row.cells)
            if mode == "target":
                cells[1] = cells[1].replace("プレイ 0 件の試合", "すべての試合")
            else:
                cells[0] = "ゴミ箱"
            rows[index_row] = replace(row, cells=tuple(cells))
            changed_markdown[index] = replace(table, rows=tuple(rows))
        rows = generator._n4_direct_rows(changed_markdown, changed_tables)
        assert len(rows) == 9
        assert all("条件付き補助参照" not in row.implementation for row in rows)
        assert all(row.judgment == row.rationale == "" for row in rows)
