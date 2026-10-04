"""Alembic revision 全件の DDL 境界を静的に検査する。"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from sqlalchemy import String
from sqlalchemy.types import TypeEngine

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_VERSIONS_ROOT = _BACKEND_ROOT / "migrations" / "versions"
_ALLOWLIST_PATH = (
    _BACKEND_ROOT.parent / "contracts" / "migrations" / "seed-allowlist.json"
)
_FORBIDDEN_SQL = re.compile(
    r"(?:"
    r"CREATE\s+(?:POLICY|ROLE)\b|"
    r"ALTER\s+ROLE\b|"
    r"INSERT\s+INTO\b|"
    r"UPDATE\s+(?:ONLY\s+)?(?:[A-Za-z_][A-Za-z0-9_$]*|\"[^\"]+\")"
    r"(?:\.(?:[A-Za-z_][A-Za-z0-9_$]*|\"[^\"]+\"))?"
    r"(?:\s+(?:AS\s+)?(?:[A-Za-z_][A-Za-z0-9_$]*|\"[^\"]+\"))?"
    r"\s+SET\b|"
    r"DELETE\s+FROM\b"
    r")",
    re.IGNORECASE,
)
_FORBIDDEN_CALLS = {"bulk_insert", "create_all"}
_DELETE_SQL = re.compile(
    r"\s*DELETE\s+FROM\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s+WHERE\s+category\s*=\s*'(?P<category>(?:[^']|'')*)'"
    r"\s+AND\s+key\s+IN\s*\((?P<keys>'(?:[^']|'')*'"
    r"(?:\s*,\s*'(?:[^']|'')*')*)\)\s*;?\s*",
    re.IGNORECASE,
)
_DELETE_KEY = re.compile(r"'((?:[^']|'')*)'")


def _load_seed_allowlist() -> dict[str, Any]:
    """シード DML の許可とその更新履歴を宣言資産から読む。"""
    ledger: dict[str, Any] = json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return ledger


def _canonical_json(value: Any) -> str:
    """JSON の値型を保ち、キー順だけを正規化した文字列を返す。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _declaration_identity(declaration: Mapping[str, Any]) -> str:
    """系列宣言の正規 JSON に対する SHA-256 を返す。"""
    canonical = _canonical_json(declaration).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _assert_seed_allowlist_history(ledger: Mapping[str, Any]) -> None:
    """各系列の履歴が鎖を成し、最新の識別値が宣言を指すと確認する。"""
    assert ledger["asset_kind"] == "migration_seed_allowlist"
    declarations = ledger["declarations"]
    history = ledger["history"]
    assert isinstance(declarations, dict) and declarations
    assert isinstance(history, list)
    for series, declaration in declarations.items():
        records = [record for record in history if record["series"] == series]
        assert records, f"{series}: 7.7-2 の記録がない"
        latest = records[-1]
        expected = {
            "present": True,
            "values": [
                {
                    "kind": declaration["identity"],
                    "value": _declaration_identity(declaration),
                }
            ],
        }
        assert _canonical_json(latest["new_identity"]) == _canonical_json(expected), (
            f"{series}: 最新履歴と宣言が異なる"
        )
        for index, record in enumerate(records):
            assert record["changes"]
            assert record["approved_by"] and record["approved_at"]
            assert isinstance(record.get("fact"), str) and record["fact"].strip()
            assert isinstance(record.get("reason"), str) and record["reason"].strip()
            if index == 0:
                assert _canonical_json(record["prior_identity"]) == _canonical_json(
                    {"present": False, "values": []}
                )
            else:
                assert _canonical_json(record["prior_identity"]) == _canonical_json(
                    records[index - 1]["new_identity"]
                )
        if len(records) == 1:
            assert _canonical_json(records[0]["changes"]) == _canonical_json(
                [
                    {
                        "aspect": "declaration",
                        "before": {"absent": True},
                        "after": declaration,
                    }
                ]
            )


def _history_append_only_violation(
    base_history: list[Any], head_history: list[Any]
) -> str | None:
    """比較元の履歴が head の逐語 prefix でなければ理由を返す。

    Args:
        base_history: 比較元の履歴。
        head_history: 現在の履歴。

    Returns:
        削除・改変の位置を含む違反理由。追記だけなら ``None``。
    """
    if len(head_history) < len(base_history):
        return (
            f"history[{len(head_history)}]: 記録が削除された "
            f"(比較元 {len(base_history)} 件、head {len(head_history)} 件)"
        )
    for index, base_record in enumerate(base_history):
        if _canonical_json(head_history[index]) != _canonical_json(base_record):
            return f"history[{index}]: 既存記録が改変された (位置 {index + 1})"
    return None


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """リポジトリルートを指定して Git の CLI を実行する。

    Args:
        args: Git に渡す引数。

    Returns:
        標準出力・標準エラーを含む実行結果。
    """
    return subprocess.run(
        ("git", "-C", str(_BACKEND_ROOT.parent), *args),
        capture_output=True,
        text=True,
        check=False,
    )


def _base_seed_history() -> tuple[list[Any] | None, str, str]:
    """開発ブランチとの merge-base から比較元の履歴を読む。

    Returns:
        比較元の履歴、解決した ref、merge-base。資産が無ければ履歴は ``None``。
    """
    ref = next(
        (
            candidate
            for candidate in ("origin/develop", "develop")
            if _git("rev-parse", "--verify", candidate).returncode == 0
        ),
        None,
    )
    assert ref is not None, "origin/develop も develop も解決できない"

    merge = _git("merge-base", ref, "HEAD")
    assert merge.returncode == 0 and merge.stdout.strip(), (
        f"{ref} と HEAD の merge-base を取得できない: {merge.stderr.strip()}"
    )
    merge_base = merge.stdout.strip()
    asset_path = _ALLOWLIST_PATH.relative_to(_BACKEND_ROOT.parent).as_posix()
    base_asset = _git("show", f"{merge_base}:{asset_path}")
    if base_asset.returncode != 0:
        presence = _git("ls-tree", "--name-only", merge_base, "--", asset_path)
        assert presence.returncode == 0, (
            f"比較元の資産の有無を確認できない: {presence.stderr.strip()}"
        )
        assert not presence.stdout.strip(), (
            f"比較元に資産があるが読み出せない: {base_asset.stderr.strip()}"
        )
        return None, ref, merge_base

    base_history = json.loads(base_asset.stdout)["history"]
    assert isinstance(base_history, list), "比較元の history がリストでない"
    return base_history, ref, merge_base


