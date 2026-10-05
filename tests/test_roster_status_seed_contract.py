"""在籍区分のシード資産、revision、要件書の一致を検査する。"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_ROOT = _REPOSITORY_ROOT / "backend"

_SEED_PATH = _REPOSITORY_ROOT / "contracts" / "seeds" / "roster-status.json"
_REVISION_PATH = (
    _BACKEND_ROOT / "migrations" / "versions" / "0027_seed_roster_status.py"
)
_REQUIREMENTS_PATH = (
    _REPOSITORY_ROOT / "docs" / "requirements" / "requirements-pitchlog-2026-07-22.md"
)
_EXPECTED_KEYS = {"active", "other", "ob"}
_EXPECTED_COLUMNS = {"key", "category", "display_name"}


def _source_inputs() -> tuple[str, str, str]:
    """照合に使う三つの原文を返す。

    Returns:
        シード JSON、revision、要件書のシステム固定行。
    """
    requirements = _REQUIREMENTS_PATH.read_text(encoding="utf-8")
    rows = [
        line
        for line in requirements.splitlines()
        if line.startswith("| システム固定 |") and "在籍区分（" in line
    ]
    assert len(rows) == 1
    return (
        _SEED_PATH.read_text(encoding="utf-8"),
        _REVISION_PATH.read_text(encoding="utf-8"),
        rows[0],
    )


def _bulk_insert_call(tree: ast.Module) -> ast.Call:
    """Upgrade 内の唯一の bulk_insert 呼び出しを返す。

    Args:
        tree: revision の構文木。

    Returns:
        投入呼び出し。
    """
    upgrades = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    ]
    assert len(upgrades) == 1
    calls = [
        node
        for node in ast.walk(upgrades[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        and node.func.attr == "bulk_insert"
    ]
    assert len(calls) == 1
    return calls[0]


def _revision_rows(source: str) -> list[dict[str, str]]:
    """Revision の投入先と行リテラルを構文木から読む。

    Args:
        source: revision の Python ソース。

    Returns:
        投入する行のリスト。
    """
    call = _bulk_insert_call(ast.parse(source))
    assert len(call.args) == 2
    table = call.args[0]
    assert isinstance(table, ast.Call)
    assert isinstance(table.func, ast.Attribute)
    assert isinstance(table.func.value, ast.Name)
    assert (table.func.value.id, table.func.attr) == ("sa", "table")
    assert table.args and ast.literal_eval(table.args[0]) == "system_vocabularies"
    rows = call.args[1]
    assert isinstance(rows, ast.List)
    assert all(isinstance(row, ast.Dict) for row in rows.elts)
    return [ast.literal_eval(row) for row in rows.elts]


def _assert_seed_contract(
    seed_json: str, revision_source: str, requirement_row: str
) -> None:
    """三つの原文が同じ在籍区分を定めていると確認する。

    Args:
        seed_json: 正とするシード資産の JSON 文字列。
        revision_source: DB 投入側の Python ソース。
        requirement_row: 要件書 4.0-3 のシステム固定行。
    """
    seed_rows: list[dict[str, str]] = json.loads(seed_json)
    revision_rows = _revision_rows(revision_source)
    assert seed_rows == revision_rows, "A: seed と revision の行が異なる"
    assert all(set(row) == _EXPECTED_COLUMNS for row in seed_rows), (
        "E: seed の列集合が契約と異なる"
    )
    assert all(set(row) == _EXPECTED_COLUMNS for row in revision_rows), (
        "E: revision の列集合が契約と異なる"
    )
    assert {row["key"] for row in seed_rows} == _EXPECTED_KEYS, "B: キーが裁定と異なる"
    match = re.search(r"在籍区分（([^）]+)）", requirement_row)
    assert match is not None, "C: 要件書の在籍区分を読めない"
    labels = match.group(1).split("/")
    assert [row["display_name"] for row in seed_rows] == labels, (
        "C: 表示名または順序が要件書と異なる"
    )
    assert len(seed_rows) == 3, "D: 行数が 3 ではない"
    assert all(row["category"] == "roster_status" for row in seed_rows), (
        "D: category が roster_status ではない"
    )


def _rewrite_revision_row(
    source: str,
    *,
    field: str | None = None,
    value: str | None = None,
    remove: bool = False,
) -> str:
    """ファイルを変更せず、構文木上の最初の投入行だけを変える。

    Args:
        source: 元の revision ソース。
        field: 書き換える列名。
        value: 新しい列値。
        remove: 最初の行を削除するか。

    Returns:
        変異後の revision ソース。
    """
    tree = ast.parse(source)
    rows = _bulk_insert_call(tree).args[1]
    assert isinstance(rows, ast.List)
    if remove:
        rows.elts.pop(0)
    else:
        assert field is not None and value is not None
        first = rows.elts[0]
        assert isinstance(first, ast.Dict)
        index = next(
            i
            for i, key in enumerate(first.keys)
            if key is not None and ast.literal_eval(key) == field
        )
        first.values[index] = ast.copy_location(
            ast.Constant(value=value), first.values[index]
        )
    return ast.unparse(tree)


def _add_revision_column(source: str) -> str:
    """投入先の列宣言と全行へ同じ余分な列を追加する。

    Args:
        source: 元の revision ソース。

    Returns:
        メモリ上で変異させた revision ソース。
    """
    tree = ast.parse(source)
    call = _bulk_insert_call(tree)
    table, rows = call.args
    assert isinstance(table, ast.Call) and isinstance(rows, ast.List)
    table.args.append(
        ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="sa", ctx=ast.Load()), attr="column", ctx=ast.Load()
            ),
            args=[
                ast.Constant(value="disabled"),
                ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="sa", ctx=ast.Load()),
                        attr="Boolean",
                        ctx=ast.Load(),
                    ),
                    args=[],
                    keywords=[],
                ),
            ],
            keywords=[],
        )
    )
    for row in rows.elts:
        assert isinstance(row, ast.Dict)
        row.keys.append(ast.Constant(value="disabled"))
        row.values.append(ast.Constant(value=True))
    return ast.unparse(ast.fix_missing_locations(tree))


def _mutated_inputs(case: str, seed_json: str, revision_source: str) -> tuple[str, str]:
    """各負例に必要な入力だけをメモリ上で変える。

    Args:
        case: 負例の種類。
        seed_json: 元のシード JSON。
        revision_source: 元の revision ソース。

    Returns:
        変異したシード JSON と revision ソース。
    """
    rows: list[dict[str, str]] = json.loads(seed_json)
    if case == "seed_typo":
        rows[0]["display_name"] = rows[0]["display_name"][:-1] + "誤"
    elif case == "revision_row_missing":
        revision_source = _rewrite_revision_row(revision_source, remove=True)
    elif case == "same_wrong_key":
        rows[0]["key"] = "outside"
        revision_source = _rewrite_revision_row(
            revision_source, field="key", value=rows[0]["key"]
        )
    elif case == "same_wrong_label":
        rows[0]["display_name"] = rows[0]["display_name"][:-1] + "誤"
        revision_source = _rewrite_revision_row(
            revision_source, field="display_name", value=rows[0]["display_name"]
        )
    elif case == "same_extra_column":
        expanded_rows: list[dict[str, object]] = [
            row | {"disabled": True} for row in rows
        ]
        return json.dumps(expanded_rows, ensure_ascii=False), _add_revision_column(
            revision_source
        )
    else:
        raise AssertionError(f"未知の負例: {case}")
    return json.dumps(rows, ensure_ascii=False), revision_source


def test_roster_status_seed_contract_matches() -> None:
    """実物の三つの原文がすべて一致する。"""
    _assert_seed_contract(*_source_inputs())


@pytest.mark.parametrize(
    ("case", "expected_check"),
    [
        ("seed_typo", "A"),
        ("revision_row_missing", "A"),
        ("same_wrong_key", "B"),
        ("same_wrong_label", "C"),
        ("same_extra_column", "E"),
    ],
)
def test_roster_status_seed_mutations_are_red(case: str, expected_check: str) -> None:
    """片側または両側を変えた五つの負例を所定の検査で拒否する。

    Args:
        case: 負例の種類。
        expected_check: 失敗すべき検査。
    """
    seed_json, revision_source, requirement_row = _source_inputs()
    mutated_seed, mutated_revision = _mutated_inputs(case, seed_json, revision_source)
    with pytest.raises(AssertionError, match=rf"^{expected_check}:"):
        _assert_seed_contract(mutated_seed, mutated_revision, requirement_row)
