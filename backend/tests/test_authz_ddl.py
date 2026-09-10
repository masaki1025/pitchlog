"""認可 DDL 生成器の資産依存と静的な安全属性を検証する。"""

from __future__ import annotations

import ast
import copy
import json
import re
import subprocess
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

import pytest

from pitchlog.authz import ddl as authz_ddl

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPOSITORY_ROOT / "backend/src/pitchlog/authz/ddl.py"
DDL_ELEMENTS_PATH = REPOSITORY_ROOT / authz_ddl.DDL_ELEMENTS_PATH
BODY_MANIFEST_PATH = REPOSITORY_ROOT / authz_ddl.BODY_MANIFEST_PATH
SQL_FRAGMENT_RE = re.compile(
    r"\b(?:CREATE|ALTER|GRANT|REVOKE|SELECT|INSERT|UPDATE|DELETE)\b",
    re.IGNORECASE,
)


def _read_json_object(path: Path) -> dict[str, object]:
    """テスト資産の JSON object を読む。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert all(isinstance(key, str) for key in raw)
    return raw


def _manifest_rows() -> list[dict[str, object]]:
    """Manifest entry を型確認して返す。"""
    manifest = _read_json_object(BODY_MANIFEST_PATH)
    raw_entries = manifest["entries"]
    assert isinstance(raw_entries, list)
    entries: list[dict[str, object]] = []
    for raw_entry in raw_entries:
        assert isinstance(raw_entry, dict)
        entries.append(raw_entry)
    return entries


def _element_key(entry: dict[str, object]) -> tuple[str, str]:
    """Manifest entry から要素種別と ID を返す。"""
    element_type = entry["element_type"]
    element_id = entry["element_id"]
    assert isinstance(element_type, str)
    assert isinstance(element_id, str)
    return element_type, element_id


def _iter_element_paths(
    ddl_elements: dict[str, object],
    manifest_entries: list[dict[str, object]],
) -> Iterator[tuple[str, int, tuple[str, str]]]:
    """Manifest の母集合から DDL 要素行を件数リテラルなしで列挙する。"""
    ids_by_type: defaultdict[str, set[str]] = defaultdict(set)
    sections_by_type: defaultdict[str, set[str]] = defaultdict(set)
    for entry in manifest_entries:
        element_type, element_id = _element_key(entry)
        ids_by_type[element_type].add(element_id)
        path_text = entry["path"]
        assert isinstance(path_text, str)
        sections_by_type[element_type].add(
            PurePosixPath(path_text).parent.name.replace("-", "_")
        )

    for element_type, expected_ids in ids_by_type.items():
        assert len(sections_by_type[element_type]) == 1
        section_name = next(iter(sections_by_type[element_type]))
        rows = ddl_elements[section_name]
        assert isinstance(rows, list)
        assert rows
        assert all(isinstance(row, dict) for row in rows)
        common_keys = set(rows[0])
        for row in rows[1:]:
            common_keys.intersection_update(row)
        id_keys = [
            key
            for key in common_keys
            if {row[key] for row in rows if isinstance(row.get(key), str)}
            == expected_ids
        ]
        assert len(id_keys) == 1
        id_key = id_keys[0]
        for index, row in enumerate(rows):
            assert isinstance(row, dict)
            element_id = row[id_key]
            assert isinstance(element_id, str)
            yield section_name, index, (element_type, element_id)


def _authz_asset_snapshot() -> dict[str, bytes]:
    """凍結された認可資産を再帰的に生バイトで採取する。"""
    root = REPOSITORY_ROOT / "contracts/authz"
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _iter_identifier_values(value: object, key: str = "") -> Iterator[str]:
    """DDL 資産の ID・識別子・権限値を再帰採取する。"""
    if isinstance(value, dict):
        for child_key, child in value.items():
            if isinstance(child_key, str):
                yield from _iter_identifier_values(child, child_key)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_identifier_values(child, key)
    elif isinstance(value, str) and (key.endswith("_id") or key.endswith("_ids")):
        yield value


@pytest.fixture
def copied_repository(tmp_path: Path) -> Iterator[Path]:
    """Git object を共有する一時複製を作り、本物の資産を事後照合する。"""
    original_assets = _authz_asset_snapshot()
    copied_root = tmp_path / "repository"
    result = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--shared",
            str(REPOSITORY_ROOT),
            str(copied_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    yield copied_root

    assert _authz_asset_snapshot() == original_assets


def test_generate_authz_ddl_maps_every_manifest_entry() -> None:
    """公開 API が manifest の全要素を ID 付きで返す。"""
    generated = authz_ddl.generate_authz_ddl(REPOSITORY_ROOT)
    expected_keys = {_element_key(entry) for entry in _manifest_rows()}

    assert {(item.element_type, item.element_id) for item in generated} == expected_keys
    assert len(generated) == len(expected_keys)


def test_removing_each_ddl_element_changes_generated_statements() -> None:
    """DDL 資産の全要素を 1 件ずつ除く変異が生成物を必ず変える。"""
    original_assets = _authz_asset_snapshot()
    ddl_elements = _read_json_object(DDL_ELEMENTS_PATH)
    manifest_entries = _manifest_rows()
    body_entries = authz_ddl._read_verified_body_entries(REPOSITORY_ROOT)
    baseline = authz_ddl._assemble_statements(ddl_elements, body_entries)
    baseline_keys = {(item.element_type, item.element_id) for item in baseline}
    element_paths = tuple(_iter_element_paths(ddl_elements, manifest_entries))
    escaped: list[str] = []

    for section_name, index, removed_key in element_paths:
        mutated = copy.deepcopy(ddl_elements)
        section = mutated[section_name]
        assert isinstance(section, list)
        del section[index]
        generated = authz_ddl._assemble_statements(mutated, body_entries)
        generated_keys = {(item.element_type, item.element_id) for item in generated}
        if generated == baseline or generated_keys != baseline_keys - {removed_key}:
            escaped.append(f"{section_name}[{index}]")

    assert len(element_paths) == len(manifest_entries)
    assert escaped == []
    assert _authz_asset_snapshot() == original_assets


def test_generator_source_contains_no_sql_or_asset_identifier_literals() -> None:
    """生成器に SQL 断片も資産由来の識別子リテラルもない。"""
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    sql_fragments = sorted(
        literal for literal in string_literals if SQL_FRAGMENT_RE.search(literal)
    )
    asset_identifiers = set(
        _iter_identifier_values(_read_json_object(DDL_ELEMENTS_PATH))
    )

    assert sql_fragments == []
    assert string_literals.isdisjoint(asset_identifiers)


def test_generated_statements_retain_security_attributes() -> None:
    """FORCE RLS・PUBLIC 閉鎖・search_path 末尾を生成物で保持する。"""
    ddl_elements = _read_json_object(DDL_ELEMENTS_PATH)
    generated = authz_ddl.generate_authz_ddl(REPOSITORY_ROOT)
    by_key = {(item.element_type, item.element_id): item.sql for item in generated}

    tables = ddl_elements["tables"]
    assert isinstance(tables, list)
    for table in tables:
        assert isinstance(table, dict)
        table_id = table["table_id"]
        assert isinstance(table_id, str)
        if table["force_rls"] is True:
            assert "FORCE ROW LEVEL SECURITY" in by_key[("table", table_id)]

    functions = ddl_elements["functions"]
    assert isinstance(functions, list)
    for function in functions:
        assert isinstance(function, dict)
        function_id = function["function_id"]
        search_path = function["search_path"]
        assert isinstance(function_id, str)
        assert isinstance(search_path, list)
        assert all(isinstance(item, str) for item in search_path)
        assert search_path[-1] == "pg_temp"
        sql = by_key[("function", function_id)]
        assert "SECURITY DEFINER" in sql
        assert f"SET search_path = {', '.join(search_path)}" in sql
        if function["public_execute"] is False:
            assert re.search(
                r"REVOKE ALL PRIVILEGES\s+ON FUNCTION.+?\s+FROM PUBLIC;",
                sql,
                re.DOTALL,
            )


def test_generated_sql_is_the_digest_verified_manifest_body(
    copied_repository: Path,
) -> None:
    """SQL は body と同一で、digest 不一致 body は取り込まない。"""
    generated = authz_ddl.generate_authz_ddl(REPOSITORY_ROOT)
    for item in generated:
        assert item.sql == (REPOSITORY_ROOT / item.source_path).read_text(
            encoding="utf-8"
        )

    copied_manifest = _read_json_object(
        copied_repository / authz_ddl.BODY_MANIFEST_PATH
    )
    entries = copied_manifest["entries"]
    assert isinstance(entries, list)
    function_entry = next(
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("element_type") == "function"
    )
    assert isinstance(function_entry, dict)
    body_path_text = function_entry["path"]
    assert isinstance(body_path_text, str)
    body_path = copied_repository / body_path_text
    body_path.write_bytes(body_path.read_bytes() + b"\n-- digest mismatch\n")

    with pytest.raises(authz_ddl.AuthzDDLGenerationError, match="body静的照合"):
        authz_ddl.generate_authz_ddl(copied_repository)


def test_generated_statements_follow_asset_dependency_order() -> None:
    """ロールから ACL までを資産が宣言する依存順で返す。"""
    generated = authz_ddl.generate_authz_ddl(REPOSITORY_ROOT)
    positions: defaultdict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(generated):
        positions[item.element_type].append(index)

    assert max(positions["role"]) < min(positions["schema"])
    assert max(positions["schema"]) < min(positions["table"])
    assert max(positions["table"]) < min(positions["predicate"])
    assert max(positions["predicate"]) < min(positions["policy"])
    assert max(positions["policy"]) < min(positions["function"])
    first_acl = min(
        min(positions["acl_expectation"]),
        min(positions["column_acl_expectation"]),
    )
    assert max(positions["function"]) < first_acl