def _assert_checker_has_no_frozen_values(
    ledger: Mapping[str, Any], source: str
) -> None:
    """許可の対象・値・行数が検査器に直書きされていないことを確認する。"""
    tree = ast.parse(source)
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    direct_row_counts = {
        part.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(
            isinstance(part, ast.Name) and part.id == "rows" for part in ast.walk(node)
        )
        for part in ast.walk(node)
        if isinstance(part, ast.Constant) and type(part.value) is int
    }
    for declaration in ledger["declarations"].values():
        allowed = declaration["allowed"]
        rows = allowed["upgrade_rows"]
        scope = allowed["downgrade_delete_scope"]
        assert all(target not in source for target in declaration["frozen_targets"])
        frozen_strings = {
            *allowed["target_tables"],
            rows["category"],
            *rows["keys"],
            scope["table"],
            scope["category"],
            *scope["keys"],
        }
        assert not string_literals.intersection(frozen_strings)
        assert rows["count"] not in direct_row_counts


def _declared_allowances(ledger: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """表示パスごとに、宣言した許可だけを対応付ける。"""
    allowances: dict[str, Mapping[str, Any]] = {}
    for declaration in ledger["declarations"].values():
        allowed = declaration["allowed"]
        for path in declaration["frozen_targets"]:
            assert path not in allowances, f"{path}: 許可対象が重複している"
            allowances[path] = allowed
    return allowances


def _call_name(node: ast.Call) -> str | None:
    """呼び出し式の末尾の名前を返す。"""
    function = node.func
    if isinstance(function, ast.Attribute):
        return function.attr
    if isinstance(function, ast.Name):
        return function.id
    return None


def _op_call(node: ast.Call, name: str) -> bool:
    """Alembic の ``op`` に対する指定 API の呼び出しかを返す。"""
    return (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        and node.func.attr == name
    )


def _sa_inspect_call(node: ast.AST | None, argument: ast.AST) -> bool:
    """指定ノードを引数に取る SQLAlchemy の inspect 呼び出しかを返す。"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sa"
        and node.func.attr == "inspect"
        and argument in node.args
    )


def _dialect_read_is_safe(node: ast.Attribute, parents: Mapping[int, ast.AST]) -> bool:
    """方言属性の参照が追加の呼び出しへ流れないことを確認する。"""
    current: ast.AST = node
    while True:
        parent = parents.get(id(current))
        if isinstance(parent, ast.Attribute) and parent.value is current:
            if parent.attr == "execute":
                return False
            current = parent
            continue
        return not isinstance(parent, ast.Call)


def _get_bind_usage_violations(
    tree: ast.Module,
    path: str,
    parents: Mapping[int, ast.AST],
    scopes: Mapping[int, int],
) -> list[str]:
    """接続取得結果の直接・束縛後の用途を保守的に検査する。

    Args:
        tree: revision の構文木。
        path: 違反表示用のパス。
        parents: 子ノードから親ノードへの対応。
        scopes: ノードから所属する関数への対応。

    Returns:
        接続経由の実行と追跡できない用途の違反一覧。
    """
    violations: list[str] = []
    bound_names: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _op_call(node, "get_bind"):
            continue
        parent = parents.get(id(node))
        if isinstance(parent, ast.Assign) and parent.value is node:
            if all(isinstance(target, ast.Name) for target in parent.targets):
                bound_names.update(
                    (scopes.get(id(node), id(tree)), target.id)
                    for target in parent.targets
                    if isinstance(target, ast.Name)
                )
                continue
        elif (
            isinstance(parent, ast.AnnAssign)
            and parent.value is node
            and isinstance(parent.target, ast.Name)
        ):
            bound_names.add((scopes.get(id(node), id(tree)), parent.target.id))
            continue
        elif isinstance(parent, ast.Expr) or _sa_inspect_call(parent, node):
            continue
        elif (
            isinstance(parent, ast.Attribute)
            and parent.value is node
            and parent.attr == "execute"
        ):
            violations.append(f"{path}:{node.lineno}: get_bind 経由の execute() は禁止")
            continue
        elif (
            isinstance(parent, ast.Attribute)
            and parent.value is node
            and parent.attr == "dialect"
            and _dialect_read_is_safe(parent, parents)
        ):
            continue
        violations.append(f"{path}:{node.lineno}: op.get_bind() の用途を追跡できない")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            continue
        scope = scopes.get(id(node), id(tree))
        if (scope, node.id) not in bound_names and (
            id(tree),
            node.id,
        ) not in bound_names:
            continue
        parent = parents.get(id(node))
        if isinstance(parent, ast.Expr) or _sa_inspect_call(parent, node):
            continue
        if isinstance(parent, ast.Attribute) and parent.value is node:
            if parent.attr == "dialect" and _dialect_read_is_safe(parent, parents):
                continue
            if parent.attr == "execute":
                violations.append(
                    f"{path}:{node.lineno}: get_bind 経由の execute() は禁止"
                )
                continue
        violations.append(f"{path}:{node.lineno}: get_bind の束縛先を追跡できない")
    return violations


def _sa_schema_call(node: ast.Call) -> bool:
    """SQLAlchemy の表・列・型の直接呼び出しかを返す。"""
    if (
        not isinstance(node.func, ast.Attribute)
        or not isinstance(node.func.value, ast.Name)
        or node.func.value.id != "sa"
    ):
        return False
    if node.func.attr in {"table", "column"}:
        return True
    candidate = getattr(sa, node.func.attr, None)
    return isinstance(candidate, type) and issubclass(candidate, TypeEngine)


def _literal_sql(node: ast.expr) -> ast.Constant | None:
    """直接の文字列または ``sa.text`` の文字列だけを取り出す。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sa"
        and node.func.attr == "text"
        and len(node.args) == 1
        and not node.keywords
    ):
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return argument
    return None


def _delete_matches_scope(sql: str, scope: Mapping[str, Any]) -> bool:
    """削除 SQL が宣言した表・区分・キーだけに閉じるかを返す。"""
    match = _DELETE_SQL.fullmatch(sql)
    if match is None:
        return False
    keys = [key.replace("''", "'") for key in _DELETE_KEY.findall(match["keys"])]
    return (
        match["table"] == scope["table"]
        and match["category"].replace("''", "'") == scope["category"]
        and len(keys) == len(scope["keys"])
        and set(keys) == set(scope["keys"])
    )


