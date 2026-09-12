"""Alembic revision 全件の DDL 境界を静的に検査する。"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_VERSIONS_ROOT = _BACKEND_ROOT / "migrations" / "versions"
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


def _migration_source_violations(sources: Mapping[str, str]) -> list[str]:
    """Revision の Python 構文木から禁止 SQL と禁止 API の使用を返す。

    ``BEFORE UPDATE OR DELETE`` のようなトリガ DDL は文頭の DML 文ではないため、
    DML として数えない。

    Args:
        sources: 表示用パスと Python ソースの対応。

    Returns:
        パス・行番号・禁止要素だけを含む違反一覧。
    """
    violations: list[str] = []
    for path, source in sorted(sources.items()):
        tree = ast.parse(source, filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                name = (
                    function.attr
                    if isinstance(function, ast.Attribute)
                    else function.id
                    if isinstance(function, ast.Name)
                    else None
                )
                if name in _FORBIDDEN_CALLS:
                    violations.append(f"{path}:{node.lineno}: 禁止 API {name}()")
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            for match in _FORBIDDEN_SQL.finditer(node.value):
                line = node.lineno + node.value.count("\n", 0, match.start())
                statement = " ".join(match[0].split())
                violations.append(f"{path}:{line}: 禁止 SQL {statement}")
    return violations


def test_all_migration_revisions_contain_only_schema_ddl() -> None:
    """走査で得た全 revision に権限 DDL・create_all・DML がないことを確認する。"""
    paths = sorted(_VERSIONS_ROOT.rglob("*.py"))
    assert paths, "migration revision が 1 件もない"
    sources = {
        str(path.relative_to(_BACKEND_ROOT)): path.read_text(encoding="utf-8")
        for path in paths
    }

    assert _migration_source_violations(sources) == []


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
