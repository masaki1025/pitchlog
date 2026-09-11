"""スキーマ契約 manifest と正本の追跡可能性を検査する。"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pitchlog.db.base import Base

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_DATA_MODEL_PATH = _REPOSITORY_ROOT / "docs" / "design" / "data-model.md"
_MIGRATIONS_PATH = _REPOSITORY_ROOT / "backend" / "migrations" / "versions"

_PROVENANCE_METHODS = {"手動転記", "正本表から照合", "カタログ照合"}
_STRUCTURE_GROUPS = {
    "table",
    "columns",
    "lifecycle",
    "foreign_keys",
    "checks",
    "unique_constraints",
    "indexes",
    "forbidden_columns",
    "immutability",
}
_DELETION_LIFECYCLES = {
    "ゴミ箱",
    "非表示",
    "無効化",
    "終了・離脱",
    "対象外",
    "親に従う",
}
_APPEND_MODES = {"追記専用", "更新可"}
_RETIREMENT_MODES = {"退役述語を持つ", "持たない"}
_UNIQUE_ROLES = {"business_unique", "primary_key", "fk_target"}
_DESTINATION_CATEGORIES = {
    "試合",
    "プレイ行",
    "走者別表",
    "スタメン・出場区間",
    "導出",
    "保持のみ",
    "移行時に使用",
}


def _load_manifest() -> dict[str, Any]:
    """実ファイルの manifest を読み込む。"""
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _section_body(document: str, section: str) -> str:
    """番号付き節見出しから次の同階層見出し直前までを返す。

    Args:
        document: Markdown 文書全体。
        section: `3-4` のような節番号。

    Returns:
        指定節の本文。

    Raises:
        ValueError: 指定した節見出しが存在しない場合。
    """
    heading_pattern = re.compile(
        rf"^(?P<marks>###+)\s+{re.escape(section)}\.\s+.*$", re.MULTILINE
    )
    match = heading_pattern.search(document)
    if match is None:
        raise ValueError(f"正本節を解決できない: {section}")

    heading_level = len(match.group("marks"))
    next_heading = re.compile(rf"^#{{2,{heading_level}}}\s+", re.MULTILINE).search(
        document, match.end()
    )
    end = next_heading.start() if next_heading is not None else len(document)
    return document[match.end() : end]


def _plain_markdown_cell(cell: str) -> str:
    """表セルを比較用の可読な平文へ正規化する。"""
    value = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", cell)
    value = value.replace("**", "").replace("`", "")
    return " ".join(value.strip().split())


def _markdown_tables(section_body: str) -> list[tuple[list[str], list[list[str]]]]:
    """節本文に含まれる Markdown 表を列名と行へ分解する。"""
    lines = section_body.splitlines()
    tables: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index + 1 < len(lines):
        header_line = lines[index].strip()
        separator_line = lines[index + 1].strip()
        if not header_line.startswith("|") or not re.fullmatch(
            r"\|(?:\s*:?-+:?\s*\|)+", separator_line
        ):
            index += 1
            continue

        headers = [cell.strip() for cell in header_line.strip("|").split("|")]
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            if len(row) == len(headers):
                rows.append(row)
            index += 1
        tables.append((headers, rows))
    return tables


def _business_uniqueness_rows(document: str) -> set[tuple[str, str, str, str]]:
    """3-4 節の業務的一意性全数表を節見出しから抽出する。"""
    body = _section_body(document, "3-4")
    for headers, rows in _markdown_tables(body):
        if headers == ["節", "一意性", "キーの形", "判定"]:
            return {
                (
                    _plain_markdown_cell(section),
                    _plain_markdown_cell(uniqueness),
                    _plain_markdown_cell(key_shape),
                    "outside"
                    if _plain_markdown_cell(judgement).startswith("➖")
                    else "scoped",
                )
                for section, uniqueness, key_shape, judgement in rows
            }
    raise ValueError("3-4 節の業務的一意性全数表を解決できない")


def _destination_categories(document: str) -> set[str]:
    """12-1 節の 88 列表から行き先区分の集合を抽出する。"""
    body = _section_body(document, "12-1")
    categories: set[str] = set()
    previous: str | None = None
    for headers, rows in _markdown_tables(body):
        if "行き先" not in headers:
            continue
        destination_index = headers.index("行き先")
        for row in rows:
            destination = _plain_markdown_cell(row[destination_index])
            if destination == "同上":
                if previous is None:
                    raise ValueError("12-1 節の行き先「同上」に先行値がない")
                category = previous
            else:
                category = destination.split("(", maxsplit=1)[0]
                if category == "スタメンのみ":
                    category = "スタメン・出場区間"
                previous = category
            categories.add(category)
    return categories


def _manifest_business_uniqueness_rows(
    manifest: dict[str, Any],
) -> set[tuple[str, str, str, str]]:
    """Manifest の business_unique タグ付き制約を比較用集合にする。"""
    rows: set[tuple[str, str, str, str]] = set()
    for table in manifest["tables"]:
        for constraint in table["unique_constraints"]:
            if "business_unique" not in constraint["roles"]:
                continue
            source_row = constraint["source_row"]
            rows.add(
                (
                    source_row["section"],
                    source_row["uniqueness"],
                    source_row["key_shape"],
                    source_row["scope"],
                )
            )
    return rows


def _business_uniqueness_violations(
    document: str, manifest: dict[str, Any]
) -> list[str]:
    """正本と manifest の業務的一意性の差分だけを返す。"""
    source_rows = _business_uniqueness_rows(document)
    manifest_rows = _manifest_business_uniqueness_rows(manifest)
    violations = [
        f"manifest に不足: {row[0]} / {row[1]}"
        for row in sorted(source_rows - manifest_rows)
    ]
    violations.extend(
        f"manifest に余剰: {row[0]} / {row[1]}"
        for row in sorted(manifest_rows - source_rows)
    )
    return violations


def _source_digest_violations(source: bytes, expected_digest: str) -> list[str]:
    """正本内容の SHA-256 が束縛値と異なる場合に stale を返す。"""
    actual_digest = hashlib.sha256(source).hexdigest()
    if actual_digest == expected_digest:
        return []
    return [f"stale: data-model.md の SHA-256 が {expected_digest} と一致しない"]


def _traceability_violations(document: str, manifest: dict[str, Any]) -> list[str]:
    """全構造群の取得区分と正本参照を検査する。"""
    violations: list[str] = []
    for destination in manifest.get("legacy_destination_categories", []):
        category = destination.get("category", "<unknown>")
        if destination.get("provenance") != "正本表から照合":
            violations.append(f"行き先区分 {category}: 取得区分が不正")
        for section in destination.get("source_sections", []):
            try:
                _section_body(document, section)
            except ValueError:
                violations.append(
                    f"行き先区分 {category}: 正本節を解決できない: {section}"
                )
        for requirement_id in destination.get("requirement_ids", []):
            if (
                re.search(
                    rf"(?<![A-Za-z0-9-]){re.escape(requirement_id)}"
                    rf"(?![A-Za-z0-9-])",
                    document,
                )
                is None
            ):
                violations.append(
                    f"行き先区分 {category}: 要求 ID を解決できない: {requirement_id}"
                )

    for table in manifest["tables"]:
        table_name = table["name"]
        provenance = table.get("provenance", {})
        if set(provenance) != _STRUCTURE_GROUPS:
            violations.append(f"{table_name}: 取得区分を持たない構造群がある")
        for group, method in provenance.items():
            if method not in _PROVENANCE_METHODS:
                violations.append(f"{table_name}.{group}: 未知の取得区分 {method}")

        for section in table.get("source_sections", []):
            try:
                _section_body(document, section)
            except ValueError:
                violations.append(f"{table_name}: 正本節を解決できない: {section}")
        if not table.get("source_sections"):
            violations.append(f"{table_name}: 正本節がない")

        for requirement_id in table.get("requirement_ids", []):
            if (
                re.search(
                    rf"(?<![A-Za-z0-9-]){re.escape(requirement_id)}"
                    rf"(?![A-Za-z0-9-])",
                    document,
                )
                is None
            ):
                violations.append(
                    f"{table_name}: 要求 ID を解決できない: {requirement_id}"
                )
        if not table.get("requirement_ids"):
            violations.append(f"{table_name}: 要求 ID がない")
    return violations


def _manifest_shape_violations(manifest: dict[str, Any]) -> list[str]:
    """Manifest のカタログ構造と 3 軸の自己整合性を検査する。"""
    violations: list[str] = []
    if set(manifest.get("provenance_methods", {})) != _PROVENANCE_METHODS:
        violations.append("取得区分の定義が exact-set 一致しない")
    destination_categories = [
        entry["category"] for entry in manifest["legacy_destination_categories"]
    ]
    if len(destination_categories) != len(set(destination_categories)):
        violations.append("行き先区分が重複している")
    table_names = [table["name"] for table in manifest["tables"]]
    tables_by_name = {table["name"]: table for table in manifest["tables"]}
    if len(table_names) != len(set(table_names)):
        violations.append("テーブル名が重複している")

    required_table_fields = {
        "name",
        "source_sections",
        "requirement_ids",
        "provenance",
        "columns",
        "lifecycle",
        "foreign_keys",
        "checks",
        "unique_constraints",
        "indexes",
        "forbidden_columns",
        "immutability",
    }
    for table in manifest["tables"]:
        name = table["name"]
        missing_fields = required_table_fields - set(table)
        if missing_fields:
            violations.append(f"{name}: 必須項目不足 {sorted(missing_fields)}")
            continue
        lifecycle = table["lifecycle"]
        if lifecycle["deletion"] not in _DELETION_LIFECYCLES:
            violations.append(f"{name}: 削除系統が不正")
        if lifecycle["append_mode"] not in _APPEND_MODES:
            violations.append(f"{name}: 追記専用性が不正")
        if lifecycle["migration_retirement"] not in _RETIREMENT_MODES:
            violations.append(f"{name}: 移行バッチ退役が不正")
        column_names = [column["name"] for column in table["columns"]]
        if len(column_names) != len(set(column_names)):
            violations.append(f"{name}: 列名が重複している")
        for column in table["columns"]:
            if set(column) != {"name", "type", "nullable", "default"}:
                violations.append(f"{name}: 列定義の項目が不正: {column.get('name')}")
        for foreign_key in table["foreign_keys"]:
            expected = {
                "name",
                "columns",
                "references",
                "match",
                "on_delete",
                "composite",
                "cross_tenant",
            }
            if set(foreign_key) != expected:
                violations.append(f"{name}: FK 定義の項目が不正")
                continue
            if not set(foreign_key["columns"]) <= set(column_names):
                violations.append(f"{name}: FK の構成列が存在しない")
            referenced_table_name = foreign_key["references"]["table"]
            referenced_table = tables_by_name.get(referenced_table_name)
            if referenced_table is None:
                violations.append(
                    f"{name}: FK 参照先表が存在しない: {referenced_table_name}"
                )
            elif not set(foreign_key["references"]["columns"]) <= {
                column["name"] for column in referenced_table["columns"]
            }:
                violations.append(f"{name}: FK 参照先列が存在しない")
            if len(foreign_key["columns"]) != len(foreign_key["references"]["columns"]):
                violations.append(f"{name}: FK の構成列数が一致しない")
        for constraint in table["unique_constraints"]:
            roles = set(constraint["roles"])
            if not roles or not roles <= _UNIQUE_ROLES:
                violations.append(f"{name}: 一意制約の役割タグが不正")
            if not set(constraint["columns"]) <= set(column_names):
                violations.append(f"{name}: 一意制約の構成列が存在しない")
            if "predicate" not in constraint:
                violations.append(f"{name}: 一意制約に述語全文がない")
            if "business_unique" in roles and "source_row" not in constraint:
                violations.append(f"{name}: business_unique に正本行がない")
        for index in table["indexes"]:
            if index["purpose"] not in {"lookup", "range_sort"}:
                violations.append(f"{name}: 索引用途が不正")
            index_columns = {column.split()[0] for column in index["columns"]}
            if not index_columns <= set(column_names):
                violations.append(f"{name}: 索引の構成列が存在しない")
        matrix_columns = set(table["immutability"]["protected_columns"]) | set(
            table["immutability"]["allowed_update_columns"]
        )
        if not matrix_columns <= set(column_names):
            violations.append(f"{name}: 不変列マトリクスの列が存在しない")
        if set(table["forbidden_columns"]) & set(column_names):
            violations.append(f"{name}: 禁止列が実列に含まれる")
        primary_keys = [
            constraint
            for constraint in table["unique_constraints"]
            if constraint["kind"] == "PRIMARY KEY"
        ]
        if len(primary_keys) != 1:
            violations.append(f"{name}: 主キーがちょうど 1 件ではない")

    business_rows = [
        (
            constraint["source_row"]["section"],
            constraint["source_row"]["uniqueness"],
            constraint["source_row"]["key_shape"],
            constraint["source_row"]["scope"],
        )
        for table in manifest["tables"]
        for constraint in table["unique_constraints"]
        if "business_unique" in constraint["roles"]
    ]
    if len(business_rows) != len(set(business_rows)):
        violations.append("business_unique の正本行が重複している")

    event_slots = next(
        table for table in manifest["tables"] if table["name"] == "event_slots"
    )
    slot_primary_key = next(
        constraint
        for constraint in event_slots["unique_constraints"]
        if constraint["kind"] == "PRIMARY KEY"
    )
    if set(slot_primary_key["roles"]) != _UNIQUE_ROLES:
        violations.append("event_slots の主キーが 3 役割タグを持たない")
    return violations


def _migration_table_names(migrations_path: Path) -> set[str]:
    """Migration ディレクトリを全走査して create_table の対象を返す。"""
    table_names: set[str] = set()
    for migration_path in migrations_path.rglob("*.py"):
        tree = ast.parse(migration_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            if node.func.attr != "create_table" or not node.args:
                continue
            first_argument = node.args[0]
            if isinstance(first_argument, ast.Constant) and isinstance(
                first_argument.value, str
            ):
                table_names.add(first_argument.value)
    return table_names


def _missing_implementation_tables(
    manifest_tables: set[str], model_tables: set[str], migration_tables: set[str]
) -> list[str]:
    """Models と migration の両方に揃っていない manifest 表を返す。"""
    return sorted(manifest_tables - (model_tables & migration_tables))


def test_manifest_is_bound_to_the_canonical_data_model() -> None:
    """実 manifest の SHA・参照・自己整合性を薄い層で検査する。"""
    manifest = _load_manifest()
    source = _DATA_MODEL_PATH.read_bytes()
    document = source.decode("utf-8")

    assert (
        _source_digest_violations(source, manifest["canonical_source"]["sha256"]) == []
    )
    assert _traceability_violations(document, manifest) == []
    assert _manifest_shape_violations(manifest) == []


def test_manifest_matches_the_two_canonical_tables_exactly() -> None:
    """正本 2 表と manifest の該当集合が exact-set 一致する。"""
    manifest = _load_manifest()
    document = _DATA_MODEL_PATH.read_text(encoding="utf-8")

    assert _business_uniqueness_violations(document, manifest) == []
    assert _destination_categories(document) == {
        entry["category"] for entry in manifest["legacy_destination_categories"]
    }
    assert _destination_categories(document) == _DESTINATION_CATEGORIES


def test_removing_one_manifest_business_unique_row_is_detected() -> None:
    """Manifest の業務的一意性を 1 行落とす負例が差分を返す。"""
    manifest = copy.deepcopy(_load_manifest())
    document = _DATA_MODEL_PATH.read_text(encoding="utf-8")
    removed: dict[str, Any] | None = None
    for table in manifest["tables"]:
        for index, constraint in enumerate(table["unique_constraints"]):
            if "business_unique" in constraint["roles"]:
                removed = table["unique_constraints"].pop(index)
                break
        if removed is not None:
            break

    assert removed is not None
    assert _business_uniqueness_violations(document, manifest) == [
        f"manifest に不足: {removed['source_row']['section']} / "
        f"{removed['source_row']['uniqueness']}"
    ]


def test_changed_canonical_digest_is_reported_as_stale() -> None:
    """正本 SHA を変えた負例が stale だけを返す。"""
    source = _DATA_MODEL_PATH.read_bytes()

    assert _source_digest_violations(source, "0" * 64) == [
        "stale: data-model.md の SHA-256 が " + "0" * 64 + " と一致しない"
    ]


def test_implemented_tables_are_manifested_while_schema_is_incomplete() -> None:
    """実装表が manifest 内にあり、全表実装前であることを検査する。"""
    manifest_tables = {table["name"] for table in _load_manifest()["tables"]}
    model_tables = set(Base.metadata.tables)
    migration_tables = _migration_table_names(_MIGRATIONS_PATH)

    missing = _missing_implementation_tables(
        manifest_tables, model_tables, migration_tables
    )

    assert (model_tables & migration_tables) <= manifest_tables
    assert missing


def test_one_sided_table_implementation_remains_missing() -> None:
    """Models または migration の片側だけにある表も欠落として扱う。"""
    manifest_tables = {"example"}

    assert _missing_implementation_tables(manifest_tables, {"example"}, set()) == [
        "example"
    ]
    assert _missing_implementation_tables(manifest_tables, set(), {"example"}) == [
        "example"
    ]
    assert (
        _missing_implementation_tables(manifest_tables, {"example"}, {"example"}) == []
    )