def _bulk_insert_matches(node: ast.Call, allowed: Mapping[str, Any]) -> bool:
    """投入先と行の集合を AST から読み、系列宣言と照合する。"""
    if not _op_call(node, "bulk_insert") or len(node.args) != 2 or node.keywords:
        return False
    table, rows = node.args
    if (
        not isinstance(table, ast.Call)
        or not isinstance(table.func, ast.Attribute)
        or not isinstance(table.func.value, ast.Name)
        or table.func.value.id != "sa"
        or table.func.attr != "table"
        or not table.args
        or not isinstance(table.args[0], ast.Constant)
        or not isinstance(table.args[0].value, str)
        or table.args[0].value not in allowed["target_tables"]
        or not isinstance(rows, ast.List)
    ):
        return False
    expected = allowed["upgrade_rows"]
    if len(rows.elts) != expected["count"]:
        return False
    keys: list[str] = []
    for row in rows.elts:
        if not isinstance(row, ast.Dict):
            return False
        fields: dict[str, Any] = {}
        for key_node, value_node in zip(row.keys, row.values, strict=True):
            if (
                not isinstance(key_node, ast.Constant)
                or not isinstance(key_node.value, str)
                or not isinstance(value_node, ast.Constant)
                or key_node.value in fields
            ):
                return False
            fields[key_node.value] = value_node.value
        if (
            not isinstance(fields.get("key"), str)
            or fields.get("category") != expected["category"]
        ):
            return False
        keys.append(fields["key"])
    return len(keys) == len(set(keys)) and set(keys) == set(expected["keys"])


def _migration_sources() -> dict[str, str]:
    """Versions 配下を走査して全 revision のソースを返す。"""
    paths = sorted(_VERSIONS_ROOT.rglob("*.py"))
    assert paths, "migration revision が 1 件もない"
    return {
        str(path.relative_to(_BACKEND_ROOT)): path.read_text(encoding="utf-8")
        for path in paths
    }


def _declared_revision_ids(sources: Mapping[str, str]) -> dict[str, str]:
    """各 revision のトップレベル ``revision`` 宣言を構文木から取り出す。"""
    revision_ids: dict[str, str] = {}
    for path, source in sorted(sources.items()):
        tree = ast.parse(source, filename=path)
        candidates: list[str] = []
        for statement in tree.body:
            target: ast.expr | None = None
            value: ast.expr | None = None
            if isinstance(statement, ast.AnnAssign):
                target = statement.target
                value = statement.value
            elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target = statement.targets[0]
                value = statement.value
            if (
                isinstance(target, ast.Name)
                and target.id == "revision"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                candidates.append(value.value)
        assert len(candidates) == 1, f"{path}: revision 宣言は 1 件必要"
        revision_ids[path] = candidates[0]
    return revision_ids


def _alembic_version_num_max_length() -> int:
    """Alembic が構築する管理表の実際の型定義から revision 上限を返す。"""
    context = MigrationContext.configure(dialect_name="postgresql")
    version_table = context.impl.version_table_impl(
        version_table="alembic_version",
        version_table_schema=None,
        version_table_pk=False,
    )
    version_num_type = version_table.c.version_num.type
    assert isinstance(version_num_type, String)
    assert version_num_type.length is not None
    return version_num_type.length


def _revision_id_length_violations(
    revision_ids: Mapping[str, str], maximum_length: int
) -> list[str]:
    """管理表の列幅を超える revision ID を返す。"""
    return [
        f"{path}: revision ID {revision_id!r} is {len(revision_id)} characters "
        f"(maximum {maximum_length})"
        for path, revision_id in sorted(revision_ids.items())
        if len(revision_id) > maximum_length
    ]


def _assert_revision_ids_fit_version_table(
    revision_ids: Mapping[str, str], maximum_length: int
) -> None:
    """全 revision ID が管理表の列幅に収まらなければ拒否する。"""
    assert _revision_id_length_violations(revision_ids, maximum_length) == []


def _migration_source_violations(
    sources: Mapping[str, str], *, ledger: Mapping[str, Any] | None = None
) -> list[str]:
    """Revision の Python 構文木から禁止 SQL と禁止 API の使用を返す。

    ``BEFORE UPDATE OR DELETE`` のようなトリガ DDL は文頭の DML 文ではないため、
    DML として数えない。

    Args:
        sources: 表示用パスと Python ソースの対応。
        ledger: 許可対象と許可範囲の宣言。省略時は資産から読む。

    Returns:
        パス・行番号・禁止要素だけを含む違反一覧。
    """
    if ledger is None:
        ledger = _load_seed_allowlist()
    allowances = _declared_allowances(ledger)
    violations: list[str] = []
    for path, source in sorted(sources.items()):
        tree = ast.parse(source, filename=path)
        allowed = allowances.get(path)
        function_by_node: dict[int, str] = {}
        scope_by_node: dict[int, int] = {}
        for statement in tree.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for descendant in ast.walk(statement):
                    function_by_node[id(descendant)] = statement.name
                    scope_by_node[id(descendant)] = id(statement)
        parents = {
            id(child): parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        violations.extend(
            _get_bind_usage_violations(tree, path, parents, scope_by_node)
        )
        accepted_delete_literals: set[int] = set()
        accepted_bulk_calls: set[int] = set()
        accepted_delete_calls: set[int] = set()
        accepted_text_calls: set[int] = set()
        table_argument_calls: set[int] = set()
        if allowed is not None:
            assert set(allowed["upgrade_calls"]).issubset(_FORBIDDEN_CALLS)
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr) or (
                    isinstance(node, ast.BinOp)
                    and isinstance(node.op, ast.Add)
                    and any(
                        isinstance(part, ast.Constant) and isinstance(part.value, str)
                        for part in ast.walk(node)
                    )
                ):
                    violations.append(
                        f"{path}:{node.lineno}: 文字列連結 SQL は解析できない"
                    )
                if not isinstance(node, ast.Call):
                    continue
                if (
                    _call_name(node) in allowed["upgrade_calls"]
                    and function_by_node.get(id(node)) == "upgrade"
                    and _bulk_insert_matches(node, allowed)
                ):
                    accepted_bulk_calls.add(id(node))
                    table_argument_calls.update(
                        id(descendant)
                        for descendant in ast.walk(node.args[0])
                        if isinstance(descendant, ast.Call)
                    )
                if (
                    _op_call(node, "execute")
                    and function_by_node.get(id(node)) == "downgrade"
                    and len(node.args) == 1
                    and not node.keywords
                ):
                    literal = _literal_sql(node.args[0])
                    if (
                        literal is not None
                        and isinstance(literal.value, str)
                        and _delete_matches_scope(
                            literal.value, allowed["downgrade_delete_scope"]
                        )
                    ):
                        accepted_delete_calls.add(id(node))
                        accepted_delete_literals.add(id(literal))
                        if isinstance(node.args[0], ast.Call):
                            accepted_text_calls.add(id(node.args[0]))
            if not accepted_bulk_calls:
                violations.append(f"{path}: upgrade() の許可 API が使われていない")
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                parent = parents.get(id(node))
                off_call_position = not (
                    isinstance(parent, ast.Call) and parent.func is node
                )
                if off_call_position and (
                    node.attr in _FORBIDDEN_CALLS
                    or (
                        allowed is not None
                        and isinstance(node.value, ast.Name)
                        and node.value.id == "op"
                    )
                ):
                    violations.append(
                        f"{path}:{node.lineno}: 禁止 API の属性参照 {node.attr}"
                    )
            if isinstance(node, ast.Call):
                name = _call_name(node)
                if name == "getattr":
                    violations.append(f"{path}:{node.lineno}: getattr() は禁止")
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "sa"
                    and node.func.attr in {"insert", "update", "delete"}
                ):
                    violations.append(
                        f"{path}:{node.lineno}: 禁止 SQLAlchemy DML "
                        f"sa.{node.func.attr}()"
                    )
                if allowed is not None and (
                    id(node) in accepted_bulk_calls
                    or id(node) in accepted_delete_calls
                    or id(node) in accepted_text_calls
                    or (id(node) in table_argument_calls and _sa_schema_call(node))
                ):
                    continue
                if name in _FORBIDDEN_CALLS:
                    violations.append(f"{path}:{node.lineno}: 禁止 API {name}()")
                elif allowed is not None:
                    violations.append(
                        f"{path}:{node.lineno}: seed revision の許可外 API {name}()"
                    )
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            for match in _FORBIDDEN_SQL.finditer(node.value):
                if id(node) in accepted_delete_literals and match[0].upper().startswith(
                    "DELETE"
                ):
                    continue
                line = node.lineno + node.value.count("\n", 0, match.start())
                statement = " ".join(match[0].split())
                violations.append(f"{path}:{line}: 禁止 SQL {statement}")
    return violations


