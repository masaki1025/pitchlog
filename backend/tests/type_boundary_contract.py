"""3 層の型境界を判定する純関数を提供する。

移行イベントの列単位の保存先網羅(B5)は機械で閉じず、`N2` の受入証跡へ送る。
このモジュールは正本 12-1 節で判定済みの区分と、manifest の型宣言だけを検査し、
TSK-250 が所有する列単位の写像や値変換を先取りしない。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from test_schema_manifest import (
    _markdown_tables,
    _plain_markdown_cell,
    _section_body,
)

_DESTINATION_CATEGORY_ALIASES = {
    "スタメンのみ": "スタメン・出場区間",
}
_LEGACY_STORAGE_TYPE_TO_SQL = {
    "TEXT": "text",
    "REAL": "double precision",
    "INTEGER": "bigint",
    "TEXT(JSON 文字列)": "text",
}
_NORMALIZED_PAIRS = {
    47: ("raw_fielder_position", "resolved_fielder_id"),
    55: ("raw_error_position", "resolved_error_player_id"),
}
_EXCLUDED_PAYLOAD_CATEGORIES = frozenset({"導出", "移行時に使用"})
_RETAINED_SCHEMA_CATEGORIES = frozenset(
    {"試合", "プレイ行", "走者別表", "スタメン・出場区間", "保持のみ"}
)


@dataclass(frozen=True)
class PayloadCategoryDefinition:
    """移行イベントのペイロードに対する区分単位の定義。"""

    held_only_columns: frozenset[int]
    excluded_categories: frozenset[str]
    retained_schema_categories: frozenset[str]


MIGRATION_EVENT_PAYLOAD_DEFINITION = PayloadCategoryDefinition(
    held_only_columns=frozenset({72}),
    excluded_categories=_EXCLUDED_PAYLOAD_CATEGORIES,
    retained_schema_categories=_RETAINED_SCHEMA_CATEGORIES,
)


@dataclass(frozen=True)
class ColumnContract:
    """型境界に必要な列の構造。"""

    data_type: str
    nullable: bool
    default: str | None


def raw_payload_round_trip_violations(
    expected: dict[int, bytes], actual: dict[int, bytes]
) -> list[str]:
    """隔離原本の入力表と出力表の exact-set 差分を返す。

    Args:
        expected: 読み出し順序と入力バイト列。
        actual: 読み出し順序と DB から戻ったバイト列。

    Returns:
        入力と出力の差分。バイト列の内容自体はメッセージに含めない。
    """
    violations = [
        f"隔離原本の行が不足: source_read_order={order}"
        for order in sorted(expected.keys() - actual.keys())
    ]
    violations.extend(
        f"隔離原本に余剰行: source_read_order={order}"
        for order in sorted(actual.keys() - expected.keys())
    )
    violations.extend(
        f"隔離原本のバイト列が変化: source_read_order={order}"
        for order in sorted(expected.keys() & actual.keys())
        if expected[order] != actual[order]
    )
    return violations


def four_shape_violations(values: list[object]) -> list[str]:
    """`0`・`"0"`・空文字・NULL が相互に区別されるかを返す。

    Args:
        values: raw 行から復元した先頭 4 フィールド。

    Returns:
        4 形態の型と値が同一化された場合の違反。
    """
    expected = [("int", "0"), ("str", "'0'"), ("str", "''"), ("NoneType", "None")]
    actual = [(type(value).__name__, repr(value)) for value in values]
    if actual == expected:
        return []
    return [f"4 形態が同一性を保っていない: {actual!r}"]


def destination_columns(document: str) -> dict[str, frozenset[int]]:
    """正本 12-1 節の表を節見出しから探し、区分別の列番号を返す。

    Args:
        document: `data-model.md` 全文。

    Returns:
        正規化した行き先区分から旧列番号集合への対応。

    Raises:
        ValueError: 表の列番号・同上・重複が解決できない場合。
    """
    body = _section_body(document, "12-1")
    columns: dict[str, set[int]] = {}
    seen: set[int] = set()
    previous_category: str | None = None
    for headers, rows in _markdown_tables(body):
        number_header = "#" if "#" in headers else "列" if "列" in headers else None
        if number_header is None or "行き先" not in headers:
            continue
        number_index = headers.index(number_header)
        destination_index = headers.index("行き先")
        for row in rows:
            destination = _plain_markdown_cell(row[destination_index])
            if destination == "同上":
                if previous_category is None:
                    raise ValueError("12-1 節の行き先「同上」に先行区分がない")
                category = previous_category
            else:
                category = destination.split("(", maxsplit=1)[0]
                category = _DESTINATION_CATEGORY_ALIASES.get(category, category)
                previous_category = category
            for number in _expanded_column_numbers(row[number_index]):
                if number in seen:
                    raise ValueError(f"12-1 節の列番号が重複している: {number}")
                seen.add(number)
                columns.setdefault(category, set()).add(number)
    return {category: frozenset(numbers) for category, numbers in columns.items()}


def _expanded_column_numbers(value: str) -> range:
    """単一番号または閉区間の列番号表記を range にする。"""
    normalized = _plain_markdown_cell(value)
    match = re.fullmatch(r"(?P<start>\d+)(?:-(?P<end>\d+))?", normalized)
    if match is None:
        raise ValueError(f"12-1 節の列番号を解決できない: {normalized}")
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    return range(start, end + 1)


def payload_contract_violations(
    destinations: dict[str, frozenset[int]],
    definition: PayloadCategoryDefinition,
    manifest_categories: set[str],
    payload_column: ColumnContract,
) -> list[str]:
    """区分単位のペイロード保存契約と型宣言の違反を返す。

    Args:
        destinations: 正本 12-1 節から抽出した区分別の列番号。
        definition: TSK-250 の列写像を含まないペイロード区分定義。
        manifest_categories: Manifest が保持する 7 区分。
        payload_column: `operation_events.payload` の manifest 宣言。

    Returns:
        B1〜B4 の違反。列単位の写像(B5)は判定しない。
    """
    violations: list[str] = []
    if set(destinations) != manifest_categories:
        violations.append("正本 12-1 節と manifest の行き先区分が一致しない")
    if destinations.get("保持のみ", frozenset()) != definition.held_only_columns:
        violations.append("保持のみ列とペイロード区分定義が一致しない")
    if definition.excluded_categories != _EXCLUDED_PAYLOAD_CATEGORIES:
        violations.append("ペイロードから除外する区分が導出・移行時使用ではない")
    for category in definition.excluded_categories:
        overlap = destinations.get(category, frozenset()) & definition.held_only_columns
        if overlap:
            violations.append(
                f"{category}の列がペイロード区分定義へ混入: {sorted(overlap)}"
            )
    if definition.retained_schema_categories != _RETAINED_SCHEMA_CATEGORIES:
        if "移行時に使用" in definition.retained_schema_categories:
            violations.append("移行時に使用の区分が新スキーマ保持区分へ残っている")
        else:
            violations.append("新スキーマに保持する行き先区分が一致しない")
    if definition.retained_schema_categories - manifest_categories:
        violations.append("新スキーマ保持区分に正本外の区分がある")
    if payload_column != ColumnContract("jsonb", False, None):
        violations.append(
            "operation_events.payload が jsonb NOT NULL・既定値なしではない"
        )
    return violations


def legacy_storage_types(document: str) -> dict[int, str]:
    """旧 play_data 表から列 47・55 の保存型を表ヘッダで特定する。

    Args:
        document: `data-layer.md` 全文。

    Returns:
        旧列番号から保存型への対応。

    Raises:
        ValueError: 対象表または対象列が一意に解決できない場合。
    """
    matches: dict[int, str] = {}
    for headers, rows in _markdown_tables(document):
        if headers != ["#", "カラム名", "DB型", "意味", "値の例 / 初期値"]:
            continue
        for row in rows:
            number = _plain_markdown_cell(row[0])
            if number in {"47", "55"}:
                source_number = int(number)
                if source_number in matches:
                    raise ValueError(
                        f"旧 play_data の対象列が重複している: {source_number}"
                    )
                matches[source_number] = _plain_markdown_cell(row[2])
    if set(matches) != set(_NORMALIZED_PAIRS):
        raise ValueError("旧 play_data の列 47・55 の保存型を一意に解決できない")
    return matches


def regular_schema_violations(
    columns: dict[tuple[str, str], ColumnContract],
    source_types: dict[int, str],
) -> list[str]:
    """正規スキーマの原本列・解決列の C1〜C4 違反を返す。

    Args:
        columns: 実スキーマから取得した `(表, 列)` ごとの構造。
        source_types: 旧 play_data の対象列ごとの保存型。

    Returns:
        原本/解決列境界の違反。
    """
    violations: list[str] = []
    for source_number, (raw_name, resolved_name) in _NORMALIZED_PAIRS.items():
        raw = columns.get(("play_rows", raw_name))
        resolved = columns.get(("play_rows", resolved_name))
        if raw is None:
            violations.append(f"列 {source_number} の原本列がない: {raw_name}")
        if resolved is None:
            violations.append(f"列 {source_number} の解決列がない: {resolved_name}")
        source_type = source_types.get(source_number)
        expected_type = _LEGACY_STORAGE_TYPE_TO_SQL.get(source_type or "")
        if expected_type is None:
            violations.append(
                f"列 {source_number} の旧保存型を変換できない: {source_type!r}"
            )
        elif raw is not None and raw.data_type != expected_type:
            violations.append(
                f"列 {source_number} の原本列型が旧 {source_type} を"
                "損失なく保持しない: "
                f"{raw_name}={raw.data_type}, 期待={expected_type}"
            )
        if resolved is not None and resolved.data_type != "uuid":
            violations.append(f"列 {source_number} の解決列が uuid ではない")
        if resolved is not None and not resolved.nullable:
            violations.append(f"列 {source_number} の解決列が nullable ではない")
        if resolved is not None and resolved.default is not None:
            violations.append(f"列 {source_number} の解決列に既定値がある")

    final_lineup_columns = {
        name for table, name in columns if table == "migrated_final_lineups"
    }
    unexpected_resolved = sorted(
        name for name in final_lineup_columns if name.startswith("resolved_")
    )
    if unexpected_resolved:
        violations.append(f"移行元最終オーダーに解決列がある: {unexpected_resolved!r}")
    return violations


def sentinel_conversion_hits(source_root: Path) -> list[str]:
    """製品コードを全走査し、フィールド別センチネル変換候補を返す。

    Args:
        source_root: 人手でファイルを列挙しない走査起点。

    Returns:
        センチネル値を条件に NULL を生成する箇所と、明示的な変換名。
    """
    hits: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _SentinelConversionVisitor()
        visitor.visit(tree)
        relative = path.relative_to(source_root)
        hits.extend(f"{relative}:{line}:{reason}" for line, reason in visitor.hits)
    return hits


class _SentinelConversionVisitor(ast.NodeVisitor):
    """センチネル値から NULL を作る構造だけを抽出する。"""

    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:  # noqa: N802
        """明示的なセンチネル変換名と条件分岐を検査する。"""
        self._record_function_name(node.name, node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(  # noqa: N802
        self, node: ast.AsyncFunctionDef
    ) -> Any:
        """非同期関数の明示的なセンチネル変換名を検査する。"""
        self._record_function_name(node.name, node.lineno)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> Any:  # noqa: N802
        """センチネル比較から NULL を作る if 文を検査する。"""
        self._record_conditional(node.test, [*node.body, *node.orelse], node.lineno)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> Any:  # noqa: N802
        """センチネル比較から NULL を作る条件式を検査する。"""
        self._record_conditional(node.test, [node.body, node.orelse], node.lineno)
        self.generic_visit(node)

    def _record_conditional(
        self, condition: ast.AST, branches: list[ast.AST], line: int
    ) -> None:
        """条件がセンチネルを比較し分岐が NULL を作る場合だけ記録する。"""
        if not _contains_sentinel_literal(condition):
            return
        if any(
            isinstance(candidate, ast.Constant) and candidate.value is None
            for branch in branches
            for candidate in ast.walk(branch)
        ):
            self.hits.append((line, "センチネル比較から NULL を生成"))

    def _record_function_name(self, name: str, line: int) -> None:
        """関数名がセンチネル変換を明示する場合に記録する。"""
        normalized = name.casefold()
        if "sentinel" in normalized or "センチネル" in normalized:
            self.hits.append((line, f"変換関数名 {name}"))


def _contains_sentinel_literal(node: ast.AST) -> bool:
    """条件式が旧データの代表的なセンチネル値を含むか返す。"""
    for comparison in ast.walk(node):
        if not isinstance(comparison, ast.Compare):
            continue
        if any(
            _is_sentinel_operand(operand)
            for operand in [comparison.left, *comparison.comparators]
        ):
            return True
    return False


def _is_sentinel_operand(node: ast.AST) -> bool:
    """比較の直接オペランドが代表的なセンチネル値か返す。"""
    candidates = (
        node.elts if isinstance(node, (ast.List, ast.Set, ast.Tuple)) else [node]
    )
    for candidate in candidates:
        if not isinstance(candidate, ast.Constant):
            continue
        if type(candidate.value) is int and candidate.value == 0:
            return True
        if isinstance(candidate.value, str) and candidate.value in {"", "0"}:
            return True
    return False
