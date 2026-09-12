"""Alembic revision 全件の DDL 境界を静的に検査する。"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from sqlalchemy import String

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
    assert _migration_source_violations(_migration_sources()) == []


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