def test_all_migration_revisions_contain_only_schema_ddl() -> None:
    """宣言した seed 以外の revision に権限 DDL・DML がないことを確認する。"""
    assert _migration_source_violations(_migration_sources()) == []


def test_seed_allowlist_values_are_externalized() -> None:
    """7.7-1: 許可の基準値が検査器のソースに直書きされていない。"""
    _assert_checker_has_no_frozen_values(
        _load_seed_allowlist(), Path(__file__).read_text(encoding="utf-8")
    )


def test_seed_allowlist_row_count_literal_is_rejected() -> None:
    """宣言行数を検査器の比較式へ直書きした場合は拒否する。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    count = declaration["allowed"]["upgrade_rows"]["count"]
    source = Path(__file__).read_text(encoding="utf-8")
    source += f"\ndef synthetic_guard(rows):\n    return len(rows) == {count}\n"

    with pytest.raises(AssertionError):
        _assert_checker_has_no_frozen_values(ledger, source)


def test_seed_allowlist_history_matches_current_declaration() -> None:
    """7.7-2: 最新の更新記録が現在の系列宣言を指している。"""
    _assert_seed_allowlist_history(_load_seed_allowlist())


@pytest.mark.parametrize("case", ("empty_fact", "missing_reason", "broken_chain"))
def test_seed_allowlist_history_missing_fields_or_broken_chain_is_red(
    case: str,
) -> None:
    """事実・理由の欠落と識別値の鎖の断絶を拒否する。

    Args:
        case: 履歴への変異の種類。
    """
    ledger = copy.deepcopy(_load_seed_allowlist())
    if case == "empty_fact":
        ledger["history"][-1]["fact"] = ""
    elif case == "missing_reason":
        del ledger["history"][-1]["reason"]
    else:
        assert case == "broken_chain"
        later = copy.deepcopy(ledger["history"][-1])
        later["prior_identity"] = {"present": False, "values": []}
        ledger["history"].append(later)

    with pytest.raises(AssertionError):
        _assert_seed_allowlist_history(ledger)


def test_seed_allowlist_history_connected_chain_is_green() -> None:
    """2 件目の直前識別値が前件へつながれば受け入れる。"""
    ledger = copy.deepcopy(_load_seed_allowlist())
    later = copy.deepcopy(ledger["history"][-1])
    later["prior_identity"] = copy.deepcopy(ledger["history"][-1]["new_identity"])
    ledger["history"].append(later)

    _assert_seed_allowlist_history(ledger)


def test_seed_allowlist_history_is_append_only_against_base() -> None:
    """実資産の履歴が比較元の全記録を逐語的に保っている。"""
    head_history = _load_seed_allowlist()["history"]
    base_history, ref, merge_base = _base_seed_history()
    if base_history is None:
        print(f"7.7-2 append-only: 初回例外 ({ref}, merge-base={merge_base[:12]})")
        return

    print(
        "7.7-2 append-only: 比較元と比較 "
        f"({ref}, merge-base={merge_base[:12]}, 比較元={len(base_history)} 件)"
    )
    violation = _history_append_only_violation(base_history, head_history)
    assert violation is None, violation


@pytest.mark.parametrize(
    ("case", "expected_word", "expected_position"),
    (
        ("rewritten_fact", "改変", "history[0]"),
        ("deleted_record", "削除", "history[1]"),
        ("reordered_records", "改変", "history[0]"),
    ),
)
def test_seed_allowlist_history_append_only_mutations_are_red(
    case: str, expected_word: str, expected_position: str
) -> None:
    """既存記録の改変・削除・入れ替えを位置付きで拒否する。

    Args:
        case: 合成履歴への変異。
        expected_word: 違反の種類。
        expected_position: 最初に違反した位置。
    """
    base_history = [{"fact": "first"}, {"fact": "second"}]
    head_history = copy.deepcopy(base_history)
    if case == "rewritten_fact":
        head_history[0]["fact"] = "changed"
    elif case == "deleted_record":
        head_history.pop()
    else:
        assert case == "reordered_records"
        head_history.reverse()

    violation = _history_append_only_violation(base_history, head_history)
    assert violation is not None
    assert expected_word in violation
    assert expected_position in violation


def test_seed_allowlist_history_append_only_accepts_appended_record() -> None:
    """末尾への追記なら既存履歴を保ったまま受け入れる。"""
    base_history = [{"fact": "first"}]
    head_history = [*copy.deepcopy(base_history), {"fact": "second"}]

    assert _history_append_only_violation(base_history, head_history) is None


@pytest.mark.parametrize("case", ("boolean_as_integer", "integer_as_float"))
def test_seed_allowlist_history_append_only_distinguishes_json_types(case: str) -> None:
    """JSON の真偽値と数値の型を変えた既存記録を拒否する。

    Args:
        case: JSON 値型の変異。
    """
    base_history = copy.deepcopy(_load_seed_allowlist()["history"])
    head_history = copy.deepcopy(base_history)
    if case == "boolean_as_integer":
        assert head_history[0]["new_identity"]["present"] is True
        head_history[0]["new_identity"]["present"] = 1
    else:
        assert case == "integer_as_float"
        upgrade_rows = head_history[0]["changes"][0]["after"]["allowed"]["upgrade_rows"]
        assert type(upgrade_rows["count"]) is int
        upgrade_rows["count"] = float(upgrade_rows["count"])

    violation = _history_append_only_violation(base_history, head_history)
    assert violation is not None
    assert "改変" in violation
    assert "history[0]" in violation


def test_seed_allowlist_history_append_only_ignores_key_order() -> None:
    """JSON オブジェクトのキー順だけが変わった記録を受け入れる。"""
    base_history = copy.deepcopy(_load_seed_allowlist()["history"])
    head_history = copy.deepcopy(base_history)
    head_history[0] = dict(reversed(list(head_history[0].items())))
    assert list(head_history[0]) != list(base_history[0])

    assert _history_append_only_violation(base_history, head_history) is None


def test_seed_allowlist_history_identity_rejects_boolean_as_integer() -> None:
    """最新の識別値で JSON の真偽値を整数に変えると拒否する。"""
    ledger = copy.deepcopy(_load_seed_allowlist())
    assert ledger["history"][-1]["new_identity"]["present"] is True
    ledger["history"][-1]["new_identity"]["present"] = 1

    with pytest.raises(AssertionError, match="最新履歴と宣言が異なる"):
        _assert_seed_allowlist_history(ledger)


def test_seed_allowlist_history_changes_rejects_integer_as_float() -> None:
    """初回記録の変更内容でも整数と浮動小数点数を区別する。"""
    ledger = copy.deepcopy(_load_seed_allowlist())
    upgrade_rows = ledger["history"][0]["changes"][0]["after"]["allowed"][
        "upgrade_rows"
    ]
    upgrade_rows["count"] = float(upgrade_rows["count"])

    with pytest.raises(AssertionError):
        _assert_seed_allowlist_history(ledger)


def test_declaration_identity_distinguishes_json_scalar_types() -> None:
    """宣言の識別値でも真偽値と数値の JSON 値型を区別する。"""
    declaration = copy.deepcopy(
        next(iter(_load_seed_allowlist()["declarations"].values()))
    )
    float_declaration = copy.deepcopy(declaration)
    upgrade_rows = float_declaration["allowed"]["upgrade_rows"]
    upgrade_rows["count"] = float(upgrade_rows["count"])
    assert _declaration_identity(declaration) != _declaration_identity(
        float_declaration
    )

    declaration["type_probe"] = True
    integer_declaration = copy.deepcopy(declaration)
    integer_declaration["type_probe"] = 1
    assert _declaration_identity(declaration) != _declaration_identity(
        integer_declaration
    )


def test_all_migration_revision_ids_fit_alembic_version_table() -> None:
    """全 revision ID が Alembic 管理表の実際の列幅に収まることを確認する。"""
    sources = _migration_sources()
    revision_ids = _declared_revision_ids(sources)

    assert len(revision_ids) == len(sources)
    _assert_revision_ids_fit_version_table(
        revision_ids, _alembic_version_num_max_length()
    )


def test_revision_id_length_negative_case_is_red() -> None:
    """列幅を 1 文字超える合成 revision を全数母集団へ混ぜると検出する。"""
    maximum_length = _alembic_version_num_max_length()
    revision_ids = _declared_revision_ids(_migration_sources())
    synthetic_path = "migrations/versions/synthetic_too_long.py"
    synthetic_revision = "x" * (maximum_length + 1)
    revision_ids[synthetic_path] = synthetic_revision

    expected_violation = (
        f"{synthetic_path}: revision ID {synthetic_revision!r} is "
        f"{len(synthetic_revision)} characters (maximum {maximum_length})"
    )
    with pytest.raises(AssertionError) as exc_info:
        _assert_revision_ids_fit_version_table(revision_ids, maximum_length)

    assert expected_violation in str(exc_info.value)


@pytest.mark.parametrize(
    "source",
    (
        "op.execute('CREATE POLICY sample ON games')",
        "op.execute('CREATE ROLE sample')",
        "op.execute('ALTER ROLE sample LOGIN')",
        "op.execute('INSERT INTO games DEFAULT VALUES')",
        "op.execute('UPDATE games SET status = 1')",
        "op.execute('DELETE FROM games')",
        "op.bulk_insert(table, [])",
        "Base.metadata.create_all()",
    ),
)
def test_migration_hygiene_negative_cases_are_red(source: str) -> None:
    """禁止事項を 1 件含む合成 revision を検査器が必ず拒否する。"""
    assert _migration_source_violations({"synthetic.py": source})


@pytest.mark.parametrize("operation", ("insert", "update", "delete"))
def test_undeclared_revision_rejects_sqlalchemy_dml(operation: str) -> None:
    """宣言外 revision の get_bind と SQLAlchemy DML を拒否する。

    Args:
        operation: SQLAlchemy の DML 呼び出し名。
    """
    expression = f"sa.{operation}(table)"
    if operation != "delete":
        expression += ".values(value=1)"
    source = f"op.get_bind().execute({expression})"

    violations = _migration_source_violations({"synthetic.py": source})
    assert any(
        "get_bind 経由の execute() は禁止" in violation for violation in violations
    )
    assert any(
        f"禁止 SQLAlchemy DML sa.{operation}()" in violation for violation in violations
    )


def test_get_bind_metadata_reads_are_green() -> None:
    """接続の方言情報とカタログ参照は DDL revision で許す。"""
    source = """
def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.create_index("ix_probe", "probe", ["id"])
    version = op.get_bind().dialect.server_version_info
    inspector = sa.inspect(op.get_bind())
    bind = op.get_bind()
    dialect_name = bind.dialect.name
"""

    assert _migration_source_violations({"synthetic.py": source}) == []


def test_get_bind_direct_execute_is_red() -> None:
    """接続結果から直接 SQL を実行する形を拒否する。"""
    source = (
        "def upgrade():\n    op.get_bind().execute(sa.insert(table).values(value=1))\n"
    )

    violations = _migration_source_violations({"synthetic.py": source})
    assert any(
        "get_bind 経由の execute() は禁止" in violation for violation in violations
    )


def test_get_bind_bound_execute_is_red() -> None:
    """束縛した接続名から SQL を実行する形を拒否する。"""
    source = "def upgrade():\n    bind = op.get_bind()\n    bind.execute('SELECT 1')\n"

    violations = _migration_source_violations({"synthetic.py": source})
    assert any(
        "get_bind 経由の execute() は禁止" in violation for violation in violations
    )

    aliased_source = (
        "def upgrade():\n"
        "    bind = op.get_bind()\n"
        "    alias = bind\n"
        "    alias.execute('SELECT 1')\n"
    )
    aliased_violations = _migration_source_violations({"synthetic.py": aliased_source})
    assert any("get_bind の束縛先を追跡できない" in item for item in aliased_violations)

    module_binding = (
        "bind = op.get_bind()\ndef upgrade():\n    bind.execute('SELECT 1')\n"
    )
    module_violations = _migration_source_violations({"synthetic.py": module_binding})
    assert any("get_bind 経由の execute() は禁止" in item for item in module_violations)


def test_trigger_event_words_are_not_mistaken_for_dml() -> None:
    """トリガ DDL の UPDATE・DELETE は DML 禁止へ誤算入しない。"""
    source = '''
op.execute(
    """
    CREATE TRIGGER sample BEFORE UPDATE OR DELETE ON games
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation()
    """
)
'''

    assert _migration_source_violations({"synthetic.py": source}) == []


def _synthetic_seed_source(
    allowed: Mapping[str, Any],
    *,
    rows: list[dict[str, str]] | None = None,
    delete_keys: list[str] | None = None,
    extra_upgrade: str = "",
) -> str:
    """系列宣言の値から、検査用の seed revision を組み立てる。"""
    expected = allowed["upgrade_rows"]
    scope = allowed["downgrade_delete_scope"]
    if rows is None:
        rows = [
            {"key": key, "category": expected["category"], "display_name": key}
            for key in expected["keys"]
        ]
    if delete_keys is None:
        delete_keys = scope["keys"]
    key_sql = ", ".join(repr(key) for key in delete_keys)
    delete_sql = (
        f"DELETE FROM {scope['table']} WHERE category = {scope['category']!r} "
        f"AND key IN ({key_sql})"
    )
    return (
        "def upgrade():\n"
        f"    op.bulk_insert(sa.table({allowed['target_tables'][0]!r}), {rows!r})\n"
        f"{extra_upgrade}"
        "\n"
        "def downgrade():\n"
        f"    op.execute({delete_sql!r})\n"
    )


def _synthetic_seed_with_text_delete(
    allowed: Mapping[str, Any],
    *,
    delete_keys: list[str] | None = None,
    dynamic: bool = False,
) -> str:
    """合成 revision の限定削除を sa.text 呼び出しで包む。

    Args:
        allowed: 系列宣言の許可範囲。
        delete_keys: 削除するキー。省略時は宣言の集合。
        dynamic: SQL 引数を定数でなく変数にするか。

    Returns:
        変異後の合成 revision ソース。
    """
    tree = ast.parse(_synthetic_seed_source(allowed, delete_keys=delete_keys))
    execute = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _op_call(node, "execute")
    )
    argument = ast.Name(id="sql", ctx=ast.Load()) if dynamic else execute.args[0]
    execute.args[0] = ast.Call(
        func=ast.Attribute(
            value=ast.Name(id="sa", ctx=ast.Load()), attr="text", ctx=ast.Load()
        ),
        args=[argument],
        keywords=[],
    )
    return ast.unparse(ast.fix_missing_locations(tree))


def _synthetic_seed_sources(tmp_path: Path, path: str, source: str) -> dict[str, str]:
    """一時ファイルの合成 revision を検査器の入力へ渡す。"""
    revision_file = tmp_path / "synthetic_revision.py"
    revision_file.write_text(source, encoding="utf-8")
    return {path: revision_file.read_text(encoding="utf-8")}


def test_declared_seed_revision_synthetic_positive_is_green(tmp_path: Path) -> None:
    """宣言した表・行・区分・キーへの投入と限定削除だけを許す。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    path = declaration["frozen_targets"][0]
    source = _synthetic_seed_source(declaration["allowed"])

    assert (
        _migration_source_violations(
            _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
        )
        == []
    )


def test_declared_seed_text_wrapped_delete_is_green(tmp_path: Path) -> None:
    """宣言の削除範囲なら sa.text で包んだ定数 SQL も許す。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    path = declaration["frozen_targets"][0]
    source = _synthetic_seed_with_text_delete(declaration["allowed"])

    assert (
        _migration_source_violations(
            _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
        )
        == []
    )


@pytest.mark.parametrize(
    ("case", "expected_violation"),
    (
        ("broader", "禁止 SQL DELETE FROM"),
        ("dynamic", "seed revision の許可外 API text()"),
    ),
)
def test_declared_seed_text_wrapped_delete_outside_scope_is_red(
    tmp_path: Path, case: str, expected_violation: str
) -> None:
    """sa.text でも削除範囲の拡大と動的 SQL を拒否する。

    Args:
        tmp_path: 合成 revision の一時配置先。
        case: 範囲拡大または動的 SQL。
        expected_violation: 検出すべき違反文言。
    """
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    allowed = declaration["allowed"]
    path = declaration["frozen_targets"][0]
    if case == "broader":
        delete_keys = [*allowed["downgrade_delete_scope"]["keys"], "outside"]
        source = _synthetic_seed_with_text_delete(allowed, delete_keys=delete_keys)
    else:
        assert case == "dynamic"
        source = _synthetic_seed_with_text_delete(allowed, dynamic=True)

    violations = _migration_source_violations(
        _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
    )
    assert any(expected_violation in violation for violation in violations)


@pytest.mark.parametrize(
    ("case", "expected_violation"),
    (
        ("alias", "禁止 API の属性参照 bulk_insert"),
        ("getattr", "getattr() は禁止"),
    ),
)
def test_declared_seed_rejects_indirect_dml_calls(
    tmp_path: Path, case: str, expected_violation: str
) -> None:
    """宣言対象でも属性の束縛と動的呼び出しを拒否する。

    Args:
        tmp_path: 合成 revision の一時配置先。
        case: 間接呼び出しの種類。
        expected_violation: 検出すべき違反文言。
    """
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    allowed = declaration["allowed"]
    table = allowed["target_tables"][0]
    if case == "alias":
        extra_upgrade = f"    f = op.bulk_insert\n    f(sa.table({table!r}), [])\n"
    else:
        assert case == "getattr"
        extra_upgrade = f"    getattr(op, 'bulk_insert')(sa.table({table!r}), [])\n"
    source = _synthetic_seed_source(allowed, extra_upgrade=extra_upgrade)
    path = declaration["frozen_targets"][0]

    violations = _migration_source_violations(
        _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
    )
    assert any(expected_violation in violation for violation in violations)


@pytest.mark.parametrize(
    "extra_upgrade",
    (
        "    helper()\n",
        "    op.get_bind()\n",
        "    sa.table('outside')\n",
    ),
)
def test_declared_seed_rejects_calls_outside_allowlist(
    tmp_path: Path, extra_upgrade: str
) -> None:
    """宣言対象の追加呼び出しは許可された表定義内以外なら拒否する。

    Args:
        tmp_path: 合成 revision の一時配置先。
        extra_upgrade: upgrade に追加する呼び出し。
    """
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    source = _synthetic_seed_source(declaration["allowed"], extra_upgrade=extra_upgrade)
    path = declaration["frozen_targets"][0]

    violations = _migration_source_violations(
        _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
    )
    assert any("seed revision の許可外 API" in violation for violation in violations)


@pytest.mark.parametrize(
    ("source", "expected_violation"),
    (
        ("getattr(object(), 'anything')", "getattr() は禁止"),
        ("handler = op.bulk_insert", "禁止 API の属性参照 bulk_insert"),
        ("handlers = [op.create_all]", "禁止 API の属性参照 create_all"),
    ),
)
def test_undeclared_revision_rejects_dynamic_or_bound_dml(
    source: str, expected_violation: str
) -> None:
    """宣言外の revision でも動的呼び出しと禁止 API の束縛を拒否する。

    Args:
        source: 合成 revision のソース。
        expected_violation: 検出すべき違反文言。
    """
    violations = _migration_source_violations({"synthetic.py": source})
    assert any(expected_violation in violation for violation in violations)


def test_declared_seed_allows_repeated_matching_calls(tmp_path: Path) -> None:
    """宣言と照合できる投入呼び出しの件数は固定しない。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    allowed = declaration["allowed"]
    rows = [
        {
            "key": key,
            "category": allowed["upgrade_rows"]["category"],
            "display_name": key,
        }
        for key in allowed["upgrade_rows"]["keys"]
    ]
    extra_upgrade = (
        f"    op.bulk_insert(sa.table({allowed['target_tables'][0]!r}), {rows!r})\n"
    )
    source = _synthetic_seed_source(allowed, extra_upgrade=extra_upgrade)
    path = declaration["frozen_targets"][0]

    assert (
        _migration_source_violations(
            _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
        )
        == []
    )


@pytest.mark.parametrize(
    "case",
    (
        "unlisted_revision",
        "checker_literal",
        "history_not_updated",
        "broader_downgrade",
        "second_table",
        "extra_row",
        "wrong_category",
    ),
)
def test_declared_seed_revision_synthetic_negative_is_red(
    tmp_path: Path, case: str
) -> None:
    """7.7 と投入・削除の 7 つの負例がそれぞれ red になる。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    allowed = declaration["allowed"]
    path = declaration["frozen_targets"][0]
    rows = [
        {
            "key": key,
            "category": allowed["upgrade_rows"]["category"],
            "display_name": key,
        }
        for key in allowed["upgrade_rows"]["keys"]
    ]
    source = _synthetic_seed_source(allowed)
    if case == "unlisted_revision":
        path = "synthetic.py"
    elif case == "checker_literal":
        with pytest.raises(AssertionError):
            _assert_checker_has_no_frozen_values(
                ledger, Path(__file__).read_text(encoding="utf-8") + repr(path)
            )
        return
    elif case == "history_not_updated":
        changed_ledger = copy.deepcopy(ledger)
        changed = next(iter(changed_ledger["declarations"].values()))
        changed["allowed"]["upgrade_rows"]["count"] += 1
        with pytest.raises(AssertionError):
            _assert_seed_allowlist_history(changed_ledger)
        return
    elif case == "broader_downgrade":
        source = _synthetic_seed_source(
            allowed, delete_keys=[*allowed["downgrade_delete_scope"]["keys"], "outside"]
        )
    elif case == "second_table":
        source = _synthetic_seed_source(
            allowed,
            extra_upgrade=f"    op.bulk_insert(sa.table('outside'), {rows!r})\n",
        )
    elif case == "extra_row":
        rows.append(
            {
                "key": "outside",
                "category": allowed["upgrade_rows"]["category"],
                "display_name": "outside",
            }
        )
        source = _synthetic_seed_source(allowed, rows=rows)
    elif case == "wrong_category":
        rows[0]["category"] = "outside"
        source = _synthetic_seed_source(allowed, rows=rows)

    assert _migration_source_violations(
        _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
    )


@pytest.mark.parametrize(
    "extra_upgrade",
    (
        "    op.execute('CREATE POLICY sample ON sample')\n",
        "    op.execute('CREATE ROLE sample')\n",
        "    op.execute('ALTER ROLE sample LOGIN')\n",
        "    op.execute('UPDATE sample SET value = 1')\n",
        "    op.execute('INSERT INTO sample DEFAULT VALUES')\n",
        "    Base.metadata.create_all()\n",
    ),
)
def test_declared_seed_still_rejects_existing_prohibitions(
    tmp_path: Path, extra_upgrade: str
) -> None:
    """Seed 許可対象でも既存の権限 DDL・DML・create_all を拒否する。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    path = declaration["frozen_targets"][0]
    source = _synthetic_seed_source(declaration["allowed"], extra_upgrade=extra_upgrade)

    assert _migration_source_violations(
        _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
    )


@pytest.mark.parametrize(
    "replacement",
    (
        "op.bulk_insert()",
        "op.bulk_insert(sa.table(table_name), [])",
        "op.bulk_insert(sa.table(table_name), tuple())",
        "op.bulk_insert(sa.table(table_name), rows)",
    ),
)
def test_declared_seed_rejects_unparseable_bulk_insert(
    tmp_path: Path, replacement: str
) -> None:
    """表名・投入行を AST で確定できない bulk_insert は拒否する。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    path = declaration["frozen_targets"][0]
    source = _synthetic_seed_source(declaration["allowed"])
    tree = ast.parse(source)
    bulk_call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) == "bulk_insert"
    )
    lines = source.splitlines(keepends=True)
    lines[bulk_call.lineno - 1] = f"    {replacement}\n"

    assert _migration_source_violations(
        _synthetic_seed_sources(tmp_path, path, "".join(lines)), ledger=ledger
    )


def test_declared_seed_rejects_concatenated_sql(tmp_path: Path) -> None:
    """SQL の文字列連結で DML 検査を避ける形を拒否する。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    path = declaration["frozen_targets"][0]
    source = _synthetic_seed_source(declaration["allowed"])
    source = source.replace(
        "def downgrade():",
        "def downgrade():\n    op.execute('DEL' + 'ETE FROM outside')",
    )

    assert _migration_source_violations(
        _synthetic_seed_sources(tmp_path, path, source), ledger=ledger
    )


def _real_seed_revision() -> tuple[dict[str, Any], str, str]:
    """系列宣言が指す実 revision の表示パスとソースを返す。"""
    ledger = _load_seed_allowlist()
    declaration = next(iter(ledger["declarations"].values()))
    path = declaration["frozen_targets"][0]
    revision_file = (_BACKEND_ROOT / path).resolve()
    assert revision_file.is_relative_to(_VERSIONS_ROOT.resolve())
    return ledger, path, revision_file.read_text(encoding="utf-8")


def _replace_ast_expression(source: str, node: ast.expr, replacement: str) -> str:
    """構文木が示す式の範囲だけをソース文字列内で置き換える。

    Args:
        source: 実 revision のソース。
        node: 置換対象の式。
        replacement: 置換後の Python 式。

    Returns:
        対象式だけを置き換えたソース。
    """
    assert node.end_lineno is not None and node.end_col_offset is not None
    lines = source.splitlines(keepends=True)

    def offset(lineno: int, byte_column: int) -> int:
        """UTF-8 のバイト列位置をソース文字列内の文字位置へ変換する。"""
        line_prefix = lines[lineno - 1].encode("utf-8")[:byte_column]
        return sum(len(line) for line in lines[: lineno - 1]) + len(
            line_prefix.decode("utf-8")
        )

    start = offset(node.lineno, node.col_offset)
    end = offset(node.end_lineno, node.end_col_offset)
    return source[:start] + replacement + source[end:]


def _real_revision_function(source: str, name: str) -> ast.FunctionDef:
    """実 revision の指定関数を構文木から一意に取り出す。"""
    functions = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(functions) == 1
    return functions[0]


def _real_revision_op_call(function: ast.FunctionDef, name: str) -> ast.Call:
    """関数内の指定 Alembic 呼び出しを構文木から一意に取り出す。"""
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and _op_call(node, name)
    ]
    assert len(calls) == 1
    return calls[0]


def _mutate_real_seed_revision(
    source: str, case: str, allowed: Mapping[str, Any]
) -> str:
    """実 revision の指定した一箇所だけを検査用に変異させる。

    Args:
        source: 実 revision のソース。
        case: 変異の種類。
        allowed: 系列宣言が定める投入先・投入行・削除範囲。

    Returns:
        変異を加えたソース。実ファイルは変更しない。
    """
    if case in {"second_table", "extra_row"}:
        call = _real_revision_op_call(
            _real_revision_function(source, "upgrade"), "bulk_insert"
        )
        table = call.args[0]
        assert isinstance(table, ast.Call)
        assert isinstance(table.args[0], ast.Constant)
        assert table.args[0].value in allowed["target_tables"]
        if case == "second_table":
            assert "outside" not in allowed["target_tables"]
            extra_call = copy.deepcopy(call)
            table = extra_call.args[0]
            assert isinstance(table, ast.Call)
            table.args[0] = ast.Constant(value="outside")
            assert call.end_lineno is not None
            lines = source.splitlines(keepends=True)
            lines.insert(call.end_lineno, f"    {ast.unparse(extra_call)}\n")
            return "".join(lines)

        rows = call.args[1]
        assert isinstance(rows, ast.List) and rows.elts
        assert len(rows.elts) == allowed["upgrade_rows"]["count"]
        assert "outside" not in allowed["upgrade_rows"]["keys"]
        expanded_rows = copy.deepcopy(rows)
        extra_row = copy.deepcopy(rows.elts[0])
        assert isinstance(extra_row, ast.Dict)
        key_positions = [
            index
            for index, key in enumerate(extra_row.keys)
            if isinstance(key, ast.Constant) and key.value == "key"
        ]
        assert len(key_positions) == 1
        extra_row.values[key_positions[0]] = ast.Constant(value="outside")
        expanded_rows.elts.append(extra_row)
        return _replace_ast_expression(source, rows, ast.unparse(expanded_rows))

    assert case == "broader_downgrade"
    call = _real_revision_op_call(
        _real_revision_function(source, "downgrade"), "execute"
    )
    assert len(call.args) == 1
    literal = _literal_sql(call.args[0])
    assert literal is not None and isinstance(literal.value, str)
    match = _DELETE_SQL.fullmatch(literal.value)
    assert match is not None
    scope = allowed["downgrade_delete_scope"]
    assert match["table"] == scope["table"]
    assert match["category"] == scope["category"]
    assert set(_DELETE_KEY.findall(match["keys"])) == set(scope["keys"])
    assert "outside" not in scope["keys"]
    expanded_sql = (
        literal.value[: match.end("keys")]
        + ", 'outside'"
        + literal.value[match.end("keys") :]
    )
    return _replace_ast_expression(source, literal, repr(expanded_sql))


def test_real_seed_revision_is_green() -> None:
    """変異前の実 revision が DML 境界検査を通ることを確認する。"""
    ledger, path, source = _real_seed_revision()
    assert _migration_source_violations({path: source}, ledger=ledger) == []


@pytest.mark.parametrize(
    ("case", "expected_violation"),
    (
        ("second_table", "禁止 API bulk_insert()"),
        ("extra_row", "禁止 API bulk_insert()"),
        ("broader_downgrade", "禁止 SQL DELETE FROM"),
    ),
)
def test_real_seed_revision_mutations_are_red(
    case: str, expected_violation: str
) -> None:
    """実 revision の別表・追加行・削除拡大がそれぞれ拒否される。"""
    ledger, path, source = _real_seed_revision()
    declaration = next(iter(ledger["declarations"].values()))
    mutated = _mutate_real_seed_revision(source, case, declaration["allowed"])

    violations = _migration_source_violations({path: mutated}, ledger=ledger)
    assert any(expected_violation in violation for violation in violations)
